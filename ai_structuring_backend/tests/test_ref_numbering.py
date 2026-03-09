"""Tests for deterministic reference-numbering preservation."""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.ref_numbering import normalize_reference_numbering


def _block(pid, text="Paragraph", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# normalize_reference_numbering — core behaviour
# ===================================================================

class TestNormalizeReferenceNumbering:
    """Test that numbered reference entries are detected and locked."""

    def _patch_ref_zone(self, ref_ids, trigger="heading_match"):
        """Return a context manager that mocks detect_reference_zone."""
        return patch(
            "processor.ref_numbering.detect_reference_zone",
            return_value=(set(ref_ids), trigger, 0 if ref_ids else None),
        )

    # --- Positive cases: numbered entries in reference zone ---

    def test_numbered_entry_marked(self):
        """A simple numbered reference 1. WHO... is locked."""
        blocks = [
            _block(1, "References", context_zone="BACK_MATTER"),
            _block(2, "1. WHO. Global Report 2020.", context_zone="BACK_MATTER"),
            _block(3, "2. CDC. Morbidity Report.", context_zone="BACK_MATTER"),
        ]
        with self._patch_ref_zone([1, 2, 3]):
            result = normalize_reference_numbering(blocks)

        assert result[1]["metadata"]["ref_numbered"] is True
        assert result[1]["lock_style"] is True
        assert result[1]["allowed_styles"] == ["REF-N"]

        assert result[2]["metadata"]["ref_numbered"] is True
        assert result[2]["lock_style"] is True

    def test_heading_not_marked(self):
        """The 'References' heading itself has no numbering → unchanged."""
        blocks = [
            _block(1, "References", context_zone="BACK_MATTER"),
            _block(2, "1. WHO. Global Report 2020.", context_zone="BACK_MATTER"),
        ]
        with self._patch_ref_zone([1, 2]):
            result = normalize_reference_numbering(blocks)

        assert result[0].get("lock_style") is not True
        assert "ref_numbered" not in result[0].get("metadata", {})

    def test_text_not_modified(self):
        """Original text must be preserved exactly — no stripping."""
        original_text = "  1.  WHO. Global Report 2020.  "
        blocks = [_block(1, original_text, context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == original_text

    def test_whitespace_preserved(self):
        """Leading whitespace before numbering is kept intact."""
        text = "   3. Smith, J. (2019). A study."
        blocks = [_block(1, text, context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0]["text"] == text
        assert result[0]["metadata"]["ref_numbered"] is True

    def test_multi_digit_numbering(self):
        """Two-digit numbers like 12. should still match."""
        blocks = [_block(1, "12. Jones, K. Handbook of X.", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0]["metadata"]["ref_numbered"] is True
        assert result[0]["lock_style"] is True

    def test_large_numbering(self):
        """Three-digit numbers like 100. should match."""
        blocks = [_block(1, "100. Final reference entry.", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0]["metadata"]["ref_numbered"] is True

    # --- Negative cases: blocks NOT in reference zone ---

    def test_body_numbered_list_not_marked(self):
        """A numbered list in BODY zone is NOT locked."""
        blocks = [
            _block(1, "1. First step in protocol."),
            _block(2, "2. Second step in protocol."),
        ]
        with self._patch_ref_zone([]):  # no ref zone
            result = normalize_reference_numbering(blocks)

        assert result[0].get("lock_style") is not True
        assert "ref_numbered" not in result[0].get("metadata", {})

    def test_non_numbered_ref_entry_not_marked(self):
        """An unnumbered reference entry is NOT locked."""
        blocks = [
            _block(1, "References", context_zone="BACK_MATTER"),
            _block(2, "Smith, J. (2020). A study.", context_zone="BACK_MATTER"),
        ]
        with self._patch_ref_zone([1, 2]):
            result = normalize_reference_numbering(blocks)

        assert result[1].get("lock_style") is not True
        assert "ref_numbered" not in result[1].get("metadata", {})

    def test_bracket_numbering_not_matched(self):
        """[1] style numbering does not match the digit-dot pattern."""
        blocks = [_block(1, "[1] WHO. Global Report.", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0].get("lock_style") is not True

    def test_period_without_space_not_matched(self):
        """'1.WHO' (no space after dot) does not match."""
        blocks = [_block(1, "1.WHO. Global Report.", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0].get("lock_style") is not True

    def test_empty_text_not_marked(self):
        blocks = [_block(1, "", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0].get("lock_style") is not True

    # --- Edge cases ---

    def test_empty_blocks(self):
        result = normalize_reference_numbering([])
        assert result == []

    def test_no_reference_zone_returns_unchanged(self):
        blocks = [_block(1, "Normal paragraph.")]
        with self._patch_ref_zone([]):
            result = normalize_reference_numbering(blocks)

        assert len(result) == 1
        assert result[0].get("lock_style") is not True

    def test_blocks_returned_as_list(self):
        blocks = [_block(1, "1. Ref entry.", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert isinstance(result, list)

    def test_identity_preserved(self):
        """Returned blocks are the same objects (in-place modification)."""
        blocks = [_block(1, "1. Ref entry.", context_zone="BACK_MATTER")]
        with self._patch_ref_zone([1]):
            result = normalize_reference_numbering(blocks)

        assert result[0] is blocks[0]

    def test_mixed_document(self):
        """Only reference-zone numbered entries are locked in a mixed doc."""
        blocks = [
            _block(1, "Introduction"),
            _block(2, "1. First finding in body."),
            _block(3, "References", context_zone="BACK_MATTER"),
            _block(4, "1. WHO. Global Report.", context_zone="BACK_MATTER"),
            _block(5, "2. CDC. Morbidity.", context_zone="BACK_MATTER"),
            _block(6, "Smith, J. (2020). Unnumbered.", context_zone="BACK_MATTER"),
        ]
        with self._patch_ref_zone([3, 4, 5, 6]):
            result = normalize_reference_numbering(blocks)

        # Body numbered list → NOT locked
        assert result[1].get("lock_style") is not True
        # Reference heading → NOT locked (no numbering)
        assert result[2].get("lock_style") is not True
        # Numbered references → locked
        assert result[3]["lock_style"] is True
        assert result[3]["allowed_styles"] == ["REF-N"]
        assert result[4]["lock_style"] is True
        # Unnumbered reference → NOT locked
        assert result[5].get("lock_style") is not True


# ===================================================================
# Integration: lock_style blocks gated by deterministic gate
# ===================================================================

class TestGateIntegration:
    """Verify that lock_style blocks are picked up by the deterministic gate."""

    def test_locked_block_gated(self):
        from processor.deterministic_gate import classify_deterministic

        block = _block(1, "1. WHO. Global Report 2020.", context_zone="BACK_MATTER")
        block["lock_style"] = True
        block["allowed_styles"] = ["REF-N"]
        block["metadata"]["ref_numbered"] = True

        result = classify_deterministic(block)

        assert result is not None
        assert result["tag"] == "REF-N"
        assert result["gate_rule"] == "gate-locked-style"
        assert result["confidence"] == 99
        assert result["gated"] is True

    def test_locked_block_not_sent_to_llm(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "1. WHO. Global Report 2020.", context_zone="BACK_MATTER"),
            _block(2, "Normal body text paragraph."),
        ]
        blocks[0]["lock_style"] = True
        blocks[0]["allowed_styles"] = ["REF-N"]
        blocks[0]["metadata"]["ref_numbered"] = True

        gated, llm, metrics = gate_for_llm(blocks)

        assert len(gated) == 1
        assert gated[0]["id"] == 1
        assert gated[0]["tag"] == "REF-N"

        assert len(llm) == 1
        assert llm[0]["id"] == 2

        assert metrics.rules_fired.get("gate-locked-style") == 1

    def test_unlocked_numbered_block_not_gated_by_lock_rule(self):
        """Without lock_style, the lock rule does not fire."""
        from processor.deterministic_gate import classify_deterministic

        block = _block(1, "1. WHO. Global Report 2020.", context_zone="BACK_MATTER")
        # No lock_style set → should not be gated by the lock rule
        result = classify_deterministic(block)

        # May or may not be gated by another rule, but NOT by gate-locked-style
        assert result is None or result.get("gate_rule") != "gate-locked-style"


# ===================================================================
# End-to-end: normalize → gate pipeline
# ===================================================================

class TestEndToEnd:
    """Verify the full normalize_reference_numbering → gate flow."""

    def test_normalize_then_gate(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "References", context_zone="BACK_MATTER"),
            _block(2, "1. WHO. Global Report 2020.", context_zone="BACK_MATTER"),
            _block(3, "2. CDC. Morbidity Report.", context_zone="BACK_MATTER"),
            _block(4, "Smith, J. (2020). Unnumbered ref.", context_zone="BACK_MATTER"),
        ]

        # Step 1: normalize reference numbering
        with patch(
            "processor.ref_numbering.detect_reference_zone",
            return_value=({1, 2, 3, 4}, "heading_match", 0),
        ):
            blocks = normalize_reference_numbering(blocks)

        # Step 2: gate for LLM
        gated, llm, metrics = gate_for_llm(blocks)

        gated_ids = {c["id"] for c in gated}
        llm_ids = {b["id"] for b in llm}

        # Numbered refs (2, 3) → gated as REF-N via lock_style
        assert 2 in gated_ids
        assert 3 in gated_ids
        gated_by_id = {c["id"]: c for c in gated}
        assert gated_by_id[2]["tag"] == "REF-N"
        assert gated_by_id[3]["tag"] == "REF-N"

        # Non-numbered ref (4) and heading (1) → sent to LLM
        # (unless another gate rule catches them)
        # The heading "References" is just text; ID 4 is an unnumbered entry
        # Both should NOT be gated by lock_style
        for g in gated:
            if g["id"] in (1, 4):
                assert g.get("gate_rule") != "gate-locked-style"
