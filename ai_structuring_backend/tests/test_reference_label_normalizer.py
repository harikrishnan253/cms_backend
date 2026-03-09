"""Tests for reference label normalization."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.reference_label_normalizer import normalize_reference_labels


def _ref_block(pid, text, **meta_overrides):
    """Helper to create reference block."""
    meta = {"context_zone": "BACK_MATTER", "tag": "REF-N"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# Duplicate number normalization
# ===================================================================

class TestDuplicateNormalization:
    """Test that duplicate numbers are fixed."""

    def test_duplicate_numbers_fixed(self):
        """Duplicate ref numbers → sequential."""
        blocks = [
            _ref_block(1, "1. First reference"),
            _ref_block(2, "2. Second reference"),
            _ref_block(3, "2. Third reference (duplicate)"),
            _ref_block(4, "3. Fourth reference"),
            _ref_block(5, "4. Fifth reference"),
        ]
        result = normalize_reference_labels(blocks)

        assert "1. First reference" in result[0]["text"]
        assert "2. Second reference" in result[1]["text"]
        assert "3. Third reference" in result[2]["text"]
        assert "4. Fourth reference" in result[3]["text"]
        assert "5. Fifth reference" in result[4]["text"]

    def test_multiple_duplicates_fixed(self):
        """Multiple duplicate numbers → all fixed."""
        blocks = [
            _ref_block(1, "[1] Ref A"),
            _ref_block(2, "[1] Ref B (dup)"),
            _ref_block(3, "[1] Ref C (dup)"),
            _ref_block(4, "[2] Ref D"),
            _ref_block(5, "[3] Ref E"),
        ]
        result = normalize_reference_labels(blocks)

        assert "[1] Ref A" in result[0]["text"]
        assert "[2] Ref B" in result[1]["text"]
        assert "[3] Ref C" in result[2]["text"]
        assert "[4] Ref D" in result[3]["text"]
        assert "[5] Ref E" in result[4]["text"]


# ===================================================================
# Gap filling normalization
# ===================================================================

class TestGapFilling:
    """Test that gaps in numbering are filled."""

    def test_gaps_filled(self):
        """Gaps in numbering (1, 2, 5, 7) → sequential (1, 2, 3, 4)."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "2. Second"),
            _ref_block(3, "5. Third (gap)"),
            _ref_block(4, "7. Fourth (gap)"),
            _ref_block(5, "10. Fifth (gap)"),
        ]
        result = normalize_reference_labels(blocks)

        assert "1. First" in result[0]["text"]
        assert "2. Second" in result[1]["text"]
        assert "3. Third" in result[2]["text"]
        assert "4. Fourth" in result[3]["text"]
        assert "5. Fifth" in result[4]["text"]

    def test_large_gap_filled(self):
        """Large gap (1, 2, 100) → sequential (1, 2, 3)."""
        blocks = [
            _ref_block(1, "(1) Ref A"),
            _ref_block(2, "(2) Ref B"),
            _ref_block(3, "(100) Ref C (large gap)"),
            _ref_block(4, "(101) Ref D"),
            _ref_block(5, "(200) Ref E"),
        ]
        result = normalize_reference_labels(blocks)

        assert "(1) Ref A" in result[0]["text"]
        assert "(2) Ref B" in result[1]["text"]
        assert "(3) Ref C" in result[2]["text"]
        assert "(4) Ref D" in result[3]["text"]
        assert "(5) Ref E" in result[4]["text"]


# ===================================================================
# Mixed format normalization
# ===================================================================

class TestMixedFormatNormalization:
    """Test that mixed formats normalize to first format."""

    def test_mixed_formats_to_first_bracket(self):
        """Mixed [1], 2., (3) → all [N]."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "2. Second (different format)"),
            _ref_block(3, "(3) Third (different format)"),
            _ref_block(4, "4) Fourth (different format)"),
            _ref_block(5, "[5] Fifth"),
        ]
        result = normalize_reference_labels(blocks)

        assert "[1] First" in result[0]["text"]
        assert "[2] Second" in result[1]["text"]
        assert "[3] Third" in result[2]["text"]
        assert "[4] Fourth" in result[3]["text"]
        assert "[5] Fifth" in result[4]["text"]

    def test_mixed_formats_to_first_period(self):
        """Mixed 1., [2], (3) → all N."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "[2] Second (different format)"),
            _ref_block(3, "(3) Third (different format)"),
            _ref_block(4, "4) Fourth (different format)"),
            _ref_block(5, "5. Fifth"),
        ]
        result = normalize_reference_labels(blocks)

        assert "1. First" in result[0]["text"]
        assert "2. Second" in result[1]["text"]
        assert "3. Third" in result[2]["text"]
        assert "4. Fourth" in result[3]["text"]
        assert "5. Fifth" in result[4]["text"]

    def test_mixed_formats_to_first_paren(self):
        """Mixed (1), 2., [3] → all (N)."""
        blocks = [
            _ref_block(1, "(1) First"),
            _ref_block(2, "2. Second (different format)"),
            _ref_block(3, "[3] Third (different format)"),
            _ref_block(4, "(4) Fourth"),
            _ref_block(5, "5) Fifth (different format)"),
        ]
        result = normalize_reference_labels(blocks)

        assert "(1) First" in result[0]["text"]
        assert "(2) Second" in result[1]["text"]
        assert "(3) Third" in result[2]["text"]
        assert "(4) Fourth" in result[3]["text"]
        assert "(5) Fifth" in result[4]["text"]


# ===================================================================
# Minimum threshold test
# ===================================================================

class TestMinimumThreshold:
    """Test that normalization only happens with ≥ N entries."""

    def test_less_than_5_entries_no_normalization(self):
        """< 5 labeled entries → no normalization."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "5. Second (gap)"),
            _ref_block(3, "10. Third (gap)"),
            _ref_block(4, "10. Fourth (duplicate)"),
        ]
        # Only 4 entries, default min is 5
        result = normalize_reference_labels(blocks)

        # Should NOT be normalized (text unchanged)
        assert "1. First" in result[0]["text"]
        assert "5. Second" in result[1]["text"]
        assert "10. Third" in result[2]["text"]
        assert "10. Fourth" in result[3]["text"]

    def test_exactly_5_entries_normalized(self):
        """Exactly 5 labeled entries → normalized."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "[5] Second (gap)"),
            _ref_block(3, "[10] Third (gap)"),
            _ref_block(4, "[10] Fourth (duplicate)"),
            _ref_block(5, "[20] Fifth (gap)"),
        ]
        result = normalize_reference_labels(blocks)

        # Should be normalized
        assert "[1] First" in result[0]["text"]
        assert "[2] Second" in result[1]["text"]
        assert "[3] Third" in result[2]["text"]
        assert "[4] Fourth" in result[3]["text"]
        assert "[5] Fifth" in result[4]["text"]

    def test_custom_min_threshold(self):
        """Custom min_labeled_entries=3 → normalizes with 3 entries."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "5. Second (gap)"),
            _ref_block(3, "10. Third (gap)"),
        ]
        result = normalize_reference_labels(blocks, min_labeled_entries=3)

        # Should be normalized with custom threshold
        assert "1. First" in result[0]["text"]
        assert "2. Second" in result[1]["text"]
        assert "3. Third" in result[2]["text"]


# ===================================================================
# Unlabeled entries preservation
# ===================================================================

class TestUnlabeledPreservation:
    """Test that unlabeled entries are preserved."""

    def test_unlabeled_entries_preserved(self):
        """Unlabeled references → left unchanged."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "[2] Second"),
            _ref_block(3, "Author A, Title B, 2020. (unlabeled)"),
            _ref_block(4, "[3] Fourth"),
            _ref_block(5, "Another unlabeled reference"),
            _ref_block(6, "[4] Sixth"),
        ]
        result = normalize_reference_labels(blocks)

        # Labeled ones renumbered
        assert "[1] First" in result[0]["text"]
        assert "[2] Second" in result[1]["text"]
        assert "[3] Fourth" in result[3]["text"]
        assert "[4] Sixth" in result[5]["text"]

        # Unlabeled ones unchanged
        assert "Author A, Title B, 2020" in result[2]["text"]
        assert "Another unlabeled" in result[4]["text"]

    def test_mixed_labeled_unlabeled_sequential(self):
        """Labeled entries renumber sequentially, skipping unlabeled."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "Unlabeled A"),
            _ref_block(3, "2. Second"),
            _ref_block(4, "Unlabeled B"),
            _ref_block(5, "3. Third"),
            _ref_block(6, "4. Fourth"),
        ]
        result = normalize_reference_labels(blocks, min_labeled_entries=4)

        assert "1. First" in result[0]["text"]
        assert "Unlabeled A" in result[1]["text"]
        assert "2. Second" in result[2]["text"]
        assert "Unlabeled B" in result[3]["text"]
        assert "3. Third" in result[4]["text"]
        assert "4. Fourth" in result[5]["text"]


# ===================================================================
# Marker line preservation
# ===================================================================

class TestMarkerPreservation:
    """Test that marker lines are never modified."""

    def test_marker_lines_preserved(self):
        """Marker lines like <REF>, <REFH1> → never modified."""
        blocks = [
            _ref_block(1, "<REF>", tag="PMI"),
            _ref_block(2, "1. First reference"),
            _ref_block(3, "<REFH1>References", tag="REFH1"),
            _ref_block(4, "2. Second reference"),
            _ref_block(5, "3. Third reference"),
            _ref_block(6, "4. Fourth reference"),
            _ref_block(7, "5. Fifth reference"),
        ]
        result = normalize_reference_labels(blocks)

        # Markers unchanged
        assert result[0]["text"] == "<REF>"
        assert result[2]["text"] == "<REFH1>References"

        # References renumbered (only 5 labeled entries)
        assert "1. First" in result[1]["text"]
        assert "2. Second" in result[3]["text"]


# ===================================================================
# Text preservation
# ===================================================================

class TestTextPreservation:
    """Test that reference content is preserved exactly."""

    def test_content_after_label_preserved(self):
        """Only label changed, content after label preserved exactly."""
        blocks = [
            _ref_block(1, "[1] Author, A., & Author, B. (2020). Title of paper. Journal Name, 10(2), 123-145."),
            _ref_block(2, "[5] Smith, J. (2019). Another paper. Different Journal, 5(1), 1-10."),
            _ref_block(3, "[10] Jones, K., et al. (2021). Third paper with DOI. Nature, 500, 200-205. doi:10.1038/nature12345"),
            _ref_block(4, "[11] Final reference with URL. Available at: http://example.com"),
            _ref_block(5, "[100] Last one with very long gap."),
        ]
        result = normalize_reference_labels(blocks)

        # Check labels changed
        assert result[0]["text"].startswith("[1] ")
        assert result[1]["text"].startswith("[2] ")
        assert result[2]["text"].startswith("[3] ")
        assert result[3]["text"].startswith("[4] ")
        assert result[4]["text"].startswith("[5] ")

        # Check content preserved
        assert "Author, A., & Author, B. (2020)" in result[0]["text"]
        assert "Smith, J. (2019)" in result[1]["text"]
        assert "doi:10.1038/nature12345" in result[2]["text"]
        assert "http://example.com" in result[3]["text"]
        assert "Last one with very long gap" in result[4]["text"]

    def test_whitespace_preserved(self):
        """Whitespace after label preserved."""
        blocks = [
            _ref_block(1, "1.  First with double space"),
            _ref_block(2, "2.   Second with triple space"),
            _ref_block(3, "3.\tThird with tab"),
            _ref_block(4, "4. Fourth normal"),
            _ref_block(5, "5.     Fifth with many spaces"),
        ]
        result = normalize_reference_labels(blocks)

        # All should have normalized labels
        assert all("First with double space" in result[0]["text"] for _ in [1])
        assert all("Second with triple space" in result[1]["text"] for _ in [1])
        assert all("Third with tab" in result[2]["text"] for _ in [1])


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:

    def test_empty_blocks(self):
        """Empty blocks list → returns empty."""
        result = normalize_reference_labels([])
        assert result == []

    def test_no_reference_zone(self):
        """No BACK_MATTER zone → no normalization."""
        blocks = [
            {"id": 1, "text": "1. Regular text", "metadata": {"context_zone": "BODY"}},
            {"id": 2, "text": "2. More text", "metadata": {"context_zone": "BODY"}},
        ]
        result = normalize_reference_labels(blocks)
        # Text unchanged
        assert result[0]["text"] == "1. Regular text"
        assert result[1]["text"] == "2. More text"

    def test_no_labeled_entries(self):
        """All entries unlabeled → no normalization."""
        blocks = [
            _ref_block(1, "Author A. Title. Journal."),
            _ref_block(2, "Author B. Another title."),
            _ref_block(3, "Author C. Third title."),
        ]
        result = normalize_reference_labels(blocks)
        # Text unchanged
        assert result[0]["text"] == "Author A. Title. Journal."

    def test_identity_preserved(self):
        """Returned blocks are same objects (in-place modification)."""
        blocks = [
            _ref_block(1, "[1] Ref A"),
            _ref_block(2, "[2] Ref B"),
            _ref_block(3, "[3] Ref C"),
            _ref_block(4, "[4] Ref D"),
            _ref_block(5, "[5] Ref E"),
        ]
        result = normalize_reference_labels(blocks)
        assert result[0] is blocks[0]
        assert result[1] is blocks[1]

    def test_returns_list(self):
        """Function returns list."""
        blocks = [_ref_block(i, f"[{i}] Ref") for i in range(1, 6)]
        result = normalize_reference_labels(blocks)
        assert isinstance(result, list)

    def test_whitespace_only_blocks_skipped(self):
        """Whitespace-only blocks → skipped."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "   "),
            _ref_block(3, "[2] Third"),
            _ref_block(4, ""),
            _ref_block(5, "[3] Fifth"),
            _ref_block(6, "[4] Sixth"),
            _ref_block(7, "[5] Seventh"),
        ]
        result = normalize_reference_labels(blocks)

        assert "[1] First" in result[0]["text"]
        assert result[1]["text"].strip() == ""
        assert "[2] Third" in result[2]["text"]


# ===================================================================
# Label format detection
# ===================================================================

class TestLabelFormatDetection:
    """Test various label formats are detected correctly."""

    def test_bracket_format_detected(self):
        """[N] format detected and used."""
        blocks = [_ref_block(i, f"[{i}] Ref {i}") for i in range(1, 6)]
        result = normalize_reference_labels(blocks)
        assert all(f"[{i}] Ref" in result[i-1]["text"] for i in range(1, 6))

    def test_paren_format_detected(self):
        """(N) format detected and used."""
        blocks = [_ref_block(i, f"({i}) Ref {i}") for i in range(1, 6)]
        result = normalize_reference_labels(blocks)
        assert all(f"({i}) Ref" in result[i-1]["text"] for i in range(1, 6))

    def test_period_format_detected(self):
        """N. format detected and used."""
        blocks = [_ref_block(i, f"{i}. Ref {i}") for i in range(1, 6)]
        result = normalize_reference_labels(blocks)
        assert all(f"{i}. Ref" in result[i-1]["text"] for i in range(1, 6))

    def test_paren_suffix_format_detected(self):
        """N) format detected and used."""
        blocks = [_ref_block(i, f"{i}) Ref {i}") for i in range(1, 6)]
        result = normalize_reference_labels(blocks)
        assert all(f"{i}) Ref" in result[i-1]["text"] for i in range(1, 6))


# ===================================================================
# Logging
# ===================================================================

class TestLogging:
    """Test logging output."""

    def test_logs_normalization_info(self, caplog):
        """Logs REF_NUM_NORMALIZED with counts."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [_ref_block(i, f"[{i}] Ref") for i in range(1, 6)]
        normalize_reference_labels(blocks)

        # Should log normalization info
        assert any("REF_NUM_NORMALIZED" in record.message for record in caplog.records)
        assert any("count_entries=5" in record.message for record in caplog.records)
        assert any("count_labeled=5" in record.message for record in caplog.records)

    def test_logs_no_normalization_when_skipped(self, caplog):
        """Logs debug when normalization skipped."""
        import logging
        caplog.set_level(logging.DEBUG)

        blocks = [_ref_block(i, f"[{i}] Ref") for i in range(1, 4)]  # Only 3
        normalize_reference_labels(blocks)

        # Should log skip reason
        debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("only 3 labeled entries" in msg for msg in debug_msgs)
