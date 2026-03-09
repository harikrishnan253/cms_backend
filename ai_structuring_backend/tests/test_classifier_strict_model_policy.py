import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import processor.classifier as classifier_mod


class _DummyRetriever:
    examples = []


class _DummyRuleLearner:
    def __init__(self):
        self.rules = []

    def load_rules(self):
        self.rules = []


def test_strict_policy_uses_only_primary_model_and_no_fallback_logs(monkeypatch, caplog):
    created_models = []

    class _DummyClient:
        def __init__(self, **kwargs):
            created_models.append(kwargs.get("model_name"))

        def get_token_usage(self):
            return {
                "total_input_tokens": None,
                "total_output_tokens": None,
                "total_tokens": None,
                "total_latency_ms": 0,
                "request_count": 0,
            }

        def get_last_usage(self):
            return {}

    monkeypatch.setattr(classifier_mod, "GeminiClient", _DummyClient)
    monkeypatch.setattr(classifier_mod, "STRICT_GEMINI_MODEL_POLICY", True)
    monkeypatch.setattr(classifier_mod, "get_retriever", lambda: _DummyRetriever())
    monkeypatch.setattr(classifier_mod, "get_cache", lambda: None)
    monkeypatch.setattr(classifier_mod, "RuleLearner", _DummyRuleLearner)
    monkeypatch.setattr(classifier_mod, "load_allowed_styles", lambda: ["TXT"])
    monkeypatch.setattr(classifier_mod.GeminiClassifier, "_load_system_prompt", lambda self: "x")
    monkeypatch.setattr(classifier_mod.GeminiClassifier, "_get_fallback_system_prompt", lambda self: "y")

    with caplog.at_level("INFO"):
        clf = classifier_mod.GeminiClassifier(
            api_key="k",
            model_name="gemini-2.5-pro",
            fallback_model_name="gemini-2.5-flash",
            enable_fallback=True,
        )

    assert created_models == ["gemini-2.5-pro"]
    assert clf.enable_fallback is False
    assert all("fallback" not in rec.message.lower() for rec in caplog.records)

