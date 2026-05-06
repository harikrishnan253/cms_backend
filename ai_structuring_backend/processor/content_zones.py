"""
Content-driven zone detection and tag overlay enforcement.

Inspects paragraph text content (independent of source pStyle) to identify
heading-driven zones — Case Study, Objectives, Key Terms, Key Points,
End-of-Chapter (Summary / Review Questions / Conclusion), and a
post-References zone for PMI promotion. Once a zone is detected, an overlay
pass rewrites validator-produced tags into the appropriate zone-qualified
form (e.g. ``H1`` -> ``EOC-H1`` inside the EOC zone, ``T1`` -> ``PMI`` after
References).

The detection is additive: it sets ``metadata['content_zone']`` on each
block and a ``metadata['content_zone_role']`` for opener / first-body
markers. Existing ``context_zone`` and ``is_reference_zone`` fields are
left untouched so prior logic continues to work.

Zone openers are heading-shaped paragraphs whose text matches a known
phrase. A zone stays active until a different known opener appears, or
until the document ends.
"""

from __future__ import annotations

import re
import logging
from typing import Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heading patterns that open each content zone
# ---------------------------------------------------------------------------

# Paragraphs whose text matches one of these (in heading shape) start the
# corresponding zone. The order here is the priority order for matching.
_ZONE_OPENERS: list[tuple[str, re.Pattern]] = [
    ("CASE_STUDY",   re.compile(r"^\s*case\s+study\b", re.IGNORECASE)),
    ("OBJ",          re.compile(r"^\s*(?:learning\s+)?objectives?\s*$", re.IGNORECASE)),
    ("KT",           re.compile(r"^\s*key\s+terms?\s*$", re.IGNORECASE)),
    ("KP",           re.compile(r"^\s*key\s+points?\s*$", re.IGNORECASE)),
    ("EOC_SUMMARY",  re.compile(r"^\s*summary\s*$", re.IGNORECASE)),
    ("EOC_REVIEW",   re.compile(r"^\s*review\s+questions?\s*$", re.IGNORECASE)),
    ("EOC_CONCL",    re.compile(r"^\s*conclusion\s*$", re.IGNORECASE)),
    ("POST_REF",     re.compile(r"^\s*references?\s*$", re.IGNORECASE)),
]

# Heading shape: short-ish, no sentence-terminating punctuation, doesn't end
# with a colon (which would be a label).
_TERMINAL_PUNCT_RE = re.compile(r"[.!?:]\s*$")


# ---------------------------------------------------------------------------
# Chapter / Section / Unit / Part opener patterns (front-matter, content-only)
# ---------------------------------------------------------------------------

# Anchor only at document start (configurable via _OPENER_LOOKAHEAD blocks).
# A standalone numeric paragraph is *only* treated as a chapter number when
# followed by a heading-shape title within the next non-blank paragraph.
_OPENER_LOOKAHEAD = 6

_CHAPTER_OPENER_RE = re.compile(
    r"^\s*(?:<CN>\s*)?chapter\s+([0-9IVXLCDM]+)\s*$", re.IGNORECASE
)
_SECTION_OPENER_RE = re.compile(
    r"^\s*(?:<SN>\s*)?section\s+([0-9IVXLCDM]+)\s*$", re.IGNORECASE
)
_UNIT_OPENER_RE = re.compile(
    r"^\s*(?:<UN>\s*)?unit\s+([0-9IVXLCDM]+)\s*$", re.IGNORECASE
)
_PART_OPENER_RE = re.compile(
    r"^\s*(?:<PN>\s*)?part\s+([0-9IVXLCDM]+)\s*$", re.IGNORECASE
)
_BARE_NUMBER_RE = re.compile(r"^\s*\d+\s*$")

# Maps the matched word to the WK style family used for number+title.
_OPENER_FAMILIES: list[tuple[re.Pattern, str, str]] = [
    (_CHAPTER_OPENER_RE, "CN", "CT"),
    (_SECTION_OPENER_RE, "SN", "ST"),
    (_UNIT_OPENER_RE,    "UN", "UT"),
    (_PART_OPENER_RE,    "PN", "PT"),
]


def _detect_front_matter_opener(blocks: list[dict]) -> None:
    """Mark the chapter/section/unit/part number+title openers in metadata.

    Looks at the first ``_OPENER_LOOKAHEAD`` non-empty paragraphs. The first
    one matching an opener pattern is tagged as the number block; the next
    non-empty heading-shape paragraph is the title block. Bare numeric-only
    text qualifies as a chapter number only when followed by a heading-shape
    title within the lookahead window (avoids tagging stray "12" body
    paragraphs as chapter openers).
    """
    if not blocks:
        return
    # Index of first non-empty block — that is where openers can live.
    candidate_indices = []
    for idx, b in enumerate(blocks):
        if (b.get("text") or "").strip():
            candidate_indices.append(idx)
        if len(candidate_indices) >= _OPENER_LOOKAHEAD:
            break
    if not candidate_indices:
        return

    for cand_pos, block_idx in enumerate(candidate_indices):
        text = (blocks[block_idx].get("text") or "").strip()

        matched_number_role: str | None = None
        matched_title_role: str | None = None

        for pat, num_role, title_role in _OPENER_FAMILIES:
            if pat.match(text):
                matched_number_role = num_role
                matched_title_role = title_role
                break

        if matched_number_role is None and _BARE_NUMBER_RE.match(text):
            # Bare-number opener: only valid if a heading-shape title follows
            # within the lookahead window.
            for next_pos in range(cand_pos + 1, len(candidate_indices)):
                next_idx = candidate_indices[next_pos]
                next_text = (blocks[next_idx].get("text") or "").strip()
                if _is_heading_shape(next_text):
                    matched_number_role = "CN"
                    matched_title_role = "CT"
                    break

        if matched_number_role is None:
            continue

        meta = blocks[block_idx].setdefault("metadata", {})
        meta["content_zone_role"] = matched_number_role

        # Title is the next heading-shape paragraph in the lookahead window.
        for next_pos in range(cand_pos + 1, len(candidate_indices)):
            next_idx = candidate_indices[next_pos]
            next_text = (blocks[next_idx].get("text") or "").strip()
            if _is_heading_shape(next_text):
                tmeta = blocks[next_idx].setdefault("metadata", {})
                tmeta["content_zone_role"] = matched_title_role
                break

        return  # Only one front-matter opener per document.


def _is_heading_shape(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if len(t) > 80:
        return False
    if _TERMINAL_PUNCT_RE.search(t):
        return False
    return True


# Chapter Section Title (CST) — all-caps section banners within a chapter
# that are NOT one of the recognised content-zone openers (Case Study,
# Objectives, Key Terms, Key Points, Summary, Review Questions,
# Conclusion, References) and NOT chapter/section/unit/part openers.
# Examples from feedback corpus: "STRUCTURE AND FUNCTION", "OBJECTIVE CUES",
# "CLINICAL JUDGMENT", "PRIORITY URGENT ASSESSMENT". The all-caps shape
# distinguishes CST from regular H1 headings (which use mixed case).
_CST_ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z0-9\s/&,\-]*[A-Z0-9]$")


def _is_cst_section_heading(text: str) -> bool:
    """Return True if *text* looks like a chapter section title (CST role).

    CST is an all-caps short heading that is not a known zone opener, not
    a chapter/section/unit/part opener, and not bare numeric content.
    """
    t = (text or "").strip()
    if not _is_heading_shape(t):
        return False
    if len(t) < 3:
        return False
    if not _CST_ALL_CAPS_RE.match(t):
        return False
    # Single-letter content sneaks through the regex; require >= 2 letters.
    letters = sum(1 for c in t if c.isalpha())
    if letters < 2:
        return False
    # Excluded: known zone openers (REFERENCES, SUMMARY, etc.) and front
    # matter openers (CHAPTER N, SECTION N, etc.).
    if _match_opener(t) is not None:
        return False
    for pat, _, _ in _OPENER_FAMILIES:
        if pat.match(t):
            return False
    return True


def _match_opener(text: str) -> str | None:
    """Return the zone name if *text* opens a known content zone."""
    if not _is_heading_shape(text):
        return None
    for name, pat in _ZONE_OPENERS:
        if pat.match(text):
            return name
    return None


# Zones whose name is just a finer-grained EOC subtype collapse to "EOC" for
# the overlay layer (one set of EOC-* rules covers all of them).
_EOC_SUBZONES = {"EOC_SUMMARY", "EOC_REVIEW", "EOC_CONCL"}


def detect_content_zones(blocks: list[dict]) -> list[dict]:
    """Annotate each block's metadata with a content-driven zone label.

    Mutates ``metadata['content_zone']`` and (for openers and first-body
    paragraphs) ``metadata['content_zone_role']``. Returns the same list for
    fluent use.

    Zone state is tracked linearly through the document. The first opener
    seen begins a zone. Subsequent openers replace it. Paragraphs between
    openers inherit the active zone. Paragraphs before any opener get no
    ``content_zone`` (treated as plain body).
    """
    # First, mark front-matter openers (chapter/section/unit/part number +
    # title). These are *roles*, not zone names — they live in
    # content_zone_role even before the first heading-driven zone opens.
    _detect_front_matter_opener(blocks)

    current: str | None = None
    role_for_first_body = False  # next non-opener paragraph becomes FIRST_BODY

    for b in blocks:
        meta = b.setdefault("metadata", {})
        text = b.get("text") or ""

        opener = _match_opener(text)
        if opener is not None:
            current = opener
            meta["content_zone"] = opener
            meta["content_zone_role"] = "OPENER"
            role_for_first_body = True
            continue

        # Chapter Section Title (CST): all-caps section banner inside a
        # chapter, not a recognised zone opener. Only set if no role was
        # already assigned (e.g. front-matter CT/CN takes priority).
        if not meta.get("content_zone_role") and _is_cst_section_heading(text):
            meta["content_zone_role"] = "CST"

        if current is not None:
            meta["content_zone"] = current
            if role_for_first_body:
                meta["content_zone_role"] = "FIRST_BODY"
                role_for_first_body = False

    return blocks


# ---------------------------------------------------------------------------
# Overlay rules — produce the zone-qualified tag from the validator's tag
# ---------------------------------------------------------------------------

# Family-level positional list mapping ("BL-FIRST" -> "{zone_prefix}-BL-FIRST")
_LIST_FAMILIES = ("BL", "NL", "UL")
_LIST_POSITIONS = ("FIRST", "MID", "LAST")


def _overlay_for_case_study(tag: str, role: str | None) -> str | None:
    if tag in {"TTL", "CS-TTL"} and role == "OPENER":
        return "CS-TTL"
    if tag == "H1":
        return "CS-H1"
    if tag == "TXT" and role == "FIRST_BODY":
        return "CS-TXT-FIRST"
    if tag == "TXT":
        return "CS-TXT"
    return None


def _overlay_for_eoc(tag: str, role: str | None) -> str | None:
    if tag == "H1":
        return "EOC-H1"
    if tag == "TXT" and role == "FIRST_BODY":
        return "EOC-TXT-FIRST"
    if tag == "TXT":
        return "EOC-TXT"
    if tag == "TXT-FLUSH":
        return "EOC-TXT-FLUSH"
    for fam in ("NL",):
        for pos in _LIST_POSITIONS:
            if tag == f"{fam}-{pos}":
                return f"EOC-NL-{pos}"
    return None


def _overlay_for_obj(tag: str, role: str | None) -> str | None:
    if tag == "H1" and role == "OPENER":
        return "OBJ1"
    for fam in _LIST_FAMILIES:
        for pos in _LIST_POSITIONS:
            if tag == f"{fam}-{pos}":
                return f"OBJ-{fam}-{pos}"
    return None


def _overlay_for_kt(tag: str, role: str | None) -> str | None:
    if tag == "H1" and role == "OPENER":
        return "KT1"
    for fam in _LIST_FAMILIES:
        for pos in _LIST_POSITIONS:
            if tag == f"{fam}-{pos}":
                return f"KT-{fam}-{pos}"
    return None


def _overlay_for_kp(tag: str, role: str | None) -> str | None:
    if tag == "H1" and role == "OPENER":
        return "KP1"
    for fam in ("BL", "NL"):
        for pos in _LIST_POSITIONS:
            if tag == f"{fam}-{pos}":
                return f"KP-{fam}-{pos}"
    return None


def _overlay_for_post_ref(tag: str, role: str | None) -> str | None:
    # After References, any figure/table caption that the engine produced
    # collapses to PMI.
    if tag in {"T1", "FIG-LEG", "UNFIG-LEG"}:
        return "PMI"
    return None


_OVERLAY_DISPATCH = {
    "CASE_STUDY": _overlay_for_case_study,
    "EOC_SUMMARY": _overlay_for_eoc,
    "EOC_REVIEW": _overlay_for_eoc,
    "EOC_CONCL": _overlay_for_eoc,
    "OBJ": _overlay_for_obj,
    "KT": _overlay_for_kt,
    "KP": _overlay_for_kp,
    "POST_REF": _overlay_for_post_ref,
}


# Front-matter opener role -> direct tag promotion. Applied in addition to
# the zone overlays above; preserves whatever the validator picked when
# the role isn't one of these.
_FRONT_MATTER_ROLE_TAGS = {
    "CN": "CN", "CT": "CT",
    "SN": "SN", "ST": "ST",
    "UN": "UN", "UT": "UT",
    "PN": "PN", "PT": "PT",
    # Chapter section title (e.g. "STRUCTURE AND FUNCTION", "OBJECTIVE CUES",
    # "CLINICAL JUDGMENT" — all-caps section banners within a chapter).
    "CST": "CST",
}


def apply_content_zone_overlays(
    classifications: list[dict],
    blocks: list[dict] | Iterable[dict],
    allowed_styles: Iterable[str] | None = None,
) -> list[dict]:
    """Rewrite ``classifications`` tags per content-zone overlay rules.

    Skips a rewrite when the candidate target is not in ``allowed_styles``
    (to avoid producing tags the validator would later strip).

    Both ``classifications`` and ``blocks`` are expected to be aligned by
    ``id``. ``blocks`` must already have ``metadata['content_zone']`` set
    (call :func:`detect_content_zones` first).
    """
    if not classifications:
        return classifications

    allowed: set[str] | None = (
        set(allowed_styles) if allowed_styles is not None else None
    )

    block_meta_by_id: dict = {}
    for b in blocks:
        bid = b.get("id")
        if bid is not None:
            block_meta_by_id[bid] = b.get("metadata") or {}

    block_by_id: dict = {}
    for b in blocks:
        bid = b.get("id")
        if bid is not None:
            block_by_id[bid] = b

    out: list[dict] = []
    for clf in classifications:
        tag = str(clf.get("tag") or "")
        meta = block_meta_by_id.get(clf.get("id"), {})
        zone = meta.get("content_zone")
        role = meta.get("content_zone_role")

        # Author asserted the tag inline (e.g. "<CJC-TTL>Foo"); skip both
        # front-matter promotion and zone overlay so we don't stomp on it.
        block = block_by_id.get(clf.get("id"), {})
        if block.get("_inline_tag_override"):
            out.append(clf)
            continue

        # Front-matter opener takes priority over zone overlays — chapter/
        # section/unit/part numbers and titles get a direct tag promotion
        # regardless of zone state.
        fm_target = _FRONT_MATTER_ROLE_TAGS.get(role) if role else None
        if fm_target and fm_target != tag:
            if allowed is None or fm_target in allowed:
                out.append({
                    **clf,
                    "tag": fm_target,
                    "repaired": True,
                    "repair_reason": (
                        (clf.get("repair_reason") or "") + ",content-front-matter"
                    ).lstrip(","),
                })
                continue

        if not zone or zone not in _OVERLAY_DISPATCH:
            out.append(clf)
            continue

        new_tag = _OVERLAY_DISPATCH[zone](tag, role)
        if not new_tag or new_tag == tag:
            out.append(clf)
            continue

        if allowed is not None and new_tag not in allowed:
            logger.debug(
                "content-zone-overlay: skip %s -> %s (not in allowed_styles)",
                tag, new_tag,
            )
            out.append(clf)
            continue

        out.append({
            **clf,
            "tag": new_tag,
            "repaired": True,
            "repair_reason": (
                (clf.get("repair_reason") or "") + ",content-zone-overlay"
            ).lstrip(","),
        })

    return out


# ---------------------------------------------------------------------------
# Roman-numeral outline overlay (BL-*/NL-* with roman markers -> OUT1-*)
# ---------------------------------------------------------------------------

# Strict roman numeral leading marker followed by . or ) and whitespace.
# Excludes single "I" / "i" because those are commonly the pronoun, not a
# list marker; require at least two roman characters or an unambiguous list
# context (sequence of same-class markers).
_ROMAN_MARKER_RE = re.compile(
    r"^\s*(?P<num>(?:[IVXLCDM]{2,}|[ivxlcdm]{2,}|[Ii]))[.)]\s+",
)
_UPPER_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")
_LOWER_ROMAN_RE = re.compile(r"^[ivxlcdm]+$")


def _has_roman_marker(text: str) -> str | None:
    """Return ``"upper"``, ``"lower"`` or None for the leading roman class."""
    m = _ROMAN_MARKER_RE.match(text or "")
    if not m:
        return None
    num = m.group("num")
    if _UPPER_ROMAN_RE.fullmatch(num):
        return "upper"
    if _LOWER_ROMAN_RE.fullmatch(num):
        return "lower"
    return None


_LIST_TAG_RE = re.compile(r"^(?:BL|NL|UL)-(?P<pos>FIRST|MID|LAST)$")


def apply_roman_outline_overlays(
    classifications: list[dict],
    blocks: list[dict] | Iterable[dict],
    allowed_styles: Iterable[str] | None = None,
) -> list[dict]:
    """Rewrite ``BL-*`` / ``NL-*`` / ``UL-*`` tags to ``OUT1-*`` for items
    whose text leads with a roman-numeral marker.

    A solitary ``I.`` or ``i.`` is only treated as a roman marker when at
    least one neighbour (previous or next) classification also carries a
    roman marker — guards against rewriting "I." sentences that are pronoun
    plus full-stop in body prose.

    Skips when the candidate ``OUT1-{pos}`` is not in ``allowed_styles``.
    """
    if not classifications:
        return classifications

    allowed: set[str] | None = (
        set(allowed_styles) if allowed_styles is not None else None
    )

    block_text_by_id: dict = {}
    block_by_id: dict = {}
    for b in blocks:
        bid = b.get("id")
        if bid is not None:
            block_text_by_id[bid] = b.get("text") or ""
            block_by_id[bid] = b

    # First pass — flag each classification's roman-marker class (or None).
    # Inline-tag-override blocks are excluded from outline rewriting so
    # author-asserted tags survive intact.
    flags: list[str | None] = []
    for clf in classifications:
        if block_by_id.get(clf.get("id"), {}).get("_inline_tag_override"):
            flags.append(None)
            continue
        text = block_text_by_id.get(clf.get("id"), "")
        flags.append(_has_roman_marker(text))

    # Filter ambiguous singletons. A solitary "I."/"i." with no neighbour
    # of the same class is not a list — leave it alone.
    n = len(classifications)
    for i, mark in enumerate(flags):
        if mark is None:
            continue
        text = block_text_by_id.get(classifications[i].get("id"), "")
        m = _ROMAN_MARKER_RE.match(text)
        if not m:
            continue
        num = m.group("num")
        if num not in {"I", "i"}:
            continue
        prev_class = flags[i - 1] if i - 1 >= 0 else None
        next_class = flags[i + 1] if i + 1 < n else None
        if prev_class != mark and next_class != mark:
            flags[i] = None

    out: list[dict] = []
    for clf, mark in zip(classifications, flags):
        if mark is None:
            out.append(clf)
            continue
        tag = str(clf.get("tag") or "")
        m = _LIST_TAG_RE.match(tag)
        if not m:
            out.append(clf)
            continue
        new_tag = f"OUT1-{m.group('pos')}"
        if allowed is not None and new_tag not in allowed:
            out.append(clf)
            continue
        out.append({
            **clf,
            "tag": new_tag,
            "repaired": True,
            "repair_reason": (
                (clf.get("repair_reason") or "") + ",roman-outline"
            ).lstrip(","),
        })

    return out
