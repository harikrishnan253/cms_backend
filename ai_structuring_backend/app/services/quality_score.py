"""
Production quality scoring for classified documents.
"""

from __future__ import annotations

import json
import sys
from typing import Iterable

from .style_normalizer import normalize_style


FIG_TAGS = {
    "FIG-LEG",
    "FIG-CRED",
    "FIG-SRC",
    "UNFIG-LEG",
    "UNFIG-SRC",
}


def _is_heading(tag: str) -> bool:
    return tag in {"H1", "H2", "H3"}


def _is_table_tag(tag: str) -> bool:
    return tag.startswith(("T", "UNT", "UNBX-T", "TBL", "TNL", "TUL"))


def _window_has_tag(tags: list[str], idx: int, window: int, predicate) -> bool:
    start = max(0, idx - window)
    end = min(len(tags), idx + window + 1)
    for j in range(start, end):
        if j == idx:
            continue
        if predicate(tags[j]):
            return True
    return False


def score_document(
    blocks: list[dict],
    allowed_styles: Iterable[str],
) -> tuple[int, dict, str]:
    """
    Score a document and return (score, metrics, action).
    Blocks must include: tag, confidence, metadata, text.
    """
    allowed = {normalize_style(s) for s in allowed_styles if normalize_style(s)}

    total = len(blocks)
    if total == 0:
        return 0, {
            "total": 0,
            "txt_ratio": 1.0,
            "low_conf_ratio": 1.0,
            "unknown_style_count": 0,
            "unknown_style_counts": {},
            "unknown_style_examples": [],
            "heading_violations": 0,
            "box_integrity_violations": 0,
            "figure_integrity_violations": 0,
            "table_integrity_violations": 0,
        }, "REVIEW"

    tags = [normalize_style(b.get("tag", "")) for b in blocks]
    confidences = [float(b.get("confidence", 0)) for b in blocks]

    txt_count = sum(1 for t in tags if t == "TXT")
    low_conf_count = sum(1 for c in confidences if c < 0.60)
    unknown_style_count = sum(1 for t in tags if t and t not in allowed)
    top_unknown_counts: dict[str, int] = {}
    unknown_examples: list[dict] = []

    if unknown_style_count > 0:
        normalized_allowed = sorted({str(s or "").strip() for s in allowed_styles if str(s or "").strip()})
        allowed_set_stripped = set(normalized_allowed)
        unknown_counts: dict[str, int] = {}

        for block in blocks:
            style_raw = block.get("style") or block.get("tag") or block.get("predicted_style") or ""
            style_raw = str(style_raw)
            style_norm = style_raw.strip()
            if style_norm and style_norm not in allowed_set_stripped:
                unknown_counts[style_norm] = unknown_counts.get(style_norm, 0) + 1
                if len(unknown_examples) < 30:
                    unknown_examples.append(
                        {
                            "id": block.get("id"),
                            "style_raw": style_raw,
                            "style_norm": style_norm,
                            "text": str(block.get("text") or "")[:80],
                        }
                    )

        top_unknown_counts = dict(sorted(unknown_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:50])
        payload = {
            "allowed_count": len(normalized_allowed),
            "allowed_styles_sample": normalized_allowed[:50],
            "total_blocks": len(blocks),
            "unknown_count": sum(unknown_counts.values()),
            "unknown_counts": top_unknown_counts,
            "unknown_examples": unknown_examples,
        }
        sys.stdout.write("QUALITY_UNKNOWN_STYLES " + json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    # Heading violations
    seen_h1 = False
    seen_h2 = False
    heading_violations = 0
    for t in tags:
        if t == "H1":
            seen_h1 = True
            seen_h2 = False
        elif t == "H2":
            if not seen_h1:
                heading_violations += 1
            seen_h2 = True
        elif t == "H3":
            if not seen_h2:
                heading_violations += 1

    # Box integrity violations
    box_integrity_violations = 0
    in_box = False
    seen_type = False
    seen_ttl = False
    merged_type_ttl = False
    current_box_zone = None

    def _close_box():
        nonlocal box_integrity_violations, seen_type, seen_ttl, merged_type_ttl
        if in_box:
            if not seen_type or not seen_ttl:
                box_integrity_violations += 1
            if merged_type_ttl:
                box_integrity_violations += 1
        seen_type = False
        seen_ttl = False
        merged_type_ttl = False

    for idx, b in enumerate(blocks):
        meta = b.get("metadata", {})
        zone = meta.get("context_zone", "")
        box_marker = meta.get("box_marker")
        tag = tags[idx]

        if box_marker == "start" or (zone.startswith("BOX_") and not in_box):
            _close_box()
            in_box = True
            current_box_zone = zone if zone.startswith("BOX_") else current_box_zone

        if in_box and not zone.startswith("BOX_") and box_marker != "start":
            _close_box()
            in_box = False
            current_box_zone = None

        if in_box:
            if tag.endswith("-TYPE"):
                seen_type = True
            if tag.endswith("-TTL"):
                seen_ttl = True
            if meta.get("box_label") and meta.get("box_title") and tag.endswith("-TTL"):
                merged_type_ttl = True

        if box_marker == "end":
            _close_box()
            in_box = False
            current_box_zone = None

    if in_box:
        _close_box()

    # Figure integrity violations (orphan within window)
    figure_integrity_violations = 0
    for i, t in enumerate(tags):
        if t in FIG_TAGS:
            has_peer = _window_has_tag(tags, i, 3, lambda x: x in FIG_TAGS)
            if not has_peer:
                figure_integrity_violations += 1

    # Table integrity violations (TFN orphan within window)
    table_integrity_violations = 0
    for i, t in enumerate(tags):
        if t.startswith("TFN"):
            has_table = _window_has_tag(tags, i, 3, _is_table_tag)
            if not has_table:
                table_integrity_violations += 1

    txt_ratio = txt_count / total
    low_conf_ratio = low_conf_count / total

    score = 100
    score -= txt_ratio * 60
    score -= low_conf_ratio * 20
    score -= heading_violations * 5
    score -= box_integrity_violations * 8
    score -= figure_integrity_violations * 6
    score -= table_integrity_violations * 6
    score = max(0, min(100, int(round(score))))

    if unknown_style_count > 0:
        penalty = min(30, int(100 * unknown_style_count / max(1, total)))
        score = max(0, score - penalty)

    if score >= 85:
        action = "PASS"
    elif score >= 70:
        action = "RETRY"
    else:
        action = "REVIEW"
    if unknown_style_count > 0:
        action = "REVIEW"

    metrics = {
        "total": total,
        "txt_ratio": round(txt_ratio, 4),
        "low_conf_ratio": round(low_conf_ratio, 4),
        "unknown_style_count": unknown_style_count,
        "unknown_style_counts": top_unknown_counts,
        "unknown_style_examples": unknown_examples,
        "heading_violations": heading_violations,
        "box_integrity_violations": box_integrity_violations,
        "figure_integrity_violations": figure_integrity_violations,
        "table_integrity_violations": table_integrity_violations,
    }

    return score, metrics, action
