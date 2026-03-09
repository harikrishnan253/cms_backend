import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_table_inference_header_row():
    blocks = [
        {"id": 1, "text": "Header", "metadata": {"context_zone": "TABLE", "is_header_row": True, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "T2"


def test_table_inference_stub_col_heading_text():
    """Stub-col with all-uppercase heading text → T4 (ISS-018)."""
    blocks = [
        {"id": 1, "text": "CAR T-CELLS", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": True}},
    ]
    classifications = [{"id": 1, "tag": "T", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "T4"


def test_table_inference_stub_col_plain_data():
    """Stub-col with plain body data → T, not T4 (ISS-018 fix)."""
    blocks = [
        {"id": 1, "text": "Stub", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": True}},
    ]
    classifications = [{"id": 1, "tag": "T", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "T"


def test_table_inference_body_cell():
    blocks = [
        {"id": 1, "text": "Cell", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "TXT-FLUSH", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "T"


def test_table_footnote_preserved():
    blocks = [
        {"id": 1, "text": "Note: values are approximate", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "TFN"


def test_table_footnote_source_line():
    blocks = [
        {"id": 1, "text": "Source: CDC 2020", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "TFN"


def test_table_footnote_lettered():
    blocks = [
        {"id": 1, "text": "a) Footnote detail", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "TFN"


def test_table_t4_heuristic_short_title_case_low_confidence():
    blocks = [
        {"id": 1, "text": "Risk Factors", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "T", "confidence": 0.55}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "T4"


def test_table_t4_heuristic_avoids_sentence_like_text():
    blocks = [
        {"id": 1, "text": "This value was collected from the trial.", "metadata": {"context_zone": "TABLE", "is_header_row": False, "is_stub_col": False}},
    ]
    classifications = [{"id": 1, "tag": "T", "confidence": 0.55}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T2", "T4", "T", "TFN"})
    assert repaired[0]["tag"] == "T"
