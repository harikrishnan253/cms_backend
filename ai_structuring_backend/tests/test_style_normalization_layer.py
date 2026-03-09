import pytest

from backend.app.styles.allowed_styles import get_allowed_styles
from backend.app.styles.normalization import normalize_style
from backend.app.services.quality_score import score_document


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" Ref-H1 ", "REFH1"),
        ("T--DIR", "T"),
        ("Cn", "CN"),
    ],
)
def test_known_aliases_normalize_to_allowed_styles(raw: str, expected: str):
    allowed = get_allowed_styles()
    normalized = normalize_style(raw, doc_type=None)
    assert normalized == expected
    assert normalized in allowed


def test_separator_cleanup_without_case_forcing():
    # Styles are case-sensitive in this repo; do not auto-uppercases unknowns.
    assert normalize_style("cn", doc_type=None) == "cn"
    assert normalize_style("APX__TXT--FLUSH", doc_type=None) == "APX-TXT-FLUSH"


def test_unknown_style_still_fails_scoring_after_normalization():
    allowed = get_allowed_styles()
    blocks = [
        {
            "id": 1,
            "text": "Unknown tag block",
            "tag": normalize_style("ZZZ__UNKNOWN", doc_type=None),
            "confidence": 0.99,
            "metadata": {"context_zone": "BODY"},
        }
    ]
    score, metrics, action = score_document(blocks, allowed)
    assert isinstance(score, int)
    assert action == "REVIEW"
    assert metrics["unknown_style_count"] == 1
    assert metrics["unknown_style_counts"]["ZZZ-UNKNOWN"] == 1
