import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_reference_zone_numbered_to_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "1. Smith et al. 2019.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "UL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_unnumbered_to_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "Scholle SH et al. 2019. Journal.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "BL-FIRST", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-U"


def test_reference_zone_author_line_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "Doe J, Smith A. Title.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-U"


def test_reference_zone_numbered_bullet_to_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "1. • Some ref", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_non_reference_sentence_unchanged():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "This chapter discusses methods.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "TXT", "H1"})
    assert repaired[1]["tag"] == "TXT"


def test_reference_zone_bracket_numbered_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "[12] Doe et al. 2020.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "UL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_paren_numbered_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "(12) Doe et al. 2020.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_numbered_paren_suffix_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "12) Doe et al. 2020.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_plain_number_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "12 Doe et al. 2020.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_bullet_number_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "• 12 Doe et al. 2020.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "UL-MID", "confidence": 0.8},
        {"id": 2, "tag": "UL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_ul_to_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "(2) Author. Title.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "UL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"
    assert not repaired[1]["tag"].startswith(("UL-", "BL-"))


def test_reference_zone_bullet_entry_to_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "• Author. Title.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "UL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-U"


def test_reference_zone_heading_ref_h2():
    blocks = [
        {"id": 1, "text": "<Ref-H2> References", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H2", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REFH2"})
    assert repaired[0]["tag"] == "REFH2"


def test_reference_zone_three_digit_numbered_to_ref_n():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "551. Author et al. 2020.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.7},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-N"


def test_reference_zone_em_dash_bullet_to_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "— Author. Title.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "BL-MID", "confidence": 0.7},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-U"


def test_reference_zone_bl_mid_maps_to_ref_u():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"is_reference_zone": True}},
        {"id": 2, "text": "Author. Title.", "metadata": {"is_reference_zone": True}},
    ]
    classifications = [
        {"id": 1, "tag": "H1", "confidence": 0.95},
        {"id": 2, "tag": "BL-MID", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "REF-U", "H1"})
    assert repaired[1]["tag"] == "REF-U"
    assert not repaired[1]["tag"].startswith(("UL-", "BL-"))


def test_ref_marker_section_coerces_entries_and_stops_before_tables():
    blocks = [
        {"id": 1, "text": "<REF>REFERENCES", "metadata": {}},
        {"id": 2, "text": "World Health Organization. Breastfeeding recommendations. https://www.who.int/", "metadata": {}},
        {"id": 3, "text": "Meek JY, Noble L. Policy Statement. Pediatrics. 2022.", "metadata": {}},
        {"id": 4, "text": "CDC Breastfeeding Topic at: https://www.cdc.gov/breastfeeding/", "metadata": {}},
        {"id": 5, "text": "Table 6.1 Clinical Resources", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "TXT", "confidence": 0.7},
        {"id": 2, "tag": "BL-MID", "confidence": 0.7},
        {"id": 3, "tag": "BL-MID", "confidence": 0.7},
        {"id": 4, "tag": "TXT", "confidence": 0.7},
        {"id": 5, "tag": "T1", "confidence": 0.95},
    ]
    repaired = validate_and_repair(
        classifications,
        blocks,
        allowed_styles={"REFH1", "REF-N", "REF-U", "T1", "TXT"},
    )
    assert repaired[0]["tag"] == "REFH1"
    assert repaired[1]["tag"] == "REF-N"
    assert repaired[2]["tag"] == "REF-N"
    assert repaired[3]["tag"] == "REF-N"
    assert repaired[4]["tag"] == "T1"


# ===================================================================
# List-preservation guard: reference-zone entries not coerced by
# enforce_list_hierarchy_from_word_xml()
# ===================================================================

def test_list_preservation_skips_is_reference_zone():
    """SR entry with is_reference_zone=True survives list-preservation pass."""
    from processor.list_preservation import enforce_list_hierarchy_from_word_xml

    blocks = [
        {"id": 1, "text": "References", "metadata": {"context_zone": "BODY"}},
        {
            "id": 2,
            "text": "Smith, J. (2020). A title.",
            "metadata": {
                "context_zone": "BODY",
                "is_reference_zone": True,
                "xml_list_level": 0,
                "xml_num_id": 1,
            },
        },
    ]
    clfs = [
        {"id": 1, "tag": "SRH1", "confidence": 0.95},
        {"id": 2, "tag": "SR", "confidence": 0.88},
    ]
    result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
    assert result[1]["tag"] == "SR"
    assert "list_preserved" not in result[1]


def test_list_preservation_skips_context_zone_reference():
    """REF-N entry with context_zone=REFERENCE survives list-preservation pass."""
    from processor.list_preservation import enforce_list_hierarchy_from_word_xml

    blocks = [
        {
            "id": 1,
            "text": "Jones, A. (2019). Another title.",
            "metadata": {
                "context_zone": "REFERENCE",
                "xml_list_level": 0,
                "xml_num_id": 2,
            },
        },
    ]
    clfs = [{"id": 1, "tag": "REF-N", "confidence": 0.85}]
    result = enforce_list_hierarchy_from_word_xml(blocks, clfs)
    assert result[0]["tag"] == "REF-N"
    assert "list_preserved" not in result[0]
