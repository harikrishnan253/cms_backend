"""
Structural marker paragraph locking.

Before LLM classification, paragraphs containing only structural markers
(e.g. ``<CN>``, ``<CT>``, ``<REF>``, ``<TAB6.1>``) are locked to the PMI
tag so the LLM cannot modify or misinterpret their content.

Marker pattern: ``^<[^<>]+>$`` (angle-bracketed content, no nested brackets)

Codebase note: The spec requested ``MARKER`` as the tag, but this tag does
not exist in the allowed-styles vocabulary. ``PMI`` (Page Marker Instruction)
is the established tag for marker-only paragraphs in this codebase.

**Two-phase locking**:
1. Pre-LLM: ``lock_marker_blocks()`` marks blocks with ``skip_llm=True``
2. Post-classification: ``relock_marker_classifications()`` enforces PMI on any
   marker blocks that leaked through or were changed by downstream passes.

Runs BEFORE ``classify_blocks_with_prompt()`` (Stage 1b) and AFTER classification
(Stage 3.5) in the pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)

# Structural marker pattern: <ANYTHING> but no nested brackets
_MARKER_RE = re.compile(r"^<[^<>]+>$")


@dataclass
class MarkerLockMetrics:
    """Metrics for marker locking operations."""

    markers_total: int = 0
    """Total marker blocks found in document."""

    relocked: int = 0
    """Marker blocks re-locked in post-classification pass."""

    leaked_to_llm: int = 0
    """Marker blocks that were sent to LLM despite skip_llm flag."""

    rules_fired: dict[str, int] = field(default_factory=dict)
    """Breakdown of which rules fired (for diagnostics)."""


def _is_marker_block(text: str) -> bool:
    """Check if text matches structural marker pattern.

    Parameters
    ----------
    text : str
        Paragraph text to check.

    Returns
    -------
    bool
        True if text is a marker-only paragraph (e.g. ``<CN>``), False otherwise.
    """
    if not text or not text.strip():
        return False
    trimmed = text.strip()
    return _MARKER_RE.match(trimmed) is not None


def lock_marker_blocks(blocks: Sequence[dict]) -> list[dict]:
    """Lock structural marker paragraphs to PMI tag.

    For every block whose text matches the marker pattern (``^<[^<>]+>$``),
    the following fields are set:

    * ``block["lock_style"]``      → ``True``
    * ``block["allowed_styles"]``  → ``["PMI"]``
    * ``block["skip_llm"]``        → ``True``

    The ``lock_style`` + ``allowed_styles`` mechanism causes the deterministic
    gate (Rule 0) to assign ``PMI`` at 99% confidence, bypassing the LLM.

    **Edge case handling**:
    - Whitespace around the marker is trimmed before matching
    - Empty text or whitespace-only blocks are skipped
    - Text is never modified; only metadata flags are set

    **Examples of matched markers**:
    - ``<CN>`` (chapter number)
    - ``<CT>`` (chapter title)
    - ``<REF>`` (reference section)
    - ``<TAB6.1>`` (table marker with ID)
    - ``<H1-INTRO>`` (heading marker)

    **Examples NOT matched**:
    - ``<H1>Introduction`` (has content after marker)
    - ``<<nested>>`` (nested brackets)
    - ``<incomplete`` (missing closing bracket)
    - ``  <MARKER>  `` (trimmed to ``<MARKER>``, then matched)

    Parameters
    ----------
    blocks : sequence of dict
        Block list from ``extract_blocks()``. Modified **in-place**;
        returned as a list for pipeline chaining.

    Returns
    -------
    list of dict
        The same block objects (identity), for chaining convenience.

    Logging
    -------
    Emits: ``MARKER_LOCK_PRE markers_total=<int>``
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    markers_total = 0
    for block in blocks:
        text = block.get("text", "")
        if not _is_marker_block(text):
            continue

        block["lock_style"] = True
        block["allowed_styles"] = ["PMI"]
        block["skip_llm"] = True
        block["_is_marker"] = True  # Track for post-classification check

        markers_total += 1

    if markers_total > 0:
        logger.info(
            "MARKER_LOCK_PRE markers_total=%d",
            markers_total,
        )

    return blocks


def relock_marker_classifications(
    blocks: Sequence[dict],
    classifications: Sequence[dict],
) -> list[dict]:
    """Re-lock marker classifications to PMI after classification pass.

    This is the **post-classification enforcement** that ensures marker blocks
    stay as PMI even if downstream heuristics or normalizers changed them.

    **Purpose**: Some normalizers or validators might modify tags. This pass
    is the FINAL AUTHORITY that marker blocks must always be PMI.

    **Detection**:
    - Identifies marker blocks from their text pattern OR ``_is_marker`` flag
    - Checks if classification tag is PMI
    - Overrides non-PMI tags back to PMI

    **Leak detection**:
    - Case A (true leak): block had ``skip_llm=True`` AND received LLM-generated
      output (``gated=False`` or ``reasoning`` without ``rule_based=True``).
      Logged as WARNING; counted in ``leaked_to_llm`` metric.
    - Case B (no prior lock): marker identified by text pattern or ``_is_marker``
      flag but without ``skip_llm=True`` metadata. Logged at DEBUG only; not
      counted in ``leaked_to_llm`` metric.

    Parameters
    ----------
    blocks : sequence of dict
        Block list with text and metadata.
    classifications : sequence of dict
        Classification list that may need correction.

    Returns
    -------
    list of dict
        Corrected classifications with marker blocks enforced to PMI.

    Logging
    -------
    Emits: ``MARKER_LOCK markers_total=<int> relocked=<int> leaked_to_llm=<int>``

    Examples
    --------
    Input (marker block classified as TXT by mistake):

        Block: {text: "<CN>", _is_marker: True}
        Classification: {tag: "TXT", confidence: 85}

    Output (corrected to PMI):

        {tag: "PMI", confidence: 99, relocked: True, original_tag: "TXT"}
    """
    classifications = list(classifications)
    if not classifications:
        return classifications

    # Build lookup by block ID
    block_by_id = {b.get("id"): b for b in blocks if "id" in b}

    markers_total = 0
    relocked = 0
    leaked_to_llm = 0

    for clf in classifications:
        clf_id = clf.get("id")
        if clf_id not in block_by_id:
            continue

        block = block_by_id[clf_id]
        text = block.get("text", "")

        # Check if this is a marker block
        is_marker = block.get("_is_marker") or _is_marker_block(text)
        if not is_marker:
            continue

        markers_total += 1

        # Check if leaked to LLM.
        # A block is "LLM-touched" if:
        #   - llm_generated=True (set by _classify_chunk on true LLM outputs), OR
        #   - gated is explicitly False (LLM path — backward compat signal).
        # Presence of "reasoning" alone is NOT sufficient — rule-based and
        # deterministic classifiers also set "reasoning".
        # Two distinct cases once llm_touched is True:
        #   Case A (true leak): block had skip_llm=True — log WARNING + count.
        #   Case B (no prior lock): marker detected post-hoc without skip_llm
        #     metadata — log DEBUG only, do not count in leaked_to_llm metric.
        had_skip_llm = block.get("skip_llm") is True
        llm_touched = (
            (clf.get("llm_generated") is True or clf.get("gated") is False)
            and not clf.get("rule_based")
        )
        if llm_touched:
            if had_skip_llm:
                leaked_to_llm += 1
                logger.warning(
                    "marker-lock: block %s leaked to LLM despite skip_llm flag (text=%r)",
                    clf_id,
                    text[:50],
                )
            else:
                logger.debug(
                    "marker-lock: block %s is a marker but had no skip_llm lock"
                    " (text=%r); relocked to PMI",
                    clf_id,
                    text[:50],
                )

        # Check if tag is already PMI
        current_tag = clf.get("tag", "")
        if current_tag == "PMI":
            continue

        # Override to PMI
        clf["tag"] = "PMI"
        clf["confidence"] = 99
        clf["relocked"] = True
        clf["original_tag"] = current_tag

        relocked += 1

        logger.debug(
            "marker-lock: relocked block %s from %s to PMI (text=%r)",
            clf_id,
            current_tag,
            text[:50],
        )

    # Emit structured log
    if markers_total > 0:
        logger.info(
            "MARKER_LOCK markers_total=%d relocked=%d leaked_to_llm=%d",
            markers_total,
            relocked,
            leaked_to_llm,
        )

    return classifications
