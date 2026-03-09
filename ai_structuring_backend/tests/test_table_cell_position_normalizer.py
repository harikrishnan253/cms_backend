import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_NORMALIZER_PATH = ROOT / "backend" / "processor" / "table_cell_position_normalizer.py"

# Load the normalizer directly by file path to avoid importing the full
# processor package (which depends on optional heavy deps like google-genai).
_spec = importlib.util.spec_from_file_location(
    "table_cell_position_normalizer", _NORMALIZER_PATH
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
normalize_table_cell_positions = _mod.normalize_table_cell_positions


def _block(bid, row, cell, *, has_xml_list=False, text="x"):
    return {
        "id": bid,
        "text": text,
        "metadata": {
            "context_zone": "TABLE",
            "table_index": 0,
            "row_index": row,
            "cell_index": cell,
            "para_in_cell": 0,
            "has_xml_list": has_xml_list,
            "has_bullet": False,
            "has_numbering": False,
        },
    }


def _cell_block(bid, row, cell, para, *, has_xml_list=False, has_bullet=False, text="x"):
    """Block with explicit para_in_cell for multi-paragraph cell tests."""
    return {
        "id": bid,
        "text": text,
        "metadata": {
            "context_zone": "TABLE",
            "table_index": 0,
            "row_index": row,
            "cell_index": cell,
            "para_in_cell": para,
            "has_xml_list": has_xml_list,
            "has_bullet": has_bullet,
            "has_numbering": False,
        },
    }


# ---------------------------------------------------------------------------
# ENA CH04 publisher-style preservation tests
# Goal: TB and TCH1 must never be re-labelled to generic T/T2/TBL-* variants.
# ---------------------------------------------------------------------------

def test_plain_table_body_cell_stays_tb():
    """A single TB-tagged table body paragraph must never be relabelled."""
    blocks = [_block(1, 0, 0)]
    clfs = [{"id": 1, "tag": "TB", "confidence": 90}]
    out = normalize_table_cell_positions(clfs, blocks)
    assert out[0]["tag"] == "TB"


def test_table_column_heading_stays_tch1():
    """A TCH1-tagged column heading must not be relabelled to T2 or any generic style."""
    blocks = [_block(1, 0, 0)]
    clfs = [{"id": 1, "tag": "TCH1", "confidence": 90}]
    out = normalize_table_cell_positions(clfs, blocks)
    assert out[0]["tag"] == "TCH1"


def test_tb_list_cell_not_promoted_to_tbl_positional():
    """Multiple TB-tagged paragraphs in one cell must stay TB even with list indicators.

    List indicators (has_xml_list) alone must not trigger TBL-FIRST/MID/LAST
    promotion when the cell uses the publisher's TB tag family.
    """
    blocks = [
        _cell_block(1, 0, 0, 0, has_xml_list=True),
        _cell_block(2, 0, 0, 1, has_xml_list=True),
        _cell_block(3, 0, 0, 2, has_xml_list=True),
    ]
    clfs = [
        {"id": 1, "tag": "TB", "confidence": 90},
        {"id": 2, "tag": "TB", "confidence": 90},
        {"id": 3, "tag": "TB", "confidence": 90},
    ]
    out = normalize_table_cell_positions(clfs, blocks)
    tags = {c["id"]: c["tag"] for c in out}
    assert tags[1] == "TB", "first TB must not become TBL-FIRST"
    assert tags[2] == "TB", "middle TB must not become TBL-MID"
    assert tags[3] == "TB", "last TB must not become TBL-LAST"


def test_mixed_cell_with_tb_prevents_t4_promotion():
    """If a cell contains any publisher-specific style (TB), co-resident
    T-family paragraphs must NOT be promoted to TBL-FIRST/LAST.

    This is the primary regression test for the ENA CH04 over-conversion bug
    where cells with mixed TB+T4 paragraphs (T4 being an LLM mis-classification)
    had their T4 paragraphs wrongly promoted to TBL-FIRST/TBL-LAST.
    """
    blocks = [
        _cell_block(1, 0, 0, 0, has_xml_list=True),   # mis-classified as T4
        _cell_block(2, 0, 0, 1, has_xml_list=True),   # mis-classified as T4
        _cell_block(3, 0, 0, 2, has_xml_list=False),  # correctly tagged TB
    ]
    clfs = [
        {"id": 1, "tag": "T4", "confidence": 70},
        {"id": 2, "tag": "T4", "confidence": 70},
        {"id": 3, "tag": "TB", "confidence": 90},
    ]
    out = normalize_table_cell_positions(clfs, blocks)
    tags = {c["id"]: c["tag"] for c in out}
    assert tags[1] == "T4", "T4 must not be promoted to TBL-FIRST when TB present in cell"
    assert tags[2] == "T4", "T4 must not be promoted to TBL-LAST when TB present in cell"
    assert tags[3] == "TB", "TB must remain unchanged"


def test_tb_in_column_prevents_t4_column_promotion():
    """When a column contains at least one TB-tagged row, contiguous T4
    rows with list indicators in the same column must NOT be promoted to
    TBL-FIRST/MID/LAST.

    The presence of TB in the column signals that the corpus uses the
    publisher's TB tag family for all body cells in that column.
    """
    blocks = [
        _block(1, 0, 0, has_xml_list=True),   # T4, list – would form a run
        _block(2, 1, 0, has_xml_list=True),   # T4, list
        _block(3, 2, 0, has_xml_list=True),   # T4, list
        _block(4, 3, 0, has_xml_list=False),  # TB – publisher style, breaks promotion
    ]
    clfs = [
        {"id": 1, "tag": "T4", "confidence": 70},
        {"id": 2, "tag": "T4", "confidence": 70},
        {"id": 3, "tag": "T4", "confidence": 70},
        {"id": 4, "tag": "TB", "confidence": 90},
    ]
    out = normalize_table_cell_positions(clfs, blocks)
    tags = {c["id"]: c["tag"] for c in out}
    assert tags[1] == "T4", "T4 must not become TBL-FIRST when TB present in column"
    assert tags[2] == "T4", "T4 must not become TBL-MID when TB present in column"
    assert tags[3] == "T4", "T4 must not become TBL-LAST when TB present in column"
    assert tags[4] == "TB", "TB must remain unchanged"


def test_normalizes_contiguous_table_column_list_rows_to_tbl_positions():
    blocks = [
        _block(1, 0, 0, has_xml_list=False, text="Header"),
        _block(2, 1, 0, has_xml_list=True, text="First bullet-like row"),
        _block(3, 2, 0, has_xml_list=True, text="Second bullet-like row"),
        _block(4, 3, 0, has_xml_list=True, text="Third bullet-like row"),
        _block(5, 4, 0, has_xml_list=False, text="Non-list row"),
    ]
    clfs = [
        {"id": 1, "tag": "T2", "confidence": 95},
        {"id": 2, "tag": "T4", "confidence": 70},
        {"id": 3, "tag": "T4", "confidence": 70},
        {"id": 4, "tag": "T4", "confidence": 70},
        {"id": 5, "tag": "T", "confidence": 95},
    ]

    out = normalize_table_cell_positions(clfs, blocks)
    tags = {c["id"]: c["tag"] for c in out}

    assert tags[1] == "T2"
    assert tags[2] == "TBL-FIRST"
    assert tags[3] == "TBL-MID"
    assert tags[4] == "TBL-LAST"
    assert tags[5] == "T"

