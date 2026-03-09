"""
Table-note / source-note classification utilities.

Rules:
- Source attribution lines → TSN  (priority)
- Note / symbol / letter footnote lines → TFN

Public API:
    is_table_note(text, zone, near_table)  → (tag, reason) | None
    _has_table_anchor(clfs, idx, range_)   → bool
    apply_table_note_overrides(blocks, clfs, allowed) → list[dict]
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Source attribution prefixes — checked FIRST (higher priority than footnotes).
_SOURCE_PREFIXES = (
    "source:",
    "sources:",
    "adapted from",
    "reproduced from",
    "reprinted from",
    "data from",
    "courtesy of",
    "with permission from",
    "from ",            # "From the 2020 Census", etc.
)

# Note-header prefixes
_NOTE_PREFIXES = ("note:", "notes:")

# Symbol footnotes: *, †, ‡, §, #
_FOOTNOTE_SYMBOL_RE = re.compile(r"^[*†‡§#]")

# Parenthesised-letter: "a) ...", "b) ..."
_FOOTNOTE_PAREN_RE = re.compile(r"^[a-z]\)\s", re.IGNORECASE)

# Letter-space: "a Adjusted ...", "b Note text ..."
_FOOTNOTE_LETTER_RE = re.compile(r"^[a-z]\s+\S", re.IGNORECASE)

# Digit-space: "1 Adjusted ...", "2 See below ..."
_FOOTNOTE_DIGIT_RE = re.compile(r"^\d\s+\S")

# ---------------------------------------------------------------------------
# Table-anchor detection
# ---------------------------------------------------------------------------

# Tags that unambiguously anchor a nearby paragraph to a table context.
_TABLE_ANCHOR_EXACT = frozenset({"T1", "T11", "T12", "TSN", "T2", "T4"})

# Prefixes whose tags are also table anchors.
_TABLE_ANCHOR_PREFIXES = ("TFN", "TBL", "TH")


def _has_table_anchor(
    clfs: list[dict],
    idx: int,
    range_: int = 10,
) -> bool:
    """Return True if any neighbour within *range_* of *idx* is a table tag.

    *idx* itself is excluded from the search.
    """
    start = max(0, idx - range_)
    end = min(len(clfs), idx + range_ + 1)
    for j in range(start, end):
        if j == idx:
            continue
        tag = clfs[j].get("tag", "")
        if tag in _TABLE_ANCHOR_EXACT:
            return True
        if any(tag.startswith(p) for p in _TABLE_ANCHOR_PREFIXES):
            return True
    return False


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------

def is_table_note(
    text: Optional[str],
    zone: str,
    near_table: bool,
) -> Optional[tuple[str, str]]:
    """Classify *text* as a table source note (TSN) or footnote (TFN).

    Returns:
        ``("TSN", "table-source-note")`` for source attribution lines.
        ``("TFN", "table-footnote")`` for note / symbol / letter footnotes.
        ``None`` when the text does not match, *near_table* is False, or
        the zone is TABLE (TABLE-zone lines are handled inline in validator.py).
    """
    if not near_table:
        return None
    if zone == "TABLE":
        return None
    if not text or not text.strip():
        return None

    stripped = text.strip()
    lower = stripped.lower()

    # --- Source attribution (FIRST — higher priority) ---
    for prefix in _SOURCE_PREFIXES:
        if lower.startswith(prefix):
            return ("TSN", "table-source-note")

    # --- Note-header ---
    if any(lower.startswith(p) for p in _NOTE_PREFIXES):
        return ("TFN", "table-footnote")

    # --- Symbol footnotes ---
    if _FOOTNOTE_SYMBOL_RE.match(stripped):
        return ("TFN", "table-footnote")

    # --- Parenthesised-letter footnotes ---
    if _FOOTNOTE_PAREN_RE.match(stripped):
        return ("TFN", "table-footnote")

    # --- Letter-space footnotes ---
    if _FOOTNOTE_LETTER_RE.match(stripped):
        return ("TFN", "table-footnote")

    # --- Digit-space footnotes ---
    if _FOOTNOTE_DIGIT_RE.match(stripped):
        return ("TFN", "table-footnote")

    return None


# ---------------------------------------------------------------------------
# Post-classification override pass
# ---------------------------------------------------------------------------

def apply_table_note_overrides(
    blocks: list[dict],
    clfs: list[dict],
    allowed: Optional[set[str]],
) -> list[dict]:
    """Re-tag paragraphs adjacent to tables that look like source notes or footnotes.

    Only touches paragraphs that:
    - are NOT in TABLE zone
    - do NOT already carry a TFN* or TSN tag
    - have a table anchor (T1, TFN*, TBL*, etc.) within 10 positions
    - match a source or footnote text pattern

    Unmodified entries are returned as-is (identity preserved).
    Modified entries have their ``tag``, ``repaired``, and ``repair_reason``
    fields updated in-place.
    """
    for idx, (block, clf) in enumerate(zip(blocks, clfs)):
        current_tag = clf.get("tag", "")

        # Already correctly tagged — skip (identity preserved).
        if current_tag.startswith("TFN") or current_tag == "TSN":
            continue

        # TABLE-zone paragraphs are handled by inline validator logic.
        zone = (block.get("metadata") or {}).get("context_zone", "BODY")
        if zone == "TABLE":
            continue

        text = block.get("text", "")
        near_table = _has_table_anchor(clfs, idx)

        result = is_table_note(text, zone, near_table)
        if result is None:
            continue

        new_tag, reason = result

        # Validate against the caller's allowed-styles set.
        if allowed is not None and new_tag not in allowed:
            continue

        # Mutate in-place so that unchanged entries keep their identity.
        clf["tag"] = new_tag
        clf["repaired"] = True
        existing_reason = clf.get("repair_reason")
        if existing_reason:
            clf["repair_reason"] = f"{existing_reason};{reason}"
        else:
            clf["repair_reason"] = reason

    return clfs
