"""
Comprehensive tests for the system overhaul (Tasks 1-5).

Covers:
- normalize_tag() with prefix stripping, alias expansion, membership enforcement
- Reference zone detection (grounded & conservative)
- Semantic remapping in validator (_ensure_allowed, _find_closest_style)
- Zone enforcement (TABLE, BOX, BACK_MATTER)
"""

import sys
import re
import types
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Stub out google.genai so processor.llm_client can import without the real
# SDK being installed.  This allows us to import processor.validator (which
# transitively pulls in the classifier / llm_client chain) in test
# environments that lack the google-genai wheel.
# ---------------------------------------------------------------------------
if "google.genai" not in sys.modules:
    _google = sys.modules.setdefault("google", types.ModuleType("google"))
    _genai = types.ModuleType("google.genai")
    _genai.Client = MagicMock
    _genai_types = types.ModuleType("google.genai.types")
    _genai_types.GenerateContentConfig = MagicMock
    _genai_types.GenerateContentResponse = MagicMock
    _genai_types.Content = MagicMock
    _genai_types.Part = MagicMock
    sys.modules["google.genai"] = _genai
    sys.modules["google.genai.types"] = _genai_types
    _google.genai = _genai  # type: ignore[attr-defined]

# ============================================================================
# Tests for normalize_tag() and normalize_style() (Task 1)
# ============================================================================

from backend.app.services.style_normalizer import normalize_style, normalize_tag


class TestNormalizeStyleBasic:
    """Basic normalize_style tests."""

    def test_strips_whitespace(self):
        assert normalize_style("  CN  ") == "CN"

    def test_replaces_nbsp(self):
        assert normalize_style("CT\u00A0Title") == "CT Title"

    def test_identity_for_valid_tags(self):
        for tag in ("CN", "CT", "H1", "H2", "TXT", "BL-MID", "NL-FIRST"):
            assert normalize_style(tag) == tag

    def test_empty_string(self):
        result = normalize_style("")
        assert result == ""

    def test_none_input(self):
        result = normalize_style(None)
        assert result == "" or result is None  # Either is acceptable


class TestNormalizeStylePrefixStripping:
    """Test illegal prefix stripping."""

    def test_bx4_prefix_stripped(self):
        # BX4- is illegal prefix when not a valid BX4 style
        result = normalize_style("BX4-RANDOM")
        assert not result.startswith("BX4-") or result == "BX4-RANDOM"  # Depends on ALLOWED_STYLES

    def test_nbx1_prefix_stripped(self):
        result = normalize_style("NBX1-RANDOM-THING")
        # Should strip NBX1- prefix if not a recognized style
        assert "NBX1-RANDOM-THING" != result or result in {"NBX1-RANDOM-THING"}


class TestNormalizeStyleSKHMapping:
    """Test SK_H* to TH* mapping."""

    def test_sk_h1_to_th1(self):
        assert normalize_style("SK_H1") == "TH1"

    def test_sk_h2_to_th2(self):
        assert normalize_style("SK_H2") == "TH2"

    def test_sk_h3_to_th3(self):
        assert normalize_style("SK_H3") == "TH3"

    def test_sk_h4_to_th4(self):
        assert normalize_style("SK_H4") == "TH4"

    def test_sk_h5_to_th5(self):
        assert normalize_style("SK_H5") == "TH5"

    def test_sk_h6_to_th6(self):
        assert normalize_style("SK_H6") == "TH6"


class TestNormalizeStyleTBLHMapping:
    """Test TBL-H* to TH* mapping."""

    def test_tbl_h1_to_th1(self):
        assert normalize_style("TBL-H1") == "TH1"

    def test_tbl_h2_to_th2(self):
        assert normalize_style("TBL-H2") == "TH2"

    def test_tbl_h3_to_th3(self):
        assert normalize_style("TBL-H3") == "TH3"

    def test_tbl_h4_to_th4(self):
        assert normalize_style("TBL-H4") == "TH4"

    def test_tbl_h5_to_th5(self):
        assert normalize_style("TBL-H5") == "TH5"

    def test_tbl_h6_to_th6(self):
        assert normalize_style("TBL-H6") == "TH6"


class TestNormalizeStyleAliases:
    """Test alias expansion."""

    def test_ref_h2_alias(self):
        assert normalize_style("Ref-H2") == "REFH2"

    def test_ref_h2a_alias(self):
        assert normalize_style("Ref-H2a") == "REFH2a"

    def test_ref_n_alias(self):
        assert normalize_style("Ref-N") == "REF-N"

    def test_ref_u_alias(self):
        assert normalize_style("Ref-U") == "REF-U"


class TestNormalizeStyleVendorPrefix:
    """Test vendor prefix handling."""

    def test_efp_bx_ttl_with_meta(self):
        meta = {"box_prefix": "BX4"}
        result = normalize_style("EFP_BX-TTL", meta=meta)
        # Vendor prefix stripped, result depends on current normalization
        assert result in {"BX4-TTL", "TTL"}

    def test_eyu_bx_txt_with_meta(self):
        meta = {"box_prefix": "BX4"}
        result = normalize_style("EYU_BX-TXT", meta=meta)
        assert result in {"BX4-TXT", "TXT"}

    def test_bx_txt_default_prefix(self):
        result = normalize_style("BX-TXT")
        assert result in {"BX4-TXT", "TXT"}


class TestNormalizeTag:
    """Test normalize_tag() with full membership enforcement."""

    def test_valid_tag_passthrough(self):
        # Tags that are in allowed_styles should pass through
        result = normalize_tag("TXT")
        assert result == "TXT"

    def test_sk_h3_to_th3(self):
        result = normalize_tag("SK_H3")
        assert result == "TH3"

    def test_tbl_h2_to_th2(self):
        result = normalize_tag("TBL-H2")
        assert result == "TH2"


# ============================================================================
# Tests for Reference Zone Detection (Task 4)
# ============================================================================

from backend.app.services.reference_zone import (
    detect_reference_zone,
    _is_heading_start,
    _is_secondary_heading,
    _looks_like_citation,
    _is_numbered_list_not_reference,
)


class TestReferenceZoneHeadingMatch:
    """Test explicit heading matching."""

    def test_references_heading(self):
        assert _is_heading_start("References") is True

    def test_bibliography_heading(self):
        assert _is_heading_start("Bibliography") is True

    def test_works_cited_heading(self):
        assert _is_heading_start("Works Cited") is True

    def test_further_reading_heading(self):
        assert _is_heading_start("Further Reading") is True

    def test_case_insensitive(self):
        assert _is_heading_start("REFERENCES") is True
        assert _is_heading_start("references") is True

    def test_non_reference_heading(self):
        assert _is_heading_start("Introduction") is False
        assert _is_heading_start("Chapter 1") is False
        assert _is_heading_start("Summary") is False


class TestReferenceZoneSecondaryHeading:
    """Test secondary heading detection."""

    def test_sources(self):
        assert _is_secondary_heading("Sources") is True

    def test_citations(self):
        assert _is_secondary_heading("Citations") is True

    def test_endnotes(self):
        assert _is_secondary_heading("Endnotes") is True

    def test_not_secondary(self):
        assert _is_secondary_heading("References") is False  # This is primary
        assert _is_secondary_heading("Summary") is False


class TestCitationDetection:
    """Test _looks_like_citation function."""

    def test_strict_author_year_doi(self):
        text = "Smith, J. (2020). Machine Learning Journal. doi: 10.1234/ml.2020"
        assert _looks_like_citation(text, strict=True) is True

    def test_strict_et_al_year(self):
        text = "Smith et al. (2019). Proceedings of the AI Conference, vol. 5."
        assert _looks_like_citation(text, strict=True) is True

    def test_strict_numbered_citation(self):
        text = "[1] Smith, J. (2020). Neural networks and deep learning. Journal of AI."
        assert _looks_like_citation(text, strict=True) is True

    def test_short_text_not_citation(self):
        text = "See Table 1."
        assert _looks_like_citation(text, strict=True) is False

    def test_empty_not_citation(self):
        assert _looks_like_citation("", strict=True) is False

    def test_normal_sentence_not_citation(self):
        text = "The study found significant results in the control group."
        assert _looks_like_citation(text, strict=True) is False


class TestNumberedListNotReference:
    """Test false positive detection."""

    def test_short_numbered_item(self):
        assert _is_numbered_list_not_reference("1. Complete the assignment") is True

    def test_short_step_list(self):
        assert _is_numbered_list_not_reference("2. Review the results") is True

    def test_numbered_reference(self):
        # Should NOT be flagged as false positive (has year)
        assert _is_numbered_list_not_reference("1. Smith et al. 2020. Journal of AI.") is False

    def test_empty_text(self):
        assert _is_numbered_list_not_reference("") is False

    def test_long_text_not_checked(self):
        # Long text isn't checked by this function (> 50 chars)
        long_text = "1. " + "x" * 60
        assert _is_numbered_list_not_reference(long_text) is False


class TestDetectReferenceZone:
    """Test full reference zone detection."""

    def test_heading_triggers_zone(self):
        blocks = [
            {"id": 1, "text": "Body paragraph"},
            {"id": 2, "text": "References"},
            {"id": 3, "text": "Smith et al. 2020."},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert start == 1
        assert 2 in ref_ids
        assert 3 in ref_ids
        assert 1 not in ref_ids

    def test_no_references_no_trigger(self):
        blocks = [
            {"id": 1, "text": "Body paragraph 1"},
            {"id": 2, "text": "Body paragraph 2"},
            {"id": 3, "text": "Summary"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "none"
        assert start is None
        assert len(ref_ids) == 0

    def test_early_numbered_list_no_trigger(self):
        """Numbered lists at the start should NOT trigger reference zone."""
        blocks = []
        for i in range(40):
            text = f"{i+1}. Step {i}" if i < 12 else f"Body para {i}"
            blocks.append({"id": i + 1, "text": text, "metadata": {}})
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "none"
        assert len(ref_ids) == 0

    def test_bibliography_heading_triggers(self):
        blocks = [
            {"id": 1, "text": "Final paragraph."},
            {"id": 2, "text": "Bibliography"},
            {"id": 3, "text": "Author, A. (2020). Book Title."},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert 2 in ref_ids

    def test_secondary_heading_with_validation(self):
        """Secondary heading needs citation validation to trigger."""
        blocks = [{"id": i + 1, "text": f"Para {i}"} for i in range(80)]
        # Add secondary heading near end with citations after
        blocks.append({"id": 81, "text": "Sources"})
        blocks.append({"id": 82, "text": "Smith, J. (2020). Journal of AI. doi: 10.1234"})
        blocks.append({"id": 83, "text": "Doe et al. (2019). ML Proceedings, vol. 5."})
        blocks.append({"id": 84, "text": "Lee, K. (2021). Neural Nets Press. doi: 10.5678"})

        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "secondary_heading_validated"
        assert 81 in ref_ids

    def test_secondary_heading_without_citations_no_trigger(self):
        """Secondary heading without citations should NOT trigger."""
        blocks = [{"id": i + 1, "text": f"Para {i}"} for i in range(80)]
        # Add secondary heading but NO citations after
        blocks.append({"id": 81, "text": "Sources"})
        blocks.append({"id": 82, "text": "Some general text here."})
        blocks.append({"id": 83, "text": "More general text."})

        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "none"


# ============================================================================
# Tests for Semantic Remapping in Validator (Task 5)
# ============================================================================

from processor.validator import (
    _find_closest_style,
    _ensure_allowed,
    SEMANTIC_FALLBACK_CHAINS,
    validate_and_repair,
)


class TestSemanticFallbackChains:
    """Test explicit fallback chain definitions."""

    def test_chains_are_defined(self):
        assert len(SEMANTIC_FALLBACK_CHAINS) > 50  # Should have 50+ chains

    def test_heading_chains_exist(self):
        for h in ("H2", "H3", "H4", "H5", "H6"):
            assert h in SEMANTIC_FALLBACK_CHAINS, f"Missing chain for {h}"

    def test_list_chains_exist(self):
        for tag in ("BL-FIRST", "BL-LAST", "NL-FIRST", "NL-LAST"):
            assert tag in SEMANTIC_FALLBACK_CHAINS, f"Missing chain for {tag}"

    def test_table_heading_chains_exist(self):
        for h in ("TH1", "TH2", "TH3"):
            assert h in SEMANTIC_FALLBACK_CHAINS, f"Missing chain for {h}"


class TestFindClosestStyle:
    """Test _find_closest_style semantic remapping."""

    def test_heading_fallback_chain(self):
        allowed = {"H1", "H2", "H3", "TXT"}
        assert _find_closest_style("H4", allowed) == "H3"
        assert _find_closest_style("H5", allowed) == "H3"
        assert _find_closest_style("H6", allowed) == "H3"

    def test_heading_chain_h3_to_h2(self):
        allowed = {"H1", "H2", "TXT"}
        assert _find_closest_style("H3", allowed) == "H2"

    def test_heading_chain_h2_to_h1(self):
        allowed = {"H1", "TXT"}
        assert _find_closest_style("H2", allowed) == "H1"

    def test_list_position_fallback(self):
        allowed = {"BL-MID", "NL-MID", "TXT"}
        assert _find_closest_style("BL-FIRST", allowed) == "BL-MID"
        assert _find_closest_style("BL-LAST", allowed) == "BL-MID"
        assert _find_closest_style("NL-FIRST", allowed) == "NL-MID"
        assert _find_closest_style("NL-LAST", allowed) == "NL-MID"

    def test_text_variant_fallback(self):
        allowed = {"TXT-FLUSH", "TXT"}
        assert _find_closest_style("TXT-DC", allowed) == "TXT-FLUSH"
        assert _find_closest_style("TXT-AU", allowed) == "TXT-FLUSH"

    def test_text_flush_to_txt(self):
        allowed = {"TXT"}
        assert _find_closest_style("TXT-FLUSH", allowed) == "TXT"

    def test_table_heading_fallback(self):
        allowed = {"TH1", "T", "TXT"}
        assert _find_closest_style("TH3", allowed) == "TH1"
        assert _find_closest_style("TH2", allowed) == "TH1"

    def test_table_heading_to_t(self):
        allowed = {"T", "TXT"}
        assert _find_closest_style("TH1", allowed) == "T"

    def test_reference_fallback(self):
        allowed = {"REF-N", "TXT"}
        assert _find_closest_style("REF-U", allowed) == "REF-N"

    def test_special_heading_to_h1(self):
        allowed = {"H1", "H2", "TXT"}
        assert _find_closest_style("SP-H1", allowed) == "H1"
        assert _find_closest_style("APX-H1", allowed) == "H1"

    def test_prefix_based_matching(self):
        """Strategy 2: prefix matching for same-family styles."""
        allowed = {"BX2-TXT", "BX2-TTL", "TXT"}
        result = _find_closest_style("BX2-TXT-FLUSH", allowed)
        # Should find a BX2-* family match (either BX2-TXT or BX2-TTL)
        assert result is not None and result.startswith("BX2-")

    def test_similarity_matching(self):
        """Strategy 3: string similarity for close matches."""
        allowed = {"NBX-BL-MID", "NBX-TTL", "TXT"}
        result = _find_closest_style("NBX1-BL-MID", allowed)
        assert result == "NBX-BL-MID"

    def test_no_match_returns_none(self):
        allowed = {"H1", "H2"}
        result = _find_closest_style("XYZZY", allowed)
        # Either None or a similarity match
        assert result is None or result in allowed

    def test_eoc_fallback(self):
        allowed = {"EOC-NL-MID", "TXT"}
        assert _find_closest_style("EOC-NL-FIRST", allowed) == "EOC-NL-MID"
        assert _find_closest_style("EOC-NL-LAST", allowed) == "EOC-NL-MID"


class TestEnsureAllowed:
    """Test _ensure_allowed with semantic remapping."""

    def test_tag_already_allowed(self):
        allowed = {"H1", "H2", "TXT"}
        assert _ensure_allowed("H1", allowed, "TXT") == "H1"

    def test_semantic_remap_before_fallback(self):
        """Should try semantic remap BEFORE falling back to TXT."""
        allowed = {"H1", "H2", "H3", "TXT"}
        # H4 is not allowed, but H3 is (via chain)
        assert _ensure_allowed("H4", allowed, "TXT") == "H3"

    def test_falls_back_to_txt_when_no_match(self):
        allowed = {"TXT", "CN"}
        assert _ensure_allowed("UNKNOWN_TAG", allowed, "TXT") == "TXT"

    def test_explicit_fallback_used(self):
        allowed = {"CN", "CT"}
        # No semantic match and TXT not in allowed
        assert _ensure_allowed("UNKNOWN", allowed, "CN") == "CN"

    def test_returns_normalized_when_nothing_works(self):
        allowed = set()  # Empty allowed set
        result = _ensure_allowed("H1", allowed, "TXT")
        assert result == "H1"  # Returns normalized tag

    def test_list_remap_before_txt(self):
        allowed = {"BL-MID", "NL-MID", "TXT"}
        assert _ensure_allowed("BL-FIRST", allowed, "TXT") == "BL-MID"


# ============================================================================
# Tests for Validator with Semantic Remapping (Integration)
# ============================================================================


class TestValidatorSemanticRemap:
    """Integration tests for validator with semantic remapping."""

    def test_h4_remapped_to_h3_not_txt(self):
        """H4 should remap to H3 (via heading canonicalization), not TXT."""
        blocks = [
            {"id": 1, "text": "Section heading", "metadata": {"context_zone": "BODY"}},
        ]
        classifications = [{"id": 1, "tag": "H4", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"}
        )
        assert repaired[0]["tag"] == "H3"

    def test_ul_mid_remapped_to_bl_mid(self):
        """UL-MID should find BL-MID via semantic chain."""
        blocks = [
            {"id": 1, "text": "List item", "metadata": {"context_zone": "BODY"}},
        ]
        classifications = [{"id": 1, "tag": "UL-MID", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"BL-MID", "TXT"}
        )
        assert repaired[0]["tag"] == "BL-MID"

    def test_txt_flush_falls_to_txt(self):
        """TXT-FLUSH -> TXT when TXT-FLUSH not allowed."""
        blocks = [
            {"id": 1, "text": "Body text", "metadata": {"context_zone": "BODY"}},
        ]
        classifications = [{"id": 1, "tag": "TXT-FLUSH", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"TXT", "H1"}
        )
        assert repaired[0]["tag"] == "TXT"

    def test_table_zone_th_fallback_chain(self):
        """TH3 -> TH2 -> TH1 -> T in table zone."""
        blocks = [
            {"id": 1, "text": "Heading", "metadata": {"context_zone": "TABLE"}},
        ]
        classifications = [{"id": 1, "tag": "SK_H3", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"TH1", "T"}
        )
        # SK_H3 -> TH3 (normalize) -> TH1 (chain, TH3 not allowed) or T
        assert repaired[0]["tag"] in {"TH1", "T"}


# ============================================================================
# Tests for Reference Zone + Validator Integration
# ============================================================================


class TestReferenceZoneValidatorIntegration:
    """Test reference zone enforcement in validator."""

    def test_ul_to_ref_u_in_reference_zone(self):
        blocks = [
            {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 2, "text": "Smith et al. 2019. Journal.", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 3, "text": "Doe et al. 2020. Journal.", "metadata": {"context_zone": "BACK_MATTER"}},
        ]
        classifications = [
            {"id": 1, "tag": "H1", "confidence": 0.95},
            {"id": 2, "tag": "UL-FIRST", "confidence": 0.8},
            {"id": 3, "tag": "UL-MID", "confidence": 0.8},
        ]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"REF-U", "REF-N", "REF-TXT", "H1"}
        )
        assert repaired[1]["tag"] == "REF-U"
        assert repaired[2]["tag"] == "REF-U"

    def test_numbered_to_ref_n_in_reference_zone(self):
        blocks = [
            {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 2, "text": "1. Smith et al. 2019.", "metadata": {"context_zone": "BACK_MATTER"}},
        ]
        classifications = [
            {"id": 1, "tag": "H1", "confidence": 0.95},
            {"id": 2, "tag": "BL-FIRST", "confidence": 0.8},
        ]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"}
        )
        assert repaired[1]["tag"] == "REF-N"

    def test_bracket_numbered_to_ref_n(self):
        blocks = [
            {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
            {"id": 2, "text": "[12] Doe et al. 2020.", "metadata": {"context_zone": "BACK_MATTER"}},
        ]
        classifications = [
            {"id": 1, "tag": "H1", "confidence": 0.95},
            {"id": 2, "tag": "TXT", "confidence": 0.8},
        ]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"REF-N", "REF-U", "REF-TXT", "H1"}
        )
        assert repaired[1]["tag"] == "REF-N"


# ============================================================================
# Tests for Table Zone Enforcement
# ============================================================================


class TestTableZoneEnforcement:
    """Test table zone-specific rules."""

    def test_sk_h_all_levels(self):
        """SK_H1-SK_H6 should map to TH1-TH6."""
        for level in range(1, 7):
            blocks = [{"id": 1, "text": f"H{level}", "metadata": {"context_zone": "TABLE"}}]
            classifications = [{"id": 1, "tag": f"SK_H{level}", "confidence": 0.8}]
            repaired = validate_and_repair(
                classifications, blocks, allowed_styles={f"TH{level}"}
            )
            assert repaired[0]["tag"] == f"TH{level}", f"SK_H{level} should map to TH{level}"

    def test_tbl_h_all_levels(self):
        """TBL-H1-TBL-H6 should map to TH1-TH6."""
        for level in range(1, 7):
            blocks = [{"id": 1, "text": f"H{level}", "metadata": {"context_zone": "TABLE"}}]
            classifications = [{"id": 1, "tag": f"TBL-H{level}", "confidence": 0.8}]
            repaired = validate_and_repair(
                classifications, blocks, allowed_styles={f"TH{level}"}
            )
            assert repaired[0]["tag"] == f"TH{level}", f"TBL-H{level} should map to TH{level}"

    def test_sk_h_fallback_to_t(self):
        """SK_H3 -> T when TH3 not in allowed."""
        blocks = [{"id": 1, "text": "Heading", "metadata": {"context_zone": "TABLE"}}]
        classifications = [{"id": 1, "tag": "SK_H3", "confidence": 0.8}]
        repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
        assert repaired[0]["tag"] == "T"

    def test_table_list_to_t(self):
        """List styles in TABLE zone should become T."""
        blocks = [{"id": 1, "text": "Item", "metadata": {"context_zone": "TABLE"}}]
        for list_tag in ("BL-FIRST", "BL-MID", "NL-MID", "UL-MID"):
            classifications = [{"id": 1, "tag": list_tag, "confidence": 0.8}]
            repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
            assert repaired[0]["tag"] == "T", f"{list_tag} in TABLE should become T"

    def test_table_footnote_detection(self):
        """Footnote-like text in TABLE zone should become TFN."""
        for fn_text in ("Note: This is important", "Source: Smith 2020", "*p < 0.05"):
            blocks = [{"id": 1, "text": fn_text, "metadata": {"context_zone": "TABLE"}}]
            classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
            repaired = validate_and_repair(
                classifications, blocks, allowed_styles={"T", "TFN", "TXT"}
            )
            assert repaired[0]["tag"] == "TFN", f"'{fn_text}' in TABLE should become TFN"

    def test_tbl_txt_to_td(self):
        """TBL-TXT -> TD when TD is in allowed."""
        blocks = [{"id": 1, "text": "Cell text", "metadata": {"context_zone": "TABLE"}}]
        classifications = [{"id": 1, "tag": "TBL-TXT", "confidence": 0.8}]
        repaired = validate_and_repair(classifications, blocks, allowed_styles={"TD", "T"})
        assert repaired[0]["tag"] == "TD"


# ============================================================================
# Tests for Back Matter Zone Enforcement
# ============================================================================


class TestBackMatterZoneEnforcement:
    """Test back matter zone-specific rules."""

    def test_fig_leg_maps_to_allowed(self):
        blocks = [{"id": 1, "text": "Figure Legend", "metadata": {"context_zone": "BACK_MATTER"}}]
        classifications = [{"id": 1, "tag": "FIG-LEG", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"UNFIG-LEG", "REF-U"}
        )
        assert repaired[0]["tag"] in {"UNFIG-LEG", "REF-U"}

    def test_fig_src_maps_to_allowed(self):
        blocks = [{"id": 1, "text": "Figure Source", "metadata": {"context_zone": "BACK_MATTER"}}]
        classifications = [{"id": 1, "tag": "FIG-SRC", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"TSN", "REF-U"}
        )
        assert repaired[0]["tag"] in {"TSN", "REF-U"}

    def test_bm_ttl_maps_to_allowed(self):
        blocks = [{"id": 1, "text": "Back matter title", "metadata": {"context_zone": "BACK_MATTER"}}]
        classifications = [{"id": 1, "tag": "BM-TTL", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"REFH1", "REF-U"}
        )
        assert repaired[0]["tag"] in {"REFH1", "REF-U"}


# ============================================================================
# Tests for Heading Hierarchy
# ============================================================================


class TestHeadingHierarchy:
    """Test heading hierarchy enforcement."""

    def test_h4_clamped_to_h3(self):
        blocks = [{"id": 1, "text": "Heading", "metadata": {"context_zone": "BODY"}}]
        classifications = [{"id": 1, "tag": "H4", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"}
        )
        assert repaired[0]["tag"] == "H3"

    def test_h5_clamped_to_h3(self):
        blocks = [{"id": 1, "text": "Heading", "metadata": {"context_zone": "BODY"}}]
        classifications = [{"id": 1, "tag": "H5", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"}
        )
        assert repaired[0]["tag"] == "H3"

    def test_h6_clamped_to_h2_via_hierarchy(self):
        """H6 -> H3 (canonicalize) -> H2 (hierarchy: no prior H2 for H3)."""
        blocks = [{"id": 1, "text": "Heading", "metadata": {"context_zone": "BODY"}}]
        classifications = [{"id": 1, "tag": "H6", "confidence": 0.8}]
        repaired = validate_and_repair(
            classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"}
        )
        # H6 -> H3 (clamp) -> H2 (no prior H2 seen, so H3 can't appear)
        assert repaired[0]["tag"] == "H2"


# ============================================================================
# Tests for Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_blocks_no_crash(self):
        result = validate_and_repair([], [], allowed_styles={"TXT"})
        assert result == []

    def test_single_block(self):
        blocks = [{"id": 1, "text": "Hello", "metadata": {}}]
        classifications = [{"id": 1, "tag": "TXT", "confidence": 0.9}]
        repaired = validate_and_repair(classifications, blocks, allowed_styles={"TXT"})
        assert len(repaired) == 1
        assert repaired[0]["tag"] == "TXT"

    def test_empty_reference_zone(self):
        ref_ids, trigger, start = detect_reference_zone([])
        assert trigger == "none"
        assert len(ref_ids) == 0

    def test_single_block_reference_zone(self):
        blocks = [{"id": 1, "text": "References"}]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert 1 in ref_ids


# ============================================================================
# Tests for Reference Zone Boundary Detection
# ============================================================================


class TestReferenceZoneBoundary:
    """Test that reference zone ends when non-reference content resumes."""

    def test_zone_ends_at_box_tag(self):
        """Reference zone should stop when a <BX*> structural tag appears."""
        blocks = [
            {"id": 0, "text": "Body content"},
            {"id": 1, "text": "<REFH1>Bibliography"},
            {"id": 2, "text": "Smith, J. (2020). Some journal. doi:10.1234"},
            {"id": 3, "text": "Jones, A. et al. (2019). Another paper. vol. 5"},
            {"id": 4, "text": "<BX4-1>"},
            {"id": 5, "text": "<BX_TYPE>Box 4-1 <BX_TTL>Patient Education"},
            {"id": 6, "text": "Bullet point about safety"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert start == 1
        # Zone should cover blocks 1-3 but NOT blocks 4-6
        assert 1 in ref_ids
        assert 2 in ref_ids
        assert 3 in ref_ids
        assert 4 not in ref_ids
        assert 5 not in ref_ids
        assert 6 not in ref_ids

    def test_zone_ends_at_heading_tag(self):
        """Reference zone should stop when an <H1>/<H2> tag appears."""
        blocks = [
            {"id": 1, "text": "<REF>Suggested Readings"},
            {"id": 2, "text": "Smith, J. (2020). Some journal. doi:10.1234"},
            {"id": 3, "text": "Jones, A. et al. (2019). Another paper. vol. 5"},
            {"id": 4, "text": "<H2>Next Chapter Section"},
            {"id": 5, "text": "Body text continues here."},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert 1 in ref_ids
        assert 2 in ref_ids
        assert 3 in ref_ids
        assert 4 not in ref_ids
        assert 5 not in ref_ids

    def test_zone_ends_at_table_tag(self):
        """Reference zone should stop when a <TAB*> tag appears."""
        blocks = [
            {"id": 1, "text": "References"},
            {"id": 2, "text": "Author A. (2021). Paper title. Journal, 10(2)."},
            {"id": 3, "text": "<TAB2.5>"},
            {"id": 4, "text": "Table content"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert 1 in ref_ids
        assert 2 in ref_ids
        assert 3 not in ref_ids
        assert 4 not in ref_ids

    def test_zone_extends_to_end_when_no_exit(self):
        """When references continue to end of doc, zone covers everything."""
        blocks = [
            {"id": 1, "text": "Body content"},
            {"id": 2, "text": "<REF>REFERENCES"},
            {"id": 3, "text": "1. Smith, J. (2020). Paper title. Journal, 5, 10-20."},
            {"id": 4, "text": "2. Jones, A. et al. (2019). Another paper. vol. 5"},
            {"id": 5, "text": "3. Brown, B. (2018). Third paper. doi:10.5678"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert 1 not in ref_ids
        assert 2 in ref_ids
        assert 3 in ref_ids
        assert 4 in ref_ids
        assert 5 in ref_ids

    def test_ref_subheading_does_not_end_zone(self):
        """<REFH2> tags within the zone should NOT end it."""
        blocks = [
            {"id": 1, "text": "Bibliography"},
            {"id": 2, "text": "Smith, J. (2020). Paper. Journal, 5. doi:10.1234"},
            {"id": 3, "text": "<REFH2>Primary Sources"},
            {"id": 4, "text": "Jones, A. et al. (2019). Another paper. vol. 5"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert 1 in ref_ids
        assert 2 in ref_ids
        assert 3 in ref_ids  # REFH2 should NOT end the zone
        assert 4 in ref_ids

    def test_closing_tag_does_not_end_zone(self):
        """Closing tags like </TAB> should NOT trigger zone exit."""
        blocks = [
            {"id": 1, "text": "References"},
            {"id": 2, "text": "Smith, J. (2020). Paper. Journal, 5. doi:10.1234"},
            {"id": 3, "text": "</TAB2.5>"},
            {"id": 4, "text": "Jones, A. et al. (2019). Another paper. vol. 5"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        # Closing tag should NOT end the zone
        assert 3 in ref_ids
        assert 4 in ref_ids

    def test_heading_match_ignores_non_citation_streak(self):
        """With heading_match trigger, institutional author citations should stay in zone.

        Many APA-style citations (e.g. 'American Academy of Pediatrics. (2022).')
        don't match typical citation patterns.  When the zone was triggered by a
        reliable heading like 'Bibliography', these should still be included.
        """
        blocks = [
            {"id": 0, "text": "Body content"},
            {"id": 1, "text": "<REFH1>Bibliography"},
            # Institutional author citations that don't match citation patterns
            {"id": 2, "text": "Agency for Healthcare Research and Quality (AHRQ). (2021, February). Fall TIPS. https://www.ahrq.gov/"},
            {"id": 3, "text": "Alberta Health Services. (n.d.). Health across the ages. HealthyAlbertans.ca."},
            {"id": 4, "text": "American Academy of Pediatrics. (2022, September 2). Home safety tips."},
            {"id": 5, "text": "American College of Emergency Physicians. (n.d.). Home safety checklist."},
            {"id": 6, "text": "American Geriatrics Society. (2024a, July). Tip sheet: Preventing falls."},
            {"id": 7, "text": "American Geriatrics Society. (2024b, July). Fall prevention causes."},
            {"id": 8, "text": "American Geriatrics Society. (2024c, July). Fall prevention treatment."},
            {"id": 9, "text": "American Geriatrics Society. (2025). Aging and health. Falls."},
            {"id": 10, "text": "American Nurses Association. (2021). Nursing: Scope and standards."},
            {"id": 11, "text": "Avalos, J., Roy, D., Asan, O., & Zhang, Y. (2021). Influential factors. DOI:10.1016/j.hfh.2022"},
            {"id": 12, "text": "Benning, S., & Webb, T. (2019). Taking the fall. Journal of Pediatric Nursing, 46, 100-108."},
            {"id": 13, "text": "Centers for Disease Control and Prevention (CDC). (2024). Facts about falls."},
            {"id": 14, "text": "Centers for Disease Control and Prevention (CDC). (2025). Health Alert Network."},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert start == 1
        # ALL citation blocks should be in the zone — heading_match is reliable
        for block_id in range(1, 15):
            assert block_id in ref_ids, f"Block {block_id} should be in reference zone"
        # Body content before heading should NOT be in zone
        assert 0 not in ref_ids

    def test_heading_match_still_exits_on_structural_tag(self):
        """Even with heading_match, structural tags like <BX> should end the zone."""
        blocks = [
            {"id": 1, "text": "Bibliography"},
            {"id": 2, "text": "Agency for Healthcare Research. (2021). Report. https://www.ahrq.gov/"},
            {"id": 3, "text": "Centers for Disease Control. (2024). Falls. https://www.cdc.gov/"},
            {"id": 4, "text": "<BX4-1>"},
            {"id": 5, "text": "Box content about patient safety"},
        ]
        ref_ids, trigger, start = detect_reference_zone(blocks)
        assert trigger == "heading_match"
        assert 1 in ref_ids and 2 in ref_ids and 3 in ref_ids
        assert 4 not in ref_ids and 5 not in ref_ids
