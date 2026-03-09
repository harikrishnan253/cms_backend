"""
Diagnostics: structured STYLE_TAG_TRACE log event.

Gated by the STYLE_TRACE=1 environment variable (default off).
Emits a single JSON log record summarising tagging decisions
without altering behaviour.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from typing import Sequence

logger = logging.getLogger(__name__)

# Angle-bracket marker token pattern (e.g. <note>, </clinical pearl>, <h1>, <fn>)
_MARKER_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9 _-]*>")

# Maximum number of example text snippets kept per category bucket.
_MAX_EXAMPLES = 10
# Maximum characters kept from a paragraph's text in any snippet.
_SNIPPET_LEN = 60


def _is_enabled() -> bool:
    return os.environ.get("STYLE_TRACE", "").strip() == "1"


def _truncate(text: str) -> str:
    if len(text) <= _SNIPPET_LEN:
        return text
    return text[:_SNIPPET_LEN] + "..."


def _collect_examples(
    bucket: dict[str, list[str]],
    key: str,
    text: str,
) -> None:
    """Append a truncated snippet if the bucket has room."""
    lst = bucket.setdefault(key, [])
    if len(lst) < _MAX_EXAMPLES:
        lst.append(_truncate(text))


def emit_style_tag_trace(
    file_name: str,
    blocks: Sequence[dict],
    classifications: Sequence[dict],
) -> dict | None:
    """Build and log the STYLE_TAG_TRACE event.

    Returns the trace dict when STYLE_TRACE=1, otherwise *None*.
    The caller is responsible for nothing beyond passing the data;
    this function never mutates *blocks* or *classifications*.
    """
    if not _is_enabled():
        return None

    clf_by_id = {c["id"]: c for c in classifications}
    block_lookup = {b["id"]: b for b in blocks}

    total_blocks = len(blocks)

    # --- per-style counts ---
    style_counter: Counter[str] = Counter()
    # --- list diagnostics ---
    list_has_numbering = 0
    list_style_applied = 0
    # --- marker token counts ---
    marker_counter: Counter[str] = Counter()
    # --- zone/region counts ---
    zone_counter: Counter[str] = Counter()

    # example buckets (key -> list[str])
    style_examples: dict[str, list[str]] = {}
    list_numbering_examples: list[str] = []
    list_style_examples: list[str] = []
    marker_examples: dict[str, list[str]] = {}
    zone_examples: dict[str, list[str]] = {}

    for blk in blocks:
        bid = blk["id"]
        text = blk.get("text", "")
        meta = blk.get("metadata", {})
        clf = clf_by_id.get(bid, {})
        tag = clf.get("tag", "UNKNOWN")

        # 1. Style counts + examples
        style_counter[tag] += 1
        _collect_examples(style_examples, tag, text)

        # 2. List diagnostics
        has_numbering = bool(
            meta.get("has_numbering")
            or meta.get("has_bullet")
            or meta.get("has_xml_list")
        )
        if has_numbering:
            list_has_numbering += 1
            if len(list_numbering_examples) < _MAX_EXAMPLES:
                list_numbering_examples.append(_truncate(text))

        is_list_tag = any(
            tag.endswith(sfx)
            for sfx in ("-FIRST", "-MID", "-LAST")
        )
        if is_list_tag:
            list_style_applied += 1
            if len(list_style_examples) < _MAX_EXAMPLES:
                list_style_examples.append(_truncate(text))

        # 3. Marker tokens
        for m in _MARKER_RE.findall(text):
            token = m.lower()
            marker_counter[token] += 1
            _collect_examples(marker_examples, token, text)

        # 4. Zone / region
        zone = meta.get("context_zone", "UNKNOWN")
        zone_counter[zone] += 1
        _collect_examples(zone_examples, zone, text)

    # Assemble the trace payload
    top_styles = style_counter.most_common(30)

    trace: dict = {
        "event": "STYLE_TAG_TRACE",
        "file_name": file_name,
        "total_blocks": total_blocks,
        "style_counts": {tag: cnt for tag, cnt in top_styles},
        "style_examples": {
            tag: style_examples.get(tag, [])
            for tag, _ in top_styles
        },
        "list_detected_count": list_has_numbering,
        "list_style_applied_count": list_style_applied,
        "list_detected_examples": list_numbering_examples,
        "list_style_applied_examples": list_style_examples,
        "marker_token_counts": dict(marker_counter.most_common()),
        "marker_token_examples": {
            tok: marker_examples.get(tok, [])
            for tok in marker_counter
        },
        "zone_counts": dict(zone_counter.most_common()),
        "zone_examples": {
            z: zone_examples.get(z, [])
            for z in zone_counter
        },
    }

    logger.info("STYLE_TAG_TRACE %s", json.dumps(trace, ensure_ascii=False))
    return trace
