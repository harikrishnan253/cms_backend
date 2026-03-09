import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.classifier import GeminiClassifier


class DummyResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = None


def _make_classifier():
    clf = GeminiClassifier.__new__(GeminiClassifier)
    clf.api_timeout = 1
    clf.max_retries = 1
    clf.retry_delay = 0
    clf.retriever = None
    clf.cache = None
    clf.rule_learner = None
    clf.enable_fallback = False
    clf.fallback_model = None
    clf.fallback_input_tokens = 0
    clf.fallback_output_tokens = 0
    clf.fallback_calls = 0
    clf.items_improved = 0
    clf.rule_predictions = 0
    clf.llm_predictions = 0
    clf.total_input_tokens = 0
    clf.total_output_tokens = 0
    clf.total_tokens = 0
    clf._last_token_usage = {}
    clf.model = type(
        "DummyModel",
        (),
        {
            "get_last_usage": staticmethod(lambda: {}),
            "get_token_usage": staticmethod(
                lambda: {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                }
            ),
        },
    )()
    return clf


def test_self_heal_retries_on_invalid():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"BADTAG","confidence":90}]'),
        DummyResp('[{"id":1,"tag":"TXT","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Hello"}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 2
    assert results[0]["tag"] == "TXT"


def test_self_heal_fallback_to_txt_when_still_invalid():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"BADTAG","confidence":90}]'),
        DummyResp('[{"id":1,"tag":"BADTAG2","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Hello"}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 2
    assert results[0]["tag"] == "TXT"


def test_alias_mapping_sk_h_table_to_th_no_downgrade():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"SK_H3","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Header", "metadata": {"context_zone": "TABLE"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "TH3"


def test_alias_mapping_ref_zone_ul_to_ref_n_no_downgrade():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"UL-MID","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [
        {"id": 1, "text": "(2) Author. Title.", "metadata": {"context_zone": "BACK_MATTER", "is_reference_zone": True}}
    ]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "REF-N"


def test_sanitize_junk_prefixed_tag_to_valid_style():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":": FIG-LEG","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Figure legend", "metadata": {"context_zone": "BACK_MATTER"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] in {"FIG-LEG", "REF-N", "REF-U"}


def test_alias_mapping_bibitem_to_ref_u_in_reference_zone():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"BibItem","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Smith J. 2019. Journal.", "metadata": {"is_reference_zone": True}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] in {"REF-U", "REF-N"}


def test_alias_mapping_cout_to_cout1():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"COUT","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Overview", "metadata": {"context_zone": "FRONT_MATTER"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] in {"COUT-1", "COUT-2"}


def test_alias_mapping_efp_box_to_bx4():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"EFP_BX-TXT","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Box text", "metadata": {"context_zone": "BODY", "box_prefix": "BX4"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] in {"BX4-TXT", "TXT"}


def test_alias_mapping_numeric_ttl_in_box_zone_bx1_no_retry():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"1-TTL","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Box heading", "metadata": {"context_zone": "BOX_BX1"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "BX1-TTL"


def test_alias_mapping_numeric_ttl_in_box_zone_bx2_no_retry():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"2-TTL","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Warning", "metadata": {"context_zone": "BOX_BX2"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "BX2-TTL"


def test_alias_mapping_tbl_bl_mid_to_tbl_mid_no_retry():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"TBL-BL-MID","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Item", "metadata": {"context_zone": "TABLE"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "TBL-MID"


def test_alias_mapping_tbl_txt_to_t_no_retry():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"TBL-TXT","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Cell text", "metadata": {"context_zone": "TABLE"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] in {"T", "TD"}


def test_alias_mapping_hh_to_h1_no_retry():
    clf = _make_classifier()
    responses = [
        DummyResp('[{"id":1,"tag":"HH","confidence":90}]'),
    ]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    clf._generate_content = _gen

    paragraphs = [{"id": 1, "text": "Heading"}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "H1"


# ===================================================================
# NBX invalid-variant alias normalization (no retry, no FN-* drift)
# ===================================================================

def test_alias_nbx_bl2_first_resolves_no_retry():
    """NBX-BL2-FIRST → NBX-BL2-MID via alias; no LLM retry triggered."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"NBX-BL2-FIRST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Sub-bullet item", "metadata": {"context_zone": "BOX_NBX"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "NBX-BL2-MID"


def test_alias_nbx_bl2_last_resolves_no_retry():
    """NBX-BL2-LAST → NBX-BL2-MID via alias; no LLM retry triggered."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"NBX-BL2-LAST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Sub-bullet last", "metadata": {"context_zone": "BOX_NBX"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "NBX-BL2-MID"


def test_alias_nbx_bl3_first_resolves_no_retry():
    """NBX-BL3-FIRST → NBX-BL2-MID via alias; no LLM retry triggered."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"NBX-BL3-FIRST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Nested bullet", "metadata": {"context_zone": "BOX_NBX"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "NBX-BL2-MID"


def test_alias_nbx_bl3_mid_resolves_no_retry():
    """NBX-BL3-MID → NBX-BL2-MID via alias; no LLM retry triggered."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"NBX-BL3-MID","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Deep sub-bullet", "metadata": {"context_zone": "BOX_NBX"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "NBX-BL2-MID"


def test_alias_nbx_bl3_last_resolves_no_retry():
    """NBX-BL3-LAST → NBX-BL2-MID via alias; no LLM retry triggered."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"NBX-BL3-LAST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Deep sub-bullet last", "metadata": {"context_zone": "BOX_NBX"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "NBX-BL2-MID"


def test_nbx_invalid_never_drifts_to_fn_bl_first():
    """NBX-BL3-FIRST must not be downgraded to FN-BL-FIRST via similarity."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"NBX-BL3-FIRST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Deep bullet", "metadata": {"context_zone": "BOX_NBX"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert results[0]["tag"] != "FN-BL-FIRST"
    assert results[0]["tag"] != "FN-BL-MID"
    assert results[0]["tag"] != "FN-BL-LAST"
    assert results[0]["tag"] == "NBX-BL2-MID"


# ===================================================================
# Task-3/4 new canonical CJC tags in TABLE zone — no retry expected
# ===================================================================

def test_cjc_nn_bl_last_in_table_no_retry():
    """CJC-NN-BL-LAST is a valid TABLE-zone style; classifier must not retry."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"CJC-NN-BL-LAST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Last bullet item", "metadata": {"context_zone": "TABLE"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "CJC-NN-BL-LAST"


def test_cjc_ul_first_in_table_no_retry():
    """CJC-UL-FIRST is a valid TABLE-zone style; classifier must not retry."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"CJC-UL-FIRST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "First unordered item", "metadata": {"context_zone": "TABLE"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "CJC-UL-FIRST"


def test_cjc_ul_last_in_table_no_retry():
    """CJC-UL-LAST is a valid TABLE-zone style; classifier must not retry."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"CJC-UL-LAST","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Last unordered item", "metadata": {"context_zone": "TABLE"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "CJC-UL-LAST"


def test_dialogue_alias_resolves_to_dia_mid_no_retry():
    """DIALOGUE alias resolves to canonical DIA-MID; classifier must not retry."""
    clf = _make_classifier()
    responses = [DummyResp('[{"id":1,"tag":"DIALOGUE","confidence":90}]')]
    calls = {"n": 0}

    def _gen(_prompt):
        r = responses[calls["n"]]; calls["n"] += 1; return r

    clf._generate_content = _gen
    paragraphs = [{"id": 1, "text": "Character spoke.", "metadata": {"context_zone": "BODY"}}]
    results = clf._classify_chunk(paragraphs, "doc", "Academic", "")
    assert calls["n"] == 1
    assert results[0]["tag"] == "DIA-MID"
