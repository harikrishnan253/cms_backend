from backend.processor.pipeline import _count_tag_fallbacks, _sanitize_classifications, sanitize_tag


def test_sanitize_tag_unknown_falls_back_to_txt_with_multiplier():
    tag, multiplier = sanitize_tag("BULLET_LIST", {"TXT", "H1"})
    assert tag == "TXT"
    assert multiplier == 0.5


def test_sanitize_classification_unknown_tag_sets_metadata_and_reduces_confidence():
    rows = [{"id": 1, "tag": "BULLET_LIST", "confidence": 80}]
    out = _sanitize_classifications(rows, {"TXT", "H1"})
    assert out[0]["tag"] == "TXT"
    assert out[0]["confidence"] == 40
    assert out[0]["metadata"]["fallback_tag_raw"] == "BULLET_LIST"
    assert out[0]["metadata"]["fallback_reason"] == "unknown_style"
    assert out[0]["metadata"]["tag_fallback_from"] == "BULLET_LIST"
    assert out[0]["metadata"]["tag_fallback_reason"] == "unknown_style"
    assert out[0]["meta"]["fallback_tag_raw"] == "BULLET_LIST"
    assert out[0]["meta"]["fallback_reason"] == "unknown_style"


def test_count_tag_fallbacks_counts_unknown_style_repairs():
    rows = [
        {"id": 1, "tag": "BULLET_LIST", "confidence": 80},
        {"id": 2, "tag": "H1", "confidence": 95},
    ]
    out = _sanitize_classifications(rows, {"TXT", "H1"})
    assert _count_tag_fallbacks(out) == 1
