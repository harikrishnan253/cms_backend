"""
Deterministic table-title classification override.

Before LLM classification, paragraphs matching the table-title pattern
(e.g. "Table 1", "Table 2.3 Demographics") are locked to the T1 tag so
the LLM cannot misclassify them as BODY text or HEADING styles.

Codebase note: The canonical tag for table titles is ``T1`` (with ``T11``
and ``T12`` as text-flow variants).  There is no ``TABLE_TITLE`` tag in
the allowed-styles vocabulary; ``T1`` is used instead.

Runs BEFORE ``classify_blocks_with_prompt()`` in the pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

logger = logging.getLogger(__name__)

# Table title: "Table 1", "Table 12", "Table 1.2", "Table 10.3 Results …"
_TABLE_TITLE_RE = re.compile(r"^Table\s+\d+(\.\d+)?\b")


def enforce_table_title_rules(blocks: Sequence[dict]) -> list[dict]:
    """Lock table-title paragraphs to the T1 tag.

    For every block whose text matches the ``Table N`` / ``Table N.M``
    pattern the following fields are set:

    * ``metadata["context_zone"]`` → ``"TABLE"``
    * ``metadata["table_title"]``  → ``True``
    * ``block["lock_style"]``      → ``True``
    * ``block["allowed_styles"]``  → ``["T1"]``
    * ``block["skip_llm"]``        → ``True``

    ``lock_style`` + ``allowed_styles`` cause the deterministic gate
    (Rule 0) to assign ``T1`` at 99% confidence, bypassing the LLM
    entirely.  ``skip_llm`` is a forward-compatible flag for any
    downstream component that checks it.

    Parameters
    ----------
    blocks : sequence of dict
        Block list from ``extract_blocks()``.  Modified **in-place**;
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
    for block in blocks:
        text = block.get("text", "")
        if not _TABLE_TITLE_RE.match(text):
            continue

        meta = block.setdefault("metadata", {})
        meta["context_zone"] = "TABLE"
        meta["table_title"] = True

        block["lock_style"] = True
        block["allowed_styles"] = ["T1"]
        block["skip_llm"] = True

        marked += 1

    if marked:
        logger.info(
            "table-title-rules: locked %d table title paragraphs to T1",
            marked,
        )

    return blocks
