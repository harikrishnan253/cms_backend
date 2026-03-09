"""
Tests for CASESTUDY-family tag canonicalization in style_normalizer.py.

Covers:
  - TestBuildCasestudyLookup   : lookup table construction from allowed set
  - TestNormalizeStyleCasestudy: normalize_style() resolves observed invalids
  - TestNormalizeTagCasestudy  : normalize_tag() (enforce_membership) also resolves
  - TestNonCasestudyUnaffected : unrelated tags pass through unchanged
  - TestInvalidTagDetection    : classifier._find_invalid_tags exclusion after fix
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# Reload module to pick up the current module-level state
import importlib
import app.services.style_normalizer as _sn_mod

from app.services.style_normalizer import (
    _build_casestudy_lookup,
    _CASESTUDY_LOOKUP,
    normalize_style,
    normalize_tag,
    _ALLOWED_STYLES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The canonical CaseStudy styles as declared in allowed_styles.json
_CANONICAL = {
    "CaseBeg Begin Case Study",
    "CaseEnd End Case Study",
    "CaseStudy-BulletList1",
    "CaseStudy-Dialogue",
    "CaseStudy-Dialogue_first",
    "CaseStudy-Dialogue_last",
    "CaseStudy-Heading1",
    "CaseStudy-Heading2",
    "CaseStudy-Note",
    "CaseStudy-NumberList1",
    "CaseStudy-NumberList1-first",
    "CaseStudy-NumberList1-last",
    "CaseStudy-Para-FL",
    "CaseStudy-ParaFirstLine-Ind",
    "CaseStudy-UL-FL1",
    "CaseStudyTitle",
}


# ---------------------------------------------------------------------------
# 1. _build_casestudy_lookup
# ---------------------------------------------------------------------------

class TestBuildCasestudyLookup:
    """_build_casestudy_lookup derives the lookup from any allowed set."""

    def test_returns_dict(self):
        result = _build_casestudy_lookup({"CaseStudy-Dialogue", "TXT"})
        assert isinstance(result, dict)

    def test_canonical_upper_key_maps_to_canonical(self):
        lookup = _build_casestudy_lookup({"CaseStudy-Dialogue"})
        assert lookup["CASESTUDY-DIALOGUE"] == "CaseStudy-Dialogue"

    def test_underscore_normalised_key_also_stored(self):
        # "CaseStudy-Dialogue_first" has an underscore; the normalised key
        # replaces it with a dash: "CASESTUDY-DIALOGUE-FIRST"
        lookup = _build_casestudy_lookup({"CaseStudy-Dialogue_first"})
        assert lookup.get("CASESTUDY-DIALOGUE-FIRST") == "CaseStudy-Dialogue_first"

    def test_casestudytitle_key_stored(self):
        lookup = _build_casestudy_lookup({"CaseStudyTitle"})
        assert lookup["CASESTUDYTITLE"] == "CaseStudyTitle"

    def test_casebeg_key_stored(self):
        lookup = _build_casestudy_lookup({"CaseBeg Begin Case Study"})
        assert lookup.get("CASEBEG BEGIN CASE STUDY") == "CaseBeg Begin Case Study"

    def test_caseend_key_stored(self):
        lookup = _build_casestudy_lookup({"CaseEnd End Case Study"})
        assert lookup.get("CASEEND END CASE STUDY") == "CaseEnd End Case Study"

    def test_non_casestudy_styles_excluded(self):
        lookup = _build_casestudy_lookup({"TXT", "BX4-TXT", "H1", "CaseStudy-Dialogue"})
        assert "TXT" not in lookup
        assert "BX4-TXT" not in lookup
        assert "H1" not in lookup

    def test_empty_set_returns_empty_dict(self):
        assert _build_casestudy_lookup(set()) == {}

    def test_full_canonical_set_all_present(self):
        lookup = _build_casestudy_lookup(_CANONICAL)
        for style in _CANONICAL:
            assert style.upper() in lookup, f"Missing key for '{style}'"
            assert lookup[style.upper()] == style

    def test_module_level_lookup_covers_allowed_styles(self):
        """_CASESTUDY_LOOKUP must include all CaseStudy entries from allowed_styles.json."""
        for style in _CANONICAL:
            if style in _ALLOWED_STYLES:
                assert style.upper() in _CASESTUDY_LOOKUP, (
                    f"'{style}' is in allowed_styles.json but missing from "
                    f"_CASESTUDY_LOOKUP"
                )

    def test_deterministic_across_calls(self):
        r1 = _build_casestudy_lookup(_CANONICAL)
        r2 = _build_casestudy_lookup(_CANONICAL)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 2. normalize_style: all 7 observed invalids → canonical
# ---------------------------------------------------------------------------

class TestNormalizeStyleCasestudy:
    """normalize_style() must resolve each observed invalid CASESTUDY variant."""

    def _ns(self, tag: str) -> str:
        return normalize_style(tag)

    # --- The 7 exact observed invalids from the task spec ---

    def test_casestudy_dialogue(self):
        assert self._ns("CASESTUDY-DIALOGUE") == "CaseStudy-Dialogue"

    def test_casestudy_dialogue_first(self):
        assert self._ns("CASESTUDY-DIALOGUE_FIRST") == "CaseStudy-Dialogue_first"

    def test_casestudy_dialogue_last(self):
        assert self._ns("CASESTUDY-DIALOGUE_LAST") == "CaseStudy-Dialogue_last"

    def test_casestudy_heading1(self):
        assert self._ns("CASESTUDY-HEADING1") == "CaseStudy-Heading1"

    def test_casestudy_para_fl(self):
        assert self._ns("CASESTUDY-PARA-FL") == "CaseStudy-Para-FL"

    def test_casestudy_parafirstline_ind(self):
        assert self._ns("CASESTUDY-PARAFIRSTLINE-IND") == "CaseStudy-ParaFirstLine-Ind"

    def test_casestudytitle(self):
        assert self._ns("CASESTUDYTITLE") == "CaseStudyTitle"

    # --- Dash/underscore variant (DIALOGUE-FIRST vs DIALOGUE_FIRST) ---

    def test_casestudy_dialogue_first_dash_variant(self):
        """Dash variant should also resolve to canonical (underscore-normalised key)."""
        assert self._ns("CASESTUDY-DIALOGUE-FIRST") == "CaseStudy-Dialogue_first"

    def test_casestudy_dialogue_last_dash_variant(self):
        assert self._ns("CASESTUDY-DIALOGUE-LAST") == "CaseStudy-Dialogue_last"

    # --- Other CASESTUDY entries ---

    def test_casestudy_bulletlist1(self):
        assert self._ns("CASESTUDY-BULLETLIST1") == "CaseStudy-BulletList1"

    def test_casestudy_numberlist1(self):
        assert self._ns("CASESTUDY-NUMBERLIST1") == "CaseStudy-NumberList1"

    def test_casestudy_numberlist1_first(self):
        assert self._ns("CASESTUDY-NUMBERLIST1-FIRST") == "CaseStudy-NumberList1-first"

    def test_casestudy_numberlist1_last(self):
        assert self._ns("CASESTUDY-NUMBERLIST1-LAST") == "CaseStudy-NumberList1-last"

    def test_casestudy_heading2(self):
        assert self._ns("CASESTUDY-HEADING2") == "CaseStudy-Heading2"

    def test_casestudy_note(self):
        assert self._ns("CASESTUDY-NOTE") == "CaseStudy-Note"

    def test_casestudy_ul_fl1(self):
        assert self._ns("CASESTUDY-UL-FL1") == "CaseStudy-UL-FL1"

    # --- CaseBeg / CaseEnd ---

    def test_casebeg_upper(self):
        result = self._ns("CASEBEG BEGIN CASE STUDY")
        assert result == "CaseBeg Begin Case Study"

    def test_caseend_upper(self):
        result = self._ns("CASEEND END CASE STUDY")
        assert result == "CaseEnd End Case Study"

    # --- Already-canonical forms pass through unchanged ---

    def test_canonical_already_valid_passthrough(self):
        for style in _CANONICAL:
            if style in _ALLOWED_STYLES:
                assert self._ns(style) == style, (
                    f"Canonical style '{style}' was mutated by normalize_style()"
                )

    # --- Underscore-only separator variant ---

    def test_casestudy_underscore_separated(self):
        """CASESTUDY_DIALOGUE (underscore not dash) must NOT be split by vendor-prefix."""
        # VENDOR_PREFIX_RE = r"^[A-Z]{2,}_(.+)$" would incorrectly strip to DIALOGUE
        # The CASESTUDY handler must fire first.
        result = self._ns("CASESTUDY_DIALOGUE")
        assert result == "CaseStudy-Dialogue"

    # --- Mixed case passthroughs ---

    def test_casestudy_mixed_case_already_valid(self):
        assert self._ns("CaseStudy-Dialogue") == "CaseStudy-Dialogue"

    def test_casestudytitle_title_case(self):
        assert self._ns("CaseStudyTitle") == "CaseStudyTitle"


# ---------------------------------------------------------------------------
# 3. normalize_tag (enforce_membership=True) — same results
# ---------------------------------------------------------------------------

class TestNormalizeTagCasestudy:
    """normalize_tag() (enforce_membership path) must resolve all CASESTUDY variants."""

    def _nt(self, tag: str) -> str:
        return normalize_tag(tag)

    def test_casestudy_dialogue_via_normalize_tag(self):
        assert self._nt("CASESTUDY-DIALOGUE") == "CaseStudy-Dialogue"

    def test_casestudytitle_via_normalize_tag(self):
        assert self._nt("CASESTUDYTITLE") == "CaseStudyTitle"

    def test_casestudy_heading1_via_normalize_tag(self):
        assert self._nt("CASESTUDY-HEADING1") == "CaseStudy-Heading1"

    def test_casestudy_para_fl_via_normalize_tag(self):
        assert self._nt("CASESTUDY-PARA-FL") == "CaseStudy-Para-FL"

    def test_casestudy_parafirstline_ind_via_normalize_tag(self):
        assert self._nt("CASESTUDY-PARAFIRSTLINE-IND") == "CaseStudy-ParaFirstLine-Ind"

    def test_casestudy_dialogue_first_via_normalize_tag(self):
        assert self._nt("CASESTUDY-DIALOGUE_FIRST") == "CaseStudy-Dialogue_first"

    def test_casestudy_dialogue_last_via_normalize_tag(self):
        assert self._nt("CASESTUDY-DIALOGUE_LAST") == "CaseStudy-Dialogue_last"

    def test_resolved_tag_is_in_allowed_styles(self):
        """Every resolved CASESTUDY tag must be a valid member of allowed_styles."""
        invalids = [
            "CASESTUDY-DIALOGUE",
            "CASESTUDY-DIALOGUE_FIRST",
            "CASESTUDY-DIALOGUE_LAST",
            "CASESTUDY-HEADING1",
            "CASESTUDY-PARA-FL",
            "CASESTUDY-PARAFIRSTLINE-IND",
            "CASESTUDYTITLE",
        ]
        for inv in invalids:
            result = self._nt(inv)
            assert result in _ALLOWED_STYLES, (
                f"normalize_tag('{inv}') = '{result}' is not in allowed_styles.json"
            )

    def test_no_downgrade_to_txt(self):
        """None of the 7 observed invalids should resolve to TXT or SP-TXT-FLUSH."""
        bad_fallbacks = {"TXT", "TXT-FLUSH", "SP-TXT-FLUSH"}
        invalids = [
            "CASESTUDY-DIALOGUE",
            "CASESTUDY-DIALOGUE_FIRST",
            "CASESTUDY-DIALOGUE_LAST",
            "CASESTUDY-HEADING1",
            "CASESTUDY-PARA-FL",
            "CASESTUDY-PARAFIRSTLINE-IND",
            "CASESTUDYTITLE",
        ]
        for inv in invalids:
            result = self._nt(inv)
            assert result not in bad_fallbacks, (
                f"normalize_tag('{inv}') fell back to '{result}' — should be canonical"
            )


# ---------------------------------------------------------------------------
# 4. Unrelated tags pass through unchanged
# ---------------------------------------------------------------------------

class TestNonCasestudyUnaffected:
    """Changes must not affect any non-CASESTUDY tags."""

    def _ns(self, tag: str) -> str:
        return normalize_style(tag)

    def test_txt_unchanged(self):
        assert self._ns("TXT") == "TXT"

    def test_h1_unchanged(self):
        assert self._ns("H1") == "H1"

    def test_bx4_txt_stripped_of_illegal_prefix(self):
        # Existing behavior: BX4- is an illegal prefix → stripped
        assert self._ns("BX4-TXT") == "TXT"

    def test_bl_first_unchanged(self):
        assert self._ns("BL-FIRST") == "BL-FIRST"

    def test_refh1_alias_resolved(self):
        # "Ref-H1" is in style_aliases.json
        assert self._ns("Ref-H1") == "REFH1"

    def test_normal_style_unchanged(self):
        assert self._ns("Normal") == "Normal"

    def test_heading1_unchanged(self):
        assert self._ns("Heading 1") == "Heading 1"

    def test_empty_string_unchanged(self):
        assert self._ns("") == ""

    def test_none_returns_empty(self):
        assert normalize_style(None) == ""

    def test_cs_h1_unchanged(self):
        # CS-H1 is a separate canonical tag — not a CASESTUDY variant
        assert self._ns("CS-H1") == "CS-H1"

    def test_cs_ttl_unchanged(self):
        assert self._ns("CS-TTL") == "CS-TTL"


# ---------------------------------------------------------------------------
# 5. Integration: classifier._find_invalid_tags no longer flags these
# ---------------------------------------------------------------------------

class TestInvalidTagDetection:
    """After the fix, _find_invalid_tags must exclude CASESTUDY canonical variants."""

    def _make_classifier(self):
        """Minimal classifier stub with just enough to call _find_invalid_tags."""
        from processor.classifier import GeminiClassifier
        clf = GeminiClassifier.__new__(GeminiClassifier)
        # Inject a no-op retriever and empty semantic artifacts
        clf.retriever = None
        clf._semantic_aliases = {}
        clf._transition_priors = {}
        return clf

    def test_casestudy_dialogue_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDY-DIALOGUE", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDY-DIALOGUE" not in invalid
        assert "CaseStudy-Dialogue" not in invalid

    def test_casestudytitle_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDYTITLE", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDYTITLE" not in invalid

    def test_casestudy_heading1_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDY-HEADING1", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDY-HEADING1" not in invalid

    def test_casestudy_para_fl_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDY-PARA-FL", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDY-PARA-FL" not in invalid

    def test_casestudy_parafirstline_ind_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDY-PARAFIRSTLINE-IND", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDY-PARAFIRSTLINE-IND" not in invalid

    def test_casestudy_dialogue_first_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDY-DIALOGUE_FIRST", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDY-DIALOGUE_FIRST" not in invalid

    def test_casestudy_dialogue_last_not_in_invalid(self):
        clf = self._make_classifier()
        results = [{"id": 1, "tag": "CASESTUDY-DIALOGUE_LAST", "confidence": 80}]
        invalid = clf._find_invalid_tags(results, meta_by_id={1: {}}, text_by_id={1: ""})
        assert "CASESTUDY-DIALOGUE_LAST" not in invalid

    def test_all_seven_invalids_clear(self):
        """All 7 observed invalids must be absent from the invalid set."""
        clf = self._make_classifier()
        observed_invalids = [
            "CASESTUDY-DIALOGUE",
            "CASESTUDY-DIALOGUE_FIRST",
            "CASESTUDY-DIALOGUE_LAST",
            "CASESTUDY-HEADING1",
            "CASESTUDY-PARA-FL",
            "CASESTUDY-PARAFIRSTLINE-IND",
            "CASESTUDYTITLE",
        ]
        results = [
            {"id": i + 1, "tag": tag, "confidence": 80}
            for i, tag in enumerate(observed_invalids)
        ]
        meta_by_id = {i + 1: {} for i in range(len(observed_invalids))}
        text_by_id = {i + 1: "" for i in range(len(observed_invalids))}
        invalid = clf._find_invalid_tags(results, meta_by_id=meta_by_id, text_by_id=text_by_id)
        for orig in observed_invalids:
            assert orig not in invalid, f"'{orig}' still in invalid set after fix"
        # Canonical forms should also not be invalid
        assert "CaseStudy-Dialogue" not in invalid
        assert "CaseStudyTitle" not in invalid
