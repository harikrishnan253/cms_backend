import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_table_zone_list_mapping():
    blocks = [
        {"id": 1, "text": "• Item", "metadata": {"context_zone": "TABLE"}},
        {"id": 2, "text": "A", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [
        {"id": 1, "tag": "BL-FIRST", "confidence": 0.8},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
    assert repaired[0]["tag"] == "T"
    assert repaired[1]["tag"] == "T"


def test_back_matter_float_without_anchor_downgrades():
    blocks = [
        {"id": 1, "text": "Figure caption", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "Some text", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "FIG-LEG", "confidence": 0.8},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"FIG-LEG", "TXT-FLUSH", "TXT"})
    assert repaired[0]["tag"] == "TXT-FLUSH"


def test_back_matter_float_with_anchor_kept():
    blocks = [
        {"id": 1, "text": "Figure caption", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "Source", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "FIG-LEG", "confidence": 0.8},
        {"id": 2, "tag": "FIG-SRC", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"FIG-LEG", "FIG-SRC"})
    assert repaired[1]["tag"] == "FIG-SRC"


def test_back_matter_table_caption_without_anchor_downgrades():
    blocks = [
        {"id": 1, "text": "Table 1. Title", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "T1", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T1", "TXT-FLUSH"})
    assert repaired[0]["tag"] == "TXT-FLUSH"


def test_back_matter_table_caption_with_anchor_kept():
    blocks = [
        {"id": 1, "text": "Table 1. Title", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "Source: A", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "T1", "confidence": 0.8},
        {"id": 2, "tag": "TSN", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T1", "TSN"})
    assert repaired[0]["tag"] == "T1"


def test_table_zone_bl_mid_to_t():
    blocks = [
        {"id": 1, "text": "Item", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [{"id": 1, "tag": "BL-MID", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
    assert repaired[0]["tag"] == "T"


def test_table_zone_skill_heading_to_t():
    blocks = [
        {"id": 1, "text": "Skill heading", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [{"id": 1, "tag": "SK_H2", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
    assert repaired[0]["tag"] == "T"


def test_table_zone_skill_heading_to_th():
    blocks = [
        {"id": 1, "text": "Skill heading", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [{"id": 1, "tag": "SK_H3", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH3"})
    assert repaired[0]["tag"] == "TH3"


def test_table_zone_tbl_h_to_th():
    blocks = [
        {"id": 1, "text": "Heading", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [{"id": 1, "tag": "TBL-H2", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH2"})
    assert repaired[0]["tag"] == "TH2"


def test_table_zone_sk_h1_to_th1():
    blocks = [{"id": 1, "text": "H1", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "SK_H1", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH1"})
    assert repaired[0]["tag"] == "TH1"


def test_table_zone_sk_h2_to_th2():
    blocks = [{"id": 1, "text": "H2", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "SK_H2", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH2"})
    assert repaired[0]["tag"] == "TH2"


def test_table_zone_sk_h4_to_th4():
    blocks = [{"id": 1, "text": "H4", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "SK_H4", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH4"})
    assert repaired[0]["tag"] == "TH4"


def test_table_zone_sk_h5_to_th5():
    blocks = [{"id": 1, "text": "H5", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "SK_H5", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH5"})
    assert repaired[0]["tag"] == "TH5"


def test_table_zone_sk_h6_to_th6():
    blocks = [{"id": 1, "text": "H6", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "SK_H6", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH6"})
    assert repaired[0]["tag"] == "TH6"


def test_table_zone_tbl_h1_to_th1():
    blocks = [{"id": 1, "text": "H1", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TBL-H1", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH1"})
    assert repaired[0]["tag"] == "TH1"


def test_table_zone_tbl_h5_to_th5():
    blocks = [{"id": 1, "text": "H5", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TBL-H5", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH5"})
    assert repaired[0]["tag"] == "TH5"


def test_table_zone_tbl_h6_to_th6():
    blocks = [{"id": 1, "text": "H6", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TBL-H6", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TH6"})
    assert repaired[0]["tag"] == "TH6"


def test_table_zone_sk_h_fallback_to_t():
    """When TH* not in allowed_styles, fall back to T"""
    blocks = [{"id": 1, "text": "Heading", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "SK_H3", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
    assert repaired[0]["tag"] == "T"


def test_table_zone_tbl_txt_to_td():
    """TBL-TXT should map to TD if TD is in allowed_styles"""
    blocks = [{"id": 1, "text": "Cell text", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TBL-TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TD", "T"})
    assert repaired[0]["tag"] == "TD"


def test_table_zone_tbl_txt_stays_if_td_not_allowed():
    """TBL-TXT should stay if TD not in allowed_styles"""
    blocks = [{"id": 1, "text": "Cell text", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TBL-TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T"})
    # Should fall through to zone-table-text and become T
    assert repaired[0]["tag"] in {"TBL-TXT", "T"}


def test_non_table_zone_sk_h_unchanged():
    """SK_H* should NOT map to TH* outside TABLE zone"""
    blocks = [{"id": 1, "text": "Heading", "metadata": {"context_zone": "BODY"}}]
    classifications = [{"id": 1, "tag": "SK_H2", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"SK_H2", "TH2", "H2"})
    # Should stay as SK_H2 or normalize to H2, but NOT become TH2
    assert repaired[0]["tag"] in {"SK_H2", "H2"}


def test_box_bx4_list_tag_not_downgraded_in_body():
    blocks = [
        {"id": 1, "text": "Item", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "BX4-BL-MID", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"BX4-BL-MID"})
    assert repaired[0]["tag"] == "BX4-BL-MID"


def test_box_bx4_txt_stays_in_body():
    blocks = [
        {"id": 1, "text": "Box text", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "BX4-TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"BX4-TXT"})
    assert repaired[0]["tag"] == "BX4-TXT"


def test_back_matter_fig_leg_maps_to_allowed():
    blocks = [
        {"id": 1, "text": "Figure Legend", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [{"id": 1, "tag": "FIG-LEG", "confidence": 0.8}]
    allowed = {"UNFIG-LEG", "REF-U"}
    repaired = validate_and_repair(classifications, blocks, allowed_styles=allowed)
    assert repaired[0]["tag"] in allowed


def test_back_matter_fig_src_maps_to_allowed():
    blocks = [
        {"id": 1, "text": "Figure Source", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [{"id": 1, "tag": "FIG-SRC", "confidence": 0.8}]
    allowed = {"TSN", "REF-U"}
    repaired = validate_and_repair(classifications, blocks, allowed_styles=allowed)
    assert repaired[0]["tag"] in allowed


def test_back_matter_t1_maps_to_allowed():
    blocks = [
        {"id": 1, "text": "Table title", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [{"id": 1, "tag": "T1", "confidence": 0.8}]
    allowed = {"BM-TTL", "REF-U"}
    repaired = validate_and_repair(classifications, blocks, allowed_styles=allowed)
    assert repaired[0]["tag"] in allowed


def test_back_matter_tfn_maps_to_allowed():
    blocks = [
        {"id": 1, "text": "Table footnote", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [{"id": 1, "tag": "TFN", "confidence": 0.8}]
    allowed = {"TSN", "REF-U"}
    repaired = validate_and_repair(classifications, blocks, allowed_styles=allowed)
    assert repaired[0]["tag"] in allowed


def test_back_matter_bm_ttl_maps_to_allowed():
    blocks = [
        {"id": 1, "text": "Back matter title", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [{"id": 1, "tag": "BM-TTL", "confidence": 0.8}]
    allowed = {"REFH1", "REF-U"}
    repaired = validate_and_repair(classifications, blocks, allowed_styles=allowed)
    assert repaired[0]["tag"] in allowed


def test_list_enforcement_does_not_override_ref_tag():
    blocks = [
        {
            "id": 1,
            "text": "Smith AB, Jones CD. N Engl J Med 2020;10:10-20.",
            "metadata": {"context_zone": "BODY", "list_kind": "unordered", "list_position": "MID"},
        }
    ]
    classifications = [{"id": 1, "tag": "REF-N", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REF-N", "UL-MID", "TXT"})
    assert repaired[0]["tag"] == "REF-N"


def test_list_enforcement_does_not_flip_bl_to_ul_when_ambiguous():
    blocks = [
        {
            "id": 1,
            "text": "Clinical item",
            "metadata": {"context_zone": "BODY", "list_kind": "unordered", "list_position": "MID"},
        }
    ]
    classifications = [{"id": 1, "tag": "BL-MID", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"BL-MID", "UL-MID", "TXT"})
    assert repaired[0]["tag"] == "BL-MID"


def test_inline_h3_marker_overrides_txt_flush():
    blocks = [
        {"id": 1, "text": "<H3>Risk Factors", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [{"id": 1, "tag": "TXT-FLUSH", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H3", "TXT-FLUSH", "TXT"})
    assert repaired[0]["tag"] == "H3"


def test_inline_h3_marker_not_applied_in_table_zone():
    blocks = [
        {"id": 1, "text": "<H3>Table Group", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [{"id": 1, "tag": "T", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"T", "H3"})
    assert repaired[0]["tag"] == "T"


def test_unordered_xml_bullet_maps_to_bl_not_ul():
    blocks = [
        {
            "id": 1,
            "text": "• Orthopnea",
            "metadata": {
                "context_zone": "BODY",
                "list_kind": "unordered",
                "list_position": "MID",
                "has_xml_list": True,
            },
        }
    ]
    classifications = [{"id": 1, "tag": "UL-MID", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"BL-MID", "UL-MID", "TXT"})
    assert repaired[0]["tag"] == "BL-MID"


def test_txt_after_heading_promotes_to_txt_flush():
    blocks = [
        {"id": 1, "text": "<H2>Clinical Presentation", "metadata": {"context_zone": "BODY"}},
        {"id": 2, "text": "Classic manifestations include edema and orthopnea.", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "H2", "confidence": 0.95},
        {"id": 2, "tag": "TXT", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"H2", "TXT", "TXT-FLUSH"})
    assert repaired[1]["tag"] == "TXT-FLUSH"


def test_apx_ref_n_preserved_in_reference_zone():
    blocks = [
        {"id": 1, "text": "References", "metadata": {"context_zone": "BACK_MATTER"}},
        {"id": 2, "text": "Cohn JN, Kowey PR, Whelton PK, et al. Arch Intern Med 2000;160:2429.", "metadata": {"context_zone": "BACK_MATTER"}},
    ]
    classifications = [
        {"id": 1, "tag": "REFH1", "confidence": 0.95},
        {"id": 2, "tag": "APX-REF-N", "confidence": 0.8},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"REFH1", "APX-REF-N", "REF-N", "REF-U"})
    assert repaired[1]["tag"] == "APX-REF-N"


# ---------------------------------------------------------------------------
# TABLE-zone: source vs footnote tagging
# ---------------------------------------------------------------------------

def test_table_zone_source_prefix_maps_to_tsn():
    """TABLE-zone 'Source: ...' line → TSN."""
    blocks = [{"id": 1, "text": "Source: Adapted from Smith (2020)", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TSN"


def test_table_zone_adapted_from_maps_to_tsn():
    """TABLE-zone 'Adapted from ...' attribution line → TSN."""
    blocks = [{"id": 1, "text": "Adapted from WHO Guidelines 2019", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TSN"


def test_table_zone_from_prefix_maps_to_tsn():
    """TABLE-zone 'From ...' attribution line → TSN."""
    blocks = [{"id": 1, "text": "From the 2020 Global Report", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TSN"


def test_table_zone_note_prefix_maps_to_tfn():
    """TABLE-zone 'Note: ...' line → TFN."""
    blocks = [{"id": 1, "text": "Note: All values are approximate", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TFN"


def test_table_zone_symbol_footnote_maps_to_tfn():
    """TABLE-zone '* ...' symbol footnote → TFN."""
    blocks = [{"id": 1, "text": "* Statistically significant (p < 0.05)", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TFN"


def test_table_zone_letter_footnote_maps_to_tfn():
    """TABLE-zone 'a) ...' letter footnote → TFN."""
    blocks = [{"id": 1, "text": "a) Adjusted for age", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TFN"


def test_table_zone_source_priority_over_footnote():
    """TABLE-zone: source check has priority — 'Source: a Adapted ...' → TSN not TFN."""
    blocks = [{"id": 1, "text": "Source: a Adapted from original", "metadata": {"context_zone": "TABLE"}}]
    classifications = [{"id": 1, "tag": "TXT", "confidence": 0.8}]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TSN", "TFN", "T"})
    assert repaired[0]["tag"] == "TSN"
