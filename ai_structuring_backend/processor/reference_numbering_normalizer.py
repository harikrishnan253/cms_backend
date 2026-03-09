"""
Deterministic reference list numbering normalization.

Post-processor that normalizes reference entry numbering to:
- Sequential 1, 2, 3... with no gaps
- Single house format enforced everywhere
- Preserves reference text content (only modifies number prefix)

Runs AFTER classification/validation, BEFORE DOCX reconstruction.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Sequence

logger = logging.getLogger(__name__)

# House format: choose ONE and enforce everywhere
# Option A: "1. " (period + space)
# Option B: "1) " (paren + space)
HOUSE_FORMAT = "1. "  # Using "N. " format as house standard

# Debug flag from environment
DEBUG_REFERENCE_NORMALIZATION = os.environ.get("DEBUG_REFERENCE_NORMALIZATION", "").lower() in ("1", "true", "yes")


def normalize_reference_numbering(blocks: Sequence[dict]) -> list[dict]:
    """Normalize reference list numbering to house format.

    **House format**: ``1. `` (number + period + space)

    **What it does**:

    1. Identifies reference/bibliography blocks (BACK_MATTER zone or REF tags)
    2. Extracts current numbering from each reference entry
    3. Renumbers sequentially: 1, 2, 3... (no gaps, no duplicates)
    4. Converts all formats to house format: ``1. ``, ``2. ``, ``3. ``...
    5. Preserves all text content except the number prefix

    **Formats normalized**:

    - ``[1]`` → ``1. ``
    - ``(1)`` → ``1. ``
    - ``1)`` → ``1. ``
    - ``1.`` → ``1. `` (already correct)
    - Superscript numbers → ``1. ``
    - Mixed formats → all converted to house format

    **Idempotency**:

    Running this function multiple times on the same input produces
    identical output (no changes after first normalization).

    **Logging**:

    Emits structured log:
    ``REFERENCE_NORMALIZATION changed=<bool> before_count=<int> after_count=<int> renumbered=<int>``

    **Debug mode**:

    Set ``DEBUG_REFERENCE_NORMALIZATION=1`` to print diff of first 5 changes.

    Parameters
    ----------
    blocks : sequence of dict
        Classified block list with ``id``, ``text``, ``tag``, ``metadata``.
        Modified **in-place** (text rewritten).

    Returns
    -------
    list of dict
        The same blocks, with reference numbering normalized.

    Examples
    --------
    Input::

        [1] First reference
        (2) Second reference
        4. Fourth reference (gap)

    Output::

        1. First reference
        2. Second reference
        3. Fourth reference (fixed)
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    # Find reference blocks
    ref_blocks = _find_reference_blocks(blocks)
    if not ref_blocks:
        logger.debug("reference-numbering-normalizer: no reference blocks found")
        _log_normalization(changed=False, before_count=0, after_count=0, renumbered=0)
        return blocks

    before_count = len(ref_blocks)

    # Extract current numbering
    numbered_blocks = []
    for block in ref_blocks:
        text = block.get("text", "")
        current_num, prefix_len = _extract_number_prefix(text)
        if current_num is not None:
            numbered_blocks.append((block, current_num, prefix_len))

    if not numbered_blocks:
        logger.debug("reference-numbering-normalizer: no numbered entries found")
        _log_normalization(changed=False, before_count=before_count, after_count=0, renumbered=0)
        return blocks

    # Check if already correct (idempotency check)
    already_correct = _check_if_correct(numbered_blocks)

    if already_correct:
        logger.debug("reference-numbering-normalizer: already correctly numbered")
        _log_normalization(changed=False, before_count=before_count, after_count=len(numbered_blocks), renumbered=0)
        return blocks

    # Renumber sequentially
    renumbered_count = 0
    diff_examples = []

    for idx, (block, old_num, prefix_len) in enumerate(numbered_blocks, start=1):
        new_num = idx
        old_text = block.get("text", "")

        # Generate new prefix in house format
        new_prefix = f"{new_num}. "

        # Replace old prefix with new prefix
        # Remove old prefix (prefix_len chars) and prepend new one
        remaining_text = old_text[prefix_len:].lstrip()
        new_text = new_prefix + remaining_text

        # Update block text
        if old_text != new_text:
            block["text"] = new_text
            renumbered_count += 1

            # Collect diff examples for debug
            if DEBUG_REFERENCE_NORMALIZATION and len(diff_examples) < 5:
                diff_examples.append((old_text[:80], new_text[:80]))

    # Log normalization
    changed = renumbered_count > 0
    _log_normalization(
        changed=changed,
        before_count=before_count,
        after_count=len(numbered_blocks),
        renumbered=renumbered_count,
    )

    # Print debug diff if enabled
    if DEBUG_REFERENCE_NORMALIZATION and diff_examples:
        logger.info("Reference numbering changes (first 5):")
        for old, new in diff_examples:
            logger.info(f"  - {old}")
            logger.info(f"  + {new}")

    return blocks


def _find_reference_blocks(blocks: Sequence[dict]) -> list[dict]:
    """Find reference/bibliography blocks."""
    ref_blocks = []

    for block in blocks:
        meta = block.get("metadata", {})
        zone = meta.get("context_zone", "")
        tag = block.get("tag") or meta.get("tag", "")

        # Include BACK_MATTER zone or REF-tagged blocks
        if zone == "BACK_MATTER" or tag.startswith("REF"):
            # Skip marker-only blocks
            text = block.get("text", "").strip()
            if text and not (text.startswith("<") and text.endswith(">")):
                ref_blocks.append(block)

    return ref_blocks


def _extract_number_prefix(text: str) -> tuple[int | None, int]:
    """Extract reference number and prefix length from text.

    Returns
    -------
    tuple[int | None, int]
        (number, prefix_length) or (None, 0) if no number found.
    """
    if not text:
        return None, 0

    # Try various numbering formats
    patterns = [
        (r'^\s*\[(\d+)\]\s*', r'^\s*\[\d+\]\s*'),      # [1]
        (r'^\s*\((\d+)\)\s*', r'^\s*\(\d+\)\s*'),      # (1)
        (r'^\s*(\d+)\.\s+', r'^\s*\d+\.\s+'),          # 1.
        (r'^\s*(\d+)\)\s*', r'^\s*\d+\)\s*'),          # 1)
        (r'^\s*(\d+)\s+', r'^\s*\d+\s+'),              # 1 (space)
    ]

    for capture_pattern, full_pattern in patterns:
        match = re.match(capture_pattern, text)
        if match:
            try:
                number = int(match.group(1))
                # Find full prefix length (including whitespace)
                full_match = re.match(full_pattern, text)
                prefix_len = len(full_match.group(0)) if full_match else len(match.group(0))
                return number, prefix_len
            except (ValueError, IndexError):
                continue

    return None, 0


def _check_if_correct(numbered_blocks: list[tuple[dict, int, int]]) -> bool:
    """Check if numbering is already correct (idempotency check).

    Returns True if:
    - Numbers are sequential (1, 2, 3, ...)
    - All use house format "N. "
    """
    for idx, (block, current_num, prefix_len) in enumerate(numbered_blocks, start=1):
        # Check if sequential
        if current_num != idx:
            return False

        # Check if using house format
        text = block.get("text", "")
        expected_prefix = f"{idx}. "
        if not text.startswith(expected_prefix) and not text.lstrip().startswith(expected_prefix):
            return False

    return True


def _log_normalization(
    changed: bool,
    before_count: int,
    after_count: int,
    renumbered: int,
) -> None:
    """Emit structured log line."""
    logger.info(
        "REFERENCE_NORMALIZATION changed=%s before_count=%d after_count=%d renumbered=%d",
        str(changed).lower(),
        before_count,
        after_count,
        renumbered,
    )
