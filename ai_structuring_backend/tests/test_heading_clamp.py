import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_h4_h5_clamped_to_h3():
    blocks = [
        {"id": 1, "text": "Head", "metadata": {"context_zone": "BODY"}},
        {"id": 2, "text": "Sub", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "H4", "confidence": 0.8},
        {"id": 2, "tag": "H5", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"})
    assert repaired[0]["tag"] == "H3"
    assert repaired[1]["tag"] == "H3"


def test_h3_without_h2_becomes_h2():
    blocks = [
        {"id": 1, "text": "Sub", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "H3", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"})
    assert repaired[0]["tag"] == "H2"


def test_h2_without_h1_becomes_h1():
    blocks = [
        {"id": 1, "text": "Sub", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "H2", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "H3", "TXT"})
    assert repaired[0]["tag"] == "H1"


def test_trusted_tags_preserved():
    blocks = [
        {"id": 1, "text": "Head", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "H4", "confidence": 0.95}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H1", "H2", "H3", "H4", "TXT"})
    assert repaired[0]["tag"] == "H4"
