"""
Deterministic gating layer for LLM classification.

Before sending paragraphs to the Gemini LLM, this module identifies blocks
that can be classified purely from metadata and text patterns.  Gated blocks
receive a high-confidence classification immediately; only ambiguous blocks
are forwarded to the LLM, reducing token usage and cost.

Called from ``classify_blocks_with_prompt`` in ``classifier.py``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from .marker_rules import parse_marker_token, resolve_marker_style

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Box prefix mapping (mirrors validator.py BOX_PREFIX_BY_ZONE)
# ---------------------------------------------------------------------------
_BOX_PREFIX = {
    "BOX_NBX": "NBX",
    "BOX_BX1": "BX1",
    "BOX_BX2": "BX2",
    "BOX_BX3": "BX3",
    "BOX_BX4": "BX4",
    "BOX_BX6": "BX6",
    "BOX_BX7": "BX7",
    "BOX_BX15": "BX15",
    "BOX_BX16": "BX16",
}

# ---------------------------------------------------------------------------
# Table-zone text patterns (mirrors validator.py lines 527-533)
# ---------------------------------------------------------------------------
_TABLE_FOOTNOTE_RE = re.compile(
    r"^(?:"
    r"note"              # "Note …"
    r"|[a-z]\)"          # "a) …"
    r")",
    re.IGNORECASE,
)
_TABLE_FOOTNOTE_SYMBOLS = frozenset("*†‡§‖¶#")

_TABLE_SOURCE_RE = re.compile(
    r"^(?:"
    r"source\s*:"
    r"|sources\s*:"
    r"|adapted\s+from"
    r"|reproduced\s+from"
    r"|reprinted\s+from"
    r"|data\s+from"
    r"|courtesy\s+of"
    r"|with\s+permission"
    r")",
    re.IGNORECASE,
)

# Lettered footnote in table zone: single lowercase letter + space
_TABLE_LETTER_NOTE_RE = re.compile(r"^[a-z]\s")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class GateMetrics:
    """Tracks deterministic-gate statistics for a single classification run."""

    total_blocks: int = 0
    gated_count: int = 0
    llm_count: int = 0
    rules_fired: dict[str, int] = field(default_factory=dict)

    def _inc(self, rule: str) -> None:
        self.rules_fired[rule] = self.rules_fired.get(rule, 0) + 1


# ---------------------------------------------------------------------------
# Single-block deterministic classifier
# ---------------------------------------------------------------------------

def classify_deterministic(block: dict) -> dict | None:
    """Try to classify *block* deterministically.

    Returns a classification dict
    ``{"id", "tag", "confidence", "gated": True, "gate_rule": str}``
    or *None* when the block cannot be resolved without the LLM.
    """
    pid = block.get("id")
    text = block.get("text", "")
    meta = block.get("metadata", {})
    zone = meta.get("context_zone", "BODY")

    def _result(tag: str, conf: float, rule: str) -> dict:
        return {
            "id": pid,
            "tag": tag,
            "confidence": int(conf * 100),
            "gated": True,
            "gate_rule": rule,
        }

    # --- Rule 0: lock_style (pre-classified by ref_numbering, etc.) ---
    if block.get("lock_style"):
        allowed = block.get("allowed_styles")
        if allowed:
            return _result(allowed[0], 0.99, "gate-locked-style")

    # --- Rule 0b: explicit skip_llm (hard exclusion from LLM) ---
    if block.get("skip_llm"):
        allowed = block.get("allowed_styles")
        tag = allowed[0] if allowed else "PMI"
        return _result(tag, 0.99, "gate-skip-llm")

    # --- Rule 1: empty / whitespace-only ---
    if not text or not text.strip():
        # Empty cells inside a TABLE zone are structural padding, not page markers.
        # Assigning PMI would break zone-style validation; use T (plain table body).
        if zone == "TABLE":
            return _result("T", 0.99, "gate-empty-table")
        return _result("PMI", 0.99, "gate-empty")

    # --- Rule 2 & 3: marker tokens ---
    token = parse_marker_token(text)
    if token is not None:
        style = resolve_marker_style(token, text, meta)
        if style is not None:
            return _result(style, 0.99, "gate-marker")
        # Marker-only paragraph with no resolved style → PMI
        remainder = text.strip()
        # Check if the text is *only* the marker token (+ whitespace)
        after = re.sub(r"^\s*</?[A-Za-z][A-Za-z0-9 _-]*>\s*", "", remainder)
        if not after:
            return _result("PMI", 0.99, "gate-marker-only")

    # --- Rule 4: table caption ---
    if meta.get("caption_type") == "table":
        return _result("T1", 0.99, "gate-table-caption")

    # --- Rule 5: figure caption ---
    if meta.get("caption_type") == "figure":
        return _result("FIG-LEG", 0.99, "gate-figure-caption")

    # --- Rule 6: source line ---
    if meta.get("source_line"):
        return _result("TSN", 0.99, "gate-source-line")

    # --- Rule 7: box start/end markers ---
    if meta.get("box_marker") in ("start", "end"):
        return _result("PMI", 0.99, "gate-box-marker")

    # --- Rule 8: box label ---
    if meta.get("box_label") and zone.startswith("BOX_"):
        prefix = _BOX_PREFIX.get(zone)
        if prefix:
            return _result(f"{prefix}-TYPE", 0.95, "gate-box-label")

    # --- Rule 9: box title ---
    if meta.get("box_title") and zone.startswith("BOX_"):
        prefix = _BOX_PREFIX.get(zone)
        if prefix:
            return _result(f"{prefix}-TTL", 0.95, "gate-box-title")

    # --- TABLE zone rules (10 & 11) ---
    if zone == "TABLE":
        stripped = text.strip()
        stripped_lower = stripped.lower()

        # Rule 11 first: source pattern (check before footnote)
        if _TABLE_SOURCE_RE.match(stripped):
            return _result("TSN", 0.95, "gate-table-source")

        # Rule 10: footnote pattern
        if (
            stripped_lower.startswith("note")
            or (stripped and stripped[0] in _TABLE_FOOTNOTE_SYMBOLS)
            or _TABLE_LETTER_NOTE_RE.match(stripped)
            or _TABLE_FOOTNOTE_RE.match(stripped)
        ):
            return _result("TFN", 0.95, "gate-table-footnote")

    # --- Rule 12: very short non-letter tokens ---
    non_ws = text.strip()
    if len(non_ws) <= 2 and not any(c.isalpha() for c in non_ws):
        return _result("PMI", 0.90, "gate-short-token")

    return None


# ---------------------------------------------------------------------------
# Batch gating entry point
# ---------------------------------------------------------------------------

def gate_for_llm(
    blocks: Sequence[dict],
) -> tuple[list[dict], list[dict], GateMetrics]:
    """Split *blocks* into deterministic classifications and LLM-needed blocks.

    Returns
    -------
    gated_classifications : list of dict
        Classification dicts for blocks resolved deterministically.
    llm_blocks : list of dict
        Block dicts that still need LLM classification.
    metrics : GateMetrics
        Counts and rule breakdown.
    """
    metrics = GateMetrics(total_blocks=len(blocks))
    gated: list[dict] = []
    llm_needed: list[dict] = []

    for block in blocks:
        clf = classify_deterministic(block)
        if clf is not None:
            gated.append(clf)
            metrics.gated_count += 1
            metrics._inc(clf["gate_rule"])
        else:
            llm_needed.append(block)
            metrics.llm_count += 1

    if gated:
        logger.info(
            "deterministic-gate: %d/%d blocks gated (%.1f%%), %d forwarded to LLM",
            metrics.gated_count,
            metrics.total_blocks,
            metrics.gated_count / max(metrics.total_blocks, 1) * 100,
            metrics.llm_count,
        )
        for rule, count in sorted(metrics.rules_fired.items()):
            logger.debug("  %s: %d", rule, count)

    return gated, llm_needed, metrics
