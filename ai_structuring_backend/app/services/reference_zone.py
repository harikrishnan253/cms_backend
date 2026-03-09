"""
Reference zone detection - Grounded and conservative approach.

This module detects reference/bibliography sections using:
1. Explicit heading match (primary, highly reliable)
2. Conservative pattern matching (secondary, strict criteria)
3. Ground truth learning (future enhancement)

False positives are minimized to avoid tagging normal lists as references.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path


logger = logging.getLogger(__name__)

# Pattern to strip XML-like tags from text (e.g., <H1>, <REF>, </KP-BX>)
_XML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_-]*>")


def _strip_tags(text: str) -> str:
    """Strip XML-like formatting tags from text for heading matching."""
    return _XML_TAG_RE.sub("", text).strip()


# Explicit heading matches (case-insensitive)
HEADING_MATCHES = {
    "references",
    "bibliography",
    "annotated bibliography",
    "suggested readings",
    "suggested reading",
    "further reading",
    "works cited",
    "literature cited",
    "cited references",
}

# Secondary headings that suggest reference zone (must be near end of document)
SECONDARY_HEADINGS = {
    "sources",
    "citations",
    "endnotes",
}

# Strict citation patterns - must match actual reference formatting
CITATION_START_PATTERNS = [
    re.compile(r"^\s*\[\s*\d+\s*\]\s*[A-Z]"),  # [1] Smith
    re.compile(r"^\s*\d+\.\s+[A-Z][a-z]+,?\s+[A-Z]"),  # 1. Smith, J.
    re.compile(r"^\s*[A-Z][a-z]+,\s+[A-Z]\.\s*\(?\d{4}\)?"),  # Smith, J. (2020)
    re.compile(r"^\s*[A-Z][a-z]+\s+et\s+al\.?\s*\(?\d{4}\)?"),  # Smith et al. (2020)
]

# Reference content patterns (must have multiple to count as citation)
REFERENCE_FEATURES = [
    (re.compile(r"\bet\s+al\.?\b"), "has_et_al"),
    (re.compile(r"\b(19|20)\d{2}\b"), "has_year"),
    (re.compile(r"\bdoi[:\s./]", re.IGNORECASE), "has_doi"),
    (re.compile(r"\b(journal|proceedings|conference|press|vol\.|volume)\b", re.IGNORECASE), "has_publication"),
    (re.compile(r"[,.;:]{2,}"), "has_citation_punctuation"),  # Multiple punctuation marks
    (re.compile(r"https?://"), "has_url"),  # URLs common in modern citations
]

# Patterns for detecting zone exit (non-reference structural elements)
# Opening tags for headings, boxes, tables signal a new section
_ZONE_EXIT_TAG_RE = re.compile(
    r"<(?!/)(H[1-6]|BX|NBX|TAB)",
    re.IGNORECASE,
)
# Reference-related tags should NOT trigger zone exit
_REF_ZONE_TAG_RE = re.compile(r"<(?!/)(REF|SR|BIBLIO)", re.IGNORECASE)


def _looks_like_citation(text: str, strict: bool = True) -> bool:
    """
    Check if text looks like a reference citation.

    Args:
        text: Paragraph text
        strict: If True, require stricter matching (fewer false positives)

    Returns:
        True if text matches citation patterns
    """
    t = text.strip()
    if not t or len(t) < 20:  # Citations are typically longer
        return False

    # Check for citation start patterns
    has_citation_start = any(pat.search(t) for pat in CITATION_START_PATTERNS)

    # Count reference features present
    feature_count = sum(1 for pat, _ in REFERENCE_FEATURES if pat.search(t))

    if strict:
        # Strict: Must have citation start AND at least 2 reference features
        return has_citation_start and feature_count >= 2
    else:
        # Relaxed: Either citation start OR 3+ reference features
        return has_citation_start or feature_count >= 3


def _is_numbered_list_not_reference(text: str) -> bool:
    """
    Check if text is likely a numbered list item, NOT a reference.

    This helps avoid false positives where normal lists are tagged as references.
    """
    t = text.strip()
    if not t:
        return False

    # Short numbered items without reference features
    if len(t) < 50 and re.match(r"^\d+\.\s+", t):
        # Check if it lacks typical reference features
        has_year = bool(re.search(r"\b(19|20)\d{2}\b", t))
        has_et_al = bool(re.search(r"\bet\s+al\.?\b", t))
        has_doi = "doi" in t.lower()
        has_journal = bool(re.search(r"\b(journal|vol\.|volume|press)\b", t, re.IGNORECASE))

        # If it's short and lacks reference features, it's probably not a reference
        if not (has_year or has_et_al or has_doi or has_journal):
            return True

    return False


def _is_heading_start(text: str) -> bool:
    """Check if text is a reference section heading (primary trigger)."""
    cleaned = _strip_tags(text).lower()
    if cleaned in HEADING_MATCHES:
        return True

    # Allow compact heading variants like "Chapter References" or
    # "Annotated Bibliography and Suggested Reading", but avoid long prose lines.
    if len(cleaned) > 80:
        return False
    if re.search(r"[.!?;:]\s*$", cleaned):
        return False
    return any(token in cleaned for token in HEADING_MATCHES)


def _is_secondary_heading(text: str) -> bool:
    """Check if text is a secondary reference heading (requires additional validation)."""
    cleaned = _strip_tags(text).lower()
    return cleaned in SECONDARY_HEADINGS


def _signals_zone_exit(text: str) -> bool:
    """Check if text contains structural tags that signal the end of a reference zone.

    Detects opening XML tags for headings (H1-H6), boxes (BX, NBX), and
    tables (TAB) that are NOT reference-related (REF, SR, BIBLIO).
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Has a non-reference structural opening tag
    if _ZONE_EXIT_TAG_RE.search(stripped) and not _REF_ZONE_TAG_RE.search(stripped):
        return True
    return False


def _has_any_reference_feature(text: str) -> bool:
    """Check if text has at least one reference-like feature.

    Much more lenient than ``_looks_like_citation`` — returns True if the
    text contains *any* single indicator (year, URL, DOI, "et al.", journal
    keyword, etc.).  Used for strong-trigger zone-end detection where we
    want to keep institutional-author citations in the zone.
    """
    stripped = text.strip()
    if not stripped or len(stripped) < 15:
        return False
    return any(pat.search(stripped) for pat, _ in REFERENCE_FEATURES)


def _find_zone_end(blocks: list[dict], start_idx: int, strong_trigger: bool = False) -> int:
    """Find where the reference zone ends after *start_idx*.

    Returns the index of the first block NOT in the reference zone.
    If references extend to end of document, returns ``len(blocks)``.

    Args:
        blocks: Document blocks.
        start_idx: Index where the reference zone starts.
        strong_trigger: If True, the zone was triggered by a reliable heading
            match (e.g. "Bibliography", "References").  Uses a lenient
            feature check (any single reference feature like a year or URL)
            instead of the strict citation-pattern check, and a higher
            streak threshold (15 vs 12).

    Signals:
    1. Structural tag detection — opening ``<H*>``, ``<BX*>``, ``<NBX*>``,
       ``<TAB*>`` tags that are not reference-related.
    2. Sustained non-reference content — consecutive substantive blocks
       lacking reference features (threshold depends on trigger strength).
    """
    total = len(blocks)
    seen_citations = 0
    non_citation_streak = 0
    streak_threshold = 15 if strong_trigger else 12

    for idx in range(start_idx + 1, total):
        text = blocks[idx].get("text", "")
        stripped = text.strip()

        # Primary signal: structural break via XML tags
        if _signals_zone_exit(stripped):
            logger.info(
                "Reference zone end: structural tag at index %d: '%s'",
                idx, stripped[:80],
            )
            return idx

        # Skip empty / very short blocks
        if not stripped or len(stripped) < 10:
            continue

        # For strong triggers, use lenient feature check;
        # for weak triggers, use full citation-pattern check
        if strong_trigger:
            is_ref_like = _has_any_reference_feature(stripped)
        else:
            is_ref_like = _looks_like_citation(stripped, strict=False)

        if is_ref_like:
            seen_citations += 1
            non_citation_streak = 0
        else:
            non_citation_streak += 1

        # After seeing real citations/ref content, a sustained streak of
        # non-reference blocks ends the zone
        if seen_citations >= 3 and non_citation_streak >= streak_threshold:
            end = idx - non_citation_streak + 1
            logger.info(
                "Reference zone end: non-citation streak at index %d",
                end,
            )
            return end

    return total  # References extend to end of document


def detect_reference_zone(blocks: list[dict]) -> tuple[set[int], str, int | None]:
    """
    Detect reference/bibliography zone in document (grounded & conservative).

    Strategy:
    1. Primary: Look for explicit heading ("References", "Bibliography")
    2. Secondary: Conservative pattern matching (strict criteria, late in document)
    3. Avoid false positives: Check for numbered lists that aren't references

    Args:
        blocks: List of text blocks with id and text

    Returns:
        Tuple of (ref_ids, trigger_reason, start_idx)
        - ref_ids: Set of block IDs in reference zone
        - trigger_reason: How the zone was detected ("heading_match", "strict_patterns", "none")
        - start_idx: Index where reference zone starts (or None)
    """
    ref_ids = set()
    trigger_reason = "none"
    start_idx = None
    total = len(blocks)

    # STRATEGY 1: Explicit heading match (highly reliable)
    for idx, b in enumerate(blocks):
        text = b.get("text", "")
        if _is_heading_start(text):
            start_idx = idx
            trigger_reason = "heading_match"
            logger.info(f"Reference zone triggered by heading at index {idx}: '{text.strip()}'")
            break

    # STRATEGY 2: Secondary heading + validation (near end of document)
    if start_idx is None and total > 0:
        min_start = int(total * 0.75)  # Only look in last 25% of document

        for idx in range(min_start, total):
            text = blocks[idx].get("text", "")

            if _is_secondary_heading(text):
                # Found secondary heading, validate next few blocks
                next_blocks = blocks[idx + 1:min(idx + 6, total)]
                citation_count = sum(
                    1 for b in next_blocks
                    if _looks_like_citation(b.get("text", ""), strict=True)
                )

                if citation_count >= 3:  # At least 3 of next 5 blocks look like citations
                    start_idx = idx
                    trigger_reason = "secondary_heading_validated"
                    logger.info(f"Reference zone triggered by secondary heading at index {idx}: '{text.strip()}'")
                    break

    # STRATEGY 3: Strict pattern matching (very conservative, only as last resort)
    # DISABLED by default to avoid false positives
    # Only enable if you have very clean, consistent reference formatting
    ENABLE_PATTERN_FALLBACK = False  # Set to True to enable aggressive detection

    if start_idx is None and ENABLE_PATTERN_FALLBACK and total > 0:
        window_size = 20
        min_start = int(total * 0.80)  # Only look in last 20% of document

        for center in range(min_start, total):
            start = max(0, center - (window_size // 2))
            end = min(total, start + window_size)
            window = blocks[start:end]

            # Count strict citation matches
            citation_matches = [
                w for w in window
                if _looks_like_citation(w.get("text", ""), strict=True)
            ]

            # Count false positive indicators (numbered lists that aren't references)
            false_positives = [
                w for w in window
                if _is_numbered_list_not_reference(w.get("text", ""))
            ]

            # Require very high density: 80% of window must be citations
            # AND no false positive indicators
            if len(citation_matches) >= int(window_size * 0.8) and len(false_positives) == 0:
                start_idx = start
                trigger_reason = "strict_patterns"
                logger.info(f"Reference zone triggered by strict patterns at index {start}")
                break

    # Find zone end and mark blocks in [start_idx, end_idx) as reference zone
    end_idx = None
    if start_idx is not None:
        strong = trigger_reason == "heading_match"
        end_idx = _find_zone_end(blocks, start_idx, strong_trigger=strong)
        for b in blocks[start_idx:end_idx]:
            ref_ids.add(b.get("id"))

    logger.info(
        "Reference zone detection: %s blocks (trigger=%s, start_idx=%s, end_idx=%s/%s)",
        len(ref_ids),
        trigger_reason,
        start_idx,
        end_idx,
        total,
    )
    return ref_ids, trigger_reason, start_idx
