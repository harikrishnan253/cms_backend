"""Tests for list hierarchy preservation from Word XML."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.list_preservation import enforce_list_hierarchy_from_word_xml


def _block(pid, text, **meta_overrides):
    """Helper to create block with metadata."""
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


def _clf(pid, tag, **extras):
    """Helper to create classification."""
    return {"id": pid, "tag": tag, "confidence": 85, **extras}


# ===================================================================
# Nested bullets preserved
# ===================================================================

class TestNestedBullets:
    """Test that nested bullet lists stay nested."""

    def test_nested_bullets_two_levels(self):
        """Two-level bullet list preserved."""
        blocks = [
            _block(1, "• Item 1", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(2, "  • Item 1.1", xml_list_level=1, has_bullet=True, xml_num_id=1),
            _block(3, "  • Item 1.2", xml_list_level=1, has_bullet=True, xml_num_id=1),
            _block(4, "• Item 2", xml_list_level=0, has_bullet=True, xml_num_id=1),
        ]
        clfs = [
            _clf(1, "BL-MID"),
            _clf(2, "BL2-MID"),
            _clf(3, "BL2-MID"),
            _clf(4, "BL-MID"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # All should remain correct
        assert result[0]["tag"] == "BL-MID"
        assert result[1]["tag"] == "BL2-MID"
        assert result[2]["tag"] == "BL2-MID"
        assert result[3]["tag"] == "BL-MID"

    def test_nested_bullets_three_levels(self):
        """Three-level bullet list preserved."""
        blocks = [
            _block(1, "• L0", xml_list_level=0, has_bullet=True),
            _block(2, "  • L1", xml_list_level=1, has_bullet=True),
            _block(3, "    • L2", xml_list_level=2, has_bullet=True),
        ]
        clfs = [
            _clf(1, "TXT"),  # LLM misclassified
            _clf(2, "TXT"),  # LLM misclassified
            _clf(3, "TXT"),  # LLM misclassified
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Should be corrected
        assert result[0]["tag"] == "BL-MID"
        assert result[1]["tag"] == "BL2-MID"
        assert result[2]["tag"] == "BL3-MID"

    def test_nested_bullets_max_level(self):
        """Four levels of nesting (max supported)."""
        blocks = [
            _block(1, "• L0", xml_list_level=0, has_bullet=True),
            _block(2, "  • L1", xml_list_level=1, has_bullet=True),
            _block(3, "    • L2", xml_list_level=2, has_bullet=True),
            _block(4, "      • L3", xml_list_level=3, has_bullet=True),
        ]
        clfs = [
            _clf(1, "BL-MID"),
            _clf(2, "BL2-MID"),
            _clf(3, "BL3-MID"),
            _clf(4, "BL4-MID"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "BL-MID"
        assert result[1]["tag"] == "BL2-MID"
        assert result[2]["tag"] == "BL3-MID"
        assert result[3]["tag"] == "BL4-MID"


# ===================================================================
# Numbered lists preserved
# ===================================================================

class TestNumberedLists:
    """Test that numbered lists stay numbered."""

    def test_numbered_list_flat(self):
        """Simple numbered list preserved."""
        blocks = [
            _block(1, "1. First", xml_list_level=0, has_numbering=True),
            _block(2, "2. Second", xml_list_level=0, has_numbering=True),
            _block(3, "3. Third", xml_list_level=0, has_numbering=True),
        ]
        clfs = [
            _clf(1, "NL-MID"),
            _clf(2, "NL-MID"),
            _clf(3, "NL-MID"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "NL-MID"
        assert result[1]["tag"] == "NL-MID"
        assert result[2]["tag"] == "NL-MID"

    def test_numbered_list_nested(self):
        """Nested numbered list preserved."""
        blocks = [
            _block(1, "1. First", xml_list_level=0, has_numbering=True),
            _block(2, "  a. Sub", xml_list_level=1, has_numbering=True),
            _block(3, "  b. Sub", xml_list_level=1, has_numbering=True),
            _block(4, "2. Second", xml_list_level=0, has_numbering=True),
        ]
        clfs = [
            _clf(1, "NL-MID"),
            _clf(2, "NL2-MID"),
            _clf(3, "NL2-MID"),
            _clf(4, "NL-MID"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "NL-MID"
        assert result[1]["tag"] == "NL2-MID"
        assert result[2]["tag"] == "NL2-MID"
        assert result[3]["tag"] == "NL-MID"


# ===================================================================
# Mixed lists preserved
# ===================================================================

class TestMixedLists:
    """Test mixed bullet and numbered lists."""

    def test_bullet_then_numbered(self):
        """Bullet list followed by numbered list."""
        blocks = [
            _block(1, "• Bullet", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(2, "• Bullet", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(3, "1. Number", xml_list_level=0, has_numbering=True, xml_num_id=2),
            _block(4, "2. Number", xml_list_level=0, has_numbering=True, xml_num_id=2),
        ]
        clfs = [
            _clf(1, "BL-MID"),
            _clf(2, "BL-MID"),
            _clf(3, "NL-MID"),
            _clf(4, "NL-MID"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "BL-MID"
        assert result[1]["tag"] == "BL-MID"
        assert result[2]["tag"] == "NL-MID"
        assert result[3]["tag"] == "NL-MID"

    def test_nested_mixed_types(self):
        """Nested list with mixed types."""
        blocks = [
            _block(1, "1. Number", xml_list_level=0, has_numbering=True),
            _block(2, "  • Bullet sub", xml_list_level=1, has_bullet=True),
            _block(3, "  • Bullet sub", xml_list_level=1, has_bullet=True),
            _block(4, "2. Number", xml_list_level=0, has_numbering=True),
        ]
        clfs = [
            _clf(1, "NL-MID"),
            _clf(2, "BL2-MID"),
            _clf(3, "BL2-MID"),
            _clf(4, "NL-MID"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "NL-MID"
        assert result[1]["tag"] == "BL2-MID"
        assert result[2]["tag"] == "BL2-MID"
        assert result[3]["tag"] == "NL-MID"


# ===================================================================
# LLM misclassification corrected
# ===================================================================

class TestLLMMisclassification:
    """Test correction of LLM misclassifications."""

    def test_list_item_tagged_as_txt(self):
        """LLM tags list item as body text → corrected."""
        blocks = [
            _block(1, "• Item 1", xml_list_level=0, has_bullet=True),
            _block(2, "• Item 2", xml_list_level=0, has_bullet=True),
        ]
        clfs = [
            _clf(1, "TXT"),  # Wrong
            _clf(2, "TXT"),  # Wrong
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Should be corrected to BL-MID
        assert result[0]["tag"] == "BL-MID"
        assert result[0]["list_preserved"] is True
        assert result[0]["original_tag"] == "TXT"
        assert result[1]["tag"] == "BL-MID"

    def test_wrong_list_level(self):
        """LLM tags nested item as top-level → corrected."""
        blocks = [
            _block(1, "• Top", xml_list_level=0, has_bullet=True),
            _block(2, "  • Nested", xml_list_level=1, has_bullet=True),
        ]
        clfs = [
            _clf(1, "BL-MID"),
            _clf(2, "BL-MID"),  # Should be BL2-MID
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "BL-MID"
        assert result[1]["tag"] == "BL2-MID"
        assert result[1]["list_preserved"] is True

    def test_wrong_list_type(self):
        """LLM tags numbered as bullet → corrected."""
        blocks = [
            _block(1, "1. Number", xml_list_level=0, has_numbering=True),
        ]
        clfs = [
            _clf(1, "BL-MID"),  # Should be NL-MID
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "NL-MID"

    def test_partial_correction(self):
        """Some items correct, some need correction."""
        blocks = [
            _block(1, "• Item 1", xml_list_level=0, has_bullet=True),
            _block(2, "• Item 2", xml_list_level=0, has_bullet=True),
            _block(3, "• Item 3", xml_list_level=0, has_bullet=True),
        ]
        clfs = [
            _clf(1, "BL-MID"),  # Correct
            _clf(2, "TXT"),     # Wrong
            _clf(3, "BL-MID"),  # Correct
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "BL-MID"
        assert "list_preserved" not in result[0]  # No override needed
        assert result[1]["tag"] == "BL-MID"
        assert result[1]["list_preserved"] is True  # Corrected
        assert result[2]["tag"] == "BL-MID"


# ===================================================================
# Non-list paragraphs unchanged
# ===================================================================

class TestNonListParagraphs:
    """Test that non-list paragraphs are not affected."""

    def test_body_text_unchanged(self):
        """Body text without list metadata → unchanged."""
        blocks = [
            _block(1, "Normal paragraph"),
            _block(2, "Another paragraph"),
        ]
        clfs = [
            _clf(1, "TXT"),
            _clf(2, "TXT"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "TXT"
        assert result[1]["tag"] == "TXT"

    def test_mixed_content(self):
        """List items mixed with body text."""
        blocks = [
            _block(1, "Introduction", xml_list_level=None),
            _block(2, "• Item", xml_list_level=0, has_bullet=True),
            _block(3, "Conclusion", xml_list_level=None),
        ]
        clfs = [
            _clf(1, "TXT"),
            _clf(2, "BL-MID"),
            _clf(3, "TXT"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert result[0]["tag"] == "TXT"
        assert result[1]["tag"] == "BL-MID"
        assert result[2]["tag"] == "TXT"


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_blocks(self):
        """Empty blocks list → returns empty."""
        result = enforce_list_hierarchy_from_word_xml([], [])
        assert result == []

    def test_empty_classifications(self):
        """Empty classifications → returns empty."""
        blocks = [_block(1, "• Item", xml_list_level=0, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks, [])
        assert result == []

    def test_ambiguous_xml_list(self):
        """XML list with unclear type (has_xml_list flag)."""
        blocks = [
            _block(1, "• Item", xml_list_level=0, has_xml_list=True),
        ]
        clfs = [
            _clf(1, "TXT"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Should default to bullet
        assert result[0]["tag"] == "BL-MID"

    def test_level_out_of_range(self):
        """List level beyond max (3) → clamped to max."""
        blocks = [
            _block(1, "• Deep", xml_list_level=5, has_bullet=True),
        ]
        clfs = [
            _clf(1, "TXT"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Should clamp to level 3
        assert result[0]["tag"] == "BL4-MID"

    def test_mismatched_ids(self):
        """Block IDs don't match classification IDs."""
        blocks = [
            _block(1, "• Item", xml_list_level=0, has_bullet=True),
        ]
        clfs = [
            _clf(99, "TXT"),  # Different ID
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Classification unchanged (no matching block)
        assert result[0]["tag"] == "TXT"

    def test_no_type_metadata(self):
        """List level present but no type information."""
        blocks = [
            _block(1, "• Item", xml_list_level=0),  # No has_bullet or has_numbering
        ]
        clfs = [
            _clf(1, "TXT"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Cannot determine type → unchanged
        assert result[0]["tag"] == "TXT"


# ===================================================================
# List sequences (numId)
# ===================================================================

class TestListSequences:
    """Test that list sequences (numId) are tracked."""

    def test_separate_list_sequences(self):
        """Two separate bullet lists with different numIds."""
        blocks = [
            _block(1, "• List A", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(2, "• List A", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(3, "Body text"),
            _block(4, "• List B", xml_list_level=0, has_bullet=True, xml_num_id=2),
            _block(5, "• List B", xml_list_level=0, has_bullet=True, xml_num_id=2),
        ]
        clfs = [
            _clf(1, "TXT"),
            _clf(2, "TXT"),
            _clf(3, "TXT"),
            _clf(4, "TXT"),
            _clf(5, "TXT"),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Both lists corrected (numId tracked but not enforced yet in tag)
        assert result[0]["tag"] == "BL-MID"
        assert result[1]["tag"] == "BL-MID"
        assert result[2]["tag"] == "TXT"
        assert result[3]["tag"] == "BL-MID"
        assert result[4]["tag"] == "BL-MID"


# ===================================================================
# Position suffix preservation
# ===================================================================

class TestListPositionSuffixPreservation:
    """Preserve FIRST/MID/LAST sequencing while enforcing XML list hierarchy."""

    def test_preserves_bl_first_mid_last_when_family_level_match(self):
        blocks = [
            _block(1, "• Item 1", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(2, "• Item 2", xml_list_level=0, has_bullet=True, xml_num_id=1),
            _block(3, "• Item 3", xml_list_level=0, has_bullet=True, xml_num_id=1),
        ]
        clfs = [
            _clf(1, "BL-FIRST"),
            _clf(2, "BL-MID"),
            _clf(3, "BL-LAST"),
        ]

        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert [c["tag"] for c in result] == ["BL-FIRST", "BL-MID", "BL-LAST"]
        assert all("list_preserved" not in c for c in result)

    def test_preserves_position_suffix_when_correcting_family(self):
        blocks = [
            _block(1, "1. Item", xml_list_level=0, has_numbering=True, xml_num_id=3),
            _block(2, "2. Item", xml_list_level=0, has_numbering=True, xml_num_id=3),
        ]
        clfs = [
            _clf(1, "BL-FIRST"),  # wrong type, right position
            _clf(2, "BL-LAST"),   # wrong type, right position
        ]

        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)

        assert [c["tag"] for c in result] == ["NL-FIRST", "NL-LAST"]
        assert result[0]["list_preserved"] is True
        assert result[1]["list_preserved"] is True


# ===================================================================
# Logging
# ===================================================================

class TestLogging:
    """Test structured logging output."""

    def test_logs_enforcement_info(self, caplog):
        """Logs LIST_HIERARCHY_ENFORCEMENT with counts."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [
            _block(1, "• Item", xml_list_level=0, has_bullet=True),
            _block(2, "• Item", xml_list_level=0, has_bullet=True),
        ]
        clfs = [
            _clf(1, "TXT"),  # Needs override
            _clf(2, "BL-MID"),  # Already correct
        ]
        enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Should log enforcement info
        assert any("LIST_HIERARCHY_ENFORCEMENT" in record.message for record in caplog.records)
        assert any("list_paras=2" in record.message for record in caplog.records)
        assert any("overrides=1" in record.message for record in caplog.records)
        assert any("restored=1" in record.message for record in caplog.records)

    def test_logs_zero_when_no_lists(self, caplog):
        """Logs zeros when no list paragraphs found."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Body text")]
        clfs = [_clf(1, "TXT")]
        enforce_list_hierarchy_from_word_xml(blocks, clfs)

        # Should log with zeros
        assert any("list_paras=0" in record.message for record in caplog.records)


# ===================================================================
# Reference-zone exclusion
# ===================================================================

class TestReferenceZoneExclusion:
    """Reference-zone list entries must not be coerced to BL-*/NL-*."""

    def test_sr_entry_preserved_via_is_reference_zone(self):
        """SR-tagged entry with is_reference_zone=True is not overwritten."""
        blocks = [
            _block(1, "References", context_zone="REFERENCE"),
            _block(2, "Smith, J. (2020). Title.", xml_list_level=0, xml_num_id=1,
                   has_bullet=True, is_reference_zone=True),
        ]
        clfs = [_clf(1, "SRH1"), _clf(2, "SR")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[1]["tag"] == "SR"

    def test_ref_n_entry_preserved_via_is_reference_zone(self):
        """REF-N entry in reference zone is not coerced."""
        blocks = [
            _block(1, "Bibliography", context_zone="REFERENCE"),
            _block(2, "Jones, A. (2019).", xml_list_level=0, xml_num_id=2,
                   has_bullet=True, is_reference_zone=True),
        ]
        clfs = [_clf(1, "SRH1"), _clf(2, "REF-N")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[1]["tag"] == "REF-N"

    def test_sr_entry_preserved_via_context_zone_reference(self):
        """SR entry with context_zone=REFERENCE (no is_reference_zone flag) is not coerced."""
        blocks = [
            _block(1, "References", context_zone="REFERENCE"),
            _block(2, "Author, B. (2021).", xml_list_level=0, xml_num_id=3,
                   has_bullet=True, context_zone="REFERENCE"),
        ]
        clfs = [_clf(1, "SRH1"), _clf(2, "SR")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[1]["tag"] == "SR"

    def test_fallback_path_also_skipped_in_reference_zone(self):
        """list_style_prefix fallback path is also skipped for reference-zone entries."""
        blocks = [
            _block(1, "References", context_zone="REFERENCE"),
            _block(2, "Author, C. (2022).", list_style_prefix="BL-",
                   is_reference_zone=True),
        ]
        clfs = [_clf(1, "SRH1"), _clf(2, "REF-U")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[1]["tag"] == "REF-U"

    def test_bl_list_outside_reference_zone_still_coerced(self):
        """Non-reference-zone list entries are still corrected as before."""
        blocks = [
            _block(1, "• Bullet item", xml_list_level=0, xml_num_id=1, has_bullet=True),
        ]
        clfs = [_clf(1, "TXT")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[0]["tag"] != "TXT"  # coerced to BL-* family

    def test_mixed_body_and_reference_zones(self):
        """Only reference-zone entries are skipped; body-zone entries are coerced."""
        blocks = [
            _block(1, "• Body bullet", xml_list_level=0, xml_num_id=1, has_bullet=True),
            _block(2, "Smith, J. (2020).", xml_list_level=0, xml_num_id=2,
                   is_reference_zone=True, has_bullet=True),
        ]
        clfs = [_clf(1, "TXT"), _clf(2, "SR")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[0]["tag"] != "TXT"  # body bullet coerced
        assert result[1]["tag"] == "SR"   # reference entry left alone

    def test_srh1_heading_not_coerced(self):
        """SRH1 heading in reference zone is not coerced even if xml_list_level set."""
        blocks = [
            _block(1, "References", xml_list_level=0, xml_num_id=1,
                   has_bullet=True, is_reference_zone=True),
        ]
        clfs = [_clf(1, "SRH1")]
        result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
        assert result[0]["tag"] == "SRH1"
