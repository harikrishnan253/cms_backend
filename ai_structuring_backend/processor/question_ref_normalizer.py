"""
Deterministic question / reference numbering tag normalizer.

Detects numbered-question and reference patterns in classified paragraphs
and enforces canonical tag assignment:

* Numbered question markers (``1.``, ``(1)``, ``1)``, ``Q1.``)
  in EXERCISE or question context → ``QUES-NL-*``
* Question body text following a question number → ``QUES-TXT-FLUSH``
* Numbered reference lines in BACK_MATTER → ``REF-N``

Non-canonical alias tags (e.g. ``QUES_NUM``, ``REF_TXT``) are
resolved via ``style_aliases.json`` before any pattern rules fire.

Runs AFTER LLM classification + main validation, alongside other
Stage 3 post-processors.  Integrated in the pipeline between
``apply_table_note_overrides`` and Stage 3.5 text normalization.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Numbering patterns
# ---------------------------------------------------------------------------

# "1. ", "12. ", "100. "
_NUM_DOT_RE = re.compile(r"^\s*(\d+)\.\s")

# "(1) ", "(12) "
_NUM_PAREN_RE = re.compile(r"^\s*\((\d+)\)\s")

# "1) ", "12) "
_NUM_RPAREN_RE = re.compile(r"^\s*(\d+)\)\s")

# "Q1.", "Q12."
_Q_NUM_RE = re.compile(r"^\s*Q(\d+)\.\s", re.IGNORECASE)

# Union: matches any of the four numbering shapes
_ANY_NUMBER_RE = re.compile(
    r"^\s*(?:Q\d+\.\s|\d+\.\s|\(\d+\)\s|\d+\)\s)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Context constants
# ---------------------------------------------------------------------------

# Zones where numbered items are questions (not references)
_QUESTION_ZONES = frozenset({"EXERCISE"})

# Zones where numbered items are references
_REFERENCE_ZONES = frozenset({"BACK_MATTER"})

# Tag prefixes that signal question context even in BODY zone
_QUES_TAG_PREFIXES = ("QUES-", "REV-QUES-", "EXER-", "CS-QUES-", "BX1-QUES-")

# Tags that are already canonical question-number tags
_CANONICAL_QUES_NL = frozenset({
    "QUES-NL-FIRST", "QUES-NL-MID", "QUES-NL-LAST",
    "REV-QUES-NL-FIRST", "REV-QUES-NL-MID", "REV-QUES-NL-LAST",
})

# Tags that are already canonical reference tags
_CANONICAL_REF = frozenset({"REF-N", "REF-N0", "REF-N-FIRST", "REF-U"})

# ---------------------------------------------------------------------------
# Style aliases (loaded once at import time)
# ---------------------------------------------------------------------------

_ALIASES_PATH = Path(__file__).resolve().parents[1] / "config" / "style_aliases.json"


def _load_aliases() -> dict[str, str]:
    try:
        with open(_ALIASES_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("question-ref-normalizer: could not load %s", _ALIASES_PATH)
        return {}


_ALIASES: dict[str, str] = _load_aliases()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_reference_numbering(
    blocks: Sequence[dict],
    classifications: list[dict],
    allowed_styles: Iterable[str] | None = None,
) -> list[dict]:
    """Normalize tags for numbered questions and reference lines.

    For each classification whose block text matches a numbering
    pattern (``1.``, ``(1)``, ``1)``, ``Q1.``), the tag is
    enforced to the canonical value based on document zone:

    * **EXERCISE / question context** → ``QUES-NL-MID``
      (position suffixes are handled by ``normalize_list_runs``).
    * **BACK_MATTER** → ``REF-N``
    * **BODY with Word XML numbering but no question context** →
      left unchanged (respects list truth from Word XML).

    Non-canonical alias names are resolved first via
    ``style_aliases.json``.

    Parameters
    ----------
    blocks : sequence of dict
        Block list from ingestion (used for text / metadata lookup).
    classifications : list of dict
        Current classification dicts, in document order.
    allowed_styles : iterable of str, optional
        Valid style tags.  When a proposed tag is not in this set the
        original tag is kept.  Pass *None* to skip validation.

    Returns
    -------
    list of dict
        New classification list (shallow copies for changed entries,
        originals for unchanged).
    """
    if not classifications:
        return classifications

    block_lookup: dict[int, dict] = {b["id"]: b for b in blocks}
    allowed: set[str] | None = (
        set(allowed_styles) if allowed_styles is not None else None
    )

    result: list[dict] = list(classifications)
    assigned = 0
    corrected = 0

    for i, clf in enumerate(result):
        tag = clf.get("tag", "")

        # --- Step 1: alias resolution ---
        canonical_tag = _ALIASES.get(tag, tag)
        alias_changed = canonical_tag != tag

        # --- Step 2: context detection ---
        block = block_lookup.get(clf.get("id"), {})
        meta = block.get("metadata", {})
        text = block.get("text", "")
        zone = meta.get("context_zone", "BODY")
        has_word_numbering = bool(meta.get("has_numbering"))

        is_numbered_text = bool(_ANY_NUMBER_RE.match(text))

        if not is_numbered_text and not alias_changed:
            continue

        in_question_zone = zone in _QUESTION_ZONES
        in_reference_zone = zone in _REFERENCE_ZONES

        # Also detect question context from neighboring tags
        if not in_question_zone and not in_reference_zone:
            in_question_zone = _is_question_context(
                i, result, canonical_tag,
            )

        # --- Step 3: determine target tag ---
        target_tag: str | None = None
        reason: str | None = None

        if is_numbered_text and in_question_zone:
            # Numbered text in question/exercise context → QUES-NL-MID
            if canonical_tag not in _CANONICAL_QUES_NL:
                target_tag = "QUES-NL-MID"
                reason = "ques-number-detected"
        elif is_numbered_text and in_reference_zone:
            # Numbered text in reference zone → REF-N
            if canonical_tag not in _CANONICAL_REF:
                target_tag = "REF-N"
                reason = "ref-number-detected"
        elif alias_changed:
            # Non-numbered text but alias resolved → apply alias
            target_tag = canonical_tag
            reason = "alias-resolved"

        if target_tag is None:
            continue

        # --- Step 4: respect Word XML list truth ---
        # If Word says this is a numbered list item in BODY zone
        # (not question/reference zone), don't override it; the
        # LLM + list normalizer have final authority on body lists.
        if (
            has_word_numbering
            and zone == "BODY"
            and not in_question_zone
            and not in_reference_zone
        ):
            continue

        # --- Step 5: allowed_styles validation ---
        if allowed is not None and target_tag not in allowed:
            logger.debug(
                "question-ref-normalizer: skip para %s  %s -> %s "
                "(not in allowed_styles)",
                clf.get("id"),
                tag,
                target_tag,
            )
            continue

        # --- Step 6: apply ---
        result[i] = {
            **clf,
            "tag": target_tag,
            "repaired": True,
            "repair_reason": (
                (clf.get("repair_reason") or "") + f",{reason}"
            ).lstrip(","),
        }

        if alias_changed and reason == "alias-resolved":
            corrected += 1
        else:
            assigned += 1

        logger.debug(
            "question-ref-normalizer: para %s  %s -> %s (%s)",
            result[i].get("id"),
            tag,
            target_tag,
            reason,
        )

    logger.info(
        "REFERENCE_NORMALIZATION assigned=%d corrected=%d",
        assigned,
        corrected,
    )

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUES_CONTEXT_RANGE = 10  # search ±10 entries for question-context tags


def _is_question_context(
    index: int,
    classifications: list[dict],
    own_tag: str,
) -> bool:
    """Return True if tags in the neighbourhood indicate question context."""
    if own_tag.startswith(_QUES_TAG_PREFIXES):
        return True

    n = len(classifications)
    lo = max(0, index - _QUES_CONTEXT_RANGE)
    hi = min(n, index + _QUES_CONTEXT_RANGE + 1)

    for j in range(lo, hi):
        if j == index:
            continue
        neighbor_tag = classifications[j].get("tag", "")
        if neighbor_tag.startswith(_QUES_TAG_PREFIXES):
            return True

    return False
