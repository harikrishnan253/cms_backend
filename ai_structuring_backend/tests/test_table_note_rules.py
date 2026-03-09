"""Tests for table-note / footnote classification override."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.table_note_rules import (
    _has_table_anchor,
    is_table_note,
    apply_table_note_overrides,
)


# Shared allowed styles for tests
ALLOWED = {
    "TFN", "TFN1", "TSN",
    "TFN-FIRST", "TFN-MID", "TFN-LAST",
    "TFN-BL-FIRST", "TFN-BL-MID", "TFN-BL-LAST",
    "TXT", "TXT-FLUSH", "REF-N", "REF-U",
    "T1", "T11", "T12", "T", "T2", "T4", "TD",
    "TH1", "TH2", "TH3",
    "H1", "H2", "BL-FIRST", "BL-MID", "BL-LAST",
    "TBL-FIRST", "TBL-MID", "TBL-LAST",
    "PMI",
}


def _block(pid, text="Paragraph", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


def _clf(pid, tag, conf=0.85, **extra):
    d = {"id": pid, "tag": tag, "confidence": conf}
    d.update(extra)
    return d


# ===================================================================
# is_table_note
# ===================================================================

class TestIsTableNote:
    def test_lettered_footnote(self):
        result = is_table_note("a Adjusted for age", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_symbol_dagger(self):
        result = is_table_note("† p < 0.05", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_symbol_asterisk(self):
        result = is_table_note("* Statistically significant", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_symbol_double_dagger(self):
        result = is_table_note("‡ Excludes outliers", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_paren_letter(self):
        result = is_table_note("a) Significance level p < 0.01", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_digit_note(self):
        result = is_table_note("1 Adjusted for age and sex", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_note_prefix(self):
        result = is_table_note("Note: Values are means ± SD", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_notes_prefix(self):
        result = is_table_note("Notes: All values are approximate", "BODY", near_table=True)
        assert result == ("TFN", "table-footnote")

    def test_source_line(self):
        result = is_table_note("Source: Adapted from Smith (2020)", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    def test_adapted_from(self):
        result = is_table_note("Adapted from WHO Guidelines 2019", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    def test_reproduced_from(self):
        result = is_table_note("Reproduced from Jones et al. (2018)", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    def test_with_permission(self):
        result = is_table_note("With permission from Elsevier", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    def test_reprinted_from(self):
        result = is_table_note("Reprinted from Nature 2021", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    def test_data_from(self):
        result = is_table_note("Data from the 2020 Census", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    def test_courtesy_of(self):
        result = is_table_note("Courtesy of the National Library", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")

    # --- Negative cases ---

    def test_no_table_anchor_returns_none(self):
        result = is_table_note("a Adjusted for age", "BODY", near_table=False)
        assert result is None

    def test_table_zone_returns_none(self):
        result = is_table_note("a Adjusted for age", "TABLE", near_table=True)
        assert result is None

    def test_normal_text_returns_none(self):
        result = is_table_note("The results indicate a positive trend.", "BODY", near_table=True)
        assert result is None

    def test_empty_text_returns_none(self):
        result = is_table_note("", "BODY", near_table=True)
        assert result is None

    def test_none_text_returns_none(self):
        result = is_table_note(None, "BODY", near_table=True)
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = is_table_note("   ", "BODY", near_table=True)
        assert result is None

    def test_source_before_letter(self):
        """Source/attribution check runs before letter check."""
        result = is_table_note("Source: a Adapted from original", "BODY", near_table=True)
        assert result == ("TSN", "table-source-note")


# ===================================================================
# _has_table_anchor
# ===================================================================

class TestHasTableAnchor:
    def test_t1_within_range(self):
        clfs = [_clf(i, "TXT") for i in range(5)]
        clfs[2] = _clf(2, "T1")
        assert _has_table_anchor(clfs, 3, range_=10) is True

    def test_tfn_within_range(self):
        clfs = [_clf(i, "TXT") for i in range(5)]
        clfs[4] = _clf(4, "TFN")
        assert _has_table_anchor(clfs, 2, range_=10) is True

    def test_tbl_prefix_within_range(self):
        clfs = [_clf(i, "TXT") for i in range(5)]
        clfs[0] = _clf(0, "TBL-FIRST")
        assert _has_table_anchor(clfs, 2, range_=10) is True

    def test_only_txt_neighbors(self):
        clfs = [_clf(i, "TXT") for i in range(5)]
        assert _has_table_anchor(clfs, 2, range_=10) is False

    def test_anchor_at_edge_of_range(self):
        clfs = [_clf(i, "TXT") for i in range(12)]
        clfs[0] = _clf(0, "T1")
        # index=10, range=10 → searches [0..10], T1 at index 0 is included
        assert _has_table_anchor(clfs, 10, range_=10) is True

    def test_anchor_beyond_range(self):
        clfs = [_clf(i, "TXT") for i in range(15)]
        clfs[0] = _clf(0, "T1")
        # index=12, range=10 → searches [2..12], T1 at index 0 is excluded
        assert _has_table_anchor(clfs, 12, range_=10) is False

    def test_self_not_counted(self):
        """The target index itself is not counted as a neighbor."""
        clfs = [_clf(i, "TXT") for i in range(3)]
        clfs[1] = _clf(1, "T1")
        assert _has_table_anchor(clfs, 1, range_=10) is False

    def test_tfn_prefix_match(self):
        clfs = [_clf(i, "TXT") for i in range(5)]
        clfs[3] = _clf(3, "TFN-BL-FIRST")
        assert _has_table_anchor(clfs, 1, range_=10) is True


# ===================================================================
# apply_table_note_overrides
# ===================================================================

class TestApplyTableNoteOverrides:
    def test_txt_to_tfn_lettered(self):
        blocks = [_block(1, "Table 1 Caption"), _block(2, "a Adjusted for age")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "T1"  # unchanged
        assert result[1]["tag"] == "TFN"

    def test_txt_to_tsn_source(self):
        blocks = [_block(1, "Table 1 Caption"), _block(2, "Source: Adapted from Smith")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TSN"

    def test_ref_n_to_tfn_symbol(self):
        """Motivating scenario: symbol note near table misclassified as REF-N."""
        blocks = [
            _block(1, "Table 1 Results"),
            _block(2, "Cell data"),
            _block(3, "† p < 0.05"),
        ]
        clfs = [_clf(1, "T1"), _clf(2, "T"), _clf(3, "REF-N")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[2]["tag"] == "TFN"

    def test_already_tfn_unchanged(self):
        blocks = [_block(1, "Table 1"), _block(2, "a Note text")]
        clfs = [_clf(1, "T1"), _clf(2, "TFN")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1] is clfs[1]  # identity — not modified

    def test_already_tsn_unchanged(self):
        blocks = [_block(1, "Table 1"), _block(2, "Source: data")]
        clfs = [_clf(1, "T1"), _clf(2, "TSN")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1] is clfs[1]

    def test_already_tfn_prefix_unchanged(self):
        blocks = [_block(1, "Table 1"), _block(2, "a Note text")]
        clfs = [_clf(1, "T1"), _clf(2, "TFN-FIRST")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1] is clfs[1]

    def test_table_zone_skipped(self):
        blocks = [
            _block(1, "Table 1"),
            _block(2, "a Note text", context_zone="TABLE"),
        ]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TXT"  # not overridden

    def test_no_table_anchor_unchanged(self):
        blocks = [_block(1, "Normal paragraph"), _block(2, "a Adjusted for age")]
        clfs = [_clf(1, "TXT"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TXT"

    def test_normal_text_near_table_unchanged(self):
        blocks = [_block(1, "Table 1"), _block(2, "The results show improvement")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TXT"

    def test_repair_metadata_set(self):
        blocks = [_block(1, "Table 1"), _block(2, "† Significant")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["repaired"] is True
        assert "table-footnote" in result[1]["repair_reason"]

    def test_preserves_existing_repair_reason(self):
        blocks = [_block(1, "Table 1"), _block(2, "† Significant")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT", repair_reason="heading-hierarchy")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TFN"
        assert "heading-hierarchy" in result[1]["repair_reason"]
        assert "table-footnote" in result[1]["repair_reason"]

    def test_allowed_styles_validation(self):
        """When TFN is not in allowed_styles, skip the override."""
        limited = {"TXT", "REF-N", "T1"}  # no TFN or TSN
        blocks = [_block(1, "Table 1"), _block(2, "a Note text")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, limited)
        assert result[1]["tag"] == "TXT"  # not overridden

    def test_allowed_styles_none_skips_validation(self):
        blocks = [_block(1, "Table 1"), _block(2, "a Note text")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, None)
        assert result[1]["tag"] == "TFN"

    def test_empty_classifications(self):
        result = apply_table_note_overrides([], [], ALLOWED)
        assert result == []

    def test_unchanged_entries_are_originals(self):
        blocks = [_block(1, "Normal text"), _block(2, "More text")]
        clfs = [_clf(1, "TXT"), _clf(2, "H1")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[0] is clfs[0]
        assert result[1] is clfs[1]

    def test_confidence_preserved(self):
        blocks = [_block(1, "Table 1"), _block(2, "a Adjusted")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT", conf=0.72)]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["confidence"] == 0.72

    def test_mixed_document_flow(self):
        """Only the table-note paragraph is rewritten in a mixed doc."""
        blocks = [
            _block(1, "Introduction"),
            _block(2, "Table 1 Results"),
            _block(3, "Cell data A"),
            _block(4, "Cell data B"),
            _block(5, "a Adjusted for age"),
            _block(6, "Source: WHO 2020"),
            _block(7, "Next section text"),
        ]
        clfs = [
            _clf(1, "H1"),
            _clf(2, "T1"),
            _clf(3, "T"),
            _clf(4, "T"),
            _clf(5, "REF-N"),
            _clf(6, "TXT"),
            _clf(7, "TXT"),
        ]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "H1", "T1", "T", "T", "TFN", "TSN", "TXT",
        ]

    def test_multiple_notes_after_table(self):
        blocks = [
            _block(1, "Table 1"),
            _block(2, "a Adjusted"),
            _block(3, "† p < 0.05"),
            _block(4, "Source: Data from census"),
        ]
        clfs = [
            _clf(1, "T1"),
            _clf(2, "TXT"),
            _clf(3, "TXT"),
            _clf(4, "TXT"),
        ]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TFN"
        assert result[2]["tag"] == "TFN"
        assert result[3]["tag"] == "TSN"

    def test_note_hash_symbol(self):
        blocks = [_block(1, "Table 1"), _block(2, "# Reference group")]
        clfs = [_clf(1, "T1"), _clf(2, "TXT")]
        result = apply_table_note_overrides(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "TFN"
