"""Tests for list-run position normalization."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.list_normalizer import _list_family, normalize_list_runs


# Shared allowed styles for tests — includes full triads for common
# families and MID-only for nested levels.
ALLOWED = {
    "BL-FIRST", "BL-MID", "BL-LAST",
    "NL-FIRST", "NL-MID", "NL-LAST",
    "UL-FIRST", "UL-MID", "UL-LAST",
    "BX1-BL-FIRST", "BX1-BL-MID", "BX1-BL-LAST",
    "BX1-NL-FIRST", "BX1-NL-MID", "BX1-NL-LAST",
    "NBX-BL-FIRST", "NBX-BL-MID", "NBX-BL-LAST",
    "TBL-FIRST", "TBL-MID", "TBL-LAST",
    "EOC-NL-FIRST", "EOC-NL-MID", "EOC-NL-LAST",
    "DIA-FIRST", "DIA-MID", "DIA-LAST",
    "BL2-MID",  # nested level — only MID exists
    "BL3-MID",
    "TXT", "H1", "H2", "PMI",
}


def _block(pid, text="Paragraph"):
    return {"id": pid, "text": text, "metadata": {}}


def _clf(pid, tag, conf=0.85, **extra):
    d = {"id": pid, "tag": tag, "confidence": conf}
    d.update(extra)
    return d


# ===================================================================
# _list_family
# ===================================================================

class TestListFamily:
    def test_bl_first(self):
        assert _list_family("BL-FIRST") == "BL"

    def test_bl_mid(self):
        assert _list_family("BL-MID") == "BL"

    def test_bl_last(self):
        assert _list_family("BL-LAST") == "BL"

    def test_bx1_bl_mid(self):
        assert _list_family("BX1-BL-MID") == "BX1-BL"

    def test_eoc_nl_last(self):
        assert _list_family("EOC-NL-LAST") == "EOC-NL"

    def test_tbl_first(self):
        assert _list_family("TBL-FIRST") == "TBL"

    def test_bl2_mid(self):
        assert _list_family("BL2-MID") == "BL2"

    def test_nbx_bl_first(self):
        assert _list_family("NBX-BL-FIRST") == "NBX-BL"

    def test_txt_returns_none(self):
        assert _list_family("TXT") is None

    def test_h1_returns_none(self):
        assert _list_family("H1") is None

    def test_empty_string(self):
        assert _list_family("") is None

    def test_none_input(self):
        assert _list_family(None) is None


# ===================================================================
# normalize_list_runs
# ===================================================================

class TestNormalizeListRuns:
    # --- correct sequence unchanged ---
    def test_already_correct_unchanged(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [_clf(1, "BL-FIRST"), _clf(2, "BL-MID"), _clf(3, "BL-LAST")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == ["BL-FIRST", "BL-MID", "BL-LAST"]
        # Unchanged entries should be the original objects
        assert result[0] is clfs[0]
        assert result[1] is clfs[1]
        assert result[2] is clfs[2]

    # --- all-MID rewritten ---
    def test_all_mid_rewritten(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [_clf(1, "BL-MID"), _clf(2, "BL-MID"), _clf(3, "BL-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == ["BL-FIRST", "BL-MID", "BL-LAST"]

    # --- double-FIRST corrected (motivating scenario) ---
    def test_double_first_corrected(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [_clf(1, "BL-FIRST"), _clf(2, "BL-FIRST"), _clf(3, "BL-LAST")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == ["BL-FIRST", "BL-MID", "BL-LAST"]

    # --- single item becomes FIRST ---
    def test_single_item_becomes_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "BL-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "BL-FIRST"

    def test_single_last_becomes_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "BL-LAST")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "BL-FIRST"

    # --- two items ---
    def test_two_items(self):
        blocks = [_block(1), _block(2)]
        clfs = [_clf(1, "BL-MID"), _clf(2, "BL-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == ["BL-FIRST", "BL-LAST"]

    # --- non-list breaks run ---
    def test_non_list_breaks_run(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [_clf(1, "BL-MID"), _clf(2, "TXT"), _clf(3, "BL-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "BL-FIRST"  # single-item run
        assert result[1]["tag"] == "TXT"        # unchanged
        assert result[2]["tag"] == "BL-FIRST"   # single-item run

    # --- different families break runs ---
    def test_different_families_break_runs(self):
        blocks = [_block(i) for i in range(1, 5)]
        clfs = [
            _clf(1, "BL-MID"), _clf(2, "BL-MID"),
            _clf(3, "NL-MID"), _clf(4, "NL-MID"),
        ]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "BL-FIRST", "BL-LAST", "NL-FIRST", "NL-LAST",
        ]

    # --- box variants normalize within their family ---
    def test_box_variants_normalize(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [
            _clf(1, "BX1-BL-FIRST"),
            _clf(2, "BX1-BL-FIRST"),  # wrong — should be MID
            _clf(3, "BX1-BL-LAST"),
        ]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "BX1-BL-FIRST", "BX1-BL-MID", "BX1-BL-LAST",
        ]

    # --- MID-only family preserved ---
    def test_mid_only_family_preserved(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [_clf(1, "BL2-MID"), _clf(2, "BL2-MID"), _clf(3, "BL2-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        # BL2-FIRST and BL2-LAST not in ALLOWED → all stay BL2-MID
        assert [c["tag"] for c in result] == ["BL2-MID", "BL2-MID", "BL2-MID"]

    # --- mixed document flow ---
    def test_mixed_document_flow(self):
        blocks = [_block(i) for i in range(1, 8)]
        clfs = [
            _clf(1, "H1"),
            _clf(2, "BL-MID"),
            _clf(3, "BL-MID"),
            _clf(4, "BL-MID"),
            _clf(5, "TXT"),
            _clf(6, "NL-MID"),
            _clf(7, "NL-MID"),
        ]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "H1",
            "BL-FIRST", "BL-MID", "BL-LAST",
            "TXT",
            "NL-FIRST", "NL-LAST",
        ]

    # --- repair metadata ---
    def test_repair_metadata_set(self):
        blocks = [_block(1), _block(2)]
        clfs = [_clf(1, "BL-MID"), _clf(2, "BL-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0]["repaired"] is True
        assert "list-run-norm" in result[0]["repair_reason"]
        assert result[1]["repaired"] is True
        assert "list-run-norm" in result[1]["repair_reason"]

    def test_preserves_existing_repair_reason(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "BL-LAST", repair_reason="heading-hierarchy")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "BL-FIRST"
        assert "heading-hierarchy" in result[0]["repair_reason"]
        assert "list-run-norm" in result[0]["repair_reason"]

    # --- allowed_styles=None skips validation ---
    def test_allowed_styles_none_skips_validation(self):
        blocks = [_block(1), _block(2)]
        clfs = [_clf(1, "BL2-MID"), _clf(2, "BL2-MID")]
        result = normalize_list_runs(blocks, clfs, None)
        # With no allowed check, BL2-FIRST and BL2-LAST are written
        assert [c["tag"] for c in result] == ["BL2-FIRST", "BL2-LAST"]

    # --- unchanged entries are originals (identity) ---
    def test_unchanged_entries_are_originals(self):
        blocks = [_block(1), _block(2)]
        clfs = [_clf(1, "TXT"), _clf(2, "H1")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0] is clfs[0]
        assert result[1] is clfs[1]

    # --- empty input ---
    def test_empty_classifications(self):
        result = normalize_list_runs([], [], ALLOWED)
        assert result == []

    # --- long run (5 items) ---
    def test_five_item_run(self):
        blocks = [_block(i) for i in range(1, 6)]
        clfs = [_clf(i, "NL-MID") for i in range(1, 6)]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "NL-FIRST", "NL-MID", "NL-MID", "NL-MID", "NL-LAST",
        ]

    # --- NBX family ---
    def test_nbx_family(self):
        blocks = [_block(1), _block(2), _block(3)]
        clfs = [
            _clf(1, "NBX-BL-MID"),
            _clf(2, "NBX-BL-MID"),
            _clf(3, "NBX-BL-MID"),
        ]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "NBX-BL-FIRST", "NBX-BL-MID", "NBX-BL-LAST",
        ]

    # --- body BL and box BX1-BL are separate families ---
    def test_body_and_box_are_separate_families(self):
        blocks = [_block(1), _block(2), _block(3), _block(4)]
        clfs = [
            _clf(1, "BL-MID"),
            _clf(2, "BL-MID"),
            _clf(3, "BX1-BL-MID"),
            _clf(4, "BX1-BL-MID"),
        ]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == [
            "BL-FIRST", "BL-LAST",
            "BX1-BL-FIRST", "BX1-BL-LAST",
        ]

    # --- confidence not modified ---
    def test_confidence_not_modified(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "BL-MID", conf=0.72)]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert result[0]["confidence"] == 0.72

    # --- EOC-NL family ---
    def test_eoc_nl_family(self):
        blocks = [_block(1), _block(2)]
        clfs = [_clf(1, "EOC-NL-MID"), _clf(2, "EOC-NL-MID")]
        result = normalize_list_runs(blocks, clfs, ALLOWED)
        assert [c["tag"] for c in result] == ["EOC-NL-FIRST", "EOC-NL-LAST"]
