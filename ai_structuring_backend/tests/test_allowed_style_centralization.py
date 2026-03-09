import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.styles.allowed_styles import get_allowed_styles
from backend.app.services.quality_score import score_document
import processor.classifier as classifier_mod


def test_scorer_and_classifier_allowed_styles_match_default():
    canonical = get_allowed_styles()
    classifier_allowed = set(classifier_mod.ALLOWED_STYLES)

    assert len(canonical) == len(classifier_allowed)
    assert canonical == classifier_allowed

    blocks = [
        {
            "id": 1,
            "text": "Sample paragraph",
            "tag": "TXT",
            "confidence": 0.9,
            "metadata": {"context_zone": "BODY"},
        }
    ]
    score, metrics, action = score_document(blocks, None)
    assert metrics["unknown_style_count"] == 0
