#!/usr/bin/env python3
"""
tools/build_semantic_knowledge.py

Offline semantic knowledge extraction from ground_truth.jsonl.

Reads:
  backend/data/ground_truth.jsonl
  backend/config/allowed_styles.json
  backend/config/style_aliases.json

Writes:
  backend/data/tag_semantics_knowledge.json   — zone-tag priors + tag families
  backend/data/tag_transition_priors.json     — sequential tag transition probs
  backend/data/style_alias_candidates.json    — alias report (no auto-merge)
  backend/outputs/corpus/tag_rationale_report.md  — human-readable summary

Constraints:
  - Generalized patterns only; no raw training text stored in artifacts.
  - Deterministic and reproducible (stable sorting, floats rounded to 4 dp).
  - No runtime classifier/validator changes.
  - No auto-merge into style_aliases.json.

Usage (from AI-structuring/backend/):
  python tools/build_semantic_knowledge.py
  python tools/build_semantic_knowledge.py --min-support 3 --min-confidence 0.70
  python tools/build_semantic_knowledge.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_DATA_DIR = _BACKEND / "data"
_CONFIG_DIR = _BACKEND / "config"
_OUTPUTS_DIR = _BACKEND / "outputs" / "corpus"

GROUND_TRUTH_PATH = _DATA_DIR / "ground_truth.jsonl"
ALLOWED_STYLES_PATH = _CONFIG_DIR / "allowed_styles.json"
STYLE_ALIASES_PATH = _CONFIG_DIR / "style_aliases.json"

KNOWLEDGE_OUT = _DATA_DIR / "tag_semantics_knowledge.json"
TRANSITIONS_OUT = _DATA_DIR / "tag_transition_priors.json"
ALIAS_CANDIDATES_OUT = _DATA_DIR / "style_alias_candidates.json"
REPORT_OUT = _OUTPUTS_DIR / "tag_rationale_report.md"

SCHEMA_VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — canonical pattern helpers
# ---------------------------------------------------------------------------
_POSITIONAL_SUFFIXES = ("FIRST", "MID", "LAST", "ONLY")

# Regex to detect positional suffix anywhere in a tag
_POS_SUFFIX_RE = re.compile(
    r"[-_](FIRST|MID|LAST|ONLY)$", re.IGNORECASE
)

# Regex to detect depth indicator (BL2, NL3, BL4, etc.)
_DEPTH_RE = re.compile(r"^(.*?[A-Z])(2|3|4|5|6)(-|$)", re.IGNORECASE)

# Tags that are fundamentally "structural markers" (PMI-family)
_PMI_PATTERN_RE = re.compile(
    r"^(<[^>]+>|</[^>]+>|<INSERT|<SPACE|<!--)", re.IGNORECASE
)

# Heuristics to detect publisher raw style names (not clean canonical tags)
_RAW_STYLE_SIGNALS = [
    re.compile(r"\s"),                          # has space
    re.compile(r"[A-Z][a-z]+[A-Z]"),           # CamelCase interior
    re.compile(r"\d{4,}"),                      # long ISBN-style number
    re.compile(r"^(Box|CaseStudy|Learning|Chapter|Objective|Number|Bullet|FE-\d|EOC-[A-Z])", re.IGNORECASE),
]

# Patterns to propose canonical mappings for publisher raw styles
_ALIAS_PROPOSAL_RULES: List[Tuple[re.Pattern, str]] = [
    # Bullet list variants
    (re.compile(r"BulletList\d*[_\-]?first", re.IGNORECASE), "BL-FIRST"),
    (re.compile(r"BulletList\d*[_\-]?last", re.IGNORECASE), "BL-LAST"),
    (re.compile(r"BulletList2", re.IGNORECASE), "BL2-MID"),
    (re.compile(r"BulletList3", re.IGNORECASE), "BL3-MID"),
    (re.compile(r"BulletList\d*$", re.IGNORECASE), "BL-MID"),
    # Number list variants
    (re.compile(r"NumberList\d*[_\-]?first", re.IGNORECASE), "NL-FIRST"),
    (re.compile(r"NumberList\d*[_\-]?last", re.IGNORECASE), "NL-LAST"),
    (re.compile(r"NumberList2", re.IGNORECASE), "NL2-MID"),
    (re.compile(r"NumberList\d*$", re.IGNORECASE), "NL-MID"),
    # Heading levels
    (re.compile(r"(Head|Heading)[_\-]?1\b", re.IGNORECASE), "H1"),
    (re.compile(r"(Head|Heading)[_\-]?2\b", re.IGNORECASE), "H2"),
    (re.compile(r"(Head|Heading)[_\-]?3\b", re.IGNORECASE), "H3"),
    (re.compile(r"(Head|Heading)[_\-]?4\b", re.IGNORECASE), "H4"),
    # Chapter / section title
    (re.compile(r"ChapterTitle", re.IGNORECASE), "CT"),
    (re.compile(r"ChapterNumber", re.IGNORECASE), "CN"),
    (re.compile(r"PartTitle", re.IGNORECASE), "PT"),
    # Para flush / first-line indent
    (re.compile(r"Para.FL|ParaFirstLine|ParaFirstLine.Ind", re.IGNORECASE), "TXT-FLUSH"),
    # References
    (re.compile(r"Reference.Alphabetical|ReferenceAlphabetical|ReferenceNumbered", re.IGNORECASE), "REF-N"),
    (re.compile(r"Reference[sS]?Heading\d*$", re.IGNORECASE), "REFH1"),
    # Table elements
    (re.compile(r"TableBody|TableParagraph", re.IGNORECASE), "T"),
    (re.compile(r"TableColumnHead\d*|TableColHead", re.IGNORECASE), "TH1"),
    (re.compile(r"TableFootnote|TableNote", re.IGNORECASE), "TFN"),
    (re.compile(r"TableCaption|TableCaptions", re.IGNORECASE), "T1"),
    (re.compile(r"TableSource|TSrc", re.IGNORECASE), "TSN"),
    # Box elements
    (re.compile(r"Box.*Title|BoxTitle|BoxT$", re.IGNORECASE), "BX1-TTL"),
    # Figure
    (re.compile(r"FigureCaption|Figure[_\-]?Caption|FigureLegend", re.IGNORECASE), "FIG-LEG"),
    (re.compile(r"FigureSource|FigureSrc", re.IGNORECASE), "FIG-SRC"),
    # Generic body text
    (re.compile(r"^Normal$|^Body\s?Text\b|^Default$|^Paragraph$", re.IGNORECASE), "TXT"),
]

# Known semantic tag groups (used for table/reference rationale sections)
_TABLE_ROLE_GROUPS: Dict[str, List[str]] = {
    "caption": ["T1", "T2", "T3", "TT"],
    "header": ["TH1", "TH2", "TH3", "TH4", "TH5", "TH6", "TCH", "TCH1"],
    "body_cell": ["T", "T4", "T5", "TBL-FIRST", "TBL-MID", "TBL-LAST"],
    "footnote": ["TFN", "TFN-FIRST", "TFN-MID", "TFN-LAST"],
    "source_note": ["TSN"],
    "list_in_table": ["TNL-FIRST", "TNL-MID", "TNL-LAST", "TUL-FIRST", "TUL-MID"],
}

_REF_ROLE_GROUPS: Dict[str, List[str]] = {
    "heading": ["REFH1", "REFH2", "REFH2a", "REF-H1", "REF-H2", "SRH1", "SRH2"],
    "numbered_entry": ["REF-N", "REF-N-FIRST"],
    "unnumbered_entry": ["REF-U"],
    "back_matter_other": ["SR", "BIB", "BIBH1", "BIBH2"],
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_ground_truth(path: Path) -> Dict[str, List[Dict]]:
    """Load ground_truth.jsonl → {doc_id: [entries sorted by para_index]}."""
    docs: Dict[str, List[Dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed line %d: %s", lineno, exc)
                continue
            doc_id = entry.get("doc_id", f"unknown_{lineno}")
            docs[doc_id].append(entry)
    for doc_id in docs:
        docs[doc_id].sort(key=lambda e: e.get("para_index", 0))
    return dict(docs)


def _load_allowed_styles(path: Path) -> Set[str]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return set(data) if isinstance(data, list) else set()


def _load_style_aliases(path: Path) -> Dict[str, str]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round4(v: float) -> float:
    return round(v, 4)


# ---------------------------------------------------------------------------
# Zone-tag priors
# ---------------------------------------------------------------------------

def _build_zone_tag_priors(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
) -> Dict[str, Any]:
    """
    Compute per-zone tag frequency distributions.

    Excludes UNMAPPED entries (empty canonical_gold_tag or canonical_gold_tag == 'UNMAPPED').
    Maps ground-truth zone strings to artifact zone keys (BODY, REFERENCE).
    """
    _ZONE_MAP = {"body": "BODY", "reference": "REFERENCE"}

    zone_counts: Dict[str, Counter] = defaultdict(Counter)

    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if not tag or tag == "UNMAPPED":
                continue
            zone_raw = e.get("zone", "body").lower().strip()
            zone = _ZONE_MAP.get(zone_raw, "BODY")
            zone_counts[zone][tag] += 1

    result: Dict[str, Any] = {}
    for zone in sorted(zone_counts.keys()):
        counter = zone_counts[zone]
        total = sum(counter.values())
        dist = {}
        for tag in sorted(counter.keys()):
            cnt = counter[tag]
            dist[tag] = {
                "count": cnt,
                "frequency": _round4(cnt / total if total > 0 else 0.0),
                "in_allowed_styles": tag in allowed_styles,
            }
        result[zone] = {"total": total, "distribution": dist}

    return result


# ---------------------------------------------------------------------------
# Tag family groupings
# ---------------------------------------------------------------------------

_MULTI_SEGMENT_PREFIXES = (
    # These prefixes span TWO dash segments, e.g. KT-BL, RQ-LL2, BX1-BL
    "KT-BL", "KT-NL", "KT-UL",
    "KP-BL", "KP-NL",
    "OBJ-BL", "OBJ-NL", "OBJ-UL",
    "EOC-NL", "EOC-LL2", "EOC-EQ",
    "RQ-LL2", "RQ-NL", "RQ-UL2", "RQ-NL2",
    "ANS-NL", "ANS-UL",
    "QUES-NL", "QUES-LL2", "QUES-SUB",
    "REV-NL", "REV-ANS-NL", "REV-QUES-NL", "REV-QUES-LL2",
    "EX-NL", "EXER-NL", "EXER-MC-NL2", "EXER-SP-NL2",
    "FN-BL", "TFN-BL",
    "GLOS-BL", "GLOS-NL", "GLOS-UL",
    "SOUT-NL", "COUT-BL", "COUT-NL",
    "BX1-BL", "BX1-NL", "BX1-UL", "BX1-EQ",
    "BX2-BL", "BX2-NL",
    "BX3-BL", "BX3-NL", "BX3-UL",
    "BX4-BL", "BX4-BL2", "BX4-NL", "BX4-NL2", "BX4-LL2",
    "BX6-BL", "BX7-BL", "BX7-NL", "BX8-BL",
    "BX15-", "BX16-",
    "NBX-BL", "NBX-BL2", "NBX-NL", "NBX-UL", "NBX-EQ",
    "NBX1-BL", "NBX1-NL",
    "SBBL", "SBNL",
    "UNT-BL", "UNT-NL", "UNT-UL",
    "CTC-BL", "CJC-BL2", "CJC-BL3",
    "AF-T", "AF-TBL",
)


def _extract_family_prefix(tag: str) -> str:
    """Return the semantic family prefix for a canonical tag.

    Multi-segment families (e.g. KT-BL, BX1-BL) are detected first;
    single-segment prefix (before first dash/digit) is the fallback.
    """
    for prefix in sorted(_MULTI_SEGMENT_PREFIXES, key=len, reverse=True):
        if tag.startswith(prefix):
            return prefix.rstrip("-")
    # Strip positional suffix
    tag_stripped = _POS_SUFFIX_RE.sub("", tag)
    # Strip depth digit before a dash
    m = _DEPTH_RE.match(tag_stripped)
    if m:
        tag_stripped = m.group(1)
    # Take prefix before first dash
    parts = tag_stripped.split("-")
    return parts[0] if parts else tag_stripped


def _build_tag_families(
    allowed_styles: Set[str],
    docs: Dict[str, List[Dict]],
) -> Dict[str, Any]:
    """Group all allowed styles into semantic families with positional/depth variants."""
    # Count corpus usage per tag
    corpus_counts: Counter = Counter()
    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if tag and tag != "UNMAPPED":
                corpus_counts[tag] += 1

    family_map: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "members": [],
            "positional_variants": set(),
            "depth_variants": set(),
            "prefixed_families": set(),
        }
    )

    for tag in sorted(allowed_styles):
        family = _extract_family_prefix(tag)
        family_map[family]["members"].append(tag)

        m_pos = _POS_SUFFIX_RE.search(tag)
        if m_pos:
            family_map[family]["positional_variants"].add(m_pos.group(1).upper())

        m_depth = _DEPTH_RE.search(tag)
        if m_depth:
            family_map[family]["depth_variants"].add(int(m_depth.group(2)))

        if "-" in family:
            root = family.split("-")[0]
            family_map[root]["prefixed_families"].add(family)

    # Convert to JSON-serializable, sorted
    result: Dict[str, Any] = {}
    for family in sorted(family_map.keys()):
        data = family_map[family]
        members = sorted(data["members"])
        pos_variants = sorted(data["positional_variants"])
        depth_variants = sorted(data["depth_variants"])
        prefixed = sorted(data["prefixed_families"])
        corpus_total = sum(corpus_counts.get(m, 0) for m in members)
        result[family] = {
            "members": members,
            "member_count": len(members),
            "corpus_count": corpus_total,
            "positional_variants": pos_variants,
            "depth_variants": depth_variants,
            "prefixed_families": prefixed,
        }

    return result


# ---------------------------------------------------------------------------
# Positional suffix semantics
# ---------------------------------------------------------------------------

def _build_positional_suffix_semantics(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
) -> Dict[str, Any]:
    """Count corpus occurrences of each positional suffix and sample example tags."""
    suffix_counts: Dict[str, Counter] = {s: Counter() for s in _POSITIONAL_SUFFIXES}

    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if not tag or tag == "UNMAPPED":
                continue
            m = _POS_SUFFIX_RE.search(tag)
            if m:
                suf = m.group(1).upper()
                if suf in suffix_counts:
                    suffix_counts[suf][tag] += 1

    descriptions = {
        "FIRST": "first item in a positional list run",
        "MID": "middle item(s) in a positional list run",
        "LAST": "last item in a positional list run",
        "ONLY": "single-item run (no FIRST/MID/LAST siblings)",
    }

    result: Dict[str, Any] = {}
    for suf in _POSITIONAL_SUFFIXES:
        counter = suffix_counts[suf]
        top_tags = [t for t, _ in counter.most_common(8) if t in allowed_styles]
        result[suf] = {
            "description": descriptions[suf],
            "corpus_count": sum(counter.values()),
            "distinct_tags": len(counter),
            "example_tags": top_tags,
        }
    return result


# ---------------------------------------------------------------------------
# List-depth semantics
# ---------------------------------------------------------------------------

_DEPTH_LABEL_MAP = {1: "depth-1 (base)", 2: "depth-2 (nested)", 3: "depth-3 (doubly nested)",
                    4: "depth-4", 5: "depth-5", 6: "depth-6"}
_DEPTH_LIST_BASES = ["BL", "NL", "UL"]


def _build_list_depth_semantics(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
) -> Dict[str, Any]:
    """
    Map each list base + depth combination to corpus frequency and variant tags.
    Also covers prefixed families (KT-BL2, BX4-NL2, etc.).
    """
    # Regex to match <PREFIX>(2-6)?[-_](FIRST|MID|LAST|ONLY|$)
    depth_pattern = re.compile(
        r"(?:^|[-_])((?:[A-Z]+-)?(?:BL|NL|UL))(2|3|4|5|6)?(?:[-_](FIRST|MID|LAST|ONLY))?$",
        re.IGNORECASE,
    )

    depth_tags: Dict[str, Counter] = defaultdict(Counter)

    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if not tag or tag == "UNMAPPED":
                continue
            m = depth_pattern.search(tag)
            if m:
                base = m.group(1).upper()
                depth = int(m.group(2)) if m.group(2) else 1
                key = f"{base}{depth}" if depth > 1 else base
                depth_tags[key][tag] += 1

    result: Dict[str, Any] = {}
    for key in sorted(depth_tags.keys()):
        counter = depth_tags[key]
        # Extract base and depth from key
        dm = re.match(r"^(.+?)(\d+)?$", key)
        base_part = dm.group(1) if dm else key
        depth_num = int(dm.group(2)) if dm and dm.group(2) else 1
        total = sum(counter.values())
        variant_list = sorted(t for t in counter if t in allowed_styles)
        result[key] = {
            "base": base_part,
            "depth": depth_num,
            "label": _DEPTH_LABEL_MAP.get(depth_num, f"depth-{depth_num}"),
            "corpus_count": total,
            "variants_in_corpus": variant_list[:12],  # cap for readability
        }

    return result


# ---------------------------------------------------------------------------
# PMI / marker semantics
# ---------------------------------------------------------------------------

def _build_marker_semantics(docs: Dict[str, List[Dict]]) -> Dict[str, Any]:
    """
    Extract structural marker text patterns that appear as PMI entries.
    Stores only the pattern string, not the paragraph text content.
    """
    open_markers: Counter = Counter()
    close_markers: Counter = Counter()
    insert_markers: Counter = Counter()
    other_markers: Counter = Counter()

    _OPEN_RE = re.compile(r"^<([A-Z][A-Z0-9_\-]*)>$", re.IGNORECASE)
    _CLOSE_RE = re.compile(r"^</([A-Z][A-Z0-9_\-]*)>$", re.IGNORECASE)
    _INSERT_RE = re.compile(r"^<INSERT\s+", re.IGNORECASE)

    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if tag != "PMI":
                continue
            text = e.get("text", "").strip()
            if not text:
                continue
            # Classify by pattern only — no text content stored
            if _OPEN_RE.match(text):
                m = _OPEN_RE.match(text)
                open_markers[f"<{m.group(1).upper()}>"] += 1
            elif _CLOSE_RE.match(text):
                m = _CLOSE_RE.match(text)
                close_markers[f"</{m.group(1).upper()}>"] += 1
            elif _INSERT_RE.match(text):
                # Normalize: extract just the type keyword (TAB, FIG, etc.)
                raw = text[:20].upper()
                type_m = re.search(r"<INSERT\s+([A-Z]+)", raw)
                key = f"<INSERT {type_m.group(1)}...>" if type_m else "<INSERT ...>"
                insert_markers[key] += 1
            else:
                other_markers["<other_pmi_pattern>"] += 1

    def _top(counter: Counter, n: int = 10) -> List[Dict]:
        return [{"pattern": p, "count": c} for p, c in counter.most_common(n)]

    return {
        "open_markers": _top(open_markers),
        "close_markers": _top(close_markers),
        "insert_markers": _top(insert_markers),
        "other_count": sum(other_markers.values()),
        "total_pmi_entries": (
            sum(open_markers.values())
            + sum(close_markers.values())
            + sum(insert_markers.values())
            + sum(other_markers.values())
        ),
    }


# ---------------------------------------------------------------------------
# Table semantics
# ---------------------------------------------------------------------------

def _build_table_semantics(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
) -> Dict[str, Any]:
    """Compute table-tag role groupings with corpus support counts."""
    # Count table-related tags in corpus (all zones, filter by tag prefix)
    _TABLE_TAG_RE = re.compile(
        r"^(T\d?$|T[1-9]\d?|TH\d|TFN|TSN|TBL|TNL|TUL|TCH|TT|TB|TIH|TN|TMATH|T-DIR|TBH|T4|T5|TTXT|AF-T)",
        re.IGNORECASE,
    )
    tag_counts: Counter = Counter()
    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if tag and tag != "UNMAPPED" and _TABLE_TAG_RE.match(tag):
                tag_counts[tag] += 1

    role_groups_out: Dict[str, Any] = {}
    for role, members in sorted(_TABLE_ROLE_GROUPS.items()):
        members_in_allowed = [m for m in members if m in allowed_styles]
        role_groups_out[role] = {
            "canonical_members": members_in_allowed,
            "corpus_counts": {m: tag_counts.get(m, 0) for m in members_in_allowed},
        }

    return {
        "role_groups": role_groups_out,
        "all_table_tags_in_corpus": {
            t: c for t, c in sorted(tag_counts.items()) if c > 0
        },
        "note": "TABLE zone not present in current ground_truth.jsonl; counts are from body/reference zones only.",
    }


# ---------------------------------------------------------------------------
# Reference / back-matter semantics
# ---------------------------------------------------------------------------

def _build_reference_semantics(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
) -> Dict[str, Any]:
    """Compute reference-zone tag distributions and role groupings."""
    ref_tag_counts: Counter = Counter()
    body_ref_tag_counts: Counter = Counter()

    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if not tag or tag == "UNMAPPED":
                continue
            zone = e.get("zone", "body").lower()
            if zone == "reference":
                ref_tag_counts[tag] += 1
            else:
                # Body-zone tags that are reference-family
                if re.match(r"^(REF|REFH|SR|BIB|EOC_REF|EOC-REF|APX-REF)", tag, re.IGNORECASE):
                    body_ref_tag_counts[tag] += 1

    role_groups_out: Dict[str, Any] = {}
    for role, members in sorted(_REF_ROLE_GROUPS.items()):
        members_in_allowed = [m for m in members if m in allowed_styles]
        role_groups_out[role] = {
            "canonical_members": members_in_allowed,
            "reference_zone_counts": {m: ref_tag_counts.get(m, 0) for m in members_in_allowed},
        }

    top_ref = [
        {"tag": t, "count": c}
        for t, c in ref_tag_counts.most_common(20)
    ]

    return {
        "zone_detection_rule": (
            "Reference entries are detected by zone='reference' in ground_truth. "
            "Zone prior should dominate raw style for reference entries."
        ),
        "role_groups": role_groups_out,
        "top_tags_in_reference_zone": top_ref,
        "ref_family_tags_in_body_zone": {
            t: c for t, c in sorted(body_ref_tag_counts.items()) if c > 0
        },
    }


# ---------------------------------------------------------------------------
# Tag transition priors
# ---------------------------------------------------------------------------

def _build_transition_priors(
    docs: Dict[str, List[Dict]],
    min_support: int = 3,
) -> Dict[str, Any]:
    """
    Compute per-tag sequential transition probabilities within each document.

    Args:
        docs: {doc_id: [sorted entries]}
        min_support: minimum bigram count to include a transition (avoids noise)

    Returns:
        global_transitions: {source_tag: {total_observed, next_tag_distribution: {next_tag: {count, probability}}}}
    """
    bigrams: Dict[str, Counter] = defaultdict(Counter)

    for entries in docs.values():
        prev_tag: Optional[str] = None
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if not tag or tag == "UNMAPPED":
                prev_tag = None  # reset on UNMAPPED
                continue
            if prev_tag is not None:
                bigrams[prev_tag][tag] += 1
            prev_tag = tag

    result: Dict[str, Any] = {}
    for src_tag in sorted(bigrams.keys()):
        counter = bigrams[src_tag]
        total = sum(counter.values())
        next_dist: Dict[str, Any] = {}
        for next_tag in sorted(counter.keys()):
            cnt = counter[next_tag]
            if cnt < min_support:
                continue
            next_dist[next_tag] = {
                "count": cnt,
                "probability": _round4(cnt / total),
            }
        if next_dist:
            result[src_tag] = {
                "total_observed": total,
                "next_tag_distribution": next_dist,
            }

    return result


# ---------------------------------------------------------------------------
# Style alias candidates
# ---------------------------------------------------------------------------

def _is_raw_style(tag: str) -> bool:
    """Return True if a style name looks like a publisher raw style (not clean canonical)."""
    for sig in _RAW_STYLE_SIGNALS:
        if sig.search(tag):
            return True
    return False


def _propose_canonical(raw_style: str, allowed_styles: Set[str]) -> Optional[str]:
    """Propose a canonical tag for a raw publisher style name using pattern rules."""
    for pattern, canonical in _ALIAS_PROPOSAL_RULES:
        if pattern.search(raw_style):
            if canonical in allowed_styles:
                return canonical
    return None


def _compute_alias_confidence(
    raw_style: str,
    proposed_canonical: str,
    corpus_support: int,
    already_in_aliases: bool,
) -> float:
    """
    Compute a confidence score [0.0, 1.0] for a proposed alias mapping.

    - Existing aliases in style_aliases.json: 1.0 (validated by expert)
    - Pattern-matched new candidates: 0.60–0.85 depending on match strength
    - Corpus support boosts confidence up to +0.10
    """
    if already_in_aliases:
        return 1.0

    # Base confidence from pattern: exact word-boundary match = higher
    base = 0.65
    # If canonical looks like a normalized version of raw (common prefix)
    raw_upper = raw_style.upper().replace("-", "").replace("_", "")
    can_upper = proposed_canonical.upper().replace("-", "").replace("_", "")
    if can_upper in raw_upper or raw_upper.startswith(can_upper[:4]):
        base += 0.10
    # Corpus support boost (capped at 0.10)
    boost = min(corpus_support / 100.0, 0.10)
    return _round4(min(base + boost, 0.95))


def _build_alias_candidates(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
    existing_aliases: Dict[str, str],
    min_confidence: float = 0.70,
) -> List[Dict]:
    """
    Build alias candidate list.

    Strategy:
    1. Corpus-validated existing aliases (in style_aliases.json) → confidence=1.0, corpus support counted.
    2. Corpus-new candidates (gold_tag not in style_aliases but looks like raw style) → pattern-proposed.
    3. Allowed-styles raw candidates (in allowed_styles.json but not in style_aliases, looks like raw style) → pattern-proposed.

    Returns list of candidate dicts sorted by confidence desc, then raw_style asc.
    """
    # Count corpus occurrences of each gold_tag
    corpus_counts: Counter = Counter()
    for entries in docs.values():
        for e in entries:
            tag = e.get("canonical_gold_tag", "").strip()
            if tag and tag != "UNMAPPED":
                corpus_counts[tag] += 1

    candidates: Dict[str, Dict] = {}

    # --- 1. Existing aliases validated against corpus ---
    for raw_style, canonical in sorted(existing_aliases.items()):
        support = corpus_counts.get(raw_style, 0)
        candidates[raw_style] = {
            "raw_style": raw_style,
            "suggested_canonical": canonical,
            "confidence": 1.0,
            "support": support,
            "in_allowed_styles": raw_style in allowed_styles,
            "already_in_aliases": True,
            "recommendation": "add_alias",
            "evidence": "existing entry in style_aliases.json",
        }

    # --- 2. Corpus-seen tags that look like raw styles (not in aliases yet) ---
    for tag in sorted(corpus_counts.keys()):
        if tag in candidates:
            continue
        if not _is_raw_style(tag):
            continue
        proposed = _propose_canonical(tag, allowed_styles)
        if proposed is None:
            continue
        support = corpus_counts[tag]
        conf = _compute_alias_confidence(tag, proposed, support, False)
        if conf < min_confidence:
            continue
        candidates[tag] = {
            "raw_style": tag,
            "suggested_canonical": proposed,
            "confidence": conf,
            "support": support,
            "in_allowed_styles": tag in allowed_styles,
            "already_in_aliases": False,
            "recommendation": "add_alias" if conf >= 0.80 else "review",
            "evidence": "corpus occurrence + pattern match",
        }

    # --- 3. Allowed-styles entries that look like raw styles (not seen in corpus) ---
    for style in sorted(allowed_styles):
        if style in candidates:
            continue
        if not _is_raw_style(style):
            continue
        proposed = _propose_canonical(style, allowed_styles)
        if proposed is None or proposed == style:
            continue
        support = corpus_counts.get(style, 0)
        conf = _compute_alias_confidence(style, proposed, support, False)
        if conf < min_confidence:
            continue
        candidates[style] = {
            "raw_style": style,
            "suggested_canonical": proposed,
            "confidence": conf,
            "support": support,
            "in_allowed_styles": True,
            "already_in_aliases": False,
            "recommendation": "add_alias" if conf >= 0.80 else "review",
            "evidence": "in allowed_styles.json + pattern match",
        }

    # Sort: confidence desc, then raw_style asc
    return sorted(
        candidates.values(),
        key=lambda c: (-c["confidence"], c["raw_style"]),
    )


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------

def _build_knowledge_artifact(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
    input_paths: Dict[str, str],
) -> Dict[str, Any]:
    """Assemble tag_semantics_knowledge.json."""
    total = sum(len(v) for v in docs.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "input_paths": input_paths,
        "corpus_stats": {
            "total_docs": len(docs),
            "total_entries": total,
        },
        "zone_tag_priors": _build_zone_tag_priors(docs, allowed_styles),
        "tag_families": _build_tag_families(allowed_styles, docs),
        "positional_suffix_semantics": _build_positional_suffix_semantics(docs, allowed_styles),
        "list_depth_semantics": _build_list_depth_semantics(docs, allowed_styles),
        "marker_semantics": _build_marker_semantics(docs),
        "table_semantics": _build_table_semantics(docs, allowed_styles),
        "reference_semantics": _build_reference_semantics(docs, allowed_styles),
    }


def _build_transitions_artifact(
    docs: Dict[str, List[Dict]],
    input_paths: Dict[str, str],
    min_support: int = 3,
) -> Dict[str, Any]:
    """Assemble tag_transition_priors.json."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "input_paths": input_paths,
        "extraction_params": {
            "min_support": min_support,
            "scope": "within-document sequential pairs (UNMAPPED entries break chains)",
        },
        "global_transitions": _build_transition_priors(docs, min_support=min_support),
    }


def _build_alias_artifact(
    docs: Dict[str, List[Dict]],
    allowed_styles: Set[str],
    existing_aliases: Dict[str, str],
    input_paths: Dict[str, str],
    min_confidence: float = 0.70,
) -> Dict[str, Any]:
    """Assemble style_alias_candidates.json."""
    candidates = _build_alias_candidates(
        docs, allowed_styles, existing_aliases, min_confidence=min_confidence
    )
    add_count = sum(1 for c in candidates if c["recommendation"] == "add_alias")
    review_count = sum(1 for c in candidates if c["recommendation"] == "review")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "input_paths": input_paths,
        "extraction_params": {
            "min_confidence": min_confidence,
            "note": "Report only — do NOT auto-merge into style_aliases.json without review.",
        },
        "summary": {
            "total_candidates": len(candidates),
            "recommendation_add_alias": add_count,
            "recommendation_review": review_count,
            "already_in_aliases": sum(1 for c in candidates if c["already_in_aliases"]),
        },
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Human-readable Markdown report
# ---------------------------------------------------------------------------

def _build_markdown_report(
    knowledge: Dict[str, Any],
    transitions: Dict[str, Any],
    alias_data: Dict[str, Any],
) -> str:
    lines: List[str] = []

    def h(level: int, text: str) -> None:
        lines.append(f"\n{'#' * level} {text}\n")

    def p(text: str) -> None:
        lines.append(text)

    h(1, "Corpus Tag Rationale Report")
    p(f"Generated: {knowledge['generated_at']}")
    p(f"Schema version: {knowledge['schema_version']}")

    # Corpus stats
    h(2, "Corpus Statistics")
    stats = knowledge["corpus_stats"]
    p(f"- Documents: {stats['total_docs']}")
    p(f"- Total entries: {stats['total_entries']}")
    zones = knowledge["zone_tag_priors"]
    for zone, zdata in sorted(zones.items()):
        p(f"- Zone `{zone}`: {zdata['total']} entries, {len(zdata['distribution'])} distinct tags")

    # Zone-tag priors
    h(2, "Zone-Tag Priors (top-15 per zone)")
    for zone, zdata in sorted(zones.items()):
        h(3, f"Zone: {zone}")
        dist = zdata["distribution"]
        top = sorted(dist.items(), key=lambda x: -x[1]["frequency"])[:15]
        p("| Tag | Count | Frequency |")
        p("|-----|-------|-----------|")
        for tag, info in top:
            p(f"| `{tag}` | {info['count']} | {info['frequency']:.3f} |")

    # Positional suffix semantics
    h(2, "Positional Suffix Semantics")
    pos = knowledge["positional_suffix_semantics"]
    p("| Suffix | Corpus Count | Distinct Tags | Description |")
    p("|--------|-------------|---------------|-------------|")
    for suf, info in pos.items():
        p(f"| `{suf}` | {info['corpus_count']} | {info['distinct_tags']} | {info['description']} |")

    # List depth semantics
    h(2, "List-Depth Semantics (corpus-observed)")
    depth = knowledge["list_depth_semantics"]
    p("| Key | Base | Depth | Count | Example Variants |")
    p("|-----|------|-------|-------|-----------------|")
    for key, info in sorted(depth.items()):
        variants_str = ", ".join(f"`{v}`" for v in info["variants_in_corpus"][:4])
        p(f"| `{key}` | `{info['base']}` | {info['depth']} | {info['corpus_count']} | {variants_str} |")

    # Tag transitions: top transitions per source
    h(2, "Tag Transitions (top-5 sources by total_observed)")
    trans = transitions["global_transitions"]
    top_sources = sorted(trans.items(), key=lambda x: -x[1]["total_observed"])[:5]
    for src, src_data in top_sources:
        h(3, f"From `{src}` (n={src_data['total_observed']})")
        next_dist = src_data["next_tag_distribution"]
        top_next = sorted(next_dist.items(), key=lambda x: -x[1]["probability"])[:5]
        p("| Next Tag | Count | Probability |")
        p("|----------|-------|-------------|")
        for nt, nt_data in top_next:
            p(f"| `{nt}` | {nt_data['count']} | {nt_data['probability']:.3f} |")

    # Alias candidates summary
    h(2, "Style Alias Candidates")
    asummary = alias_data["summary"]
    p(f"- Total candidates: {asummary['total_candidates']}")
    p(f"- Recommended add_alias: {asummary['recommendation_add_alias']}")
    p(f"- Recommended review: {asummary['recommendation_review']}")
    p(f"- Already in style_aliases.json: {asummary['already_in_aliases']}")
    p("")
    p("> **Note:** Do NOT auto-merge. Review each candidate before adding to `style_aliases.json`.")

    h(3, "New Alias Candidates (not yet in style_aliases.json, confidence >= 0.70)")
    new_cands = [c for c in alias_data["candidates"] if not c["already_in_aliases"]]
    if new_cands:
        p("| Raw Style | Suggested Canonical | Confidence | Support | Recommendation |")
        p("|-----------|--------------------|-----------:|--------:|---------------|")
        for c in new_cands[:40]:
            p(f"| `{c['raw_style']}` | `{c['suggested_canonical']}` | {c['confidence']:.2f} | {c['support']} | {c['recommendation']} |")
    else:
        p("_No new alias candidates found above the confidence threshold._")

    # Marker semantics
    h(2, "PMI Marker Semantics")
    marker = knowledge["marker_semantics"]
    p(f"Total PMI entries in corpus: {marker['total_pmi_entries']}")
    h(3, "Open Markers")
    for item in marker["open_markers"][:8]:
        p(f"- `{item['pattern']}` ({item['count']})")
    h(3, "Close Markers")
    for item in marker["close_markers"][:8]:
        p(f"- `{item['pattern']}` ({item['count']})")
    h(3, "Insert Markers")
    for item in marker["insert_markers"][:6]:
        p(f"- `{item['pattern']}` ({item['count']})")

    # Reference semantics
    h(2, "Reference / Back-Matter Semantics")
    ref = knowledge["reference_semantics"]
    p(ref["zone_detection_rule"])
    h(3, "Top Tags in Reference Zone")
    for item in ref["top_tags_in_reference_zone"][:15]:
        p(f"- `{item['tag']}`: {item['count']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    gt_path: Path = GROUND_TRUTH_PATH,
    allowed_path: Path = ALLOWED_STYLES_PATH,
    aliases_path: Path = STYLE_ALIASES_PATH,
    knowledge_out: Path = KNOWLEDGE_OUT,
    transitions_out: Path = TRANSITIONS_OUT,
    alias_out: Path = ALIAS_CANDIDATES_OUT,
    report_out: Path = REPORT_OUT,
    min_support: int = 3,
    min_alias_confidence: float = 0.70,
    dry_run: bool = False,
) -> Dict[str, Path]:
    """
    Run the full semantic knowledge extraction pipeline.

    Args:
        gt_path: ground_truth.jsonl input path.
        allowed_path: allowed_styles.json input path.
        aliases_path: style_aliases.json input path.
        knowledge_out: output path for tag_semantics_knowledge.json.
        transitions_out: output path for tag_transition_priors.json.
        alias_out: output path for style_alias_candidates.json.
        report_out: output path for Markdown rationale report.
        min_support: minimum bigram count for transition priors.
        min_alias_confidence: minimum confidence to include alias candidate.
        dry_run: if True, compute but do not write files.

    Returns:
        Dict mapping artifact name → resolved output path.
    """
    logger.info("Loading inputs...")
    docs = _load_ground_truth(gt_path)
    allowed_styles = _load_allowed_styles(allowed_path)
    existing_aliases = _load_style_aliases(aliases_path)

    total_entries = sum(len(v) for v in docs.values())
    logger.info(
        "Corpus: %d docs, %d entries. Allowed styles: %d. Existing aliases: %d.",
        len(docs), total_entries, len(allowed_styles), len(existing_aliases),
    )

    input_paths = {
        "ground_truth": str(gt_path),
        "allowed_styles": str(allowed_path),
        "style_aliases": str(aliases_path),
    }

    logger.info("Building tag_semantics_knowledge.json...")
    knowledge = _build_knowledge_artifact(docs, allowed_styles, input_paths)

    logger.info("Building tag_transition_priors.json (min_support=%d)...", min_support)
    transitions = _build_transitions_artifact(docs, input_paths, min_support=min_support)

    logger.info(
        "Building style_alias_candidates.json (min_confidence=%.2f)...",
        min_alias_confidence,
    )
    alias_data = _build_alias_artifact(
        docs, allowed_styles, existing_aliases, input_paths,
        min_confidence=min_alias_confidence,
    )

    logger.info("Building Markdown report...")
    report_md = _build_markdown_report(knowledge, transitions, alias_data)

    if dry_run:
        logger.info("Dry run — no files written.")
        logger.info(
            "Would write: %s, %s, %s, %s",
            knowledge_out, transitions_out, alias_out, report_out,
        )
        return {
            "knowledge": knowledge_out,
            "transitions": transitions_out,
            "alias_candidates": alias_out,
            "report": report_out,
        }

    # Write artifacts
    for path in (knowledge_out, transitions_out, alias_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    def _write_json(obj: Any, path: Path) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
        logger.info("Wrote %s (%d bytes)", path, path.stat().st_size)

    _write_json(knowledge, knowledge_out)
    _write_json(transitions, transitions_out)
    _write_json(alias_data, alias_out)

    with report_out.open("w", encoding="utf-8") as f:
        f.write(report_md)
    logger.info("Wrote %s (%d bytes)", report_out, report_out.stat().st_size)

    # Log summary
    n_trans_src = len(transitions["global_transitions"])
    n_alias = alias_data["summary"]["total_candidates"]
    n_alias_new = n_alias - alias_data["summary"]["already_in_aliases"]
    logger.info(
        "Done. Zone priors: %d zones. Tag families: %d. Transitions: %d source tags. "
        "Alias candidates: %d total (%d new).",
        len(knowledge["zone_tag_priors"]),
        len(knowledge["tag_families"]),
        n_trans_src,
        n_alias,
        n_alias_new,
    )

    return {
        "knowledge": knowledge_out,
        "transitions": transitions_out,
        "alias_candidates": alias_out,
        "report": report_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build semantic knowledge artifacts from the ground-truth corpus.",
        epilog=(
            "Run from AI-structuring/backend/:\n"
            "  python tools/build_semantic_knowledge.py\n"
            "  python tools/build_semantic_knowledge.py --min-support 5 --dry-run"
        ),
    )
    parser.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH_PATH,
                        help=f"Input ground_truth.jsonl (default: {GROUND_TRUTH_PATH})")
    parser.add_argument("--allowed-styles", type=Path, default=ALLOWED_STYLES_PATH,
                        help=f"Input allowed_styles.json (default: {ALLOWED_STYLES_PATH})")
    parser.add_argument("--style-aliases", type=Path, default=STYLE_ALIASES_PATH,
                        help=f"Input style_aliases.json (default: {STYLE_ALIASES_PATH})")
    parser.add_argument("--knowledge-out", type=Path, default=KNOWLEDGE_OUT,
                        help=f"Output tag_semantics_knowledge.json (default: {KNOWLEDGE_OUT})")
    parser.add_argument("--transitions-out", type=Path, default=TRANSITIONS_OUT,
                        help=f"Output tag_transition_priors.json (default: {TRANSITIONS_OUT})")
    parser.add_argument("--alias-out", type=Path, default=ALIAS_CANDIDATES_OUT,
                        help=f"Output style_alias_candidates.json (default: {ALIAS_CANDIDATES_OUT})")
    parser.add_argument("--report-out", type=Path, default=REPORT_OUT,
                        help=f"Output Markdown report (default: {REPORT_OUT})")
    parser.add_argument("--min-support", type=int, default=3,
                        help="Minimum bigram count for transition priors (default: 3)")
    parser.add_argument("--min-alias-confidence", type=float, default=0.70,
                        help="Minimum confidence to include alias candidate (default: 0.70)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write any output files")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: INFO)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run(
        gt_path=args.ground_truth,
        allowed_path=args.allowed_styles,
        aliases_path=args.style_aliases,
        knowledge_out=args.knowledge_out,
        transitions_out=args.transitions_out,
        alias_out=args.alias_out,
        report_out=args.report_out,
        min_support=args.min_support,
        min_alias_confidence=args.min_alias_confidence,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
