import types as pytypes

from processor import llm_client as llm


class _FakeUsage:
    prompt_token_count = 10
    candidates_token_count = 5
    total_token_count = 15


class _FakeResponse:
    usage_metadata = _FakeUsage()


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
    resp = pytypes.SimpleNamespace(usage_metadata=None)
    in_toks, out_toks = llm.GeminiClient.parse_usage(resp)
    assert in_toks is None
    assert out_toks is None


def test_parse_usage_supports_dict_usage_metadata():
    resp = {"usage_metadata": {"prompt_token_count": 9, "candidates_token_count": 4}}
    in_toks, out_toks = llm.GeminiClient.parse_usage(resp)
    assert in_toks == 9
    assert out_toks == 4


def test_gemini_client_passes_configured_model_name(monkeypatch):
    captured = {}

    class _Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    class _Client:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.models = _Models()

    monkeypatch.setattr(llm, "types", _FakeTypes)
    monkeypatch.setattr(llm, "genai", pytypes.SimpleNamespace(Client=_Client))

    client = llm.GeminiClient(api_key="k", model_name="gemini-2.5-pro")
    client.generate_content("hello")

    assert captured["model"] == "gemini-2.5-pro"


def test_gemini_client_retries_on_429(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    class _Models:
        def generate_content(self, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise Exception("429 ResourceExhausted")
            return _FakeResponse()

    class _Client:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.models = _Models()

    monkeypatch.setattr(llm, "types", _FakeTypes)
    monkeypatch.setattr(llm, "genai", pytypes.SimpleNamespace(Client=_Client))
    monkeypatch.setattr(llm.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(llm.time, "sleep", lambda s: sleeps.append(s))

    client = llm.GeminiClient(api_key="k", max_retries=5, retry_delay=1)
    response = client.generate_content("hello")

    assert response is not None
    assert calls["n"] == 3
    assert len(sleeps) == 2
