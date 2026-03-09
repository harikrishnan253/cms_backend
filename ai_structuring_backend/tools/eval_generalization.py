#!/usr/bin/env python3
"""
tools/eval_generalization.py

Offline ablation & generalization evaluation for the document structuring pipeline.
No LLM API calls required.

ABLATION MODES (additive, each builds on the previous):
  baseline    normalize_tag(gold_tag) only — minimum normalization
  alias       + style alias candidates from style_alias_candidates.json (conf >= 0.70)
  semantic    + semantic zone-prior hints + transition-prior hints from corpus artifacts
  rules       + learned rules via RuleLearner.apply_rules() as primary predictor
  retriever   + TF-IDF grounded retriever [DEV ONLY — DATA LEAKAGE RISK]

HOLDOUT STRATEGIES:
  book        doc-level random split (default 20%, seed-reproducible)
  publisher   hold out all docs from a random subset of publishers (book families)

METRICS:
  accuracy          overall canonical tag accuracy on holdout set
  zone_violation    % predictions invalid for their document zone
  list_depth        accuracy on BL2/BL3/NL2/NL3 depth-2/3 list entries
  table_sem         accuracy on TABLE-zone entries
  ref_accuracy      accuracy on BACK_MATTER/REFERENCE zone entries
  txt_fallback      % predictions that fell back to TXT or TXT-FLUSH
  unmapped_rate     % entries with canonical_gold_tag == UNMAPPED (excluded from accuracy)

Usage:
  cd AI-structuring/backend
  python tools/eval_generalization.py
  python tools/eval_generalization.py --split publisher --modes all
  python tools/eval_generalization.py --split book --holdout-fraction 0.3 --seed 7
  python tools/eval_generalization.py --modes baseline alias semantic rules --report-file outputs/eval.txt
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------
# Ensure backend/ is on sys.path so internal imports work
# -----------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------
_DATA_DIR = _BACKEND / "data"
_GROUND_TRUTH_PATH = _DATA_DIR / "ground_truth.jsonl"
_LEARNED_RULES_PATH = _DATA_DIR / "learned_rules.json"
_ALLOWED_STYLES_PATH = _BACKEND / "config" / "allowed_styles.json"
_ALIAS_CANDIDATES_PATH = _DATA_DIR / "style_alias_candidates.json"
_SEMANTIC_KNOWLEDGE_PATH = _DATA_DIR / "tag_semantics_knowledge.json"
_SEMANTIC_TRANSITIONS_PATH = _DATA_DIR / "tag_transition_priors.json"

# -----------------------------------------------------------------------
# Zone normalization  (GT lowercase → pipeline uppercase)
# -----------------------------------------------------------------------
_GT_ZONE_NORM: Dict[str, str] = {
    "body": "BODY",
    "reference": "BACK_MATTER",
    "back_matter": "BACK_MATTER",
    "front_matter": "FRONT_MATTER",
    "table": "TABLE",
    "appendix": "BACK_MATTER",
    "index": "BACK_MATTER",
    "glossary": "BACK_MATTER",
    "exercise": "EXERCISE",
    "box": "BOX_NBX",
    "nbx": "BOX_NBX",
    "bx1": "BOX_BX1",
    "bx2": "BOX_BX2",
    "bx3": "BOX_BX3",
    "bx4": "BOX_BX4",
    "bx6": "BOX_BX6",
    "bx7": "BOX_BX7",
    "bx15": "BOX_BX15",
    "bx16": "BOX_BX16",
}

# Maps pipeline zone → artifact zone key used in tag_semantics_knowledge.json
_ARTIFACT_ZONE_MAP: Dict[str, str] = {
    "BODY": "BODY",
    "BACK_MATTER": "REFERENCE",
    "FRONT_MATTER": "BODY",  # fallback: BODY priors for FRONT_MATTER
}

# Zones that have non-empty ZONE_VALID_STYLES restrictions (zone violation is checkable)
_RESTRICTED_ZONES = {
    "FRONT_MATTER", "TABLE", "BACK_MATTER", "EXERCISE",
    "BOX_NBX", "BOX_BX1", "BOX_BX2", "BOX_BX3",
    "BOX_BX4", "BOX_BX6", "BOX_BX7", "BOX_BX15", "BOX_BX16",
}


def _norm_zone(zone_raw: str) -> str:
    """Normalize a ground-truth zone string to the pipeline zone name."""
    return _GT_ZONE_NORM.get(zone_raw.lower().strip(), "BODY")


# -----------------------------------------------------------------------
# Publisher extraction from doc_id
# -----------------------------------------------------------------------
_PUBLISHER_RE = re.compile(r"^([A-Za-z]+)")


def _extract_publisher(doc_id: str) -> str:
    """Extract publisher/author prefix from a doc_id like 'Acharya9781975261764-ch002_tag'."""
    m = _PUBLISHER_RE.match(doc_id)
    return m.group(1).lower() if m else "unknown"


# -----------------------------------------------------------------------
# Metric category helpers
# -----------------------------------------------------------------------
_LIST_DEPTH_RE = re.compile(r"(?:^|[-_])(BL[23]|NL[23])[-_]", re.IGNORECASE)


def _is_list_depth(tag: str) -> bool:
    """Return True if tag is a depth-2/3 list tag (BL2/BL3/NL2/NL3 variants)."""
    return bool(_LIST_DEPTH_RE.search(tag))


# Structural-semantics detectors used by structure-guard simulation.
# Intentionally excludes TBL-FIRST/MID/LAST (table rows, not lists).
_LIST_TAG_RE = re.compile(r"(?:^|[-_])(BL|NL|UL)\d*(?:[-_]|$)", re.IGNORECASE)
_HEADING_TAG_RE = re.compile(r"^(H[1-9]|TH[1-9]|CH)$")

# TABLE-zone tags shown in the per-tag detail section (focus tags first).
_TABLE_FOCUS_TAGS: List[str] = ["T", "T1", "T2", "T4", "TFN", "TSN"]


def _is_list_tag(tag: str) -> bool:
    """True if *tag* encodes list semantics (BL/NL/UL family, any nesting level)."""
    return bool(_LIST_TAG_RE.search(tag))


def _is_heading_tag(tag: str) -> bool:
    """True if *tag* is a standalone heading (H1–H9, TH1–TH9, or CH)."""
    return bool(_HEADING_TAG_RE.match(tag))


# -----------------------------------------------------------------------
# Data loaders
# -----------------------------------------------------------------------
def _load_allowed_styles(path: Path = _ALLOWED_STYLES_PATH) -> set:
    """Load allowed canonical styles from config/allowed_styles.json."""
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except Exception as exc:
        logger.warning("Failed to load allowed styles: %s", exc)
        return set()


def _load_alias_map(
    path: Path = _ALIAS_CANDIDATES_PATH,
    min_confidence: float = 0.70,
) -> Dict[str, str]:
    """Load high-confidence alias candidates → {raw_style: canonical_tag}."""
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        result: Dict[str, str] = {}
        for c in data.get("candidates", []):
            if (
                c.get("recommendation") == "add_alias"
                and c.get("in_allowed_styles", False)
                and c.get("confidence", 0.0) >= min_confidence
            ):
                result[c["raw_style"]] = c["suggested_canonical"]
        logger.info(
            "Loaded %d alias entries (min_confidence=%.2f)", len(result), min_confidence
        )
        return result
    except Exception as exc:
        logger.warning("Failed to load alias candidates: %s", exc)
        return {}


def _load_semantic_artifacts(
    knowledge_path: Path = _SEMANTIC_KNOWLEDGE_PATH,
    transitions_path: Path = _SEMANTIC_TRANSITIONS_PATH,
) -> dict:
    """Load semantic knowledge artifacts; returns {} on any error."""
    try:
        from processor.rule_learner import load_semantic_artifacts

        return load_semantic_artifacts(
            knowledge_path=knowledge_path, transitions_path=transitions_path
        )
    except Exception as exc:
        logger.warning("Failed to load semantic artifacts: %s", exc)
        return {}


def _load_normalize_tag() -> Callable:
    """Load normalize_tag from app.services.style_normalizer; use fallback if unavailable."""
    try:
        from app.services.style_normalizer import normalize_tag as _impl

        return _impl
    except ImportError:
        allowed = _load_allowed_styles()

        def _fallback(tag: str, meta: Optional[dict] = None) -> str:
            return tag if tag in allowed else "TXT"

        logger.warning(
            "app.services.style_normalizer not importable — using simple fallback for normalize_tag"
        )
        return _fallback


# -----------------------------------------------------------------------
# Context builder: flatten ground_truth with prev_tag chain
# -----------------------------------------------------------------------
def build_context(gt: Dict[str, List[Dict]]) -> List[Dict]:
    """Flatten a ground_truth dict into an ordered list with prev_canonical_tag added.

    Entries with canonical_gold_tag == UNMAPPED still appear in the list (so
    zone_violation and unmapped_rate can be computed) but do NOT advance prev_canonical_tag.
    """
    result: List[Dict] = []
    for doc_id in sorted(gt.keys()):
        entries = sorted(gt[doc_id], key=lambda e: e.get("para_index", 0))
        prev_canonical = "START"
        for entry in entries:
            enriched = dict(entry)
            enriched["prev_canonical_tag"] = prev_canonical
            result.append(enriched)
            # Advance only on non-UNMAPPED entries
            tag = entry.get("canonical_gold_tag", "")
            if tag and tag != "UNMAPPED":
                prev_canonical = tag
    return result


# -----------------------------------------------------------------------
# Predictors
# -----------------------------------------------------------------------
class Predictors:
    """Container for ablation-mode prediction functions.

    Each predict_* method receives a context entry (dict with prev_canonical_tag
    populated by build_context) and returns the predicted canonical tag string.

    Modes are additive:
      baseline → alias → semantic → rules → retriever
    """

    def __init__(
        self,
        normalize_tag_fn: Callable,
        alias_map: Dict[str, str],
        artifacts: dict,
        allowed_styles: set,
        learner: Any = None,
        retriever: Any = None,
    ) -> None:
        self._norm = normalize_tag_fn
        self._aliases = alias_map
        self._artifacts = artifacts
        self._allowed = allowed_styles
        self._learner = learner
        self._retriever = retriever

    # ---- mode: baseline ----
    def predict_baseline(self, entry: dict) -> str:
        """normalize_tag(gold_tag) only."""
        return self._norm(entry.get("gold_tag", "TXT"))

    # ---- mode: + alias ----
    def predict_alias(self, entry: dict) -> str:
        """High-confidence alias candidates + normalize_tag."""
        gold = entry.get("gold_tag", "TXT")
        if gold in self._aliases:
            return self._aliases[gold]
        return self._norm(gold)

    # ---- mode: + semantic priors ----
    def predict_semantic(self, entry: dict) -> str:
        """Alias chain + zone-prior hint + transition-prior hint."""
        result = self.predict_alias(entry)
        if result not in {"TXT", "TXT-FLUSH"}:
            return result

        zone = _norm_zone(entry.get("zone", "body"))

        # Zone prior: if a single tag dominates this zone (freq >= 0.40), use it
        artifact_zone = _ARTIFACT_ZONE_MAP.get(zone)
        if artifact_zone:
            zone_data = (
                self._artifacts.get("zone_tag_priors", {})
                .get(artifact_zone, {})
            )
            dist = zone_data.get("distribution", {})
            if dist:
                top_tag, top_stats = max(
                    dist.items(), key=lambda x: x[1].get("frequency", 0)
                )
                if top_stats.get("frequency", 0) >= 0.40 and top_tag in self._allowed:
                    return top_tag

        # Transition prior: if previous tag strongly predicts a next tag, use it
        # Use gold prev_tag (not predicted) to isolate this mode's effect
        prev = entry.get("prev_canonical_tag", "START")
        if prev not in {"START", "UNMAPPED", ""}:
            src_trans = self._artifacts.get("global_transitions", {}).get(prev, {})
            next_dist = src_trans.get("next_tag_distribution", {})
            for next_tag, t_stats in sorted(
                next_dist.items(), key=lambda x: -x[1].get("probability", 0)
            ):
                if t_stats.get("probability", 0) >= 0.75 and next_tag in self._allowed:
                    return next_tag
                break  # only check the top-1 transition

        return result

    # ---- mode: + learned rules ----
    def predict_rules(self, entry: dict) -> str:
        """apply_rules() as primary predictor; semantic chain as fallback."""
        if self._learner and self._learner.rules:
            zone = _norm_zone(entry.get("zone", "body"))
            predicted = self._learner.apply_rules(
                entry.get("text", ""), {"context_zone": zone}
            )
            if predicted:
                return predicted
        return self.predict_semantic(entry)

    # ---- mode: + retriever (dev-only) ----
    def predict_retriever(self, entry: dict) -> str:
        """Rules chain + TF-IDF grounded retriever as final fallback.

        WARNING: When the retriever is initialized with the full ground_truth.jsonl
        (including holdout docs), the results are contaminated by data leakage.
        Use only as a dev-time upper-bound estimate.
        """
        result = self.predict_rules(entry)
        if result not in {"TXT", "TXT-FLUSH"}:
            return result
        if self._retriever:
            zone = _norm_zone(entry.get("zone", "body"))
            try:
                examples = self._retriever.retrieve_examples(
                    entry.get("text", ""), k=3, zone=zone
                )
                if examples:
                    return examples[0].get("canonical_gold_tag", result)
            except Exception as exc:
                logger.debug("Retriever error for entry: %s", exc)
        return result


# -----------------------------------------------------------------------
# Metrics computation
# -----------------------------------------------------------------------
def compute_metrics(
    predictions: List[str],
    entries: List[Dict],
    allowed_styles: set,
) -> Dict[str, Any]:
    """Compute all 7 evaluation metrics for one ablation mode.

    Skips entries with canonical_gold_tag == UNMAPPED for accuracy/precision metrics,
    but counts them for unmapped_rate.

    Returns:
        dict with keys: accuracy, zone_violation_rate, list_depth_accuracy,
        table_sem_accuracy, ref_accuracy, txt_fallback_rate, unmapped_rate,
        and _n_* sample-size keys for each metric category.
    """
    try:
        from processor.zone_styles import get_allowed_styles_for_zone as _gasz

        def zone_valid(zone: str) -> set:
            return _gasz(zone, allowed_styles)

    except ImportError:
        def zone_valid(zone: str) -> set:  # type: ignore[misc]
            return allowed_styles

    # Precompute zone-specific style sets for fast category membership
    table_styles: set = zone_valid("TABLE")
    ref_styles: set = zone_valid("BACK_MATTER")

    total = 0
    correct = 0
    zone_violations = 0
    zone_checkable = 0
    list_depth_total = 0
    list_depth_correct = 0
    table_total = 0
    table_correct = 0
    ref_total = 0
    ref_correct = 0
    txt_fallback = 0
    unmapped_n = 0
    # New metrics
    invalid_n = 0       # predictions not in allowed_styles
    sg_fail = 0         # simulated structure-guard failures (list/heading mismatch)
    sg_checkable = 0    # entries where the gold tag is a list or heading
    table_per_tag: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "total": 0}
    )

    for entry, pred in zip(entries, predictions):
        gold = entry.get("canonical_gold_tag", "")
        if gold == "UNMAPPED" or not gold:
            unmapped_n += 1
            continue

        total += 1
        zone = _norm_zone(entry.get("zone", "body"))
        is_correct = pred == gold

        if is_correct:
            correct += 1

        # Invalid tag: prediction is outside the canonical allowed-styles set
        if pred not in allowed_styles:
            invalid_n += 1

        # Structure-guard simulation
        # Failure = gold and pred have different list-or-heading semantics, i.e.
        # the reconstruction would change the structural type of the paragraph.
        # Only evaluated when gold is itself a list or heading (the gate fires on
        # source-side classification, so neutral gold tags are not checkable here).
        gold_is_list = _is_list_tag(gold)
        pred_is_list = _is_list_tag(pred)
        gold_is_heading = _is_heading_tag(gold)
        pred_is_heading = _is_heading_tag(pred)
        if gold_is_list or gold_is_heading:
            sg_checkable += 1
            if (gold_is_list != pred_is_list) or (gold_is_heading != pred_is_heading):
                sg_fail += 1

        # Zone violation (only for zones with explicit restrictions)
        if zone in _RESTRICTED_ZONES:
            zone_checkable += 1
            if pred not in zone_valid(zone):
                zone_violations += 1

        # List-depth entries (BL2/BL3/NL2/NL3 and variants)
        if _is_list_depth(gold):
            list_depth_total += 1
            if is_correct:
                list_depth_correct += 1

        # Table semantics: TABLE zone or tag is a table-specific style
        if zone == "TABLE" or gold in table_styles:
            table_total += 1
            if is_correct:
                table_correct += 1

        # TABLE per-tag breakdown (same gate as table_sem_accuracy)
        if zone == "TABLE" or gold in table_styles:
            table_per_tag[gold]["total"] += 1
            if is_correct:
                table_per_tag[gold]["correct"] += 1

        # Reference / back-matter: BACK_MATTER zone or tag is a back-matter style
        if zone in {"BACK_MATTER", "REFERENCE"} or gold in ref_styles:
            ref_total += 1
            if is_correct:
                ref_correct += 1

        # TXT fallback
        if pred in {"TXT", "TXT-FLUSH"}:
            txt_fallback += 1

    grand_total = total + unmapped_n
    return {
        "accuracy": correct / total if total else 0.0,
        "zone_violation_rate": zone_violations / zone_checkable if zone_checkable else 0.0,
        "list_depth_accuracy": list_depth_correct / list_depth_total if list_depth_total else None,
        "table_sem_accuracy": table_correct / table_total if table_total else None,
        "ref_accuracy": ref_correct / ref_total if ref_total else None,
        "txt_fallback_rate": txt_fallback / total if total else 0.0,
        "unmapped_rate": unmapped_n / grand_total if grand_total else 0.0,
        # New metrics
        "invalid_tag_rate": invalid_n / total if total else 0.0,
        "structure_guard_fail_rate": sg_fail / sg_checkable if sg_checkable else 0.0,
        "table_per_tag": {
            tag: {
                "accuracy": v["correct"] / v["total"] if v["total"] else 0.0,
                "n": v["total"],
            }
            for tag, v in sorted(table_per_tag.items())
        },
        # Sample sizes for context
        "_n_total": total,
        "_n_zone_checkable": zone_checkable,
        "_n_list_depth": list_depth_total,
        "_n_table": table_total,
        "_n_ref": ref_total,
        "_n_unmapped": unmapped_n,
        "_n_invalid": invalid_n,
        "_n_sg_checkable": sg_checkable,
    }


# -----------------------------------------------------------------------
# Publisher-level holdout split
# -----------------------------------------------------------------------
def split_holdout_publisher(
    ground_truth: Dict[str, List],
    holdout_fraction: float = 0.2,
    seed: int = 42,
) -> Tuple[Dict, Dict, List[str]]:
    """Split ground_truth by publisher prefix, holding out entire book families.

    Publisher prefix is extracted from doc_id (e.g. "Acharya" from
    "Acharya9781975261764-ch002_tag").

    Args:
        ground_truth: {doc_id -> entries}
        holdout_fraction: fraction of publishers to hold out (default 0.2)
        seed: RNG seed for reproducibility

    Returns:
        (train_gt, holdout_gt, holdout_doc_ids)
    """
    import random

    rng = random.Random(seed)

    by_publisher: Dict[str, List[str]] = defaultdict(list)
    for doc_id in sorted(ground_truth.keys()):
        by_publisher[_extract_publisher(doc_id)].append(doc_id)

    publishers = sorted(by_publisher.keys())
    n_holdout = max(1, round(len(publishers) * holdout_fraction))
    holdout_pubs = set(rng.sample(publishers, n_holdout))

    holdout_gt: Dict[str, List] = {}
    train_gt: Dict[str, List] = {}
    holdout_doc_ids: List[str] = []

    for pub, doc_ids in by_publisher.items():
        for doc_id in doc_ids:
            if pub in holdout_pubs:
                holdout_gt[doc_id] = ground_truth[doc_id]
                holdout_doc_ids.append(doc_id)
            else:
                train_gt[doc_id] = ground_truth[doc_id]

    holdout_doc_ids.sort()
    logger.info(
        "Publisher holdout: %d train docs / %d holdout docs  (held-out publishers: %s)",
        len(train_gt),
        len(holdout_gt),
        sorted(holdout_pubs),
    )
    return train_gt, holdout_gt, holdout_doc_ids


# -----------------------------------------------------------------------
# Table semantics per-tag breakdown helper
# -----------------------------------------------------------------------

def _format_table_breakdown(results: Dict[str, Dict], modes_run: List[str]) -> List[str]:
    """Return lines for the per-tag TABLE-zone accuracy breakdown across ablation modes.

    Focus tags (T, T1, T2, T4, TFN, TSN) appear first, then all other TABLE tags
    in alphabetical order.  Entries that never appear in the TABLE zone across any
    mode are skipped.

    Args:
        results: {mode_name -> metrics_dict} from run_evaluation()
        modes_run: ordered list of mode names to show as columns

    Returns:
        List of formatted lines to append to the report.
    """
    # Gather all TABLE-zone gold tags that appear in at least one mode
    all_tags: set = set()
    for mode in modes_run:
        per_tag = results.get(mode, {}).get("table_per_tag", {})
        all_tags.update(per_tag.keys())
    if not all_tags:
        return []

    # Focus tags first, then alphabetical remainder
    sorted_tags = [t for t in _TABLE_FOCUS_TAGS if t in all_tags]
    sorted_tags += sorted(all_tags - set(_TABLE_FOCUS_TAGS))

    # Build header
    tag_col = 16
    cell_w = 18  # "  xx.x% (n=NNN)" fits in 18 chars
    header = f"  {'Tag':<{tag_col}}"
    for mode in modes_run:
        label = _MODE_LABELS.get(mode, mode)
        header += f"  {label:>{cell_w}}"
    sep = "-" * min(120, tag_col + 4 + cell_w * len(modes_run) + 2 * len(modes_run))

    lines = [
        "",
        "TABLE SEMANTICS DETAIL  (TABLE-zone, per gold-tag accuracy across modes)",
        sep,
        header,
        sep,
    ]

    for tag in sorted_tags:
        row = f"  {tag:<{tag_col}}"
        for mode in modes_run:
            per_tag = results.get(mode, {}).get("table_per_tag", {})
            if tag in per_tag:
                s = per_tag[tag]
                cell = f"{s['accuracy'] * 100:5.1f}% (n={s['n']})"
                row += f"  {cell:>{cell_w}}"
            else:
                row += f"  {'N/A':>{cell_w}}"
        lines.append(row)

    lines.append(sep)
    return lines


# -----------------------------------------------------------------------
# Report formatting
# -----------------------------------------------------------------------
_MODE_LABELS: Dict[str, str] = {
    "baseline": "baseline",
    "alias": "+ alias",
    "semantic": "+ semantic priors",
    "rules": "+ learned rules",
    "retriever": "+ retriever [LEAKAGE]",
}


def _fmt_opt(v: Optional[float]) -> str:
    """Format an optional percentage value for the table."""
    if v is None:
        return "  N/A   "
    return f"{v * 100:6.1f}% "


def format_report(
    results: Dict[str, Dict],
    split_type: str,
    holdout_doc_ids: List[str],
    n_train_docs: int,
    n_holdout_docs: int,
    modes_run: List[str],
    retriever_leakage_warning: bool = False,
) -> str:
    """Format the ablation comparison table as a readable string.

    Columns in the main table:
      Accuracy   — overall tag accuracy on the holdout set
      ZoneViol   — % predictions invalid for their document zone
      ListDepth  — accuracy on BL2/BL3/NL2/NL3 depth-2+ entries
      TableSem   — accuracy on TABLE-zone entries (all table tags)
      RefAcc     — accuracy on BACK_MATTER/REFERENCE entries
      TXTFall    — % predictions that fell back to TXT/TXT-FLUSH
      Unmapped   — % entries with UNMAPPED gold (skipped from accuracy)
      Invalid%   — % predictions NOT in the canonical allowed-styles set
      SG-Fail%   — simulated structure-guard failure rate: % list/heading
                   entries whose predicted tag changes structural semantics
                   (↓ = fewer spurious semantic changes = better)
    """
    W = 120  # report body width
    col_w = 24

    # Header
    lines = [
        "=" * W,
        "GENERALIZATION EVALUATION REPORT",
        "=" * W,
        f"Split strategy  : {split_type}",
        f"Train docs      : {n_train_docs}",
        (
            f"Holdout docs    : {n_holdout_docs}  "
            f"({', '.join(holdout_doc_ids[:8])}"
            f"{'…' if len(holdout_doc_ids) > 8 else ''})"
        ),
    ]

    if retriever_leakage_warning:
        lines += [
            "",
            "*** RETRIEVER LEAKAGE WARNING ***",
            "    The grounded retriever indexes ALL docs including holdout docs.",
            "    Results marked [LEAKAGE] are for dev-time upper-bound estimation only.",
            "    Do NOT use these to judge held-out generalization.",
        ]

    # Ablation table (10 columns)
    lines += [
        "",
        "ABLATION RESULTS",
        "=" * W,
        (
            f"{'Mode':<{col_w}}  {'Accuracy':>8}  {'ZoneViol':>8}  "
            f"{'ListDepth':>9}  {'TableSem':>8}  {'RefAcc':>7}  "
            f"{'TXTFall':>8}  {'Unmapped':>8}  {'Invalid%':>8}  {'SG-Fail%':>8}"
        ),
        "-" * W,
    ]

    for mode in modes_run:
        m = results.get(mode)
        if m is None:
            continue
        label = _MODE_LABELS.get(mode, mode)
        lines.append(
            f"{label:<{col_w}}  "
            f"{m['accuracy'] * 100:7.1f}%  "
            f"{m['zone_violation_rate'] * 100:7.1f}%  "
            f"{_fmt_opt(m['list_depth_accuracy']):>9}  "
            f"{_fmt_opt(m['table_sem_accuracy']):>8}  "
            f"{_fmt_opt(m['ref_accuracy']):>7}  "
            f"{m['txt_fallback_rate'] * 100:7.1f}%  "
            f"{m['unmapped_rate'] * 100:7.1f}%  "
            f"{m.get('invalid_tag_rate', 0.0) * 100:7.1f}%  "
            f"{m.get('structure_guard_fail_rate', 0.0) * 100:7.1f}%"
        )

    # Sample sizes (from first mode)
    first = results.get(modes_run[0]) if modes_run else None
    if first:
        lines += [
            "",
            "Sample sizes (holdout set):",
            f"  total (non-UNMAPPED)              = {first['_n_total']}",
            f"  zone-checkable (restricted zones) = {first['_n_zone_checkable']}",
            f"  list-depth entries (BL2/NL2/…)   = {first['_n_list_depth']}",
            f"  table entries                     = {first['_n_table']}",
            f"  reference/back-matter entries     = {first['_n_ref']}",
            f"  UNMAPPED entries (skipped)        = {first['_n_unmapped']}",
            f"  SG-checkable (list or heading)    = {first.get('_n_sg_checkable', 'N/A')}",
        ]

    # Incremental delta table vs baseline
    if len(modes_run) > 1 and "baseline" in results:
        base = results["baseline"]
        lines += [
            "",
            "INCREMENTAL GAIN VS BASELINE  (+Accuracy/ListDepth/TableSem/RefAcc = better;"
            " -ZoneViol/TXTFall/Invalid%%/SG-Fail%% = better)",
            "-" * W,
            (
                f"{'Mode':<{col_w}}  {'dAccuracy':>10}  {'dZoneViol':>10}  "
                f"{'dListDepth':>10}  {'dTableSem':>10}  {'dRefAcc':>9}  "
                f"{'dInvalid%':>10}  {'dSG-Fail%':>10}"
            ),
        ]
        for mode in modes_run:
            if mode == "baseline":
                continue
            m = results.get(mode)
            if m is None:
                continue
            label = _MODE_LABELS.get(mode, mode)

            def delta(key: str, m: dict = m, base: dict = base) -> str:
                a, b = m.get(key), base.get(key)
                if a is None or b is None:
                    return "      N/A"
                return f"{(a - b) * 100:+8.1f}%"

            lines.append(
                f"{label:<{col_w}}  "
                f"{delta('accuracy'):>10}  "
                f"{delta('zone_violation_rate'):>10}  "
                f"{delta('list_depth_accuracy'):>10}  "
                f"{delta('table_sem_accuracy'):>10}  "
                f"{delta('ref_accuracy'):>9}  "
                f"{delta('invalid_tag_rate'):>10}  "
                f"{delta('structure_guard_fail_rate'):>10}"
            )

    # TABLE per-tag breakdown section
    table_lines = _format_table_breakdown(results, modes_run)
    lines += table_lines

    lines += ["", "=" * W]
    return "\n".join(lines)


# -----------------------------------------------------------------------
# Main evaluation orchestrator
# -----------------------------------------------------------------------
_ALL_MODES = ["baseline", "alias", "semantic", "rules", "retriever"]


def run_evaluation(
    split_type: str = "book",
    holdout_fraction: float = 0.2,
    holdout_seed: int = 42,
    modes: Optional[List[str]] = None,
    train_rules_if_missing: bool = True,
    min_alias_confidence: float = 0.70,
    report_file: Optional[str] = None,
    semantic_knowledge_path: Optional[Path] = None,
    semantic_transitions_path: Optional[Path] = None,
    allowed_styles_override: Optional[set] = None,
) -> str:
    """Run all requested ablation modes on the holdout set and return a report.

    Args:
        split_type: "book" (doc-level) or "publisher" (publisher-family-level)
        holdout_fraction: fraction of docs/publishers to hold out
        holdout_seed: RNG seed for reproducible splits
        modes: list of ablation mode names to run; None → all except retriever
        train_rules_if_missing: if True, train rules on training split when
            learned_rules.json does not exist
        min_alias_confidence: minimum confidence for alias candidate entries
        report_file: if provided, also write the report to this path
        semantic_knowledge_path: override for tag_semantics_knowledge.json path
        semantic_transitions_path: override for tag_transition_priors.json path
        allowed_styles_override: override allowed_styles set (for testing)

    Returns:
        Formatted report string.
    """
    if modes is None:
        modes = ["baseline", "alias", "semantic", "rules"]

    # Validate mode names
    unknown = [m for m in modes if m not in _ALL_MODES]
    if unknown:
        raise ValueError(f"Unknown ablation modes: {unknown}. Valid: {_ALL_MODES}")

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    allowed_styles = allowed_styles_override if allowed_styles_override is not None else _load_allowed_styles()

    from processor.rule_learner import RuleLearner

    learner = RuleLearner()
    ground_truth = learner.load_ground_truth()
    if not ground_truth:
        return f"ERROR: No ground truth data found at {_GROUND_TRUTH_PATH}"

    # ------------------------------------------------------------------
    # Holdout split
    # ------------------------------------------------------------------
    if split_type == "publisher":
        train_gt, holdout_gt, holdout_doc_ids = split_holdout_publisher(
            ground_truth, holdout_fraction=holdout_fraction, seed=holdout_seed
        )
    else:  # book
        train_gt, holdout_gt, holdout_doc_ids = learner.split_holdout(
            ground_truth, holdout_fraction=holdout_fraction, seed=holdout_seed
        )

    n_train = len(train_gt)
    n_holdout = len(holdout_gt)

    # ------------------------------------------------------------------
    # Build holdout context (flatten with prev_canonical_tag)
    # ------------------------------------------------------------------
    holdout_entries = build_context(holdout_gt)

    # ------------------------------------------------------------------
    # Load / train rules (only if needed)
    # ------------------------------------------------------------------
    if any(m in modes for m in ("rules", "retriever")):
        rules_loaded = learner.load_rules()
        if not rules_loaded and train_rules_if_missing:
            logger.info(
                "learned_rules.json not found — training rules on %d train docs...", n_train
            )
            train_examples = learner.extract_training_examples(train_gt)
            learner.learn_rules(train_examples)
            logger.info("Trained %d rules (training split only)", len(learner.rules))

    # ------------------------------------------------------------------
    # Load artefacts (lazy, only what each mode needs)
    # ------------------------------------------------------------------
    alias_map: Dict[str, str] = {}
    if any(m in modes for m in ("alias", "semantic", "rules", "retriever")):
        alias_map = _load_alias_map(min_confidence=min_alias_confidence)

    artifacts: dict = {}
    if any(m in modes for m in ("semantic", "rules", "retriever")):
        artifacts = _load_semantic_artifacts(
            knowledge_path=semantic_knowledge_path or _SEMANTIC_KNOWLEDGE_PATH,
            transitions_path=semantic_transitions_path or _SEMANTIC_TRANSITIONS_PATH,
        )

    normalize_tag_fn = _load_normalize_tag()

    # ------------------------------------------------------------------
    # Grounded retriever (dev-only, data leakage risk)
    # ------------------------------------------------------------------
    retriever = None
    retriever_leakage_warning = False
    if "retriever" in modes:
        retriever_leakage_warning = True
        try:
            from app.services.grounded_retriever import GroundedRetriever

            retriever = GroundedRetriever(_GROUND_TRUTH_PATH)
            logger.warning(
                "RETRIEVER mode enabled: full ground_truth.jsonl is indexed "
                "(includes holdout docs — DATA LEAKAGE)."
            )
        except Exception as exc:
            logger.warning("Could not initialize retriever (%s) — retriever mode disabled.", exc)

    # ------------------------------------------------------------------
    # Build predictor container
    # ------------------------------------------------------------------
    preds = Predictors(
        normalize_tag_fn=normalize_tag_fn,
        alias_map=alias_map,
        artifacts=artifacts,
        allowed_styles=allowed_styles,
        learner=learner,
        retriever=retriever,
    )

    _predict_fn: Dict[str, Callable] = {
        "baseline": preds.predict_baseline,
        "alias": preds.predict_alias,
        "semantic": preds.predict_semantic,
        "rules": preds.predict_rules,
        "retriever": preds.predict_retriever,
    }

    # ------------------------------------------------------------------
    # Run each mode and compute metrics
    # ------------------------------------------------------------------
    results: Dict[str, Dict] = {}
    for mode in modes:
        fn = _predict_fn[mode]
        predictions = [fn(e) for e in holdout_entries]
        metrics = compute_metrics(predictions, holdout_entries, allowed_styles)
        results[mode] = metrics
        logger.info(
            "Mode=%-22s  accuracy=%5.1f%%  zone_viol=%5.1f%%  txt_fallback=%5.1f%%",
            mode,
            metrics["accuracy"] * 100,
            metrics["zone_violation_rate"] * 100,
            metrics["txt_fallback_rate"] * 100,
        )

    # ------------------------------------------------------------------
    # Format and emit report
    # ------------------------------------------------------------------
    report = format_report(
        results=results,
        split_type=f"{split_type}-level holdout ({holdout_fraction:.0%}, seed={holdout_seed})",
        holdout_doc_ids=holdout_doc_ids,
        n_train_docs=n_train,
        n_holdout_docs=n_holdout,
        modes_run=[m for m in modes if m in results],
        retriever_leakage_warning=retriever_leakage_warning,
    )

    if report_file:
        Path(report_file).write_text(report, encoding="utf-8")
        logger.info("Report written to %s", report_file)

    return report


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline ablation & generalization evaluation — no LLM API required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: book-level holdout (20%), baseline -> alias -> semantic -> rules
  python tools/eval_generalization.py

  # Publisher-level holdout, all modes (includes retriever leakage warning)
  python tools/eval_generalization.py --split publisher --modes all

  # Larger holdout fraction with reproducible seed
  python tools/eval_generalization.py --split book --holdout-fraction 0.3 --seed 7

  # Save report to file
  python tools/eval_generalization.py --report-file outputs/eval_report.txt

  # Only baseline vs rules comparison
  python tools/eval_generalization.py --modes baseline rules
        """,
    )

    parser.add_argument(
        "--split",
        choices=["book", "publisher"],
        default="book",
        help="Holdout split strategy: book (doc-level) or publisher (family-level). Default: book",
    )
    parser.add_argument(
        "--holdout-fraction",
        type=float,
        default=0.2,
        help="Fraction of docs/publishers to hold out (default: 0.2)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for holdout split (default: 42)",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        metavar="MODE",
        default=["baseline", "alias", "semantic", "rules"],
        help=(
            "Ablation modes to run. Choices: all baseline alias semantic rules retriever. "
            "Default: baseline alias semantic rules"
        ),
    )
    parser.add_argument(
        "--min-alias-confidence",
        type=float,
        default=0.70,
        help="Minimum alias candidate confidence (default: 0.70)",
    )
    parser.add_argument(
        "--no-train-rules",
        dest="train_rules",
        action="store_false",
        default=True,
        help="Do not auto-train rules if learned_rules.json is missing",
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="Also write the report to this file path",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level: DEBUG INFO WARNING ERROR (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Expand "all" shorthand
    modes_requested: List[str] = args.modes
    if "all" in modes_requested:
        modes_requested = list(_ALL_MODES)

    # Validate
    unknown = [m for m in modes_requested if m not in _ALL_MODES]
    if unknown:
        parser.error(f"Unknown mode(s): {unknown}. Valid choices: {_ALL_MODES}")

    report = run_evaluation(
        split_type=args.split,
        holdout_fraction=args.holdout_fraction,
        holdout_seed=args.seed,
        modes=modes_requested,
        train_rules_if_missing=args.train_rules,
        min_alias_confidence=args.min_alias_confidence,
        report_file=args.report_file,
    )
    print(report)


if __name__ == "__main__":
    main()
