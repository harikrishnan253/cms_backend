"""
Toggle matrix tests for the grounded retriever.

Tests all combinations of ENABLE_GROUNDED_RETRIEVER × GROUNDED_RETRIEVER_MODE
plus missing-file handling and no "GROUND TRUTH EXAMPLES" injection in the
default (disabled) mode.

These tests monkeypatch the module-level flags directly so no env-var reload
is needed between test runs.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import backend.app.services.grounded_retriever as gr_module
from backend.app.services.grounded_retriever import GroundedRetriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _minimal_gt(tmp_path: Path) -> Path:
    """Write a tiny ground-truth JSONL file and return its path."""
    p = tmp_path / "gt.jsonl"
    _write_jsonl(p, [
        {"doc_id": "A_01", "text": "Introduction", "canonical_gold_tag": "H1",
         "alignment_score": 1.0, "zone": "BODY"},
        {"doc_id": "B_01", "text": "Summary section", "canonical_gold_tag": "H2",
         "alignment_score": 1.0, "zone": "BODY"},
    ])
    return p


# ---------------------------------------------------------------------------
# Toggle: get_retriever() returns None when disabled
# ---------------------------------------------------------------------------

class TestGetRetrieverToggle:
    """get_retriever() must return None for every disabled configuration."""

    def _patch(self, monkeypatch, enable: bool, mode: str):
        monkeypatch.setattr(gr_module, "_ENABLE_RETRIEVER", enable)
        monkeypatch.setattr(gr_module, "_RETRIEVER_MODE", mode)
        monkeypatch.setattr(gr_module, "_retriever_instance", None)

    def test_disabled_flag_returns_none(self, monkeypatch):
        self._patch(monkeypatch, enable=False, mode="prompt_examples")
        assert gr_module.get_retriever() is None

    def test_mode_off_returns_none_even_when_enabled(self, monkeypatch):
        self._patch(monkeypatch, enable=True, mode="off")
        assert gr_module.get_retriever() is None

    def test_mode_off_with_disabled_flag_returns_none(self, monkeypatch):
        self._patch(monkeypatch, enable=False, mode="off")
        assert gr_module.get_retriever() is None

    def test_enabled_prompt_examples_creates_instance(self, monkeypatch, tmp_path):
        gt = _minimal_gt(tmp_path)
        monkeypatch.setattr(gr_module, "GROUND_TRUTH_PATH", gt)
        self._patch(monkeypatch, enable=True, mode="prompt_examples")
        result = gr_module.get_retriever()
        assert result is not None
        assert isinstance(result, GroundedRetriever)

    def test_enabled_invalid_tag_fallback_creates_instance(self, monkeypatch, tmp_path):
        gt = _minimal_gt(tmp_path)
        monkeypatch.setattr(gr_module, "GROUND_TRUTH_PATH", gt)
        self._patch(monkeypatch, enable=True, mode="invalid_tag_fallback")
        result = gr_module.get_retriever()
        assert result is not None

    def test_singleton_reused_on_second_call(self, monkeypatch, tmp_path):
        gt = _minimal_gt(tmp_path)
        monkeypatch.setattr(gr_module, "GROUND_TRUTH_PATH", gt)
        self._patch(monkeypatch, enable=True, mode="prompt_examples")
        r1 = gr_module.get_retriever()
        r2 = gr_module.get_retriever()
        assert r1 is r2


# ---------------------------------------------------------------------------
# Toggle: helper predicate functions
# ---------------------------------------------------------------------------

class TestPredicateFunctions:
    """is_prompt_examples_enabled / is_invalid_tag_fallback_enabled truth table."""

    def _patch(self, monkeypatch, enable: bool, mode: str):
        monkeypatch.setattr(gr_module, "_ENABLE_RETRIEVER", enable)
        monkeypatch.setattr(gr_module, "_RETRIEVER_MODE", mode)

    # is_prompt_examples_enabled
    def test_prompt_enabled_true_when_enabled_and_mode_prompt(self, monkeypatch):
        self._patch(monkeypatch, True, "prompt_examples")
        assert gr_module.is_prompt_examples_enabled() is True

    def test_prompt_disabled_when_flag_false(self, monkeypatch):
        self._patch(monkeypatch, False, "prompt_examples")
        assert gr_module.is_prompt_examples_enabled() is False

    def test_prompt_disabled_when_mode_is_off(self, monkeypatch):
        self._patch(monkeypatch, True, "off")
        assert gr_module.is_prompt_examples_enabled() is False

    def test_prompt_disabled_when_mode_is_invalid_tag_fallback(self, monkeypatch):
        self._patch(monkeypatch, True, "invalid_tag_fallback")
        assert gr_module.is_prompt_examples_enabled() is False

    # is_invalid_tag_fallback_enabled
    def test_fallback_enabled_true_when_enabled_and_mode_fallback(self, monkeypatch):
        self._patch(monkeypatch, True, "invalid_tag_fallback")
        assert gr_module.is_invalid_tag_fallback_enabled() is True

    def test_fallback_disabled_when_flag_false(self, monkeypatch):
        self._patch(monkeypatch, False, "invalid_tag_fallback")
        assert gr_module.is_invalid_tag_fallback_enabled() is False

    def test_fallback_disabled_when_mode_is_off(self, monkeypatch):
        self._patch(monkeypatch, True, "off")
        assert gr_module.is_invalid_tag_fallback_enabled() is False

    def test_fallback_disabled_when_mode_is_prompt_examples(self, monkeypatch):
        self._patch(monkeypatch, True, "prompt_examples")
        assert gr_module.is_invalid_tag_fallback_enabled() is False

    # Mutual exclusion — exactly one mode is active at a time
    def test_at_most_one_mode_active_prompt(self, monkeypatch):
        self._patch(monkeypatch, True, "prompt_examples")
        assert gr_module.is_prompt_examples_enabled() is True
        assert gr_module.is_invalid_tag_fallback_enabled() is False

    def test_at_most_one_mode_active_fallback(self, monkeypatch):
        self._patch(monkeypatch, True, "invalid_tag_fallback")
        assert gr_module.is_prompt_examples_enabled() is False
        assert gr_module.is_invalid_tag_fallback_enabled() is True

    def test_both_disabled_when_off(self, monkeypatch):
        self._patch(monkeypatch, True, "off")
        assert gr_module.is_prompt_examples_enabled() is False
        assert gr_module.is_invalid_tag_fallback_enabled() is False


# ---------------------------------------------------------------------------
# Missing ground_truth.jsonl does NOT crash when retriever is disabled
# ---------------------------------------------------------------------------

class TestMissingFileHandling:
    """ground_truth.jsonl absence must be silent when the retriever is disabled."""

    def test_no_crash_when_file_missing_and_retriever_disabled(
        self, monkeypatch, tmp_path
    ):
        nonexistent = tmp_path / "does_not_exist.jsonl"
        monkeypatch.setattr(gr_module, "_ENABLE_RETRIEVER", False)
        monkeypatch.setattr(gr_module, "_retriever_instance", None)
        # Must not raise even though the path doesn't exist
        result = gr_module.get_retriever()
        assert result is None

    def test_retriever_loads_gracefully_with_missing_file(self, tmp_path):
        nonexistent = tmp_path / "missing.jsonl"
        # GroundedRetriever with a missing path: no examples, but no exception
        retriever = GroundedRetriever(nonexistent)
        assert retriever.examples == []
        assert retriever.retrieve_examples("anything") == []

    def test_retriever_returns_empty_on_missing_file(self, tmp_path):
        retriever = GroundedRetriever(tmp_path / "nope.jsonl")
        result = retriever.retrieve_examples("Introduction", k=3)
        assert result == []

    def test_suggest_returns_none_on_empty_corpus(self, tmp_path):
        retriever = GroundedRetriever(tmp_path / "nope.jsonl")
        result = retriever.suggest_teacher_forced_tag(
            text="Introduction",
            metadata={"context_zone": "BODY"},
            allowed_styles={"H1", "TXT"},
        )
        assert result is None


# ---------------------------------------------------------------------------
# No "GROUND TRUTH EXAMPLES" injected in default-disabled mode
# ---------------------------------------------------------------------------

class TestNoGroundTruthInjectionWhenDisabled:
    """
    When retriever is disabled (the default), format_examples_for_prompt()
    should return an empty string and the canonical 'GROUND TRUTH EXAMPLES'
    header must never appear in a formatted prompt.
    """

    INJECTION_MARKER = "GROUND TRUTH EXAMPLES"

    def test_format_examples_empty_list_returns_empty_string(self, tmp_path):
        retriever = GroundedRetriever(_minimal_gt(tmp_path))
        result = retriever.format_examples_for_prompt([])
        assert result == ""

    def test_injection_marker_absent_from_empty_format(self, tmp_path):
        retriever = GroundedRetriever(_minimal_gt(tmp_path))
        formatted = retriever.format_examples_for_prompt([])
        assert self.INJECTION_MARKER not in formatted

    def test_is_prompt_examples_disabled_by_default_env(self, monkeypatch):
        # Simulate a clean env (no ENABLE_GROUNDED_RETRIEVER set)
        monkeypatch.setattr(gr_module, "_ENABLE_RETRIEVER", False)
        assert gr_module.is_prompt_examples_enabled() is False

    def test_format_with_examples_contains_marker(self, tmp_path):
        """Sanity-check: marker IS present when examples are non-empty."""
        retriever = GroundedRetriever(_minimal_gt(tmp_path))
        examples = retriever.retrieve_examples("Introduction", k=1)
        formatted = retriever.format_examples_for_prompt(examples)
        assert self.INJECTION_MARKER in formatted

    def test_no_injection_when_retriever_returns_none(self, monkeypatch):
        """get_retriever() returning None means callers skip injection entirely."""
        monkeypatch.setattr(gr_module, "_ENABLE_RETRIEVER", False)
        monkeypatch.setattr(gr_module, "_retriever_instance", None)
        retriever = gr_module.get_retriever()
        assert retriever is None  # callers: if retriever is None: skip injection


# ---------------------------------------------------------------------------
# retrieve_examples: metadata kwarg propagates zone correctly
# ---------------------------------------------------------------------------

class TestRetrieveExamplesMetadataParam:
    """metadata dict as alternative to explicit zone= kwarg."""

    def test_metadata_context_zone_filters_correctly(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        _write_jsonl(gt, [
            {"doc_id": "A", "text": "Appendix content", "canonical_gold_tag": "APP-H1",
             "alignment_score": 1.0, "zone": "BACK_MATTER"},
            {"doc_id": "B", "text": "Main body text", "canonical_gold_tag": "TXT",
             "alignment_score": 1.0, "zone": "BODY"},
        ])
        retriever = GroundedRetriever(gt)
        results = retriever.retrieve_examples(
            "Appendix content",
            k=5,
            metadata={"context_zone": "BACK_MATTER"},
        )
        assert all(r["zone"] == "BACK_MATTER" for r in results)

    def test_explicit_zone_takes_precedence_over_metadata(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        _write_jsonl(gt, [
            {"doc_id": "A", "text": "Body text", "canonical_gold_tag": "TXT",
             "alignment_score": 1.0, "zone": "BODY"},
            {"doc_id": "B", "text": "Back matter", "canonical_gold_tag": "APP-H1",
             "alignment_score": 1.0, "zone": "BACK_MATTER"},
        ])
        retriever = GroundedRetriever(gt)
        # explicit zone="BODY" should win over metadata's "BACK_MATTER"
        results = retriever.retrieve_examples(
            "Body text",
            k=5,
            zone="BODY",
            metadata={"context_zone": "BACK_MATTER"},
        )
        assert all(r["zone"] == "BODY" for r in results)

    def test_no_zone_no_metadata_returns_all_zones(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        _write_jsonl(gt, [
            {"doc_id": "A", "text": "Intro text", "canonical_gold_tag": "H1",
             "alignment_score": 1.0, "zone": "BODY"},
            {"doc_id": "B", "text": "Figure 1 caption", "canonical_gold_tag": "FIG-LEG",
             "alignment_score": 1.0, "zone": "FLOATS"},
        ])
        retriever = GroundedRetriever(gt)
        results = retriever.retrieve_examples("some text", k=5)
        zones = {r["zone"] for r in results}
        assert len(zones) > 1  # both zones returned


# ---------------------------------------------------------------------------
# UNMAPPED and low-quality entries are filtered at load time
# ---------------------------------------------------------------------------

class TestDatasetFiltering:
    def test_unmapped_entries_excluded(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        _write_jsonl(gt, [
            {"doc_id": "A", "text": "Good text", "canonical_gold_tag": "H1",
             "alignment_score": 1.0, "zone": "BODY"},
            {"doc_id": "B", "text": "Bad text", "canonical_gold_tag": "UNMAPPED",
             "alignment_score": 1.0, "zone": "BODY"},
        ])
        retriever = GroundedRetriever(gt)
        assert len(retriever.examples) == 1
        assert all(e["canonical_gold_tag"] != "UNMAPPED" for e in retriever.examples)

    def test_low_alignment_score_excluded(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        _write_jsonl(gt, [
            {"doc_id": "A", "text": "High quality", "canonical_gold_tag": "H1",
             "alignment_score": 0.90, "zone": "BODY"},
            {"doc_id": "B", "text": "Low quality", "canonical_gold_tag": "H2",
             "alignment_score": 0.50, "zone": "BODY"},
        ])
        retriever = GroundedRetriever(gt)
        assert len(retriever.examples) == 1
        assert retriever.examples[0]["text"] == "High quality"

    def test_boundary_score_075_included(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        _write_jsonl(gt, [
            {"doc_id": "A", "text": "Boundary text", "canonical_gold_tag": "H1",
             "alignment_score": 0.75, "zone": "BODY"},
        ])
        retriever = GroundedRetriever(gt)
        assert len(retriever.examples) == 1

    def test_malformed_json_line_skipped(self, tmp_path):
        gt = tmp_path / "gt.jsonl"
        gt.write_text(
            '{"doc_id": "A", "text": "Good", "canonical_gold_tag": "H1", '
            '"alignment_score": 1.0, "zone": "BODY"}\n'
            'NOT VALID JSON\n',
            encoding="utf-8",
        )
        retriever = GroundedRetriever(gt)
        assert len(retriever.examples) == 1
