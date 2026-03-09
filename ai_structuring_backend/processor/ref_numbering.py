"""
Deterministic reference-numbering preservation.

Before LLM classification, numbered reference entries (e.g. "1. WHO...",
"2. CDC...") are detected and locked so the LLM cannot strip their
structural numbering or misclassify them.

Runs BEFORE ``classify_blocks_with_prompt()`` in the pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from app.services.reference_zone import detect_reference_zone

logger = logging.getLogger(__name__)

# Pattern: leading digits + period + whitespace  ("1. ", "12. ", etc.)
_NUMBERED_REF_RE = re.compile(r"^\s*\d+\.\s+")


def normalize_reference_numbering(blocks: Sequence[dict]) -> list[dict]:
    """Mark numbered reference entries to preserve their structure.

    For every block inside the detected reference zone whose text starts
    with a numbered pattern (``1. …``, ``2. …``), the following fields
    are set:

    * ``block["metadata"]["ref_numbered"] = True``
    * ``block["lock_style"] = True``
    * ``block["allowed_styles"] = ["REF-N"]``

    The ``lock_style`` flag is consumed by the deterministic gate to
    assign the tag directly (skipping LLM classification), and by the
    validator to preserve the tag.

    Parameters
    ----------
    blocks : sequence of dict
        Block list from ``extract_blocks()``.  Modified **in-place**;
        returned as a list for chaining convenience.

    Returns
    -------
    list of dict
        The same block objects (identity), for pipeline chaining.
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    ref_ids, trigger, _ = detect_reference_zone(blocks)
    if not ref_ids:
        return blocks

    marked = 0
    for block in blocks:
        bid = block.get("id")
        if bid not in ref_ids:
            continue

        text = block.get("text", "")
        if not _NUMBERED_REF_RE.match(text):
            continue

        # Set metadata flag
        meta = block.setdefault("metadata", {})
        meta["ref_numbered"] = True

        # Lock the block so downstream gate / validator skip LLM
        block["lock_style"] = True
        block["allowed_styles"] = ["REF-N"]

        marked += 1

    if marked:
        logger.info(
            "ref-numbering: marked %d numbered reference entries (trigger=%s)",
            marked,
            trigger,
        )

    return blocks
