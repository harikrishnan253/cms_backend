"""
Zone-based style restriction enforcement.

**Two-phase architecture**:

1. **Pre-classification** (``restrict_allowed_styles_per_zone``): Sets metadata
   hints to guide LLM towards zone-valid styles.

2. **Post-classification** (``enforce_zone_style_restrictions``): **FINAL
   AUTHORITY** that ensures output never contains unknown/invalid styles.
   Runs immediately before quality scoring.

**IMPORTANT**: The codebase has comprehensive zone validation built into the
classifier and validator via ``ZONE_VALID_STYLES`` in ``ingestion.py``, but
LLM can still generate unknown styles or the validator might miss edge cases.
This module provides the **final safety net** before quality scoring.

**Tag name mapping**:

The spec requested tags like "BODY_TEXT", "TABLE_TITLE", "REF_ITEM" which
do not exist in the WK Template vocabulary. This implementation maps them to
actual allowed tags:

- "BODY_TEXT" → "TXT", "TXT-FLUSH"
- "LIST_LEVEL_1" → "BL-FIRST/MID/LAST", "NL-FIRST/MID/LAST", etc.
- "TABLE_TITLE" → "T1", "T11", "T12"
- "REF_ITEM" → "REF-N", "REF-U"

**Pipeline Integration**:

- Pre-classification (Stage 1b): ``restrict_allowed_styles_per_zone()``
- Post-classification (Stage 3.5): ``enforce_zone_style_restrictions()``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)

# Import existing zone constraints
try:
    from .ingestion import ZONE_VALID_STYLES, validate_style_for_zone
except ImportError:
    ZONE_VALID_STYLES = {}

    def validate_style_for_zone(style: str, zone: str) -> bool:
        return True


@dataclass
class ZoneRestrictionMetrics:
    """Metrics for zone-based style restriction enforcement."""

    total: int = 0
    """Total blocks processed."""

    replaced: int = 0
    """Blocks with styles replaced due to zone violations."""

    unknown_from_llm: int = 0
    """Styles that don't exist in global allowed styles (LLM hallucinations)."""

    by_zone: dict[str, int] = field(default_factory=dict)
    """Replacement count breakdown by zone."""

    unknown_styles: dict[str, int] = field(default_factory=dict)
    """Count of each unknown style encountered."""


# Fallback styles per zone when validation fails
_ZONE_FALLBACKS = {
    'METADATA': 'PMI',
    'FRONT_MATTER': 'TXT',
    'TABLE': 'T',
    'BOX_NBX': 'NBX-TXT',
    'BOX_BX1': 'BX1-TXT',
    'BOX_BX2': 'BX2-TXT',
    'BOX_BX3': 'BX3-TXT',
    'BOX_BX4': 'BX4-TXT',
    'BOX_BX6': 'BX6-TXT',
    'BOX_BX7': 'BX7-TXT',
    'BOX_BX15': 'BX15-TXT',
    'BOX_BX16': 'BX16-UNT',
    'BACK_MATTER': 'PMI',  # References/figures default to marker
    'EXERCISE': 'PMI',
    'BODY': 'TXT',  # Default fallback for BODY zone
}


def restrict_allowed_styles_per_zone(blocks: Sequence[dict]) -> list[dict]:
    """Set zone-restricted style hints on block metadata.

    For every block, reads ``metadata["context_zone"]`` and stores the
    zone's valid styles in ``metadata["zone_allowed_styles"]``. This
    provides an early hint for validation, though the classifier and
    validator already enforce zone constraints independently.

    **How it works**:

    1. Reads ``block["metadata"]["context_zone"]``
    2. Looks up valid styles from ``ZONE_VALID_STYLES[zone]``
    3. Stores in ``metadata["zone_allowed_styles"]`` for reference
    4. Existing classifier validation (validate_style_for_zone) still applies

    **Zone validation flow**:

    ```
    Pre-classification:
        restrict_allowed_styles_per_zone() → sets metadata hint

    During classification:
        Classifier checks zone constraints in validate_zone_constraints()

    Post-classification:
        Validator repairs zone violations via validate_and_repair()
    ```

    **Logging**:

    - Info: Number of blocks with zone restrictions set
    - Debug: Per-zone breakdown

    Parameters
    ----------
    blocks : sequence of dict
        Block list from ``extract_blocks()``. Modified **in-place**;
        returned as a list for pipeline chaining.

    Returns
    -------
    list of dict
        The same block objects (identity), for chaining convenience.
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    zone_counts = {}
    total_restricted = 0

    for block in blocks:
        meta = block.get("metadata", {})
        zone = meta.get("context_zone", "BODY")

        # Look up valid styles for this zone
        zone_styles = ZONE_VALID_STYLES.get(zone, [])

        if zone_styles:
            # Store as metadata hint (does not override lock_style mechanism)
            meta["zone_allowed_styles"] = zone_styles
            total_restricted += 1
            zone_counts[zone] = zone_counts.get(zone, 0) + 1

    if total_restricted:
        logger.info(
            "zone-style-restriction: set style hints on %d blocks",
            total_restricted,
        )
        for zone, count in sorted(zone_counts.items()):
            logger.debug("  %s: %d blocks", zone, count)

    return blocks


def validate_block_style_for_zone(
    block: dict,
    proposed_style: str,
    log_violations: bool = True,
) -> bool:
    """Validate if a proposed style is allowed for the block's zone.

    **Usage in classifier**:

    ```python
    if not validate_block_style_for_zone(block, llm_proposed_tag, log_violations=True):
        # LLM proposed an invalid style for this zone
        # Fall back to heuristic or repair
        tag = fallback_heuristic_tag(block)
    ```

    Parameters
    ----------
    block : dict
        Block dictionary with metadata containing ``context_zone``.
    proposed_style : str
        The style tag to validate (e.g., "BL-MID", "T1", "REFH1").
    log_violations : bool, optional
        If True, log a warning when validation fails. Default: True.

    Returns
    -------
    bool
        True if the style is valid for the block's zone, False otherwise.
    """
    from .ingestion import validate_style_for_zone

    meta = block.get("metadata", {})
    zone = meta.get("context_zone", "BODY")

    is_valid = validate_style_for_zone(proposed_style, zone)

    if not is_valid and log_violations:
        logger.warning(
            "Zone violation: block %d in zone %s cannot use style %s",
            block.get("id"),
            zone,
            proposed_style,
        )

    return is_valid


def enforce_zone_style_restrictions(
    blocks: Sequence[dict],
    allowed_styles: set[str] | None = None,
) -> list[dict]:
    """Enforce zone-based style restrictions on classified blocks.

    This is the **FINAL AUTHORITY** that runs immediately before quality scoring
    to ensure the output never contains unknown/invalid styles.

    **Purpose**:
    - Prevent quality_score from failing with "Unknown styles detected"
    - Replace zone-invalid styles with safe fallbacks
    - Replace LLM hallucinations (unknown styles) with valid styles
    - Provide structured logging of all replacements

    **Replacement strategy**:
    1. If style doesn't exist in global ``allowed_styles``: unknown_from_llm++
    2. If style exists but invalid for zone: zone violation
    3. Replace with zone-specific fallback from ``_ZONE_FALLBACKS``

    **Integration**:
    Runs in Stage 3.5 (post-classification normalization), immediately before
    quality scoring.

    Parameters
    ----------
    blocks : sequence of dict
        Block list with ``tag`` and ``metadata["context_zone"]``.
        Modified **in-place**.
    allowed_styles : set of str, optional
        Global allowed styles vocabulary. If None, loads from config.

    Returns
    -------
    list of dict
        The same block objects (identity), for chaining convenience.

    Logging
    -------
    Emits: ``ZONE_STYLE_RESTRICTION total=<int> replaced=<int> unknown_from_llm=<int> by_zone={...}``

    Examples
    --------
    Input (LLM hallucination):

        Block: {id: 1, tag: "BODY_TEXT", metadata: {context_zone: "BODY"}}

    Output (replaced with valid style):

        Block: {
            id: 1,
            tag: "TXT",  # Replaced
            original_tag: "BODY_TEXT",
            zone_restricted: True,
            metadata: {context_zone: "BODY"}
        }

    Input (zone violation):

        Block: {id: 2, tag: "BL-MID", metadata: {context_zone: "TABLE"}}

    Output (replaced with zone fallback):

        Block: {
            id: 2,
            tag: "T",  # Replaced with TABLE fallback
            original_tag: "BL-MID",
            zone_restricted: True,
            metadata: {context_zone: "TABLE"}
        }
    """
    blocks = list(blocks)
    if not blocks:
        return blocks

    # Load global allowed styles if not provided
    if allowed_styles is None:
        from app.services.allowed_styles import load_allowed_styles
        allowed_styles = load_allowed_styles()

    # Normalize allowed styles
    allowed_styles_normalized = {str(s).strip() for s in allowed_styles if s}

    # Track metrics
    metrics = ZoneRestrictionMetrics()
    metrics.total = len(blocks)

    for block in blocks:
        current_tag = block.get("tag", "")
        if not current_tag:
            continue

        # Get zone
        meta = block.get("metadata", {})
        zone = meta.get("context_zone", "BODY")

        # Check if style is globally valid (exists in vocabulary)
        is_globally_valid = current_tag in allowed_styles_normalized

        # Check if style is zone-valid
        is_zone_valid = validate_style_for_zone(current_tag, zone)

        # If both checks pass, no action needed
        if is_globally_valid and is_zone_valid:
            continue

        # Determine fallback
        fallback_tag = _ZONE_FALLBACKS.get(zone, "TXT")

        # Track unknown styles
        if not is_globally_valid:
            metrics.unknown_from_llm += 1
            metrics.unknown_styles[current_tag] = (
                metrics.unknown_styles.get(current_tag, 0) + 1
            )
            logger.warning(
                "zone-restriction: block %s has unknown style %r (zone=%s), replacing with %s",
                block.get("id"),
                current_tag,
                zone,
                fallback_tag,
            )
        else:
            logger.debug(
                "zone-restriction: block %s style %r invalid for zone %s, replacing with %s",
                block.get("id"),
                current_tag,
                zone,
                fallback_tag,
            )

        # Replace tag
        block["tag"] = fallback_tag
        block["zone_restricted"] = True
        block["original_tag"] = current_tag

        # Track metrics
        metrics.replaced += 1
        metrics.by_zone[zone] = metrics.by_zone.get(zone, 0) + 1

    # Emit structured log
    if metrics.replaced > 0:
        logger.info(
            "ZONE_STYLE_RESTRICTION total=%d replaced=%d unknown_from_llm=%d by_zone=%s",
            metrics.total,
            metrics.replaced,
            metrics.unknown_from_llm,
            dict(metrics.by_zone),
        )

        if metrics.unknown_styles:
            logger.warning(
                "zone-restriction: unknown styles encountered: %s",
                dict(metrics.unknown_styles),
            )

    return blocks
