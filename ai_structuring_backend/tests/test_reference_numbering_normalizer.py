"""Tests for deterministic reference numbering normalization."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.reference_numbering_normalizer import normalize_reference_numbering, HOUSE_FORMAT


def _ref_block(pid, text, tag="REF-N"):
    """Helper to create reference block."""
    meta = {"context_zone": "BACK_MATTER", "tag": tag}
    return {"id": pid, "text": text, "tag": tag, "metadata": meta}


# ===================================================================
# Already-correct numbering (no changes)
# ===================================================================

class TestAlreadyCorrect:
    """Test that correct numbering is left unchanged."""

    def test_already_correct_no_changes(self):
        """Already correctly numbered → no changes."""
        blocks = [
            _ref_block(1, "1. First reference entry"),
            _ref_block(2, "2. Second reference entry"),
            _ref_block(3, "3. Third reference entry"),
        ]
        original_texts = [b["text"] for b in blocks]
        result = normalize_reference_numbering(blocks)

        # Text unchanged
        result_texts = [b["text"] for b in result]
        assert result_texts == original_texts

    def test_already_correct_house_format(self):
        """Already using house format (1. ) → no changes."""
        blocks = [
            _ref_block(1, "1. Smith, J. (2020). Paper title."),
            _ref_block(2, "2. Jones, K. (2019). Another paper."),
            _ref_block(3, "3. Brown, L. (2021). Third paper."),
        ]
        original = [b["text"] for b in blocks]
        result = normalize_reference_numbering(blocks)

        assert [b["text"] for b in result] == original


# ===================================================================
# Mixed numbering styles normalized
# ===================================================================

class TestMixedStyles:
    """Test that mixed formats are normalized to house format."""

    def test_bracket_format_normalized(self):
        """[1], [2], [3] → 1., 2., 3."""
        blocks = [
            _ref_block(1, "[1] First reference"),
            _ref_block(2, "[2] Second reference"),
            _ref_block(3, "[3] Third reference"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First reference"
        assert result[1]["text"] == "2. Second reference"
        assert result[2]["text"] == "3. Third reference"

    def test_paren_format_normalized(self):
        """(1), (2), (3) → 1., 2., 3."""
        blocks = [
            _ref_block(1, "(1) First reference"),
            _ref_block(2, "(2) Second reference"),
            _ref_block(3, "(3) Third reference"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First reference"
        assert result[1]["text"] == "2. Second reference"
        assert result[2]["text"] == "3. Third reference"

    def test_paren_suffix_normalized(self):
        """1), 2), 3) → 1., 2., 3."""
        blocks = [
            _ref_block(1, "1) First reference"),
            _ref_block(2, "2) Second reference"),
            _ref_block(3, "3) Third reference"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First reference"
        assert result[1]["text"] == "2. Second reference"
        assert result[2]["text"] == "3. Third reference"

    def test_mixed_formats_unified(self):
        """Mixed [1], 2), (3), 4. → all 1., 2., 3., 4."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "2) Second"),
            _ref_block(3, "(3) Third"),
            _ref_block(4, "4. Fourth"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First"
        assert result[1]["text"] == "2. Second"
        assert result[2]["text"] == "3. Third"
        assert result[3]["text"] == "4. Fourth"


# ===================================================================
# Missing numbers / gaps fixed
# ===================================================================

class TestGapsFixed:
    """Test that gaps in numbering are fixed."""

    def test_gaps_filled_sequential(self):
        """1, 2, 5, 7 → 1, 2, 3, 4."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "2. Second"),
            _ref_block(3, "5. Third (was 5)"),
            _ref_block(4, "7. Fourth (was 7)"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First"
        assert result[1]["text"] == "2. Second"
        assert result[2]["text"] == "3. Third (was 5)"
        assert result[3]["text"] == "4. Fourth (was 7)"

    def test_large_gap_normalized(self):
        """1, 2, 100 → 1, 2, 3."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "2. Second"),
            _ref_block(3, "100. Third (huge gap)"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First"
        assert result[1]["text"] == "2. Second"
        assert result[2]["text"] == "3. Third (huge gap)"

    def test_duplicate_numbers_sequential(self):
        """1, 2, 2, 3 → 1, 2, 3, 4."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "2. Second"),
            _ref_block(3, "2. Third (duplicate)"),
            _ref_block(4, "3. Fourth"),
        ]
        result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == "1. First"
        assert result[1]["text"] == "2. Second"
        assert result[2]["text"] == "3. Third (duplicate)"
        assert result[3]["text"] == "4. Fourth"


# ===================================================================
# Text content preserved (only prefix changed)
# ===================================================================

class TestTextPreserved:
    """Test that reference text content is preserved."""

    def test_full_citation_preserved(self):
        """Full citation text preserved, only number changes."""
        blocks = [
            _ref_block(1, "[1] Smith, J., & Jones, K. (2020). Title of paper. Journal Name, 10(2), 123-145. https://doi.org/10.1234/example"),
            _ref_block(2, "(2) Brown, L. (2019). Another paper title. Different Journal, 5(1), 1-10."),
            _ref_block(3, "5. Wilson, M., et al. (2021). Third paper. Nature, 500, 200-205."),
        ]
        result = normalize_reference_numbering(blocks)

        # Check prefixes changed
        assert result[0]["text"].startswith("1. ")
        assert result[1]["text"].startswith("2. ")
        assert result[2]["text"].startswith("3. ")

        # Check content preserved
        assert "Smith, J., & Jones, K. (2020)" in result[0]["text"]
        assert "https://doi.org/10.1234/example" in result[0]["text"]
        assert "Brown, L. (2019)" in result[1]["text"]
        assert "Wilson, M., et al. (2021)" in result[2]["text"]

    def test_special_characters_preserved(self):
        """Special characters in references preserved."""
        blocks = [
            _ref_block(1, "[1] Author (2020). Title with—dash & ampersand."),
            _ref_block(2, "2. Author (2019). Title with 'quotes' and \"double quotes\"."),
            _ref_block(3, "(3) Author (2021). Title with [brackets] and (parens)."),
        ]
        result = normalize_reference_numbering(blocks)

        assert "Title with—dash & ampersand" in result[0]["text"]
        assert "Title with 'quotes' and \"double quotes\"" in result[1]["text"]
        assert "Title with [brackets] and (parens)" in result[2]["text"]


# ===================================================================
# Idempotency test
# ===================================================================

class TestIdempotency:
    """Test that running twice produces identical output."""

    def test_idempotent_single_run(self):
        """Running twice on same input → identical output."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "(2) Second"),
            _ref_block(3, "5) Third"),
        ]

        # First run
        result1 = normalize_reference_numbering(blocks)
        texts1 = [b["text"] for b in result1]

        # Second run on same blocks
        result2 = normalize_reference_numbering(result1)
        texts2 = [b["text"] for b in result2]

        # Should be identical
        assert texts1 == texts2

    def test_idempotent_already_correct(self):
        """Running on already-correct input → no changes."""
        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "2. Second"),
            _ref_block(3, "3. Third"),
        ]
        original = [b["text"] for b in blocks]

        # Run normalization
        result = normalize_reference_numbering(blocks)
        after_first = [b["text"] for b in result]

        # Should be unchanged
        assert after_first == original

        # Run again
        result2 = normalize_reference_numbering(result)
        after_second = [b["text"] for b in result2]

        # Should still be unchanged
        assert after_second == original

    def test_idempotent_multiple_runs(self):
        """Running 5 times → stable after first normalization."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "(5) Second"),
            _ref_block(3, "10) Third"),
        ]

        results = []
        current = blocks
        for _ in range(5):
            current = normalize_reference_numbering(current)
            results.append([b["text"] for b in current])

        # All runs after first should be identical
        for i in range(1, len(results)):
            assert results[i] == results[0]


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:

    def test_empty_blocks(self):
        """Empty blocks list → returns empty."""
        result = normalize_reference_numbering([])
        assert result == []

    def test_no_reference_blocks(self):
        """No reference blocks → no changes."""
        blocks = [
            {"id": 1, "text": "Normal text", "tag": "TXT", "metadata": {"context_zone": "BODY"}},
            {"id": 2, "text": "More text", "tag": "TXT", "metadata": {"context_zone": "BODY"}},
        ]
        original = [b["text"] for b in blocks]
        result = normalize_reference_numbering(blocks)
        assert [b["text"] for b in result] == original

    def test_no_numbered_entries(self):
        """Reference blocks without numbers → no changes."""
        blocks = [
            _ref_block(1, "Author A. Title. Journal."),
            _ref_block(2, "Author B. Another title."),
        ]
        original = [b["text"] for b in blocks]
        result = normalize_reference_numbering(blocks)
        assert [b["text"] for b in result] == original

    def test_whitespace_handling(self):
        """Extra whitespace handled correctly."""
        blocks = [
            _ref_block(1, "1.  First (double space)"),
            _ref_block(2, "2.   Second (triple space)"),
            _ref_block(3, "3.\tThird (tab)"),
        ]
        result = normalize_reference_numbering(blocks)

        # All should have normalized to single space after number
        assert result[0]["text"] == "1. First (double space)"
        assert result[1]["text"] == "2. Second (triple space)"
        assert result[2]["text"] == "3. Third (tab)"

    def test_marker_blocks_skipped(self):
        """Marker blocks like <REF>, <REFH1> → skipped."""
        blocks = [
            _ref_block(1, "<REF>", tag="PMI"),
            _ref_block(2, "1. First reference", tag="REF-N"),
            _ref_block(3, "<REFH1>", tag="REFH1"),
            _ref_block(4, "2. Second reference", tag="REF-N"),
        ]
        result = normalize_reference_numbering(blocks)

        # Markers unchanged
        assert result[0]["text"] == "<REF>"
        assert result[2]["text"] == "<REFH1>"

        # References normalized
        assert result[1]["text"] == "1. First reference"
        assert result[3]["text"] == "2. Second reference"

    def test_identity_preserved(self):
        """Returned blocks are same objects (in-place modification)."""
        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "[2] Second"),
        ]
        result = normalize_reference_numbering(blocks)
        assert result[0] is blocks[0]
        assert result[1] is blocks[1]

    def test_returns_list(self):
        """Function returns list."""
        blocks = [_ref_block(1, "1. First")]
        result = normalize_reference_numbering(blocks)
        assert isinstance(result, list)


# ===================================================================
# Logging
# ===================================================================

class TestLogging:
    """Test structured logging output."""

    def test_logs_normalization_changed_true(self, caplog):
        """Logs REFERENCE_NORMALIZATION with changed=true when modified."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "(2) Second"),
        ]
        normalize_reference_numbering(blocks)

        # Should log normalization
        assert any("REFERENCE_NORMALIZATION" in record.message for record in caplog.records)
        assert any("changed=true" in record.message for record in caplog.records)
        assert any("renumbered=2" in record.message for record in caplog.records)

    def test_logs_normalization_changed_false(self, caplog):
        """Logs REFERENCE_NORMALIZATION with changed=false when already correct."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [
            _ref_block(1, "1. First"),
            _ref_block(2, "2. Second"),
        ]
        normalize_reference_numbering(blocks)

        # Should log no change
        assert any("REFERENCE_NORMALIZATION" in record.message for record in caplog.records)
        assert any("changed=false" in record.message for record in caplog.records)
        assert any("renumbered=0" in record.message for record in caplog.records)

    def test_logs_counts(self, caplog):
        """Logs before_count and after_count."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [
            _ref_block(1, "[1] First"),
            _ref_block(2, "[2] Second"),
            _ref_block(3, "[3] Third"),
        ]
        normalize_reference_numbering(blocks)

        messages = [r.message for r in caplog.records if "REFERENCE_NORMALIZATION" in r.message]
        assert len(messages) == 1
        assert "before_count=3" in messages[0]
        assert "after_count=3" in messages[0]
