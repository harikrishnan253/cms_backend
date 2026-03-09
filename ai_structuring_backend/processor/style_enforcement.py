"""
Final style enforcement gate before DOCX reconstruction.

This module ensures 100% compliance with allowed_styles.json by providing
a final safety check after all classification and repair passes. Any style
not in allowed_styles gets mapped to a zone-safe fallback.

This is the last line of defense before writing the output DOCX.
"""

from __future__ import annotations

import logging
from typing import Sequence

from app.services.style_normalizer import normalize_style
from .validator import _find_closest_style, SEMANTIC_FALLBACK_CHAINS
from .zone_styles import get_allowed_styles_for_zone

logger = logging.getLogger(__name__)


def enforce_style_compliance(
    classifications: list[dict],
    blocks: Sequence[dict],
    allowed_styles: set[str] | list[str],
) -> list[dict]:
    """
    Final enforcement pass. Ensures every classification uses a valid style.

    This is the last line of defense before reconstruction. Any style not in
    allowed_styles gets mapped to a zone-safe fallback using:
    1. Canonicalization via normalize_style()
    2. Semantic fallback via _find_closest_style()
    3. Zone-safe ultimate fallback (TXT for most, T for TABLE, PMI for METADATA)

    Args:
        classifications: List of classification dicts with id, tag, confidence
        blocks: List of paragraph blocks with metadata (for zone lookup)
        allowed_styles: Set or list of globally allowed style tags

    Returns:
        List of classifications with all styles guaranteed valid.
        Any invalid style is repaired with "repaired": True and
        "repair_reason" includes "final-enforcement".

    Example:
        >>> clfs = [{"id": "p1", "tag": "FAKE-TAG", "confidence": 90}]
        >>> blocks = [{"id": "p1", "text": "...", "metadata": {"context_zone": "BODY"}}]
        >>> allowed = {"TXT", "H1", "PMI"}
        >>> result = enforce_style_compliance(clfs, blocks, allowed)
        >>> result[0]["tag"]
        'TXT'  # Unknown style repaired to TXT
        >>> result[0]["repaired"]
        True
    """
    # Convert to set for O(1) membership checking
    if not isinstance(allowed_styles, set):
        allowed_styles = set(allowed_styles)

    # Build block lookup for zone access
    block_lookup = {b["id"]: b for b in blocks}

    # Metrics tracking
    metrics = {
        "enforced": 0,        # Total repairs made
        "unknown_styles": 0,  # Styles not in allowed_styles
    }

    result = []
    for clf in classifications:
        para_id = clf.get("id")
        tag = clf.get("tag", "TXT")
        block = block_lookup.get(para_id, {})
        meta = block.get("metadata", {})
        zone = meta.get("context_zone", "BODY")

        # Canonicalize tag
        canonical_tag = normalize_style(tag, meta=meta)

        # Check if tag is in allowed_styles
        if canonical_tag in allowed_styles:
            # Valid style, no repair needed
            result.append(clf)
            continue

        # Invalid style detected
        metrics["unknown_styles"] += 1

        # Try semantic fallback
        closest = _find_closest_style(canonical_tag, allowed_styles)

        if closest:
            # Found a semantically similar valid style
            repaired_tag = closest
        else:
            # No semantic match, use zone-safe fallback
            if zone == "TABLE":
                repaired_tag = "T" if "T" in allowed_styles else "PMI"
            elif zone == "METADATA":
                repaired_tag = "PMI"
            else:
                # Default: TXT for most zones
                repaired_tag = "TXT" if "TXT" in allowed_styles else "PMI"

        # Apply repair
        repaired_clf = {
            **clf,
            "tag": repaired_tag,
            "repaired": True,
        }

        # Append to repair_reason
        existing_reason = clf.get("repair_reason", "")
        new_reason = f"{existing_reason},final-enforcement" if existing_reason else "final-enforcement"
        repaired_clf["repair_reason"] = new_reason

        metrics["enforced"] += 1
        result.append(repaired_clf)

    # Emit final enforcement metrics
    logger.info(
        "STYLE_ENFORCEMENT enforced=%d unknown_styles=%d",
        metrics["enforced"],
        metrics["unknown_styles"],
    )

    return result
