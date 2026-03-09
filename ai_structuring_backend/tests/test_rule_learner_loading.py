"""Tests for learned-rules loading behavior (optional vs strict mode)."""

from __future__ import annotations

import logging
from collections import defaultdict, Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from processor.rule_learner import (
    RuleLearner,
    MissingLearnedRulesError,
    _MISSING_RULES_LOGGED_PATHS,
)
from processor.classifier import GeminiClassifier


@pytest.fixture(autouse=True)
def _reset_missing_rules_log_cache():
    _MISSING_RULES_LOGGED_PATHS.clear()
    yield
    _MISSING_RULES_LOGGED_PATHS.clear()


class TestRuleLearnerMissingRulesOptional:
    def test_missing_rules_file_logs_once_and_returns_false(self, tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        missing_path = tmp_path / "learned_rules.json"

        learner1 = RuleLearner()
        learner2 = RuleLearner()

        assert learner1.load_rules(path=missing_path, required=False) is False
        assert learner2.load_rules(path=missing_path, required=False) is False

        matching = [r for r in caplog.records if "Rules file not found:" in r.message]
        info_matching = [r for r in matching if r.levelno == logging.INFO]
        debug_matching = [r for r in matching if r.levelno == logging.DEBUG]
        warning_matching = [r for r in matching if r.levelno == logging.WARNING]

        assert len(info_matching) == 1, "missing rules should be logged once at INFO"
        assert len(debug_matching) >= 1, "repeat missing rules logs should be downgraded to DEBUG"
        assert len(warning_matching) == 0, "optional missing rules should not warn"

    def test_missing_rules_clears_existing_state(self, tmp_path):
        learner = RuleLearner()
        learner.rules = [{"condition": {}, "predicted_tag": "TXT"}]
        learner.tag_stats = defaultdict(Counter, {"TXT": Counter({"x": 1})})

        learner.load_rules(path=tmp_path / "missing.json", required=False)

        assert learner.rules == []
        assert dict(learner.tag_stats) == {}


class TestRuleLearnerMissingRulesStrict:
    def test_missing_rules_file_raises_in_strict_mode(self, tmp_path):
        learner = RuleLearner()
        with pytest.raises(MissingLearnedRulesError):
            learner.load_rules(path=tmp_path / "missing.json", required=True)


class TestClassifierStartupWithoutLearnedRules:
    def test_classifier_proceeds_without_rules_file(self, tmp_path, caplog, monkeypatch):
        caplog.set_level(logging.INFO)
        missing_rules = tmp_path / "learned_rules.json"
        monkeypatch.setenv("REQUIRE_LEARNED_RULES", "false")

        with (
            patch("processor.classifier.GeminiClient") as mock_client_cls,
            patch("processor.classifier.get_cache", return_value=None),
            patch("processor.rule_learner.LEARNED_RULES_PATH", missing_rules),
        ):
            mock_client = MagicMock()
            mock_client.get_last_usage.return_value = {}
            mock_client.get_token_usage.return_value = {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "api_calls": 0,
            }
            mock_client_cls.return_value = mock_client

            clf = GeminiClassifier(api_key="test-key", model_name="gemini-2.5-pro", enable_fallback=False)

        assert clf.rule_learner is not None
        assert clf.rule_learner.rules == []

        rule_preds, llm_needed, _ = clf._apply_rules(
            [{"id": 1, "text": "Normal paragraph", "metadata": {"context_zone": "BODY"}}]
        )
        assert rule_preds == []
        assert len(llm_needed) == 1
        assert any("No learned rules found - will use LLM for all predictions" in r.message for r in caplog.records)

    def test_classifier_raises_when_rules_required(self, tmp_path, monkeypatch):
        missing_rules = tmp_path / "learned_rules.json"
        monkeypatch.setenv("REQUIRE_LEARNED_RULES", "true")

        with (
            patch("processor.classifier.GeminiClient") as mock_client_cls,
            patch("processor.classifier.get_cache", return_value=None),
            patch("processor.rule_learner.LEARNED_RULES_PATH", missing_rules),
        ):
            mock_client_cls.return_value = MagicMock()
            with pytest.raises(MissingLearnedRulesError):
                GeminiClassifier(api_key="test-key", model_name="gemini-2.5-pro", enable_fallback=False)
