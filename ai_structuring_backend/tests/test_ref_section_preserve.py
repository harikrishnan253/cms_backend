import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_ref_section_preserves_sr_tag():
    blocks = [
        {"id": 1, "text": "Suggested Readings", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "Some reference entry", "metadata": {"context_zone": "BACK_MATTER", "list_kind": "unordered", "list_position": "FIRST"}},
        {"id": 3, "text": "Next reference entry", "metadata": {"context_zone": "BACK_MATTER", "list_kind": "unordered", "list_position": "MID"}},
        {"id": 4, "text": "Chapter Title", "metadata": {"context_zone": "BODY"}},
    ]

    classifications = [
        {"id": 1, "tag": "SRH1", "confidence": 99},
        {"id": 2, "tag": "SR", "confidence": 99},
        {"id": 3, "tag": "SR", "confidence": 99},
        {"id": 4, "tag": "H1", "confidence": 99},
    ]

    repaired = validate_and_repair(
        classifications,
        blocks,
        preserve_lists=True,
        preserve_marker_pmi=True,
    )

    tags = [r["tag"] for r in repaired]
    assert tags[1] == "SR"
    assert tags[2] == "SR"
    assert tags[0] == "SRH1"
