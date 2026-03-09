"""
Deterministic list hierarchy enforcement from Word XML.

Before LLM classification, paragraphs with Word XML numbering properties
(``numPr.ilvl``) are locked to level-specific list tags so the LLM cannot
misclassify their indentation level.

Codebase note: The spec requested ``LIST_LEVEL_1/2/3`` tags, but these do
not exist in the allowed-styles vocabulary. Instead, this implementation uses
the standard list family tags (``BL-MID``, ``NL-MID``, ``UL-MID``) which
the list normalizer will later adjust to correct ``FIRST/MID/LAST`` positions.

The ``xml_list_level`` (Word's ``ilvl``) is extracted during ingestion from
``para._p.pPr.numPr.ilvl.val`` and stored in block metadata.

Runs BEFORE ``classify_blocks_with_prompt()`` in the pipeline.
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)


def enforce_list_hierarchy_from_word_xml(blocks: Sequence[dict]) -> list[dict]:
    """Lock list paragraphs with XML ilvl to level-specific tags.

    For every block that has Word XML list properties (``numPr``), the
    indentation level (``ilvl``) is read from ``metadata["xml_list_level"]``
    (extracted during ingestion) and mapped to a deterministic tag:

    * ilvl == 0 → ``BL-MID`` (bullet list, level 1)
    * ilvl == 1 → ``BL2-MID`` (bullet list, level 2)
    * ilvl == 2 → ``BL3-MID`` (bullet list, level 3)
    * ilvl >= 3 → ``BL4-MID`` (bullet list, level 4+)

    The chosen tag family (``BL``, ``NL``, ``UL``) is determined by existing
    metadata hints (``has_bullet``, ``has_numbering``, ``has_xml_list``).

    The following fields are set:

    * ``block["lock_style"]``      → ``True``
    * ``block["allowed_styles"]``  → ``[tag]``
    * ``block["skip_llm"]``        → ``True``

    ``lock_style`` + ``allowed_styles`` cause the deterministic gate (Rule 0)
    to assign the tag at 99% confidence, bypassing the LLM. The downstream
    list normalizer will correct ``-MID`` to ``-FIRST/-MID/-LAST`` as needed.

    Parameters
    ----------
    blocks : sequence of dict
        Block list from ``extract_blocks()``. Modified **in-place**;
        returned as a list for pipeline chaining.

    Returns
    -------
    list of dict
        The same block objects (identity), for chaining convenience.
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    marked = 0
    skipped_table = 0
    for block in blocks:
        meta = block.get("metadata", {})

        # TABLE zone paragraphs must NOT be list-locked: list styles (BL-MID, NL-MID,
        # etc.) are invalid in TABLE zone and the cell-position normalizer handles
        # multi-paragraph cells separately.
        if meta.get("context_zone") == "TABLE":
            skipped_table += 1
            continue

        # Check for XML list level (ilvl extracted from Word numPr during ingestion)
        xml_level = meta.get("xml_list_level")

        if xml_level is None:
            # Fallback: use detector-enriched list_style_prefix when OOXML numPr
            # is absent (style-based or indent-only lists detected by
            # _enrich_list_metadata in extract_blocks).
            list_style_prefix = meta.get("list_style_prefix")
            if not list_style_prefix:
                continue
            tag = f"{list_style_prefix}MID"  # e.g. "BL2-MID", "NL-MID"
            block["lock_style"] = True
            block["allowed_styles"] = [tag]
            block["skip_llm"] = True
            marked += 1
            continue

        # Determine list family from metadata hints
        has_bullet = meta.get("has_bullet", False)
        has_numbering = meta.get("has_numbering", False)
        has_xml_list = meta.get("has_xml_list", False)

        if has_bullet:
            family = "BL"
        elif has_numbering:
            family = "NL"
        elif has_xml_list:
            family = "UL"  # Ambiguous XML list → unordered
        else:
            # Fallback: no type hint, default to bullet
            family = "BL"

        # Map ilvl to tag suffix:
        # ilvl 0 → level 1 (base family)
        # ilvl 1 → level 2 (family + "2")
        # ilvl 2 → level 3 (family + "3")
        # ilvl 3+ → level 4 (family + "4")
        if xml_level == 0:
            tag = f"{family}-MID"
        elif xml_level == 1:
            tag = f"{family}2-MID"
        elif xml_level == 2:
            tag = f"{family}3-MID"
        else:
            tag = f"{family}4-MID"

        block["lock_style"] = True
        block["allowed_styles"] = [tag]
        block["skip_llm"] = True

        marked += 1

    if marked or skipped_table:
        logger.info(
            "list-hierarchy: locked %d list paragraphs from Word XML ilvl; skipped %d TABLE-zone paragraphs",
            marked,
            skipped_table,
        )

    return blocks
