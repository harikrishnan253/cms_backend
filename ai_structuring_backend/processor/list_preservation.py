"""
List hierarchy preservation from Word XML numbering.

Enforces list structure from original Word document after LLM classification,
preventing the LLM from flattening or corrupting list hierarchy.

**SOURCE OF TRUTH**: Word numbering properties (w:numPr, w:ilvl, w:numId)
from the input DOCX, NOT the LLM's classification.

**What it does:**

1. Identifies paragraphs that were lists in the original Word document
2. Verifies LLM classification matches expected list style
3. Overrides misclassified list items back to correct style
4. Preserves:
   - List level (ilvl)
   - Ordered vs unordered type
   - List sequence grouping (numId)

Runs AFTER classification, BEFORE reconstruction (Stage 3.5).
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)


# List tag mapping by level and type
_LIST_TAGS = {
    "bullet": {
        0: "BL-MID",
        1: "BL2-MID",
        2: "BL3-MID",
        3: "BL4-MID",
    },
    "number": {
        0: "NL-MID",
        1: "NL2-MID",
        2: "NL3-MID",
        3: "NL4-MID",
    },
}


def _list_position_suffix(tag: str) -> str | None:
    """Return FIRST/MID/LAST suffix when present."""
    if not tag or "-" not in tag:
        return None
    suffix = tag.rsplit("-", 1)[-1]
    return suffix if suffix in {"FIRST", "MID", "LAST"} else None


def _is_position_compatible(current_tag: str, expected_tag: str) -> bool:
    """True when current tag matches expected list family/level and only differs by position.

    Accepts both exact-family and prefixed-family variants so that normaliser-
    assigned prefixed tags (e.g. ``KT-BL-FIRST``) are not needlessly coerced
    back to their base family.

    Examples::

        # exact match
        _is_position_compatible("BL-FIRST", "BL-MID")    → True
        # prefixed variant — KT-BL shares the same level as BL
        _is_position_compatible("KT-BL-FIRST", "BL-MID") → True
        # wrong level
        _is_position_compatible("BL2-FIRST", "BL-MID")   → False
        # incompatible family
        _is_position_compatible("NL-FIRST",  "BL-MID")   → False
    """
    if current_tag == expected_tag:
        return True
    if not current_tag or not expected_tag:
        return False
    if not expected_tag.endswith("-MID"):
        return False

    expected_family = expected_tag[:-4]   # e.g. "BL-"  or  "BL2-"  (trailing dash)
    suffix = _list_position_suffix(current_tag)
    if suffix is None:
        return False

    # Exact-family match  (e.g. current="BL-FIRST", expected_family="BL-")
    if current_tag == f"{expected_family}-{suffix}":
        return True

    # Prefixed-family match: current ends with "-<base_family_no_dash>-<suffix>"
    # e.g. "KT-BL-FIRST" ends with "-BL-FIRST"  when expected_family="BL-"
    bare_family = expected_family.rstrip("-")   # "BL" or "BL2"
    if current_tag.endswith(f"-{bare_family}-{suffix}"):
        return True

    return False


def _coerce_expected_tag_preserving_position(current_tag: str, expected_tag: str) -> str:
    """Override to expected family/level, retaining FIRST/LAST when classifier had a position suffix.

    This keeps list-run continuity (set by ``normalize_list_runs``) while still
    enforcing Word XML list type/level.

    When the current tag already carries a prefix (e.g. ``KT-BL-FIRST``) but the
    expected tag is a base family (e.g. ``BL-MID``), we prefer the *prefixed* form
    (``KT-BL-FIRST``) to avoid silently stripping the semantic prefix.

    Falls back to ``expected_tag`` (the plain ``*-MID`` form) only when:
    * no position suffix is present on the current tag, OR
    * the expected tag does not end with ``-MID``.
    """
    if not expected_tag.endswith("-MID"):
        return expected_tag
    suffix = _list_position_suffix(current_tag)
    if suffix is None:
        return expected_tag

    # Prefer current tag's family when it is a prefixed variant of the expected
    # base family (to avoid stripping meaningful prefixes like KT-, OBJ-, etc.)
    expected_base = expected_tag[:-4].rstrip("-")   # e.g. "BL"
    if current_tag.endswith(f"-{expected_base}-{suffix}"):
        # current carries a valid prefix; return the prefixed form.
        return current_tag

    return f"{expected_tag[:-4]}-{suffix}"


def enforce_list_hierarchy_from_word_xml(
    blocks: Sequence[dict],
    classifications: Sequence[dict],
) -> list[dict]:
    """Enforce list hierarchy from Word XML after classification.

    Identifies paragraphs that were lists in the original document and
    ensures they're classified with correct list styles, overriding LLM
    if needed.

    **Preserves:**
    - List level (ilvl from Word XML)
    - List type (bullet vs numbered)
    - List grouping (numId sequences)

    **Overrides:**
    - LLM classifications that incorrectly tag list items as body text
    - Wrong list levels
    - Wrong list types (bullet vs numbered)

    Parameters
    ----------
    blocks : sequence of dict
        Block list with Word XML metadata (``xml_list_level``, ``xml_num_id``).
    classifications : sequence of dict
        LLM classifications that may need correction.

    Returns
    -------
    list of dict
        Corrected classifications with list hierarchy enforced.

    Examples
    --------
    Input (LLM misclassified nested list as body)::

        Block: {metadata: {xml_list_level: 1, has_bullet: true}}
        LLM:   {tag: "TXT"}

    Output (corrected to nested bullet)::

        {tag: "BL2-MID"}

    Logging
    -------
    Emits: ``LIST_HIERARCHY_ENFORCEMENT list_paras=<int> restored=<int> overrides=<int> unmatched=<int>``
    """
    classifications = list(classifications)
    if not classifications:
        return classifications

    # Build metadata lookup by block ID
    meta_by_id = {}
    for block in blocks:
        block_id = block.get("id")
        meta = block.get("metadata", {})
        if block_id:
            meta_by_id[block_id] = meta

    # Track statistics
    list_paras = 0
    restored = 0
    overrides = 0
    unmatched = 0

    # Process each classification
    for clf in classifications:
        clf_id = clf.get("id")
        if clf_id not in meta_by_id:
            continue

        meta = meta_by_id[clf_id]

        # TABLE-zone paragraphs use TBL-* styles, not BL-*/NL-*. Skip both
        # the OOXML path and the fallback path so TBL-MID is never rewritten.
        if meta.get("context_zone") == "TABLE":
            continue

        # Reference-zone paragraphs carry SR/REF-* family tags. List coercion
        # must not overwrite them — skip both OOXML and fallback paths.
        if meta.get("is_reference_zone") or meta.get("context_zone") == "REFERENCE":
            continue

        # Check if this paragraph was a list in Word
        xml_level = meta.get("xml_list_level")
        xml_num_id = meta.get("xml_num_id")

        if xml_level is None:
            # Fallback: use detector-enriched list_style_prefix when OOXML
            # numPr is absent (style-based or indent-detected lists).
            list_style_prefix = meta.get("list_style_prefix")
            if not list_style_prefix:
                continue

            list_paras += 1
            expected_tag = f"{list_style_prefix}MID"
            current_tag = clf.get("tag", "")

            if not _is_position_compatible(current_tag, expected_tag):
                corrected_tag = _coerce_expected_tag_preserving_position(
                    current_tag, expected_tag
                )
                clf["tag"] = corrected_tag
                clf["list_preserved"] = True
                clf["original_tag"] = current_tag
                overrides += 1
                logger.debug(
                    "list-preservation: corrected block %s from %s to %s"
                    " (prefix-fallback, list_style_prefix=%s)",
                    clf_id,
                    current_tag,
                    corrected_tag,
                    list_style_prefix,
                )
            else:
                restored += 1
            continue

        list_paras += 1

        # Determine list type
        list_type = _determine_list_type(meta)
        if not list_type:
            logger.debug(
                "list-preservation: block %s has xml_list_level but unclear type, skipping",
                clf_id,
            )
            unmatched += 1
            continue

        # Determine expected tag based on level and type
        expected_tag = _get_expected_tag(list_type, xml_level)
        if not expected_tag:
            logger.debug(
                "list-preservation: no tag mapping for level=%d type=%s",
                xml_level,
                list_type,
            )
            unmatched += 1
            continue

        current_tag = clf.get("tag", "")

        # Accept FIRST/LAST variants when family/level/type matches.
        if not _is_position_compatible(current_tag, expected_tag):
            corrected_tag = _coerce_expected_tag_preserving_position(current_tag, expected_tag)
            # Override to correct list tag
            clf["tag"] = corrected_tag
            clf["list_preserved"] = True
            clf["original_tag"] = current_tag
            overrides += 1

            logger.debug(
                "list-preservation: corrected block %s from %s to %s (level=%d, type=%s, numId=%s)",
                clf_id,
                current_tag,
                corrected_tag,
                xml_level,
                list_type,
                xml_num_id,
            )
        else:
            # Already correct
            restored += 1

    # Log results
    _log_enforcement(
        list_paras=list_paras,
        restored=restored,
        overrides=overrides,
        unmatched=unmatched,
    )

    return classifications


def _determine_list_type(meta: dict) -> str | None:
    """Determine list type from metadata.

    Returns
    -------
    str or None
        "bullet", "number", or None if unclear
    """
    # Check explicit flags
    if meta.get("has_bullet"):
        return "bullet"
    if meta.get("has_numbering"):
        return "number"

    # Check if generic XML list (ambiguous type)
    if meta.get("has_xml_list"):
        # Default to bullet for ambiguous cases
        # This is safer than defaulting to number
        return "bullet"

    return None


def _get_expected_tag(list_type: str, level: int) -> str | None:
    """Get expected WK tag for list type and level.

    Parameters
    ----------
    list_type : str
        "bullet" or "number"
    level : int
        0-based nesting level (0 = top level)

    Returns
    -------
    str or None
        Tag name (e.g. "BL-MID", "NL2-MID") or None if level out of range
    """
    tags = _LIST_TAGS.get(list_type, {})

    # Clamp to max supported level
    level = min(level, 3)

    return tags.get(level)


def _log_enforcement(
    list_paras: int,
    restored: int,
    overrides: int,
    unmatched: int,
) -> None:
    """Emit structured log line."""
    logger.info(
        "LIST_HIERARCHY_ENFORCEMENT list_paras=%d restored=%d overrides=%d unmatched=%d",
        list_paras,
        restored,
        overrides,
        unmatched,
    )
