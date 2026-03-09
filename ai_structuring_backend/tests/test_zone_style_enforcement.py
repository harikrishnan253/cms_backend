"""Tests for zone-based style restriction enforcement (post-classification)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.zone_style_restriction import enforce_zone_style_restrictions


def _block(pid, tag, zone="BODY", **extras):
    """Create a block dict with tag and zone."""
    return {
        "id": pid,
        "tag": tag,
        "text": f"Paragraph {pid} text",
        "metadata": {"context_zone": zone},
        **extras,
    }


# ===================================================================
# Unknown style replacement (LLM hallucinations)
# ===================================================================

class TestUnknownStyleReplacement:
    """Test replacement of unknown/hallucinated styles from LLM."""

    def test_unknown_style_replaced_with_fallback(self, caplog):
        """Unknown style like BODY_TEXT (doesn't exist) → replaced with TXT."""
        allowed = {"TXT", "H1", "H2", "PMI"}
        blocks = [_block(1, "BODY_TEXT", zone="BODY")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        # Should replace with BODY zone fallback (TXT)
        assert result[0]["tag"] == "TXT"
        assert result[0]["original_tag"] == "BODY_TEXT"
        assert result[0]["zone_restricted"] is True

        # Should log warning
        assert "unknown style" in caplog.text.lower()
        assert "BODY_TEXT" in caplog.text

    def test_unknown_style_in_table_zone(self, caplog):
        """Unknown style in TABLE zone → replaced with T."""
        allowed = {"T", "T1", "TH1", "PMI"}
        blocks = [_block(1, "TABLE_BODY", zone="TABLE")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "T"
        assert result[0]["original_tag"] == "TABLE_BODY"

    def test_unknown_style_in_box_zone(self, caplog):
        """Unknown style in BOX_NBX → replaced with NBX-TXT."""
        allowed = {"NBX-TXT", "NBX-H1", "PMI"}
        blocks = [_block(1, "BOX_TEXT", zone="BOX_NBX")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "NBX-TXT"
        assert result[0]["original_tag"] == "BOX_TEXT"

    def test_multiple_unknown_styles(self, caplog):
        """Multiple unknown styles all replaced."""
        allowed = {"TXT", "T", "PMI"}
        blocks = [
            _block(1, "BODY_TEXT", zone="BODY"),
            _block(2, "TABLE_TITLE", zone="TABLE"),
            _block(3, "REF_ITEM", zone="BACK_MATTER"),
        ]

        with caplog.at_level("INFO"):
            result = enforce_zone_style_restrictions(blocks, allowed)

        # All replaced with zone fallbacks
        assert result[0]["tag"] == "TXT"
        assert result[1]["tag"] == "T"
        assert result[2]["tag"] == "PMI"

        # Check logging - all 3 are replaced
        assert "replaced=3" in caplog.text
        assert "unknown_from_llm=3" in caplog.text


# ===================================================================
# Zone violation replacement (valid style, wrong zone)
# ===================================================================

class TestZoneViolationReplacement:
    """Test replacement of valid-but-disallowed styles in zones."""

    def test_bullet_list_in_table_zone(self):
        """BL-MID (valid style) in TABLE zone → replaced with T."""
        allowed = {"BL-MID", "T", "T1", "PMI"}
        blocks = [_block(1, "BL-MID", zone="TABLE")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "T"
        assert result[0]["original_tag"] == "BL-MID"
        assert result[0]["zone_restricted"] is True

    def test_table_style_in_body_zone(self):
        """T1 (table title) in BODY zone → allowed (BODY has no restrictions)."""
        allowed = {"T1", "TXT", "PMI"}
        blocks = [_block(1, "T1", zone="BODY")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        # BODY zone allows all styles (ZONE_VALID_STYLES['BODY'] = None)
        # So T1 should be unchanged
        assert result[0]["tag"] == "T1"
        assert result[0].get("zone_restricted") is not True

    def test_heading_in_table_zone(self):
        """H1 (heading) in TABLE zone → replaced with T."""
        allowed = {"H1", "T", "PMI"}
        blocks = [_block(1, "H1", zone="TABLE")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "T"
        assert result[0]["original_tag"] == "H1"

    def test_box_style_in_front_matter(self):
        """NBX-TXT in FRONT_MATTER → replaced with TXT."""
        allowed = {"NBX-TXT", "TXT", "PMI"}
        blocks = [_block(1, "NBX-TXT", zone="FRONT_MATTER")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "TXT"
        assert result[0]["original_tag"] == "NBX-TXT"


# ===================================================================
# Valid styles unchanged
# ===================================================================

class TestValidStylesUnchanged:
    """Test that valid styles in correct zones are left unchanged."""

    def test_txt_in_body_unchanged(self):
        """TXT in BODY zone → unchanged."""
        allowed = {"TXT", "H1", "PMI"}
        blocks = [_block(1, "TXT", zone="BODY")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "TXT"
        assert result[0].get("zone_restricted") is not True
        assert "original_tag" not in result[0]

    def test_t1_in_table_unchanged(self):
        """T1 in TABLE zone → unchanged."""
        allowed = {"T1", "T", "PMI"}
        blocks = [_block(1, "T1", zone="TABLE")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "T1"
        assert result[0].get("zone_restricted") is not True

    def test_nbx_txt_in_box_unchanged(self):
        """NBX-TXT in BOX_NBX zone → unchanged."""
        allowed = {"NBX-TXT", "NBX-H1", "PMI"}
        blocks = [_block(1, "NBX-TXT", zone="BOX_NBX")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0]["tag"] == "NBX-TXT"
        assert result[0].get("zone_restricted") is not True

    def test_pmi_always_valid(self):
        """PMI is valid in most zones (but not TABLE - TABLE doesn't list PMI in ZONE_VALID_STYLES)."""
        allowed = {"PMI", "TXT", "T"}
        blocks = [
            _block(1, "PMI", zone="BODY"),          # Valid (BODY allows all)
            _block(2, "PMI", zone="BOX_NBX"),       # Valid (listed in BOX_NBX)
            _block(3, "PMI", zone="BACK_MATTER"),   # Valid (listed in BACK_MATTER)
        ]

        result = enforce_zone_style_restrictions(blocks, allowed)

        for b in result:
            assert b["tag"] == "PMI"
            assert b.get("zone_restricted") is not True

    def test_mixed_valid_and_invalid(self):
        """Mixed blocks: valid unchanged, invalid replaced."""
        allowed = {"TXT", "T1", "PMI"}
        blocks = [
            _block(1, "TXT", zone="BODY"),           # Valid
            _block(2, "UNKNOWN", zone="BODY"),       # Invalid
            _block(3, "T1", zone="TABLE"),           # Valid
            _block(4, "TXT", zone="TABLE"),          # Invalid for TABLE
        ]

        result = enforce_zone_style_restrictions(blocks, allowed)

        # Block 1: unchanged
        assert result[0]["tag"] == "TXT"
        assert result[0].get("zone_restricted") is not True

        # Block 2: replaced (unknown)
        assert result[1]["tag"] == "TXT"
        assert result[1]["zone_restricted"] is True

        # Block 3: unchanged
        assert result[2]["tag"] == "T1"
        assert result[2].get("zone_restricted") is not True

        # Block 4: replaced (zone violation)
        assert result[3]["tag"] == "T"
        assert result[3]["zone_restricted"] is True


# ===================================================================
# Logging format tests
# ===================================================================

class TestLoggingFormat:
    """Verify structured logging format."""

    def test_logging_with_replacements(self, caplog):
        """Emits ZONE_STYLE_RESTRICTION with metrics."""
        allowed = {"TXT", "T", "PMI"}
        blocks = [
            _block(1, "UNKNOWN1", zone="BODY"),
            _block(2, "UNKNOWN2", zone="TABLE"),
            _block(3, "TXT", zone="BODY"),
        ]

        with caplog.at_level("INFO"):
            enforce_zone_style_restrictions(blocks, allowed)

        # Should log "ZONE_STYLE_RESTRICTION total=3 replaced=2 unknown_from_llm=2 by_zone={'BODY': 1, 'TABLE': 1}"
        assert "ZONE_STYLE_RESTRICTION" in caplog.text
        assert "total=3" in caplog.text
        assert "replaced=2" in caplog.text
        assert "unknown_from_llm=2" in caplog.text

    def test_logging_by_zone_breakdown(self, caplog):
        """by_zone breakdown includes all zones with replacements."""
        allowed = {"TXT", "PMI"}
        blocks = [
            _block(1, "BAD1", zone="BODY"),
            _block(2, "BAD2", zone="BODY"),
            _block(3, "BAD3", zone="TABLE"),
            _block(4, "BAD4", zone="BOX_NBX"),
        ]

        with caplog.at_level("INFO"):
            enforce_zone_style_restrictions(blocks, allowed)

        # Should have by_zone with BODY: 2, TABLE: 1, BOX_NBX: 1
        assert "'BODY': 2" in caplog.text
        assert "'TABLE': 1" in caplog.text
        assert "'BOX_NBX': 1" in caplog.text

    def test_no_replacements_no_log(self, caplog):
        """No replacements → no ZONE_STYLE_RESTRICTION log."""
        allowed = {"TXT", "H1", "PMI"}
        blocks = [
            _block(1, "TXT", zone="BODY"),
            _block(2, "H1", zone="BODY"),
        ]

        with caplog.at_level("INFO"):
            caplog.clear()
            enforce_zone_style_restrictions(blocks, allowed)

        assert "ZONE_STYLE_RESTRICTION" not in caplog.text

    def test_unknown_styles_logged_separately(self, caplog):
        """Unknown styles are logged with counts."""
        allowed = {"TXT", "PMI"}
        blocks = [
            _block(1, "UNKNOWN_A", zone="BODY"),
            _block(2, "UNKNOWN_A", zone="BODY"),
            _block(3, "UNKNOWN_B", zone="BODY"),
        ]

        with caplog.at_level("WARNING"):
            enforce_zone_style_restrictions(blocks, allowed)

        # Should log unknown styles with counts
        assert "unknown styles encountered" in caplog.text.lower()
        assert "UNKNOWN_A" in caplog.text
        assert "UNKNOWN_B" in caplog.text


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_blocks(self):
        """Empty blocks list → no errors."""
        allowed = {"TXT", "PMI"}
        result = enforce_zone_style_restrictions([], allowed)
        assert result == []

    def test_block_without_tag(self):
        """Block without tag field → skipped."""
        allowed = {"TXT", "PMI"}
        blocks = [
            {"id": 1, "text": "No tag", "metadata": {"context_zone": "BODY"}},
            _block(2, "TXT", zone="BODY"),
        ]

        result = enforce_zone_style_restrictions(blocks, allowed)

        # Block 1 skipped, block 2 processed
        assert "tag" not in result[0] or result[0].get("tag") == ""
        assert result[1]["tag"] == "TXT"

    def test_block_without_zone(self):
        """Block without zone → defaults to BODY."""
        allowed = {"TXT", "PMI"}
        blocks = [
            {"id": 1, "tag": "UNKNOWN", "metadata": {}},
        ]

        result = enforce_zone_style_restrictions(blocks, allowed)

        # Should use BODY zone fallback (TXT)
        assert result[0]["tag"] == "TXT"

    def test_allowed_styles_none_loads_from_config(self):
        """allowed_styles=None → loads from config."""
        blocks = [_block(1, "TXT", zone="BODY")]

        # Should not crash, loads from config
        result = enforce_zone_style_restrictions(blocks, allowed_styles=None)

        # Should work (TXT is valid in config)
        assert result[0]["tag"] == "TXT"

    def test_identity_preserved(self):
        """Returned blocks are the same objects (in-place modification)."""
        allowed = {"TXT", "PMI"}
        blocks = [_block(1, "TXT", zone="BODY")]

        result = enforce_zone_style_restrictions(blocks, allowed)

        assert result[0] is blocks[0]


# ===================================================================
# Idempotency tests
# ===================================================================

class TestIdempotency:
    """Verify running enforcement twice produces same result."""

    def test_enforce_twice_same_result(self):
        """Running enforce_zone_style_restrictions twice → idempotent."""
        allowed = {"TXT", "PMI"}
        blocks = [
            _block(1, "UNKNOWN", zone="BODY"),
            _block(2, "TXT", zone="BODY"),
        ]

        # First pass
        result1 = enforce_zone_style_restrictions(blocks, allowed)
        # Second pass on same blocks
        result2 = enforce_zone_style_restrictions(result1, allowed)

        # Should be identical
        assert result1[0]["tag"] == "TXT"
        assert result2[0]["tag"] == "TXT"
        assert result1[0]["zone_restricted"] is True
        assert result2[0]["zone_restricted"] is True

        # Block 2 unchanged both times
        assert result1[1]["tag"] == "TXT"
        assert result2[1]["tag"] == "TXT"

    def test_already_restricted_block_unchanged(self):
        """Block with zone_restricted=True → not re-processed."""
        allowed = {"TXT", "PMI"}
        blocks = [
            {
                "id": 1,
                "tag": "TXT",
                "original_tag": "UNKNOWN",
                "zone_restricted": True,
                "metadata": {"context_zone": "BODY"},
            }
        ]

        result = enforce_zone_style_restrictions(blocks, allowed)

        # Should remain unchanged (already TXT)
        assert result[0]["tag"] == "TXT"
        assert result[0]["zone_restricted"] is True


# ===================================================================
# Quality scoring integration tests
# ===================================================================

class TestQualityScoringIntegration:
    """Test that enforcement prevents quality_score failures."""

    def test_unknown_style_replaced_before_quality_check(self):
        """Unknown style is replaced, quality_score should not see it."""
        from app.services.quality_score import score_document

        allowed = {"TXT", "H1", "PMI"}
        blocks = [
            _block(1, "UNKNOWN_STYLE", zone="BODY"),
            _block(2, "TXT", zone="BODY"),
        ]

        # Enforce restrictions
        blocks = enforce_zone_style_restrictions(blocks, allowed)

        # Should have replaced unknown style
        assert blocks[0]["tag"] == "TXT"

        # Quality score should pass (no unknown styles)
        score, metrics, action = score_document(blocks, allowed)

        # Should not detect any unknown styles
        assert metrics["unknown_style_count"] == 0

    def test_multiple_unknown_styles_all_fixed(self):
        """Multiple unknown styles → all fixed, quality_score passes."""
        from app.services.quality_score import score_document

        allowed = {"TXT", "H1", "T", "PMI"}
        blocks = [
            _block(1, "BODY_TEXT", zone="BODY"),
            _block(2, "TABLE_TITLE", zone="TABLE"),
            _block(3, "REF_ITEM", zone="BACK_MATTER"),
        ]

        # Before enforcement: would fail quality check
        score_before, metrics_before, _ = score_document(blocks, allowed)
        assert metrics_before["unknown_style_count"] == 3

        # Enforce restrictions
        blocks = enforce_zone_style_restrictions(blocks, allowed)

        # After enforcement: should pass quality check
        score_after, metrics_after, _ = score_document(blocks, allowed)
        assert metrics_after["unknown_style_count"] == 0


# ===================================================================
# Zone fallback mapping tests
# ===================================================================

class TestZoneFallbackMapping:
    """Test that each zone has correct fallback style."""

    def test_body_fallback(self):
        """BODY zone fallback is TXT."""
        allowed = {"TXT", "PMI"}
        blocks = [_block(1, "UNKNOWN", zone="BODY")]
        result = enforce_zone_style_restrictions(blocks, allowed)
        assert result[0]["tag"] == "TXT"

    def test_table_fallback(self):
        """TABLE zone fallback is T."""
        allowed = {"T", "PMI"}
        blocks = [_block(1, "UNKNOWN", zone="TABLE")]
        result = enforce_zone_style_restrictions(blocks, allowed)
        assert result[0]["tag"] == "T"

    def test_box_nbx_fallback(self):
        """BOX_NBX zone fallback is NBX-TXT."""
        allowed = {"NBX-TXT", "PMI"}
        blocks = [_block(1, "UNKNOWN", zone="BOX_NBX")]
        result = enforce_zone_style_restrictions(blocks, allowed)
        assert result[0]["tag"] == "NBX-TXT"

    def test_box_bx1_fallback(self):
        """BOX_BX1 zone fallback is BX1-TXT."""
        allowed = {"BX1-TXT", "PMI"}
        blocks = [_block(1, "UNKNOWN", zone="BOX_BX1")]
        result = enforce_zone_style_restrictions(blocks, allowed)
        assert result[0]["tag"] == "BX1-TXT"

    def test_back_matter_fallback(self):
        """BACK_MATTER zone fallback is PMI."""
        allowed = {"PMI", "REF-N"}
        blocks = [_block(1, "UNKNOWN", zone="BACK_MATTER")]
        result = enforce_zone_style_restrictions(blocks, allowed)
        assert result[0]["tag"] == "PMI"

    def test_front_matter_fallback(self):
        """FRONT_MATTER zone fallback is TXT."""
        allowed = {"TXT", "PMI"}
        blocks = [_block(1, "UNKNOWN", zone="FRONT_MATTER")]
        result = enforce_zone_style_restrictions(blocks, allowed)
        assert result[0]["tag"] == "TXT"


# ===================================================================
# Comprehensive integration test
# ===================================================================

class TestComprehensiveIntegration:
    """End-to-end test simulating real pipeline scenarios."""

    def test_mixed_document_with_all_issue_types(self, caplog):
        """Complex document with unknown styles, zone violations, valid styles."""
        allowed = {"TXT", "H1", "T", "T1", "NBX-TXT", "BX1-TXT", "PMI"}
        blocks = [
            # Valid styles
            _block(1, "TXT", zone="BODY"),
            _block(2, "H1", zone="BODY"),
            _block(3, "T1", zone="TABLE"),
            _block(4, "NBX-TXT", zone="BOX_NBX"),
            _block(5, "PMI", zone="BODY"),
            _block(6, "NBX-TXT", zone="BODY"),  # Valid (BODY allows all styles)
            # Unknown styles (LLM hallucinations)
            _block(7, "BODY_TEXT", zone="BODY"),
            _block(8, "TABLE_TITLE", zone="TABLE"),
            # Zone violations (valid styles, wrong zone)
            _block(9, "H1", zone="TABLE"),
            _block(10, "BX1-TXT", zone="FRONT_MATTER"),
        ]

        with caplog.at_level("INFO"):
            result = enforce_zone_style_restrictions(blocks, allowed)

        # Valid styles unchanged
        assert result[0]["tag"] == "TXT"
        assert result[1]["tag"] == "H1"
        assert result[2]["tag"] == "T1"
        assert result[3]["tag"] == "NBX-TXT"
        assert result[4]["tag"] == "PMI"
        assert result[5]["tag"] == "NBX-TXT"  # BODY allows all

        # Unknown styles replaced
        assert result[6]["tag"] == "TXT"
        assert result[6]["original_tag"] == "BODY_TEXT"
        assert result[7]["tag"] == "T"
        assert result[7]["original_tag"] == "TABLE_TITLE"

        # Zone violations replaced
        assert result[8]["tag"] == "T"
        assert result[8]["original_tag"] == "H1"
        assert result[9]["tag"] == "TXT"
        assert result[9]["original_tag"] == "BX1-TXT"

        # Logging
        assert "ZONE_STYLE_RESTRICTION" in caplog.text
        assert "total=10" in caplog.text
        assert "replaced=4" in caplog.text
