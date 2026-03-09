"""
Tests for tools/build_semantic_knowledge.py

Coverage
--------
- Unit tests for all helper/classification functions
- Extraction function correctness on small synthetic corpora
- Artifact schema validation (required fields + schema_version)
- Regression: no raw paragraph text stored in runtime-facing artifact fields
- Integration: main() generates all 4 artifacts from a synthetic JSONL
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the tool module
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]  # AI-structuring/
_TOOLS = str(ROOT / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import build_semantic_knowledge as bsm  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _ex(
    doc_id: str,
    para_index: int,
    canonical_gold_tag: str,
    *,
    zone: str = "BODY",
    alignment_score: float = 1.0,
    text: str = "sample paragraph",
) -> dict:
    """Build a minimal ground-truth example dict."""
    return {
        "doc_id": doc_id,
        "para_index": para_index,
        "text": text,
        "gold_tag": canonical_gold_tag,
        "canonical_gold_tag": canonical_gold_tag,
        "alignment_score": alignment_score,
        "zone": zone,
        "notes": "",
    }


# A reusable small synthetic corpus covering all tag families
_SYNTHETIC_CORPUS = [
    # doc1 — body zone
    _ex("doc1", 0,  "H1"),
    _ex("doc1", 1,  "TXT"),
    _ex("doc1", 2,  "TXT-FLUSH"),
    _ex("doc1", 3,  "BL-FIRST"),
    _ex("doc1", 4,  "BL-MID"),
    _ex("doc1", 5,  "BL-LAST"),
    _ex("doc1", 6,  "PMI"),
    _ex("doc1", 7,  "T1"),
    _ex("doc1", 8,  "TFN"),
    _ex("doc1", 9,  "REF-N",  zone="REFERENCE"),
    _ex("doc1", 10, "REF-N",  zone="REFERENCE"),
    # doc1 — publisher styles (non-clean canonical)
    _ex("doc1", 11, "Head2"),
    _ex("doc1", 12, "BulletList1"),
    # doc1 — UNMAPPED (low alignment, should be excluded from quality filter)
    _ex("doc1", 13, "UNMAPPED", alignment_score=0.0),
    # doc2 — various families
    _ex("doc2", 0,  "H1"),
    _ex("doc2", 1,  "H2"),
    _ex("doc2", 2,  "NL-FIRST"),
    _ex("doc2", 3,  "NL-MID"),
    _ex("doc2", 4,  "NL-LAST"),
    _ex("doc2", 5,  "BL2-FIRST"),
    _ex("doc2", 6,  "BL2-MID"),
    _ex("doc2", 7,  "KT-BL-MID"),
    _ex("doc2", 8,  "EOC-H1"),
    _ex("doc2", 9,  "REF-U", zone="REFERENCE"),
]

# Quality subset (alignment >= 0.75, non-UNMAPPED)
_QUALITY = [
    ex for ex in _SYNTHETIC_CORPUS
    if ex["alignment_score"] >= 0.75
    and ex["canonical_gold_tag"] not in ("", "UNMAPPED", None)
]


# ===========================================================================
# Helper function unit tests
# ===========================================================================

class TestStripPositional:
    def test_with_first_suffix(self):
        base, suf = bsm.strip_positional("BL-FIRST")
        assert base == "BL"
        assert suf == "FIRST"

    def test_with_mid_suffix(self):
        base, suf = bsm.strip_positional("NL-MID")
        assert base == "NL"
        assert suf == "MID"

    def test_with_last_suffix(self):
        base, suf = bsm.strip_positional("UL-LAST")
        assert base == "UL"
        assert suf == "LAST"

    def test_with_only_suffix(self):
        base, suf = bsm.strip_positional("EQ-ONLY")
        assert base == "EQ"
        assert suf == "ONLY"

    def test_no_suffix(self):
        base, suf = bsm.strip_positional("BL")
        assert base == "BL"
        assert suf is None

    def test_compound_prefix_suffix(self):
        base, suf = bsm.strip_positional("KT-BL-MID")
        assert base == "KT-BL"
        assert suf == "MID"

    def test_depth_with_suffix(self):
        base, suf = bsm.strip_positional("BL2-FIRST")
        assert base == "BL2"
        assert suf == "FIRST"

    def test_eoc_list_suffix(self):
        base, suf = bsm.strip_positional("EOC-NL-LAST")
        assert base == "EOC-NL"
        assert suf == "LAST"


class TestIsCleanCanonical:
    @pytest.mark.parametrize("tag", [
        "H1", "H2", "H3", "H4", "H5", "H6",
        "CN", "CT",
        "TXT", "TXT-FLUSH",
        "PMI",
        "TBL-FIRST", "TBL-MID", "TBL-LAST", "TBL3",
        "T", "T1", "T2", "T4", "TFN", "TSN",
        "BL", "BL-FIRST", "BL-MID", "BL-LAST",
        "NL2-MID", "UL-ONLY",
        "KT-BL-MID", "EOC-NL-LAST",
        "REF-N", "REF-U", "SR",
        "EOC-H1", "KT-TXT", "OBJ-NL-FIRST",
        "BX-TTL", "BX1-H1",
        "FIG-LEG",
    ])
    def test_clean_tags_identified(self, tag: str):
        assert bsm.is_clean_canonical(tag), f"{tag!r} should be clean canonical"

    @pytest.mark.parametrize("tag", [
        "Normal", "Head2", "BulletList1", "NumberList1",
        "ParaFirstLine-Ind", "Para-FL", "CaseStudyTitle",
        "Reference-Alphabetical", "ChapterTitle", "ChapterNumber",
        "", "UNMAPPED",
    ])
    def test_publisher_styles_not_clean(self, tag: str):
        assert not bsm.is_clean_canonical(tag), f"{tag!r} should NOT be clean canonical"


class TestClassifyFamily:
    @pytest.mark.parametrize("tag,expected_family", [
        ("H1",         "heading"),
        ("H6",         "heading"),
        ("CN",         "chapter_front_matter"),
        ("CT",         "chapter_front_matter"),
        ("TXT",        "body_text"),
        ("TXT-FLUSH",  "body_text"),
        ("PMI",        "marker"),
        ("T1",         "table_cell"),
        ("T4",         "table_cell"),
        ("TFN",        "table_cell"),
        ("TSN",        "table_cell"),
        ("TBL-FIRST",  "table_body"),
        ("TBL-MID",    "table_body"),
        ("TBL3",       "table_body"),
        ("BL",         "bullet_list"),
        ("BL-FIRST",   "bullet_list"),
        ("BL-MID",     "bullet_list"),
        ("BL2-MID",    "bullet_list"),
        ("NL-FIRST",   "numbered_list"),
        ("NL2",        "numbered_list"),
        ("UL-LAST",    "unnumbered_list"),
        ("REF-N",      "references"),
        ("REF-U",      "references"),
        ("SR",         "references"),  # SR matches _REF_RE before family-prefix check
        ("EOC-H1",     "end_of_chapter"),
        ("KT-BL-MID",  "key_terms_bullet_list"),
        ("KT-NL-FIRST","key_terms_numbered_list"),
        ("OBJ-NL-MID", "objectives_numbered_list"),
        ("NBX-BL-MID", "numbered_box_bullet_list"),
        ("BX-TTL",     "box"),
        ("UNMAPPED",   "unmapped"),
    ])
    def test_family_classification(self, tag: str, expected_family: str):
        assert bsm.classify_family(tag) == expected_family, (
            f"classify_family({tag!r}) expected {expected_family!r}"
        )

    def test_empty_tag_is_unmapped(self):
        assert bsm.classify_family("") == "unmapped"

    def test_eoc_list_tag(self):
        # EOC-NL-LAST → end_of_chapter_numbered_list
        fam = bsm.classify_family("EOC-NL-LAST")
        assert fam == "end_of_chapter_numbered_list"


class TestExtractListInfo:
    def test_simple_bl(self):
        info = bsm.extract_list_info("BL-MID")
        assert info is not None
        assert info["list_type"] == "BL"
        assert info["depth"] == 1
        assert info["family_prefix"] is None
        assert info["positional_suffix"] == "MID"

    def test_depth_2(self):
        info = bsm.extract_list_info("BL2-FIRST")
        assert info is not None
        assert info["depth"] == 2
        assert info["positional_suffix"] == "FIRST"

    def test_family_prefixed(self):
        info = bsm.extract_list_info("KT-BL-LAST")
        assert info is not None
        assert info["list_type"] == "BL"
        assert info["family_prefix"] == "KT"
        assert info["positional_suffix"] == "LAST"

    def test_eoc_nl(self):
        info = bsm.extract_list_info("EOC-NL-FIRST")
        assert info is not None
        assert info["list_type"] == "NL"
        assert info["family_prefix"] == "EOC"
        assert info["depth"] == 1

    def test_non_list_returns_none(self):
        assert bsm.extract_list_info("H1") is None
        assert bsm.extract_list_info("TXT") is None
        assert bsm.extract_list_info("PMI") is None
        assert bsm.extract_list_info("REF-N") is None

    def test_plain_base_no_suffix(self):
        info = bsm.extract_list_info("BL")
        assert info is not None
        assert info["depth"] == 1
        assert info["positional_suffix"] is None


class TestHeuristicCanonical:
    @pytest.mark.parametrize("raw,expected_canonical,min_conf", [
        ("Head2",              "H2",         0.85),
        ("Head1",              "H1",         0.85),
        ("BulletList1_first",  "BL-FIRST",   0.85),
        ("BulletList1_last",   "BL-LAST",    0.85),
        ("BulletList1",        "BL-MID",     0.70),
        ("NumberList1",        "NL-MID",     0.70),  # no FIRST/LAST substring → ambiguous MID
        ("Lc-AlphaList3",      "UL-MID",     0.60),
        ("Normal",             "TXT",        0.80),
        ("Para-FL",            "TXT-FLUSH",  0.80),
        ("ParaFirstLine-Ind",  "TXT-FLUSH",  0.80),
        ("Reference-Alphabetical", "REF-U",  0.80),
        ("ChapterNumber",      "CN",         0.85),
        ("ChapterTitle",       "CT",         0.85),
        ("FigureLegend",       "FIG-LEG",    0.80),
    ])
    def test_suggestion_and_confidence(
        self, raw: str, expected_canonical: str, min_conf: float
    ):
        suggestion, confidence = bsm._heuristic_canonical(raw)
        assert suggestion == expected_canonical, (
            f"_heuristic_canonical({raw!r}) → got {suggestion!r}, expected {expected_canonical!r}"
        )
        assert confidence >= min_conf, (
            f"confidence {confidence:.2f} < min {min_conf:.2f} for {raw!r}"
        )

    def test_unknown_returns_none_suggestion(self):
        suggestion, confidence = bsm._heuristic_canonical("ZZZUNKNOWNSTYLE")
        assert suggestion is None
        assert confidence == 0.0


# ===========================================================================
# Extraction function tests
# ===========================================================================

class TestZoneTagPriors:
    def test_zones_present(self):
        result = bsm.build_zone_tag_priors(_QUALITY)
        assert "BODY" in result
        assert "REFERENCE" in result

    def test_body_contains_expected_tags(self):
        result = bsm.build_zone_tag_priors(_QUALITY)
        body = result["BODY"]
        assert "TXT" in body["distribution"]
        assert "H1" in body["distribution"]
        assert "BL-MID" in body["distribution"]

    def test_reference_contains_ref_tags(self):
        result = bsm.build_zone_tag_priors(_QUALITY)
        ref = result["REFERENCE"]
        assert "REF-N" in ref["distribution"]
        assert "REF-U" in ref["distribution"]

    def test_total_matches_example_count(self):
        result = bsm.build_zone_tag_priors(_QUALITY)
        # UNMAPPED excluded from _QUALITY already; verify totals
        body_total = result["BODY"]["total"]
        ref_total = result["REFERENCE"]["total"]
        assert body_total + ref_total == len(_QUALITY)

    def test_frequency_sums_to_approximately_one(self):
        result = bsm.build_zone_tag_priors(_QUALITY)
        for zone, zd in result.items():
            total_freq = sum(td["frequency"] for td in zd["distribution"].values())
            # May not be exactly 1 if top-40 truncation is applied on a small set
            assert 0.99 <= total_freq <= 1.01, (
                f"Zone {zone}: frequencies sum to {total_freq:.4f}"
            )

    def test_unmapped_excluded(self):
        result = bsm.build_zone_tag_priors(_QUALITY)
        for zone, zd in result.items():
            assert "UNMAPPED" not in zd["distribution"]


class TestTagFamilies:
    def test_heading_family_present(self):
        result = bsm.build_tag_families(_QUALITY)
        assert "heading" in result
        assert "H1" in result["heading"]["members_by_count"]
        assert "H2" in result["heading"]["members_by_count"]

    def test_bullet_list_family(self):
        result = bsm.build_tag_families(_QUALITY)
        assert "bullet_list" in result
        fam = result["bullet_list"]
        assert "BL-FIRST" in fam["members_by_count"]
        assert "BL-MID" in fam["members_by_count"]
        assert "BL-LAST" in fam["members_by_count"]

    def test_numbered_list_family(self):
        result = bsm.build_tag_families(_QUALITY)
        assert "numbered_list" in result

    def test_marker_family(self):
        result = bsm.build_tag_families(_QUALITY)
        assert "marker" in result
        assert "PMI" in result["marker"]["members_by_count"]

    def test_clean_vs_publisher_split_tracked(self):
        result = bsm.build_tag_families(_QUALITY)
        # body_text family has both TXT (clean) and publisher styles (Normal etc.)
        body = result.get("body_text", {})
        assert "clean_canonical_count" in body
        assert "publisher_style_count" in body

    def test_total_count_correct(self):
        result = bsm.build_tag_families(_QUALITY)
        total_across_families = sum(fd["total_count"] for fd in result.values())
        assert total_across_families == len(_QUALITY)


class TestPositionalSuffixSemantics:
    def test_bl_sequence(self):
        result = bsm.build_positional_suffix_semantics(_QUALITY)
        assert "BL" in result
        bl = result["BL"]
        assert bl["suffix_distribution"]["FIRST"]["count"] >= 1
        assert bl["suffix_distribution"]["MID"]["count"] >= 1
        assert bl["suffix_distribution"]["LAST"]["count"] >= 1
        assert bl["typical_sequence"] == "FIRST -> MID -> LAST"

    def test_nl_sequence(self):
        result = bsm.build_positional_suffix_semantics(_QUALITY)
        assert "NL" in result
        nl = result["NL"]
        assert "FIRST" in nl["suffix_distribution"]
        assert "MID" in nl["suffix_distribution"]
        assert "LAST" in nl["suffix_distribution"]

    def test_publisher_styles_excluded(self):
        # Publisher styles like Head2, BulletList1 have no positional suffix
        # and should NOT appear as keys since they are not clean canonical
        result = bsm.build_positional_suffix_semantics(_QUALITY)
        assert "Head2" not in result
        assert "BulletList1" not in result

    def test_mid_dominance_is_float(self):
        result = bsm.build_positional_suffix_semantics(_QUALITY)
        for base, bd in result.items():
            assert isinstance(bd["mid_dominance"], float)

    def test_tag_without_positional_not_included(self):
        result = bsm.build_positional_suffix_semantics(_QUALITY)
        # H1, TXT, PMI never have positional suffixes → not in result
        assert "H1" not in result
        assert "TXT" not in result
        assert "PMI" not in result


class TestListDepthSemantics:
    def test_depth_keys_present(self):
        result = bsm.build_list_depth_semantics(_QUALITY)
        depths = result["by_depth"]
        assert "BL_depth_1" in depths
        assert "BL_depth_2" in depths
        assert "NL_depth_1" in depths

    def test_bl_depth_1_contains_expected_tags(self):
        result = bsm.build_list_depth_semantics(_QUALITY)
        depth1 = result["by_depth"]["BL_depth_1"]["tags"]
        assert "BL-FIRST" in depth1
        assert "BL-MID" in depth1
        assert "BL-LAST" in depth1

    def test_bl_depth_2_contains_expected_tags(self):
        result = bsm.build_list_depth_semantics(_QUALITY)
        depth2 = result["by_depth"]["BL_depth_2"]["tags"]
        assert "BL2-FIRST" in depth2
        assert "BL2-MID" in depth2

    def test_family_prefixed_variants_present(self):
        result = bsm.build_list_depth_semantics(_QUALITY)
        fp = result["family_prefixed_variants"]
        assert "KT:BL" in fp
        assert "KT-BL-MID" in fp["KT:BL"]["tags"]

    def test_totals_consistent(self):
        result = bsm.build_list_depth_semantics(_QUALITY)
        for key, kd in result["by_depth"].items():
            assert kd["total"] == sum(kd["tags"].values())


class TestMarkerPMISemantics:
    def test_pmi_total_counted(self):
        result = bsm.build_marker_pmi_semantics(_QUALITY)
        assert result["total_pmi"] == 1  # one PMI in _QUALITY

    def test_pmi_zone_distribution(self):
        result = bsm.build_marker_pmi_semantics(_QUALITY)
        assert "BODY" in result["zone_distribution"]
        assert result["zone_distribution"]["BODY"] == 1

    def test_preceding_tags_non_empty(self):
        result = bsm.build_marker_pmi_semantics(_QUALITY)
        # PMI at index 6 in doc1; preceding within window=2 are BL-LAST (5), BL-MID (4)
        preceding = result["top_preceding_tags"]
        assert len(preceding) > 0
        assert "BL-LAST" in preceding or "BL-MID" in preceding

    def test_following_tags_non_empty(self):
        result = bsm.build_marker_pmi_semantics(_QUALITY)
        following = result["top_following_tags"]
        assert len(following) > 0
        # PMI at index 6; following within window=2 are T1 (7), TFN (8)
        assert "T1" in following or "TFN" in following

    def test_no_pmi_example(self):
        examples_no_pmi = [e for e in _QUALITY if e["canonical_gold_tag"] != "PMI"]
        result = bsm.build_marker_pmi_semantics(examples_no_pmi)
        assert result["total_pmi"] == 0
        assert result["zone_distribution"] == {}


class TestTableSemantics:
    def test_table_tags_detected(self):
        result = bsm.build_table_semantics(_QUALITY)
        dist = result["global_distribution"]
        assert "T1" in dist
        assert "TFN" in dist

    def test_total_table_tagged(self):
        result = bsm.build_table_semantics(_QUALITY)
        assert result["total_table_tagged"] == 2  # T1 and TFN

    def test_by_zone_present(self):
        result = bsm.build_table_semantics(_QUALITY)
        assert "BODY" in result["by_zone"]

    def test_non_table_tags_excluded(self):
        result = bsm.build_table_semantics(_QUALITY)
        dist = result["global_distribution"]
        assert "TXT" not in dist
        assert "H1" not in dist
        assert "BL-MID" not in dist


class TestReferenceSemantics:
    def test_ref_tags_detected(self):
        result = bsm.build_reference_semantics(_QUALITY)
        dist = result["global_distribution"]
        assert "REF-N" in dist
        assert "REF-U" in dist

    def test_total_reference_tagged(self):
        result = bsm.build_reference_semantics(_QUALITY)
        # 2x REF-N + 1x REF-U = 3
        assert result["total_reference_tagged"] == 3

    def test_reference_zone_distribution(self):
        result = bsm.build_reference_semantics(_QUALITY)
        assert "REFERENCE" in result["by_zone"]

    def test_non_ref_excluded(self):
        result = bsm.build_reference_semantics(_QUALITY)
        dist = result["global_distribution"]
        assert "TXT" not in dist
        assert "H1" not in dist


class TestTransitionPriors:
    def test_global_transitions_have_expected_keys(self):
        result = bsm.build_transition_priors(_QUALITY)
        gt = result["global_transitions"]
        # H1 appears in doc1 (followed by TXT) and doc2 (followed by H2)
        assert "H1" in gt
        # BL-FIRST followed by BL-MID
        assert "BL-FIRST" in gt

    def test_bl_first_follows_bl_mid(self):
        result = bsm.build_transition_priors(_QUALITY)
        gt = result["global_transitions"]
        assert "BL-FIRST" in gt
        bl_first_trans = gt["BL-FIRST"]["next_tag_distribution"]
        assert "BL-MID" in bl_first_trans
        assert bl_first_trans["BL-MID"]["probability"] == pytest.approx(1.0)

    def test_probabilities_sum_to_one_per_tag(self):
        result = bsm.build_transition_priors(_QUALITY)
        for tag, td in result["global_transitions"].items():
            total_p = sum(d["probability"] for d in td["next_tag_distribution"].values())
            assert abs(total_p - 1.0) < 0.01, (
                f"Transitions from {tag!r}: probabilities sum to {total_p:.4f}"
            )

    def test_zone_conditioned_transitions_present(self):
        result = bsm.build_transition_priors(_QUALITY)
        assert "zone_conditioned_transitions" in result
        assert "BODY" in result["zone_conditioned_transitions"]

    def test_total_transitions_correct(self):
        result = bsm.build_transition_priors(_QUALITY)
        gt = result["global_transitions"]
        # Total outgoing transitions = len(_QUALITY) minus 1 per doc
        # doc1 has 12 quality paragraphs (excluding UNMAPPED) → 11 transitions
        # doc2 has 10 quality paragraphs → 9 transitions = 20 total
        total = sum(td["total_transitions"] for td in gt.values())
        # We have 22 quality examples across 2 docs → 22 - 2 = 20 transitions
        expected = len(_QUALITY) - 2  # 2 docs
        assert total == expected


class TestAliasCandidates:
    def test_publisher_styles_flagged(self):
        allowed = {"TXT", "H1", "BL-FIRST", "BL-MID", "BL-LAST", "PMI",
                   "T1", "TFN", "REF-N", "REF-U", "H2", "NL-FIRST",
                   "NL-MID", "NL-LAST", "TXT-FLUSH", "BL2-FIRST", "BL2-MID",
                   "KT-BL-MID", "EOC-H1"}
        aliases: dict = {}
        # Use all non-UNMAPPED examples
        examples = [ex for ex in _SYNTHETIC_CORPUS
                    if ex["canonical_gold_tag"] not in ("", "UNMAPPED")]
        candidates = bsm.find_alias_candidates(examples, allowed, aliases)
        raw_styles = {c["raw_style"] for c in candidates}
        assert "Head2" in raw_styles
        assert "BulletList1" in raw_styles

    def test_clean_tags_not_flagged(self):
        allowed = {"TXT", "H1", "BL-FIRST", "BL-MID", "BL-LAST", "PMI",
                   "T1", "TFN", "REF-N", "REF-U", "H2", "NL-FIRST",
                   "NL-MID", "NL-LAST", "TXT-FLUSH", "BL2-FIRST", "BL2-MID",
                   "KT-BL-MID", "EOC-H1"}
        aliases: dict = {}
        examples = [ex for ex in _SYNTHETIC_CORPUS
                    if ex["canonical_gold_tag"] not in ("", "UNMAPPED")]
        candidates = bsm.find_alias_candidates(examples, allowed, aliases)
        raw_styles = {c["raw_style"] for c in candidates}
        assert "H1" not in raw_styles
        assert "BL-MID" not in raw_styles
        assert "TXT" not in raw_styles

    def test_already_in_aliases_excluded(self):
        allowed: set = set()
        aliases = {"Head2": "H2"}
        examples = [ex for ex in _SYNTHETIC_CORPUS
                    if ex["canonical_gold_tag"] not in ("", "UNMAPPED")]
        candidates = bsm.find_alias_candidates(examples, allowed, aliases)
        raw_styles = {c["raw_style"] for c in candidates}
        assert "Head2" not in raw_styles

    def test_support_counts_correct(self):
        allowed: set = set()
        aliases: dict = {}
        examples = [ex for ex in _SYNTHETIC_CORPUS
                    if ex["canonical_gold_tag"] not in ("", "UNMAPPED")]
        candidates = bsm.find_alias_candidates(examples, allowed, aliases)
        head2_cand = next((c for c in candidates if c["raw_style"] == "Head2"), None)
        assert head2_cand is not None
        assert head2_cand["support"] == 1  # appears once in synthetic corpus

    def test_recommendation_field_present(self):
        allowed: set = set()
        aliases: dict = {}
        examples = [ex for ex in _SYNTHETIC_CORPUS
                    if ex["canonical_gold_tag"] not in ("", "UNMAPPED")]
        candidates = bsm.find_alias_candidates(examples, allowed, aliases)
        for c in candidates:
            assert c["recommendation"] in ("add_alias", "review_needed")

    def test_sorted_by_support_descending(self):
        allowed: set = set()
        aliases: dict = {}
        # Create examples where one publisher style appears much more often
        examples = (
            [_ex("d", i, "Normal") for i in range(20)]
            + [_ex("d", 100 + i, "BulletList1") for i in range(5)]
        )
        candidates = bsm.find_alias_candidates(examples, allowed, aliases)
        supports = [c["support"] for c in candidates]
        assert supports == sorted(supports, reverse=True)


# ===========================================================================
# Artifact schema validation
# ===========================================================================

class TestArtifactSchema:
    """All generated artifacts must contain required top-level schema fields."""

    def test_knowledge_artifact_required_fields(self):
        knowledge = {
            "schema_version": bsm.SCHEMA_VERSION,
            "tool_version": bsm.TOOL_VERSION,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source": "test.jsonl",
            "total_examples_raw": 10,
            "total_examples_quality": 8,
            "min_alignment_threshold": 0.75,
            "zone_tag_priors": bsm.build_zone_tag_priors(_QUALITY),
            "tag_families": bsm.build_tag_families(_QUALITY),
            "positional_suffix_semantics": bsm.build_positional_suffix_semantics(_QUALITY),
            "list_depth_semantics": bsm.build_list_depth_semantics(_QUALITY),
            "marker_pmi_semantics": bsm.build_marker_pmi_semantics(_QUALITY),
            "table_semantics": bsm.build_table_semantics(_QUALITY),
            "reference_semantics": bsm.build_reference_semantics(_QUALITY),
        }
        required = [
            "schema_version", "tool_version", "generated_at", "source",
            "total_examples_raw", "total_examples_quality",
            "zone_tag_priors", "tag_families", "positional_suffix_semantics",
            "list_depth_semantics", "marker_pmi_semantics",
            "table_semantics", "reference_semantics",
        ]
        for field in required:
            assert field in knowledge, f"Missing field: {field!r}"
        assert knowledge["schema_version"] == "1.0"

    def test_transitions_artifact_required_fields(self):
        trans = bsm.build_transition_priors(_QUALITY)
        artifact = {
            "schema_version": bsm.SCHEMA_VERSION,
            "tool_version": bsm.TOOL_VERSION,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source": "test.jsonl",
            "total_examples_quality": len(_QUALITY),
            **trans,
        }
        for field in ["schema_version", "global_transitions", "zone_conditioned_transitions"]:
            assert field in artifact, f"Missing field: {field!r}"
        assert artifact["schema_version"] == "1.0"

    def test_alias_artifact_required_fields(self):
        candidates = bsm.find_alias_candidates(
            [ex for ex in _SYNTHETIC_CORPUS
             if ex["canonical_gold_tag"] not in ("", "UNMAPPED")],
            set(), {}
        )
        artifact = {
            "schema_version": bsm.SCHEMA_VERSION,
            "tool_version": bsm.TOOL_VERSION,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source": "test.jsonl",
            "total_non_unmapped": 22,
            "total_candidates": len(candidates),
            "note": "Report only",
            "candidates": candidates,
        }
        for field in ["schema_version", "total_candidates", "candidates", "note"]:
            assert field in artifact, f"Missing field: {field!r}"
        assert artifact["note"] != ""  # must have a non-empty note

    def test_schema_version_is_string(self):
        assert isinstance(bsm.SCHEMA_VERSION, str)
        assert bsm.SCHEMA_VERSION  # non-empty


# ===========================================================================
# Regression: no raw paragraph text in runtime-facing artifact fields
# ===========================================================================

class TestNoRawTextInArtifacts:
    """
    Regression guard: the semantic knowledge artifacts must store only
    aggregated statistics (counts, frequencies, tag names).  Raw paragraph
    text from the training corpus must NEVER appear in any field that is
    destined for runtime inference use (zone_priors, tag_families,
    positional, list_depth, pmi, table, ref, transitions).
    """

    SENTINEL = "UNIQUE_SENTINEL_TRAINING_TEXT_SHOULD_NOT_APPEAR_9x7z"

    def _make_sentinel_examples(self) -> list[dict]:
        return [
            _ex("s_doc", 0, "TXT",       text=self.SENTINEL),
            _ex("s_doc", 1, "BL-FIRST",  text=f"prefix_{self.SENTINEL}_suffix"),
            _ex("s_doc", 2, "BL-MID",    text=self.SENTINEL + "_2"),
            _ex("s_doc", 3, "BL-LAST",   text=self.SENTINEL + "_3"),
            _ex("s_doc", 4, "PMI",       text=f"<{self.SENTINEL}>"),
            _ex("s_doc", 5, "REF-N",     zone="REFERENCE", text=self.SENTINEL),
        ]

    def test_sentinel_not_in_zone_priors(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_zone_tag_priors(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_tag_families(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_tag_families(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_positional_suffix_semantics(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_positional_suffix_semantics(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_list_depth_semantics(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_list_depth_semantics(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_pmi_semantics(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_marker_pmi_semantics(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_table_semantics(self):
        examples = self._make_sentinel_examples() + [
            _ex("s_doc", 6, "T1", text=self.SENTINEL)
        ]
        result = bsm.build_table_semantics(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_reference_semantics(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_reference_semantics(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_transitions(self):
        examples = self._make_sentinel_examples()
        result = bsm.build_transition_priors(examples)
        serialised = json.dumps(result)
        assert self.SENTINEL not in serialised

    def test_sentinel_not_in_combined_knowledge_artifact(self):
        """Full combined check across all knowledge artifact sections."""
        examples = self._make_sentinel_examples()
        combined = {
            "zone_tag_priors":           bsm.build_zone_tag_priors(examples),
            "tag_families":              bsm.build_tag_families(examples),
            "positional_suffix":         bsm.build_positional_suffix_semantics(examples),
            "list_depth":                bsm.build_list_depth_semantics(examples),
            "marker_pmi":                bsm.build_marker_pmi_semantics(examples),
            "table_semantics":           bsm.build_table_semantics(examples),
            "reference_semantics":       bsm.build_reference_semantics(examples),
            "transitions":               bsm.build_transition_priors(examples),
        }
        full_json = json.dumps(combined)
        assert self.SENTINEL not in full_json, (
            "Sentinel training text was found in a knowledge artifact field. "
            "Artifacts must store only aggregated statistics, not raw text."
        )


# ===========================================================================
# Integration test: main() generates all 4 artifacts from synthetic JSONL
# ===========================================================================

class TestMainIntegration:
    """End-to-end: main() completes successfully and all output files are valid."""

    def _write_synthetic_jsonl(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for ex in _SYNTHETIC_CORPUS:
                f.write(json.dumps(ex) + "\n")

    def test_main_returns_zero_and_creates_artifacts(self, tmp_path, monkeypatch):
        jsonl_path = tmp_path / "ground_truth.jsonl"
        self._write_synthetic_jsonl(jsonl_path)

        allowed_path = tmp_path / "allowed_styles.json"
        allowed_path.write_text(
            json.dumps(["TXT", "H1", "H2", "BL-FIRST", "BL-MID", "BL-LAST",
                        "PMI", "T1", "TFN", "REF-N", "REF-U", "NL-FIRST",
                        "NL-MID", "NL-LAST", "TXT-FLUSH", "BL2-FIRST", "BL2-MID",
                        "KT-BL-MID", "EOC-H1"]),
            encoding="utf-8"
        )
        aliases_path = tmp_path / "style_aliases.json"
        aliases_path.write_text(json.dumps({"Head1": "H1"}), encoding="utf-8")

        out_knowledge    = tmp_path / "knowledge.json"
        out_transitions  = tmp_path / "transitions.json"
        out_aliases      = tmp_path / "alias_cands.json"
        out_report       = tmp_path / "report.md"

        monkeypatch.setattr(sys, "argv", [
            "build_semantic_knowledge.py",
            "--ground-truth",         str(jsonl_path),
            "--allowed-styles",       str(allowed_path),
            "--style-aliases",        str(aliases_path),
            "--out-knowledge",        str(out_knowledge),
            "--out-transitions",      str(out_transitions),
            "--out-alias-candidates", str(out_aliases),
            "--out-report",           str(out_report),
        ])

        result = bsm.main()
        assert result == 0

        for path in (out_knowledge, out_transitions, out_aliases, out_report):
            assert path.exists(), f"Expected output not created: {path.name}"
            assert path.stat().st_size > 0, f"Output file is empty: {path.name}"

    def test_knowledge_json_valid_schema(self, tmp_path, monkeypatch):
        jsonl_path = tmp_path / "ground_truth.jsonl"
        self._write_synthetic_jsonl(jsonl_path)
        allowed_path = tmp_path / "allowed_styles.json"
        allowed_path.write_text(json.dumps([]), encoding="utf-8")
        aliases_path = tmp_path / "style_aliases.json"
        aliases_path.write_text(json.dumps({}), encoding="utf-8")
        out_knowledge = tmp_path / "knowledge.json"

        monkeypatch.setattr(sys, "argv", [
            "build_semantic_knowledge.py",
            "--ground-truth",         str(jsonl_path),
            "--allowed-styles",       str(allowed_path),
            "--style-aliases",        str(aliases_path),
            "--out-knowledge",        str(out_knowledge),
            "--out-transitions",      str(tmp_path / "t.json"),
            "--out-alias-candidates", str(tmp_path / "a.json"),
            "--out-report",           str(tmp_path / "r.md"),
        ])

        bsm.main()
        knowledge = json.loads(out_knowledge.read_text(encoding="utf-8"))

        assert knowledge["schema_version"] == bsm.SCHEMA_VERSION
        assert knowledge["tool_version"] == bsm.TOOL_VERSION
        assert "generated_at" in knowledge
        assert "zone_tag_priors" in knowledge
        assert "tag_families" in knowledge
        assert "positional_suffix_semantics" in knowledge
        assert "list_depth_semantics" in knowledge
        assert "marker_pmi_semantics" in knowledge
        assert "table_semantics" in knowledge
        assert "reference_semantics" in knowledge

    def test_alias_json_has_report_note(self, tmp_path, monkeypatch):
        jsonl_path = tmp_path / "ground_truth.jsonl"
        self._write_synthetic_jsonl(jsonl_path)
        allowed_path = tmp_path / "allowed_styles.json"
        allowed_path.write_text(json.dumps([]), encoding="utf-8")
        aliases_path = tmp_path / "style_aliases.json"
        aliases_path.write_text(json.dumps({}), encoding="utf-8")
        out_aliases = tmp_path / "alias_cands.json"

        monkeypatch.setattr(sys, "argv", [
            "build_semantic_knowledge.py",
            "--ground-truth",         str(jsonl_path),
            "--allowed-styles",       str(allowed_path),
            "--style-aliases",        str(aliases_path),
            "--out-knowledge",        str(tmp_path / "k.json"),
            "--out-transitions",      str(tmp_path / "t.json"),
            "--out-alias-candidates", str(out_aliases),
            "--out-report",           str(tmp_path / "r.md"),
        ])

        bsm.main()
        alias_artifact = json.loads(out_aliases.read_text(encoding="utf-8"))

        # Must have a note field that explicitly mentions no auto-merge
        assert "note" in alias_artifact
        note = alias_artifact["note"].lower()
        assert "auto" in note or "manual" in note or "review" in note, (
            "Alias artifact note must mention manual review or no auto-merge"
        )

    def test_missing_ground_truth_returns_nonzero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "build_semantic_knowledge.py",
            "--ground-truth", str(tmp_path / "does_not_exist.jsonl"),
        ])
        result = bsm.main()
        assert result != 0


# ===========================================================================
# Alias candidate evidence fields — zone_distribution and full field coverage
# ===========================================================================

class TestAliasCandidateEvidenceFields:
    """Every alias candidate returned by find_alias_candidates must carry the
    complete set of evidence fields, including zone_distribution."""

    REQUIRED_FIELDS = {
        "raw_style",
        "suggested_canonical",
        "support",
        "confidence",
        "zone_distribution",
        "recommendation",
        "num_docs",
        "in_allowed_styles",
    }

    def _make_candidates(
        self, allowed: set | None = None, aliases: dict | None = None
    ) -> list[dict]:
        if allowed is None:
            allowed = {
                "TXT", "H1", "H2", "BL-FIRST", "BL-MID", "BL-LAST",
                "PMI", "T1", "TFN", "REF-N", "REF-U",
            }
        if aliases is None:
            aliases = {}
        examples = [
            ex for ex in _SYNTHETIC_CORPUS
            if ex["canonical_gold_tag"] not in ("", "UNMAPPED")
        ]
        return bsm.find_alias_candidates(examples, allowed, aliases)

    def test_all_candidates_have_required_fields(self):
        candidates = self._make_candidates()
        assert candidates, "Expected at least one alias candidate from synthetic corpus"
        for c in candidates:
            for field in self.REQUIRED_FIELDS:
                assert field in c, (
                    f"Candidate {c.get('raw_style')!r} is missing field {field!r}"
                )

    def test_zone_distribution_is_dict_of_str_to_int(self):
        candidates = self._make_candidates()
        for c in candidates:
            zd = c["zone_distribution"]
            assert isinstance(zd, dict), (
                f"zone_distribution for {c['raw_style']!r} must be a dict, got {type(zd)}"
            )
            for k, v in zd.items():
                assert isinstance(k, str), (
                    f"zone_distribution key {k!r} for {c['raw_style']!r} must be str"
                )
                assert isinstance(v, int), (
                    f"zone_distribution value {v!r} for {c['raw_style']!r} must be int"
                )

    def test_zone_distribution_sum_equals_support(self):
        """Sum of per-zone counts must equal the candidate's support count."""
        candidates = self._make_candidates()
        for c in candidates:
            zd = c["zone_distribution"]
            assert sum(zd.values()) == c["support"], (
                f"For {c['raw_style']!r}: sum(zone_distribution)={sum(zd.values())} "
                f"!= support={c['support']}"
            )

    def test_zone_distribution_keys_are_nonempty_strings(self):
        candidates = self._make_candidates()
        for c in candidates:
            for zone_key in c["zone_distribution"].keys():
                assert zone_key, (
                    f"zone_distribution for {c['raw_style']!r} has empty zone key"
                )

    def test_publisher_style_has_correct_zone_in_distribution(self):
        """Head2 appears in BODY-zone examples → zone_distribution must include BODY."""
        candidates = self._make_candidates(allowed=set(), aliases={})
        head2 = next((c for c in candidates if c["raw_style"] == "Head2"), None)
        assert head2 is not None, "Head2 should appear as alias candidate"
        assert "BODY" in head2["zone_distribution"], (
            "Head2 seen in BODY zone should have BODY in zone_distribution"
        )
        assert head2["zone_distribution"]["BODY"] >= 1

    def test_recommendation_values_are_valid(self):
        valid = {"add_alias", "review_needed"}
        candidates = self._make_candidates()
        for c in candidates:
            assert c["recommendation"] in valid, (
                f"Invalid recommendation {c['recommendation']!r} for {c['raw_style']!r}"
            )

    def test_support_is_positive_int(self):
        candidates = self._make_candidates()
        for c in candidates:
            assert isinstance(c["support"], int), (
                f"support for {c['raw_style']!r} must be int, got {type(c['support'])}"
            )
            assert c["support"] > 0, (
                f"support for {c['raw_style']!r} must be positive"
            )

    def test_confidence_is_float_in_unit_interval(self):
        candidates = self._make_candidates()
        for c in candidates:
            assert isinstance(c["confidence"], float), (
                f"confidence for {c['raw_style']!r} must be float"
            )
            assert 0.0 <= c["confidence"] <= 1.0, (
                f"confidence {c['confidence']:.4f} out of [0,1] for {c['raw_style']!r}"
            )

    def test_num_docs_at_least_one(self):
        candidates = self._make_candidates()
        for c in candidates:
            assert c["num_docs"] >= 1, (
                f"num_docs for {c['raw_style']!r} must be >= 1"
            )

    def test_in_allowed_styles_is_bool(self):
        candidates = self._make_candidates()
        for c in candidates:
            assert isinstance(c["in_allowed_styles"], bool), (
                f"in_allowed_styles for {c['raw_style']!r} must be bool"
            )

    def test_ref_style_in_reference_zone(self):
        """A publisher style seen only in REFERENCE zone must not have BODY in zone_dist."""
        # Add a fake reference-zone publisher style
        extra_examples = [
            _ex("z_doc", 0, "ReferencesHeading", zone="REFERENCE"),
            _ex("z_doc", 1, "ReferencesHeading", zone="REFERENCE"),
        ]
        all_examples = [
            ex for ex in _SYNTHETIC_CORPUS
            if ex["canonical_gold_tag"] not in ("", "UNMAPPED")
        ] + extra_examples
        candidates = bsm.find_alias_candidates(all_examples, set(), {})
        ref_cand = next(
            (c for c in candidates if c["raw_style"] == "ReferencesHeading"), None
        )
        assert ref_cand is not None, "ReferencesHeading should be a candidate"
        assert "REFERENCE" in ref_cand["zone_distribution"]
        assert ref_cand["zone_distribution"]["REFERENCE"] == 2
        assert "BODY" not in ref_cand["zone_distribution"]

    def test_empty_examples_yields_empty_candidates(self):
        candidates = bsm.find_alias_candidates([], set(), {})
        assert candidates == []

    def test_zone_distribution_not_in_artifacts_raw_text(self):
        """zone_distribution values must be zone names (strings), not raw paragraph text."""
        sentinel = "SENTINEL_RAW_TEXT_SHOULD_NOT_APPEAR_AS_ZONE"
        examples = [
            _ex("s", 0, "PublisherStyle1", text=sentinel, zone="BODY"),
            _ex("s", 1, "PublisherStyle1", text=sentinel + "_2", zone="BODY"),
        ]
        candidates = bsm.find_alias_candidates(examples, set(), {})
        assert candidates
        cand = candidates[0]
        zone_keys = list(cand["zone_distribution"].keys())
        assert sentinel not in zone_keys, (
            "Sentinel raw text appeared as a zone_distribution key"
        )
        serialised = json.dumps(cand["zone_distribution"])
        assert sentinel not in serialised


# ===========================================================================
# Deterministic ordering — byte-stable JSON across multiple calls
# ===========================================================================

class TestDeterministicOrdering:
    """Extraction functions must produce identical JSON when called twice on
    the same input.  Only `generated_at` (timestamp) is allowed to differ
    between runs of the full pipeline."""

    @staticmethod
    def _stable(obj) -> str:
        """Deterministic JSON string for comparison (sort_keys=True)."""
        return json.dumps(obj, sort_keys=True)

    @staticmethod
    def _strip_ts(obj):
        """Recursively remove generated_at to allow cross-run comparison."""
        if isinstance(obj, dict):
            return {
                k: TestDeterministicOrdering._strip_ts(v)
                for k, v in obj.items()
                if k != "generated_at"
            }
        if isinstance(obj, list):
            return [TestDeterministicOrdering._strip_ts(i) for i in obj]
        return obj

    def test_zone_tag_priors_stable(self):
        r1 = bsm.build_zone_tag_priors(_QUALITY)
        r2 = bsm.build_zone_tag_priors(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_tag_families_stable(self):
        r1 = bsm.build_tag_families(_QUALITY)
        r2 = bsm.build_tag_families(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_positional_suffix_semantics_stable(self):
        r1 = bsm.build_positional_suffix_semantics(_QUALITY)
        r2 = bsm.build_positional_suffix_semantics(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_list_depth_semantics_stable(self):
        r1 = bsm.build_list_depth_semantics(_QUALITY)
        r2 = bsm.build_list_depth_semantics(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_marker_pmi_semantics_stable(self):
        r1 = bsm.build_marker_pmi_semantics(_QUALITY)
        r2 = bsm.build_marker_pmi_semantics(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_table_semantics_stable(self):
        r1 = bsm.build_table_semantics(_QUALITY)
        r2 = bsm.build_table_semantics(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_reference_semantics_stable(self):
        r1 = bsm.build_reference_semantics(_QUALITY)
        r2 = bsm.build_reference_semantics(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_transition_priors_stable(self):
        r1 = bsm.build_transition_priors(_QUALITY)
        r2 = bsm.build_transition_priors(_QUALITY)
        assert self._stable(r1) == self._stable(r2)

    def test_find_alias_candidates_stable(self):
        examples = [
            ex for ex in _SYNTHETIC_CORPUS
            if ex["canonical_gold_tag"] not in ("", "UNMAPPED")
        ]
        r1 = bsm.find_alias_candidates(examples, set(), {})
        r2 = bsm.find_alias_candidates(examples, set(), {})
        assert self._stable(r1) == self._stable(r2)

    def test_full_pipeline_stable_except_timestamp(self, tmp_path, monkeypatch):
        """main() produces byte-stable artifact content across two separate runs
        (only generated_at is allowed to differ)."""
        jsonl_path = tmp_path / "gt.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ex in _SYNTHETIC_CORPUS:
                f.write(json.dumps(ex) + "\n")

        allowed_path = tmp_path / "allowed.json"
        allowed_path.write_text(
            json.dumps([
                "TXT", "H1", "H2", "BL-FIRST", "BL-MID", "BL-LAST",
                "PMI", "T1", "TFN", "REF-N", "REF-U",
            ]),
            encoding="utf-8",
        )
        aliases_path = tmp_path / "aliases.json"
        aliases_path.write_text(json.dumps({}), encoding="utf-8")

        def _run(prefix: str) -> dict:
            out_k = tmp_path / f"{prefix}_k.json"
            out_t = tmp_path / f"{prefix}_t.json"
            out_a = tmp_path / f"{prefix}_a.json"
            out_r = tmp_path / f"{prefix}_r.md"
            monkeypatch.setattr(sys, "argv", [
                "build_semantic_knowledge.py",
                "--ground-truth",         str(jsonl_path),
                "--allowed-styles",       str(allowed_path),
                "--style-aliases",        str(aliases_path),
                "--out-knowledge",        str(out_k),
                "--out-transitions",      str(out_t),
                "--out-alias-candidates", str(out_a),
                "--out-report",           str(out_r),
            ])
            bsm.main()
            return {
                "knowledge":    json.loads(out_k.read_text(encoding="utf-8")),
                "transitions":  json.loads(out_t.read_text(encoding="utf-8")),
                "aliases":      json.loads(out_a.read_text(encoding="utf-8")),
            }

        run1 = _run("r1")
        run2 = _run("r2")

        for artifact_name in ("knowledge", "transitions", "aliases"):
            stripped1 = self._strip_ts(run1[artifact_name])
            stripped2 = self._strip_ts(run2[artifact_name])
            assert self._stable(stripped1) == self._stable(stripped2), (
                f"Artifact '{artifact_name}' is not byte-stable across two runs "
                "(only generated_at should differ between runs)"
            )
