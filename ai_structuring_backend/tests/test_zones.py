import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.zones import apply_marker_zones


def test_alias_body_open_close_are_accepted():
    paragraphs = [
        {"id": 1, "text": "<body-open>", "metadata": {}},
        {"id": 2, "text": "Paragraph 1", "metadata": {}},
        {"id": 3, "text": "<body-close>", "metadata": {}},
    ]
    zoned = apply_marker_zones(paragraphs)
    assert len(zoned) == 1
    assert zoned[0]["text"] == "Paragraph 1"
    assert zoned[0]["metadata"]["context_zone"] == "BODY"


def test_content_before_first_marker_recovers_to_body():
    paragraphs = [
        {"id": 1, "text": "Orphan paragraph", "metadata": {}},
        {"id": 2, "text": "<front-open>", "metadata": {}},
        {"id": 3, "text": "Front paragraph", "metadata": {}},
        {"id": 4, "text": "<front-close>", "metadata": {}},
    ]
    stats = {}
    zoned = apply_marker_zones(paragraphs, strict=False, stats=stats)
    assert [p["id"] for p in zoned] == [1, 3]
    assert zoned[0]["metadata"]["context_zone"] == "BODY_MATTER"
    assert zoned[1]["metadata"]["context_zone"] == "FRONT_MATTER"
    assert stats.get("zone_recoveries", 0) == 1


def test_unknown_marker_does_not_crash():
    paragraphs = [
        {"id": 1, "text": "<body-open>", "metadata": {}},
        {"id": 2, "text": "<mystery-open>", "metadata": {}},  # unknown marker token, treated as text
        {"id": 3, "text": "Body paragraph", "metadata": {}},
        {"id": 4, "text": "<body-close>", "metadata": {}},
    ]
    zoned = apply_marker_zones(paragraphs)
    assert len(zoned) == 2
    assert zoned[0]["id"] == 2
    assert zoned[0]["metadata"]["context_zone"] == "BODY"
    assert zoned[1]["id"] == 3
    assert zoned[1]["metadata"]["context_zone"] == "BODY"


def test_float_open_close_state_machine():
    paragraphs = [
        {"id": 1, "text": "<body-open>", "metadata": {}},
        {"id": 2, "text": "Body para", "metadata": {}},
        {"id": 3, "text": "<float-open>", "metadata": {}},
        {"id": 4, "text": "<float-open>", "metadata": {}},  # duplicate open, ignored
        {"id": 5, "text": "Figure legend", "metadata": {}},
        {"id": 6, "text": "<float-close>", "metadata": {}},
        {"id": 7, "text": "<float-close>", "metadata": {}},  # close without active float, ignored
        {"id": 8, "text": "Body para 2", "metadata": {}},
        {"id": 9, "text": "<body-close>", "metadata": {}},
    ]
    zoned = apply_marker_zones(paragraphs)
    assert [p["id"] for p in zoned] == [2, 5, 8]
    assert [p["metadata"]["context_zone"] for p in zoned] == ["BODY", "FLOAT", "BODY"]
