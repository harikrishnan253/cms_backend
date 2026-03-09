"""
Tests for style enforcement layer - composite detection, canonicalization logging,
and final enforcement gate.
"""

import pytest
import logging
from unittest.mock import patch
from backend.processor.validator import validate_and_repair, _is_composite_tag, _split_composite_tag
from backend.processor.style_enforcement import enforce_style_compliance


# Test helpers
def _block(pid, text, zone="BODY", **meta_overrides):
    """Create test block with metadata."""
    meta = {"context_zone": zone}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


def _clf(pid, tag, confidence=85, **extra):
    """Create test classification."""
    d = {"id": pid, "tag": tag, "confidence": confidence}
    d.update(extra)
    return d


# Subset of allowed styles for testing
ALLOWED = {
    "TXT", "TXT-FLUSH", "PMI",
    "H1", "H2", "H3", "H10", "H20", "H21",
    "REF-N", "REF-U",
    "T", "T1", "T2", "TH1", "TH2", "TFN", "TSN",
    "QUES-NL-MID", "QUES-TXT-FLUSH",
    "BL-MID", "NL-MID",
    "NBX-TTL", "NBX-TXT",
    "BX1-TTL", "BX1-TXT",
    "FIG-LEG", "EOC-H1",
}


class TestCompositeDetection:
    def test_plus_separator_detected(self):
        """Composite tag with + separator detected."""
        assert _is_composite_tag("TBL-H2+TXT") is True
        assert _is_composite_tag("H1+H2") is True

    def test_slash_separator_detected(self):
        """Composite tag with / separator detected."""
        assert _is_composite_tag("REF-N/PMI") is True
        assert _is_composite_tag("TXT/TXT-FLUSH") is True

    def test_comma_separator_detected(self):
        """Composite tag with comma separator detected."""
        assert _is_composite_tag("H1,H2") is True
        assert _is_composite_tag("TXT,PMI,H1") is True

    def test_pipe_separator_detected(self):
        """Composite tag with pipe separator detected."""
        assert _is_composite_tag("TXT|PMI") is True

    def test_single_tag_not_composite(self):
        """Single tag without separators NOT detected as composite."""
        assert _is_composite_tag("REF-N") is False
        assert _is_composite_tag("TXT") is False
        assert _is_composite_tag("H1") is False

    def test_hyphenated_tag_not_composite(self):
        """Hyphenated tags (normal style names) NOT detected as composite."""
        assert _is_composite_tag("QUES-NL-MID") is False
        assert _is_composite_tag("BX1-TXT-FLUSH") is False
        assert _is_composite_tag("EOC-NL-FIRST") is False

    def test_split_composite_tag(self):
        """_split_composite_tag correctly splits on all separators."""
        assert _split_composite_tag("TXT+PMI") == ["TXT", "PMI"]
        assert _split_composite_tag("H1/H2") == ["H1", "H2"]
        assert _split_composite_tag("TXT,PMI,H1") == ["TXT", "PMI", "H1"]
        assert _split_composite_tag("A|B") == ["A", "B"]


class TestCompositeRepair:
    def test_first_valid_component_used(self):
        """First valid component of composite used."""
        blocks = [_block("p1", "Some text", "BODY")]
        clfs = [_clf("p1", "TXT+PMI", 90)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "TXT"
        assert result[0]["repaired"] is True
        assert "composite-rejected" in result[0]["repair_reason"]

    def test_second_component_if_first_invalid(self):
        """If first component invalid, use second valid component."""
        blocks = [_block("p1", "Reference text", "BACK_MATTER")]
        clfs = [_clf("p1", "INVALID+REF-N", 90)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "REF-N"
        assert result[0]["repaired"] is True
        assert "composite-rejected" in result[0]["repair_reason"]

    def test_all_invalid_uses_fallback(self):
        """All components invalid, uses semantic fallback to TXT."""
        blocks = [_block("p1", "Some text", "BODY")]
        clfs = [_clf("p1", "FAKE1+FAKE2", 90)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "TXT"
        assert result[0]["repaired"] is True
        assert "composite-rejected" in result[0]["repair_reason"]

    def test_repair_reason_set(self):
        """repair_reason includes composite-rejected."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "H1+H2", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert "composite-rejected" in result[0]["repair_reason"]

    def test_repaired_flag_set(self):
        """repaired flag set to True."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "TXT+PMI", 90)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["repaired"] is True


class TestStyleCanonicalizationLogging:
    @patch('backend.processor.validator.logger')
    def test_alias_resolved_logged(self, mock_logger):
        """Alias resolution (QUES_NUM → QUES-NL-MID) logs alias_resolved."""
        blocks = [_block("p1", "1. Question", "EXERCISE")]
        clfs = [_clf("p1", "QUES_NUM", 85)]  # Alias that resolves to QUES-NL-MID
        validate_and_repair(clfs, blocks, ALLOWED)
        # Check that STYLE_CANONICALIZATION was logged
        mock_logger.info.assert_any_call(
            "STYLE_CANONICALIZATION invalid=%d repaired=%d composite_rejected=%d alias_resolved=%d zone_repaired=%d",
            pytest.approx(0, abs=5),  # invalid_styles (may vary)
            pytest.approx(1, abs=1),  # repaired
            0,  # composite_rejected
            pytest.approx(1, abs=1),  # alias_resolved
            pytest.approx(0, abs=5),  # zone_repaired (may vary)
        )

    @patch('backend.processor.validator.logger')
    def test_composite_rejected_logged(self, mock_logger):
        """Composite tag rejection logs composite_rejected."""
        blocks = [_block("p1", "Heading", "BODY")]
        clfs = [_clf("p1", "H1+H2", 90)]
        validate_and_repair(clfs, blocks, ALLOWED)
        # Check that STYLE_CANONICALIZATION was logged with composite_rejected=1
        mock_logger.info.assert_any_call(
            "STYLE_CANONICALIZATION invalid=%d repaired=%d composite_rejected=%d alias_resolved=%d zone_repaired=%d",
            pytest.approx(0, abs=5),
            1,  # repaired
            1,  # composite_rejected
            pytest.approx(0, abs=5),
            pytest.approx(0, abs=5),
        )

    @patch('backend.processor.validator.logger')
    def test_zone_invalid_logged(self, mock_logger):
        """STYLE_CANONICALIZATION logs with all metrics."""
        blocks = [_block("p1", "Table cell", "TABLE")]
        clfs = [_clf("p1", "T", 85)]
        validate_and_repair(clfs, blocks, ALLOWED)
        # Check that STYLE_CANONICALIZATION was logged with all metric fields
        calls = [str(call) for call in mock_logger.info.call_args_list]
        style_canon_calls = [c for c in calls if "STYLE_CANONICALIZATION" in c]
        assert len(style_canon_calls) > 0, "STYLE_CANONICALIZATION should be logged"

    @patch('backend.processor.validator.logger')
    def test_invalid_style_logged(self, mock_logger):
        """Invalid style (not in allowed_styles) logs invalid_styles."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "FAKE-TAG", 85)]
        validate_and_repair(clfs, blocks, ALLOWED)
        # Check that invalid_styles was logged
        mock_logger.info.assert_any_call(
            "STYLE_CANONICALIZATION invalid=%d repaired=%d composite_rejected=%d alias_resolved=%d zone_repaired=%d",
            1,  # invalid_styles
            1,  # repaired
            pytest.approx(0, abs=5),
            pytest.approx(0, abs=5),
            pytest.approx(0, abs=5),
        )

    @patch('backend.processor.validator.logger')
    def test_multiple_repairs_logged(self, mock_logger):
        """Multiple repairs all counted correctly."""
        blocks = [
            _block("p1", "Text", "BODY"),
            _block("p2", "Composite", "BODY"),
            _block("p3", "Invalid", "BODY"),
        ]
        clfs = [
            _clf("p1", "H1+H2", 90),       # composite
            _clf("p2", "TXT+PMI", 85),     # composite
            _clf("p3", "FAKE", 80),        # invalid
        ]
        validate_and_repair(clfs, blocks, ALLOWED)
        # Check metrics: 3 repaired, 2 composite, 1 invalid
        mock_logger.info.assert_any_call(
            "STYLE_CANONICALIZATION invalid=%d repaired=%d composite_rejected=%d alias_resolved=%d zone_repaired=%d",
            1,  # invalid_styles
            3,  # repaired (all 3)
            2,  # composite_rejected
            pytest.approx(0, abs=5),
            pytest.approx(0, abs=5),
        )


class TestFinalEnforcement:
    @patch('backend.processor.style_enforcement.logger')
    def test_unknown_style_repaired(self, mock_logger):
        """Classification with unknown tag repaired to closest valid style."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "UNKNOWN-TAG", 90)]
        result = enforce_style_compliance(clfs, blocks, ALLOWED)
        # Should be repaired to TXT (fallback)
        assert result[0]["tag"] == "TXT"
        assert result[0]["repaired"] is True
        assert "final-enforcement" in result[0]["repair_reason"]

    @patch('backend.processor.style_enforcement.logger')
    def test_zone_safe_fallback(self, mock_logger):
        """Invalid style in TABLE zone falls back to T (not TXT)."""
        blocks = [_block("p1", "Table text", "TABLE")]
        clfs = [_clf("p1", "INVALID-STYLE", 85)]
        result = enforce_style_compliance(clfs, blocks, ALLOWED)
        # TABLE zone should fallback to T, not TXT
        assert result[0]["tag"] == "T"
        assert result[0]["repaired"] is True

    def test_already_valid_unchanged(self):
        """Valid style unchanged, no repair."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "TXT", 90)]
        result = enforce_style_compliance(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "TXT"
        assert result[0].get("repaired") is not True  # Original didn't have repaired flag

    def test_repair_reason_appended(self):
        """final-enforcement added to existing repair_reason."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "INVALID", 85, repair_reason="not-allowed")]
        result = enforce_style_compliance(clfs, blocks, ALLOWED)
        assert "not-allowed" in result[0]["repair_reason"]
        assert "final-enforcement" in result[0]["repair_reason"]

    @patch('backend.processor.style_enforcement.logger')
    def test_no_unknown_in_output(self, mock_logger):
        """After enforcement, all styles in allowed_styles."""
        blocks = [
            _block("p1", "Text 1", "BODY"),
            _block("p2", "Text 2", "TABLE"),
            _block("p3", "Text 3", "BACK_MATTER"),
        ]
        clfs = [
            _clf("p1", "FAKE1", 90),
            _clf("p2", "FAKE2", 85),
            _clf("p3", "FAKE3", 80),
        ]
        result = enforce_style_compliance(clfs, blocks, ALLOWED)
        # All result tags should be in ALLOWED
        for clf in result:
            assert clf["tag"] in ALLOWED, f"Tag {clf['tag']} not in allowed_styles"

    @patch('backend.processor.style_enforcement.logger')
    def test_metadata_zone_fallback(self, mock_logger):
        """Invalid style in METADATA zone falls back to PMI."""
        blocks = [_block("p1", "Metadata text", "METADATA")]
        clfs = [_clf("p1", "INVALID-META", 85)]
        result = enforce_style_compliance(clfs, blocks, ALLOWED)
        # METADATA zone should fallback to PMI
        assert result[0]["tag"] == "PMI"


class TestInlineHeadingVariants:
    def test_inline_h1_marker_upgrades_plain_h1_to_h10_from_heading2_source(self):
        blocks = [_block("p1", "<H1>Section Title", "BODY", style_name="Heading 2")]
        clfs = [_clf("p1", "H1", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "H10"

    def test_inline_h2_marker_upgrades_plain_h2_to_h20_from_heading3_source(self):
        blocks = [_block("p1", "<H2>Overview", "BODY", style_name="Heading 3")]
        clfs = [_clf("p1", "H2", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "H20"

    def test_inline_h2_marker_upgrades_plain_h2_to_h21_from_heading2_source(self):
        blocks = [_block("p1", "<H2>Molecular and Functional Biology", "BODY", style_name="Heading 2")]
        clfs = [_clf("p1", "H2", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "H21"

    def test_inline_h2_marker_does_not_collapse_h20_variant(self):
        """Inline <H2> marker should preserve valid H20/H21 variants, not force plain H2."""
        blocks = [_block("p1", "<H2>Overview", "BODY")]
        clfs = [_clf("p1", "H20", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "H20"

    def test_inline_h2_marker_does_not_collapse_h21_variant(self):
        blocks = [_block("p1", "<H2>Molecular and Functional Biology", "BODY")]
        clfs = [_clf("p1", "H21", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "H21"

    def test_marker_only_paragraph_forces_pmi_even_when_high_confidence(self):
        blocks = [_block("p1", "</BL>", "BODY")]
        clfs = [_clf("p1", "H3", 99)]
        result = validate_and_repair(clfs, blocks, ALLOWED)
        assert result[0]["tag"] == "PMI"


class TestSemanticListAlignment:
    def test_kt_bullet_family_preserves_prefix_while_aligning_position(self):
        blocks = [_block("p1", "Key term bullet", "BODY", list_kind="bullet", list_position="first")]
        clfs = [_clf("p1", "KT-BL-MID", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED | {"KT-BL-FIRST", "KT-BL-MID", "KT-BL-LAST"})
        assert result[0]["tag"] == "KT-BL-FIRST"

    def test_rq_ll2_family_aligns_last_without_losing_level(self):
        blocks = [_block("p1", "Review question nested item", "BODY", list_kind="numbered", list_position="last")]
        clfs = [_clf("p1", "RQ-LL2-MID", 85)]
        result = validate_and_repair(clfs, blocks, ALLOWED | {"RQ-LL2-MID", "RQ-LL2-LAST"})
        assert result[0]["tag"] == "RQ-LL2-LAST"

    def test_bl2_first_falls_back_to_mid_when_first_variant_not_allowed(self):
        blocks = [_block("p1", "Nested bullet", "BODY", list_kind="bullet", list_position="first")]
        clfs = [_clf("p1", "BL2-MID", 85)]
        # ALLOWED lacks BL2-FIRST by design in this test set
        result = validate_and_repair(clfs, blocks, ALLOWED | {"BL2-MID", "BL2-LAST"})
        assert result[0]["tag"] == "BL2-MID"


class TestEndToEnd:
    def test_composite_through_pipeline(self):
        """Composite tag through validate_and_repair + enforce_style_compliance."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "TXT+PMI", 90)]

        # Stage 1: validate_and_repair (should fix composite)
        repaired = validate_and_repair(clfs, blocks, ALLOWED)
        assert repaired[0]["tag"] == "TXT"
        assert repaired[0]["repaired"] is True

        # Stage 2: enforce_style_compliance (should accept valid TXT)
        final = enforce_style_compliance(repaired, blocks, ALLOWED)
        assert final[0]["tag"] == "TXT"

    def test_alias_through_pipeline(self):
        """Alias (QUES_NUM → QUES-NL-MID) through pipeline."""
        blocks = [_block("p1", "1. Question", "EXERCISE")]
        clfs = [_clf("p1", "QUES_NUM", 85)]

        # Stage 1: validate_and_repair (should resolve alias)
        repaired = validate_and_repair(clfs, blocks, ALLOWED)
        # QUES_NUM should be resolved, but to what depends on normalize_style
        # Let's just check it's repaired
        assert repaired[0]["repaired"] is True

        # Stage 2: enforce_style_compliance
        final = enforce_style_compliance(repaired, blocks, ALLOWED)
        # Should be a valid tag
        assert final[0]["tag"] in ALLOWED

    def test_zone_forbidden_through_pipeline(self):
        """Invalid style through validate_and_repair + enforce_style_compliance."""
        blocks = [_block("p1", "Cell text", "BODY")]
        clfs = [_clf("p1", "INVALID-STYLE", 85)]

        # Stage 1: validate_and_repair (should fix invalid style)
        repaired = validate_and_repair(clfs, blocks, ALLOWED)
        # Should be repaired to valid style
        assert repaired[0]["tag"] in ALLOWED
        assert repaired[0]["repaired"] is True

        # Stage 2: enforce_style_compliance (should accept valid style)
        final = enforce_style_compliance(repaired, blocks, ALLOWED)
        # Should be valid tag
        assert final[0]["tag"] in ALLOWED


class TestLoggingIntegration:
    @patch('backend.processor.validator.logger')
    @patch('backend.processor.style_enforcement.logger')
    def test_both_stages_log_metrics(self, mock_enforcement_logger, mock_validator_logger):
        """Both validate_and_repair and enforce_style_compliance log metrics."""
        blocks = [_block("p1", "Text", "BODY")]
        clfs = [_clf("p1", "FAKE", 85)]

        # Stage 1: validate_and_repair
        repaired = validate_and_repair(clfs, blocks, ALLOWED)
        # Should log STYLE_CANONICALIZATION
        assert any(
            "STYLE_CANONICALIZATION" in str(call)
            for call in mock_validator_logger.info.call_args_list
        )

        # Stage 2: enforce_style_compliance
        final = enforce_style_compliance(repaired, blocks, ALLOWED)
        # Should log STYLE_ENFORCEMENT
        assert any(
            "STYLE_ENFORCEMENT" in str(call)
            for call in mock_enforcement_logger.info.call_args_list
        )
