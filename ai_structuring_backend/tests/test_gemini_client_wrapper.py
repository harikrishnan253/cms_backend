import os
import sys
from pathlib import Path
import types as pytypes

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm import gemini_client as gc


class _FakeTypes:
    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Part:
        def __init__(self, text: str):
            self.text = text

    class Content:
        def __init__(self, role: str, parts: list):
            self.role = role
            self.parts = parts


def test_parse_usage_returns_none_when_missing():
    resp = pytypes.SimpleNamespace(text="[]", usage_metadata=None)
    in_toks, out_toks = gc.GeminiClient.parse_usage(resp)
    assert in_toks is None
    assert out_toks is None


def test_parse_usage_supports_dict_usage_metadata():
    resp = {"usage_metadata": {"prompt_token_count": 7, "candidates_token_count": 3}}
    in_toks, out_toks = gc.GeminiClient.parse_usage(resp)
    assert in_toks == 7
    assert out_toks == 3


def test_model_name_used_in_request(monkeypatch):
    captured = {}

    class _Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return pytypes.SimpleNamespace(text='[{"id":1,"tag":"TXT","confidence":90}]', usage_metadata=None)

    class _Client:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.models = _Models()

    monkeypatch.setattr(gc, "types", _FakeTypes)
    monkeypatch.setattr(gc, "genai", pytypes.SimpleNamespace(Client=_Client))
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    client = gc.GeminiClient(model_name=model_name)
    labels = client.generate_labels("x")

    assert captured["model"] == "gemini-2.5-pro"
    assert labels and labels[0]["tag"] == "TXT"
