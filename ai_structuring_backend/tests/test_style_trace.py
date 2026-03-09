"""Tests for the STYLE_TAG_TRACE diagnostics module."""

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.style_trace import emit_style_tag_trace


# ---------------------------------------------------------------------------
# Tiny fixture: 8 blocks mimicking a small chapter fragment.
# ---------------------------------------------------------------------------
BLOCKS = [
    {
        "id": 1,
        "text": "<cn>Chapter 1",
        "metadata": {"context_zone": "FRONT_MATTER", "has_numbering": False, "has_bullet": False, "has_xml_list": False},
    },
    {
        "id": 2,
        "text": "<ct>Introduction to Nursing",
        "metadata": {"context_zone": "FRONT_MATTER", "has_numbering": False, "has_bullet": False, "has_xml_list": False},
    },
    {
        "id": 3,
        "text": "<h1>Overview of Key Concepts in Modern Healthcare Practices and Evidence-Based Interventions",
        "metadata": {"context_zone": "BODY", "has_numbering": False, "has_bullet": False, "has_xml_list": False},
    },
    {
        "id": 4,
        "text": "Heart failure is a clinical syndrome.",
        "metadata": {"context_zone": "BODY", "has_numbering": False, "has_bullet": False, "has_xml_list": False},
    },
    {
        "id": 5,
        "text": "• Orthopnea",
        "metadata": {"context_zone": "BODY", "has_numbering": False, "has_bullet": True, "has_xml_list": False, "list_kind": "bullet", "list_position": "FIRST"},
    },
    {
        "id": 6,
        "text": "• Dyspnea on exertion",
        "metadata": {"context_zone": "BODY", "has_numbering": False, "has_bullet": True, "has_xml_list": False, "list_kind": "bullet", "list_position": "LAST"},
    },
    {
        "id": 7,
        "text": "<note>",
        "metadata": {"context_zone": "BOX_NBX", "has_numbering": False, "has_bullet": False, "has_xml_list": False, "box_type": "note"},
    },
    {
        "id": 8,
        "text": "References",
        "metadata": {"context_zone": "BACK_MATTER", "has_numbering": False, "has_bullet": False, "has_xml_list": False},
    },
]

CLASSIFICATIONS = [
    {"id": 1, "tag": "CN", "confidence": 0.95},
    {"id": 2, "tag": "CT", "confidence": 0.95},
    {"id": 3, "tag": "H1", "confidence": 0.92},
    {"id": 4, "tag": "TXT-FLUSH", "confidence": 0.88},
    {"id": 5, "tag": "BL-FIRST", "confidence": 0.90},
    {"id": 6, "tag": "BL-LAST", "confidence": 0.90},
    {"id": 7, "tag": "PMI", "confidence": 0.99},
    {"id": 8, "tag": "REFH1", "confidence": 0.95},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_trace_disabled_by_default(monkeypatch):
    """When STYLE_TRACE is not set, emit returns None and logs nothing."""
    monkeypatch.delenv("STYLE_TRACE", raising=False)
    result = emit_style_tag_trace("test.docx", BLOCKS, CLASSIFICATIONS)
    assert result is None


def test_trace_produces_valid_event(monkeypatch, caplog):
    """With STYLE_TRACE=1 the function returns a well-formed trace dict
    and emits exactly one INFO log line containing the JSON payload."""
    monkeypatch.setenv("STYLE_TRACE", "1")

    with caplog.at_level(logging.INFO, logger="processor.style_trace"):
        trace = emit_style_tag_trace("test.docx", BLOCKS, CLASSIFICATIONS)

    assert trace is not None

    # Top-level keys
    assert trace["event"] == "STYLE_TAG_TRACE"
    assert trace["file_name"] == "test.docx"
    assert trace["total_blocks"] == len(BLOCKS)

    # Style counts – every classification tag appears
    for clf in CLASSIFICATIONS:
        assert clf["tag"] in trace["style_counts"]

    # List diagnostics: 2 bullets detected, 2 list-style tags applied
    assert trace["list_detected_count"] == 2
    assert trace["list_style_applied_count"] == 2

    # Marker tokens: <cn>, <ct>, <h1>, <note> should all be counted
    markers = trace["marker_token_counts"]
    assert markers.get("<cn>", 0) >= 1
    assert markers.get("<ct>", 0) >= 1
    assert markers.get("<h1>", 0) >= 1
    assert markers.get("<note>", 0) >= 1

    # Zone counts
    zones = trace["zone_counts"]
    assert zones.get("FRONT_MATTER", 0) == 2
    assert zones.get("BODY", 0) == 4
    assert zones.get("BACK_MATTER", 0) == 1
    assert zones.get("BOX_NBX", 0) == 1

    # Log line is parseable JSON
    trace_log_lines = [r for r in caplog.records if "STYLE_TAG_TRACE" in r.message]
    assert len(trace_log_lines) == 1
    # The JSON payload starts after "STYLE_TAG_TRACE "
    payload_str = trace_log_lines[0].message.split("STYLE_TAG_TRACE ", 1)[1]
    parsed = json.loads(payload_str)
    assert parsed["event"] == "STYLE_TAG_TRACE"


def test_text_truncation(monkeypatch):
    """No example snippet exceeds 63 chars (60 + '...' suffix)."""
    monkeypatch.setenv("STYLE_TRACE", "1")
    trace = emit_style_tag_trace("test.docx", BLOCKS, CLASSIFICATIONS)
    assert trace is not None

    max_len = 60 + len("...")
    for examples in trace["style_examples"].values():
        for snippet in examples:
            assert len(snippet) <= max_len

    for snippet in trace["list_detected_examples"]:
        assert len(snippet) <= max_len

    for examples in trace["marker_token_examples"].values():
        for snippet in examples:
            assert len(snippet) <= max_len


def test_example_cap_respected(monkeypatch):
    """Even with many blocks of the same style, at most 10 examples are kept."""
    monkeypatch.setenv("STYLE_TRACE", "1")

    many_blocks = [
        {"id": i, "text": f"Paragraph {i}", "metadata": {"context_zone": "BODY", "has_numbering": False, "has_bullet": False, "has_xml_list": False}}
        for i in range(50)
    ]
    many_clfs = [{"id": i, "tag": "TXT", "confidence": 0.85} for i in range(50)]

    trace = emit_style_tag_trace("big.docx", many_blocks, many_clfs)
    assert trace is not None
    assert len(trace["style_examples"]["TXT"]) == 10


def test_no_full_paragraph_text_in_log(monkeypatch, caplog):
    """The log message must never contain the full text of a paragraph
    longer than the snippet limit."""
    monkeypatch.setenv("STYLE_TRACE", "1")
    long_text = "A" * 200
    blocks = [
        {"id": 1, "text": long_text, "metadata": {"context_zone": "BODY", "has_numbering": False, "has_bullet": False, "has_xml_list": False}},
    ]
    clfs = [{"id": 1, "tag": "TXT", "confidence": 0.85}]

    with caplog.at_level(logging.INFO, logger="processor.style_trace"):
        emit_style_tag_trace("long.docx", blocks, clfs)

    for record in caplog.records:
        assert long_text not in record.message
