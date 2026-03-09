import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_h2_without_h1_downgrades():
    blocks = [
        {"id": 1, "text": "Subhead", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "H2", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "TXT"})
    assert repaired[0]["tag"] == "H1"


def test_h3_without_h2_downgrades():
    blocks = [
        {"id": 1, "text": "Head", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "H3", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"})
    assert repaired[0]["tag"] == "H2"


def test_heading_jump_clamped_or_txt():
    blocks = [
        {"id": 1, "text": "Top", "metadata": {"context_zone": "BODY"}},
        {"id": 2, "text": "Jump", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.9},
        {"id": 2, "tag": "H3", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"})
    assert repaired[1]["tag"] == "H2"


def test_low_confidence_downgrades_to_txt():
    blocks = [
        {"id": 1, "text": "Subhead", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "H2", "confidence": 0.6}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "TXT"})
    assert repaired[0]["tag"] == "TXT"
