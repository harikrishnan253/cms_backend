"""Style name normalization utilities."""

from __future__ import annotations

import re
import json
from pathlib import Path
from difflib import SequenceMatcher

NBSP = "\u00A0"
ALIASES_PATH = Path(__file__).resolve().parents[2] / "config" / "style_aliases.json"
ALLOWED_STYLES_PATH = Path(__file__).resolve().parents[2] / "config" / "allowed_styles.json"
VENDOR_PREFIX_RE = re.compile(r"^[A-Z]{2,}_(.+)$")
LIST_SUFFIXES = ("-FIRST", "-MID", "-LAST")
LIST_BASES = {"BL", "NL", "UL", "TBL", "TNL", "TUL"}
LIST_BASE_FAMILY_RE = re.compile(r"(?:^|[-])(BL|NL|UL|TBL|TNL|TUL)\d*$")
DEFAULT_BOX_PREFIX = "BX4"
VENDOR_BX_RE = re.compile(r"^[A-Z]{2,}[-_]?BX[-_](.+)$")
_COMPACT_BULLET_LIST_RE = re.compile(r"^BULLETLIST(\d+)(FIRST|LAST)?$")
_COMPACT_NUMBER_LIST_RE = re.compile(r"^NUMBERLIST(\d+)(FIRST|LAST)?$")
_COMPACT_UNNUMBERED_LIST_RE = re.compile(r"^(?:UNNUMBEREDLIST|UNLIST)(\d+)(FIRST|LAST)?$")

# Illegal prefixes that should be stripped (except SK_H1-SK_H6 and TBL-H1-TBL-H6 which map to TH1-TH6)
ILLEGAL_PREFIXES = ["BX4-", "NBX1-"]
SK_H_PATTERN = re.compile(r"^SK_H([1-6])$")
TBL_H_PATTERN = re.compile(r"^TBL-H([1-6])$")


def _load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    with ALIASES_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _load_allowed_styles() -> set[str]:
    if not ALLOWED_STYLES_PATH.exists():
        return set()
    try:
        with ALLOWED_STYLES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(s).strip() for s in data if s}
        return set()
    except Exception:
        return set()


_ALIASES = _load_aliases()
_ALLOWED_STYLES = _load_allowed_styles()


def _build_casestudy_lookup(allowed: set[str]) -> dict[str, str]:
    """Build a case-insensitive lookup for the CaseStudy/CaseBeg/CaseEnd style family.

    For each matching entry in *allowed* (e.g. ``CaseStudy-Dialogue``,
    ``CaseStudyTitle``), two lookup keys are stored:

    * ``style.upper()``                   — e.g. ``"CASESTUDY-DIALOGUE"``
    * ``style.upper().replace('_', '-')`` — e.g. ``"CASESTUDY-DIALOGUE-FIRST"``

    This lets :func:`normalize_style` resolve LLM outputs such as
    ``"CASESTUDY-DIALOGUE"`` or ``"CASESTUDYTITLE"`` to the correct mixed-case
    canonical form without touching the fuzzy ``_find_closest_style`` fallback.

    The function is deliberately agnostic about which canonical forms exist;
    it derives everything from the live *allowed* set so it automatically
    tracks additions to ``allowed_styles.json``.
    """
    lookup: dict[str, str] = {}
    for style in sorted(allowed):  # sorted → deterministic precedence on conflicts
        if style.lower().startswith(("casestudy", "casebeg", "caseend")):
            key_exact = style.upper()
            key_norm = key_exact.replace("_", "-")  # underscore → dash variant
            lookup.setdefault(key_exact, style)
            lookup.setdefault(key_norm, style)
    return lookup


_CASESTUDY_LOOKUP: dict[str, str] = _build_casestudy_lookup(_ALLOWED_STYLES)


def _find_closest_style(tag: str, allowed_styles: set[str] | None = None, min_similarity: float = 0.6) -> str:
    """
    Find the closest valid style to the given tag using string similarity.

    Args:
        tag: The tag to find a match for
        allowed_styles: Set of allowed styles (uses global _ALLOWED_STYLES if None)
        min_similarity: Minimum similarity threshold (0.0-1.0)

    Returns:
        The closest matching style, or "TXT" as ultimate fallback
    """
    if allowed_styles is None:
        allowed_styles = _ALLOWED_STYLES

    if not allowed_styles:
        return "TXT"

    if not tag:
        return "TXT"

    # Box-prefix family guard: NBX-* and NBX1-* tags must stay within their
    # own prefix family to prevent cross-family similarity drift
    # (e.g. NBX-BL3-FIRST drifting to FN-BL-FIRST).
    _tag_upper = tag.upper()
    for _nbx_pfx in ("NBX-", "NBX1-"):
        if _tag_upper.startswith(_nbx_pfx):
            family = {s for s in allowed_styles if s.upper().startswith(_nbx_pfx)}
            if family:
                best_fm, best_fs = None, 0.0
                for s in family:
                    r = SequenceMatcher(None, _tag_upper, s.upper()).ratio()
                    if r > best_fs:
                        best_fs, best_fm = r, s
                if best_fs >= min_similarity and best_fm:
                    return best_fm
            # No acceptable match within the NBX family — return TXT rather
            # than allowing drift into an unrelated tag family.
            return "TXT"

    best_match = None
    best_score = 0.0

    for style in allowed_styles:
        ratio = SequenceMatcher(None, tag.upper(), style.upper()).ratio()
        if ratio > best_score:
            best_score = ratio
            best_match = style

    # If best match is good enough, return it
    if best_score >= min_similarity and best_match:
        return best_match

    # Fallback hierarchy based on tag characteristics
    if tag.startswith("H") and any(c.isdigit() for c in tag):
        # Heading-like tags
        for fallback in ["H3", "H2", "H1", "TXT"]:
            if fallback in allowed_styles:
                return fallback
    elif "BL" in tag or "BULLET" in tag.upper():
        # Bullet list tags
        for fallback in ["BL-MID", "BL", "TXT"]:
            if fallback in allowed_styles:
                return fallback
    elif "NL" in tag or "NUMBER" in tag.upper():
        # Numbered list tags
        for fallback in ["NL-MID", "NL", "TXT"]:
            if fallback in allowed_styles:
                return fallback
    elif "REF" in tag:
        # Reference tags
        for fallback in ["REF-U", "REF-N", "TXT"]:
            if fallback in allowed_styles:
                return fallback
    elif "FIG" in tag:
        # Figure tags
        for fallback in ["FIG-LEG", "TXT"]:
            if fallback in allowed_styles:
                return fallback
    elif tag.startswith("T") and any(c.isdigit() for c in tag):
        # Table text tags
        for fallback in ["T", "TXT"]:
            if fallback in allowed_styles:
                return fallback

    # Ultimate fallback
    return "TXT" if "TXT" in allowed_styles else (best_match or "TXT")


def _compact_list_style_alias(text: str) -> str | None:
    """
    Corpus-driven list style normalization for publisher style names that do not
    use the canonical WK tag format, e.g. ``BulletList1first``.
    """
    compact = re.sub(r"[^A-Za-z0-9]", "", text or "").upper()
    if not compact:
        return None

    def _pos_or_mid(raw: str | None) -> str:
        return (raw or "MID").upper()

    m = _COMPACT_BULLET_LIST_RE.fullmatch(compact)
    if m:
        level = int(m.group(1))
        pos = _pos_or_mid(m.group(2))
        if level <= 1:
            return f"BL-{pos}"
        # Nested bullet variants commonly preserve level in the base (BL2/BL3...).
        return f"BL{level}-{pos if pos == 'LAST' else 'MID'}"

    m = _COMPACT_NUMBER_LIST_RE.fullmatch(compact)
    if m:
        level = int(m.group(1))
        pos = _pos_or_mid(m.group(2))
        if level <= 1:
            return f"NL-{pos}"
        # Generic nested numbered publisher styles vary by corpus (NL2 vs LL2).
        # Keep a conservative mapping until a semantic family is known.
        return f"NL-{pos if pos in {'FIRST', 'LAST'} else 'MID'}"

    m = _COMPACT_UNNUMBERED_LIST_RE.fullmatch(compact)
    if m:
        level = int(m.group(1))
        pos = _pos_or_mid(m.group(2))
        if level <= 1:
            return f"UL-{pos}"
        return f"UL-{pos if pos in {'FIRST', 'LAST'} else 'MID'}"

    return None


def normalize_style(name: str, meta: dict | None = None, enforce_membership: bool = False) -> str:
    """
    Normalize a style name by:
    1. Cleaning whitespace
    2. Stripping illegal prefixes (BX4-, NBX1-, TBL-, SK_ except SK_H1-SK_H6)
    3. Expanding aliases
    4. Optionally enforcing membership in allowed_styles.json

    Args:
        name: The style name to normalize
        meta: Optional metadata dict with box_prefix, etc.
        enforce_membership: If True, returns closest valid style if not in allowed_styles

    Returns:
        Normalized style name
    """
    if name is None:
        return ""
    text = str(name).strip().replace(NBSP, " ")
    # Collapse internal whitespace
    text = re.sub(r"\s+", " ", text)

    # CaseStudy family: normalize all-caps / mixed-separator LLM variants to the
    # canonical mixed-case style names from allowed_styles.json.
    #
    # Examples resolved here (not via fuzzy fallback):
    #   "CASESTUDY-DIALOGUE"         → "CaseStudy-Dialogue"
    #   "CASESTUDYTITLE"             → "CaseStudyTitle"
    #   "CASESTUDY-PARAFIRSTLINE-IND"→ "CaseStudy-ParaFirstLine-Ind"
    #   "CASESTUDY_DIALOGUE_FIRST"   → "CaseStudy-Dialogue_first"
    #
    # Placed BEFORE the vendor-prefix stripper so that inputs like
    # "CASESTUDY_DIALOGUE" are not split into prefix=CASESTUDY + rest=DIALOGUE.
    _text_upper = text.upper()
    if _text_upper.startswith(("CASESTUDY", "CASEBEG", "CASEEND")):
        _canon = _CASESTUDY_LOOKUP.get(_text_upper) or _CASESTUDY_LOOKUP.get(
            _text_upper.replace("_", "-")
        )
        if _canon:
            text = _canon

    # BX-style normalization (keep separate from general vendor prefixes)
    if "BX" in text:
        # Normalize underscores to dashes for BX tags
        text = text.replace("_", "-")
        bx_match = VENDOR_BX_RE.match(text)
        if bx_match:
            text = f"{DEFAULT_BOX_PREFIX}-{bx_match.group(1)}"
        elif text.startswith("BX-"):
            text = f"{DEFAULT_BOX_PREFIX}-{text[3:]}"
        text = text.upper()

    # Strip vendor prefixes like EFP_, EYU_, etc. (non-BX)
    if not re.match(r"^SK_H[1-6]$", text):
        vendor_match = VENDOR_PREFIX_RE.match(text)
        if vendor_match:
            text = vendor_match.group(1)

    # Strip illegal prefixes and map special heading patterns
    # SK_H1-SK_H6 → TH1-TH6 (table headings)
    sk_h_match = SK_H_PATTERN.match(text)
    if sk_h_match:
        text = f"TH{sk_h_match.group(1)}"
    else:
        # TBL-H1-TBL-H6 → TH1-TH6 (table headings)
        tbl_h_match = TBL_H_PATTERN.match(text)
        if tbl_h_match:
            text = f"TH{tbl_h_match.group(1)}"
        else:
            # Strip other illegal prefixes
            for prefix in ILLEGAL_PREFIXES:
                if text.startswith(prefix):
                    text = text[len(prefix):]
                    break

    # Apply explicit aliases
    text = _ALIASES.get(text, text)

    # Apply corpus-driven list name heuristics (e.g. BulletList1first -> BL-FIRST)
    # after explicit aliases so curated mappings win.
    heuristic = _compact_list_style_alias(text)
    if heuristic:
        text = heuristic

    # Apply box prefix expansion if provided
    if text.startswith("BX-"):
        box_prefix = None
        if meta and isinstance(meta, dict):
            box_prefix = meta.get("box_prefix")
        if not box_prefix:
            box_prefix = DEFAULT_BOX_PREFIX
        text = f"{box_prefix}-{text[3:]}"

    # Remove illegal list-position suffixes on non-list bases
    for suffix in LIST_SUFFIXES:
        if text.endswith(suffix):
            base = text[: -len(suffix)]
            # Preserve positional suffixes for nested list families such as
            # BL2-MID, TBL3-MID, KT-BL2-MID, BX4-NL2-MID.
            if base not in LIST_BASES and not LIST_BASE_FAMILY_RE.search(base):
                text = base
            break

    # Enforce membership in allowed_styles if requested
    if enforce_membership and _ALLOWED_STYLES:
        if text not in _ALLOWED_STYLES:
            text = _find_closest_style(text, _ALLOWED_STYLES)

    return text


def normalize_tag(tag: str, meta: dict | None = None) -> str:
    """
    Public API for normalizing tags with full membership enforcement.
    Alias for normalize_style() with enforce_membership=True.

    This function:
    - Strips illegal prefixes (BX4-, NBX1-, TBL-, SK_ except SK_H1-SK_H6 → TH1-TH6)
    - Expands aliases (T-DIR → T, CN → CH, etc.)
    - Enforces membership in allowed_styles.json
    - Returns closest valid style if not in allowed_styles

    Args:
        tag: The tag to normalize
        meta: Optional metadata dict

    Returns:
        Normalized and validated tag from allowed_styles.json
    """
    return normalize_style(tag, meta=meta, enforce_membership=True)
