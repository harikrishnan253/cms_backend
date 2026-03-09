"""Tests for deterministic list hierarchy enforcement from Word XML."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.list_hierarchy import enforce_list_hierarchy_from_word_xml


def _block(pid, text="List item", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# enforce_list_hierarchy_from_word_xml — positive cases
# ===================================================================

class TestListHierarchyPositive:
    """Blocks with xml_list_level are locked to level-specific tags."""

    def test_bullet_list_level_0(self):
        """ilvl 0 (base level) → BL-MID."""
        blocks = [_block(1, "• First item", xml_list_level=0, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)

        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["BL-MID"]
        assert result[0]["skip_llm"] is True

    def test_bullet_list_level_1(self):
        """ilvl 1 (nested once) → BL2-MID."""
        blocks = [_block(1, "  ◦ Nested item", xml_list_level=1, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)

        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["BL2-MID"]
        assert result[0]["skip_llm"] is True

    def test_bullet_list_level_2(self):
        """ilvl 2 (nested twice) → BL3-MID."""
        blocks = [_block(1, "    ▪ Nested twice", xml_list_level=2, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)

        assert result[0]["allowed_styles"] == ["BL3-MID"]

    def test_bullet_list_level_3_plus(self):
        """ilvl 3+ → BL4-MID (max level)."""
        blocks = [_block(1, "      Deep nest", xml_list_level=3, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL4-MID"]

        blocks = [_block(1, "      Very deep", xml_list_level=5, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL4-MID"]

    def test_numbered_list_level_0(self):
        """Numbered list ilvl 0 → NL-MID."""
        blocks = [_block(1, "1. First", xml_list_level=0, has_numbering=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["NL-MID"]

    def test_numbered_list_level_1(self):
        """Numbered list ilvl 1 → NL2-MID."""
        blocks = [_block(1, "  a. Sub", xml_list_level=1, has_numbering=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["NL2-MID"]

    def test_numbered_list_level_2(self):
        """Numbered list ilvl 2 → NL3-MID."""
        blocks = [_block(1, "    i. Sub-sub", xml_list_level=2, has_numbering=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["NL3-MID"]

    def test_unordered_list_ambiguous(self):
        """Ambiguous XML list (has_xml_list=True) → UL-MID."""
        blocks = [_block(1, "Item", xml_list_level=0, has_xml_list=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["UL-MID"]

        blocks = [_block(1, "Nested", xml_list_level=1, has_xml_list=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["UL2-MID"]

    def test_fallback_to_bullet_when_no_hint(self):
        """If xml_list_level is present but no type hint, default to BL."""
        blocks = [_block(1, "Mystery list", xml_list_level=0)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL-MID"]

    def test_multiple_lists_in_document(self):
        blocks = [
            _block(1, "• Level 0", xml_list_level=0, has_bullet=True),
            _block(2, "  ◦ Level 1", xml_list_level=1, has_bullet=True),
            _block(3, "    ▪ Level 2", xml_list_level=2, has_bullet=True),
            _block(4, "Normal paragraph"),  # no xml_list_level
            _block(5, "1. Numbered", xml_list_level=0, has_numbering=True),
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)

        assert result[0]["allowed_styles"] == ["BL-MID"]
        assert result[1]["allowed_styles"] == ["BL2-MID"]
        assert result[2]["allowed_styles"] == ["BL3-MID"]
        assert result[3].get("lock_style") is not True  # not locked
        assert result[4]["allowed_styles"] == ["NL-MID"]


# ===================================================================
# enforce_list_hierarchy_from_word_xml — negative cases
# ===================================================================

class TestListHierarchyNegative:
    """Blocks without xml_list_level are NOT locked."""

    def test_no_xml_list_level(self):
        """Block with no xml_list_level metadata → unchanged."""
        blocks = [_block(1, "• Bullet item", has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True

    def test_normal_body_text(self):
        blocks = [_block(1, "Normal paragraph text.")]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True

    def test_heading_text(self):
        blocks = [_block(1, "Chapter 3 Methodology")]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True

    def test_xml_list_level_none(self):
        """xml_list_level=None → not locked."""
        blocks = [_block(1, "Item", xml_list_level=None, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True


# ===================================================================
# Text & indentation preservation
# ===================================================================

class TestTextPreservation:
    """Verify text is never modified."""

    def test_text_not_modified(self):
        original = "  • Nested bullet item with spaces"
        blocks = [_block(1, original, xml_list_level=1, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["text"] == original

    def test_text_with_trailing_whitespace(self):
        original = "1. First item  "
        blocks = [_block(1, original, xml_list_level=0, has_numbering=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["text"] == original

    def test_indentation_metadata_preserved(self):
        """Existing indent_level metadata is preserved."""
        blocks = [_block(1, "Item", xml_list_level=1, indent_level=1, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["metadata"]["indent_level"] == 1
        assert result[0]["metadata"]["xml_list_level"] == 1


# ===================================================================
# Edge cases & error handling
# ===================================================================

class TestEdgeCases:

    def test_empty_blocks(self):
        result = enforce_list_hierarchy_from_word_xml([])
        assert result == []

    def test_identity_preserved(self):
        """Returned blocks are the same objects (in-place modification)."""
        blocks = [_block(1, "• Item", xml_list_level=0, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0] is blocks[0]

    def test_returns_list(self):
        blocks = [_block(1, "• Item", xml_list_level=0, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert isinstance(result, list)

    def test_metadata_created_if_missing(self):
        """If block has no metadata dict, xml_list_level check fails gracefully."""
        block = {"id": 1, "text": "• Item"}  # no metadata
        result = enforce_list_hierarchy_from_word_xml([block])
        # Should not crash, just skip
        assert result[0].get("lock_style") is not True

    def test_negative_ilvl_treated_as_level_4(self):
        """Negative ilvl (shouldn't happen, but if it does) → BL4-MID."""
        blocks = [_block(1, "Item", xml_list_level=-1, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        # xml_level < 0 falls through to else branch (level 4+)
        assert result[0]["allowed_styles"] == ["BL4-MID"]

    def test_zero_ilvl_is_base_level(self):
        """ilvl 0 is the base level (not nested)."""
        blocks = [_block(1, "• Base", xml_list_level=0, has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL-MID"]


# ===================================================================
# Gate integration: locked lists skip LLM
# ===================================================================

class TestGateIntegration:
    """Verify that lock_style lists are gated by deterministic gate."""

    def test_locked_list_gated(self):
        from processor.deterministic_gate import classify_deterministic

        block = _block(1, "• Item", xml_list_level=0, has_bullet=True)
        block["lock_style"] = True
        block["allowed_styles"] = ["BL-MID"]
        block["skip_llm"] = True

        result = classify_deterministic(block)

        assert result is not None
        assert result["tag"] == "BL-MID"
        assert result["gate_rule"] == "gate-locked-style"
        assert result["confidence"] == 99
        assert result["gated"] is True

    def test_locked_list_not_sent_to_llm(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "• Item", xml_list_level=0, has_bullet=True),
            _block(2, "Normal body text paragraph."),
        ]
        blocks[0]["lock_style"] = True
        blocks[0]["allowed_styles"] = ["BL-MID"]
        blocks[0]["skip_llm"] = True

        gated, llm, metrics = gate_for_llm(blocks)

        assert len(gated) == 1
        assert gated[0]["id"] == 1
        assert gated[0]["tag"] == "BL-MID"

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
            _block(1, "Introduction paragraph."),
            _block(2, "• Level 0 bullet", xml_list_level=0, has_bullet=True),
            _block(3, "  ◦ Level 1 nested", xml_list_level=1, has_bullet=True),
            _block(4, "1. Numbered item", xml_list_level=0, has_numbering=True),
            _block(5, "Conclusion paragraph."),
        ]

        # Step 1: enforce list hierarchy
        blocks = enforce_list_hierarchy_from_word_xml(blocks)

        # Step 2: gate for LLM
        gated, llm, metrics = gate_for_llm(blocks)

        gated_ids = {c["id"] for c in gated}
        llm_ids = {b["id"] for b in llm}

        # Lists (2, 3, 4) → gated via lock_style
        assert 2 in gated_ids
        assert 3 in gated_ids
        assert 4 in gated_ids

        gated_by_id = {c["id"]: c for c in gated}
        assert gated_by_id[2]["tag"] == "BL-MID"
        assert gated_by_id[3]["tag"] == "BL2-MID"
        assert gated_by_id[4]["tag"] == "NL-MID"

        # Non-list blocks → sent to LLM
        assert 1 in llm_ids
        assert 5 in llm_ids


# ===================================================================
# Safe XML handling — no crashes
# ===================================================================

class TestSafeXMLHandling:
    """Verify graceful handling of malformed or missing XML."""

    def test_missing_metadata_dict(self):
        """Block with no metadata dict → no crash."""
        block = {"id": 1, "text": "• Item"}
        result = enforce_list_hierarchy_from_word_xml([block])
        assert len(result) == 1
        assert result[0].get("lock_style") is not True

    def test_xml_list_level_string(self):
        """If xml_list_level is a string (shouldn't happen), skip gracefully."""
        blocks = [_block(1, "• Item", xml_list_level="0", has_bullet=True)]
        # This will be compared to None, so it passes the xml_level is None check
        # and attempts int comparison. Since "0" != 0/1/2, falls to else (level 4)
        result = enforce_list_hierarchy_from_word_xml(blocks)
        # The string "0" is not None, so it gets processed
        # xml_level == 0 checks "0" == 0 → False
        # Falls through to else → BL4-MID
        assert result[0]["allowed_styles"] == ["BL4-MID"]

    def test_no_type_hints_defaults_to_bullet(self):
        """No has_bullet/has_numbering/has_xml_list → defaults to BL."""
        blocks = [_block(1, "Item", xml_list_level=0)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL-MID"]
