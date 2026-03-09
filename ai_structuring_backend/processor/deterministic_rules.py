"""
Deterministic Classification Engine

High-confidence rule-based classification that runs BEFORE any LLM call.
Handles patterns that should NEVER go to an LLM because they are
unambiguous structural markers, zone-specific patterns, or explicit tags.

Priority tiers:
  100%  Zone markers (<front-open>, <back-close>, <ref>, etc.) → PMI
   99%  Inline heading/chapter markers (<H1>, <CN>, <CT>, <CAU>)
 95-98% Reference patterns (numbered refs, author refs, headings)
 95-97% Figure/table caption patterns
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# BULLET / NUMBERED-LIST DETECTION (shared with ListSequenceProcessor)
# =============================================================================

# Characters that mark a bullet list item (any of these at any level)
_BULLET_CHARS: frozenset[str] = frozenset({
    # Standard
    '\u25b2', '\u25b3',                     # Triangles
    '\u25cf', '\u2022', '\u00b7',           # Filled circles
    '\u25cb', '\u25e6', '\u25ef',           # Open circles
    '\u25a0', '\u25aa', '\u25a1',           # Squares
    '\u25ba', '\u25b8', '\u25b6',           # Right-pointing
    '\u25c6', '\u25c7', '\u2756',           # Diamonds
    '\u2713', '\u2714', '\u2611',           # Checkmarks
    '\u27a2', '\u27a4', '\u2192',           # Arrows
    '\u2605', '\u2606',                     # Stars
    '\u2500', '\u2013', '\u2014', '-',      # Dashes
    # Wingdings (private use area)
    '\uf0b7', '\uf0a7', '\uf0d8', '\uf076', '\uf0fc',
})

_NUMBERED_PREFIX_RE = re.compile(r'^\s*\d+\s*[.\)]\s')
_LETTERED_PREFIX_RE = re.compile(r'^\s*[a-z]\s*[.\)]\s', re.IGNORECASE)


# =============================================================================
# COMPILED REGEX PATTERNS
# =============================================================================

# --- Zone markers (100% → PMI) ---
_ZONE_MARKER_RE = re.compile(
    r"^\s*<\s*/?(?:"
    r"front-open|front-close|"
    r"body-open|body-close|"
    r"back-open|back-close|"
    r"float-open|float-close|"
    r"metadata|"
    r"/metadata"
    r")\s*>\s*$",
    re.IGNORECASE,
)

# <ref> or <REF> at start of line (may have trailing text like "References")
_REF_MARKER_RE = re.compile(r"^\s*<\s*/?ref\s*>", re.IGNORECASE)

# Generic box open/close markers → PMI
_BOX_MARKER_RE = re.compile(
    r"^\s*<\s*/?(?:"
    r"note|clinical\s*pearl|red\s*flag|box|tip|example|warning|alert|"
    r"case\s*study|reflection|discussion|practice|key\s*point|"
    r"important|remember|unnumbered\s*box"
    r")\s*>\s*$",
    re.IGNORECASE,
)

# --- Inline heading markers (99%) ---
_INLINE_H_RE = re.compile(r"^\s*<H([1-6])>(.*)$", re.IGNORECASE)

# --- Chapter metadata markers (99%) ---
_CN_RE = re.compile(r"^\s*(?:<CN>)?\s*chapter\s+(\d+|[IVXLCDM]+)\s*$", re.IGNORECASE)
_CT_RE = re.compile(r"^\s*<CT>(.+)$", re.IGNORECASE)
_CAU_RE = re.compile(r"^\s*<CAU>(.+)$", re.IGNORECASE)

# --- Reference heading patterns (95-98%) ---
_REF_HEADING_RE = re.compile(
    r"^\s*(?:<ref>\s*)?(?:references|bibliography|suggested\s+readings?"
    r"|further\s+reading|works\s+cited|annotated\s+bibliography)\s*$",
    re.IGNORECASE,
)
_SR_HEADING_RE = re.compile(
    r"^\s*(?:suggested\s+readings?|further\s+reading)\s*$",
    re.IGNORECASE,
)

# Numbered reference: "1. Author..." or "[1] Author..." or "(1) Author..."
_REF_NUMBERED_RE = re.compile(
    r"^\s*(?:\[\s*\d+\s*\]|\(\s*\d+\s*\)|\d+\s*[\.\)])\s+[A-Z]"
)

# Author-style reference: "LastName AB, ..."
_REF_AUTHOR_RE = re.compile(
    r"^\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,?\s+[A-Z]{1,3}[,.]"
)

# Journal/year markers inside text
_HAS_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_HAS_JOURNAL_RE = re.compile(
    r"(?:et\s+al\.?|doi:|https?://|J\s+\w+|Clin\s+|Ann\s+|Am\s+J\s+)", re.IGNORECASE
)

# --- Figure / table patterns (95-97%) ---
_FIG_CAPTION_RE = re.compile(
    r"^\s*(?:<fn>|<ft>)?\s*(?:e-)?(?:figure|fig\.?)\s+\d", re.IGNORECASE
)
_TBL_CAPTION_RE = re.compile(
    r"^\s*(?:<tn>|<tt>|<tab\w*>)?\s*(?:e-)?(?:table|tab\.?)\s+\d", re.IGNORECASE
)
_FIG_LEGEND_HEADING_RE = re.compile(
    r"^\s*figure\s+legends?\s*$", re.IGNORECASE
)

# Table footnote: lowercase letter + punctuation in a short line
_TFN_LETTER_RE = re.compile(r"^\s*[a-z][.)]\s+\S")
# Abbreviation block: "CAPS, text; CAPS, text" or all-caps definitions
_TFN_ABBREV_RE = re.compile(
    r"^\s*(?:[A-Z]{2,},\s+[a-z].*?;\s*){1,}[A-Z]{2,},\s+[a-z]"
)

# Source lines
_SOURCE_LINE_RE = re.compile(
    r"^\s*(?:source|adapted\s+from|reproduced\s+from|data\s+from|courtesy\s+of)\s*:",
    re.IGNORECASE,
)


# =============================================================================
# ZONE STATE TRACKER
# =============================================================================

class _ZoneTracker:
    """
    Lightweight zone tracker that mirrors ingestion zones but is driven
    purely by the explicit structural markers in the text stream.
    """

    def __init__(self):
        self.zone: str = "BODY"
        self.in_float: bool = False

    def update(self, text: str) -> None:
        low = text.strip().lower()

        if "<front-open>" in low:
            self.zone = "FRONT_MATTER"
        elif "<body-open>" in low:
            self.zone = "BODY"
        elif "<back-open>" in low:
            self.zone = "BACK_MATTER"
        elif _REF_MARKER_RE.match(text):
            self.zone = "BACK_MATTER"
        elif "<float-open>" in low:
            self.in_float = True
        elif "<float-close>" in low:
            self.in_float = False

        # Heading markers inside back matter don't switch zone
        # but reference headings confirm we're in back matter
        if _REF_HEADING_RE.match(text):
            self.zone = "BACK_MATTER"

    @property
    def effective_zone(self) -> str:
        if self.in_float:
            return "FLOAT"
        return self.zone


# =============================================================================
# SINGLE-PARAGRAPH CLASSIFICATION
# =============================================================================

def _classify_one(
    text: str,
    meta: Dict,
    zone: str,
    in_float: bool,
) -> Optional[Dict]:
    """
    Apply deterministic rules to a single paragraph.

    Returns a result dict or None if no rule matches.
    """
    stripped = text.strip()
    low = stripped.lower()

    # ── 1. ZONE MARKERS → PMI (100%) ──────────────────────────────────────
    if _ZONE_MARKER_RE.match(text):
        return _result("PMI", 100, "zone_marker", f"Zone marker: {stripped[:40]}")

    if _REF_MARKER_RE.match(text):
        # <ref>References → still PMI (the marker itself is structural)
        return _result("PMI", 100, "zone_marker", f"Reference marker: {stripped[:40]}")

    if _BOX_MARKER_RE.match(text):
        return _result("PMI", 100, "box_marker", f"Box marker: {stripped[:40]}")

    # ── 2. CHAPTER METADATA (99%) ─────────────────────────────────────────
    if _CN_RE.match(text):
        return _result("CN", 99, "chapter_marker", "Chapter number marker")

    if _CT_RE.match(text):
        return _result("CT", 99, "chapter_marker", "Chapter title marker")

    if _CAU_RE.match(text):
        return _result("CAU", 99, "chapter_marker", "Chapter author marker")

    # ── 3. HEADING MARKERS (99%) ──────────────────────────────────────────
    m = _INLINE_H_RE.match(text)
    if m:
        level = int(m.group(1))
        tag = f"H{level}"
        return _result(tag, 99, "heading_marker", f"Inline <H{level}> marker")

    # ── 4. REFERENCE PATTERNS (95-98%) ────────────────────────────────────
    ctx_zone = meta.get("context_zone", zone)

    if _FIG_LEGEND_HEADING_RE.match(text):
        return _result("H1", 96, "figure_legend_heading", "Figure Legends heading")

    # Reference/SR heading
    if _REF_HEADING_RE.match(text):
        if _SR_HEADING_RE.match(text):
            return _result("SRH1", 98, "ref_heading", "Suggested readings heading")
        return _result("REFH1", 98, "ref_heading", "References heading")

    # Only apply numbered-ref / author-ref rules inside BACK_MATTER
    if ctx_zone == "BACK_MATTER":
        if _REF_NUMBERED_RE.match(text):
            return _result("REF-N", 96, "ref_numbered", "Numbered reference entry")

        if _REF_AUTHOR_RE.match(text) and _HAS_YEAR_RE.search(text):
            return _result("REF-U", 95, "ref_author", "Author-style reference entry")

        # Generic back-matter text with journal/year signals → SR
        if _HAS_YEAR_RE.search(text) and _HAS_JOURNAL_RE.search(text):
            if len(stripped) > 30:
                return _result("SR", 95, "ref_generic", "Reference-like text in back matter")

    # ── 5. FIGURE / TABLE PATTERNS (95-97%) ───────────────────────────────
    if _FIG_CAPTION_RE.match(text):
        return _result("FIG-LEG", 97, "fig_caption", "Figure caption pattern")

    if _TBL_CAPTION_RE.match(text):
        # Table caption lines don't have a TBL-LEG tag in this system,
        # so use the standard table title tag T1
        return _result("T1", 97, "tbl_caption", "Table caption pattern")

    # Table footnotes: only when inside TABLE zone or FLOAT
    if ctx_zone == "TABLE" or in_float:
        if _TFN_LETTER_RE.match(text):
            return _result("TFN", 95, "tbl_footnote", "Table footnote (letter prefix)")

        if _TFN_ABBREV_RE.match(text):
            return _result("TFN", 95, "tbl_footnote", "Abbreviation block")

    # Source lines (any zone)
    if _SOURCE_LINE_RE.match(text):
        if ctx_zone == "TABLE" or in_float:
            return _result("TSN", 96, "source_line", "Table source note")
        return _result("FIG-SRC", 95, "source_line", "Figure source line")

    # ── No match → needs LLM ─────────────────────────────────────────────
    return None


def _result(tag: str, confidence: int, source: str, reasoning: str) -> Dict:
    return {
        "tag": tag,
        "confidence": confidence,
        "source": f"deterministic:{source}",
        "reasoning": reasoning,
        "rule_based": True,
    }


# =============================================================================
# MAIN PUBLIC API
# =============================================================================

def apply_deterministic_rules(
    paragraphs: List[Dict],
) -> Dict[str, object]:
    """
    Classify paragraphs using deterministic high-confidence rules.

    Args:
        paragraphs: List of paragraph dicts with keys:
            id, text, metadata (including context_zone)

    Returns:
        Dictionary with:
            deterministic: list of {id, tag, confidence, source, reasoning, rule_based}
            llm_queue: list of paragraph dicts that need LLM classification
            zone_map: dict of {para_id: effective_zone}
    """
    tracker = _ZoneTracker()
    deterministic: List[Dict] = []
    llm_queue: List[Dict] = []
    zone_map: Dict[int, str] = {}

    for para in paragraphs:
        para_id = para.get("id")
        text = para.get("text", "")
        meta = para.get("metadata", {})

        # Update zone tracker from text markers
        tracker.update(text)

        # Use ingestion zone if available, otherwise tracker zone
        effective_zone = meta.get("context_zone", tracker.effective_zone)
        zone_map[para_id] = effective_zone

        result = _classify_one(text, meta, tracker.zone, tracker.in_float)

        if result is not None:
            result["id"] = para_id
            deterministic.append(result)
        else:
            llm_queue.append(para)

    logger.info(
        f"Deterministic rules: {len(deterministic)} classified, "
        f"{len(llm_queue)} queued for LLM "
        f"({len(deterministic)}/{len(paragraphs)} = "
        f"{len(deterministic)/max(len(paragraphs),1)*100:.1f}% coverage)"
    )

    return {
        "deterministic": deterministic,
        "llm_queue": llm_queue,
        "zone_map": zone_map,
    }


# =============================================================================
# LIST SEQUENCE PROCESSOR — FIRST / MID / LAST position fixer
# =============================================================================

# Tag families whose position suffix can be rewritten.
# Maps the base prefix (without position) to itself for quick membership test.
_LIST_TAG_FAMILIES: tuple[str, ...] = (
    # Body lists
    "BL-", "BL2-", "BL3-",
    "NL-", "NL2-", "NL3-",
    "UL-",
    # Table lists
    "TBL-", "TBL2-", "TBL3-", "TBL4-",
    "TNL-", "TNL2-", "TNL3-",
    "TUL-",
    # Box lists  (NBX-, BX1-, BX2-, BX3-, …)
    "NBX-BL-", "NBX-NL-", "NBX-BL2-", "NBX-NL2-",
    "BX1-BL-", "BX1-NL-", "BX1-BL2-", "BX1-NL2-",
    "BX2-BL-", "BX2-NL-", "BX2-BL2-", "BX2-NL2-",
    "BX3-BL-", "BX3-NL-", "BX3-BL2-", "BX3-NL2-",
    # EOC lists
    "EOC-NL-", "EOC-BL-",
)

_POSITION_RE = re.compile(r"-(FIRST|MID|LAST)$")


def _split_tag_position(tag: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Split a list tag into (prefix_with_dash, position).

    Returns (None, None) if *tag* is not a recognised list-position tag.

    Examples:
        "BL-MID"      → ("BL-", "MID")
        "BL2-FIRST"   → ("BL2-", "FIRST")
        "NBX-BL-LAST" → ("NBX-BL-", "LAST")
        "H1"          → (None, None)
    """
    m = _POSITION_RE.search(tag)
    if not m:
        return None, None
    prefix = tag[: m.start() + 1]   # includes the trailing "-"
    position = m.group(1)
    return prefix, position


def _is_list_item(text: str, meta: Dict) -> bool:
    """
    Determine whether a paragraph is a list item using metadata and text.
    """
    # Fast path: metadata flags set by ingestion / list_hierarchy_detector
    if meta.get("has_bullet") or meta.get("has_numbering") or meta.get("has_xml_list"):
        return True
    if meta.get("is_list"):
        return True

    # Text-based detection
    stripped = text.lstrip()
    if not stripped:
        return False

    # First-char bullet check
    if stripped[0] in _BULLET_CHARS:
        return True

    # "o " pattern (Word circle bullet)
    if len(stripped) > 1 and stripped[0] == 'o' and stripped[1] in ' \t':
        return True

    # Numbered / lettered prefix
    if _NUMBERED_PREFIX_RE.match(stripped):
        return True
    if _LETTERED_PREFIX_RE.match(stripped):
        return True

    return False


@dataclass
class _ListSequence:
    """A contiguous run of list items sharing the same tag-family prefix."""
    start: int                          # index into the items list
    end: int                            # exclusive
    prefix: str                         # e.g. "BL-"
    ids: List[int] = field(default_factory=list)


class ListSequenceProcessor:
    """
    Groups consecutive list items into sequences and assigns
    FIRST / MID / LAST positions.

    Usage::

        proc = ListSequenceProcessor()
        fixed = proc.process(paragraphs, classifications)

    *paragraphs* is the list of ``{id, text, metadata}`` dicts.
    *classifications* is the list of ``{id, tag, confidence, …}`` dicts
    (modified **in-place** and also returned).
    """

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def process(
        self,
        paragraphs: List[Dict],
        classifications: List[Dict],
    ) -> List[Dict]:
        """
        Identify list sequences and rewrite FIRST/MID/LAST positions.

        Returns *classifications* (mutated in-place for convenience).
        """
        para_by_id: Dict[int, Dict] = {p["id"]: p for p in paragraphs}
        clf_by_id: Dict[int, Dict] = {c["id"]: c for c in classifications}

        # Ordered ids as they appear in classifications
        ordered_ids: List[int] = [c["id"] for c in classifications]

        sequences = self._find_sequences(ordered_ids, para_by_id, clf_by_id)
        self._apply_positions(sequences, clf_by_id)

        return classifications

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _find_sequences(
        self,
        ordered_ids: List[int],
        para_by_id: Dict[int, Dict],
        clf_by_id: Dict[int, Dict],
    ) -> List[_ListSequence]:
        """
        Walk the classification list and group consecutive list items
        that share the same tag-family prefix into sequences.
        """
        sequences: List[_ListSequence] = []
        current: Optional[_ListSequence] = None

        for idx, pid in enumerate(ordered_ids):
            clf = clf_by_id.get(pid)
            para = para_by_id.get(pid, {})
            if clf is None:
                # gap → close any open sequence
                if current is not None:
                    sequences.append(current)
                    current = None
                continue

            tag = clf.get("tag", "")
            text = para.get("text", "")
            meta = para.get("metadata", {})

            prefix, _pos = _split_tag_position(tag)

            is_list = prefix is not None or _is_list_item(text, meta)

            if is_list and prefix is not None:
                # Same family as current sequence?
                if current is not None and current.prefix == prefix:
                    current.end = idx + 1
                    current.ids.append(pid)
                else:
                    # Close previous, start new
                    if current is not None:
                        sequences.append(current)
                    current = _ListSequence(
                        start=idx, end=idx + 1, prefix=prefix, ids=[pid]
                    )
            else:
                # Not a list-position tag → close any open sequence
                if current is not None:
                    sequences.append(current)
                    current = None

        # Don't forget a trailing open sequence
        if current is not None:
            sequences.append(current)

        return sequences

    def _apply_positions(
        self,
        sequences: List[_ListSequence],
        clf_by_id: Dict[int, Dict],
    ) -> None:
        """Rewrite tags in *clf_by_id* with correct FIRST/MID/LAST."""
        for seq in sequences:
            n = len(seq.ids)
            for i, pid in enumerate(seq.ids):
                clf = clf_by_id.get(pid)
                if clf is None:
                    continue

                if n == 1:
                    desired_pos = "FIRST"
                    clf["list_single"] = True
                elif i == 0:
                    desired_pos = "FIRST"
                elif i == n - 1:
                    desired_pos = "LAST"
                else:
                    desired_pos = "MID"

                new_tag = f"{seq.prefix}{desired_pos}"
                old_tag = clf["tag"]
                if new_tag != old_tag:
                    clf["tag"] = new_tag
                    clf["position_corrected"] = True
                    clf.setdefault("repair_reason", "")
                    if clf["repair_reason"]:
                        clf["repair_reason"] += ","
                    clf["repair_reason"] += "list-sequence-position"
