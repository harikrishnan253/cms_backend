import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair
from backend.app.services.reference_zone import detect_reference_zone


def test_reference_zone_ul_to_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "Smith et al. 2019. Journal.", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 3, "text": "Doe et al. 2020. Journal.", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "UL-FIRST", "confidence": 0.8},
        {"id": 3, "tag": "UL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-U", "REF-N", "REF-TXT", "H1"})
    assert repaired[1]["tag"] == "REF-N"
    assert repaired[2]["tag"] == "REF-N"


def test_reference_zone_bullet_entry_to_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "• Smith et al. 2019. Journal.", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "UL-FIRST", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-U", "REF-N", "H1"})
    assert repaired[1]["tag"] == "REF-U"


def test_reference_zone_numbered_to_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "1. Smith et al. 2019.", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "BL-FIRST", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_bracket_numbered_to_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "[12] Doe et al. 2020.", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "REF-TXT", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_citation_density_early_no_trigger():
    blocks = []
    for i in range(40):
        text = f"{i+1}. Smith et al. 2019." if i < 12 else f"Body para {i}"
        blocks.append({"id": i + 1, "text": text, "metadata": {}})
    ref_ids, trigger, start_idx = detect_reference_zone(blocks)
    assert trigger == "none"
    assert start_idx is None
    assert len(ref_ids) == 0


def test_reference_zone_citation_density_late_trigger():
    blocks = []
    for i in range(60):
        text = f"Body para {i}"
        if i >= 45:
            text = f"{i+1}. Smith et al. 2019."
        blocks.append({"id": i + 1, "text": text, "metadata": {}})
    ref_ids, trigger, start_idx = detect_reference_zone(blocks)
    assert trigger == "citation_density"
    assert start_idx is not None
    assert start_idx >= 42
    assert len(ref_ids) > 0


def test_reference_zone_annotated_bibliography_heading_trigger():
    blocks = [
        {"id": 1, "text": "Body paragraph", "metadata": {}},
        {"id": 2, "text": "<Ref-H1>Annotated Bibliography", "metadata": {}},
        {"id": 3, "text": "Smith AB, Jones C. Journal. 2020;10:1-5.", "metadata": {}},
        {"id": 4, "text": "Doe D, Roe E. N Engl J Med 2021;12:6-8.", "metadata": {}},
        {"id": 5, "text": "Lee F, Kim G. doi:10.1000/test.123", "metadata": {}},
    ]
    ref_ids, trigger, start_idx = detect_reference_zone(blocks)
    assert trigger == "heading_match"
    assert start_idx == 1
    assert ref_ids == {2, 3, 4, 5}
