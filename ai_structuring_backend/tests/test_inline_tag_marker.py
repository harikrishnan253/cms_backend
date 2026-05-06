"""Tests for the generic inline tag marker mechanism.

Covers detection of ``<TAG>content`` patterns at paragraph start, the
pre-classification lock, and integration with overlays so author
assertions survive the full pipeline.
"""

from __future__ import annotations

from processor.inline_tag_marker import (
    INLINE_TAG_MARKER_RE,
    extract_inline_tag,
    lock_inline_tag_blocks,
)
from processor.content_zones import (
    apply_content_zone_overlays,
    apply_roman_outline_overlays,
)


# A minimal allowed-styles set covering the cases we exercise. The real
# config has ~1450 entries; using a small fixture keeps tests fast and
# obvious.
ALLOWED = {
    "H1", "H2", "H3", "H4", "H5", "H6",
    "T", "T2", "T3",
    "TBL-MID", "TNL-MID", "TUL-MID",
    "CJC-TTL", "CJC-NN-TTL", "CJC-NN-TXT-FIRST",
    "UNT-T2", "UNT-T3", "UNT-H1",
    "NBX-TTL", "NBX-BL-FIRST",
    "BX1-CS", "BX2-SA",
    "KP-BX", "KP-BL-FIRST",
    "CTC", "CTC-H1",
    "CST",
    "RQ1", "RQ-NL-FIRST",
    "FIG-LEG", "REF-H1",
    "TXT", "TXT-FLUSH",
}


# ---------------------------------------------------------------------------
# extract_inline_tag — detection
# ---------------------------------------------------------------------------


def test_extract_h2_marker():
    tag, marker, rest = extract_inline_tag("<H2>Pain Control Theories", ALLOWED)
    assert tag == "H2"
    assert marker == "<H2>"
    assert rest == "Pain Control Theories"


def test_extract_t2_marker():
    tag, marker, rest = extract_inline_tag("<T2>System", ALLOWED)
    assert tag == "T2"
    assert marker == "<T2>"
    assert rest == "System"


def test_extract_cjc_ttl_marker():
    tag, marker, rest = extract_inline_tag("<CJC-TTL>Clinical Judgment Case", ALLOWED)
    assert tag == "CJC-TTL"
    assert marker == "<CJC-TTL>"
    assert rest == "Clinical Judgment Case"


def test_extract_tbl_mid_marker():
    tag, marker, rest = extract_inline_tag("<TBL-MID>1. Pain: An unpleasant", ALLOWED)
    assert tag == "TBL-MID"
    assert marker == "<TBL-MID>"
    assert rest == "1. Pain: An unpleasant"


def test_extract_unt_t3_marker():
    tag, marker, rest = extract_inline_tag("<UNT-T3>Onset/Duration", ALLOWED)
    assert tag == "UNT-T3"
    assert rest == "Onset/Duration"


def test_extract_cst_marker():
    tag, _, rest = extract_inline_tag("<CST>STRUCTURE AND FUNCTION", ALLOWED)
    assert tag == "CST"
    assert rest == "STRUCTURE AND FUNCTION"


def test_extract_lowercase_marker_canonicalises():
    """Author writes lowercase; engine canonicalises to allowed-styles form."""
    tag, _, rest = extract_inline_tag("<h2>Foo", ALLOWED)
    assert tag == "H2"
    assert rest == "Foo"


def test_extract_marker_not_in_allowed_no_match():
    tag, marker, rest = extract_inline_tag("<NOT-A-REAL-TAG>Foo", ALLOWED)
    assert tag is None
    assert marker == ""
    assert rest == "<NOT-A-REAL-TAG>Foo"


def test_extract_marker_only_no_match():
    """Bare ``<TAG>`` (no following content) is the marker_lock module's
    territory; this module declines so it gets PMI'd."""
    tag, _, rest = extract_inline_tag("<CJC-BX>", ALLOWED)
    assert tag is None
    assert rest == "<CJC-BX>"


def test_extract_closing_marker_no_match():
    tag, _, _ = extract_inline_tag("</CJC-BX>", ALLOWED)
    assert tag is None


def test_extract_marker_mid_paragraph_no_match():
    """Marker not at paragraph start is content text, not an override."""
    tag, _, _ = extract_inline_tag("Some prose then <H1> mid-paragraph", ALLOWED)
    assert tag is None


def test_extract_empty_text():
    tag, _, _ = extract_inline_tag("", ALLOWED)
    assert tag is None


def test_extract_marker_with_leading_whitespace():
    tag, _, rest = extract_inline_tag("   <H2>Foo", ALLOWED)
    assert tag == "H2"
    assert rest == "Foo"


# ---------------------------------------------------------------------------
# lock_inline_tag_blocks — pre-classification lock
# ---------------------------------------------------------------------------


def _make_block(bid: str, text: str) -> dict:
    return {"id": bid, "text": text, "metadata": {}}


def test_lock_sets_skip_llm_and_allowed_styles():
    blocks = [_make_block("p1", "<CJC-TTL>Clinical Judgment Case")]
    out = lock_inline_tag_blocks(blocks, ALLOWED)
    b = out[0]
    assert b["lock_style"] is True
    assert b["allowed_styles"] == ["CJC-TTL"]
    assert b["skip_llm"] is True
    assert b["_inline_tag_override"] == "CJC-TTL"
    assert b["_inline_tag_marker"] == "<CJC-TTL>"


def test_lock_skips_unknown_tag():
    blocks = [_make_block("p1", "<NOT-REAL>Foo")]
    out = lock_inline_tag_blocks(blocks, ALLOWED)
    assert "lock_style" not in out[0]
    assert "skip_llm" not in out[0]


def test_lock_skips_marker_only():
    """<CJC-BX> alone is marker-only — left for marker_lock to PMI."""
    blocks = [_make_block("p1", "<CJC-BX>")]
    out = lock_inline_tag_blocks(blocks, ALLOWED)
    assert "_inline_tag_override" not in out[0]


def test_lock_respects_existing_lock():
    """If marker_lock already locked the block to PMI, don't stomp it."""
    block = _make_block("p1", "<CJC-TTL>Foo")
    block["lock_style"] = True
    block["allowed_styles"] = ["PMI"]
    block["skip_llm"] = True
    out = lock_inline_tag_blocks([block], ALLOWED)
    # The earlier lock wins; we don't override.
    assert out[0]["allowed_styles"] == ["PMI"]
    assert "_inline_tag_override" not in out[0]


def test_lock_handles_empty_blocks():
    out = lock_inline_tag_blocks([], ALLOWED)
    assert out == []


def test_lock_idempotent():
    """Running the lock twice yields the same result."""
    blocks = [_make_block("p1", "<T2>System"), _make_block("p2", "<H1>Foo")]
    once = lock_inline_tag_blocks(blocks, ALLOWED)
    twice = lock_inline_tag_blocks(once, ALLOWED)
    assert once[0]["_inline_tag_override"] == twice[0]["_inline_tag_override"] == "T2"
    assert once[1]["_inline_tag_override"] == twice[1]["_inline_tag_override"] == "H1"


# ---------------------------------------------------------------------------
# Overlay guards — author assertion survives content-zone + roman overlays
# ---------------------------------------------------------------------------


def test_content_zone_overlay_skips_inline_override():
    """A block with an inline override should not get its tag rewritten by
    the zone overlay even if the block sits inside a recognised zone."""
    blocks = [
        {
            "id": "p1",
            "text": "<CJC-TTL>Clinical Judgment Case",
            "metadata": {
                "content_zone": "CASE_STUDY",
                "content_zone_role": "OPENER",
            },
            "_inline_tag_override": "CJC-TTL",
        }
    ]
    classifications = [{"id": "p1", "tag": "CJC-TTL", "confidence": 0.99}]
    out = apply_content_zone_overlays(classifications, blocks, ALLOWED)
    assert out[0]["tag"] == "CJC-TTL"


def test_roman_overlay_skips_inline_override():
    """A block tagged BL-FIRST via inline override would normally get
    rewritten to OUT1-FIRST if its text starts with a roman marker."""
    blocks = [
        {
            "id": "p1",
            "text": "II. Some outline item",
            "metadata": {},
            "_inline_tag_override": "BL-FIRST",
        }
    ]
    classifications = [{"id": "p1", "tag": "BL-FIRST", "confidence": 0.99}]
    allowed_with_out1 = ALLOWED | {"BL-FIRST", "OUT1-FIRST"}
    out = apply_roman_outline_overlays(classifications, blocks, allowed_with_out1)
    assert out[0]["tag"] == "BL-FIRST"


# ---------------------------------------------------------------------------
# Regex spot-checks
# ---------------------------------------------------------------------------


def test_regex_matches_simple():
    assert INLINE_TAG_MARKER_RE.match("<H1>Foo")
    assert INLINE_TAG_MARKER_RE.match("<CJC-TTL>Bar")
    assert INLINE_TAG_MARKER_RE.match("<TBL-MID>1. Item")


def test_regex_rejects_closing():
    assert INLINE_TAG_MARKER_RE.match("</H1>") is None


def test_regex_rejects_marker_only():
    assert INLINE_TAG_MARKER_RE.match("<H1>") is None
    assert INLINE_TAG_MARKER_RE.match("<H1>   ") is None
