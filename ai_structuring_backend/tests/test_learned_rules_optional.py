import sys
import json
import shutil
from pathlib import Path
import types as pytypes

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import processor.rule_learner as rl
import processor.classifier as classifier_mod


def test_missing_learned_rules_logs_once(monkeypatch, caplog):
    missing_path = Path("backend/tests/nonexistent_learned_rules.json")
    monkeypatch.setattr(rl, "_MISSING_RULES_WARNED", False)

    learner1 = rl.RuleLearner()
    learner2 = rl.RuleLearner()

    with caplog.at_level("WARNING"):
        learner1.load_rules(path=missing_path)
        learner2.load_rules(path=missing_path)

    warnings = [r.message for r in caplog.records if "learned_rules disabled; using heuristics/LLM only" in r.message]
    assert len(warnings) == 1


def test_learned_rules_path_env_override(monkeypatch):
    tmp_root = Path("backend/tests/.tmp_rule_learner")
    tmp_root.mkdir(parents=True, exist_ok=True)
    override_path = tmp_root / "custom_learned_rules.json"
    payload = {
        "rules": [{"condition": "has_bullet", "predicted_tag": "BL-MID", "support": 10, "total": 10, "confidence": 1.0}],
        "num_rules": 1,
        "tag_stats": {},
    }
    override_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("LEARNED_RULES_PATH", str(override_path))
    learner = rl.RuleLearner()
    learner.load_rules()

    assert len(learner.rules) == 1
    assert learner.rules[0]["predicted_tag"] == "BL-MID"
    shutil.rmtree(tmp_root, ignore_errors=True)


def test_initialize_empty_learned_rules_schema():
    tmp_root = Path("backend/tests/.tmp_rule_learner")
    tmp_root.mkdir(parents=True, exist_ok=True)
    target = tmp_root / "learned_rules.json"
    path = rl.initialize_learned_rules_file(path=target, force=True)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"rules": [], "num_rules": 0, "tag_stats": {}}
    shutil.rmtree(tmp_root, ignore_errors=True)


def test_classifier_runs_without_learned_rules_file(monkeypatch):
    class _DummyClient:
        calls = 0

        def __init__(self, **kwargs):
            pass

        def generate_content(self, prompt, timeout=None):
            _DummyClient.calls += 1
            return pytypes.SimpleNamespace(
                text='[{"id":1,"tag":"TXT","confidence":90}]',
                usage_metadata=None,
            )

        def get_token_usage(self):
            return {
                "total_input_tokens": None,
                "total_output_tokens": None,
                "total_tokens": None,
                "total_latency_ms": 1,
                "request_count": _DummyClient.calls,
            }

        def get_last_usage(self):
            return {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "latency_ms": 1,
                "provider": "gemini",
                "model": "gemini-2.5-pro",
            }

    class _DummyRetriever:
        examples = []

    class _NoRulesLearner:
        def __init__(self):
            self.rules = []

        def load_rules(self):
            self.rules = []

    monkeypatch.setattr(classifier_mod, "GeminiClient", _DummyClient)
    monkeypatch.setattr(classifier_mod, "RuleLearner", _NoRulesLearner)
    monkeypatch.setattr(classifier_mod, "get_retriever", lambda: _DummyRetriever())
    monkeypatch.setattr(classifier_mod, "get_cache", lambda: None)
    monkeypatch.setattr(classifier_mod, "get_allowed_styles", lambda *args, **kwargs: {"TXT", "REF-N", "REF-U"})
    monkeypatch.setattr(classifier_mod.GeminiClassifier, "_load_system_prompt", lambda self: "x")

    clf = classifier_mod.GeminiClassifier(api_key="k", model_name="gemini-2.5-pro", enable_fallback=False)
    results = clf.classify([{"id": 1, "text": "Regular paragraph", "metadata": {"context_zone": "BODY"}}], "doc", "Academic")

    assert results
    assert results[0]["tag"] == "TXT"
    assert _DummyClient.calls >= 1
