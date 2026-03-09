"""
Region-aware box style normalization.

When a paragraph sits inside a box region (``in_box_region=True``), any
NBX-* or NBX1-* style is deterministically remapped to its BX1-* equivalent,
provided the target style exists in the project's allowed style set.

This pass runs AFTER classification / validation / marker-overrides and
BEFORE final DOCX reconstruction so that the written styles are always
from the BX1 family inside box regions.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence

from app.services.allowed_styles import load_allowed_styles

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Explicit overrides that do NOT follow the simple prefix swap.
# ---------------------------------------------------------------------------
_EXPLICIT_MAP: dict[str, str] = {
    # Requirement: NBX-TXT → BX1-TXT-FLUSH (not BX1-TXT)
    "NBX-TXT": "BX1-TXT-FLUSH",
    # NBX-H4 has no BX1-H4; clamp to BX1-H3
    "NBX-H4": "BX1-H3",
}

# Prefixes we rewrite, longest first so NBX1- is tried before NBX-.
_SRC_PREFIXES = ("NBX1-", "NBX-")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_bx1_set(allowed: Iterable[str] | None = None) -> set[str]:
    """Return the set of BX1-* styles present in *allowed*."""
    styles = allowed if allowed is not None else load_allowed_styles()
    return {s for s in styles if s.startswith("BX1-") or s.startswith("BX1_")}


def _map_nbx_to_bx1(
    tag: str,
    bx1_styles: set[str],
) -> str | None:
    """Return the BX1 equivalent of *tag*, or *None* if none exists.

    Resolution order:
    1. Explicit override table (_EXPLICIT_MAP).
    2. Generic prefix swap  NBX{1}-{suffix} → BX1-{suffix}.
    3. Return *None* (no valid mapping).
    """
    upper = tag.upper()

    # 1. Explicit table (case-insensitive key lookup)
    for src, dst in _EXPLICIT_MAP.items():
        if upper == src.upper():
            return dst if dst in bx1_styles else None

    # 2. Generic prefix swap
    for prefix in _SRC_PREFIXES:
        if upper.startswith(prefix.upper()):
            suffix = tag[len(prefix):]          # preserve original casing
            candidate = f"BX1-{suffix}"
            if candidate in bx1_styles:
                return candidate
            # Try upper-cased suffix as fallback
            candidate_upper = f"BX1-{suffix.upper()}"
            if candidate_upper in bx1_styles:
                return candidate_upper
            return None

    return None


def is_in_box_region(meta: dict) -> bool:
    """True when *meta* indicates the paragraph is inside a box region."""
    zone = meta.get("context_zone", "")
    return zone.startswith("BOX_")


def stamp_in_box_region(blocks: Sequence[dict]) -> None:
    """Add ``in_box_region`` boolean to every block's metadata (in-place)."""
    for blk in blocks:
        meta = blk.setdefault("metadata", {})
        meta["in_box_region"] = is_in_box_region(meta)


def normalize_box_styles(
    blocks: Sequence[dict],
    classifications: list[dict],
    allowed_styles: Iterable[str] | None = None,
) -> list[dict]:
    """Remap NBX-*/NBX1-* → BX1-* for paragraphs inside a box region.

    Side-effects:
        Stamps ``in_box_region`` on every block's metadata via
        :func:`stamp_in_box_region`.

    Returns a new classification list (shallow-copied dicts for changed
    entries; originals for unchanged ones).
    """
    stamp_in_box_region(blocks)

    bx1_styles = _build_bx1_set(allowed_styles)
    if not bx1_styles:
        # Nothing to remap into – bail out.
        return list(classifications)

    block_lookup = {b["id"]: b for b in blocks}
    result: list[dict] = []

    for clf in classifications:
        para_id = clf.get("id")
        block = block_lookup.get(para_id, {})
        meta = block.get("metadata", {})

        if not meta.get("in_box_region"):
            result.append(clf)
            continue

        tag = clf.get("tag", "")
        # Only remap NBX* prefixed styles.
        tag_upper = tag.upper()
        if not (tag_upper.startswith("NBX-") or tag_upper.startswith("NBX1-")):
            result.append(clf)
            continue

        mapped = _map_nbx_to_bx1(tag, bx1_styles)
        if mapped is None or mapped == tag:
            result.append(clf)
            continue

        new_clf = {
            **clf,
            "tag": mapped,
            "repaired": True,
            "repair_reason": (
                (clf.get("repair_reason") or "") + ",box-region-normalize"
            ).lstrip(","),
        }
        logger.debug(
            "box-region-normalize: para %s  %s -> %s",
            para_id,
            tag,
            mapped,
        )
        result.append(new_clf)

    return result
