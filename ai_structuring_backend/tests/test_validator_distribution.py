import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_validator_logs_tag_distribution(caplog):
    blocks = [
        {"id": 1, "text": "Figure 1. Something", "metadata": {"context_zone": "FLOATS"}},
        {"id": 2, "text": "Regular text", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "FIG", "confidence": 0.8},
        {"id": 2, "tag": "NOT-A-STYLE", "confidence": 0.8},
    ]
    with caplog.at_level("INFO"):
        _ = validate_and_repair(classifications, blocks, allowed_styles={"FIG-LEG", "TXT"})

    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "TAG_DISTRIBUTION_BEFORE" in msgs
    assert "TAG_DISTRIBUTION_AFTER" in msgs
    assert "TAG_COERCIONS_TOP" in msgs


def test_validator_fail_fast_when_llm_required():
    blocks = [{"id": 1, "text": "Unknown", "metadata": {"context_zone": "BODY"}}]
    classifications = [{"id": 1, "tag": "NOT-A-STYLE", "confidence": 0.8}]
    with pytest.raises(ValueError):
        validate_and_repair(classifications, blocks, allowed_styles={"TXT"}, llm_required=True)

