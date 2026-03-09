import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.zones import apply_marker_zones, parse_and_normalize_marker


def test_marker_zone_assignment_front_and_body():
    paragraphs = [
        {"id": 1, "text": "<front-open>", "metadata": {}},
        {"id": 2, "text": "Title", "metadata": {}},
        {"id": 3, "text": "<front-close>", "metadata": {}},
        {"id": 4, "text": "<body-matter-open>", "metadata": {}},
        {"id": 5, "text": "Paragraph 1", "metadata": {}},
        {"id": 6, "text": "<body-matter-close>", "metadata": {}},
    ]

    zoned = apply_marker_zones(paragraphs)

    assert [p["text"] for p in zoned] == ["Title", "Paragraph 1"]
    assert zoned[0]["metadata"]["context_zone"] == "FRONT_MATTER"
    assert zoned[1]["metadata"]["context_zone"] == "BODY"
    assert all("<" not in p["text"] for p in zoned)
    assert all(p["metadata"].get("context_zone") for p in zoned)


def test_legacy_marker_aliases_are_normalized():
    paragraphs = [
        {"id": 1, "text": "<front-open>", "metadata": {}},
        {"id": 2, "text": "Title", "metadata": {}},
        {"id": 3, "text": "<front-close>", "metadata": {}},
        {"id": 4, "text": "<body-open>", "metadata": {}},
        {"id": 5, "text": "Paragraph 1", "metadata": {}},
        {"id": 6, "text": "<body-close>", "metadata": {}},
        {"id": 7, "text": "<back-open>", "metadata": {}},
        {"id": 8, "text": "Reference entry", "metadata": {}},
        {"id": 9, "text": "<back-close>", "metadata": {}},
    ]

    zoned = apply_marker_zones(paragraphs)

    assert [p["text"] for p in zoned] == ["Title", "Paragraph 1", "Reference entry"]
    assert zoned[0]["metadata"]["context_zone"] == "FRONT_MATTER"
    assert zoned[1]["metadata"]["context_zone"] == "BODY"
    assert zoned[2]["metadata"]["context_zone"] == "BACK_MATTER"


def test_canonical_markers_unchanged_behavior():
    paragraphs = [
        {"id": 1, "text": "<body-matter-open>", "metadata": {}},
        {"id": 2, "text": "Body line", "metadata": {}},
        {"id": 3, "text": "<body-matter-close>", "metadata": {}},
    ]

    zoned = apply_marker_zones(paragraphs)

    assert len(zoned) == 1
    assert zoned[0]["text"] == "Body line"
    assert zoned[0]["metadata"]["context_zone"] == "BODY"


def test_marker_paragraphs_removed_from_output():
    paragraphs = [
        {"id": 1, "text": "<body-open>", "metadata": {}},
        {"id": 2, "text": "<float-open>", "metadata": {}},
        {"id": 3, "text": "Figure 1. Something", "metadata": {}},
        {"id": 4, "text": "<float-close>", "metadata": {}},
        {"id": 5, "text": "<body-close>", "metadata": {}},
    ]

    zoned = apply_marker_zones(paragraphs)

    assert [p["id"] for p in zoned] == [3]
    assert zoned[0]["metadata"]["context_zone"] == "FLOAT"
    assert all(p["text"] not in {"<body-open>", "<float-open>", "<float-close>", "<body-close>"} for p in zoned)


def test_marker_only_paragraphs_are_skipped():
    paragraphs = [
        {"id": 1, "text": "<front-open>", "metadata": {}},
        {"id": 2, "text": "<front-close>", "metadata": {}},
        {"id": 3, "text": "<body-matter-open>", "metadata": {}},
        {"id": 4, "text": "<body-matter-close>", "metadata": {}},
        {"id": 5, "text": "<back-matter-open>", "metadata": {}},
        {"id": 6, "text": "<back-matter-close>", "metadata": {}},
        {"id": 7, "text": "<float-open>", "metadata": {}},
        {"id": 8, "text": "<float-close>", "metadata": {}},
    ]
    zoned = apply_marker_zones(paragraphs)
    assert zoned == []


def test_zone_state_transitions_with_markers_and_no_marker_output():
    paragraphs = [
        {"id": 1, "text": "<front-open>", "metadata": {}},
        {"id": 2, "text": "Front title", "metadata": {}},
        {"id": 3, "text": "<front-close>", "metadata": {}},
        {"id": 4, "text": "<body-open>", "metadata": {}},
        {"id": 5, "text": "Body line", "metadata": {}},
        {"id": 6, "text": "<float-open>", "metadata": {}},
        {"id": 7, "text": "Figure 1", "metadata": {}},
        {"id": 8, "text": "<float-close>", "metadata": {}},
        {"id": 9, "text": "Body line 2", "metadata": {}},
        {"id": 10, "text": "<body-close>", "metadata": {}},
    ]
    zoned = apply_marker_zones(paragraphs)
    assert [p["text"] for p in zoned] == ["Front title", "Body line", "Figure 1", "Body line 2"]
    assert [p["metadata"]["context_zone"] for p in zoned] == ["FRONT_MATTER", "BODY", "FLOAT", "BODY"]
    assert all(p["text"] not in {
        "<front-open>", "<front-close>", "<body-matter-open>", "<body-matter-close>",
        "<back-matter-open>", "<back-matter-close>", "<float-open>", "<float-close>",
        "<body-open>", "<body-close>", "<back-open>", "<back-close>"
    } for p in zoned)


def test_underscore_marker_variants_are_normalized():
    paragraphs = [
        {"id": 1, "text": "<front_open>", "metadata": {}},
        {"id": 2, "text": "Front", "metadata": {}},
        {"id": 3, "text": "<front_close>", "metadata": {}},
        {"id": 4, "text": "<body_open>", "metadata": {}},
        {"id": 5, "text": "Body", "metadata": {}},
        {"id": 6, "text": "<float_open>", "metadata": {}},
        {"id": 7, "text": "Float", "metadata": {}},
        {"id": 8, "text": "<float_close>", "metadata": {}},
        {"id": 9, "text": "<body_close>", "metadata": {}},
        {"id": 10, "text": "<back_open>", "metadata": {}},
        {"id": 11, "text": "Back", "metadata": {}},
        {"id": 12, "text": "<back_close>", "metadata": {}},
    ]

    zoned = apply_marker_zones(paragraphs)
    assert [p["text"] for p in zoned] == ["Front", "Body", "Float", "Back"]
    assert [p["metadata"]["context_zone"] for p in zoned] == ["FRONT_MATTER", "BODY", "FLOAT", "BACK_MATTER"]
    assert all(
        p["text"] not in {
            "<front_open>", "<front_close>", "<body_open>", "<body_close>",
            "<back_open>", "<back_close>", "<float_open>", "<float_close>"
        }
        for p in zoned
    )


def test_outside_zone_error_contains_debug_fields():
    paragraphs = [
        {"id": 100, "text": "<body-open>", "metadata": {}},
        {"id": 101, "text": "<body-close>", "metadata": {}},
        {"id": 102, "text": "This paragraph appears after close and should fail.", "metadata": {}},
    ]

    with pytest.raises(ValueError) as exc:
        apply_marker_zones(paragraphs, strict=True)

    msg = str(exc.value)
    assert "Zone parser state error: paragraph outside zone markers." in msg
    assert "id=102" in msg
    assert "text_snippet='This paragraph appears after close and should fail'" in msg
    assert "current_zone=None" in msg
    assert "expected one of" in msg
    assert "<body-matter-open>" in msg


def test_parse_marker_whitespace_alias_normalizes():
    assert parse_and_normalize_marker(" <body-open> ") == "<body-matter-open>"


def test_parse_marker_uppercase_normalizes():
    assert parse_and_normalize_marker("<BODY-MATTER-OPEN>") == "<body-matter-open>"


def test_parse_marker_with_nbsp_detected():
    assert parse_and_normalize_marker("<body-matter-open>\u00A0") == "<body-matter-open>"


def test_parse_marker_non_marker_text_returns_none():
    assert parse_and_normalize_marker("<not a marker> extra") is None


def test_no_markers_defaults_without_exception():
    paragraphs = [
        {"id": 1, "text": "First paragraph", "metadata": {}},
        {"id": 2, "text": "Second paragraph", "metadata": {}},
    ]
    zoned = apply_marker_zones(paragraphs)
    assert len(zoned) == 2
    assert zoned[0]["metadata"]["context_zone"] == "BODY_MATTER"
    assert zoned[1]["metadata"]["context_zone"] == "BODY_MATTER"


def test_recovery_when_markers_exist_but_first_open_missing():
    paragraphs = [
        {"id": 1, "text": "Orphan content before markers", "metadata": {}},
        {"id": 2, "text": "<front-open>", "metadata": {}},
        {"id": 3, "text": "Front content", "metadata": {}},
        {"id": 4, "text": "<front-close>", "metadata": {}},
    ]

    zoned = apply_marker_zones(paragraphs)
    assert [p["id"] for p in zoned] == [1, 3]
    assert zoned[0]["metadata"]["context_zone"] == "BODY_MATTER"
    assert zoned[1]["metadata"]["context_zone"] == "FRONT_MATTER"


def test_recovery_strict_mode_still_raises():
    paragraphs = [
        {"id": 1, "text": "Orphan content before markers", "metadata": {}},
        {"id": 2, "text": "<front-open>", "metadata": {}},
    ]

    with pytest.raises(ValueError):
        apply_marker_zones(paragraphs, strict=True)
