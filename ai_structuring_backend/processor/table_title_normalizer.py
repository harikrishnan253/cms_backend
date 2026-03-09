"""
Table title style/tag normalization (structure-safe).

This module only normalizes table-title block tagging/metadata in-place.
It must not reorder, add, remove, merge, or split blocks.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from .structural_invariants import assert_style_tag_only_block_transform, snapshot_blocks_for_contract

logger = logging.getLogger(__name__)

# Table title patterns (actual titles, not markers)
_TABLE_TITLE_PATTERNS = [
    r"^Table\s+(\d+(?:\.\d+)?)\b",  # "Table 5.1"
    r"^TABLE\s+(\d+(?:\.\d+)?)\b",  # "TABLE 5.1"
]

# Table marker/anchor patterns
_TABLE_MARKER_PATTERNS = [
    r"^<TAB\s*(\d+(?:\.\d+)?)>",  # "<TAB5.1>"
    r"^<INSERT\s+TAB\s*(\d+(?:\.\d+)?)>",  # "<INSERT TAB5.1>"
]

# Canonical table title style (from WK Template)
TABLE_TITLE_STYLE = "T1"

# Window size for searching titles around table anchors
SEARCH_WINDOW = 3


def normalize_table_titles(blocks: Sequence[dict]) -> list[dict]:
    """Normalize table-title tags/metadata without structural mutation.

    Structural safety contract:
    - same block count in/out
    - same ordered block IDs in/out
    - no reordering/deletion/insertion

    The function may retag detected table-title blocks to `TABLE_TITLE_STYLE`
    and update table-title metadata.
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    before_snapshot = snapshot_blocks_for_contract(blocks)

    anchors = _find_table_anchors(blocks)
    if not anchors:
        logger.debug("table-title-normalizer: no table anchors found")
        assert_style_tag_only_block_transform(before_snapshot, blocks, stage="table_title_normalizer")
        return blocks

    tables_found = len(anchors)
    titles_fixed = 0
    titles_restyled = 0
    placement_mismatches = 0

    # Structure-safe mode: inspect and retag only; no index-changing operations.
    for anchor_idx, table_num in anchors:
        candidates = _find_title_candidates(blocks, anchor_idx, table_num)
        if not candidates:
            logger.debug(
                "table-title-normalizer: no title found for anchor at idx %d",
                anchor_idx,
            )
            continue

        title_idx = _select_best_candidate(candidates, anchor_idx, table_num, blocks)
        if title_idx is None:
            continue

        title_block = blocks[title_idx]
        if title_idx != anchor_idx - 1:
            placement_mismatches += 1
            logger.debug(
                "table-title-normalizer: title idx %d not adjacent to anchor idx %d; preserving order in structure-safe mode",
                title_idx,
                anchor_idx,
            )

        current_style = title_block.get("tag") or title_block.get("metadata", {}).get("tag", "")
        if current_style != TABLE_TITLE_STYLE:
            _set_title_style(title_block)
            titles_restyled += 1
            logger.debug(
                "table-title-normalizer: retagged block %s to %s",
                title_block.get("id"),
                TABLE_TITLE_STYLE,
            )
        else:
            # Still ensure metadata is normalized for correctly tagged titles.
            _set_title_style(title_block)

        titles_fixed += 1

    if titles_fixed > 0:
        logger.info(
            "TABLE_TITLE_ENFORCED tables_found=%d titles_fixed=%d titles_restyled=%d placement_mismatches=%d structure_safe=1",
            tables_found,
            titles_fixed,
            titles_restyled,
            placement_mismatches,
        )

    assert_style_tag_only_block_transform(before_snapshot, blocks, stage="table_title_normalizer")
    return blocks


def _find_table_anchors(blocks: Sequence[dict]) -> list[tuple[int, str | None]]:
    """Find table anchor blocks (markers) and optional table numbers."""
    anchors: list[tuple[int, str | None]] = []

    for idx, block in enumerate(blocks):
        text = block.get("text", "").strip()
        for pattern in _TABLE_MARKER_PATTERNS:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                anchors.append((idx, match.group(1)))
                break

    return anchors


def _find_title_candidates(
    blocks: Sequence[dict],
    anchor_idx: int,
    table_num: str | None,
) -> list[int]:
    """Find title candidate blocks near anchor.

    Searches `SEARCH_WINDOW` paragraphs before and after anchor.
    """
    del table_num  # Selection logic handles number preference later.
    candidates: list[int] = []
    start = max(0, anchor_idx - SEARCH_WINDOW)
    end = min(len(blocks), anchor_idx + SEARCH_WINDOW + 1)

    for idx in range(start, end):
        if idx == anchor_idx:
            continue
        text = blocks[idx].get("text", "").strip()
        if not text:
            continue
        if _is_title_candidate(text, None):
            candidates.append(idx)

    return candidates


def _is_title_candidate(text: str, expected_table_num: str | None) -> bool:
    """Check whether text looks like a table title."""
    del expected_table_num

    if not text or not text.strip():
        return False
    if len(text) > 200:
        return False

    for pattern in _TABLE_TITLE_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return True

    if re.match(r"^Table\s*:", text, re.IGNORECASE) or re.match(r"^Table\s+", text, re.IGNORECASE):
        return True

    return False


def _select_best_candidate(
    candidates: list[int],
    anchor_idx: int,
    table_num: str | None,
    blocks: Sequence[dict],
) -> int | None:
    """Select best title candidate near an anchor.

    Prefers matching table number, then closest distance, then before-anchor.
    """
    if not candidates:
        return None

    def extract_table_num(text: str) -> str | None:
        for pattern in _TABLE_TITLE_PATTERNS:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    if table_num:
        matching_candidates: list[int] = []
        numberless_candidates: list[int] = []

        for idx in candidates:
            candidate_num = extract_table_num(blocks[idx].get("text", ""))
            if candidate_num == table_num:
                matching_candidates.append(idx)
            elif candidate_num is None:
                numberless_candidates.append(idx)

        if matching_candidates:
            candidates = matching_candidates
        elif numberless_candidates:
            candidates = numberless_candidates
        else:
            return None

    if len(candidates) == 1:
        return candidates[0]

    scored: list[tuple[int, int]] = []
    for idx in candidates:
        score = 0
        score -= abs(idx - anchor_idx) * 10
        if idx < anchor_idx:
            score += 5
        scored.append((score, idx))

    scored.sort(reverse=True)
    return scored[0][1]


def _set_title_style(block: dict) -> None:
    """Retag block as TABLE_TITLE and mark table-title metadata."""
    block["tag"] = TABLE_TITLE_STYLE
    meta = block.setdefault("metadata", {})
    meta["tag"] = TABLE_TITLE_STYLE
    meta["context_zone"] = "TABLE"
    meta["table_title"] = True
