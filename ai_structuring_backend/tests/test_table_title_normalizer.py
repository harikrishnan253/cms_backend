"""Tests for structure-safe table title normalization."""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.table_title_normalizer import TABLE_TITLE_STYLE, normalize_table_titles


def _block(pid, text, tag="TXT", **meta_overrides):
    meta = {"context_zone": "BODY", "tag": tag}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "tag": tag, "metadata": meta}


def test_retags_detected_title_without_reordering():
    blocks = [
        _block(1, "<TAB5.1>", tag="PMI"),
        _block(2, "Table 5.1: Results Summary", tag="TXT"),
        _block(3, "Cell content", tag="TC"),
    ]

    result = normalize_table_titles(blocks)

    assert [b["id"] for b in result] == [1, 2, 3]
    assert result[1]["tag"] == TABLE_TITLE_STYLE
    assert result[1]["metadata"]["tag"] == TABLE_TITLE_STYLE
    assert result[1]["metadata"]["context_zone"] == "TABLE"
    assert result[1]["metadata"]["table_title"] is True


def test_length_preserved_even_with_blank_between_title_and_anchor():
    blocks = [
        _block(1, "Table 1.1: Title", tag="TXT"),
        _block(2, "   ", tag="TXT"),
        _block(3, "<TAB1.1>", tag="PMI"),
        _block(4, "Cell", tag="TC"),
    ]

    result = normalize_table_titles(blocks)

    assert len(result) == 4
    assert [b["id"] for b in result] == [1, 2, 3, 4]
    assert result[0]["tag"] == TABLE_TITLE_STYLE
    assert result[1]["text"] == "   "


def test_id_order_preserved_with_multiple_tables():
    blocks = [
        _block(10, "<TAB1.1>", tag="PMI"),
        _block(11, "Table 1.1: First", tag="TXT"),
        _block(12, "Body", tag="TXT"),
        _block(13, "<TAB1.2>", tag="PMI"),
        _block(14, "Table 1.2: Second", tag="TXT"),
    ]

    result = normalize_table_titles(blocks)

    assert [b["id"] for b in result] == [10, 11, 12, 13, 14]
    assert result[1]["tag"] == TABLE_TITLE_STYLE
    assert result[4]["tag"] == TABLE_TITLE_STYLE


def test_non_table_heading_and_list_metadata_unchanged():
    blocks = [
        _block(
            1,
            "Section Header",
            tag="H1",
            heading_level=1,
            is_list=False,
            list_level=None,
            list_id=None,
        ),
        _block(
            2,
            "Bullet line",
            tag="BL1",
            heading_level=None,
            is_list=True,
            list_level=0,
            list_id=42,
        ),
        _block(3, "<TAB2.1>", tag="PMI"),
        _block(4, "Table 2.1: Data", tag="TXT"),
    ]
    before = copy.deepcopy(blocks)

    result = normalize_table_titles(blocks)

    for idx in (0, 1, 2):
        assert result[idx]["id"] == before[idx]["id"]
        assert result[idx]["tag"] == before[idx]["tag"]
        assert result[idx]["metadata"] == before[idx]["metadata"]

    # Title retag is allowed and expected.
    assert result[3]["tag"] == TABLE_TITLE_STYLE
    assert result[3]["metadata"].get("heading_level") == before[3]["metadata"].get("heading_level")
    assert result[3]["metadata"].get("is_list") == before[3]["metadata"].get("is_list")
    assert result[3]["metadata"].get("list_level") == before[3]["metadata"].get("list_level")
    assert result[3]["metadata"].get("list_id") == before[3]["metadata"].get("list_id")


def test_no_changes_when_no_table_anchors():
    blocks = [
        _block(1, "Normal paragraph", tag="TXT"),
        _block(2, "Another paragraph", tag="TXT"),
    ]
    before = copy.deepcopy(blocks)

    result = normalize_table_titles(blocks)

    assert result == before


def test_matching_number_preferred_without_reordering():
    blocks = [
        _block(1, "Table 1.1: Wrong", tag="TXT"),
        _block(2, "<TAB2.5>", tag="PMI"),
        _block(3, "Table 2.5: Correct", tag="TXT"),
    ]

    result = normalize_table_titles(blocks)

    assert [b["id"] for b in result] == [1, 2, 3]
    assert result[2]["tag"] == TABLE_TITLE_STYLE
    assert result[0]["tag"] == "TXT"


def test_logs_structure_safe_enforcement_once(caplog):
    import logging

    caplog.set_level(logging.INFO)
    blocks = [
        _block(1, "<TAB1.1>", tag="PMI"),
        _block(2, "Table 1.1: Title", tag="TXT"),
    ]

    normalize_table_titles(blocks)

    messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any("TABLE_TITLE_ENFORCED" in m for m in messages)
    assert any("structure_safe=1" in m for m in messages)
