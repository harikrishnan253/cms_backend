import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services.style_normalizer import normalize_style


def test_normalize_style_strips_and_collapses_whitespace():
    assert normalize_style("  CN  ") == "CN"
    assert normalize_style("H2   after   H1") == "H2 after H1"


def test_normalize_style_replaces_nbsp():
    nbsp = "\u00A0"
    assert normalize_style(f"CT{nbsp}Title") == "CT Title"


def test_normalize_style_alias_ref_h2():
    assert normalize_style("Ref-H2") == "REFH2"

def test_normalize_style_alias_ref_n_u():
    assert normalize_style("Ref-N") == "REF-N"
    assert normalize_style("Ref-U") == "REF-U"

def test_normalize_style_alias_ref_h2a():
    assert normalize_style("Ref-H2a") == "REFH2a"


def test_normalize_style_vendor_prefix_box_ttl():
    meta = {"box_prefix": "BX4"}
    canonical = normalize_style("EFP_BX-TTL", meta=meta)
    assert canonical == "BX4-TTL"
    assert canonical in {"BX4-TTL"}


def test_normalize_style_vendor_prefix_box_txt():
    meta = {"box_prefix": "BX4"}
    assert normalize_style("EYU_BX-TXT", meta=meta) == "BX4-TXT"

def test_normalize_style_default_box_prefix():
    assert normalize_style("BX-TXT") == "BX4-TXT"

def test_normalize_style_vendor_bx_txt_without_meta():
    assert normalize_style("EFP_BX-TXT") == "BX4-TXT"


def test_normalize_style_strip_illegal_list_suffix():
    assert normalize_style("BX4-TXT-LAST") == "BX4-TXT"


def test_normalize_style_preserves_nested_list_suffixes():
    assert normalize_style("BL2-MID") == "BL2-MID"
    assert normalize_style("BL2-LAST") == "BL2-LAST"
    assert normalize_style("TBL3-MID") == "TBL3-MID"


def test_normalize_style_preserves_prefixed_nested_list_suffixes():
    assert normalize_style("KT-BL2-MID") == "KT-BL2-MID"
    assert normalize_style("KT-BL2-LAST") == "KT-BL2-LAST"
    assert normalize_style("BX4-NL2-MID") == "BX4-NL2-MID"


def test_corpus_aliases_from_tagged_zip_samples():
    assert normalize_style("BulletList1first") == "BL-FIRST"
    assert normalize_style("BulletList1last") == "BL-LAST"
    assert normalize_style("NumberList1last") == "NL-LAST"
    assert normalize_style("BulletList2") == "BL2-MID"
    assert normalize_style("BulletList2last") == "BL2-LAST"
    assert normalize_style("EOCREF") == "REF-N"
    assert normalize_style("COKTL") == "CO_KTL"
    assert normalize_style("NBX1-TXT-FLUSH") == "NBX-TXT-FLUSH"


# -----------------------------------------------------------------------
# Task-2 alias mappings: DIALOGUE, CJC-NGN-BL-LAST, ANS-UL, ANS-NL
# -----------------------------------------------------------------------

def test_normalize_style_dialogue_alias():
    """DIALOGUE is an alias for DIA-MID."""
    assert normalize_style("DIALOGUE") == "DIA-MID"


def test_normalize_style_cjc_ngn_bl_last_alias():
    """CJC-NGN-BL-LAST is a backward-compat alias for CJC-NN-BL-LAST."""
    assert normalize_style("CJC-NGN-BL-LAST") == "CJC-NN-BL-LAST"


def test_normalize_style_ans_ul_alias():
    """Unsuffixed ANS-UL resolves to ANS-UL-MID deterministically."""
    assert normalize_style("ANS-UL") == "ANS-UL-MID"


def test_normalize_style_ans_nl_alias():
    """Unsuffixed ANS-NL resolves to ANS-NL-MID deterministically."""
    assert normalize_style("ANS-NL") == "ANS-NL-MID"


# -----------------------------------------------------------------------
# Task-8 alias mappings: TUL, TUL-LAST
# -----------------------------------------------------------------------

def test_normalize_style_tul_alias():
    """Unsuffixed TUL resolves to TUL-MID deterministically."""
    assert normalize_style("TUL") == "TUL-MID"


def test_normalize_style_tul_last_alias():
    """TUL-LAST is aliased to TUL-MID (no standalone last variant)."""
    assert normalize_style("TUL-LAST") == "TUL-MID"
