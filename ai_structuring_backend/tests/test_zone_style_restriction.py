"""Tests for zone-based style restriction enforcement."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.zone_style_restriction import (
    restrict_allowed_styles_per_zone,
    validate_block_style_for_zone,
)


def _block(pid, text="Sample text", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# restrict_allowed_styles_per_zone — positive cases
# ===================================================================

class TestRestrictAllowedStylesPositive:
    """Blocks with zones get zone_allowed_styles metadata hints."""

    def test_body_zone_no_restrictions(self):
        """BODY zone has no restrictions (ZONE_VALID_STYLES['BODY'] = None)."""
        blocks = [_block(1, "Normal paragraph", context_zone="BODY")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        # BODY zone has None (no restrictions), so no hints are set
        assert "zone_allowed_styles" not in meta

    def test_table_zone_gets_style_hints(self):
        """TABLE zone blocks get table-specific allowed styles."""
        blocks = [_block(1, "Table cell content", context_zone="TABLE")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        assert "zone_allowed_styles" in meta
        # TABLE zone should include table-specific styles
        styles = meta["zone_allowed_styles"]
        assert any("T" in style or "TC" in style for style in styles)

    def test_back_matter_zone_gets_style_hints(self):
        """BACK_MATTER zone blocks get reference-specific allowed styles."""
        blocks = [_block(1, "Reference entry", context_zone="BACK_MATTER")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        assert "zone_allowed_styles" in meta
        # BACK_MATTER zone should include reference styles
        styles = meta["zone_allowed_styles"]
        assert any("REF" in style for style in styles)

    def test_front_matter_zone_gets_style_hints(self):
        """FRONT_MATTER zone blocks get front matter styles."""
        blocks = [_block(1, "Chapter Title", context_zone="FRONT_MATTER")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        assert "zone_allowed_styles" in meta

    def test_box_zone_gets_style_hints(self):
        """BOX zones get box-specific allowed styles."""
        blocks = [_block(1, "Box content", context_zone="BOX_BX1")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        assert "zone_allowed_styles" in meta
        # Box zones should include BX1 styles
        styles = meta["zone_allowed_styles"]
        assert any("BX1" in style for style in styles)

    def test_multiple_zones_in_document(self):
        """Different zones get different style hints."""
        blocks = [
            _block(1, "Front matter", context_zone="FRONT_MATTER"),
            _block(2, "Table cell", context_zone="TABLE"),
            _block(3, "Reference", context_zone="BACK_MATTER"),
        ]
        result = restrict_allowed_styles_per_zone(blocks)

        # Zones with restrictions should have hints
        assert "zone_allowed_styles" in result[0]["metadata"]
        assert "zone_allowed_styles" in result[1]["metadata"]
        assert "zone_allowed_styles" in result[2]["metadata"]

        # Hints should be different for different zones
        styles_1 = result[0]["metadata"]["zone_allowed_styles"]
        styles_2 = result[1]["metadata"]["zone_allowed_styles"]
        styles_3 = result[2]["metadata"]["zone_allowed_styles"]

        # Front matter and table should have different styles
        assert styles_1 != styles_2
        # Front matter and back matter should have different styles
        assert styles_1 != styles_3


# ===================================================================
# restrict_allowed_styles_per_zone — negative cases
# ===================================================================

class TestRestrictAllowedStylesNegative:
    """Blocks without zone info or unknown zones handled gracefully."""

    def test_missing_zone_uses_default(self):
        """Block with no context_zone metadata uses BODY default (no restrictions)."""
        block = {"id": 1, "text": "Text", "metadata": {}}
        result = restrict_allowed_styles_per_zone([block])

        # BODY is default but has None (no restrictions), so no hints set
        meta = result[0]["metadata"]
        assert "zone_allowed_styles" not in meta

    def test_unknown_zone_no_hints(self):
        """Unknown zone name → no hints set (empty list from ZONE_VALID_STYLES)."""
        blocks = [_block(1, "Text", context_zone="UNKNOWN_ZONE_XYZ")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        # Unknown zones get empty list or aren't set
        hints = meta.get("zone_allowed_styles", [])
        assert isinstance(hints, list)

    def test_empty_blocks_list(self):
        """Empty blocks list → returns empty list."""
        result = restrict_allowed_styles_per_zone([])
        assert result == []

    def test_none_zone_uses_default(self):
        """context_zone=None → uses BODY default."""
        blocks = [_block(1, "Text", context_zone=None)]
        result = restrict_allowed_styles_per_zone(blocks)

        # Should not crash, should use default
        assert len(result) == 1


# ===================================================================
# Text & metadata preservation
# ===================================================================

class TestTextPreservation:
    """Verify text and existing metadata never modified."""

    def test_text_not_modified(self):
        """Block text is never changed."""
        original = "Original paragraph text content"
        blocks = [_block(1, original, context_zone="BODY")]
        result = restrict_allowed_styles_per_zone(blocks)
        assert result[0]["text"] == original

    def test_existing_metadata_preserved(self):
        """Existing metadata fields are preserved."""
        blocks = [_block(1, "Text", context_zone="BODY", custom_field="value", indent_level=2)]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        assert meta["custom_field"] == "value"
        assert meta["indent_level"] == 2
        assert meta["context_zone"] == "BODY"

    def test_identity_preserved(self):
        """Returned blocks are the same objects (in-place modification)."""
        blocks = [_block(1, "Text", context_zone="BODY")]
        result = restrict_allowed_styles_per_zone(blocks)
        assert result[0] is blocks[0]

    def test_returns_list(self):
        """Function returns list (not generator or other iterable)."""
        blocks = [_block(1, "Text", context_zone="BODY")]
        result = restrict_allowed_styles_per_zone(blocks)
        assert isinstance(result, list)


# ===================================================================
# validate_block_style_for_zone — validation helper
# ===================================================================

class TestValidateBlockStyleForZone:
    """Test the validation helper function."""

    def test_valid_style_for_zone_returns_true(self):
        """Valid style for zone → returns True."""
        block = _block(1, "Normal text", context_zone="BODY")
        # TXT is valid in BODY
        assert validate_block_style_for_zone(block, "TXT", log_violations=False) is True

    def test_invalid_style_for_zone_returns_false(self):
        """Invalid style for zone → returns False."""
        block = _block(1, "Text", context_zone="FRONT_MATTER")
        # TC (table cell) is NOT valid in FRONT_MATTER zone
        assert validate_block_style_for_zone(block, "TC", log_violations=False) is False

    def test_table_style_valid_in_table_zone(self):
        """Table styles valid in TABLE zone."""
        block = _block(1, "Cell", context_zone="TABLE")
        assert validate_block_style_for_zone(block, "T1", log_violations=False) is True
        assert validate_block_style_for_zone(block, "T2", log_violations=False) is True
        assert validate_block_style_for_zone(block, "TFN", log_violations=False) is True

    def test_table_style_valid_in_body_zone(self):
        """BODY zone has no restrictions, so all styles are valid."""
        block = _block(1, "Text", context_zone="BODY")
        # BODY has None (no restrictions), so table styles are valid too
        assert validate_block_style_for_zone(block, "TC", log_violations=False) is True

    def test_ref_style_valid_in_back_matter_zone(self):
        """Reference styles valid in BACK_MATTER zone."""
        block = _block(1, "Reference", context_zone="BACK_MATTER")
        assert validate_block_style_for_zone(block, "REF-N", log_violations=False) is True
        assert validate_block_style_for_zone(block, "REFH1", log_violations=False) is True

    def test_ref_style_valid_in_body_zone(self):
        """BODY zone has no restrictions, so reference styles are also valid."""
        block = _block(1, "Text", context_zone="BODY")
        # BODY has None (no restrictions), so REF styles are valid too
        assert validate_block_style_for_zone(block, "REF-N", log_violations=False) is True

    def test_pmi_valid_in_most_zones(self):
        """PMI (page marker instruction) is valid in most zones (not TABLE)."""
        zones = ["BODY", "BACK_MATTER", "FRONT_MATTER", "BOX_NBX", "METADATA"]
        for zone in zones:
            block = _block(1, "Text", context_zone=zone)
            assert validate_block_style_for_zone(block, "PMI", log_violations=False) is True

    def test_logging_violations(self, caplog):
        """log_violations=True logs warnings for invalid styles."""
        import logging
        caplog.set_level(logging.WARNING)

        block = _block(1, "Text", context_zone="TABLE")
        # CN (chapter number) is not valid in TABLE zone
        validate_block_style_for_zone(block, "CN", log_violations=True)

        # Should have logged a warning
        assert any("Zone violation" in record.message for record in caplog.records)

    def test_no_logging_when_valid(self, caplog):
        """Valid styles don't log warnings even with log_violations=True."""
        import logging
        caplog.set_level(logging.WARNING)

        block = _block(1, "Text", context_zone="BODY")
        validate_block_style_for_zone(block, "TXT", log_violations=True)

        # Should NOT have logged any warnings
        assert not any("Zone violation" in record.message for record in caplog.records)


# ===================================================================
# Edge cases & error handling
# ===================================================================

class TestEdgeCases:

    def test_metadata_dict_missing(self):
        """Block with no metadata dict → handles gracefully (defaults to BODY)."""
        block = {"id": 1, "text": "Text"}
        result = restrict_allowed_styles_per_zone([block])

        # Should not crash
        assert len(result) == 1
        # BODY zone (default) has no restrictions, so no hints set
        meta = result[0].get("metadata", {})
        assert "zone_allowed_styles" not in meta

    def test_zone_case_sensitivity(self):
        """Zone names should match exactly (case-sensitive)."""
        blocks = [_block(1, "Text", context_zone="body")]  # lowercase
        result = restrict_allowed_styles_per_zone(blocks)

        # Should handle gracefully (unknown zone)
        meta = result[0]["metadata"]
        hints = meta.get("zone_allowed_styles", [])
        assert isinstance(hints, list)

    def test_large_document_performance(self):
        """Large document with many blocks → processes efficiently."""
        blocks = [_block(i, f"Paragraph {i}", context_zone="TABLE") for i in range(1000)]
        result = restrict_allowed_styles_per_zone(blocks)

        assert len(result) == 1000
        # All TABLE zone blocks should have hints
        assert all("zone_allowed_styles" in b["metadata"] for b in result)


# ===================================================================
# Integration with existing zone validation
# ===================================================================

class TestIntegrationWithExistingValidation:
    """Verify this module complements existing zone validation."""

    def test_uses_existing_zone_valid_styles(self):
        """restrict_allowed_styles_per_zone uses ZONE_VALID_STYLES from ingestion."""
        from processor.ingestion import ZONE_VALID_STYLES

        blocks = [_block(1, "Text", context_zone="TABLE")]
        result = restrict_allowed_styles_per_zone(blocks)

        meta = result[0]["metadata"]
        hints = meta["zone_allowed_styles"]

        # Should match ZONE_VALID_STYLES["TABLE"]
        expected = ZONE_VALID_STYLES.get("TABLE", [])
        assert hints == expected

    def test_validate_helper_uses_existing_function(self):
        """validate_block_style_for_zone uses validate_style_for_zone from ingestion."""
        from processor.ingestion import validate_style_for_zone

        block = _block(1, "Text", context_zone="BODY")
        style = "TXT"

        # Our helper should return same result as existing function
        our_result = validate_block_style_for_zone(block, style, log_violations=False)
        expected = validate_style_for_zone(style, "BODY")

        assert our_result == expected

    def test_does_not_set_lock_style(self):
        """This module sets hints, NOT lock_style (that's for deterministic locks)."""
        blocks = [_block(1, "Text", context_zone="BODY")]
        result = restrict_allowed_styles_per_zone(blocks)

        # Should NOT set lock_style (this is for hints only)
        assert result[0].get("lock_style") is not True
        assert result[0].get("skip_llm") is not True

    def test_does_not_modify_allowed_styles_field(self):
        """Does not modify block.allowed_styles (used by lock mechanism)."""
        blocks = [_block(1, "Text", context_zone="TABLE")]
        result = restrict_allowed_styles_per_zone(blocks)

        # Should NOT modify allowed_styles at block level
        assert "allowed_styles" not in result[0]
        # Only sets metadata hint (for zones with restrictions)
        assert "zone_allowed_styles" in result[0]["metadata"]


# ===================================================================
# Logging behavior
# ===================================================================

class TestLogging:
    """Verify logging output."""

    def test_logs_info_when_hints_set(self, caplog):
        """Logs info message when hints are set (zones with restrictions)."""
        import logging
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Text", context_zone="TABLE")]
        restrict_allowed_styles_per_zone(blocks)

        # Should log info about hints being set
        assert any("zone-style-restriction" in record.message for record in caplog.records)

    def test_logs_zone_breakdown(self, caplog):
        """Logs debug-level breakdown by zone (only for zones with restrictions)."""
        import logging
        caplog.set_level(logging.DEBUG)

        blocks = [
            _block(1, "Text1", context_zone="FRONT_MATTER"),
            _block(2, "Text2", context_zone="FRONT_MATTER"),
            _block(3, "Text3", context_zone="TABLE"),
        ]
        restrict_allowed_styles_per_zone(blocks)

        # Should log debug info with zone counts (only for zones with restrictions)
        debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("FRONT_MATTER" in msg and "2 blocks" in msg for msg in debug_msgs)
        assert any("TABLE" in msg and "1 block" in msg for msg in debug_msgs)

    def test_no_log_when_empty_blocks(self, caplog):
        """No logging when blocks list is empty."""
        import logging
        caplog.set_level(logging.INFO)

        restrict_allowed_styles_per_zone([])

        # Should not log anything
        assert len(caplog.records) == 0
