"""
Post-reconstruction enforcement of table-title house rules.

Opens the reconstructed DOCX, detects tables via python-docx body
structure, and enforces strict adjacency / styling rules for
table titles and captions.

Runs AFTER document reconstruction and BEFORE the structure guard
(Stage 5.25 in the pipeline).

House Rules
-----------
1. A table title must immediately precede the table object.
2. No blank paragraph is allowed between title and table.
3. Valid title patterns: "Table X: <text>" or "Table X.<text>"
4. Title style must be canonical T1 (TABLE_TITLE).
5. Multiple candidate captions above a table: closest valid → T1,
   others → TXT.
6. Placeholder patterns like "<TAB5.1>" → T1 if directly preceding
   a table; untouched otherwise.
7. Never create or delete table content.
8. Never move a table.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches
from docx.enum.style import WD_STYLE_TYPE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Strict title: "Table 1: Title" or "Table 1.Title" or "Table 1.2: Title"
_TITLE_STRICT_RE = re.compile(
    r"^Table\s+\d+(?:\.\d+)?\s*[:.]\s*\S",
    re.IGNORECASE,
)

# Broad title: "Table 1" / "Table 1.2" (possibly followed by more text)
_TITLE_BROAD_RE = re.compile(
    r"^Table\s+\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)

# Placeholder: "<TAB5.1>" or "<INSERT TAB 5.1>"
_PLACEHOLDER_RE = re.compile(
    r"^<(?:INSERT\s+)?TAB\s*\d+(?:\.\d+)?>",
    re.IGNORECASE,
)


def _heading_level_for_style_name(style_name: str) -> int | None:
    """Return Word heading/title semantic level for a style name."""
    if not style_name:
        return None
    if style_name == "Title":
        return 0
    match = re.fullmatch(r"Heading (\d)", style_name)
    if match:
        return int(match.group(1))
    return None

# ---------------------------------------------------------------------------
# Style definitions (mirrored from reconstruction.STYLE_DEFINITIONS)
# ---------------------------------------------------------------------------

_T1_STYLE_DEF = {
    "font_size": 10,
    "bold": True,
    "space_before": 6,
    "space_after": 2,
}

_TXT_STYLE_DEF = {
    "font_size": 11,
    "first_line_indent": 0.5,
    "space_after": 6,
}

_PMI_STYLE_DEF = {
    "font_size": 9,
    "italic": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enforce_table_title_house_rules(docx_path: str) -> dict:
    """Enforce table-title house rules on a reconstructed DOCX.

    Opens *docx_path*, iterates body elements in document order to
    locate ``<w:tbl>`` elements, then enforces adjacency and styling
    rules on the paragraphs immediately above each table.

    The file is modified **in place**.

    Parameters
    ----------
    docx_path : str
        Path to the reconstructed DOCX file.

    Returns
    -------
    dict
        Enforcement metrics::

            {
                "tables": int,
                "titles_fixed": int,
                "blank_lines_removed": int,
                "demoted_to_txt": int,
                "placeholders_converted": int,
            }
    """
    doc = Document(docx_path)
    body = doc.element.body

    metrics = {
        "tables": 0,
        "titles_fixed": 0,
        "blank_lines_removed": 0,
        "demoted_to_txt": 0,
        "placeholders_converted": 0,
    }

    # Collect body children in document order.
    elements = list(body)

    # Find table positions.
    table_positions: list[int] = []
    for i, el in enumerate(elements):
        if el.tag == qn("w:tbl"):
            table_positions.append(i)
            metrics["tables"] += 1

    if not table_positions:
        logger.debug("table-title-enforcement: no tables found in %s", docx_path)
        return metrics

    # Ensure T1 / TXT / PMI styles exist in the document.
    _ensure_style(doc, "T1", _T1_STYLE_DEF)
    _ensure_style(doc, "TXT", _TXT_STYLE_DEF)
    _ensure_style(doc, "PMI", _PMI_STYLE_DEF)

    # Process each table (reverse order not needed since we don't
    # add/remove elements, only modify styles).
    for tbl_pos in table_positions:
        _enforce_for_table(elements, tbl_pos, doc, metrics)

    doc.save(docx_path)

    logger.info(
        "TABLE_TITLE_ENFORCEMENT tables=%d titles_fixed=%d "
        "blank_lines_removed=%d demoted_to_txt=%d "
        "placeholders_converted=%d",
        metrics["tables"],
        metrics["titles_fixed"],
        metrics["blank_lines_removed"],
        metrics["demoted_to_txt"],
        metrics["placeholders_converted"],
    )

    return metrics


# ---------------------------------------------------------------------------
# Per-table enforcement
# ---------------------------------------------------------------------------

_MAX_LOOKBACK = 5  # Maximum paragraphs to scan above a table


def _enforce_for_table(
    elements: list,
    tbl_pos: int,
    doc: Document,
    metrics: dict,
) -> None:
    """Apply house rules to the paragraphs immediately above one table."""

    candidates: list[tuple[int, str, str]] = []   # (pos, text, kind)
    blank_positions: list[int] = []
    looked = 0
    i = tbl_pos - 1

    while i >= 0 and looked < _MAX_LOOKBACK:
        el = elements[i]

        if el.tag == qn("w:p"):
            text = _para_text(el).strip()
            if not text:
                blank_positions.append(i)
            elif _TITLE_STRICT_RE.match(text) or _TITLE_BROAD_RE.match(text):
                candidates.append((i, text, "title"))
            elif _PLACEHOLDER_RE.match(text):
                candidates.append((i, text, "placeholder"))
            else:
                # Hit a non-blank, non-title paragraph → stop.
                break
            looked += 1
        elif el.tag == qn("w:tbl"):
            # Hit another table → stop.
            break
        else:
            # Other element (section break, etc.) → stop.
            break
        i -= 1

    if not candidates:
        return

    # Rule 5: Closest valid candidate wins (highest position index).
    candidates.sort(key=lambda c: c[0], reverse=True)
    closest_pos, closest_text, closest_kind = candidates[0]

    # --- Rule 2: Collapse blank paragraphs between title and table ---
    for bp in blank_positions:
        if closest_pos < bp < tbl_pos:
            _apply_style(elements[bp], doc, "PMI")
            metrics["blank_lines_removed"] += 1

    # --- Rules 3, 4, 6: Style the closest candidate as T1 ---
    _apply_style(elements[closest_pos], doc, "T1")
    metrics["titles_fixed"] += 1

    if closest_kind == "placeholder":
        metrics["placeholders_converted"] += 1

    # --- Rule 5: Demote remaining candidates to TXT ---
    for pos, _text, _kind in candidates[1:]:
        _apply_style(elements[pos], doc, "TXT")
        metrics["demoted_to_txt"] += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _para_text(p_element) -> str:
    """Extract concatenated text from a ``<w:p>`` XML element."""
    return "".join(
        t.text for t in p_element.iter(qn("w:t")) if t.text
    )


def _para_style_id(p_element) -> str | None:
    """Read the style ID from ``<w:pPr><w:pStyle w:val='...'/>``."""
    pPr = p_element.find(qn("w:pPr"))
    if pPr is None:
        return None
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is None:
        return None
    return pStyle.get(qn("w:val"))


def _style_chain_names(style_obj) -> list[str]:
    """Return style names for ``style_obj`` and its base-style chain."""
    names: list[str] = []
    seen = set()
    current = style_obj
    while current is not None:
        name = getattr(current, "name", "") or ""
        if name and name not in seen:
            names.append(name)
            seen.add(name)
        current = getattr(current, "base_style", None)
    return names


def _find_style_by_id(doc: Document, style_id: str | None):
    if not style_id:
        return None
    for style in doc.styles:
        if getattr(style, "style_id", None) == style_id:
            return style
    return None


def _element_heading_level(p_element, doc: Document) -> int | None:
    """Return heading/title semantic level for a body paragraph XML element."""
    style_obj = _find_style_by_id(doc, _para_style_id(p_element))
    for style_name in _style_chain_names(style_obj):
        level = _heading_level_for_style_name(style_name)
        if level is not None:
            return level
    return None


def _set_outline_level(p_element, level: int) -> None:
    """Set paragraph-level ``w:outlineLvl`` (0-based) on a ``<w:p>`` element."""
    pPr = p_element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_element.insert(0, pPr)

    outline = pPr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        pPr.append(outline)
    outline.set(qn("w:val"), str(level))


def _apply_style(p_element, doc: Document, style_name: str) -> None:
    """Set the Word paragraph style on a ``<w:p>`` element via XML.

    Sets ``<w:pPr><w:pStyle w:val="…"/></w:pPr>`` directly,
    avoiding the need for a full ``Paragraph`` wrapper (which
    requires a parent with a ``.part`` attribute).
    """
    # Structural safety: this post-reconstruction stage must not change heading
    # semantics. Exception: source "Title" (heading_level=0) table captions may
    # be canonicalized to T1 if we preserve title-equivalent semantics via
    # paragraph-level outlineLvl.
    source_style_id = _para_style_id(p_element)
    source_heading_level = _element_heading_level(p_element, doc)
    # Fallback: built-in Title style can be present by style ID even if style
    # object lookup fails in python-docx for a template-specific style table.
    if source_heading_level is None and source_style_id == "Title":
        source_heading_level = 0
    if source_heading_level is not None and source_heading_level != 0:
        logger.debug(
            "table-title-enforcement: preserving source heading semantics; skip style '%s' for text=%r",
            style_name,
            _para_text(p_element)[:120],
        )
        return

    # Ensure the target style exists in the document.
    try:
        style_obj = doc.styles[style_name]
        style_id = style_obj.style_id
    except KeyError:
        logger.warning(
            "table-title-enforcement: style '%s' not found; skipping",
            style_name,
        )
        return

    pPr = p_element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_element.insert(0, pPr)

    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is None:
        pStyle = OxmlElement("w:pStyle")
        pPr.insert(0, pStyle)

    pStyle.set(qn("w:val"), style_id)

    # Preserve Title semantics when canonicalizing ``Title`` -> ``T1``.
    if source_heading_level == 0:
        _set_outline_level(p_element, 0)


def _ensure_style(doc: Document, name: str, style_def: dict) -> None:
    """Create a paragraph style if it doesn't already exist."""
    try:
        _ = doc.styles[name]
        return  # Already exists.
    except KeyError:
        pass

    try:
        new_style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        new_style.base_style = doc.styles["Normal"]

        font = new_style.font
        font.size = Pt(style_def.get("font_size", 11))
        font.bold = style_def.get("bold", False)
        font.italic = style_def.get("italic", False)

        pf = new_style.paragraph_format
        if "space_before" in style_def:
            pf.space_before = Pt(style_def["space_before"])
        if "space_after" in style_def:
            pf.space_after = Pt(style_def["space_after"])
        if "first_line_indent" in style_def:
            pf.first_line_indent = Inches(style_def["first_line_indent"])

        logger.debug("table-title-enforcement: created style '%s'", name)
    except Exception as exc:
        logger.warning(
            "table-title-enforcement: could not create style '%s': %s",
            name,
            exc,
        )
