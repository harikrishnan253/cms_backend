"""Tests for content-driven zone detection and overlay enforcement."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.content_zones import (
    detect_content_zones,
    apply_content_zone_overlays,
    apply_roman_outline_overlays,
)


def _b(bid, text):
    return {"id": bid, "text": text, "metadata": {}}


def _c(bid, tag):
    return {"id": bid, "tag": tag, "confidence": 85}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_detect_case_study_zone_propagates_until_next_opener():
    blocks = [
        _b(1, "Some intro paragraph."),
        _b(2, "Case Study"),
        _b(3, "Mr. Smith presents with..."),
        _b(4, "He was admitted on Tuesday."),
        _b(5, "Summary"),
        _b(6, "In conclusion..."),
    ]
    detect_content_zones(blocks)

    assert blocks[0]["metadata"].get("content_zone") is None
    assert blocks[1]["metadata"]["content_zone"] == "CASE_STUDY"
    assert blocks[1]["metadata"]["content_zone_role"] == "OPENER"
    assert blocks[2]["metadata"]["content_zone"] == "CASE_STUDY"
    assert blocks[2]["metadata"]["content_zone_role"] == "FIRST_BODY"
    assert blocks[3]["metadata"]["content_zone"] == "CASE_STUDY"
    assert blocks[3]["metadata"].get("content_zone_role") is None
    assert blocks[4]["metadata"]["content_zone"] == "EOC_SUMMARY"
    assert blocks[4]["metadata"]["content_zone_role"] == "OPENER"
    assert blocks[5]["metadata"]["content_zone"] == "EOC_SUMMARY"
    assert blocks[5]["metadata"]["content_zone_role"] == "FIRST_BODY"


def test_heading_with_terminal_punctuation_is_not_an_opener():
    blocks = [
        _b(1, "Case study: a discussion of."),  # has terminal punctuation
        _b(2, "Body paragraph."),
    ]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"].get("content_zone") is None
    assert blocks[1]["metadata"].get("content_zone") is None


def test_objectives_kt_kp_eoc_post_ref_all_detected():
    blocks = [
        _b(1, "Objectives"),
        _b(2, "Learn things"),
        _b(3, "Key Terms"),
        _b(4, "Term A"),
        _b(5, "Summary"),
        _b(6, "We discussed."),
        _b(7, "Key Points"),
        _b(8, "Point one"),
        _b(9, "References"),
        _b(10, "Smith J. 2020."),
        _b(11, "Figure 99 caption"),  # post-ref figure caption
    ]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"]["content_zone"] == "OBJ"
    assert blocks[2]["metadata"]["content_zone"] == "KT"
    assert blocks[4]["metadata"]["content_zone"] == "EOC_SUMMARY"
    assert blocks[6]["metadata"]["content_zone"] == "KP"
    assert blocks[8]["metadata"]["content_zone"] == "POST_REF"
    assert blocks[10]["metadata"]["content_zone"] == "POST_REF"


# ---------------------------------------------------------------------------
# Overlay enforcement
# ---------------------------------------------------------------------------

ALLOWED = {
    "TXT", "TXT-FLUSH", "H1", "PMI", "T1", "FIG-LEG",
    "BL-FIRST", "BL-MID", "BL-LAST",
    "NL-FIRST", "NL-MID", "NL-LAST",
    "UL-FIRST", "UL-MID", "UL-LAST",
    "CS-TTL", "CS-H1", "CS-TXT", "CS-TXT-FIRST",
    "EOC-H1", "EOC-TXT", "EOC-TXT-FIRST", "EOC-TXT-FLUSH",
    "EOC-NL-FIRST", "EOC-NL-MID", "EOC-NL-LAST",
    "OBJ1", "OBJ-BL-FIRST", "OBJ-BL-MID", "OBJ-BL-LAST",
    "OBJ-NL-FIRST", "OBJ-NL-MID", "OBJ-NL-LAST",
    "OBJ-UL-FIRST", "OBJ-UL-MID", "OBJ-UL-LAST",
    "KT1", "KT-UL-FIRST", "KT-UL-MID", "KT-UL-LAST",
    "KT-BL-FIRST", "KT-BL-MID", "KT-BL-LAST",
    "KT-NL-FIRST", "KT-NL-MID", "KT-NL-LAST",
    "KP1", "KP-BL-FIRST", "KP-BL-MID", "KP-BL-LAST",
    "KP-NL-FIRST", "KP-NL-MID", "KP-NL-LAST",
}


def test_overlay_case_study_promotes_text_and_heading():
    blocks = [
        _b(1, "Case Study"),
        _b(2, "First paragraph of the case."),
        _b(3, "Second paragraph."),
        _b(4, "Diagnostic heading"),
    ]
    detect_content_zones(blocks)
    clfs = [
        _c(1, "TTL"),
        _c(2, "TXT"),
        _c(3, "TXT"),
        _c(4, "H1"),
    ]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED)
    assert out[0]["tag"] == "CS-TTL"
    assert out[1]["tag"] == "CS-TXT-FIRST"
    assert out[2]["tag"] == "CS-TXT"
    assert out[3]["tag"] == "CS-H1"


def test_overlay_eoc_summary_remaps_text_and_lists():
    blocks = [
        _b(1, "Summary"),
        _b(2, "First sentence."),
        _b(3, "Second sentence."),
        _b(4, "First bullet"),
        _b(5, "Last bullet"),
    ]
    detect_content_zones(blocks)
    clfs = [
        _c(1, "H1"),
        _c(2, "TXT"),
        _c(3, "TXT-FLUSH"),
        _c(4, "NL-FIRST"),
        _c(5, "NL-LAST"),
    ]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED)
    assert out[0]["tag"] == "EOC-H1"
    assert out[1]["tag"] == "EOC-TXT-FIRST"
    assert out[2]["tag"] == "EOC-TXT-FLUSH"
    assert out[3]["tag"] == "EOC-NL-FIRST"
    assert out[4]["tag"] == "EOC-NL-LAST"


def test_overlay_objectives_remaps_lists_and_title():
    blocks = [
        _b(1, "Objectives"),
        _b(2, "Identify..."),
        _b(3, "Describe..."),
    ]
    detect_content_zones(blocks)
    clfs = [
        _c(1, "H1"),
        _c(2, "BL-FIRST"),
        _c(3, "BL-LAST"),
    ]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED)
    assert out[0]["tag"] == "OBJ1"
    assert out[1]["tag"] == "OBJ-BL-FIRST"
    assert out[2]["tag"] == "OBJ-BL-LAST"


def test_overlay_key_terms_uses_kt_family():
    blocks = [
        _b(1, "Key Terms"),
        _b(2, "Term A"),
        _b(3, "Term B"),
    ]
    detect_content_zones(blocks)
    clfs = [
        _c(1, "H1"),
        _c(2, "UL-FIRST"),
        _c(3, "UL-LAST"),
    ]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED)
    assert out[0]["tag"] == "KT1"
    assert out[1]["tag"] == "KT-UL-FIRST"
    assert out[2]["tag"] == "KT-UL-LAST"


def test_overlay_key_points_uses_kp_family_not_kt():
    blocks = [
        _b(1, "Key Points"),
        _b(2, "Point one"),
        _b(3, "Point two"),
    ]
    detect_content_zones(blocks)
    clfs = [
        _c(1, "H1"),
        _c(2, "BL-FIRST"),
        _c(3, "BL-LAST"),
    ]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED)
    assert out[0]["tag"] == "KP1"
    assert out[1]["tag"] == "KP-BL-FIRST"
    assert out[2]["tag"] == "KP-BL-LAST"


def test_overlay_post_references_promotes_captions_to_pmi():
    blocks = [
        _b(1, "References"),
        _b(2, "Smith et al. 2020."),
        _b(3, "Figure 99. Cardiac anatomy."),
        _b(4, "Table 99. Patient demographics."),
    ]
    detect_content_zones(blocks)
    clfs = [
        _c(1, "H1"),
        _c(2, "REF-N"),
        _c(3, "FIG-LEG"),
        _c(4, "T1"),
    ]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED)
    # The opener H1 in POST_REF zone is left alone (POST_REF only promotes
    # captions); the reference body stays REF-N.
    assert out[0]["tag"] == "H1"
    assert out[1]["tag"] == "REF-N"
    assert out[2]["tag"] == "PMI"
    assert out[3]["tag"] == "PMI"


def test_detect_chapter_opener_marks_number_and_title_roles():
    blocks = [
        _b(1, "Chapter 3"),
        _b(2, "Cardiac Anatomy"),
        _b(3, "Body paragraph."),
    ]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"]["content_zone_role"] == "CN"
    assert blocks[1]["metadata"]["content_zone_role"] == "CT"
    assert blocks[2]["metadata"].get("content_zone_role") is None


def test_detect_section_opener_uses_section_family():
    blocks = [
        _b(1, "Section 2"),
        _b(2, "Pediatric Care"),
    ]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"]["content_zone_role"] == "SN"
    assert blocks[1]["metadata"]["content_zone_role"] == "ST"


def test_detect_bare_number_opener_only_when_title_follows():
    # "3" on its own with a heading-shape title following → chapter number.
    blocks = [_b(1, "3"), _b(2, "Cardiac Anatomy"), _b(3, "Body.")]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"]["content_zone_role"] == "CN"
    assert blocks[1]["metadata"]["content_zone_role"] == "CT"

    # "12" with no following heading → not a chapter opener.
    blocks2 = [_b(1, "12"), _b(2, "This is a body sentence with a period.")]
    detect_content_zones(blocks2)
    assert blocks2[0]["metadata"].get("content_zone_role") is None


def test_overlay_promotes_chapter_number_and_title_tags():
    blocks = [
        _b(1, "Chapter 3"),
        _b(2, "Cardiac Anatomy"),
        _b(3, "Body."),
    ]
    detect_content_zones(blocks)
    clfs = [_c(1, "TXT"), _c(2, "H1"), _c(3, "TXT")]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED | {"CN", "CT"})
    assert out[0]["tag"] == "CN"
    assert out[1]["tag"] == "CT"
    assert out[2]["tag"] == "TXT"


def test_overlay_promotes_section_number_and_title_tags():
    blocks = [
        _b(1, "Section 2"),
        _b(2, "Pediatric Care"),
    ]
    detect_content_zones(blocks)
    clfs = [_c(1, "TXT"), _c(2, "H1")]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED | {"SN", "ST"})
    assert out[0]["tag"] == "SN"
    assert out[1]["tag"] == "ST"


def test_roman_overlay_promotes_upper_roman_list_to_out1():
    blocks = [
        _b(1, "I. Planning"),
        _b(2, "II. Development"),
        _b(3, "III. Testing"),
    ]
    clfs = [_c(1, "BL-FIRST"), _c(2, "BL-MID"), _c(3, "BL-LAST")]
    out = apply_roman_outline_overlays(clfs, blocks, ALLOWED | {
        "OUT1-FIRST", "OUT1-MID", "OUT1-LAST",
    })
    assert out[0]["tag"] == "OUT1-FIRST"
    assert out[1]["tag"] == "OUT1-MID"
    assert out[2]["tag"] == "OUT1-LAST"


def test_roman_overlay_promotes_lower_roman_list_to_out1():
    blocks = [
        _b(1, "i. Apple"),
        _b(2, "ii. Banana"),
        _b(3, "iii. Mango"),
    ]
    clfs = [_c(1, "NL-FIRST"), _c(2, "NL-MID"), _c(3, "NL-LAST")]
    out = apply_roman_outline_overlays(clfs, blocks, ALLOWED | {
        "OUT1-FIRST", "OUT1-MID", "OUT1-LAST",
    })
    assert out[0]["tag"] == "OUT1-FIRST"
    assert out[2]["tag"] == "OUT1-LAST"


def test_roman_overlay_does_not_promote_solitary_pronoun_I():
    # "I. " on its own without a roman neighbour is ambiguous (pronoun
    # plus terminal period) and must not be promoted.
    blocks = [
        _b(1, "Some preamble."),
        _b(2, "I. think this is a body sentence."),
        _b(3, "Following text."),
    ]
    clfs = [_c(1, "TXT"), _c(2, "BL-FIRST"), _c(3, "TXT")]
    out = apply_roman_outline_overlays(clfs, blocks, ALLOWED | {
        "OUT1-FIRST", "OUT1-MID", "OUT1-LAST",
    })
    assert out[1]["tag"] == "BL-FIRST"  # unchanged


def test_roman_overlay_skips_non_list_tags():
    blocks = [_b(1, "II. Heading-like")]
    clfs = [_c(1, "H1")]  # not a list tag
    out = apply_roman_outline_overlays(clfs, blocks, ALLOWED | {"OUT1-FIRST"})
    assert out[0]["tag"] == "H1"


def test_roman_overlay_skips_when_target_not_allowed():
    blocks = [_b(1, "II. Item one"), _b(2, "III. Item two")]
    clfs = [_c(1, "BL-FIRST"), _c(2, "BL-LAST")]
    out = apply_roman_outline_overlays(clfs, blocks, ALLOWED)  # no OUT1-*
    assert out[0]["tag"] == "BL-FIRST"


def test_overlay_skips_when_target_not_in_allowed():
    blocks = [_b(1, "Case Study"), _b(2, "Body.")]
    detect_content_zones(blocks)
    clfs = [_c(1, "TTL"), _c(2, "TXT")]
    # ALLOWED minus CS-TTL — CS-TXT-FIRST is allowed though, so test partial.
    limited = ALLOWED - {"CS-TTL"}
    out = apply_content_zone_overlays(clfs, blocks, limited)
    assert out[0]["tag"] == "TTL"  # unchanged: CS-TTL not allowed
    assert out[1]["tag"] == "CS-TXT-FIRST"  # promoted: target is allowed


# ---------------------------------------------------------------------------
# Chapter Section Title (CST) — content-only fallback
# ---------------------------------------------------------------------------


def test_cst_detected_for_all_caps_section_heading():
    blocks = [_b(1, "STRUCTURE AND FUNCTION")]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"].get("content_zone_role") == "CST"


def test_cst_detected_for_objective_cues():
    blocks = [_b(1, "OBJECTIVE CUES")]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"].get("content_zone_role") == "CST"


def test_cst_not_set_for_mixed_case_heading():
    """Regular H1-shape headings stay un-roled."""
    blocks = [_b(1, "Structure and Function")]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"].get("content_zone_role") is None


def test_cst_skipped_when_text_is_known_zone_opener():
    """REFERENCES is a POST_REF opener, not CST."""
    blocks = [_b(1, "REFERENCES")]
    detect_content_zones(blocks)
    role = blocks[0]["metadata"].get("content_zone_role")
    # OPENER role wins; CST never fires.
    assert role == "OPENER"


def test_cst_skipped_for_chapter_opener():
    """CHAPTER 6 is a chapter number opener, not CST."""
    blocks = [_b(1, "CHAPTER 6"), _b(2, "Pain Assessment")]
    detect_content_zones(blocks)
    assert blocks[0]["metadata"].get("content_zone_role") == "CN"


def test_cst_overlay_promotes_to_cst_tag():
    blocks = [_b(1, "STRUCTURE AND FUNCTION")]
    detect_content_zones(blocks)
    clfs = [_c(1, "H1")]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED | {"CST"})
    assert out[0]["tag"] == "CST"


def test_cst_overlay_skipped_when_inline_override_present():
    """Author wrote <CST>...; Slice 1 lock means overlay must not double-stamp."""
    blocks = [
        {
            "id": 1,
            "text": "STRUCTURE AND FUNCTION",
            "metadata": {"content_zone_role": "CST"},
            "_inline_tag_override": "CST",
        }
    ]
    clfs = [{"id": 1, "tag": "CST", "confidence": 0.99}]
    out = apply_content_zone_overlays(clfs, blocks, ALLOWED | {"CST"})
    assert out[0]["tag"] == "CST"
    # repaired flag should be absent (no rewrite happened)
    assert not out[0].get("repaired")
