"""
Block extraction for DOCX documents.
Builds block-level records with structural features for lists, tables, captions, and boxes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .ingestion import extract_document, BOX_TYPE_MAPPING, BOX_START_PATTERNS, BOX_END_PATTERNS


FIGURE_CAPTION_PATTERNS = [
    r"^figure\s*\d",
    r"^fig\.\s*\d",
    r"^<fn>",
    r"^<ft>",
]

TABLE_CAPTION_PATTERNS = [
    r"^table\s*\d",
    r"^tab\.\s*\d",
    r"^<tab",
    r"^<tn>",
    r"^<tt>",
]

SOURCE_LINE_PATTERNS = [
    r"^source:",
    r"^adapted from",
    r"^reproduced from",
    r"^data from",
    r"^courtesy of",
    r"^<cl>",
]

BOX_TITLE_PATTERNS = [
    r"^<bt>",
    r"^<bn>",
    r"^box\s*\d",
]


def _is_box_marker(text: str) -> Optional[str]:
    text_lower = text.lower().strip()
    for pattern in BOX_START_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return "start"
    for pattern in BOX_END_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return "end"
    return None


def _detect_caption_type(text: str) -> Optional[str]:
    text_lower = text.lower().strip()
    for pattern in FIGURE_CAPTION_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return "figure"
    for pattern in TABLE_CAPTION_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return "table"
    return None


def _detect_source_line(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(re.match(p, text_lower, re.IGNORECASE) for p in SOURCE_LINE_PATTERNS)


def _detect_box_label(text: str) -> Optional[str]:
    text_lower = text.lower().strip()
    for box_type in BOX_TYPE_MAPPING.keys():
        if text_lower == box_type:
            return box_type
    return None


def _detect_box_title(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(re.match(p, text_lower, re.IGNORECASE) for p in BOX_TITLE_PATTERNS)


def _is_list_item(metadata: dict, text: str) -> bool:
    if metadata.get("has_bullet") or metadata.get("has_numbering") or metadata.get("has_xml_list"):
        return True
    # Mnemonic / lettered list heuristic: single capital letter + tab/space + text
    if re.match(r"^[A-Z]\s+.+", text.strip()):
        return True
    # Style-name fallback: defence-in-depth for style-only lists whose
    # has_bullet/has_numbering flags were not set by ingestion (e.g. an edge
    # case where the style_name inference in ingestion was not reached).
    _sn = metadata.get("style_name", "").lower()
    if _sn and ("bullet" in _sn or "number" in _sn):
        return True
    return False


def _list_kind(metadata: dict, text: str) -> Optional[str]:
    if metadata.get("has_bullet"):
        return "bullet"
    if metadata.get("has_numbering"):
        return "numbered"
    if metadata.get("has_xml_list"):
        # Ambiguous XML list; treat as unordered
        return "unordered"
    if re.match(r"^[A-Z]\s+.+", text.strip()):
        return "unordered"
    # Style-name fallback (mirrors the _is_list_item fallback above)
    _sn = metadata.get("style_name", "").lower()
    if _sn:
        if "bullet" in _sn:
            return "bullet"
        if "number" in _sn:
            return "numbered"
    return None


def _compute_list_positions(paragraphs: list[dict]) -> dict[int, dict]:
    """Determine list positions (FIRST/MID/LAST) for list items.

    Key design choice
    -----------------
    For paragraphs that carry Word XML numbering (``xml_num_id`` set), the
    grouping key is ``(xml_num_id, xml_list_level, context_zone)``.  All
    paragraphs that share the same ``numId`` belong to the same logical list
    (per the OOXML spec), so outer-level items that "resume" after a sublist
    are correctly recognised as part of the same sequence.

    For style-based list items (no ``xml_num_id``), the legacy key
    ``(kind, indent_level, context_zone, …)`` is retained — these items are
    grouped by consecutive runs at the same apparent level, which is the best
    we can do without XML proof of list identity.

    Nested sublists (different ``xml_list_level`` within the same ``numId``)
    are assigned positions independently at each level.
    """
    positions: dict[int, dict] = {}

    # -----------------------------------------------------------------------
    # Phase 1: collect per-numId, per-level runs from XML-numbered paragraphs.
    # We walk in document order and group by (num_id, level, zone).
    # -----------------------------------------------------------------------
    # Bucket: (num_id, level, zone) -> list of (doc_index, para_id, kind)
    from collections import defaultdict
    xml_buckets: dict[tuple, list[tuple[int, int, str | None]]] = defaultdict(list)

    # Track which para_ids are handled via XML path so we skip them in Phase 2.
    xml_handled: set[int] = set()

    for idx, para in enumerate(paragraphs):
        meta = para.get("metadata", {})
        num_id = meta.get("xml_num_id")
        xml_level = meta.get("xml_list_level")
        if num_id is None or xml_level is None:
            continue
        zone = meta.get("context_zone", "BODY")
        kind = _list_kind(meta, para["text"])
        key = (num_id, xml_level, zone)
        xml_buckets[key].append((idx, para["id"], kind))
        xml_handled.add(para["id"])

    # Assign positions within each XML bucket (already in document order
    # because we appended in idx order).
    for (num_id, xml_level, zone), entries in xml_buckets.items():
        n = len(entries)
        for rank, (doc_idx, para_id, kind) in enumerate(entries):
            if n == 1:
                pos = "FIRST"
            elif rank == 0:
                pos = "FIRST"
            elif rank == n - 1:
                pos = "LAST"
            else:
                pos = "MID"
            positions[para_id] = {
                "list_position": pos,
                "list_kind": kind,
                "list_level": xml_level,
            }

    # -----------------------------------------------------------------------
    # Phase 2: style-based list items (no xml_num_id).  Use consecutive-run
    # grouping by (kind, indent_level, zone, is_table, table_index, box_type).
    # -----------------------------------------------------------------------
    style_entries: list[tuple[int, int, tuple | None]] = []
    for idx, para in enumerate(paragraphs):
        if para["id"] in xml_handled:
            style_entries.append((idx, para["id"], None))
            continue
        text = para["text"]
        meta = para.get("metadata", {})
        if _is_list_item(meta, text):
            kind = _list_kind(meta, text)
            key = (
                kind,
                meta.get("indent_level", 0),
                meta.get("context_zone", "BODY"),
                bool(meta.get("is_table")),
                meta.get("table_index"),
                meta.get("box_type"),
            )
            style_entries.append((idx, para["id"], key))
        else:
            style_entries.append((idx, para["id"], None))

    i = 0
    while i < len(style_entries):
        idx, para_id, key = style_entries[i]
        if key is None:
            i += 1
            continue
        run = [para_id]
        j = i + 1
        while j < len(style_entries) and style_entries[j][2] == key:
            run.append(style_entries[j][1])
            j += 1

        n = len(run)
        kind_val = key[0]
        level_val = key[1]
        if n == 1:
            positions[run[0]] = {"list_position": "FIRST", "list_kind": kind_val, "list_level": level_val}
        else:
            positions[run[0]] = {"list_position": "FIRST", "list_kind": kind_val, "list_level": level_val}
            for mid_id in run[1:-1]:
                positions[mid_id] = {"list_position": "MID", "list_kind": kind_val, "list_level": level_val}
            positions[run[-1]] = {"list_position": "LAST", "list_kind": kind_val, "list_level": level_val}

        i = j

    return positions


def _enrich_list_metadata(paragraphs: list[dict], docx_path) -> list[dict]:
    """Non-destructively enrich list paragraphs with hierarchy detector metadata.

    Calls ``ListHierarchyDetector`` for each paragraph that is (or might be) a
    list item and writes ``list_style_prefix``, ``semantic_level``,
    ``indent_twips``, and ``indent_source`` when those keys are absent.

    **Never overwrites** OOXML-derived keys (``xml_list_level``, ``xml_num_id``,
    ``has_bullet``, ``has_numbering``, ``has_xml_list``).  The detector result
    is additive only — existing evidence always wins.
    """
    try:
        from .list_hierarchy_detector import ListHierarchyDetector
    except ImportError:
        return paragraphs  # graceful degradation if module not present

    detector = ListHierarchyDetector(docx_path)

    for i, para in enumerate(paragraphs):
        meta = para.get("metadata", {})
        text = para.get("text", "")

        # Only enrich candidate list paragraphs
        _sn_lower = meta.get("style_name", "").lower()
        is_candidate = (
            meta.get("has_bullet")
            or meta.get("has_numbering")
            or meta.get("has_xml_list")
            or meta.get("xml_list_level") is not None
            # Style-name fallback: catches any style-only list that ingestion
            # did not flag (defence-in-depth alongside the ingestion fix).
            or bool(_sn_lower and ("bullet" in _sn_lower or "number" in _sn_lower))
        )
        if not is_candidate:
            continue

        # Alias OOXML keys so the detector can use them (added here because the
        # detector checks 'ooxml_ilvl' not 'xml_list_level').
        detect_meta: dict = dict(meta)
        if "xml_list_level" in meta and "ooxml_ilvl" not in detect_meta:
            detect_meta["ooxml_ilvl"] = meta["xml_list_level"]
        if "xml_num_id" in meta and "ooxml_numId" not in detect_meta:
            detect_meta["ooxml_numId"] = str(meta["xml_num_id"])

        list_info = detector.detect(text, para_index=i, metadata=detect_meta)

        if list_info.is_list:
            # Write only keys not already present — preserve OOXML primacy
            if "indent_twips" not in meta and list_info.indent_twips:
                meta["indent_twips"] = list_info.indent_twips
            if "semantic_level" not in meta:
                meta["semantic_level"] = list_info.semantic_level
            if "list_style_prefix" not in meta:
                meta["list_style_prefix"] = list_info.style_prefix
            if "indent_source" not in meta:
                meta["indent_source"] = list_info.indent_source

    return paragraphs


def extract_blocks(docx_path: str | Path) -> tuple[list[dict], list[dict], dict]:
    """
    Extract blocks with structural features.
    Returns blocks, original paragraphs, and stats.
    """
    paragraphs, stats = extract_document(docx_path)
    paragraphs = _enrich_list_metadata(paragraphs, docx_path)
    list_positions = _compute_list_positions(paragraphs)

    blocks: list[dict] = []

    for para in paragraphs:
        para_id = para["id"]
        text = para["text"]
        meta = dict(para.get("metadata", {}))

        caption_type = _detect_caption_type(text)
        source_line = _detect_source_line(text)
        box_marker = _is_box_marker(text)
        box_label = _detect_box_label(text)
        box_title = _detect_box_title(text)

        list_info = list_positions.get(para_id, {})

        meta.update(
            {
                "caption_type": caption_type,
                "source_line": source_line,
                "box_marker": box_marker,
                "box_label": box_label,
                "box_title": box_title,
                "list_kind": list_info.get("list_kind"),
                "list_position": list_info.get("list_position"),
                "list_level": list_info.get("list_level"),
            }
        )

        blocks.append(
            {
                "id": para_id,
                "para_ids": [para_id],
                "text": text,
                "text_truncated": para["text_truncated"],
                "metadata": meta,
            }
        )

    return blocks, paragraphs, stats
