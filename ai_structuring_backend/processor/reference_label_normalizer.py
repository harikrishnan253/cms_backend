"""
Reference label normalization for numbered bibliography entries.

Normalizes reference labels in the REFERENCES/BACK_MATTER zone to:
- Fix duplicated numbers
- Fill gaps in numbering
- Standardize format (bracket/paren/period style)
- Ensure sequential 1..N ordering

Runs AFTER classification in the pipeline (Stage 3/4).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

logger = logging.getLogger(__name__)

# Label format patterns (in priority order for detection)
_LABEL_PATTERNS = [
    (r'^\s*\[(\d+)\]\s*', '[{}]'),      # [1] format
    (r'^\s*\((\d+)\)\s*', '({})'),      # (1) format
    (r'^\s*(\d+)\.\s+', '{}.'),         # 1. format
    (r'^\s*(\d+)\)\s*', '{})'),         # 1) format
    (r'^\s*(\d+)\s+', '{}'),            # 1 format (space after)
]


def normalize_reference_labels(
    blocks: Sequence[dict],
    min_labeled_entries: int = 5,
) -> list[dict]:
    """Normalize reference labels to sequential numbering.

    Detects and fixes:
    - Duplicate numbers (1, 2, 2, 3 → 1, 2, 3, 4)
    - Gaps in numbering (1, 2, 5, 7 → 1, 2, 3, 4)
    - Mixed formats ([1], 2., (3) → [1], [2], [3])
    - Non-sequential ordering

    **How it works**:

    1. Locate reference zone blocks (BACK_MATTER or zone starting with REF)
    2. Parse leading labels from each reference entry
    3. Detect the first valid label's format (e.g., "[1]" vs "1.")
    4. If ≥ min_labeled_entries found, renumber sequentially
    5. Rewrite only the leading label, preserve remaining text

    **Label format detection**:

    The function tries these patterns in order:
    - ``[N]`` → output as ``[1]``, ``[2]``, ``[3]``...
    - ``(N)`` → output as ``(1)``, ``(2)``, ``(3)``...
    - ``N.`` → output as ``1.``, ``2.``, ``3.``...
    - ``N)`` → output as ``1)``, ``2)``, ``3)``...
    - ``N `` → output as ``1``, ``2``, ``3``... (space after number)

    **Edge cases**:

    - Unlabeled references: left unchanged, labeled ones still renumbered
    - < min_labeled_entries: no normalization performed
    - Multiple reference zones: each zone normalized independently
    - Marker lines (``<REF>``, ``<REFH1>``): never modified

    Parameters
    ----------
    blocks : sequence of dict
        Classified block list with ``id``, ``text``, ``metadata`` fields.
        Modified **in-place**; returned as a list for chaining.
    min_labeled_entries : int, optional
        Minimum number of labeled entries required to trigger normalization.
        Default: 5.

    Returns
    -------
    list of dict
        The same block objects (identity), for chaining convenience.

    Examples
    --------
    Input blocks with duplicates::

        1. First reference
        2. Second reference
        2. Third reference (duplicate)
        4. Fourth reference (gap)

    Output after normalization::

        1. First reference
        2. Second reference
        3. Third reference (fixed)
        4. Fourth reference (sequential)
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    # Find reference zone blocks
    ref_blocks = _find_reference_blocks(blocks)
    if not ref_blocks:
        logger.debug("reference-label-normalizer: no reference zone found")
        return blocks

    # Parse labels from reference entries
    label_info = _parse_reference_labels(ref_blocks)
    if not label_info:
        logger.debug("reference-label-normalizer: no labeled entries found")
        return blocks

    # Detect label format from first valid entry
    chosen_format = _detect_label_format(ref_blocks, label_info)
    if not chosen_format:
        logger.debug("reference-label-normalizer: could not detect label format")
        return blocks

    # Count labeled entries
    labeled_count = len([info for info in label_info if info is not None])
    if labeled_count < min_labeled_entries:
        logger.debug(
            "reference-label-normalizer: only %d labeled entries (< %d), skipping",
            labeled_count,
            min_labeled_entries,
        )
        return blocks

    # Renumber sequentially
    renumbered = _renumber_labels(ref_blocks, label_info, chosen_format)

    # Log results
    logger.info(
        "REF_NUM_NORMALIZED count_entries=%d count_labeled=%d chosen_format=%s",
        len(ref_blocks),
        labeled_count,
        repr(chosen_format),
    )

    return blocks


def _find_reference_blocks(blocks: Sequence[dict]) -> list[dict]:
    """Find blocks in reference/back matter zone."""
    ref_blocks = []
    for block in blocks:
        meta = block.get("metadata", {})
        zone = meta.get("context_zone", "")
        tag = meta.get("tag") or block.get("tag", "")

        # Include BACK_MATTER zone or REF-tagged blocks
        if zone == "BACK_MATTER" or zone.startswith("REF") or tag.startswith("REF"):
            ref_blocks.append(block)

    return ref_blocks


def _parse_reference_labels(blocks: Sequence[dict]) -> list[dict | None]:
    """Parse leading labels from reference entries.

    Returns
    -------
    list of dict | None
        For each block, either:
        - ``{"original_label": str, "number": int, "pattern": str, "format": str}``
        - ``None`` if no label found
    """
    label_info = []

    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            label_info.append(None)
            continue

        # Skip marker-only lines (e.g., "<REF>", "<REFH1>")
        if text.startswith("<") and text.endswith(">"):
            label_info.append(None)
            continue

        # Try each label pattern
        found = False
        for pattern, fmt in _LABEL_PATTERNS:
            match = re.match(pattern, text)
            if match:
                try:
                    number = int(match.group(1))
                    label_info.append({
                        "original_label": match.group(0),
                        "number": number,
                        "pattern": pattern,
                        "format": fmt,
                    })
                    found = True
                    break
                except (ValueError, IndexError):
                    continue

        if not found:
            label_info.append(None)

    return label_info


def _detect_label_format(
    blocks: Sequence[dict],
    label_info: Sequence[dict | None],
) -> str | None:
    """Detect label format from first valid entry.

    Returns
    -------
    str | None
        Format string like "[{}]" or "{}." or None if no valid labels found.
    """
    for info in label_info:
        if info is not None:
            return info["format"]
    return None


def _renumber_labels(
    blocks: Sequence[dict],
    label_info: Sequence[dict | None],
    chosen_format: str,
) -> int:
    """Renumber labels sequentially, rewriting block text.

    Returns
    -------
    int
        Number of blocks renumbered.
    """
    renumbered = 0
    new_number = 1

    for block, info in zip(blocks, label_info):
        if info is None:
            # No label found, leave unchanged
            continue

        # Generate new label
        new_label = chosen_format.format(new_number)

        # Rewrite text: replace old label with new label
        old_text = block.get("text", "")
        old_label = info["original_label"]

        # Ensure old_label is at the start of text
        if old_text.startswith(old_label) or old_text.lstrip().startswith(old_label):
            # Replace only the first occurrence
            new_text = old_text.replace(old_label, new_label + " ", 1)
            block["text"] = new_text
            renumbered += 1

            # Debug log
            logger.debug(
                "reference-label-normalizer: block %d: %s → %s",
                block.get("id"),
                repr(old_label.strip()),
                repr(new_label),
            )

        new_number += 1

    return renumbered
