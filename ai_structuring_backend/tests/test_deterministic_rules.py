"""
Tests for the deterministic classification engine.

Each test class covers one tier of the confidence hierarchy:
  100%  Zone markers → PMI
   99%  Chapter metadata & heading markers
 95-98% Reference patterns
 95-97% Figure / table patterns
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from processor.deterministic_rules import (
    apply_deterministic_rules,
    _classify_one,
    _is_list_item,
    ListSequenceProcessor,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _quick(text: str, zone: str = "BODY", **extra_meta) -> dict | None:
    """Shortcut: classify a single paragraph and return the result dict."""
    meta = {"context_zone": zone, **extra_meta}
    return _classify_one(text, meta, zone, in_float=False)


def _quick_float(text: str) -> dict | None:
    """Classify inside FLOAT zone."""
    return _classify_one(text, {"context_zone": "TABLE"}, "TABLE", in_float=True)


# =============================================================================
# 1. ZONE MARKERS → PMI  (100 %)
# =============================================================================

class TestZoneMarkers:

    @pytest.mark.parametrize("marker", [
        "<front-open>",
        "<front-close>",
        "<body-open>",
        "<body-close>",
        "<back-open>",
        "<back-close>",
        "<float-open>",
        "<float-close>",
        "<metadata>",
        "</metadata>",
    ])
    def test_zone_markers_are_pmi(self, marker):
        r = _quick(marker)
        assert r is not None
        assert r["tag"] == "PMI"
        assert r["confidence"] == 100

    @pytest.mark.parametrize("marker", [
        "<FRONT-OPEN>",
        "<Front-Close>",
        "  <body-open>  ",
        " <BACK-CLOSE> ",
    ])
    def test_zone_markers_case_insensitive(self, marker):
        r = _quick(marker)
        assert r is not None and r["tag"] == "PMI"

    def test_ref_marker_is_pmi(self):
        r = _quick("<ref>References")
        assert r is not None
        assert r["tag"] == "PMI"
        assert r["confidence"] == 100

    def test_ref_marker_uppercase(self):
        r = _quick("<REF>")
        assert r is not None
        assert r["tag"] == "PMI"

    def test_ref_closing_tag(self):
        r = _quick("</ref>")
        assert r is not None
        assert r["tag"] == "PMI"


class TestBoxMarkers:

    @pytest.mark.parametrize("marker", [
        "<note>",
        "</note>",
        "<clinical pearl>",
        "</clinical pearl>",
        "<red flag>",
        "<box>",
        "</box>",
        "<tip>",
        "<example>",
        "<warning>",
        "<case study>",
        "<key point>",
        "<unnumbered box>",
    ])
    def test_box_markers_are_pmi(self, marker):
        r = _quick(marker)
        assert r is not None
        assert r["tag"] == "PMI"
        assert r["confidence"] == 100


# =============================================================================
# 2. CHAPTER METADATA  (99 %)
# =============================================================================

class TestChapterMetadata:

    def test_cn_with_marker(self):
        r = _quick("<CN>Chapter 5")
        assert r is not None
        assert r["tag"] == "CN"
        assert r["confidence"] == 99

    def test_cn_without_marker(self):
        r = _quick("Chapter 12")
        assert r is not None
        assert r["tag"] == "CN"

    def test_cn_roman_numeral(self):
        r = _quick("Chapter IV")
        assert r is not None
        assert r["tag"] == "CN"

    def test_ct_marker(self):
        r = _quick("<CT>Immune-Related Adverse Events")
        assert r is not None
        assert r["tag"] == "CT"
        assert r["confidence"] == 99

    def test_cau_marker(self):
        r = _quick("<CAU>John Smith, MD")
        assert r is not None
        assert r["tag"] == "CAU"
        assert r["confidence"] == 99


# =============================================================================
# 3. HEADING MARKERS  (99 %)
# =============================================================================

class TestHeadingMarkers:

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
    def test_inline_heading(self, level):
        r = _quick(f"<H{level}>Section Title Here")
        assert r is not None
        assert r["tag"] == f"H{level}"
        assert r["confidence"] == 99

    def test_heading_case_insensitive(self):
        r = _quick("<h2>Epidemiology")
        assert r is not None
        assert r["tag"] == "H2"

    def test_heading_with_whitespace(self):
        r = _quick("  <H1>Introduction  ")
        assert r is not None
        assert r["tag"] == "H1"


# =============================================================================
# 4. REFERENCE PATTERNS  (95-98 %)
# =============================================================================

class TestReferenceHeadings:

    def test_references_heading(self):
        r = _quick("References")
        assert r is not None
        assert r["tag"] == "REFH1"
        assert r["confidence"] == 98

    def test_references_uppercase(self):
        r = _quick("REFERENCES")
        assert r is not None
        assert r["tag"] == "REFH1"

    def test_bibliography_heading(self):
        r = _quick("Bibliography")
        assert r is not None
        assert r["tag"] == "REFH1"

    def test_suggested_readings_heading(self):
        r = _quick("Suggested Readings")
        assert r is not None
        assert r["tag"] == "SRH1"
        assert r["confidence"] == 98

    def test_further_reading_heading(self):
        r = _quick("Further Reading")
        assert r is not None
        assert r["tag"] == "SRH1"

    def test_ref_marker_plus_references(self):
        """<ref>References is PMI (marker), but bare 'References' is REFH1."""
        r = _quick("References")
        assert r["tag"] == "REFH1"


class TestReferenceEntries:

    def test_numbered_ref_bracket(self):
        r = _quick("[1] Smith AB, Jones CD. J Clin Oncol. 2020;38:1234.", zone="BACK_MATTER")
        assert r is not None
        assert r["tag"] == "REF-N"

    def test_numbered_ref_dot(self):
        r = _quick("1. Brahmer JR, Abu-Sbeih H, et al. J Clin Oncol. 2018;36:1714.", zone="BACK_MATTER")
        assert r is not None
        assert r["tag"] == "REF-N"

    def test_numbered_ref_paren(self):
        r = _quick("(1) Author AB, Title. Journal. 2021.", zone="BACK_MATTER")
        assert r is not None
        assert r["tag"] == "REF-N"

    def test_author_style_ref(self):
        r = _quick("Smith, AB. (2020). Title of paper. Journal, 15(3), 123-130.", zone="BACK_MATTER")
        assert r is not None
        assert r["tag"] == "REF-U"

    def test_generic_sr_in_back_matter(self):
        r = _quick(
            "Thompson JA et al. NCCN Clinical Practice Guidelines in Oncology. 2022;20(4):123.",
            zone="BACK_MATTER",
        )
        assert r is not None
        assert r["tag"] in ("SR", "REF-U", "REF-N")

    def test_numbered_ref_not_in_body(self):
        """Numbered references should NOT match in BODY zone."""
        r = _quick("1. Introduction to the topic at hand.")
        assert r is None or r["tag"] not in ("REF-N", "REF-U", "SR")

    def test_short_back_matter_text_not_sr(self):
        """Very short text in back matter should not match SR."""
        r = _quick("See also:", zone="BACK_MATTER")
        assert r is None or r["tag"] != "SR"


# =============================================================================
# 5. FIGURE / TABLE PATTERNS  (95-97 %)
# =============================================================================

class TestFigureCaptions:

    def test_figure_caption(self):
        r = _quick("Figure 1.1. Mechanism of immune checkpoint inhibition")
        assert r is not None
        assert r["tag"] == "FIG-LEG"
        assert r["confidence"] == 97

    def test_fig_abbreviated(self):
        r = _quick("Fig. 3. Overview of treatment algorithm")
        assert r is not None
        assert r["tag"] == "FIG-LEG"

    def test_efigure_caption(self):
        r = _quick("e-Figure 2.1. Supplementary data overview")
        assert r is not None
        assert r["tag"] == "FIG-LEG"

    def test_figure_with_fn_marker(self):
        r = _quick("<fn>Figure 4. Dose-response curve")
        assert r is not None
        assert r["tag"] == "FIG-LEG"

    def test_figure_legends_heading(self):
        r = _quick("Figure Legends")
        assert r is not None
        assert r["tag"] == "H1"


class TestTableCaptions:

    def test_table_caption(self):
        r = _quick("Table 2.3. Patient demographics and baseline characteristics")
        assert r is not None
        assert r["tag"] == "T1"
        assert r["confidence"] == 97

    def test_table_abbreviated(self):
        r = _quick("Tab. 1. Summary of adverse events")
        assert r is not None
        assert r["tag"] == "T1"

    def test_etable_caption(self):
        r = _quick("e-Table 1.2. Extended data")
        assert r is not None
        assert r["tag"] == "T1"

    def test_table_with_tn_marker(self):
        r = _quick("<tn>Table 5. Drug interactions")
        assert r is not None
        assert r["tag"] == "T1"


class TestTableFootnotes:

    def test_letter_footnote_in_table(self):
        r = _quick("a. Adjusted for age and sex", zone="TABLE")
        assert r is not None
        assert r["tag"] == "TFN"
        assert r["confidence"] == 95

    def test_letter_footnote_in_float(self):
        r = _quick_float("b) Based on modified ITT population")
        assert r is not None
        assert r["tag"] == "TFN"

    def test_abbreviation_block(self):
        r = _quick("CBC, complete blood count; CMP, comprehensive metabolic panel", zone="TABLE")
        assert r is not None
        assert r["tag"] == "TFN"

    def test_letter_footnote_not_in_body(self):
        """Letter-prefix lines in BODY should not become TFN."""
        r = _quick("a. First option in the treatment algorithm")
        assert r is None or r["tag"] != "TFN"


class TestSourceLines:

    def test_source_in_table(self):
        r = _quick("Source: National Cancer Institute, 2022", zone="TABLE")
        assert r is not None
        assert r["tag"] == "TSN"

    def test_adapted_from_in_float(self):
        r = _quick_float("Adapted from: Smith et al., 2021")
        assert r is not None
        assert r["tag"] == "TSN"

    def test_source_in_body(self):
        r = _quick("Source: Clinical trial data, 2023")
        assert r is not None
        assert r["tag"] == "FIG-SRC"


# =============================================================================
# 6. FULL PIPELINE  (apply_deterministic_rules)
# =============================================================================

class TestApplyDeterministicRules:

    def test_mixed_document(self):
        paragraphs = [
            {"id": 1, "text": "<CN>Chapter 5", "metadata": {"context_zone": "FRONT_MATTER"}},
            {"id": 2, "text": "<CT>Immune-Related Adverse Events", "metadata": {"context_zone": "FRONT_MATTER"}},
            {"id": 3, "text": "<CAU>John Smith, MD", "metadata": {"context_zone": "FRONT_MATTER"}},
            {"id": 4, "text": "<H1>Introduction", "metadata": {"context_zone": "BODY"}},
            {"id": 5, "text": "Regular paragraph needing LLM", "metadata": {"context_zone": "BODY"}},
            {"id": 6, "text": "Another regular paragraph", "metadata": {"context_zone": "BODY"}},
            {"id": 7, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 8, "text": "1. Smith AB et al. J Oncol. 2020;1:23.", "metadata": {"context_zone": "BACK_MATTER"}},
        ]

        out = apply_deterministic_rules(paragraphs)

        det = {r["id"]: r for r in out["deterministic"]}
        llm_ids = {p["id"] for p in out["llm_queue"]}

        # Deterministic classifications
        assert det[1]["tag"] == "CN"
        assert det[2]["tag"] == "CT"
        assert det[3]["tag"] == "CAU"
        assert det[4]["tag"] == "H1"
        assert det[7]["tag"] == "REFH1"
        assert det[8]["tag"] == "REF-N"

        # LLM queue
        assert 5 in llm_ids
        assert 6 in llm_ids

        # Zone map populated for every paragraph
        assert len(out["zone_map"]) == 8

    def test_empty_input(self):
        out = apply_deterministic_rules([])
        assert out["deterministic"] == []
        assert out["llm_queue"] == []
        assert out["zone_map"] == {}

    def test_all_need_llm(self):
        paragraphs = [
            {"id": 1, "text": "Plain body text.", "metadata": {"context_zone": "BODY"}},
            {"id": 2, "text": "More body text.", "metadata": {"context_zone": "BODY"}},
        ]
        out = apply_deterministic_rules(paragraphs)
        assert len(out["deterministic"]) == 0
        assert len(out["llm_queue"]) == 2

    def test_zone_tracking(self):
        """Zone tracker updates from markers."""
        paragraphs = [
            {"id": 1, "text": "<front-open>", "metadata": {}},
            {"id": 2, "text": "Author info", "metadata": {}},
            {"id": 3, "text": "<body-open>", "metadata": {}},
            {"id": 4, "text": "Body paragraph", "metadata": {}},
            {"id": 5, "text": "<back-open>", "metadata": {}},
            {"id": 6, "text": "1. Ref entry here with Author AB. 2020.", "metadata": {}},
        ]
        out = apply_deterministic_rules(paragraphs)

        # Markers themselves are PMI
        det = {r["id"]: r for r in out["deterministic"]}
        assert det[1]["tag"] == "PMI"
        assert det[3]["tag"] == "PMI"
        assert det[5]["tag"] == "PMI"

        # Zone map reflects transitions
        assert out["zone_map"][1] == "FRONT_MATTER"
        assert out["zone_map"][4] == "BODY"
        assert out["zone_map"][6] == "BACK_MATTER"

    def test_deterministic_results_have_rule_based_flag(self):
        paragraphs = [
            {"id": 1, "text": "<H2>Methods", "metadata": {"context_zone": "BODY"}},
        ]
        out = apply_deterministic_rules(paragraphs)
        assert out["deterministic"][0]["rule_based"] is True


# =============================================================================
# 7. EDGE CASES
# =============================================================================

class TestEdgeCases:

    def test_none_text(self):
        """Empty text should not crash."""
        r = _quick("")
        assert r is None

    def test_whitespace_only(self):
        r = _quick("   ")
        assert r is None

    def test_partial_marker_not_matched(self):
        """Text containing a marker substring but not a full marker."""
        r = _quick("This is not a <front-open> situation")
        assert r is None or r["tag"] != "PMI"

    def test_chapter_text_not_cn(self):
        """'Chapter' inside a sentence should NOT be CN."""
        r = _quick("This chapter discusses immunology topics in depth.")
        assert r is None or r["tag"] != "CN"

    def test_figure_in_sentence_not_caption(self):
        """'Figure' mentioned mid-sentence should NOT be FIG-LEG."""
        r = _quick("As shown in Figure 2, the results indicate improvement.")
        # This starts with "As shown" not "Figure 2", so should not match
        assert r is None or r["tag"] != "FIG-LEG"


# =============================================================================
# 8. LIST SEQUENCE PROCESSOR
# =============================================================================

class TestListSequenceIdentification:

    def test_is_list_from_metadata_flags(self):
        assert _is_list_item("Any text", {"has_bullet": True})
        assert _is_list_item("Any text", {"has_numbering": True})
        assert _is_list_item("Any text", {"has_xml_list": True})

    @pytest.mark.parametrize("lead", ["▲", "●", "○", "■", "•", "►", "◆", "✓", "\uf0b7", "\uf0a7"])
    def test_is_list_from_bullet_char(self, lead):
        assert _is_list_item(f"{lead} item", {})

    def test_is_list_from_numbered_pattern(self):
        assert _is_list_item("1. Item", {})
        assert _is_list_item("2) Item", {})

    def test_is_list_from_lettered_pattern(self):
        assert _is_list_item("a. Item", {})
        assert _is_list_item("b) Item", {})


class TestListSequenceProcessor:

    def test_groups_consecutive_and_assigns_positions(self):
        p = [
            {"id": 1, "text": "• One", "metadata": {"has_bullet": True}},
            {"id": 2, "text": "• Two", "metadata": {"has_bullet": True}},
            {"id": 3, "text": "• Three", "metadata": {"has_bullet": True}},
        ]
        c = [
            {"id": 1, "tag": "BL-MID"},
            {"id": 2, "tag": "BL-MID"},
            {"id": 3, "tag": "BL-MID"},
        ]
        out = ListSequenceProcessor().process(p, c)
        by_id = {x["id"]: x for x in out}
        assert by_id[1]["tag"] == "BL-FIRST"
        assert by_id[2]["tag"] == "BL-MID"
        assert by_id[3]["tag"] == "BL-LAST"

    def test_single_item_sequence_marked_first_with_flag(self):
        p = [{"id": 1, "text": "• Solo", "metadata": {"has_bullet": True}}]
        c = [{"id": 1, "tag": "BL-MID"}]
        out = ListSequenceProcessor().process(p, c)
        assert out[0]["tag"] == "BL-FIRST"
        assert out[0]["list_single"] is True

    def test_non_list_gap_breaks_sequence(self):
        p = [
            {"id": 1, "text": "• One", "metadata": {"has_bullet": True}},
            {"id": 2, "text": "Body text", "metadata": {}},
            {"id": 3, "text": "• Two", "metadata": {"has_bullet": True}},
        ]
        c = [
            {"id": 1, "tag": "BL-MID"},
            {"id": 2, "tag": "TXT"},
            {"id": 3, "tag": "BL-MID"},
        ]
        out = ListSequenceProcessor().process(p, c)
        by_id = {x["id"]: x for x in out}
        assert by_id[1]["tag"] == "BL-FIRST"
        assert by_id[3]["tag"] == "BL-FIRST"

    @pytest.mark.parametrize("family_tag", ["BL2-MID", "BL3-MID", "NL2-MID", "NL3-MID", "TBL-MID", "TNL-MID", "NBX-BL-MID", "BX1-BL-MID"])
    def test_applies_positions_across_families(self, family_tag):
        p = [
            {"id": 1, "text": "x", "metadata": {"has_xml_list": True}},
            {"id": 2, "text": "y", "metadata": {"has_xml_list": True}},
        ]
        c = [{"id": 1, "tag": family_tag}, {"id": 2, "tag": family_tag}]
        out = ListSequenceProcessor().process(p, c)
        by_id = {x["id"]: x for x in out}
        prefix = family_tag.rsplit("-", 1)[0] + "-"
        assert by_id[1]["tag"] == f"{prefix}FIRST"
        assert by_id[2]["tag"] == f"{prefix}LAST"
