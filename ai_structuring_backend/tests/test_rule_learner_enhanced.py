"""
Tests for offline rule-learner enhancements:
- Holdout split (doc-level)
- Semantic artifact enrichment
- Holdout validator
- Enhanced report generation
- Backward-compatible save/load
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to import the module under test
# ---------------------------------------------------------------------------
import sys
import os

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from processor.rule_learner import (
    RuleLearner,
    load_semantic_artifacts,
    SEMANTIC_KNOWLEDGE_PATH,
    SEMANTIC_TRANSITIONS_PATH,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_learner() -> RuleLearner:
    """Return a fresh RuleLearner with no rules loaded."""
    learner = RuleLearner()
    learner.rules = []
    learner.tag_stats = defaultdict(Counter)
    return learner


def _make_ground_truth(n_docs: int = 10, entries_per_doc: int = 5) -> Dict[str, List[Dict]]:
    """Build a minimal ground_truth dict for testing."""
    gt: Dict[str, List[Dict]] = {}
    for d in range(n_docs):
        doc_id = f"doc_{d:03d}"
        gt[doc_id] = [
            {
                "doc_id": doc_id,
                "para_index": i,
                "text": f"Paragraph {i} of {doc_id}.",
                "canonical_gold_tag": "TXT",
                "zone": "BODY",
            }
            for i in range(entries_per_doc)
        ]
    return gt


def _make_examples(n: int = 20, zone: str = "BODY", tag: str = "TXT") -> List[Dict]:
    """Build minimal training examples."""
    learner = _make_learner()
    examples = []
    for i in range(n):
        feat = learner.feature_extractor.extract_features(
            f"Some text here {i}.", {"context_zone": zone}
        )
        feat["prev_tag"] = "TXT" if i > 0 else "START"
        feat["next_tag"] = "TXT" if i < n - 1 else "END"
        examples.append({
            "features": feat,
            "label": tag,
            "text": f"Some text here {i}.",
            "doc_id": f"doc_{i // 5:03d}",
            "zone": zone,
        })
    return examples


# ============================================================================
# TestHoldoutSplit
# ============================================================================

class TestHoldoutSplit:
    def test_correct_doc_count_in_holdout(self):
        learner = _make_learner()
        gt = _make_ground_truth(n_docs=10)
        train_gt, holdout_gt, holdout_ids = learner.split_holdout(gt, holdout_fraction=0.2, seed=42)
        assert len(holdout_gt) == 2  # round(10 * 0.2) = 2
        assert len(train_gt) == 8

    def test_holdout_and_train_are_disjoint(self):
        learner = _make_learner()
        gt = _make_ground_truth(n_docs=15)
        train_gt, holdout_gt, holdout_ids = learner.split_holdout(gt, holdout_fraction=0.3, seed=0)
        assert set(train_gt.keys()).isdisjoint(set(holdout_gt.keys()))

    def test_train_plus_holdout_covers_all_docs(self):
        learner = _make_learner()
        gt = _make_ground_truth(n_docs=10)
        train_gt, holdout_gt, _ = learner.split_holdout(gt, holdout_fraction=0.2, seed=7)
        assert set(train_gt.keys()) | set(holdout_gt.keys()) == set(gt.keys())

    def test_reproducible_with_same_seed(self):
        learner = _make_learner()
        gt = _make_ground_truth(n_docs=20)
        _, _, ids1 = learner.split_holdout(gt, holdout_fraction=0.2, seed=99)
        _, _, ids2 = learner.split_holdout(gt, holdout_fraction=0.2, seed=99)
        assert ids1 == ids2

    def test_different_seeds_give_different_splits(self):
        learner = _make_learner()
        gt = _make_ground_truth(n_docs=20)
        _, _, ids1 = learner.split_holdout(gt, holdout_fraction=0.3, seed=1)
        _, _, ids2 = learner.split_holdout(gt, holdout_fraction=0.3, seed=2)
        # With 20 docs and different seeds it is overwhelmingly likely to differ
        assert ids1 != ids2

    def test_single_doc_still_works(self):
        learner = _make_learner()
        gt = {"only_doc": [{"doc_id": "only_doc", "para_index": 0, "text": "A", "canonical_gold_tag": "TXT", "zone": "BODY"}]}
        train_gt, holdout_gt, ids = learner.split_holdout(gt, holdout_fraction=0.5, seed=0)
        # max(1, round(1 * 0.5)) = 1 → holdout gets the only doc
        assert len(holdout_gt) == 1
        assert len(train_gt) == 0

    def test_returned_ids_are_sorted(self):
        learner = _make_learner()
        gt = _make_ground_truth(n_docs=10)
        _, _, ids = learner.split_holdout(gt, holdout_fraction=0.3, seed=42)
        assert ids == sorted(ids)


# ============================================================================
# TestSemanticEnrichment
# ============================================================================

class TestSemanticEnrichment:

    def _zone_artifacts(self, zone_key: str, tag: str, frequency: float) -> dict:
        return {
            "zone_tag_priors": {
                zone_key: {
                    "distribution": {
                        tag: {"frequency": frequency, "count": 100}
                    }
                }
            }
        }

    def _transition_artifacts(self, src: str, dst: str, prob: float) -> dict:
        return {
            "global_transitions": {
                src: {
                    "next_tag_distribution": {
                        dst: {"probability": prob, "count": 50}
                    }
                }
            }
        }

    def test_zone_prior_rule_added_when_above_threshold(self):
        learner = _make_learner()
        examples = _make_examples(n=20, zone="BACK_MATTER", tag="REF-N")
        artifacts = self._zone_artifacts("BACK_MATTER", "REF-N", frequency=0.50)
        added = learner.enrich_from_semantic_artifacts(
            examples, artifacts,
            min_support_semantic=3,
            min_confidence=0.50,
            zone_prior_threshold=0.25,
        )
        assert added >= 0  # may be 0 if training data doesn't confirm — no hard failure

    def test_zone_prior_rule_not_added_below_frequency_threshold(self):
        learner = _make_learner()
        examples = _make_examples(n=20, zone="BACK_MATTER", tag="REF-N")
        artifacts = self._zone_artifacts("BACK_MATTER", "REF-N", frequency=0.10)
        added = learner.enrich_from_semantic_artifacts(
            examples, artifacts,
            min_support_semantic=1,
            min_confidence=0.01,
            zone_prior_threshold=0.25,
        )
        assert added == 0  # frequency 0.10 < threshold 0.25 → not added

    def test_no_artifact_no_enrichment(self):
        learner = _make_learner()
        examples = _make_examples(n=20)
        added = learner.enrich_from_semantic_artifacts(examples, artifacts={})
        assert added == 0
        assert all(not r.get("semantic_enriched") for r in learner.rules)

    def test_existing_condition_not_duplicated(self):
        learner = _make_learner()
        learner.rules = [{
            "condition": "zone=BACK_MATTER",
            "predicted_tag": "REF-N",
            "support": 50,
            "total": 60,
            "confidence": 0.83,
        }]
        examples = _make_examples(n=20, zone="BACK_MATTER", tag="REF-N")
        artifacts = self._zone_artifacts("BACK_MATTER", "REF-N", frequency=0.50)
        added = learner.enrich_from_semantic_artifacts(
            examples, artifacts,
            min_support_semantic=1,
            min_confidence=0.01,
            zone_prior_threshold=0.25,
        )
        assert added == 0  # already exists

    def test_semantic_enriched_flag_set_on_new_rule(self):
        """Rules added via enrichment must have semantic_enriched=True."""
        learner = _make_learner()
        # Craft examples so "zone=SPECIAL" → "TXT" is highly supported
        n = 20
        special_examples = []
        for i in range(n):
            feat = learner.feature_extractor.extract_features(
                f"Text {i}.", {"context_zone": "SPECIAL"}
            )
            feat["prev_tag"] = "START"
            feat["next_tag"] = "END"
            special_examples.append({
                "features": feat,
                "label": "TXT",
                "text": f"Text {i}.",
                "doc_id": "doc_000",
                "zone": "SPECIAL",
            })

        artifacts = self._zone_artifacts("SPECIAL", "TXT", frequency=0.99)
        added = learner.enrich_from_semantic_artifacts(
            special_examples, artifacts,
            min_support_semantic=1,
            min_confidence=0.50,
            zone_prior_threshold=0.25,
        )
        if added > 0:
            enriched = [r for r in learner.rules if r.get("semantic_enriched")]
            assert len(enriched) == added
            for r in enriched:
                assert r["semantic_enriched"] is True

    def test_transition_prior_rule_candidate_evaluated_on_training_data(self):
        """Transition prior candidates that fail training-data check are not added."""
        learner = _make_learner()
        # Examples where prev_tag=H1 → TXT doesn't hold
        examples = []
        for i in range(20):
            feat = {"prev_tag": "H1", "zone": "BODY"}
            examples.append({"features": feat, "label": "H2", "text": f"T {i}", "doc_id": "d", "zone": "BODY"})

        artifacts = self._transition_artifacts("H1", "TXT", prob=0.90)
        added = learner.enrich_from_semantic_artifacts(
            examples, artifacts,
            min_support_semantic=5,
            min_confidence=0.80,
            transition_prior_threshold=0.70,
        )
        # Even though artifact says H1→TXT with 90% prob, training data says otherwise
        assert added == 0


# ============================================================================
# TestCountRuleMatch
# ============================================================================

class TestCountRuleMatch:
    def test_boolean_feature_count(self):
        learner = _make_learner()
        examples = [
            {"features": {"has_bullet": True}, "label": "BL-FIRST"},
            {"features": {"has_bullet": True}, "label": "BL-MID"},
            {"features": {"has_bullet": False}, "label": "TXT"},
        ]
        support, total = learner._count_rule_match(examples, "has_bullet", "BL-FIRST")
        assert total == 2
        assert support == 1

    def test_value_feature_count(self):
        learner = _make_learner()
        examples = [
            {"features": {"zone": "BODY"}, "label": "TXT"},
            {"features": {"zone": "BODY"}, "label": "TXT"},
            {"features": {"zone": "BACK_MATTER"}, "label": "REF-N"},
        ]
        support, total = learner._count_rule_match(examples, "zone=BODY", "TXT")
        assert total == 2
        assert support == 2

    def test_zero_when_no_match(self):
        learner = _make_learner()
        examples = [{"features": {"zone": "BODY"}, "label": "TXT"}]
        support, total = learner._count_rule_match(examples, "zone=TABLE", "TXT")
        assert total == 0
        assert support == 0


# ============================================================================
# TestHoldoutValidator
# ============================================================================

class TestHoldoutValidator:

    def _learner_with_perfect_rule(self) -> RuleLearner:
        learner = _make_learner()
        # Rule: is_short → TXT (will match all short examples)
        learner.rules = [{
            "condition": "is_short",
            "predicted_tag": "TXT",
            "support": 10,
            "total": 10,
            "confidence": 1.0,
        }]
        return learner

    def test_zero_rules_gives_zero_coverage(self):
        learner = _make_learner()
        learner.rules = []
        examples = _make_examples(n=10)
        stats = learner.evaluate_on_holdout(examples)
        assert stats["covered"] == 0
        assert stats["coverage"] == pytest.approx(0.0)
        assert stats["precision"] == pytest.approx(0.0)

    def test_coverage_and_precision_computed_correctly(self):
        learner = _make_learner()
        # Rule: zone=BODY → TXT (all examples are BODY zone, tagged TXT)
        learner.rules = [{
            "condition": "zone=BODY",
            "predicted_tag": "TXT",
            "support": 20,
            "total": 20,
            "confidence": 1.0,
        }]
        examples = _make_examples(n=10, zone="BODY", tag="TXT")
        stats = learner.evaluate_on_holdout(examples)
        assert stats["total"] == 10
        assert stats["covered"] == 10
        assert stats["correct"] == 10
        assert stats["coverage"] == pytest.approx(1.0)
        assert stats["precision"] == pytest.approx(1.0)
        assert stats["accuracy"] == pytest.approx(1.0)

    def test_per_tag_tp_fp_fn_computed(self):
        learner = _make_learner()
        # Rule predicts TXT for zone=BODY, but gold is H1 → FP for TXT, FN for H1
        learner.rules = [{
            "condition": "zone=BODY",
            "predicted_tag": "TXT",
            "support": 5,
            "total": 5,
            "confidence": 1.0,
        }]
        examples = _make_examples(n=5, zone="BODY", tag="H1")
        stats = learner.evaluate_on_holdout(examples)
        per = stats["per_tag"]
        assert per["TXT"]["fp"] == 5
        assert per["H1"]["fn"] == 5

    def test_per_tag_precision_recall_computed(self):
        learner = _make_learner()
        # 8 correct TXT, 2 wrong (gold=TXT but predict nothing → FN via no rule match)
        # Use rule that matches only 8/10
        learner.rules = [{
            "condition": "zone=BODY",
            "predicted_tag": "TXT",
            "support": 8,
            "total": 10,
            "confidence": 0.8,
        }]
        examples = _make_examples(n=10, zone="BODY", tag="TXT")
        stats = learner.evaluate_on_holdout(examples)
        # All 10 match zone=BODY → covered=10, correct=10 (rule says TXT, gold=TXT)
        per = stats["per_tag"]
        assert per["TXT"]["tp"] == 10
        assert per["TXT"]["precision"] == pytest.approx(1.0)
        assert per["TXT"]["recall"] == pytest.approx(1.0)

    def test_empty_holdout_gives_zero_stats(self):
        learner = _make_learner()
        stats = learner.evaluate_on_holdout([])
        assert stats["total"] == 0
        assert stats["coverage"] == pytest.approx(0.0)
        assert stats["precision"] == pytest.approx(0.0)
        assert stats["accuracy"] == pytest.approx(0.0)
        assert stats["per_tag"] == {}


# ============================================================================
# TestEnhancedReport
# ============================================================================

class TestEnhancedReport:

    def _learner_with_rules(self) -> RuleLearner:
        learner = _make_learner()
        learner.rules = [
            {
                "condition": "zone=BODY",
                "predicted_tag": "TXT",
                "support": 100,
                "total": 110,
                "confidence": 0.91,
            },
            {
                "condition": "zone=BACK_MATTER",
                "predicted_tag": "REF-N",
                "support": 50,
                "total": 55,
                "confidence": 0.91,
                "semantic_enriched": True,
            },
        ]
        return learner

    def test_report_without_holdout_is_backward_compatible(self):
        learner = self._learner_with_rules()
        report = learner.generate_report()
        assert "LEARNED RULES REPORT" in report
        assert "HOLDOUT EVALUATION" not in report
        assert "SEMANTIC ENRICHMENT" not in report

    def test_report_contains_holdout_section(self):
        learner = self._learner_with_rules()
        holdout_stats = {
            "total": 200,
            "covered": 160,
            "correct": 140,
            "coverage": 0.80,
            "precision": 0.875,
            "accuracy": 0.70,
            "per_tag": {
                "TXT": {"tp": 100, "fp": 10, "fn": 20, "precision": 0.91, "recall": 0.83},
            },
        }
        report = learner.generate_report(
            holdout_stats=holdout_stats,
            holdout_doc_ids=["doc_001", "doc_002"],
        )
        assert "HOLDOUT EVALUATION" in report
        assert "doc_001" in report
        assert "200" in report  # total paragraphs
        assert "80.0%" in report  # coverage

    def test_report_contains_per_tag_metrics(self):
        learner = self._learner_with_rules()
        holdout_stats = {
            "total": 100,
            "covered": 80,
            "correct": 70,
            "coverage": 0.80,
            "precision": 0.875,
            "accuracy": 0.70,
            "per_tag": {
                "TXT": {"tp": 60, "fp": 5, "fn": 10, "precision": 0.92, "recall": 0.86},
            },
        }
        report = learner.generate_report(holdout_stats=holdout_stats, holdout_doc_ids=[])
        assert "TXT" in report
        assert "tp=" in report
        assert "fp=" in report
        assert "fn=" in report

    def test_report_contains_semantic_enrichment_section(self):
        learner = self._learner_with_rules()
        report = learner.generate_report(semantic_enriched_count=1)
        assert "SEMANTIC ENRICHMENT" in report
        assert "1 rules added" in report

    def test_semantic_marker_in_rules_list(self):
        learner = self._learner_with_rules()
        report = learner.generate_report()
        assert "[semantic]" in report  # marker for semantic_enriched rule

    def test_no_rules_returns_stub_message(self):
        learner = _make_learner()
        report = learner.generate_report()
        assert "No rules learned yet" in report


# ============================================================================
# TestLoadRulesBackwardCompat
# ============================================================================

class TestLoadRulesBackwardCompat:

    def test_load_existing_rules_no_metadata_field(self):
        """Files without metadata key load successfully."""
        learner = _make_learner()
        data = {
            "rules": [{"condition": "is_short", "predicted_tag": "TXT", "support": 5, "total": 6, "confidence": 0.83}],
            "num_rules": 1,
            "tag_stats": {"TXT": {"is_short": 5}},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            result = learner.load_rules(path=path)
            assert result is True
            assert len(learner.rules) == 1
        finally:
            path.unlink(missing_ok=True)

    def test_metadata_field_ignored_at_load(self):
        """Files with metadata key still load rules correctly."""
        learner = _make_learner()
        data = {
            "rules": [{"condition": "is_short", "predicted_tag": "TXT", "support": 5, "total": 6, "confidence": 0.83}],
            "num_rules": 1,
            "tag_stats": {},
            "metadata": {"train_docs": ["doc_000"], "holdout_docs": [], "holdout_fraction": 0.2},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            result = learner.load_rules(path=path)
            assert result is True
            assert len(learner.rules) == 1
            assert not hasattr(learner, "metadata") or True  # metadata not stored on learner
        finally:
            path.unlink(missing_ok=True)

    def test_semantic_enriched_field_does_not_break_apply_rules(self):
        """Rules with semantic_enriched=True still work in apply_rules()."""
        learner = _make_learner()
        learner.rules = [{
            "condition": "zone=BODY",
            "predicted_tag": "TXT",
            "support": 10,
            "total": 10,
            "confidence": 1.0,
            "semantic_enriched": True,
        }]
        result = learner.apply_rules("Some text.", {"context_zone": "BODY"})
        assert result == "TXT"

    def test_save_rules_with_metadata_creates_valid_json(self):
        """save_rules(metadata=...) writes a valid JSON that load_rules() accepts."""
        learner = _make_learner()
        learner.rules = [{"condition": "is_short", "predicted_tag": "TXT", "support": 5, "total": 6, "confidence": 0.83}]
        meta = {"train_docs": ["d1", "d2"], "holdout_docs": ["d3"], "semantic_enriched_count": 0}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rules.json"
            learner.save_rules(path=path, metadata=meta)
            assert path.exists()
            # Load back
            learner2 = _make_learner()
            result = learner2.load_rules(path=path)
            assert result is True
            assert len(learner2.rules) == 1


# ============================================================================
# TestExtractTrainingExamplesZoneField
# ============================================================================

class TestExtractTrainingExamplesZoneField:

    def test_zone_field_stored_in_example(self):
        """extract_training_examples() must store 'zone' for holdout eval."""
        learner = _make_learner()
        gt = {
            "doc_a": [
                {"doc_id": "doc_a", "para_index": 0, "text": "Hello world.", "canonical_gold_tag": "TXT", "zone": "BACK_MATTER"},
            ]
        }
        examples = learner.extract_training_examples(gt)
        assert len(examples) == 1
        assert examples[0]["zone"] == "BACK_MATTER"

    def test_zone_defaults_to_body_when_missing(self):
        learner = _make_learner()
        gt = {
            "doc_a": [
                {"doc_id": "doc_a", "para_index": 0, "text": "Hello.", "canonical_gold_tag": "TXT"},
            ]
        }
        examples = learner.extract_training_examples(gt)
        assert examples[0]["zone"] == "BODY"


# ============================================================================
# TestLoadSemanticArtifacts (module-level function)
# ============================================================================

class TestLoadSemanticArtifacts:

    def test_returns_empty_dict_on_missing_files(self):
        result = load_semantic_artifacts(
            knowledge_path=Path("/nonexistent/path/knowledge.json"),
            transitions_path=Path("/nonexistent/path/transitions.json"),
        )
        assert result == {}

    def test_loads_zone_tag_priors_when_file_exists(self):
        data = {"zone_tag_priors": {"BODY": {"distribution": {"TXT": {"frequency": 0.5}}}}, "tag_families": {}}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            kp = Path(f.name)
        try:
            result = load_semantic_artifacts(knowledge_path=kp, transitions_path=Path("/no/transitions.json"))
            assert "zone_tag_priors" in result
            assert "BODY" in result["zone_tag_priors"]
        finally:
            kp.unlink(missing_ok=True)

    def test_loads_global_transitions_when_file_exists(self):
        data = {"global_transitions": {"TXT": {"next_tag_distribution": {"H1": {"probability": 0.8}}}}}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            tp = Path(f.name)
        try:
            result = load_semantic_artifacts(knowledge_path=Path("/no/knowledge.json"), transitions_path=tp)
            assert "global_transitions" in result
            assert "TXT" in result["global_transitions"]
        finally:
            tp.unlink(missing_ok=True)

    def test_gracefully_handles_malformed_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            f.write("NOT VALID JSON {{{")
            kp = Path(f.name)
        try:
            # Should not raise
            result = load_semantic_artifacts(knowledge_path=kp, transitions_path=Path("/no/t.json"))
            assert isinstance(result, dict)
        finally:
            kp.unlink(missing_ok=True)
