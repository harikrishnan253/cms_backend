"""Tests for deterministic gating layer (LLM cost optimization)."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.deterministic_gate import (
    classify_deterministic,
    gate_for_llm,
    GateMetrics,
)


def _block(pid, text="Paragraph", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# classify_deterministic — single-block rules
# ===================================================================

class TestClassifyDeterministic:
    # --- Rule 1: empty / whitespace ---
    def test_empty_text(self):
        result = classify_deterministic(_block(1, ""))
        assert result is not None
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-empty"

    def test_whitespace_only(self):
        result = classify_deterministic(_block(1, "   \n\t  "))
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-empty"

    # --- Rule 2: marker token with resolved style ---
    def test_marker_h1_intro(self):
        result = classify_deterministic(_block(1, "<H1-INTRO>Introduction"))
        assert result is not None
        assert result["tag"] == "SP-H1"
        assert result["gate_rule"] == "gate-marker"

    def test_marker_sum_summary(self):
        result = classify_deterministic(_block(1, "<SUM>Summary"))
        assert result is not None
        assert result["tag"] == "EOC-H1"
        assert result["gate_rule"] == "gate-marker"

    def test_marker_h1_references(self):
        result = classify_deterministic(_block(1, "<H1>References"))
        assert result is not None
        assert result["tag"] == "REFH1"
        assert result["gate_rule"] == "gate-marker"

    # --- Rule 3: marker-only → PMI (via resolve_marker_style Rule 4) ---
    def test_marker_only_note(self):
        result = classify_deterministic(_block(1, "<NOTE>"))
        assert result is not None
        assert result["tag"] == "PMI"
        # resolve_marker_style handles marker-only → PMI, so gate-marker fires
        assert result["gate_rule"] == "gate-marker"

    def test_marker_only_body(self):
        result = classify_deterministic(_block(1, "<BODY>  "))
        assert result is not None
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-marker"

    # --- Rule 4: table caption ---
    def test_table_caption(self):
        result = classify_deterministic(_block(1, "Table 1 Results", caption_type="table"))
        assert result["tag"] == "T1"
        assert result["gate_rule"] == "gate-table-caption"

    # --- Rule 5: figure caption ---
    def test_figure_caption(self):
        result = classify_deterministic(_block(1, "Figure 1 Diagram", caption_type="figure"))
        assert result["tag"] == "FIG-LEG"
        assert result["gate_rule"] == "gate-figure-caption"

    # --- Rule 6: source line ---
    def test_source_line(self):
        result = classify_deterministic(_block(1, "Source: WHO 2020", source_line=True))
        assert result["tag"] == "TSN"
        assert result["gate_rule"] == "gate-source-line"

    # --- Rule 7: box marker ---
    def test_box_marker_start(self):
        # <bxs> is a marker token resolved to PMI by marker_rules Rule 4
        result = classify_deterministic(_block(1, "<bxs>", box_marker="start"))
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-marker"

    def test_box_marker_end(self):
        # <bxe> is a marker token resolved to PMI by marker_rules Rule 4
        result = classify_deterministic(_block(1, "<bxe>", box_marker="end"))
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-marker"

    # --- Rule 8: box label ---
    def test_box_label_bx1(self):
        result = classify_deterministic(
            _block(1, "Box 1", box_label="Box 1", context_zone="BOX_BX1")
        )
        assert result["tag"] == "BX1-TYPE"
        assert result["gate_rule"] == "gate-box-label"

    def test_box_label_nbx(self):
        result = classify_deterministic(
            _block(1, "Note", box_label="Note", context_zone="BOX_NBX")
        )
        assert result["tag"] == "NBX-TYPE"
        assert result["gate_rule"] == "gate-box-label"

    def test_box_label_not_in_box_zone(self):
        """box_label outside a BOX_ zone should NOT be gated."""
        result = classify_deterministic(
            _block(1, "Box 1", box_label="Box 1", context_zone="BODY")
        )
        # Should fall through (not gated by box-label rule)
        assert result is None or result.get("gate_rule") != "gate-box-label"

    # --- Rule 9: box title ---
    def test_box_title_nbx(self):
        result = classify_deterministic(
            _block(1, "Important Concepts", box_title="Important Concepts", context_zone="BOX_NBX")
        )
        assert result["tag"] == "NBX-TTL"
        assert result["gate_rule"] == "gate-box-title"

    def test_box_title_bx2(self):
        result = classify_deterministic(
            _block(1, "Case Study", box_title="Case Study", context_zone="BOX_BX2")
        )
        assert result["tag"] == "BX2-TTL"
        assert result["gate_rule"] == "gate-box-title"

    # --- Rule 10: table zone + footnote ---
    def test_table_zone_footnote_dagger(self):
        result = classify_deterministic(
            _block(1, "† p < 0.05", context_zone="TABLE")
        )
        assert result["tag"] == "TFN"
        assert result["gate_rule"] == "gate-table-footnote"

    def test_table_zone_footnote_note(self):
        result = classify_deterministic(
            _block(1, "Note: Values are means", context_zone="TABLE")
        )
        assert result["tag"] == "TFN"
        assert result["gate_rule"] == "gate-table-footnote"

    def test_table_zone_footnote_letter(self):
        result = classify_deterministic(
            _block(1, "a Adjusted for age", context_zone="TABLE")
        )
        assert result["tag"] == "TFN"
        assert result["gate_rule"] == "gate-table-footnote"

    def test_table_zone_footnote_asterisk(self):
        result = classify_deterministic(
            _block(1, "* Statistically significant", context_zone="TABLE")
        )
        assert result["tag"] == "TFN"
        assert result["gate_rule"] == "gate-table-footnote"

    def test_table_zone_footnote_paren_letter(self):
        result = classify_deterministic(
            _block(1, "a) Reference group", context_zone="TABLE")
        )
        assert result["tag"] == "TFN"
        assert result["gate_rule"] == "gate-table-footnote"

    # --- Rule 11: table zone + source ---
    def test_table_zone_source(self):
        result = classify_deterministic(
            _block(1, "Source: Adapted from Smith", context_zone="TABLE")
        )
        assert result["tag"] == "TSN"
        assert result["gate_rule"] == "gate-table-source"

    def test_table_zone_adapted(self):
        result = classify_deterministic(
            _block(1, "Adapted from WHO 2019", context_zone="TABLE")
        )
        assert result["tag"] == "TSN"
        assert result["gate_rule"] == "gate-table-source"

    # --- Rule 12: short token ---
    def test_short_dash(self):
        result = classify_deterministic(_block(1, "—"))
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-short-token"

    def test_short_number(self):
        result = classify_deterministic(_block(1, "42"))
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-short-token"

    def test_short_single_char_letter(self):
        """A single letter should NOT be gated as short-token."""
        result = classify_deterministic(_block(1, "A"))
        # Single letter has isalpha() → True, so short-token rule skips it
        assert result is None or result.get("gate_rule") != "gate-short-token"

    # --- Negative cases: not gated ---
    def test_normal_body_text(self):
        result = classify_deterministic(_block(1, "The results of the study indicate a positive trend."))
        assert result is None

    def test_heading_without_marker(self):
        result = classify_deterministic(_block(1, "Introduction"))
        assert result is None

    def test_long_reference_text(self):
        result = classify_deterministic(
            _block(1, "Smith, J. (2020). A study of methods. Journal of Testing, 15(3), 200-210.")
        )
        assert result is None

    def test_list_item(self):
        result = classify_deterministic(_block(1, "First item in the numbered list"))
        assert result is None

    # --- Confidence values ---
    def test_marker_confidence_99(self):
        result = classify_deterministic(_block(1, "<H1-INTRO>Intro"))
        assert result["confidence"] == 99

    def test_table_zone_footnote_confidence_95(self):
        result = classify_deterministic(_block(1, "† sig", context_zone="TABLE"))
        assert result["confidence"] == 95

    def test_short_token_confidence_90(self):
        result = classify_deterministic(_block(1, "--"))
        assert result["confidence"] == 90

    # --- gated flag ---
    def test_gated_flag_set(self):
        result = classify_deterministic(_block(1, ""))
        assert result["gated"] is True


# ===================================================================
# gate_for_llm — batch gating
# ===================================================================

class TestGateForLlm:
    def test_mixed_blocks(self):
        blocks = [
            _block(1, ""),                                          # gated: empty
            _block(2, "Table 1 Results", caption_type="table"),     # gated: caption
            _block(3, "The study found positive results."),         # LLM
            _block(4, "<NOTE>"),                                    # gated: marker-only
            _block(5, "Another paragraph of body text."),           # LLM
        ]
        gated, llm, metrics = gate_for_llm(blocks)
        assert len(gated) == 3
        assert len(llm) == 2
        gated_ids = {c["id"] for c in gated}
        llm_ids = {b["id"] for b in llm}
        assert gated_ids == {1, 2, 4}
        assert llm_ids == {3, 5}

    def test_all_deterministic(self):
        blocks = [
            _block(1, ""),
            _block(2, "Table 1", caption_type="table"),
            _block(3, "<H1-INTRO>Intro"),
        ]
        gated, llm, metrics = gate_for_llm(blocks)
        assert len(gated) == 3
        assert len(llm) == 0
        assert metrics.gated_count == 3
        assert metrics.llm_count == 0

    def test_all_ambiguous(self):
        blocks = [
            _block(1, "The study results."),
            _block(2, "Another paragraph."),
        ]
        gated, llm, metrics = gate_for_llm(blocks)
        assert len(gated) == 0
        assert len(llm) == 2
        assert metrics.gated_count == 0
        assert metrics.llm_count == 2

    def test_metrics_rules_fired(self):
        blocks = [
            _block(1, ""),
            _block(2, ""),
            _block(3, "Table 1", caption_type="table"),
            _block(4, "Normal text."),
        ]
        _, _, metrics = gate_for_llm(blocks)
        assert metrics.rules_fired["gate-empty"] == 2
        assert metrics.rules_fired["gate-table-caption"] == 1
        assert metrics.total_blocks == 4
        assert metrics.gated_count == 3
        assert metrics.llm_count == 1

    def test_ids_preserved(self):
        blocks = [_block(i, "Normal text.") for i in range(1, 6)]
        blocks[0] = _block(1, "")  # gated
        blocks[3] = _block(4, "<NOTE>")  # gated
        gated, llm, _ = gate_for_llm(blocks)
        assert [c["id"] for c in gated] == [1, 4]
        assert [b["id"] for b in llm] == [2, 3, 5]

    def test_empty_input(self):
        gated, llm, metrics = gate_for_llm([])
        assert gated == []
        assert llm == []
        assert metrics.total_blocks == 0


# ===================================================================
# Integration: deterministic paragraphs never sent to LLM
# ===================================================================

class TestDeterministicNeverSentToLlm:
    def test_gated_blocks_not_in_llm(self):
        """Verify that classify_blocks_with_prompt doesn't send gated blocks to LLM."""
        from processor.classifier import classify_blocks_with_prompt

        blocks = [
            _block(1, ""),                                          # gated
            _block(2, "Table 1 Results", caption_type="table"),     # gated
            _block(3, "Normal body text paragraph."),               # LLM
            _block(4, "<H1-INTRO>Introduction"),                    # gated
            _block(5, "Another body paragraph."),                   # LLM
        ]

        # Mock GeminiClassifier so no real API call happens
        mock_results = [
            {"id": 3, "tag": "TXT", "confidence": 90},
            {"id": 5, "tag": "TXT", "confidence": 88},
        ]
        received_block_ids = []

        with patch("processor.classifier.GeminiClassifier") as MockCls:
            instance = MockCls.return_value
            def fake_classify(llm_blocks, doc_name, doc_type):
                received_block_ids.extend(b["id"] for b in llm_blocks)
                return mock_results
            instance.classify.side_effect = fake_classify
            instance.get_token_usage.return_value = {
                "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                "last_call": {},
                "fallback": {"enabled": False, "model": None, "threshold": 0,
                             "calls": 0, "items_improved": 0,
                             "input_tokens": 0, "output_tokens": 0},
                "estimated_cost_usd": 0.0,
                "rule_based": {"predictions": 0, "llm_predictions": 2,
                               "total_predictions": 2, "rule_coverage": 0.0},
                "combined_input_tokens": 100, "combined_output_tokens": 50,
            }

            results, usage = classify_blocks_with_prompt(
                blocks, "test.docx", "fake-api-key"
            )

        # Gated blocks should NOT have been sent to LLM
        assert 1 not in received_block_ids
        assert 2 not in received_block_ids
        assert 4 not in received_block_ids

        # LLM blocks should have been sent
        assert 3 in received_block_ids
        assert 5 in received_block_ids

        # Result should have all 5 blocks
        assert len(results) == 5
        result_ids = [r["id"] for r in results]
        assert result_ids == [1, 2, 3, 4, 5]

        # Gate metrics should be in usage
        assert "gate" in usage
        assert usage["gate"]["gated"] == 3
        assert usage["gate"]["sent_to_llm"] == 2

    def test_all_gated_skips_llm(self):
        """When all blocks are deterministic, GeminiClassifier should not be instantiated."""
        from processor.classifier import classify_blocks_with_prompt

        blocks = [
            _block(1, ""),
            _block(2, "Table 1", caption_type="table"),
        ]

        with patch("processor.classifier.GeminiClassifier") as MockCls:
            results, usage = classify_blocks_with_prompt(
                blocks, "test.docx", "fake-api-key"
            )
            # GeminiClassifier should never have been called
            MockCls.assert_not_called()

        assert len(results) == 2
        assert usage["total_tokens"] == 0
        assert usage["gate"]["gated"] == 2
        assert usage["gate"]["sent_to_llm"] == 0


# ===================================================================
# Batching and batch fallback
# ===================================================================

class TestBatchingProducesMultipleCalls:
    def test_multiple_batches(self, monkeypatch):
        """When input exceeds batch size, multiple _classify_chunk calls are made."""
        from processor.classifier import GeminiClassifier

        monkeypatch.setattr("processor.classifier.MAX_PARAGRAPHS_PER_CHUNK", 5)

        # Create 12 blocks (should produce 3 batches: 5 + 5 + 2)
        blocks = [_block(i, f"Paragraph {i} text content.") for i in range(1, 13)]

        call_count = [0]
        def fake_classify_chunk(self_, chunk, doc_name, doc_type, chunk_info=""):
            call_count[0] += 1
            return [{"id": p["id"], "tag": "TXT", "confidence": 85} for p in chunk]

        with patch.object(GeminiClassifier, "_classify_chunk", fake_classify_chunk):
            with patch.object(GeminiClassifier, "__init__", lambda self_, *a, **kw: None):
                classifier = GeminiClassifier.__new__(GeminiClassifier)
                # Set required attributes
                classifier.model = MagicMock()
                classifier.model.get_token_usage.return_value = {
                    "total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0
                }
                classifier.model.get_last_usage.return_value = {}
                classifier.enable_fallback = False
                classifier.fallback_model = None
                classifier.fallback_model_name = ""
                classifier.primary_model_name = "gemini-2.5-flash-lite"
                classifier.fallback_threshold = 75
                classifier.fallback_calls = 0
                classifier.items_improved = 0
                classifier.fallback_input_tokens = 0
                classifier.fallback_output_tokens = 0
                classifier.rule_predictions = 0
                classifier.llm_predictions = 0
                classifier.retriever = None
                classifier.cache = None
                classifier.rule_learner = None

                results = classifier.classify(blocks, "test.docx", "Academic Document")

        assert call_count[0] == 3  # ceil(12/5) = 3 batches
        assert len(results) == 12

    def test_batch_failure_fallback(self, monkeypatch):
        """When one batch fails, its paragraphs get TXT fallback while others succeed."""
        from processor.classifier import GeminiClassifier

        monkeypatch.setattr("processor.classifier.MAX_PARAGRAPHS_PER_CHUNK", 3)

        blocks = [_block(i, f"Paragraph {i}.") for i in range(1, 8)]
        # 7 blocks → 3 batches: [1,2,3], [4,5,6], [7]

        batch_num = [0]
        def fake_classify_chunk(self_, chunk, doc_name, doc_type, chunk_info=""):
            batch_num[0] += 1
            if batch_num[0] == 2:
                raise RuntimeError("API timeout")
            return [{"id": p["id"], "tag": "H1", "confidence": 90} for p in chunk]

        with patch.object(GeminiClassifier, "_classify_chunk", fake_classify_chunk):
            with patch.object(GeminiClassifier, "__init__", lambda self_, *a, **kw: None):
                classifier = GeminiClassifier.__new__(GeminiClassifier)
                classifier.model = MagicMock()
                classifier.model.get_token_usage.return_value = {
                    "total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0
                }
                classifier.model.get_last_usage.return_value = {}
                classifier.enable_fallback = False
                classifier.fallback_model = None
                classifier.fallback_model_name = ""
                classifier.primary_model_name = "gemini-2.5-flash-lite"
                classifier.fallback_threshold = 75
                classifier.fallback_calls = 0
                classifier.items_improved = 0
                classifier.fallback_input_tokens = 0
                classifier.fallback_output_tokens = 0
                classifier.rule_predictions = 0
                classifier.llm_predictions = 0
                classifier.retriever = None
                classifier.cache = None
                classifier.rule_learner = None

                results = classifier.classify(blocks, "test.docx", "Academic Document")

        assert len(results) == 7

        result_by_id = {r["id"]: r for r in results}
        # Batch 1 (ids 1,2,3) and Batch 3 (id 7) succeeded
        assert result_by_id[1]["tag"] == "H1"
        assert result_by_id[2]["tag"] == "H1"
        assert result_by_id[3]["tag"] == "H1"
        assert result_by_id[7]["tag"] == "H1"

        # Batch 2 (ids 4,5,6) failed → TXT fallback
        assert result_by_id[4]["tag"] == "TXT"
        assert result_by_id[4]["confidence"] == 30
        assert result_by_id[4].get("batch_fallback") is True
        assert result_by_id[5]["tag"] == "TXT"
        assert result_by_id[6]["tag"] == "TXT"


# ===================================================================
# Cost estimation
# ===================================================================

class TestCostEstimation:
    def test_estimate_cost_function(self):
        from processor.classifier import _estimate_cost
        # gemini-2.5-pro: 0.00125 per 1K input, 0.005 per 1K output
        cost = _estimate_cost("gemini-2.5-pro", 10000, 2000)
        expected = (10000 / 1000) * 0.00125 + (2000 / 1000) * 0.005
        assert abs(cost - expected) < 1e-9

    def test_estimate_cost_zero_for_free_tier(self):
        from processor.classifier import _estimate_cost
        cost = _estimate_cost("gemini-2.5-flash-lite", 50000, 10000)
        assert cost == 0.0

    def test_estimate_cost_unknown_model(self):
        from processor.classifier import _estimate_cost
        cost = _estimate_cost("unknown-model", 1000, 500)
        assert cost == 0.0


# ===================================================================
# GateMetrics
# ===================================================================

class TestGateMetrics:
    def test_default_values(self):
        m = GateMetrics()
        assert m.total_blocks == 0
        assert m.gated_count == 0
        assert m.llm_count == 0
        assert m.rules_fired == {}

    def test_inc(self):
        m = GateMetrics(total_blocks=5)
        m._inc("gate-empty")
        m._inc("gate-empty")
        m._inc("gate-marker")
        assert m.rules_fired == {"gate-empty": 2, "gate-marker": 1}
