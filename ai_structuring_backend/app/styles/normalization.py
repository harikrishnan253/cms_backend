"""Deterministic style normalization for post-classification canonicalization."""

from __future__ import annotations

import re

from .allowed_styles import get_allowed_styles, get_style_alias_map

NBSP = "\u00A0"
SEP_REPEAT_RE = re.compile(r"[-_]{2,}")


def _styles_are_case_insensitive(doc_type: str | None = None) -> bool:
    """
    Detect whether style vocabulary is case-insensitive.

    If two different allowed styles collapse to the same lowercase value,
    styles are treated as case-sensitive.
    """
    allowed = get_allowed_styles(document_type=doc_type)
    lowered: dict[str, str] = {}
    for style in allowed:
        key = style.lower()
        existing = lowered.get(key)
        if existing is not None and existing != style:
            return False
        lowered[key] = style
    return True


def normalize_style(style: str, doc_type: str | None = None) -> str:
    """
    Normalize a predicted style into canonical form when possible.

    Order:
    1) trim/whitespace cleanup
    2) collapse repeated '-' / '_' separators
    3) optional case normalization (only if style set is case-insensitive)
    4) alias map canonicalization

    Returns normalized value; membership is validated downstream.
    """
    if style is None:
        return ""

    text = str(style).replace(NBSP, " ").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""

    text = SEP_REPEAT_RE.sub("-", text)

    if _styles_are_case_insensitive(doc_type):
        text = text.upper()

    aliases = get_style_alias_map(document_type=doc_type)

    # Exact alias first.
    mapped = aliases.get(text)
    if mapped:
        return mapped

    # Separator-normalized alias fallback.
    dashed = text.replace("_", "-")
    if dashed != text:
        mapped = aliases.get(dashed)
        if mapped:
            return mapped

    underscored = text.replace("-", "_")
    if underscored != text:
        mapped = aliases.get(underscored)
        if mapped:
            return mapped

    return text

