"""
Table cell list-position normalizer.

When a table cell contains 2+ paragraphs that all carry list indicators
(``has_bullet``, ``has_numbering``, or ``has_xml_list``) and are currently
tagged with a "flat" T-family style (``T``, ``T2``, ``T4``, ``TBL-MID``),
this normalizer re-tags them positionally:

* First paragraph  → ``TBL-FIRST``
* Middle paragraph(s) → ``TBL-MID``
* Last paragraph   → ``TBL-LAST``

Cells that already contain ``TBL-FIRST`` or ``TBL-LAST`` are skipped (already
correct). Cells with a single paragraph, or where no paragraph carries a list
indicator, are left unchanged.

Runs after ``relock_marker_classifications`` in Stage 3.5, before confidence
filtering and quality scoring.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Sequence

logger = logging.getLogger(__name__)

# Flat T-family styles that can be promoted to positional TBL-* styles.
_FLAT_T_FAMILY: frozenset[str] = frozenset({"T", "T2", "T4", "TBL-MID"})

# Positional styles that mark a cell as already processed.
_POSITIONAL_STYLES: frozenset[str] = frozenset({"TBL-FIRST", "TBL-LAST"})

# Publisher-specific table body / heading styles (e.g. ENA, JBL).
#
# These are semantically complete equivalents of the canonical T / T2 / TH*
# family and must NOT be promoted to positional TBL-FIRST/MID/LAST variants.
# More importantly, their presence anywhere in a cell or column is treated as
# a signal that the whole cell/column uses the publisher's tag family – so
# co-resident T-family paragraphs (which may be mis-classifications by the
# LLM) are also left unchanged, preventing TB→TBL-* over-conversion.
_PUBLISHER_TABLE_STYLES: frozenset[str] = frozenset({
    "TB",    # ENA/JBL table body cell (publisher equivalent of T / TBL-MID)
    "TCH1",  # ENA table column heading level-1 (publisher equivalent of TH1/T2)
    "TCH",   # ENA table column heading generic
    "TT",    # ENA table title alternate (publisher equivalent of T1)
})


def _has_list_indicator(meta: dict) -> bool:
    return bool(
        meta.get("has_bullet")
        or meta.get("has_numbering")
        or meta.get("has_xml_list")
    )


def _relabel_positional_run(
    run_bids: list[int],
    clf_by_id: dict[int, dict],
    *,
    key_for_log,
) -> int:
    """Apply TBL-FIRST/MID/LAST to an eligible run and return relabel count."""
    if len(run_bids) < 2:
        return 0

    # If a run already carries explicit positional tags, avoid clobbering it.
    if any(clf_by_id.get(bid, {}).get("tag") in _POSITIONAL_STYLES for bid in run_bids):
        return 0

    relabeled = 0
    for pos, bid in enumerate(run_bids):
        clf = clf_by_id[bid]
        if pos == 0:
            new_tag = "TBL-FIRST"
        elif pos == len(run_bids) - 1:
            new_tag = "TBL-LAST"
        else:
            new_tag = "TBL-MID"

        if clf["tag"] != new_tag:
            old_tag = clf["tag"]
            clf["tag"] = new_tag
            clf["confidence"] = max(clf.get("confidence", 85), 85)
            clf.setdefault("repair_reason", [])
            if isinstance(clf["repair_reason"], list):
                clf["repair_reason"].append("cell-position-normalized")
            clf["repaired"] = True
            logger.debug(
                "table-cell-position: block %s %s→%s (group=%s)",
                bid,
                old_tag,
                new_tag,
                key_for_log,
            )
            relabeled += 1
    return relabeled


def normalize_table_cell_positions(
    classifications: Sequence[dict],
    blocks: Sequence[dict],
) -> list[dict]:
    """Re-tag multi-paragraph table-cell lists with positional TBL-* styles.

    Parameters
    ----------
    classifications : sequence of dict
        Current classification dicts (``{"id", "tag", "confidence", ...}``).
    blocks : sequence of dict
        Block dicts from ``extract_blocks()``, used for table-cell metadata.

    Returns
    -------
    list of dict
        Updated classifications (same objects, modified in-place where needed).

    Logging
    -------
    Emits ``TABLE_CELL_POSITIONS cells_normalized=<int> paragraphs_relabeled=<int>``
    """
    classifications = list(classifications)
    if not classifications:
        return classifications

    # Build lookup: block id → block metadata
    block_by_id: dict[int, dict] = {b["id"]: b for b in blocks if "id" in b}

    # Build classification lookup by id
    clf_by_id: dict[int, dict] = {c["id"]: c for c in classifications}

    # -------------------------------------------------------------------
    # Group TABLE-zone block IDs by (table_index, row_index, cell_index).
    # Preserve insertion order (ingestion order = para_in_cell order).
    # -------------------------------------------------------------------
    cell_groups: dict[tuple, list[int]] = defaultdict(list)

    for block_id, block in block_by_id.items():
        meta = block.get("metadata", {})
        if meta.get("context_zone") != "TABLE":
            continue
        key = (
            meta.get("table_index", -1),
            meta.get("row_index", -1),
            meta.get("cell_index", -1),
        )
        cell_groups[key].append(block_id)

    # Sort each group by para_in_cell to guarantee positional order.
    for key in cell_groups:
        cell_groups[key].sort(
            key=lambda bid: block_by_id[bid].get("metadata", {}).get("para_in_cell", 0)
        )

    cells_normalized = 0
    paragraphs_relabeled = 0

    for key, bid_list in cell_groups.items():
        if len(bid_list) < 2:
            continue  # Single-paragraph cell → nothing to do

        # Skip if any paragraph already has positional TBL-FIRST/LAST style.
        if any(
            clf_by_id.get(bid, {}).get("tag") in _POSITIONAL_STYLES
            for bid in bid_list
        ):
            continue

        # Guard: if any paragraph in this cell carries a publisher-specific
        # table style (TB, TCH1, …) the corpus uses a publisher tag family.
        # Promoting co-resident T-family paragraphs to TBL-* would produce
        # semantically wrong tags (observed pattern: TB→TBL-FIRST/MID/LAST).
        if any(
            clf_by_id.get(bid, {}).get("tag") in _PUBLISHER_TABLE_STYLES
            for bid in bid_list
        ):
            continue

        # Identify the "eligible" subset: blocks with a list indicator whose
        # current tag is in the flat T family.
        eligible: list[int] = []
        for bid in bid_list:
            block = block_by_id.get(bid)
            clf = clf_by_id.get(bid)
            if block is None or clf is None:
                continue
            meta = block.get("metadata", {})
            if _has_list_indicator(meta) and clf.get("tag") in _FLAT_T_FAMILY:
                eligible.append(bid)

        if len(eligible) < 2:
            continue  # Not enough eligible paragraphs to form FIRST…LAST pair

        paragraphs_relabeled += _relabel_positional_run(eligible, clf_by_id, key_for_log=key)

        cells_normalized += 1

    # -------------------------------------------------------------------
    # Second pass: some publisher tables encode bullet lists as one paragraph
    # per row (same column) rather than multi-paragraph cells. Normalize
    # contiguous list runs down the same table column.
    # -------------------------------------------------------------------
    column_groups: dict[tuple, list[int]] = defaultdict(list)
    for block_id, block in block_by_id.items():
        meta = block.get("metadata", {})
        if meta.get("context_zone") != "TABLE":
            continue
        key = (
            meta.get("table_index", -1),
            meta.get("cell_index", -1),
        )
        column_groups[key].append(block_id)

    for key in column_groups:
        column_groups[key].sort(
            key=lambda bid: (
                block_by_id[bid].get("metadata", {}).get("row_index", 0),
                block_by_id[bid].get("metadata", {}).get("para_in_cell", 0),
            )
        )

    for key, bid_list in column_groups.items():
        # Guard: if ANY paragraph in this column carries a publisher-specific
        # table style the entire column is assumed to use publisher semantics.
        # Promoting T-family tags elsewhere in the column would produce wrong
        # TBL-* tags instead of the expected TB etc. (observed: TB→TBL-*).
        if any(
            clf_by_id.get(bid, {}).get("tag") in _PUBLISHER_TABLE_STYLES
            for bid in bid_list
        ):
            continue

        run: list[int] = []
        any_run_in_group = False
        for bid in bid_list:
            block = block_by_id.get(bid)
            clf = clf_by_id.get(bid)
            if block is None or clf is None:
                if run:
                    paragraphs_relabeled += _relabel_positional_run(run, clf_by_id, key_for_log=("col", key))
                    any_run_in_group = any_run_in_group or len(run) >= 2
                    run = []
                continue

            meta = block.get("metadata", {})
            tag = clf.get("tag")
            eligible = _has_list_indicator(meta) and tag in _FLAT_T_FAMILY

            if eligible:
                run.append(bid)
            else:
                if run:
                    paragraphs_relabeled += _relabel_positional_run(run, clf_by_id, key_for_log=("col", key))
                    any_run_in_group = any_run_in_group or len(run) >= 2
                    run = []
        if run:
            paragraphs_relabeled += _relabel_positional_run(run, clf_by_id, key_for_log=("col", key))
            any_run_in_group = any_run_in_group or len(run) >= 2
        if any_run_in_group:
            cells_normalized += 1

    if cells_normalized > 0:
        logger.info(
            "TABLE_CELL_POSITIONS cells_normalized=%d paragraphs_relabeled=%d",
            cells_normalized,
            paragraphs_relabeled,
        )

    return classifications
