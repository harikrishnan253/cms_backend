"""Tests for deterministic marker-token override rules."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.marker_rules import (
    apply_marker_overrides,
    parse_marker_token,
    resolve_marker_style,
)


# ===================================================================
# parse_marker_token
# ===================================================================

class TestParseMarkerToken:
    def test_h1_intro(self):
        assert parse_marker_token("<H1-INTRO>Introduction") == "<h1-intro>"

    def test_h1(self):
        assert parse_marker_token("<H1>Overview") == "<h1>"

    def test_sum(self):
        assert parse_marker_token("<SUM>Summary") == "<sum>"

    def test_closing_tag(self):
        assert parse_marker_token("</NOTE>") == "</note>"

    def test_leading_whitespace(self):
        assert parse_marker_token("  <H2>Section") == "<h2>"

    def test_no_marker(self):
        assert parse_marker_token("Normal paragraph text") is None

    def test_empty(self):
        assert parse_marker_token("") is None

    def test_none(self):
        assert parse_marker_token(None) is None

    def test_marker_with_spaces(self):
        assert parse_marker_token("<clinical pearl>") == "<clinical pearl>"

    def test_bxm(self):
        assert parse_marker_token("<BXM>") == "<bxm>"

    def test_body_open(self):
        assert parse_marker_token("<body-open>") == "<body-open>"


# ===================================================================
# resolve_marker_style
# ===================================================================

class TestResolveMarkerStyle:
    # Rule 1: <H1-INTRO> => SP-H1
    def test_h1_intro_with_text(self):
        assert resolve_marker_style("<h1-intro>", "<H1-INTRO>Introduction to Nursing") == "SP-H1"

    def test_h1_intro_alone(self):
        assert resolve_marker_style("<h1-intro>", "<H1-INTRO>") == "SP-H1"

    def test_h1_intro_case_insensitive(self):
        assert resolve_marker_style("<h1-intro>", "<h1-intro>Some Text") == "SP-H1"

    # Rule 2: <SUM> + SUMMARY text => EOC-H1
    def test_sum_with_summary(self):
        assert resolve_marker_style("<sum>", "<SUM>Summary") == "EOC-H1"

    def test_sum_with_chapter_summary(self):
        assert resolve_marker_style("<sum>", "<SUM>Chapter Summary") == "EOC-H1"

    def test_sum_alone_is_pmi(self):
        """<SUM> with no further text is marker-only => PMI."""
        assert resolve_marker_style("<sum>", "<SUM>") == "PMI"

    def test_sum_without_summary_keyword(self):
        """<SUM> followed by non-SUMMARY text gets no override."""
        assert resolve_marker_style("<sum>", "<SUM>Next Steps") is None

    # Rule 3: <H1> + REFERENCES => REFH1
    def test_h1_references(self):
        assert resolve_marker_style("<h1>", "<H1>References") == "REFH1"

    def test_h1_references_case_insensitive(self):
        assert resolve_marker_style("<h1>", "<H1>REFERENCES") == "REFH1"

    def test_h1_references_trailing_space(self):
        assert resolve_marker_style("<h1>", "<H1>References  ") == "REFH1"

    def test_h1_non_references(self):
        """<H1> with non-references heading returns None (handled by validator)."""
        assert resolve_marker_style("<h1>", "<H1>Overview") is None

    # Rule 4: generic marker-only => PMI
    def test_generic_marker_only(self):
        assert resolve_marker_style("<bxm>", "<BXM>") == "PMI"

    def test_body_open_marker_only(self):
        assert resolve_marker_style("<body-open>", "<body-open>") == "PMI"

    def test_closing_note_marker_only(self):
        assert resolve_marker_style("</note>", "</NOTE>") == "PMI"

    def test_generic_marker_with_text(self):
        """Unrecognised marker + text: no rule fires."""
        assert resolve_marker_style("<bxm>", "<BXM>Some content") is None


# ===================================================================
# apply_marker_overrides  (integration-level)
# ===================================================================

class TestApplyMarkerOverrides:
    def _make(self, blocks, tags):
        """Helper: build (blocks, classifications) from minimal data."""
        clfs = [
            {"id": b["id"], "tag": t, "confidence": 0.85}
            for b, t in zip(blocks, tags)
        ]
        return blocks, clfs

    # --- H1-INTRO override ---
    def test_h1_intro_overrides_txt(self):
        blocks, clfs = self._make(
            [{"id": 1, "text": "<H1-INTRO>Introduction", "metadata": {"context_zone": "FRONT_MATTER"}}],
            ["TXT"],
        )
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "SP-H1"
        assert result[0]["confidence"] >= 0.99
        assert "marker-override" in result[0].get("repair_reason", "")

    # --- SUM + SUMMARY override ---
    def test_sum_summary_overrides_h1(self):
        blocks, clfs = self._make(
            [{"id": 1, "text": "<SUM>Summary", "metadata": {"context_zone": "BACK_MATTER"}}],
            ["H1"],
        )
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "EOC-H1"

    # --- H1 + REFERENCES override ---
    def test_h1_references_overrides_to_refh1(self):
        blocks, clfs = self._make(
            [{"id": 1, "text": "<H1>References", "metadata": {"context_zone": "BACK_MATTER"}}],
            ["H1"],
        )
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "REFH1"

    # --- marker-only paragraph ---
    def test_marker_only_becomes_pmi(self):
        blocks, clfs = self._make(
            [{"id": 1, "text": "<BXM>", "metadata": {"context_zone": "BODY"}}],
            ["TXT"],
        )
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "PMI"

    # --- no marker: pass-through ---
    def test_no_marker_unchanged(self):
        blocks, clfs = self._make(
            [{"id": 1, "text": "Regular paragraph.", "metadata": {"context_zone": "BODY"}}],
            ["TXT"],
        )
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "TXT"
        assert result[0]["confidence"] == 0.85

    # --- zone safety: skip override if zone invalid ---
    def test_zone_invalid_skips_override(self):
        """SP-H1 is not valid for TABLE zone => override skipped."""
        blocks, clfs = self._make(
            [{"id": 1, "text": "<H1-INTRO>Intro", "metadata": {"context_zone": "TABLE"}}],
            ["T"],
        )
        result = apply_marker_overrides(blocks, clfs)
        # SP-H1 is not valid in TABLE zone, so original tag preserved
        assert result[0]["tag"] == "T"

    # --- PMI override always valid (zone-independent) ---
    def test_pmi_override_in_any_zone(self):
        for zone in ["BODY", "TABLE", "FRONT_MATTER", "BACK_MATTER", "BOX_NBX"]:
            blocks, clfs = self._make(
                [{"id": 1, "text": "<body-open>", "metadata": {"context_zone": zone}}],
                ["TXT"],
            )
            result = apply_marker_overrides(blocks, clfs)
            assert result[0]["tag"] == "PMI", f"Failed for zone={zone}"

    # --- does not break list tags ---
    def test_list_paragraphs_with_no_marker_unchanged(self):
        blocks, clfs = self._make(
            [
                {"id": 1, "text": "• First item", "metadata": {"context_zone": "BODY", "list_kind": "bullet", "list_position": "FIRST"}},
                {"id": 2, "text": "• Second item", "metadata": {"context_zone": "BODY", "list_kind": "bullet", "list_position": "LAST"}},
            ],
            ["BL-FIRST", "BL-LAST"],
        )
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "BL-FIRST"
        assert result[1]["tag"] == "BL-LAST"

    # --- preserves existing repair_reason ---
    def test_appends_to_existing_repair_reason(self):
        blocks = [{"id": 1, "text": "<H1>References", "metadata": {"context_zone": "BACK_MATTER"}}]
        clfs = [{"id": 1, "tag": "H1", "confidence": 0.85, "repair_reason": "heading-hierarchy"}]
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "REFH1"
        assert "heading-hierarchy" in result[0]["repair_reason"]
        assert "marker-override" in result[0]["repair_reason"]

    # --- multi-block pipeline ---
    def test_mixed_blocks(self):
        blocks = [
            {"id": 1, "text": "<H1-INTRO>Introduction", "metadata": {"context_zone": "FRONT_MATTER"}},
            {"id": 2, "text": "Normal body text.", "metadata": {"context_zone": "BODY"}},
            {"id": 3, "text": "<H1>References", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 4, "text": "<SUM>Summary", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 5, "text": "<BXM>", "metadata": {"context_zone": "BODY"}},
        ]
        clfs = [
            {"id": 1, "tag": "TXT", "confidence": 0.80},
            {"id": 2, "tag": "TXT", "confidence": 0.90},
            {"id": 3, "tag": "H1", "confidence": 0.88},
            {"id": 4, "tag": "H1", "confidence": 0.85},
            {"id": 5, "tag": "TXT", "confidence": 0.70},
        ]
        result = apply_marker_overrides(blocks, clfs)
        assert result[0]["tag"] == "SP-H1"
        assert result[1]["tag"] == "TXT"      # unchanged
        assert result[2]["tag"] == "REFH1"
        assert result[3]["tag"] == "EOC-H1"
        assert result[4]["tag"] == "PMI"
