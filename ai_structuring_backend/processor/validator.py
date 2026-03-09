"""
Deterministic validation and repair for classified styles.
Rules:
- Heading hierarchy
- Box wrapper integrity (TYPE vs TTL)
- Figure/Table grouping
- Front-matter enforcement
"""

from __future__ import annotations

import re
import logging
from typing import Iterable

from difflib import SequenceMatcher

from .style_list import ALLOWED_STYLES
from app.services.style_normalizer import normalize_style
from .ingestion import validate_style_for_zone, BOX_TYPE_MAPPING
from app.services.reference_zone import detect_reference_zone

logger = logging.getLogger(__name__)

# Composite tag separators: tags with these characters are invalid composite tags
# that need to be split and repaired (e.g., "TBL-H2+TXT", "REF-N/PMI")
_COMPOSITE_SEPARATORS = frozenset({"+", "/", ",", "|"})


def _is_composite_tag(tag: str) -> bool:
    """Returns True if tag contains composite separators."""
    return any(sep in tag for sep in _COMPOSITE_SEPARATORS)


def _split_composite_tag(tag: str) -> list[str]:
    """Split composite tag into component parts."""
    return re.split(r'[+/,|]', tag)


# Semantic fallback chains: when a tag is not in allowed_styles,
# try these alternatives in order before falling back to TXT.
SEMANTIC_FALLBACK_CHAINS: dict[str, list[str]] = {
    # Headings: fall to lower level, then TXT
    "H6": ["H5", "H4", "H3"],
    "H5": ["H4", "H3"],
    "H4": ["H3"],
    "H3": ["H2"],
    "H2": ["H1"],
    # Flush text variants
    "TXT-FLUSH": ["TXT"],
    "TXT-FLUSH1": ["TXT-FLUSH", "TXT1", "TXT"],
    "TXT-FLUSH2": ["TXT-FLUSH", "TXT2", "TXT"],
    "TXT-FLUSH4": ["TXT-FLUSH", "TXT4", "TXT"],
    "TXT-DC": ["TXT-FLUSH", "TXT"],
    "TXT-AU": ["TXT-FLUSH", "TXT"],
    "TXT1": ["TXT"],
    "TXT2": ["TXT"],
    "TXT3": ["TXT"],
    "TXT4": ["TXT"],
    # Bullet lists: position variants
    "BL-FIRST": ["BL-MID"],
    "BL-LAST": ["BL-MID"],
    "BL2-MID": ["BL-MID"],
    "BL3-MID": ["BL2-MID", "BL-MID"],
    # Numbered lists: position variants
    "NL-FIRST": ["NL-MID"],
    "NL-LAST": ["NL-MID"],
    # Unordered lists
    "UL-FIRST": ["UL-MID", "BL-FIRST", "BL-MID"],
    "UL-LAST": ["UL-MID", "BL-LAST", "BL-MID"],
    "UL-MID": ["BL-MID"],
    # Table headings: fall through levels
    "TH6": ["TH5", "TH4", "TH3"],
    "TH5": ["TH4", "TH3"],
    "TH4": ["TH3"],
    "TH3": ["TH2", "TH1", "T"],
    "TH2": ["TH1", "T"],
    "TH1": ["T"],
    # Table lists
    "TBL-FIRST": ["TBL-MID"],
    "TBL-LAST": ["TBL-MID"],
    "TBL2-MID": ["TBL-MID"],
    "TBL3-MID": ["TBL2-MID", "TBL-MID"],
    "TBL4-MID": ["TBL3-MID", "TBL2-MID", "TBL-MID"],
    "TNL-FIRST": ["TNL-MID"],
    "TNL-LAST": ["TNL-MID"],
    # Table cell types
    "T2-C": ["T2"],
    "T21": ["T2"],
    "T22": ["T2"],
    "T23": ["T2"],
    "T3": ["T4", "T"],
    "T4": ["T3", "T"],
    "T5": ["T"],
    "T6": ["T"],
    "TD": ["T"],
    # Table footnotes
    "TFN1": ["TFN"],
    "TSN": ["TFN"],
    # Figure variants
    "FIG-SRC": ["TSN", "FIG-LEG"],
    "UNFIG-SRC": ["FIG-SRC", "TSN"],
    # Reference variants
    "REF-N0": ["REF-N"],
    "REF-U": ["REF-N"],
    "Ref-H1": ["REFH1"],
    "Ref-H2": ["REFH2"],
    # Box variants: try generic box, then body equivalent
    "NBX1-TTL": ["NBX-TTL"],
    "NBX1-TXT": ["NBX-TXT", "TXT"],
    "NBX1-TXT-FLUSH": ["NBX-TXT-FLUSH", "NBX-TXT", "TXT-FLUSH", "TXT"],
    "NBX1-BL-FIRST": ["NBX-BL-FIRST", "NBX1-BL-MID", "BL-FIRST"],
    "NBX1-BL-MID": ["NBX-BL-MID", "BL-MID"],
    "NBX1-BL-LAST": ["NBX-BL-LAST", "NBX1-BL-MID", "BL-LAST"],
    "NBX1-NL-FIRST": ["NBX-NL-FIRST", "NBX1-NL-MID", "NL-FIRST"],
    "NBX1-NL-MID": ["NBX-NL-MID", "NL-MID"],
    "NBX1-NL-LAST": ["NBX-NL-LAST", "NBX1-NL-MID", "NL-LAST"],
    # EOC variants
    "EOC-NL-FIRST": ["EOC-NL-MID"],
    "EOC-NL-LAST": ["EOC-NL-MID"],
    "EOC-LL2-MID": ["EOC-NL-MID"],
    "EOC-H1": ["H1"],
    # Appendix variants
    "APX-H1": ["H1"],
    "APX-H2": ["H2"],
    "APX-H3": ["H3"],
    "APX-TXT": ["TXT"],
    "APX-TXT-FLUSH": ["TXT-FLUSH", "TXT"],
    # Special
    "SP-H1": ["H1"],
    "SP-TTL": ["H1"],
    "SP-TXT": ["TXT"],
    "INTRO": ["TXT-FLUSH", "TXT"],
    "EXT-ONLY": ["TXT"],
    "QUO": ["TXT"],
    # Exercise variants: generic falls to subtype-specific
    "EXER-NL-FIRST": ["EXER-MC-NL-FIRST", "EXER-SP-NL-FIRST", "NL-FIRST"],
    "EXER-NL-MID": ["EXER-MC-NL-MID", "EXER-SP-NL-MID", "NL-MID"],
    "EXER-NL-LAST": ["EXER-NL-MID", "NL-LAST", "NL-MID"],
    # SKILL: specialized content tag
    "SKILL": ["TXT-FLUSH", "TXT"],
    # Vendor prefix fallbacks (bare box without subtype)
    "EFP-BX": ["TXT"],
    "EYU-BX": ["TXT"],
}

REF_NUMBER_RE = re.compile(
    r"^\s*(?:[\u2022\u25CF\-\*\u2013\u2014]\s*)?(?:\(\d+\)|\[\d+\]|\d+[\.\)]|\d+\s+)"
)
REF_BULLET_RE = re.compile(r"^\s*[\u2022\u25CF\-\*\u2013\u2014]\s+")
LEADING_XML_TAGS_RE = re.compile(r"^\s*(?:<[^>]+>\s*)+")
T4_HEADING_CASE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s/&\-]{1,59}$")
INLINE_H_TAG_RE = re.compile(r"^\s*<H([1-6])>\b", re.IGNORECASE)
MARKER_ONLY_TAG_RE = re.compile(r"^\s*<[^>]+>\s*$")
SEMANTIC_LIST_POS_RE = re.compile(
    r"^(?P<prefix>.*?)(?P<base>(?:BL|NL|UL|LL)\d*)-(?P<pos>FIRST|MID|LAST)$"
)
# Matches unsuffixed list-family tags (no FIRST/MID/LAST), e.g. ANS-UL, KT-BL, OBJ-NL.
# Used in fallback to prefer -MID deterministically over nondeterministic set iteration.
_UNSUFFIXED_LIST_FAMILY_RE = re.compile(
    r"^.+-(BL\d*|NL\d*|UL\d*|LL\d*|TBL\d*|TNL\d*|TUL\d*)$"
)

# Tags that represent generic hard fallbacks (true downgrades, not semantic repairs).
# Only these get WARNING-level logs; all other remaps get INFO-level "semantic-repair".
_HARD_FALLBACK_TAGS: frozenset[str] = frozenset({"TXT", "TXT-FLUSH", "T", "PMI"})

BOX_PREFIX_BY_ZONE = {
    "BOX_NBX": "NBX",
    "BOX_BX1": "BX1",
    "BOX_BX2": "BX2",
    "BOX_BX3": "BX3",
    "BOX_BX4": "BX4",
    "BOX_BX6": "BX6",
    "BOX_BX7": "BX7",
    "BOX_BX15": "BX15",
    "BOX_BX16": "BX16",
}


def _allowed_set(allowed: Iterable[str] | None) -> set[str]:
    source = ALLOWED_STYLES if allowed is None or not list(allowed) else allowed
    return {normalize_style(s) for s in source if normalize_style(s)}


def _is_heading(tag: str) -> bool:
    return tag in {"H1", "H2", "H3", "H4", "H5", "H6"}


def _heading_level(tag: str) -> int:
    try:
        return int(tag[1])
    except Exception:
        return 0


def _box_prefix_from_meta(meta: dict) -> str | None:
    zone = meta.get("context_zone")
    if zone in BOX_PREFIX_BY_ZONE:
        return BOX_PREFIX_BY_ZONE[zone]
    box_type = meta.get("box_type")
    if box_type:
        return BOX_TYPE_MAPPING.get(box_type, "NBX")
    return None


def _list_tag_from_meta(meta: dict, base_tag: str | None = None) -> str | None:
    kind = meta.get("list_kind")
    pos = meta.get("list_position")
    if not kind or not pos:
        return None

    zone = meta.get("context_zone", "BODY")
    prefix = None

    if zone == "TABLE":
        if kind == "bullet":
            prefix = "TBL"
        elif kind == "numbered":
            prefix = "TNL"
        else:
            # Some pipelines emit unordered for bullet-like XML markers.
            prefix = "TBL" if (meta.get("has_bullet") or meta.get("has_xml_list")) else "TUL"
    elif zone.startswith("BOX_"):
        box_prefix = _box_prefix_from_meta(meta) or "NBX"
        if kind == "bullet":
            prefix = f"{box_prefix}-BL"
        elif kind == "numbered":
            prefix = f"{box_prefix}-NL"
        else:
            prefix = f"{box_prefix}-UL"
    else:
        if kind == "bullet":
            prefix = "BL"
        elif kind == "numbered":
            prefix = "NL"
        else:
            # Treat unordered + bullet marker as BL to avoid BL->UL drift.
            prefix = "BL" if (meta.get("has_bullet") or meta.get("has_xml_list")) else "UL"

    if base_tag:
        # If base tag implies OBJ/KT/KP etc, preserve that prefix
        if "-BL" in base_tag:
            prefix = base_tag.split("-BL")[0] + "-BL"
        elif "-NL" in base_tag:
            prefix = base_tag.split("-NL")[0] + "-NL"
        elif "-UL" in base_tag:
            prefix = base_tag.split("-UL")[0] + "-UL"

    return f"{prefix}-{pos}"


def _find_closest_style(tag: str, allowed: set[str]) -> str | None:
    """
    Find the closest semantically similar style in the allowed set.

    Uses three strategies in order:
    1. Explicit semantic fallback chains (most reliable)
    2. Prefix-based matching (same family, e.g., BX2-TXT -> BX2-TXT-FLUSH)
    3. String similarity (last resort, threshold 0.6)

    Returns:
        Closest allowed style, or None if no good match found.
    """
    normalized = normalize_style(tag)

    # Strategy 1: Explicit fallback chains
    chain = SEMANTIC_FALLBACK_CHAINS.get(normalized, [])
    for candidate in chain:
        norm_candidate = normalize_style(candidate)
        if norm_candidate in allowed:
            return norm_candidate

    # Strategy 1.5: Unsuffixed positional family → prefer MID for deterministic output.
    # e.g. ANS-UL → ANS-UL-MID (not ANS-UL-FIRST which is nondeterministic via set iteration)
    if _UNSUFFIXED_LIST_FAMILY_RE.fullmatch(normalized):
        for pos in ("MID", "FIRST", "LAST"):
            candidate = f"{normalized}-{pos}"
            if candidate in allowed:
                return candidate

    # Strategy 2: Prefix-based matching
    # Try to find styles in same family (e.g., BX2-TXT -> BX2-*)
    if "-" in normalized:
        parts = normalized.rsplit("-", 1)
        prefix = parts[0]
        # Look for any style with same prefix
        prefix_matches = [s for s in allowed if s.startswith(prefix + "-")]
        if prefix_matches:
            # Prefer -MID variant for deterministic output
            mid_candidate = prefix + "-MID"
            if mid_candidate in allowed:
                return mid_candidate
            # Fall back to shortest match, stable lexicographic sort for determinism
            prefix_matches.sort(key=lambda s: (len(s), s))
            return prefix_matches[0]

    # Strategy 3: String similarity (conservative threshold)
    best_match = None
    best_score = 0.0
    for candidate in allowed:
        score = SequenceMatcher(None, normalized, candidate).ratio()
        if score > best_score and score >= 0.6:
            best_score = score
            best_match = candidate

    return best_match


def _ensure_allowed(tag: str, allowed: set[str], fallback: str) -> str:
    """
    Ensure tag is in allowed styles, using semantic remapping before downgrading.

    Order of preference:
    1. Normalized tag (if in allowed)
    2. Semantic fallback chain (closest related style)
    3. Explicit fallback parameter (if in allowed)
    4. TXT (universal fallback)
    5. Original normalized tag (if nothing else works)
    """
    normalized_tag = normalize_style(tag)
    if normalized_tag in allowed:
        return normalized_tag

    # Try semantic remapping before falling back to TXT
    closest = _find_closest_style(normalized_tag, allowed)
    if closest:
        logger.debug(f"Semantic remap: '{normalized_tag}' -> '{closest}'")
        return closest

    # Explicit fallback
    normalized_fallback = normalize_style(fallback)
    if normalized_fallback in allowed:
        return normalized_fallback

    # Last resort: TXT if present
    if "TXT" in allowed:
        return "TXT"

    # Otherwise return normalized tag
    return normalized_tag


def _first_allowed(candidates: list[str], allowed: set[str]) -> str | None:
    for candidate in candidates:
        if normalize_style(candidate) in allowed:
            return candidate
    return None


def _starts_with_number(text: str) -> bool:
    t = LEADING_XML_TAGS_RE.sub("", text or "")
    return bool(REF_NUMBER_RE.match(t))


def _starts_with_ref_bullet(text: str) -> bool:
    t = LEADING_XML_TAGS_RE.sub("", text or "")
    return bool(REF_BULLET_RE.match(t))


def _looks_like_reference_entry(text: str) -> bool:
    t = LEADING_XML_TAGS_RE.sub("", text or "").strip()
    if not t:
        return False
    t_lower = t.lower()
    if re.search(r"\b(suggested readings|further reading|recommended reading)\b", t_lower):
        return False
    if _starts_with_number(t):
        return True
    if REF_BULLET_RE.match(t):
        return True
    has_year = bool(re.search(r"\b(19|20)\d{2}\b", t_lower))
    has_doi = "doi" in t_lower
    has_et_al = "et al" in t_lower
    punct = t.count(".") + t.count(";") + t.count(":") + t.count(",")
    if (has_year or has_doi or has_et_al) and punct >= 2:
        return True
    # Permissive author-title pattern (no year but looks like citation)
    if re.search(r"[A-Za-z].*,.+\.", t) and punct >= 2:
        return True
    return False


def _looks_like_t4_heading(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if len(t) > 60:
        return False
    if re.search(r"[.!?;:]\s*$", t):
        return False
    # Numeric-ish data cells should stay as body table text.
    if re.fullmatch(r"[\d\s,./%\-()+]+", t):
        return False
    if T4_HEADING_CASE_RE.match(t):
        return True
    words = [w for w in re.split(r"\s+", t) if w]
    if not words:
        return False
    if len(words) < 2:
        return False
    titled = 0
    for w in words:
        token = re.sub(r"[^A-Za-z0-9]", "", w)
        if not token:
            continue
        if token[:1].isupper():
            titled += 1
    return titled >= max(1, int(0.7 * len(words)))


def _inline_heading_tag(text: str) -> str | None:
    m = INLINE_H_TAG_RE.match(text or "")
    if not m:
        return None
    return f"H{m.group(1)}"


def _inline_heading_level(text: str) -> int | None:
    m = INLINE_H_TAG_RE.match(text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _tag_matches_inline_heading_level(tag: str, level: int | None) -> bool:
    if level is None:
        return False
    t = normalize_style(tag or "")
    if not t:
        return False
    # Preserve valid heading variants (e.g. H10/H20/H21) when they match the
    # explicit inline marker family. We only need the leading heading digit.
    m = re.fullmatch(r"H([1-6])\d*", t)
    return bool(m and int(m.group(1)) == int(level))


def _align_semantic_list_position_variant(tag: str, meta: dict, allowed: set[str]) -> str | None:
    """
    Align FIRST/MID/LAST for semantic list families while preserving the tag family.

    Examples:
    - KT-BL-MID  -> KT-BL-FIRST / KT-BL-LAST
    - EOC-NL-MID -> EOC-NL-FIRST / EOC-NL-LAST
    - RQ-LL2-MID -> RQ-LL2-LAST
    - BL2-MID    -> BL2-LAST
    """
    m = SEMANTIC_LIST_POS_RE.fullmatch(normalize_style(tag or ""))
    if not m:
        return None
    list_pos = str((meta or {}).get("list_position") or "").strip().upper()
    if list_pos not in {"FIRST", "MID", "LAST"}:
        return None

    prefix = m.group("prefix") or ""
    base = m.group("base")
    desired = f"{prefix}{base}-{list_pos}"
    if not allowed or desired in allowed:
        return desired

    # Nested families often only define MID/LAST. Fall back conservatively to MID.
    mid = f"{prefix}{base}-MID"
    if not allowed or mid in allowed:
        return mid
    return None


def _inline_heading_variant_for_context(text: str, meta: dict, zone: str) -> str | None:
    """
    Infer custom heading variants (H10/H20/H21) from explicit inline markers and
    source heading styles in BODY text when the model returns plain H1/H2.

    This matches a common publisher pattern where source Word styles are built-in
    Heading 2 / Heading 3, while the tagged corpus expects canonical H10/H20/H21.
    """
    lvl = _inline_heading_level(text)
    if lvl is None:
        return None
    if zone != "BODY":
        return None
    source_style = str((meta or {}).get("style_name") or "")
    if lvl == 1 and source_style == "Heading 2":
        return "H10"
    if lvl == 2:
        if source_style == "Heading 3":
            return "H20"
        if source_style == "Heading 2":
            return "H21"
    return None


def validate_and_repair(
    classifications: list[dict],
    blocks: list[dict],
    allowed_styles: Iterable[str] | None = None,
    preserve_lists: bool = False,
    preserve_marker_pmi: bool = False,
) -> list[dict]:
    """
    Validate and repair classification results based on deterministic rules.
    """
    # Metrics tracking for STYLE_CANONICALIZATION logging
    metrics = {
        "invalid_styles": 0,      # Styles not in allowed_styles
        "repaired": 0,            # Total repairs made
        "composite_rejected": 0,  # Composite tags split/rejected
        "alias_resolved": 0,      # Alias canonicalized
        "zone_repaired": 0,       # Zone-invalid styles fixed
    }

    allowed = _allowed_set(allowed_styles)
    block_lookup = {b["id"]: b for b in blocks}

    original_by_id = {c.get("id"): c.get("tag") for c in classifications}
    # Prepare reference zone detection using initial tags
    ref_blocks = []
    for c in classifications:
        blk = block_lookup.get(c.get("id"), {})
        ref_blocks.append(
            {
                "id": c.get("id"),
                "text": blk.get("text", ""),
                "tag": c.get("tag", ""),
                "metadata": blk.get("metadata", {}),
            }
        )
    reference_zone_ids, _ref_trigger, _ref_start = detect_reference_zone(ref_blocks)
    # Mark reference zone on blocks metadata for downstream enforcement/debug
    for b in blocks:
        if b.get("id") in reference_zone_ids:
            meta = b.setdefault("metadata", {})
            meta["is_reference_zone"] = True
    repaired: list[dict] = []
    for clf in classifications:
        para_id = clf.get("id")
        tag = clf.get("tag", "TXT")
        original_input_tag = tag  # Preserve original for table heading map lookup
        confidence = clf.get("confidence", 85)
        reason = clf.get("reasoning")

        block = block_lookup.get(para_id, {})
        meta = block.get("metadata", {})
        if "box_prefix" not in meta:
            meta["box_prefix"] = _box_prefix_from_meta(meta)
        norm_tag = normalize_style(tag, meta=meta)
        zone = meta.get("context_zone", "BODY")
        text = block.get("text", "")
        in_reference_zone = bool(meta.get("is_reference_zone")) or zone == "REFERENCE"

        lock_tag = norm_tag in allowed and confidence >= 0.90
        if preserve_marker_pmi and tag == "PMI" and text.lstrip().startswith("<"):
            lock_tag = True
        if preserve_marker_pmi and text.strip().upper() == "<BL>":
            tag = "PMI"
            lock_tag = True

        changed = False
        change_reason = []
        original_tag = norm_tag
        came_from_h4h5 = False

        # Composite tag detection and repair (before canonicalization)
        if not lock_tag and _is_composite_tag(tag):
            components = _split_composite_tag(tag)
            # Try each component in order, use first valid one
            chosen_component = None
            for component in components:
                comp = component.strip()
                if comp:
                    # Normalize the component
                    norm_comp = normalize_style(comp, meta=meta)
                    # Check if valid in allowed_styles
                    if norm_comp in allowed:
                        chosen_component = comp
                        break

            # If no valid component found, use first component and let fallback handle it
            if chosen_component is None and components:
                chosen_component = components[0].strip()

            if chosen_component:
                tag = chosen_component
                # Re-normalize with proper meta context (zone-aware)
                norm_tag = normalize_style(tag, meta=meta)
                changed = True
                change_reason.append("composite-rejected")
                metrics["composite_rejected"] += 1

        # Canonicalize style before applying other rules (non-trusted only)
        if not lock_tag and norm_tag and norm_tag != tag:
            tag = norm_tag
            changed = True
            change_reason.append("style-canonicalize")
            metrics["alias_resolved"] += 1

        # Box markers -> PMI
        if not lock_tag and meta.get("box_marker") in {"start", "end"}:
            if tag != "PMI":
                tag = "PMI"
                changed = True
                change_reason.append("box-marker")

        # Generic marker-only paragraphs (e.g. </BL>, <front-open>, <FIG...>) should
        # remain PMI, not semantic content styles. Inline heading markers are excluded.
        #
        # Apply this even for "locked" high-confidence tags because marker paragraphs
        # can occasionally leak into the classifier and arrive with a valid heading/tag.
        text_stripped = (text or "").strip()
        if (
            MARKER_ONLY_TAG_RE.match(text_stripped)
            and _inline_heading_level(text_stripped) is None
            and tag != "PMI"
        ):
            tag = "PMI"
            lock_tag = True
            changed = True
            change_reason.append("marker-only")

        # Metadata zone enforced
        if not lock_tag and zone == "METADATA" and tag != "PMI":
            tag = "PMI"
            changed = True
            change_reason.append("metadata-zone")

        # Explicit inline heading marker should win over model drift like TXT/TXT-FLUSH.
        if not lock_tag and zone != "TABLE":
            inline_heading = _inline_heading_tag(text)
            inline_heading_level = _inline_heading_level(text)
            inline_heading_variant = _inline_heading_variant_for_context(text, meta, zone)
            if (
                inline_heading_variant
                and inline_heading_variant in allowed
                and tag != inline_heading_variant
            ):
                tag = inline_heading_variant
                changed = True
                change_reason.append("inline-heading-variant")
            if inline_heading and not _tag_matches_inline_heading_level(tag, inline_heading_level):
                tag = inline_heading
                changed = True
                change_reason.append("inline-heading-marker")

        # Figure/Table captions and sources
        if not lock_tag and meta.get("caption_type") == "table" and tag != "T1":
            tag = "T1"
            changed = True
            change_reason.append("table-caption")
        if not lock_tag and meta.get("caption_type") == "figure" and tag != "FIG-LEG":
            tag = "FIG-LEG"
            changed = True
            change_reason.append("figure-caption")
        if not lock_tag and meta.get("source_line") and tag != "TSN":
            tag = "TSN"
            changed = True
            change_reason.append("source-line")

        # Box type vs title separation
        if not lock_tag and zone.startswith("BOX_"):
            box_prefix = _box_prefix_from_meta(meta) or "NBX"
            if meta.get("box_label"):
                desired = f"{box_prefix}-TYPE"
                if tag != desired:
                    tag = desired
                    changed = True
                    change_reason.append("box-type-label")
            elif meta.get("box_title"):
                desired = f"{box_prefix}-TTL"
                if tag != desired:
                    tag = desired
                    changed = True
                    change_reason.append("box-title")

        # Reference zone enforcement (initial pass)
        if para_id in reference_zone_ids and lock_tag and not norm_tag.startswith("REF-"):
            lock_tag = False

        if in_reference_zone and _looks_like_reference_entry(text):
            # Defer strict REF-N/REF-U assignment to final reference-zone pass
            pass

        # Zone-based enforcement: TABLE - Canonical heading mappings
        if not lock_tag and zone == "TABLE":
            # Map SK_H* and TBL-H* to TH* (all levels 1-6)
            # Check original input tag to handle fallback logic correctly
            table_heading_map = {
                "SK_H1": "TH1", "SK_H2": "TH2", "SK_H3": "TH3",
                "SK_H4": "TH4", "SK_H5": "TH5", "SK_H6": "TH6",
                "TBL-H1": "TH1", "TBL-H2": "TH2", "TBL-H3": "TH3",
                "TBL-H4": "TH4", "TBL-H5": "TH5", "TBL-H6": "TH6",
            }
            mapped_heading = table_heading_map.get(original_input_tag)
            if mapped_heading:
                # Only apply if target is in allowed_styles (or no constraint)
                if not allowed or mapped_heading in allowed:
                    tag = mapped_heading
                    changed = True
                    change_reason.append("zone-table-heading-map")
                else:
                    # Fallback to generic table cell if TH* not allowed
                    tag = "T"
                    changed = True
                    change_reason.append("zone-table-heading-fallback")

            text_stripped = text.strip()
            text_lower = text_stripped.lower()
            # Source attribution lines → TSN  (checked first — higher priority)
            is_source = bool(
                text_lower.startswith("source")
                or text_lower.startswith("adapted from")
                or text_lower.startswith("reproduced from")
                or text_lower.startswith("reprinted from")
                or text_lower.startswith("data from")
                or text_lower.startswith("courtesy of")
                or text_lower.startswith("with permission from")
                or text_lower.startswith("from ")
            )
            # Note / symbol / letter footnotes → TFN
            is_footnote = (not is_source) and bool(
                text_lower.startswith("note")
                or text_stripped.startswith("*")
                or text_stripped.startswith("†")
                or re.match(r"^[a-z]\)", text_stripped, re.IGNORECASE)
            )
            if is_source:
                tag = "TSN"
                changed = True
                change_reason.append("zone-table-source")
            elif is_footnote:
                tag = "TFN"
                changed = True
                change_reason.append("zone-table-footnote")

            # Table text canonicalization (TBL-TXT -> TD if TD is allowed)
            if tag == "TBL-TXT" and "TD" in allowed:
                tag = "TD"
                changed = True
                change_reason.append("zone-table-txt-to-td")

            if tag.startswith(("BL-", "UL-", "NL-")):
                tag = "T"
                changed = True
                change_reason.append("zone-table-list")
            elif tag in {"TXT", "TXT-FLUSH", "T"} and not is_footnote:
                # Deterministic T/T2/T4 inference to reduce classifier drift.
                if meta.get("is_header_row") and "T2" in allowed:
                    tag = "T2"
                    change_reason.append("zone-table-header-row")
                elif (
                    meta.get("is_stub_col")
                    and "T4" in allowed
                    and _looks_like_t4_heading(text)
                ):
                    tag = "T4"
                    change_reason.append("zone-table-stub-col")
                elif (
                    float(confidence) < 0.90
                    and _looks_like_t4_heading(text)
                    and "T4" in allowed
                ):
                    tag = "T4"
                    change_reason.append("zone-table-t4-heuristic")
                else:
                    tag = "T"
                    change_reason.append("zone-table-text")
                changed = True

        # Zone-based enforcement: BACK_MATTER semantic normalization
        if not lock_tag and zone == "BACK_MATTER":
            backmatter_map = {
                "FIG-LEG": ["FIG-LEG", "UNFIG-LEG", "FG-CAP", "TXT-FLUSH", "TXT"],
                "FIG-SRC": ["FIG-SRC", "UNFIG-SRC", "TSN", "TXT-FLUSH", "TXT"],
                "T1": ["T1", "BM-TTL", "TXT-FLUSH", "TXT"],
                "TFN": ["TFN", "TSN", "TXT-FLUSH", "TXT"],
                "BM-TTL": ["BM-TTL", "T1", "REFH1", "REF-H1", "TXT-FLUSH", "TXT"],
            }
            if tag in backmatter_map:
                mapped = _first_allowed(backmatter_map[tag], allowed)
                if mapped and mapped != tag:
                    tag = mapped
                    changed = True
                    change_reason.append("zone-backmatter-normalize")

        # List enforcement (skip inside reference zone)
        if not in_reference_zone:
            semantic_list_tag = _align_semantic_list_position_variant(tag, meta, allowed)
            list_tag = _list_tag_from_meta(meta, base_tag=tag)
            norm_tag = normalize_style(tag)
            is_ref_like_tag = norm_tag.startswith("REF") or norm_tag in {"BIB", "SR", "SRH1"}
            is_ref_like_text = _looks_like_reference_entry(text)

            if (
                not lock_tag
                and semantic_list_tag
                and semantic_list_tag != tag
                and not is_ref_like_tag
                and not is_ref_like_text
            ):
                tag = semantic_list_tag
                changed = True
                change_reason.append("semantic-list-position")
            elif (
                not lock_tag
                and list_tag
                and not tag.endswith(("-FIRST", "-MID", "-LAST"))
                and not is_ref_like_tag
                and not is_ref_like_text
            ):
                tag = list_tag
                changed = True
                change_reason.append("list-position")
            elif not lock_tag and list_tag and tag.startswith(("BL", "NL", "UL", "TBL", "TNL", "TUL")):
                # Align list position if needed
                if tag != list_tag:
                    skip_alignment = False
                    # Prevent BL -> UL drift when metadata is ambiguous.
                    # But allow UL -> BL correction when list metadata indicates bullet lists.
                    if tag.startswith("BL-") and list_tag.startswith("UL-"):
                        skip_alignment = True
                    if preserve_lists and tag.startswith("BL-"):
                        skip_alignment = True
                    if not skip_alignment:
                        tag = list_tag
                        changed = True
                        change_reason.append("list-position")
            elif preserve_lists and tag.startswith("BL-"):
                # Preserve publishing-tag bullet lists when requested
                pass

        # Table zone fallback keeps table-safe styles only
        if not lock_tag and zone == "TABLE" and not validate_style_for_zone(tag, zone):
            if tag.startswith("BX4-"):
                inferred = "BX4-TXT"
            else:
                inferred = "T"
            if tag != inferred:
                tag = inferred
                changed = True
                change_reason.append("table-inferred")
                metrics["zone_repaired"] += 1

        # Front matter enforcement (zone constraints)
        if not lock_tag and zone != "BODY" and not validate_style_for_zone(tag, zone):
            # Prefer list-based fallback if present
            list_tag = _list_tag_from_meta(meta, base_tag=tag)
            if zone == "TABLE":
                fallback = "T"
            elif zone == "BACK_MATTER":
                fallback = (
                    list_tag
                    or _first_allowed(["REF-U", "REF-N", "BM-TTL", "TSN", "TXT-FLUSH", "TXT"], allowed)
                    or tag
                )
            else:
                fallback = list_tag or "TXT"
            if tag != fallback:
                tag = fallback
                changed = True
                change_reason.append("zone-fallback")
                metrics["zone_repaired"] += 1

        # Canonicalize headings before allowed-style enforcement (non-trusted only)
        if not lock_tag and tag in {"H4", "H5"}:
            tag = "H3"
            changed = True
            change_reason.append("heading-canonicalize")
            came_from_h4h5 = True

        # Reference-zone deterministic mapping must happen before allowed-style filtering.
        if in_reference_zone:
            text_stripped = text.strip()
            if text_stripped.lower().startswith("<ref-h2>") or meta.get("ref_heading"):
                if tag != "REFH2":
                    tag = "REFH2"
                    changed = True
                    change_reason.append("ref-zone-heading")
            elif tag.startswith(("UL-", "BL-")) and tag not in {"SR", "SRH1"}:
                desired_ref = "REF-U" if _starts_with_ref_bullet(text) else "REF-N"
                if tag != desired_ref:
                    tag = desired_ref
                    changed = True
                    change_reason.append("ref-zone-list-override")
            elif tag.startswith("APX-REF"):
                # Preserve appendix reference family tags in appendix/reference sections.
                pass
            elif tag not in {"SR", "SRH1"} and _looks_like_reference_entry(text):
                desired_ref = "REF-U" if _starts_with_ref_bullet(text) else "REF-N"
                if tag != desired_ref:
                    tag = desired_ref
                    changed = True
                    change_reason.append("ref-zone-pre-allowed")

        # Ensure tag is in allowed styles
        fallback_tag = "TXT"
        ensured = _ensure_allowed(tag, allowed, fallback=fallback_tag)
        if ensured != tag:
            tag = ensured
            changed = True
            change_reason.append("not-allowed")
            metrics["invalid_styles"] += 1
            if tag in _HARD_FALLBACK_TAGS:
                logger.warning(f"Tag not allowed, downgraded: para {para_id} -> {tag}")
            else:
                logger.info(f"Tag not allowed, semantic-repair: para {para_id} -> {tag}")

        if changed:
            confidence = min(confidence, 80)
            clf = {**clf, "tag": tag, "confidence": confidence, "repaired": True}
            metrics["repaired"] += 1
            if change_reason:
                clf["repair_reason"] = ",".join(change_reason)
            if reason:
                clf["reasoning"] = reason
        else:
            clf = {**clf, "tag": tag}

        repaired.append(clf)

    # Reference section preservation pass (keep SR/REF/BIB from classifier)
    in_ref_section = False
    ref_trigger_tags = {"SRH1", "REFH1"}
    ref_keep_tags = {"SR", "REF-N", "REF-N0", "BIB", "APX-REF-N", "APX-REF-U", "APX-REFH1"}
    section_end_tags = {"H1", "H2", "CN", "CT"}

    for clf in repaired:
        para_id = clf.get("id")
        original_tag = original_by_id.get(para_id)
        text = block_lookup.get(para_id, {}).get("text", "")

        if normalize_style(clf.get("tag", "")) in ref_trigger_tags or text.lstrip().upper().startswith("<REF>"):
            in_ref_section = True

        if in_ref_section and normalize_style(original_tag or "") in ref_keep_tags:
            if normalize_style(original_tag or "") in allowed:
                if clf.get("tag") != original_tag:
                    clf["tag"] = original_tag
                    clf["repaired"] = True
                    clf["repair_reason"] = (clf.get("repair_reason", "") + ",ref-section-preserve").strip(",")

        if normalize_style(clf.get("tag", "")) in section_end_tags:
            in_ref_section = False

    # BACK_MATTER handling for FIG/TABLE-like tags (post-pass using indices)
    for idx, clf in enumerate(repaired):
        para_id = clf.get("id")
        block = block_lookup.get(para_id, {})
        zone = block.get("metadata", {}).get("context_zone", "BODY")
        tag = clf.get("tag", "")

        if zone == "BACK_MATTER" and (
            tag.startswith("FIG-")
            or tag in {"T1", "T2", "T4", "TFN", "TSN", "TBL-FIRST", "TBL-MID", "TBL-LAST"}
        ):
            anchor_found = False
            for j in range(max(0, idx - 10), min(len(repaired), idx + 11)):
                if j == idx:
                    continue
                other_tag = repaired[j].get("tag", "")
                if other_tag.startswith("FIG-") or other_tag in {"T1", "T2", "T4", "TFN", "TSN"}:
                    anchor_found = True
                    break
            if not anchor_found:
                meta = block.get("metadata", {})
                in_ref_zone = bool(meta.get("is_reference_zone")) or meta.get("context_zone") == "REFERENCE"
                if in_ref_zone:
                    fallback = _first_allowed(["REF-U", "REF-N", "REF-TXT", "TXT-FLUSH", "TXT"], allowed) or "TXT-FLUSH"
                else:
                    fallback = _first_allowed(["TSN", "BM-TTL", "TXT-FLUSH", "TXT"], allowed) or "TXT-FLUSH"
                clf["tag"] = fallback
                clf["repaired"] = True
                clf["repair_reason"] = (clf.get("repair_reason", "") + ",zone-backmatter-downgrade").strip(",")
                logger.warning(f"BACK_MATTER float without anchor: para {para_id} -> {clf['tag']}")

    # First paragraph after heading should be flush text in normal body flow.
    for idx in range(1, len(repaired)):
        prev = repaired[idx - 1]
        cur = repaired[idx]
        cur_id = cur.get("id")
        block = block_lookup.get(cur_id, {})
        meta = block.get("metadata", {})
        zone = meta.get("context_zone", "BODY")
        text = (block.get("text") or "").strip()
        if not text:
            continue
        if zone not in {"BODY", "BACK_MATTER", "REFERENCE"}:
            continue
        prev_tag = normalize_style(prev.get("tag", ""))
        cur_tag = normalize_style(cur.get("tag", ""))
        if prev_tag not in {"H1", "H2", "H3", "APX-H1", "APX-H2", "APX-H3"}:
            continue
        if cur_tag != "TXT":
            continue
        # Do not rewrite list/table/caption-like lines.
        if _list_tag_from_meta(meta, base_tag=cur.get("tag", "")):
            continue
        if meta.get("caption_type") or meta.get("source_line"):
            continue
        cur["tag"] = "TXT-FLUSH" if "TXT-FLUSH" in allowed else "TXT"
        cur["repaired"] = True
        cur["repair_reason"] = (cur.get("repair_reason", "") + ",heading-following-flush").strip(",")

    # Heading hierarchy pass (safe enforcement)
    last_heading_level = 0
    seen_h1 = False
    seen_h2 = False
    for clf in repaired:
        tag = clf.get("tag", "TXT")
        confidence = float(clf.get("confidence", 0))
        if normalize_style(tag) in allowed and confidence >= 0.90:
            # Preserve trusted tags
            if tag == "H1":
                seen_h1 = True
                seen_h2 = False
                last_heading_level = 1
            elif tag == "H2":
                seen_h2 = True
                last_heading_level = 2
            elif tag == "H3":
                last_heading_level = 3
            continue
        if not _is_heading(tag):
            continue
        level = _heading_level(tag)

        new_tag = tag
        violation = False

        # Clamp H4/H5/H6 to H3
        if level >= 4:
            violation = True
            new_tag = "H3"

        # Disallow H2 if no prior H1
        if level == 2 and not seen_h1:
            violation = True
            if confidence >= 0.7:
                new_tag = "H1"
            else:
                new_tag = "TXT"

        # Disallow H3 if no prior H2 in section
        if level == 3 and not seen_h2 and not came_from_h4h5:
            violation = True
            new_tag = "H2"
            logger.warning("Heading hierarchy violation (H3 without prior H2): H3 -> H2")

        # Disallow jumps > 1
        if last_heading_level and level > last_heading_level + 1:
            violation = True
            if confidence >= 0.7:
                new_level = min(last_heading_level + 1, 2) if last_heading_level >= 1 else 1
                new_tag = f"H{new_level}"
            else:
                new_tag = "TXT"

        # Never promote past H1
        if new_tag not in {"H1", "H2", "H3"} and new_tag.startswith("H"):
            new_tag = "H1"

        if new_tag != tag:
            clf["tag"] = new_tag
            clf["confidence"] = min(confidence, 80)
            clf["repaired"] = True
            clf["repair_reason"] = (clf.get("repair_reason", "") + ",heading-hierarchy").strip(",")
            logger.warning(f"Heading hierarchy violation: {tag} -> {new_tag}")

        # Update seen state with possibly adjusted tag
        if clf.get("tag") == "H1":
            seen_h1 = True
            seen_h2 = False
            last_heading_level = 1
        elif clf.get("tag") == "H2":
            seen_h2 = True
            last_heading_level = 2
        elif clf.get("tag") == "H3":
            last_heading_level = 3

    # Final reference zone enforcement (idempotent guard)
    for clf in repaired:
        para_id = clf.get("id")
        block = block_lookup.get(para_id, {})
        meta = block.get("metadata", {})
        in_reference_zone = bool(meta.get("is_reference_zone")) or (
            meta.get("context_zone") in {"REFERENCE", "BACK_MATTER"} and meta.get("is_reference_zone")
        )
        if not in_reference_zone:
            continue

        text = block.get("text", "")
        tag = clf.get("tag", "")
        text_stripped = text.strip()
        if text_stripped.lower().startswith("<ref-h2>") or meta.get("ref_heading"):
            clf["tag"] = "REFH2"
            clf["confidence"] = max(float(clf.get("confidence", 0)), 0.99)
            clf["repaired"] = True
            clf["repair_reason"] = (clf.get("repair_reason", "") + ",ref-zone-heading").strip(",")
            continue

        if tag in {"SR", "SRH1"}:
            continue
        if tag.startswith("APX-REF"):
            continue
        if preserve_lists and preserve_marker_pmi and tag.startswith("SR") and not _looks_like_reference_entry(text):
            continue
        if not _looks_like_reference_entry(text):
            continue

        desired = "REF-U" if _starts_with_ref_bullet(text) else "REF-N"
        if clf.get("tag") != desired:
            clf["tag"] = desired
            clf["confidence"] = max(float(clf.get("confidence", 0)), 0.99)
            clf["repaired"] = True
            clf["repair_reason"] = (clf.get("repair_reason", "") + ",ref-zone-final").strip(",")

    # Marker-triggered reference-section fallback (covers docs where metadata-based
    # reference-zone detection misses <REF>-prefixed reference sections).
    in_ref_marker_section = False
    seen_ref_entries = 0
    marker_ref_headings = {
        "references",
        "bibliography",
        "works cited",
        "cited references",
        "literature cited",
    }
    marker_section_end_tags = {"H1", "H2", "CN", "CT", "T1", "BM-TTL"}
    for clf in repaired:
        para_id = clf.get("id")
        block = block_lookup.get(para_id, {})
        meta = block.get("metadata", {})
        text = (block.get("text", "") or "").strip()
        tag = clf.get("tag", "")
        norm_tag = normalize_style(tag)
        text_no_tags = LEADING_XML_TAGS_RE.sub("", text).strip()
        text_no_tags_lower = text_no_tags.lower()
        starts_ref_marker = text.lower().startswith("<ref>")

        if starts_ref_marker and text_no_tags_lower in marker_ref_headings:
            in_ref_marker_section = True
            seen_ref_entries = 0
            if clf.get("tag") != "REFH1":
                clf["tag"] = "REFH1"
                clf["confidence"] = max(float(clf.get("confidence", 0)), 0.99)
                clf["repaired"] = True
                clf["repair_reason"] = (clf.get("repair_reason", "") + ",ref-marker-heading").strip(",")
            continue

        if not in_ref_marker_section:
            continue

        if meta.get("context_zone") == "TABLE":
            in_ref_marker_section = False
            seen_ref_entries = 0
            continue
        if norm_tag in marker_section_end_tags and not starts_ref_marker:
            in_ref_marker_section = False
            seen_ref_entries = 0
            continue
        if text_no_tags.lower().startswith("table ") and norm_tag in {"T1", "BM-TTL", "TXT", "TXT-FLUSH"}:
            in_ref_marker_section = False
            seen_ref_entries = 0
            continue

        if tag in {"SR", "SRH1"} or tag.startswith("APX-REF"):
            continue

        if not text_no_tags:
            continue

        if tag.startswith(("UL-", "BL-", "NL-")) or _looks_like_reference_entry(text):
            desired = "REF-U" if _starts_with_ref_bullet(text) else "REF-N"
            if clf.get("tag") != desired:
                clf["tag"] = desired
                clf["confidence"] = max(float(clf.get("confidence", 0)), 0.99)
                clf["repaired"] = True
                clf["repair_reason"] = (clf.get("repair_reason", "") + ",ref-marker-section").strip(",")
            seen_ref_entries += 1
            continue

        # Allow a small amount of blank/transition text, but once we have seen
        # multiple refs and hit non-reference prose, end the marker section.
        if seen_ref_entries >= 3:
            in_ref_marker_section = False
            seen_ref_entries = 0

    # Emit STYLE_CANONICALIZATION metrics
    logger.info(
        "STYLE_CANONICALIZATION invalid=%d repaired=%d composite_rejected=%d alias_resolved=%d zone_repaired=%d",
        metrics["invalid_styles"],
        metrics["repaired"],
        metrics["composite_rejected"],
        metrics["alias_resolved"],
        metrics["zone_repaired"],
    )

    return repaired
