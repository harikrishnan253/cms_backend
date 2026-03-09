"""
Tests for tools/eval_generalization.py

Covers:
  - Zone normalization
  - Publisher extraction
  - Metric category helpers (_is_list_depth)
  - build_context (prev_tag chaining)
  - Predictor modes (baseline, alias, semantic, rules, retriever)
  - compute_metrics (all 7 metrics)
  - split_holdout_publisher
  - format_report (smoke test)
  - run_evaluation (integration with mocks)
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure backend is on sys.path
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tools.eval_generalization import (
    Predictors,
    _extract_publisher,
    _is_list_depth,
    _norm_zone,
    build_context,
    compute_metrics,
    format_report,
    run_evaluation,
    split_holdout_publisher,
)


# ===========================================================================
# TestZoneNormalization
# ===========================================================================
class TestZoneNormalization:
    def test_body_lowercase(self):
        assert _norm_zone("body") == "BODY"

    def test_reference_maps_to_back_matter(self):
        assert _norm_zone("reference") == "BACK_MATTER"

    def test_back_matter_explicit(self):
        assert _norm_zone("back_matter") == "BACK_MATTER"

    def test_table_lowercase(self):
        assert _norm_zone("table") == "TABLE"

    def test_unknown_defaults_to_body(self):
        assert _norm_zone("unknown_zone_xyz") == "BODY"

    def test_case_insensitive(self):
        assert _norm_zone("BODY") == "BODY"
        assert _norm_zone("Reference") == "BACK_MATTER"

    def test_box_variants(self):
        assert _norm_zone("nbx") == "BOX_NBX"
        assert _norm_zone("bx1") == "BOX_BX1"
        assert _norm_zone("bx2") == "BOX_BX2"

    def test_appendix_and_index_map_to_back_matter(self):
        assert _norm_zone("appendix") == "BACK_MATTER"
        assert _norm_zone("index") == "BACK_MATTER"

    def test_front_matter(self):
        assert _norm_zone("front_matter") == "FRONT_MATTER"


# ===========================================================================
# TestPublisherExtraction
# ===========================================================================
class TestPublisherExtraction:
    def test_standard_doc_id(self):
        assert _extract_publisher("Acharya9781975261764-ch002_tag") == "acharya"

    def test_all_alpha_doc_id(self):
        assert _extract_publisher("Smith2024xyz") == "smith"

    def test_starts_with_number_returns_unknown(self):
        assert _extract_publisher("9781234567890-ch01") == "unknown"

    def test_single_letter_prefix(self):
        assert _extract_publisher("A9781234567890-ch01") == "a"

    def test_lowercase_input(self):
        assert _extract_publisher("jones9780000000000-ch01") == "jones"

    def test_empty_string(self):
        assert _extract_publisher("") == "unknown"


# ===========================================================================
# TestMetricHelpers
# ===========================================================================
class TestMetricHelpers:
    def test_bl2_mid_is_list_depth(self):
        assert _is_list_depth("BL2-MID") is True

    def test_bl3_first_is_list_depth(self):
        assert _is_list_depth("BL3-FIRST") is True

    def test_nl2_last_is_list_depth(self):
        assert _is_list_depth("NL2-LAST") is True

    def test_nl3_mid_is_list_depth(self):
        assert _is_list_depth("NL3-MID") is True

    def test_bl_mid_not_list_depth(self):
        # BL-MID = depth 1, not depth 2/3
        assert _is_list_depth("BL-MID") is False

    def test_nl_first_not_list_depth(self):
        assert _is_list_depth("NL-FIRST") is False

    def test_txt_not_list_depth(self):
        assert _is_list_depth("TXT") is False

    def test_kt_bl2_mid_is_list_depth(self):
        assert _is_list_depth("KT-BL2-MID") is True


# ===========================================================================
# TestBuildContext
# ===========================================================================
class TestBuildContext:

    def _gt(self, docs: Dict[str, List[tuple]]) -> Dict[str, List[Dict]]:
        """Build a minimal ground_truth from (para_index, gold, canonical, zone) tuples."""
        gt: Dict[str, List[Dict]] = {}
        for doc_id, entries in docs.items():
            gt[doc_id] = [
                {
                    "doc_id": doc_id,
                    "para_index": i,
                    "gold_tag": gold,
                    "canonical_gold_tag": canonical,
                    "zone": zone,
                    "text": f"Text {i}",
                }
                for i, (gold, canonical, zone) in enumerate(entries)
            ]
        return gt

    def test_prev_tag_is_start_for_first_entry(self):
        gt = self._gt({"doc_a": [("TXT", "TXT", "body")]})
        ctx = build_context(gt)
        assert ctx[0]["prev_canonical_tag"] == "START"

    def test_prev_tag_chains_correctly(self):
        gt = self._gt({
            "doc_a": [
                ("H1", "H1", "body"),
                ("TXT", "TXT", "body"),
                ("TXT", "TXT", "body"),
            ]
        })
        ctx = build_context(gt)
        assert ctx[0]["prev_canonical_tag"] == "START"
        assert ctx[1]["prev_canonical_tag"] == "H1"
        assert ctx[2]["prev_canonical_tag"] == "TXT"

    def test_unmapped_does_not_advance_prev_tag(self):
        gt = self._gt({
            "doc_a": [
                ("H1", "H1", "body"),
                ("??", "UNMAPPED", "body"),
                ("TXT", "TXT", "body"),
            ]
        })
        ctx = build_context(gt)
        assert ctx[2]["prev_canonical_tag"] == "H1"  # UNMAPPED skipped

    def test_prev_tag_resets_at_doc_boundary(self):
        gt = self._gt({
            "doc_a": [("H1", "H1", "body")],
            "doc_b": [("TXT", "TXT", "body")],
        })
        ctx = build_context(gt)
        # Find doc_b's first entry
        doc_b_entry = next(e for e in ctx if e["doc_id"] == "doc_b")
        assert doc_b_entry["prev_canonical_tag"] == "START"

    def test_entries_sorted_by_para_index(self):
        gt = {
            "doc_a": [
                {"doc_id": "doc_a", "para_index": 2, "gold_tag": "H2", "canonical_gold_tag": "H2", "zone": "body", "text": "C"},
                {"doc_id": "doc_a", "para_index": 0, "gold_tag": "H1", "canonical_gold_tag": "H1", "zone": "body", "text": "A"},
                {"doc_id": "doc_a", "para_index": 1, "gold_tag": "TXT", "canonical_gold_tag": "TXT", "zone": "body", "text": "B"},
            ]
        }
        ctx = build_context(gt)
        assert [e["para_index"] for e in ctx] == [0, 1, 2]


# ===========================================================================
# TestPredictors
# ===========================================================================
def _make_predictors(
    alias_map=None,
    artifacts=None,
    allowed=None,
    learner=None,
    retriever=None,
    normalize_fn=None,
):
    if allowed is None:
        allowed = {"TXT", "TXT-FLUSH", "H1", "H2", "REF-N", "REF-U", "BL-MID", "BL-FIRST", "T"}
    if normalize_fn is None:
        def normalize_fn(tag, meta=None):
            return tag if tag in allowed else "TXT"
    return Predictors(
        normalize_tag_fn=normalize_fn,
        alias_map=alias_map or {},
        artifacts=artifacts or {},
        allowed_styles=allowed,
        learner=learner,
        retriever=retriever,
    )


class TestPredictorBaseline:
    def test_known_tag_returned_unchanged(self):
        p = _make_predictors()
        entry = {"gold_tag": "H1", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_baseline(entry) == "H1"

    def test_unknown_tag_falls_back_to_txt(self):
        p = _make_predictors()
        entry = {"gold_tag": "UNKNOWN_PUBLISHER_STYLE", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_baseline(entry) == "TXT"

    def test_missing_gold_tag_defaults_to_txt(self):
        p = _make_predictors()
        entry = {"zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_baseline(entry) == "TXT"


class TestPredictorAlias:
    def test_alias_takes_precedence_over_normalize(self):
        p = _make_predictors(alias_map={"Normal": "TXT-FLUSH"})
        entry = {"gold_tag": "Normal", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_alias(entry) == "TXT-FLUSH"

    def test_no_alias_falls_back_to_normalize(self):
        p = _make_predictors(alias_map={})
        entry = {"gold_tag": "H1", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_alias(entry) == "H1"

    def test_alias_not_in_map_uses_normalize(self):
        p = _make_predictors(alias_map={"Other": "REF-N"})
        entry = {"gold_tag": "H2", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_alias(entry) == "H2"


class TestPredictorSemantic:
    def test_passes_through_when_alias_succeeds(self):
        p = _make_predictors(alias_map={"Normal": "H1"})
        entry = {"gold_tag": "Normal", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_semantic(entry) == "H1"

    def test_zone_prior_used_when_alias_fails(self):
        artifacts = {
            "zone_tag_priors": {
                "REFERENCE": {
                    "distribution": {
                        "REF-N": {"frequency": 0.55, "count": 1000},
                    }
                }
            }
        }
        allowed = {"TXT", "TXT-FLUSH", "REF-N"}
        p = _make_predictors(artifacts=artifacts, allowed=allowed)
        entry = {
            "gold_tag": "UNKNOWN",
            "zone": "reference",  # maps to BACK_MATTER → artifact zone REFERENCE
            "text": "A",
            "prev_canonical_tag": "START",
        }
        result = p.predict_semantic(entry)
        assert result == "REF-N"

    def test_zone_prior_not_used_when_below_threshold(self):
        artifacts = {
            "zone_tag_priors": {
                "REFERENCE": {
                    "distribution": {
                        "REF-N": {"frequency": 0.20, "count": 100},  # below 0.40
                    }
                }
            }
        }
        allowed = {"TXT", "TXT-FLUSH", "REF-N"}
        p = _make_predictors(artifacts=artifacts, allowed=allowed)
        entry = {"gold_tag": "UNKNOWN", "zone": "reference", "text": "A", "prev_canonical_tag": "START"}
        result = p.predict_semantic(entry)
        assert result == "TXT"  # zone prior not applied

    def test_transition_prior_used_when_zone_prior_absent(self):
        artifacts = {
            "global_transitions": {
                "H1": {
                    "next_tag_distribution": {
                        "TXT": {"probability": 0.85},
                    }
                }
            }
        }
        allowed = {"TXT", "TXT-FLUSH"}
        p = _make_predictors(artifacts=artifacts, allowed=allowed)
        entry = {"gold_tag": "UNKNOWN", "zone": "body", "text": "A", "prev_canonical_tag": "H1"}
        result = p.predict_semantic(entry)
        assert result == "TXT"

    def test_transition_prior_not_used_when_below_threshold(self):
        artifacts = {
            "global_transitions": {
                "H1": {
                    "next_tag_distribution": {
                        "TXT": {"probability": 0.60},  # below 0.75
                    }
                }
            }
        }
        allowed = {"TXT", "TXT-FLUSH"}
        p = _make_predictors(artifacts=artifacts, allowed=allowed)
        entry = {"gold_tag": "UNKNOWN", "zone": "body", "text": "A", "prev_canonical_tag": "H1"}
        # No zone prior and transition below threshold → stays TXT from normalize
        result = p.predict_semantic(entry)
        assert result == "TXT"


class TestPredictorRules:
    def test_apply_rules_used_first(self):
        mock_learner = MagicMock()
        mock_learner.rules = [{"condition": "is_short", "predicted_tag": "H1", "support": 10, "total": 10, "confidence": 1.0}]
        mock_learner.apply_rules.return_value = "H2"
        p = _make_predictors(learner=mock_learner)
        entry = {"gold_tag": "UNKNOWN", "zone": "body", "text": "Short text.", "prev_canonical_tag": "START"}
        assert p.predict_rules(entry) == "H2"
        mock_learner.apply_rules.assert_called_once()

    def test_falls_back_to_semantic_when_rules_return_none(self):
        mock_learner = MagicMock()
        mock_learner.rules = [{"condition": "dummy", "predicted_tag": "H1", "support": 1, "total": 1, "confidence": 1.0}]
        mock_learner.apply_rules.return_value = None  # no match
        p = _make_predictors(learner=mock_learner, alias_map={"MyStyle": "H1"})
        entry = {"gold_tag": "MyStyle", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_rules(entry) == "H1"  # falls through to alias

    def test_no_learner_falls_through_to_semantic(self):
        p = _make_predictors(learner=None, alias_map={"Special": "REF-N"})
        entry = {"gold_tag": "Special", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_rules(entry) == "REF-N"

    def test_empty_rules_list_falls_through(self):
        mock_learner = MagicMock()
        mock_learner.rules = []  # empty — should not call apply_rules
        p = _make_predictors(learner=mock_learner, alias_map={"Style": "H2"})
        entry = {"gold_tag": "Style", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_rules(entry) == "H2"
        mock_learner.apply_rules.assert_not_called()


class TestPredictorRetriever:
    def test_retriever_called_when_rules_give_txt(self):
        mock_retriever = MagicMock()
        mock_retriever.retrieve_examples.return_value = [
            {"canonical_gold_tag": "REF-N"}
        ]
        mock_learner = MagicMock()
        mock_learner.rules = []
        p = _make_predictors(learner=mock_learner, retriever=mock_retriever)
        entry = {"gold_tag": "UNKNOWN", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        result = p.predict_retriever(entry)
        assert result == "REF-N"
        mock_retriever.retrieve_examples.assert_called_once()

    def test_retriever_skipped_when_rules_give_good_prediction(self):
        mock_retriever = MagicMock()
        mock_learner = MagicMock()
        mock_learner.rules = [{"condition": "x", "predicted_tag": "H1", "support": 1, "total": 1, "confidence": 1.0}]
        mock_learner.apply_rules.return_value = "H1"
        p = _make_predictors(learner=mock_learner, retriever=mock_retriever)
        entry = {"gold_tag": "UNKNOWN", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_retriever(entry) == "H1"
        mock_retriever.retrieve_examples.assert_not_called()

    def test_no_retriever_falls_through_to_rules_chain(self):
        mock_learner = MagicMock()
        mock_learner.rules = []
        p = _make_predictors(learner=mock_learner, retriever=None, alias_map={"S": "H2"})
        entry = {"gold_tag": "S", "zone": "body", "text": "A", "prev_canonical_tag": "START"}
        assert p.predict_retriever(entry) == "H2"


# ===========================================================================
# TestComputeMetrics
# ===========================================================================

def _make_entry(gold: str, zone: str = "body", gold_tag: str = None) -> dict:
    return {
        "canonical_gold_tag": gold,
        "zone": zone,
        "gold_tag": gold_tag or gold,
        "text": "Some text.",
        "prev_canonical_tag": "START",
    }


def _no_zone_valid(zone):
    # Minimal zone validity: allow all (BODY behaviour)
    return {"TXT", "TXT-FLUSH", "H1", "H2", "REF-N", "REF-U", "T", "BL2-MID", "NL2-MID"}


class TestComputeMetrics:
    def _metrics(self, predictions, entries, allowed=None):
        if allowed is None:
            allowed = {"TXT", "TXT-FLUSH", "H1", "H2", "REF-N", "REF-U", "T", "BL2-MID", "NL2-MID", "BL-MID"}
        with patch("tools.eval_generalization.compute_metrics.__globals__", {}):
            pass
        # Patch get_allowed_styles_for_zone to avoid zone_styles dependency
        import tools.eval_generalization as eg_mod
        with patch.object(eg_mod, "compute_metrics", wraps=eg_mod.compute_metrics):
            try:
                from processor.zone_styles import get_allowed_styles_for_zone
            except ImportError:
                get_allowed_styles_for_zone = None
        return eg_mod.compute_metrics(predictions, entries, allowed)

    def test_perfect_predictions_give_100_accuracy(self):
        entries = [_make_entry("H1"), _make_entry("TXT")]
        preds = ["H1", "TXT"]
        m = compute_metrics(preds, entries, {"H1", "TXT", "TXT-FLUSH"})
        assert m["accuracy"] == pytest.approx(1.0)

    def test_all_wrong_gives_zero_accuracy(self):
        entries = [_make_entry("H1"), _make_entry("H2")]
        preds = ["TXT", "TXT"]
        m = compute_metrics(preds, entries, {"H1", "H2", "TXT"})
        assert m["accuracy"] == pytest.approx(0.0)

    def test_unmapped_entries_excluded_from_accuracy(self):
        entries = [
            _make_entry("UNMAPPED"),
            _make_entry("H1"),
        ]
        preds = ["TXT", "H1"]
        m = compute_metrics(preds, entries, {"H1", "TXT"})
        assert m["_n_total"] == 1
        assert m["accuracy"] == pytest.approx(1.0)
        assert m["unmapped_rate"] == pytest.approx(0.5)

    def test_txt_fallback_rate(self):
        entries = [_make_entry("H1"), _make_entry("H2"), _make_entry("TXT")]
        preds = ["TXT", "TXT", "TXT"]
        m = compute_metrics(preds, entries, {"H1", "H2", "TXT"})
        assert m["txt_fallback_rate"] == pytest.approx(1.0)

    def test_list_depth_accuracy(self):
        entries = [
            _make_entry("BL2-MID"),
            _make_entry("NL2-MID"),
            _make_entry("TXT"),
        ]
        preds = ["BL2-MID", "TXT", "TXT"]  # 1/2 correct on list-depth
        m = compute_metrics(preds, entries, {"BL2-MID", "NL2-MID", "TXT"})
        assert m["_n_list_depth"] == 2
        assert m["list_depth_accuracy"] == pytest.approx(0.5)

    def test_ref_accuracy_computed_for_back_matter_zone(self):
        entries = [
            _make_entry("REF-N", zone="reference"),
            _make_entry("REF-N", zone="reference"),
        ]
        preds = ["REF-N", "TXT"]  # 1/2 correct
        allowed = {"REF-N", "TXT"}
        m = compute_metrics(preds, entries, allowed)
        assert m["_n_ref"] == 2
        assert m["ref_accuracy"] == pytest.approx(0.5)

    def test_table_accuracy_computed_for_table_zone(self):
        entries = [
            _make_entry("T", zone="table"),
            _make_entry("T", zone="table"),
        ]
        preds = ["T", "TXT"]
        m = compute_metrics(preds, entries, {"T", "TXT"})
        assert m["_n_table"] == 2
        assert m["table_sem_accuracy"] == pytest.approx(0.5)

    def test_empty_entries_gives_zero_metrics(self):
        m = compute_metrics([], [], set())
        assert m["accuracy"] == pytest.approx(0.0)
        assert m["_n_total"] == 0
        assert m["list_depth_accuracy"] is None
        assert m["table_sem_accuracy"] is None
        assert m["ref_accuracy"] is None

    def test_all_body_zone_gives_zero_zone_violations(self):
        """BODY zone is unrestricted — zone_checkable should be 0."""
        entries = [_make_entry("TXT", zone="body"), _make_entry("H1", zone="body")]
        preds = ["GARBAGE_TAG_1", "GARBAGE_TAG_2"]
        m = compute_metrics(preds, entries, {"TXT", "H1"})
        assert m["_n_zone_checkable"] == 0
        assert m["zone_violation_rate"] == pytest.approx(0.0)


# ===========================================================================
# TestPublisherHoldoutSplit
# ===========================================================================
class TestPublisherHoldoutSplit:

    def _gt_from_publishers(self, publishers: List[str], docs_per_pub: int = 2) -> Dict[str, List]:
        gt: Dict[str, List] = {}
        for pub in publishers:
            for i in range(docs_per_pub):
                doc_id = f"{pub}97800000{i:04d}-ch{i:02d}"
                gt[doc_id] = [{"doc_id": doc_id, "para_index": 0, "text": "Hi.", "canonical_gold_tag": "TXT", "zone": "body"}]
        return gt

    def test_splits_at_publisher_level(self):
        gt = self._gt_from_publishers(["Alpha", "Beta", "Gamma", "Delta"], docs_per_pub=2)
        train_gt, holdout_gt, holdout_ids = split_holdout_publisher(gt, holdout_fraction=0.25, seed=42)
        # 4 publishers × 25% = 1 publisher held out → 2 docs
        assert len(holdout_gt) == 2
        assert len(train_gt) == 6

    def test_holdout_and_train_disjoint(self):
        gt = self._gt_from_publishers(["A", "B", "C", "D"], docs_per_pub=3)
        train_gt, holdout_gt, _ = split_holdout_publisher(gt, holdout_fraction=0.25, seed=0)
        assert set(train_gt.keys()).isdisjoint(set(holdout_gt.keys()))

    def test_reproducible_with_same_seed(self):
        gt = self._gt_from_publishers(["A", "B", "C", "D", "E"], docs_per_pub=2)
        _, _, ids1 = split_holdout_publisher(gt, holdout_fraction=0.4, seed=10)
        _, _, ids2 = split_holdout_publisher(gt, holdout_fraction=0.4, seed=10)
        assert ids1 == ids2

    def test_different_seeds_give_different_splits(self):
        gt = self._gt_from_publishers(["A", "B", "C", "D", "E", "F"], docs_per_pub=2)
        _, _, ids1 = split_holdout_publisher(gt, holdout_fraction=0.4, seed=1)
        _, _, ids2 = split_holdout_publisher(gt, holdout_fraction=0.4, seed=2)
        assert ids1 != ids2

    def test_returned_ids_are_sorted(self):
        gt = self._gt_from_publishers(["C", "A", "B"], docs_per_pub=2)
        _, _, ids = split_holdout_publisher(gt, holdout_fraction=0.33, seed=42)
        assert ids == sorted(ids)

    def test_all_docs_from_held_out_publisher_go_to_holdout(self):
        gt = self._gt_from_publishers(["Alpha", "Beta"], docs_per_pub=3)
        train_gt, holdout_gt, holdout_ids = split_holdout_publisher(
            gt, holdout_fraction=0.5, seed=1
        )
        # All 3 docs from the held-out publisher should be in holdout
        held_pub = _extract_publisher(holdout_ids[0])
        for doc_id in holdout_ids:
            assert _extract_publisher(doc_id) == held_pub


# ===========================================================================
# TestFormatReport
# ===========================================================================
class TestFormatReport:

    def _dummy_results(self, modes):
        results = {}
        for mode in modes:
            results[mode] = {
                "accuracy": 0.75,
                "zone_violation_rate": 0.03,
                "list_depth_accuracy": 0.60,
                "table_sem_accuracy": 0.80,
                "ref_accuracy": 0.70,
                "txt_fallback_rate": 0.20,
                "unmapped_rate": 0.05,
                "_n_total": 500,
                "_n_zone_checkable": 100,
                "_n_list_depth": 30,
                "_n_table": 80,
                "_n_ref": 120,
                "_n_unmapped": 25,
            }
        return results

    def test_report_contains_header(self):
        results = self._dummy_results(["baseline"])
        report = format_report(
            results=results,
            split_type="book-level holdout (20%, seed=42)",
            holdout_doc_ids=["doc_001", "doc_002"],
            n_train_docs=24,
            n_holdout_docs=6,
            modes_run=["baseline"],
        )
        assert "GENERALIZATION EVALUATION REPORT" in report
        assert "book-level holdout" in report

    def test_report_contains_mode_rows(self):
        modes = ["baseline", "alias", "semantic", "rules"]
        results = self._dummy_results(modes)
        report = format_report(
            results=results,
            split_type="book-level holdout (20%, seed=42)",
            holdout_doc_ids=["d1"],
            n_train_docs=24,
            n_holdout_docs=6,
            modes_run=modes,
        )
        assert "baseline" in report
        assert "+ alias" in report
        assert "+ semantic priors" in report
        assert "+ learned rules" in report

    def test_report_contains_incremental_delta_section(self):
        modes = ["baseline", "alias"]
        results = self._dummy_results(modes)
        report = format_report(
            results=results,
            split_type="book",
            holdout_doc_ids=[],
            n_train_docs=20,
            n_holdout_docs=5,
            modes_run=modes,
        )
        assert "INCREMENTAL GAIN VS BASELINE" in report

    def test_leakage_warning_shown_when_retriever(self):
        results = self._dummy_results(["retriever"])
        report = format_report(
            results=results,
            split_type="book",
            holdout_doc_ids=[],
            n_train_docs=20,
            n_holdout_docs=5,
            modes_run=["retriever"],
            retriever_leakage_warning=True,
        )
        assert "LEAKAGE" in report

    def test_none_metric_shown_as_na(self):
        results = {"baseline": {
            "accuracy": 0.5,
            "zone_violation_rate": 0.0,
            "list_depth_accuracy": None,   # no list-depth entries
            "table_sem_accuracy": None,
            "ref_accuracy": 0.6,
            "txt_fallback_rate": 0.3,
            "unmapped_rate": 0.0,
            "_n_total": 100, "_n_zone_checkable": 0, "_n_list_depth": 0,
            "_n_table": 0, "_n_ref": 50, "_n_unmapped": 0,
        }}
        report = format_report(
            results=results,
            split_type="book",
            holdout_doc_ids=[],
            n_train_docs=20,
            n_holdout_docs=5,
            modes_run=["baseline"],
        )
        assert "N/A" in report


# ===========================================================================
# TestRunEvaluationIntegration
# ===========================================================================
class TestRunEvaluationIntegration:
    """Integration tests using a minimal in-memory ground_truth via mocks."""

    def _mock_gt(self) -> Dict[str, List[Dict]]:
        """10 docs, 10 entries each, all canonical_gold_tag=TXT, zone=body."""
        gt: Dict[str, List[Dict]] = {}
        for d in range(10):
            doc_id = f"Pub{d:03d}0000000000{d:04d}-ch01"
            gt[doc_id] = [
                {
                    "doc_id": doc_id,
                    "para_index": i,
                    "text": f"Paragraph {i}.",
                    "gold_tag": "TXT",
                    "canonical_gold_tag": "TXT",
                    "zone": "body",
                }
                for i in range(10)
            ]
        return gt

    def _run_with_mocked_gt(self, gt, modes=None, split_type="book"):
        if modes is None:
            modes = ["baseline"]
        allowed = {"TXT", "TXT-FLUSH", "H1", "REF-N"}

        from processor.rule_learner import RuleLearner

        with (
            patch.object(RuleLearner, "load_ground_truth", return_value=gt),
            patch("tools.eval_generalization._load_allowed_styles", return_value=allowed),
            patch("tools.eval_generalization._load_alias_map", return_value={}),
            patch("tools.eval_generalization._load_semantic_artifacts", return_value={}),
            patch("tools.eval_generalization._load_normalize_tag", return_value=lambda tag, meta=None: tag if tag in allowed else "TXT"),
        ):
            return run_evaluation(
                split_type=split_type,
                holdout_fraction=0.2,
                holdout_seed=42,
                modes=modes,
                train_rules_if_missing=False,
                allowed_styles_override=allowed,
            )

    def test_returns_string(self):
        gt = self._mock_gt()
        report = self._run_with_mocked_gt(gt)
        assert isinstance(report, str)
        assert len(report) > 100

    def test_report_contains_accuracy(self):
        gt = self._mock_gt()
        report = self._run_with_mocked_gt(gt)
        assert "Accuracy" in report or "accuracy" in report.lower() or "%" in report

    def test_all_modes_run_without_error(self):
        gt = self._mock_gt()
        allowed = {"TXT", "TXT-FLUSH", "H1", "REF-N"}
        from processor.rule_learner import RuleLearner

        with (
            patch.object(RuleLearner, "load_ground_truth", return_value=gt),
            patch("tools.eval_generalization._load_allowed_styles", return_value=allowed),
            patch("tools.eval_generalization._load_alias_map", return_value={}),
            patch("tools.eval_generalization._load_semantic_artifacts", return_value={}),
            patch("tools.eval_generalization._load_normalize_tag", return_value=lambda t, meta=None: t if t in allowed else "TXT"),
        ):
            report = run_evaluation(
                modes=["baseline", "alias", "semantic", "rules"],
                split_type="book",
                holdout_fraction=0.2,
                holdout_seed=42,
                train_rules_if_missing=False,
                allowed_styles_override=allowed,
            )
        assert "ABLATION RESULTS" in report

    def test_publisher_split_runs_without_error(self):
        gt = self._mock_gt()
        report = self._run_with_mocked_gt(gt, split_type="publisher")
        assert isinstance(report, str)
        assert "GENERALIZATION EVALUATION REPORT" in report

    def test_invalid_mode_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown ablation modes"):
            run_evaluation(modes=["not_a_mode"])

    def test_report_file_written_when_specified(self):
        gt = self._mock_gt()
        allowed = {"TXT", "TXT-FLUSH"}
        from processor.rule_learner import RuleLearner

        # Use TemporaryDirectory on Windows to avoid file-lock issues
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "eval_report.txt"
            with (
                patch.object(RuleLearner, "load_ground_truth", return_value=gt),
                patch("tools.eval_generalization._load_allowed_styles", return_value=allowed),
                patch("tools.eval_generalization._load_alias_map", return_value={}),
                patch("tools.eval_generalization._load_semantic_artifacts", return_value={}),
                patch("tools.eval_generalization._load_normalize_tag", return_value=lambda t, meta=None: t if t in allowed else "TXT"),
            ):
                run_evaluation(
                    modes=["baseline"],
                    holdout_fraction=0.2,
                    holdout_seed=42,
                    train_rules_if_missing=False,
                    allowed_styles_override=allowed,
                    report_file=str(report_path),
                )
            content = report_path.read_text(encoding="utf-8")
        assert "GENERALIZATION EVALUATION REPORT" in content
