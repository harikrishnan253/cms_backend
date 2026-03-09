import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_marker_bl_remains_pmi_with_markers():
    blocks = [
        {"id": 1, "text": "Heading", "metadata": {"context_zone": "BODY"}},
        {"id": 2, "text": "<BL>", "metadata": {"context_zone": "BODY"}},
        {"id": 3, "text": "• First", "metadata": {"context_zone": "BODY", "list_kind": "bullet", "list_position": "FIRST"}},
        {"id": 4, "text": "• Second", "metadata": {"context_zone": "BODY", "list_kind": "bullet", "list_position": "MID"}},
    ]

    classifications = [
        {"id": 1, "tag": "H1", "confidence": 99},
        {"id": 2, "tag": "TXT", "confidence": 99},
        {"id": 3, "tag": "BL-FIRST", "confidence": 99},
        {"id": 4, "tag": "BL-MID", "confidence": 99},
    ]

    repaired = validate_and_repair(
        classifications,
        blocks,
        preserve_lists=True,
        preserve_marker_pmi=True,
    )

    tags = [r["tag"] for r in repaired]
    assert tags == ["H1", "PMI", "BL-FIRST", "BL-MID"]
