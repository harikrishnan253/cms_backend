"""Tests for deterministic table-title classification override."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.table_title_rules import enforce_table_title_rules


def _block(pid, text="Paragraph", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# enforce_table_title_rules — positive cases
# ===================================================================

class TestTableTitlePositive:
    """Blocks matching the table-title pattern are locked."""

    def test_simple_table_1(self):
        blocks = [_block(1, "Table 1 Demographics of Study Participants")]
        result = enforce_table_title_rules(blocks)

        assert result[0]["metadata"]["context_zone"] == "TABLE"
        assert result[0]["metadata"]["table_title"] is True
        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["T1"]
        assert result[0]["skip_llm"] is True

    def test_table_with_sub_number(self):
        """Table 1.2 (sub-numbered) is detected."""
        blocks = [_block(1, "Table 1.2 Subgroup Analysis")]
        result = enforce_table_title_rules(blocks)

        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["T1"]
        assert result[0]["metadata"]["table_title"] is True

    def test_multi_digit_table(self):
        """Table 12, Table 100, etc."""
        blocks = [_block(1, "Table 12 Results")]
        result = enforce_table_title_rules(blocks)
        assert result[0]["lock_style"] is True

    def test_table_number_only(self):
        """'Table 1' with no trailing description."""
        blocks = [_block(1, "Table 1")]
        result = enforce_table_title_rules(blocks)
        assert result[0]["lock_style"] is True

    def test_table_with_period_and_trailing(self):
        blocks = [_block(1, "Table 3.14 PI Calculations")]
        result = enforce_table_title_rules(blocks)
        assert result[0]["lock_style"] is True

    def test_multiple_tables_in_document(self):
        blocks = [
            _block(1, "Introduction paragraph."),
            _block(2, "Table 1 Demographics"),
            _block(3, "Some body text here."),
            _block(4, "Table 2 Lab Results"),
            _block(5, "More body text."),
        ]
        result = enforce_table_title_rules(blocks)

        # Only table titles are locked
        assert result[1]["lock_style"] is True
        assert result[3]["lock_style"] is True

        # Non-table blocks are untouched
        assert result[0].get("lock_style") is not True
        assert result[2].get("lock_style") is not True
        assert result[4].get("lock_style") is not True

    def test_zone_overridden_to_table(self):
        """Even if the block was in BODY zone, it gets moved to TABLE."""
        blocks = [_block(1, "Table 1 Results", context_zone="BODY")]
        result = enforce_table_title_rules(blocks)
        assert result[0]["metadata"]["context_zone"] == "TABLE"

    def test_zone_override_from_back_matter(self):
        blocks = [_block(1, "Table 5 Summary", context_zone="BACK_MATTER")]
        result = enforce_table_title_rules(blocks)
        assert result[0]["metadata"]["context_zone"] == "TABLE"


# ===================================================================
# enforce_table_title_rules — negative cases
# ===================================================================

class TestTableTitleNegative:
    """Blocks that do NOT match the pattern are left unchanged."""

    def test_lowercase_table(self):
        """The regex is case-sensitive: 'table 1' does not match."""
        blocks = [_block(1, "table 1 results")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_no_space_after_table(self):
        """'Table1' (no space) does not match."""
        blocks = [_block(1, "Table1 Results")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_table_word_in_sentence(self):
        """'The table shows...' does not start with 'Table N'."""
        blocks = [_block(1, "The table shows important results.")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_table_without_number(self):
        """'Table of Contents' does not have a digit after Table."""
        blocks = [_block(1, "Table of Contents")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_normal_body_text(self):
        blocks = [_block(1, "The results indicate a positive trend.")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_heading_text(self):
        blocks = [_block(1, "Chapter 3 Methodology")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_figure_caption(self):
        blocks = [_block(1, "Figure 1 Study Flow Diagram")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_empty_text(self):
        blocks = [_block(1, "")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True

    def test_tables_plural(self):
        """'Tables 1-3 summarize...' is not a table title."""
        blocks = [_block(1, "Tables 1-3 summarize the findings.")]
        result = enforce_table_title_rules(blocks)
        assert result[0].get("lock_style") is not True


# ===================================================================
# Text & whitespace preservation
# ===================================================================

class TestTextPreservation:
    """Verify text is never modified."""

    def test_text_not_modified(self):
        original = "Table 1 Demographics of Study Participants"
        blocks = [_block(1, original)]
        result = enforce_table_title_rules(blocks)
        assert result[0]["text"] == original

    def test_text_with_trailing_whitespace_preserved(self):
        original = "Table 1 Results  "
        blocks = [_block(1, original)]
        result = enforce_table_title_rules(blocks)
        assert result[0]["text"] == original

    def test_text_not_lowercased(self):
        original = "Table 1 UPPERCASE TITLE"
        blocks = [_block(1, original)]
        result = enforce_table_title_rules(blocks)
        assert result[0]["text"] == original


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:

    def test_empty_blocks(self):
        result = enforce_table_title_rules([])
        assert result == []

    def test_identity_preserved(self):
        """Returned blocks are the same objects (in-place modification)."""
        blocks = [_block(1, "Table 1 Results")]
        result = enforce_table_title_rules(blocks)
        assert result[0] is blocks[0]

    def test_returns_list(self):
        blocks = [_block(1, "Table 1")]
        result = enforce_table_title_rules(blocks)
        assert isinstance(result, list)

    def test_metadata_created_if_missing(self):
        """If block has no metadata dict, one is created."""
        block = {"id": 1, "text": "Table 1 Results"}
        result = enforce_table_title_rules([block])
        assert result[0]["metadata"]["table_title"] is True
        assert result[0]["metadata"]["context_zone"] == "TABLE"

    def test_existing_metadata_preserved(self):
        """Other metadata fields are not removed."""
        blocks = [_block(1, "Table 1 Results", is_bold=True, font_size=14.0)]
        result = enforce_table_title_rules(blocks)
        assert result[0]["metadata"]["is_bold"] is True
        assert result[0]["metadata"]["font_size"] == 14.0
        assert result[0]["metadata"]["table_title"] is True


# ===================================================================
# Gate integration: locked table titles skip LLM
# ===================================================================

class TestGateIntegration:
    """Verify that lock_style table titles are gated by deterministic gate."""

    def test_locked_table_title_gated(self):
        from processor.deterministic_gate import classify_deterministic

        block = _block(1, "Table 1 Demographics", context_zone="TABLE")
        block["lock_style"] = True
        block["allowed_styles"] = ["T1"]
        block["skip_llm"] = True
        block["metadata"]["table_title"] = True

        result = classify_deterministic(block)

        assert result is not None
        assert result["tag"] == "T1"
        assert result["gate_rule"] == "gate-locked-style"
        assert result["confidence"] == 99
        assert result["gated"] is True

    def test_locked_table_title_not_sent_to_llm(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "Table 1 Demographics", context_zone="TABLE"),
            _block(2, "Normal body text paragraph."),
        ]
        blocks[0]["lock_style"] = True
        blocks[0]["allowed_styles"] = ["T1"]
        blocks[0]["skip_llm"] = True
        blocks[0]["metadata"]["table_title"] = True

        gated, llm, metrics = gate_for_llm(blocks)

        assert len(gated) == 1
        assert gated[0]["id"] == 1
        assert gated[0]["tag"] == "T1"

        assert len(llm) == 1
        assert llm[0]["id"] == 2

        assert metrics.rules_fired.get("gate-locked-style") == 1


# ===================================================================
# End-to-end: enforce → gate pipeline
# ===================================================================

class TestEndToEnd:

    def test_enforce_then_gate(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "Introduction"),
            _block(2, "Table 1 Demographics"),
            _block(3, "Data in the first row shows..."),
            _block(4, "Table 2.1 Subgroup Analysis"),
            _block(5, "Conclusion paragraph."),
        ]

        # Step 1: enforce table title rules
        blocks = enforce_table_title_rules(blocks)

        # Step 2: gate for LLM
        gated, llm, metrics = gate_for_llm(blocks)

        gated_ids = {c["id"] for c in gated}
        llm_ids = {b["id"] for b in llm}

        # Table titles (2, 4) → gated as T1 via lock_style
        assert 2 in gated_ids
        assert 4 in gated_ids

        gated_by_id = {c["id"]: c for c in gated}
        assert gated_by_id[2]["tag"] == "T1"
        assert gated_by_id[4]["tag"] == "T1"

        # Non-table-title blocks → sent to LLM
        assert 1 in llm_ids
        assert 3 in llm_ids
        assert 5 in llm_ids


# ===================================================================
# Before/after example (documentation test)
# ===================================================================

class TestBeforeAfterExample:
    """Demonstrates the transformation applied by enforce_table_title_rules."""

    def test_before_after_transformation(self):
        """
        BEFORE:
            block = {
                "id": 42,
                "text": "Table 3 Patient Outcomes by Treatment Group",
                "metadata": {"context_zone": "BODY", "is_bold": True}
            }

        AFTER enforce_table_title_rules():
            block = {
                "id": 42,
                "text": "Table 3 Patient Outcomes by Treatment Group",  # unchanged
                "metadata": {
                    "context_zone": "TABLE",     # was BODY
                    "is_bold": True,              # preserved
                    "table_title": True,          # NEW
                },
                "lock_style": True,              # NEW
                "allowed_styles": ["T1"],         # NEW
                "skip_llm": True,                # NEW
            }
        """
        # --- Before ---
        block = {
            "id": 42,
            "text": "Table 3 Patient Outcomes by Treatment Group",
            "metadata": {"context_zone": "BODY", "is_bold": True},
        }

        assert block["metadata"]["context_zone"] == "BODY"
        assert "lock_style" not in block
        assert "table_title" not in block["metadata"]

        # --- Apply ---
        result = enforce_table_title_rules([block])

        # --- After ---
        b = result[0]
        assert b["text"] == "Table 3 Patient Outcomes by Treatment Group"
        assert b["metadata"]["context_zone"] == "TABLE"
        assert b["metadata"]["is_bold"] is True
        assert b["metadata"]["table_title"] is True
        assert b["lock_style"] is True
        assert b["allowed_styles"] == ["T1"]
        assert b["skip_llm"] is True
