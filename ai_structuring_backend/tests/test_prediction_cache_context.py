import sys
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.prediction_cache import PredictionCache


def _base_context() -> dict:
    return {
        "document_name": "doc1",
        "document_content_hash": "doc-hash-123",
        "block_fingerprint": "block-hash-456",
        "system_prompt_hash": "sys-hash-111",
        "user_prompt_hash": "usr-hash-222",
        "provider": "gemini",
        "model": "gemini-2.5-pro",
        "allowed_styles_hash": "styles-hash-aaa",
        "style_aliases_hash": "aliases-hash-bbb",
    }


def _run_with_cache_dir(test_fn):
    run_dir = ROOT / "backend" / "tests" / ".tmp_cache_context" / f"run_{uuid.uuid4().hex}"
    cache_dir = run_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        test_fn(cache_dir)
    finally:
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)


def test_cache_hit_requires_exact_context():
    def _test(cache_dir):
        cache = PredictionCache(cache_dir=cache_dir)
        ctx = _base_context()
        pred = {"id": 1, "tag": "TXT", "confidence": 90}
        cache.set("doc1", 1, "Same block text", pred, zone="BODY", key_context=ctx)
        got = cache.get("doc1", 1, "Same block text", zone="BODY", key_context=ctx)
        assert got is not None
        assert got["tag"] == "TXT"
    _run_with_cache_dir(_test)


def test_cache_miss_when_model_changes():
    def _test(cache_dir):
        cache = PredictionCache(cache_dir=cache_dir)
        ctx = _base_context()
        cache.set("doc1", 1, "Same block text", {"id": 1, "tag": "TXT"}, zone="BODY", key_context=ctx)
        changed = dict(ctx)
        changed["model"] = "gemini-2.5-flash"
        assert cache.get("doc1", 1, "Same block text", zone="BODY", key_context=changed) is None
    _run_with_cache_dir(_test)


def test_cache_miss_when_prompt_changes():
    def _test(cache_dir):
        cache = PredictionCache(cache_dir=cache_dir)
        ctx = _base_context()
        cache.set("doc1", 1, "Same block text", {"id": 1, "tag": "TXT"}, zone="BODY", key_context=ctx)
        changed = dict(ctx)
        changed["user_prompt_hash"] = "usr-hash-999"
        assert cache.get("doc1", 1, "Same block text", zone="BODY", key_context=changed) is None
    _run_with_cache_dir(_test)


def test_cache_miss_when_allowed_styles_change():
    def _test(cache_dir):
        cache = PredictionCache(cache_dir=cache_dir)
        ctx = _base_context()
        cache.set("doc1", 1, "Same block text", {"id": 1, "tag": "TXT"}, zone="BODY", key_context=ctx)
        changed = dict(ctx)
        changed["allowed_styles_hash"] = "styles-hash-zzz"
        assert cache.get("doc1", 1, "Same block text", zone="BODY", key_context=changed) is None
    _run_with_cache_dir(_test)
