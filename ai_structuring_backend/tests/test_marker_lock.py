"""Tests for structural marker paragraph locking."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.marker_lock import (
    lock_marker_blocks,
    relock_marker_classifications,
    _is_marker_block,
)


def _block(pid, text="Paragraph", **meta_overrides):
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


# ===================================================================
# lock_marker_blocks — positive cases
# ===================================================================

class TestMarkerLockPositive:
    """Blocks matching marker pattern are locked to PMI."""

    def test_simple_marker_cn(self):
        """<CN> (chapter number) marker."""
        blocks = [_block(1, "<CN>")]
        result = lock_marker_blocks(blocks)

        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["PMI"]
        assert result[0]["skip_llm"] is True

    def test_marker_ct(self):
        """<CT> (chapter title) marker."""
        blocks = [_block(1, "<CT>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_ref(self):
        """<REF> (reference section) marker."""
        blocks = [_block(1, "<REF>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["allowed_styles"] == ["PMI"]

    def test_marker_with_hyphen(self):
        """<H1-INTRO> marker with hyphen."""
        blocks = [_block(1, "<H1-INTRO>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_with_dot(self):
        """<TAB6.1> marker with dot/period."""
        blocks = [_block(1, "<TAB6.1>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_with_underscore(self):
        """<SOME_MARKER> marker with underscore."""
        blocks = [_block(1, "<SOME_MARKER>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_with_numbers(self):
        """<BOX123> marker with numbers."""
        blocks = [_block(1, "<BOX123>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_with_spaces(self):
        """<WITH SPACES> marker with internal spaces."""
        blocks = [_block(1, "<WITH SPACES>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_insert_figure_marker_with_here(self):
        """Regression: figure insertion markers should be marker-locked."""
        blocks = [_block(1, "<INSERT FIGURE 7.1 HERE>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["PMI"]
        assert result[0]["skip_llm"] is True

    def test_insert_figure_marker_without_here(self):
        """Regression: figure insertion marker variant should be marker-locked."""
        blocks = [_block(1, "<INSERT FIGURE 7.2>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["PMI"]
        assert result[0]["skip_llm"] is True

    def test_marker_lowercase(self):
        """<lowercase> marker."""
        blocks = [_block(1, "<lowercase>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_mixed_case(self):
        """<MixedCase> marker."""
        blocks = [_block(1, "<MixedCase>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_multiple_markers_in_document(self):
        blocks = [
            _block(1, "<CN>"),
            _block(2, "Normal paragraph"),
            _block(3, "<CT>"),
            _block(4, "Another paragraph"),
            _block(5, "<REF>"),
        ]
        result = lock_marker_blocks(blocks)

        # Markers (1, 3, 5) → locked
        assert result[0]["lock_style"] is True
        assert result[2]["lock_style"] is True
        assert result[4]["lock_style"] is True

        # Non-markers → not locked
        assert result[1].get("lock_style") is not True
        assert result[3].get("lock_style") is not True


# ===================================================================
# lock_marker_blocks — negative cases
# ===================================================================

class TestMarkerLockNegative:
    """Blocks NOT matching marker pattern are left unchanged."""

    def test_marker_with_content_after(self):
        """<H1>Introduction has content after marker."""
        blocks = [_block(1, "<H1>Introduction")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_marker_with_content_before(self):
        """Prefix<H1> has content before marker."""
        blocks = [_block(1, "Prefix<H1>")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_nested_brackets(self):
        """<<nested>> has nested brackets."""
        blocks = [_block(1, "<<nested>>")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_incomplete_marker_missing_close(self):
        """<incomplete is missing closing bracket."""
        blocks = [_block(1, "<incomplete")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_incomplete_marker_missing_open(self):
        """incomplete> is missing opening bracket."""
        blocks = [_block(1, "incomplete>")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_empty_brackets(self):
        """<> empty brackets."""
        blocks = [_block(1, "<>")]
        result = lock_marker_blocks(blocks)
        # Pattern requires [^<>]+ (at least one char), so <> doesn't match
        assert result[0].get("lock_style") is not True

    def test_normal_body_text(self):
        blocks = [_block(1, "Normal paragraph text.")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_heading_text(self):
        blocks = [_block(1, "Chapter 3 Methodology")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_empty_text(self):
        blocks = [_block(1, "")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True


# ===================================================================
# Edge case handling: whitespace
# ===================================================================

class TestWhitespaceHandling:
    """Verify whitespace trimming and preservation."""

    def test_marker_with_leading_whitespace(self):
        """  <CN> with leading spaces."""
        blocks = [_block(1, "  <CN>")]
        result = lock_marker_blocks(blocks)
        # Whitespace is trimmed for matching
        assert result[0]["lock_style"] is True

    def test_marker_with_trailing_whitespace(self):
        """<CN>   with trailing spaces."""
        blocks = [_block(1, "<CN>   ")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_marker_with_surrounding_whitespace(self):
        """  <CN>   with both."""
        blocks = [_block(1, "  <CN>   ")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True

    def test_text_not_modified(self):
        """Original text is preserved exactly, including whitespace."""
        original = "  <CN>  "
        blocks = [_block(1, original)]
        result = lock_marker_blocks(blocks)
        assert result[0]["text"] == original

    def test_whitespace_only_not_locked(self):
        """'   ' whitespace-only block."""
        blocks = [_block(1, "   ")]
        result = lock_marker_blocks(blocks)
        assert result[0].get("lock_style") is not True

    def test_marker_with_newline(self):
        """<CN>\n with newline."""
        blocks = [_block(1, "<CN>\n")]
        result = lock_marker_blocks(blocks)
        # strip() removes \n, leaving <CN> which matches
        assert result[0]["lock_style"] is True

    def test_marker_with_tab(self):
        """\t<CN> with tab."""
        blocks = [_block(1, "\t<CN>")]
        result = lock_marker_blocks(blocks)
        assert result[0]["lock_style"] is True


# ===================================================================
# Text preservation
# ===================================================================

class TestTextPreservation:
    """Verify text is never modified."""

    def test_text_not_modified_simple(self):
        original = "<REF>"
        blocks = [_block(1, original)]
        result = lock_marker_blocks(blocks)
        assert result[0]["text"] == original

    def test_text_not_modified_with_whitespace(self):
        original = "  <TAB6.1>  "
        blocks = [_block(1, original)]
        result = lock_marker_blocks(blocks)
        assert result[0]["text"] == original

    def test_text_not_modified_unlocked(self):
        """Non-marker text is also preserved."""
        original = "Normal paragraph with <bracket> content"
        blocks = [_block(1, original)]
        result = lock_marker_blocks(blocks)
        assert result[0]["text"] == original
        assert result[0].get("lock_style") is not True


# ===================================================================
# Edge cases & error handling
# ===================================================================

class TestEdgeCases:

    def test_empty_blocks(self):
        result = lock_marker_blocks([])
        assert result == []

    def test_identity_preserved(self):
        """Returned blocks are the same objects (in-place modification)."""
        blocks = [_block(1, "<CN>")]
        result = lock_marker_blocks(blocks)
        assert result[0] is blocks[0]

    def test_returns_list(self):
        blocks = [_block(1, "<CN>")]
        result = lock_marker_blocks(blocks)
        assert isinstance(result, list)

    def test_metadata_created_if_missing(self):
        """If block has no metadata dict, it's still processed."""
        block = {"id": 1, "text": "<CN>"}  # no metadata
        result = lock_marker_blocks([block])
        # Should not crash, should lock
        assert result[0]["lock_style"] is True

    def test_none_text_not_locked(self):
        """Block with text=None."""
        block = {"id": 1, "text": None}
        result = lock_marker_blocks([block])
        assert result[0].get("lock_style") is not True


# ===================================================================
# Gate integration: locked markers skip LLM
# ===================================================================

class TestGateIntegration:
    """Verify that lock_style markers are gated by deterministic gate."""

    def test_locked_marker_gated(self):
        from processor.deterministic_gate import classify_deterministic

        block = _block(1, "<CN>")
        block["lock_style"] = True
        block["allowed_styles"] = ["PMI"]
        block["skip_llm"] = True

        result = classify_deterministic(block)

        assert result is not None
        assert result["tag"] == "PMI"
        assert result["gate_rule"] == "gate-locked-style"
        assert result["confidence"] == 99
        assert result["gated"] is True

    def test_locked_marker_not_sent_to_llm(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "<CN>"),
            _block(2, "Normal body text paragraph."),
        ]
        blocks[0]["lock_style"] = True
        blocks[0]["allowed_styles"] = ["PMI"]
        blocks[0]["skip_llm"] = True

        gated, llm, metrics = gate_for_llm(blocks)

        assert len(gated) == 1
        assert gated[0]["id"] == 1
        assert gated[0]["tag"] == "PMI"

        assert len(llm) == 1
        assert llm[0]["id"] == 2

        assert metrics.rules_fired.get("gate-locked-style") == 1

    def test_skip_llm_marker_without_lock_style_not_sent_to_llm(self):
        """Regression: skip_llm alone must exclude marker from LLM if lock metadata is lost."""
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "<INSERT FIGURE 7.1 HERE>"),
            _block(2, "Normal body text paragraph."),
        ]
        blocks[0]["skip_llm"] = True
        blocks[0]["_is_marker"] = True

        gated, llm, metrics = gate_for_llm(blocks)

        gated_by_id = {c["id"]: c for c in gated}
        llm_ids = {b["id"] for b in llm}

        assert gated_by_id[1]["tag"] == "PMI"
        assert gated_by_id[1]["gate_rule"] == "gate-skip-llm"
        assert 1 not in llm_ids
        assert llm_ids == {2}
        assert metrics.rules_fired.get("gate-skip-llm") == 1


# ===================================================================
# End-to-end: lock → gate pipeline
# ===================================================================

class TestEndToEnd:

    def test_lock_then_gate(self):
        from processor.deterministic_gate import gate_for_llm

        blocks = [
            _block(1, "Introduction paragraph."),
            _block(2, "<CN>"),
            _block(3, "Chapter content."),
            _block(4, "<CT>"),
            _block(5, "More content."),
            _block(6, "<REF>"),
        ]

        # Step 1: lock markers
        blocks = lock_marker_blocks(blocks)

        # Step 2: gate for LLM
        gated, llm, metrics = gate_for_llm(blocks)

        gated_ids = {c["id"] for c in gated}
        llm_ids = {b["id"] for b in llm}

        # Markers (2, 4, 6) → gated as PMI via lock_style
        assert 2 in gated_ids
        assert 4 in gated_ids
        assert 6 in gated_ids

        gated_by_id = {c["id"]: c for c in gated}
        assert gated_by_id[2]["tag"] == "PMI"
        assert gated_by_id[4]["tag"] == "PMI"
        assert gated_by_id[6]["tag"] == "PMI"

        # Non-marker blocks → sent to LLM
        assert 1 in llm_ids
        assert 3 in llm_ids
        assert 5 in llm_ids


# ===================================================================
# Helper for classification dicts
# ===================================================================

def _clf(pid, tag, confidence=85, **extras):
    """Create a classification dict."""
    return {"id": pid, "tag": tag, "confidence": confidence, **extras}


# ===================================================================
# Idempotency tests
# ===================================================================

class TestIdempotency:
    """Verify running lock twice produces same result."""

    def test_lock_twice_same_result(self):
        """Running lock_marker_blocks twice should be idempotent."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "Normal paragraph"),
            _block(3, "<CT>"),
        ]

        # First pass
        result1 = lock_marker_blocks(blocks)
        # Second pass on same blocks
        result2 = lock_marker_blocks(result1)

        # Should be identical
        assert result1[0]["lock_style"] is True
        assert result2[0]["lock_style"] is True
        assert result1[0]["allowed_styles"] == result2[0]["allowed_styles"]
        assert result1[0]["skip_llm"] == result2[0]["skip_llm"]

        # Non-marker unchanged
        assert result1[1].get("lock_style") is not True
        assert result2[1].get("lock_style") is not True

    def test_relock_twice_same_result(self):
        """Running relock_marker_classifications twice should be idempotent."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "Normal text"),
        ]
        blocks[0]["_is_marker"] = True

        clfs = [
            _clf(1, "TXT"),  # Wrong
            _clf(2, "TXT"),  # Correct
        ]

        # First relock
        result1 = relock_marker_classifications(blocks, clfs)
        # Second relock
        result2 = relock_marker_classifications(blocks, result1)

        # Should be identical
        assert result1[0]["tag"] == "PMI"
        assert result2[0]["tag"] == "PMI"
        assert result1[0]["relocked"] is True
        # Second pass doesn't add relocked flag again (already PMI)
        assert result2[0].get("relocked") is True

    def test_text_never_modified_repeated_locks(self):
        """Text is preserved byte-for-byte across multiple lock passes."""
        original = "  <TAB6.1>  "
        blocks = [_block(1, original)]

        result1 = lock_marker_blocks(blocks)
        result2 = lock_marker_blocks(result1)
        result3 = lock_marker_blocks(result2)

        assert result1[0]["text"] == original
        assert result2[0]["text"] == original
        assert result3[0]["text"] == original


# ===================================================================
# Post-classification re-locking tests
# ===================================================================

class TestRelockMarkerClassifications:
    """Verify post-classification re-locking enforces PMI."""

    def test_marker_misclassified_as_txt(self):
        """Marker block classified as TXT → relocked to PMI."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True

        clfs = [_clf(1, "TXT")]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "PMI"
        assert result[0]["confidence"] == 99
        assert result[0]["relocked"] is True
        assert result[0]["original_tag"] == "TXT"

    def test_marker_misclassified_as_heading(self):
        """Marker block classified as heading → relocked to PMI."""
        blocks = [_block(1, "<H1-INTRO>")]
        blocks[0]["_is_marker"] = True

        clfs = [_clf(1, "SP-H1", confidence=95)]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "PMI"
        assert result[0]["relocked"] is True
        assert result[0]["original_tag"] == "SP-H1"

    def test_marker_already_pmi_unchanged(self):
        """Marker block already PMI → no relocking needed."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True

        clfs = [_clf(1, "PMI", confidence=99)]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "PMI"
        assert result[0].get("relocked") is not True
        assert "original_tag" not in result[0]

    def test_non_marker_unchanged(self):
        """Non-marker blocks are left unchanged."""
        blocks = [
            _block(1, "Normal paragraph"),
            _block(2, "Another paragraph"),
        ]

        clfs = [
            _clf(1, "TXT"),
            _clf(2, "TXT"),
        ]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "TXT"
        assert result[1]["tag"] == "TXT"
        assert result[0].get("relocked") is not True
        assert result[1].get("relocked") is not True

    def test_mixed_markers_and_non_markers(self):
        """Mixed document: only markers are relocked."""
        blocks = [
            _block(1, "Introduction"),
            _block(2, "<CN>"),
            _block(3, "Chapter content"),
            _block(4, "<CT>"),
            _block(5, "More content"),
        ]
        blocks[1]["_is_marker"] = True
        blocks[3]["_is_marker"] = True

        clfs = [
            _clf(1, "TXT"),
            _clf(2, "TXT"),  # Wrong
            _clf(3, "TXT"),
            _clf(4, "H1"),   # Wrong
            _clf(5, "TXT"),
        ]

        result = relock_marker_classifications(blocks, clfs)

        # Non-markers unchanged
        assert result[0]["tag"] == "TXT"
        assert result[2]["tag"] == "TXT"
        assert result[4]["tag"] == "TXT"

        # Markers relocked
        assert result[1]["tag"] == "PMI"
        assert result[1]["relocked"] is True
        assert result[3]["tag"] == "PMI"
        assert result[3]["relocked"] is True

    def test_detects_marker_without_flag(self):
        """Detects markers even without _is_marker flag (based on text pattern)."""
        blocks = [_block(1, "<REF>")]
        # No _is_marker flag set

        clfs = [_clf(1, "TXT")]

        result = relock_marker_classifications(blocks, clfs)

        # Should still detect as marker and relock
        assert result[0]["tag"] == "PMI"
        assert result[0]["relocked"] is True

    def test_multiple_markers_all_relocked(self):
        """All marker blocks are relocked if misclassified."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "<CT>"),
            _block(3, "<REF>"),
            _block(4, "<TAB6.1>"),
        ]
        for b in blocks:
            b["_is_marker"] = True

        clfs = [
            _clf(1, "H1"),
            _clf(2, "H1"),
            _clf(3, "TXT"),
            _clf(4, "TXT"),
        ]

        result = relock_marker_classifications(blocks, clfs)

        for i in range(4):
            assert result[i]["tag"] == "PMI"
            assert result[i]["relocked"] is True

    def test_empty_classifications(self):
        """Empty classifications list handled gracefully."""
        blocks = [_block(1, "<CN>")]
        clfs = []

        result = relock_marker_classifications(blocks, clfs)
        assert result == []

    def test_mismatched_ids(self):
        """Classifications with IDs not in blocks are skipped."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True

        clfs = [
            _clf(1, "TXT"),   # Exists
            _clf(99, "TXT"),  # No matching block
        ]

        result = relock_marker_classifications(blocks, clfs)

        # ID 1 relocked
        assert result[0]["tag"] == "PMI"
        # ID 99 unchanged (no matching block)
        assert result[1]["tag"] == "TXT"


# ===================================================================
# Leaked marker detection tests
# ===================================================================

class TestLeakedMarkerDetection:
    """Verify detection of markers that leaked to LLM."""

    def test_marker_with_llm_reasoning_detected(self, caplog):
        """Marker with skip_llm=True + LLM reasoning → case A true leak."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True  # had prior lock → case A

        clfs = [
            _clf(
                1,
                "TXT",
                reasoning="This appears to be a chapter number marker.",
                gated=False,
            )
        ]

        with caplog.at_level("WARNING"):
            result = relock_marker_classifications(blocks, clfs)

        # Should detect leak and log warning
        assert "leaked to LLM" in caplog.text
        assert "block 1" in caplog.text

        # Should still relock to PMI
        assert result[0]["tag"] == "PMI"

    def test_marker_not_gated_detected(self, caplog):
        """Marker with skip_llm=True + gated=False → case A true leak."""
        blocks = [_block(1, "<CT>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True  # had prior lock → case A

        clfs = [_clf(1, "PMI", gated=False)]

        with caplog.at_level("WARNING"):
            result = relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" in caplog.text

    def test_marker_properly_gated_no_leak(self, caplog):
        """Marker with gated=True and no reasoning → no leak."""
        blocks = [_block(1, "<REF>")]
        blocks[0]["_is_marker"] = True

        clfs = [_clf(1, "PMI", gated=True)]

        with caplog.at_level("WARNING"):
            result = relock_marker_classifications(blocks, clfs)

        assert "leaked" not in caplog.text

    def test_multiple_leaked_markers(self, caplog):
        """Multiple markers with skip_llm=True + LLM output → 2 case A leaks."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "<CT>"),
            _block(3, "<REF>"),
        ]
        for b in blocks:
            b["_is_marker"] = True
        # blocks 1 and 2 had prior lock; block 3 was properly gated
        blocks[0]["skip_llm"] = True
        blocks[1]["skip_llm"] = True

        clfs = [
            _clf(1, "TXT", reasoning="LLM analyzed this", gated=False),
            _clf(2, "TXT", reasoning="LLM analyzed this", gated=False),
            _clf(3, "PMI", gated=True),  # Proper
        ]

        with caplog.at_level("WARNING"):
            result = relock_marker_classifications(blocks, clfs)

        # Should log 2 leaks (blocks 1 and 2)
        warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
        assert len(warnings) == 2


# ===================================================================
# Case A vs Case B leak diagnostic correctness
# ===================================================================

class TestLeakDiagnosticCorrectness:
    """Case A (true skip_llm leak) vs Case B (no prior lock) distinction."""

    # ------------------------------------------------------------------
    # Case A: block had skip_llm=True — must fire WARNING + count metric
    # ------------------------------------------------------------------

    def test_case_a_gated_false_fires_warning(self, caplog):
        """Case A: skip_llm=True + gated=False → WARNING 'leaked to LLM'."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "TXT", gated=False)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" in caplog.text

    def test_case_a_reasoning_fires_warning(self, caplog):
        """Case A: skip_llm=True + reasoning (no rule_based) → WARNING."""
        blocks = [_block(1, "<CT>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "TXT", reasoning="LLM said so", gated=False)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" in caplog.text

    def test_case_a_counted_in_leaked_metric(self, caplog):
        """Case A leak increments leaked_to_llm in structured log."""
        blocks = [_block(1, "<REF>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "TXT", gated=False)]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked_to_llm=1" in caplog.text

    def test_case_a_still_relocks_to_pmi(self, caplog):
        """Case A: PMI enforcement still fires even when warning is emitted."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "H1", gated=False)]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "PMI"
        assert result[0].get("relocked") is True

    # ------------------------------------------------------------------
    # Case B: block has no skip_llm — must NOT fire WARNING; still relocks
    # ------------------------------------------------------------------

    def test_case_b_no_skip_llm_no_warning(self, caplog):
        """Case B: _is_marker=True but no skip_llm + gated=False → no WARNING."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        # skip_llm intentionally NOT set

        clfs = [_clf(1, "TXT", gated=False)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 0
        assert "leaked to LLM" not in caplog.text

    def test_case_b_not_counted_in_leaked_metric(self, caplog):
        """Case B does NOT increment leaked_to_llm counter."""
        blocks = [_block(1, "<CT>")]
        blocks[0]["_is_marker"] = True
        # skip_llm NOT set

        clfs = [_clf(1, "TXT", reasoning="LLM says TXT", gated=False)]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked_to_llm=0" in caplog.text

    def test_case_b_still_relocks_to_pmi(self):
        """Case B: PMI enforcement fires regardless (functional behavior unchanged)."""
        blocks = [_block(1, "<REF>")]
        blocks[0]["_is_marker"] = True
        # skip_llm NOT set

        clfs = [_clf(1, "TXT", gated=False)]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "PMI"
        assert result[0].get("relocked") is True

    def test_case_b_text_pattern_detection_also_no_warning(self, caplog):
        """Case B: marker detected by text pattern (no _is_marker flag, no skip_llm) → no WARNING."""
        blocks = [_block(1, "<TAB6.1>")]
        # Neither _is_marker nor skip_llm set — detected purely by text pattern

        clfs = [_clf(1, "TXT", gated=False)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" not in caplog.text

    # ------------------------------------------------------------------
    # Rule-based path: never a true LLM leak regardless of skip_llm
    # ------------------------------------------------------------------

    def test_rule_based_never_fires_warning(self, caplog):
        """rule_based=True is not a true LLM leak even with skip_llm=True."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "PMI", reasoning="rule: marker=PMI", rule_based=True)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" not in caplog.text

    def test_rule_based_not_counted_in_leaked_metric(self, caplog):
        """rule_based=True not counted as a leak even if skip_llm=True."""
        blocks = [_block(1, "<CT>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "PMI", reasoning="rule matched", rule_based=True)]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked_to_llm=0" in caplog.text

    # ------------------------------------------------------------------
    # Mixed scenario: case A + case B in same batch
    # ------------------------------------------------------------------

    def test_mixed_case_a_and_case_b_in_one_batch(self, caplog):
        """One case A (skip_llm=True) + one case B (no skip_llm) in same pass.

        Expects: 1 WARNING (case A), leaked_to_llm=1, both relocked to PMI.
        """
        blocks = [
            _block(1, "<CN>"),  # case A — had prior lock
            _block(2, "<CT>"),  # case B — no prior lock
        ]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True
        blocks[1]["_is_marker"] = True
        # blocks[1] has no skip_llm

        clfs = [
            _clf(1, "TXT", gated=False),  # case A: true leak
            _clf(2, "TXT", gated=False),  # case B: no lock metadata
        ]

        with caplog.at_level("WARNING"):
            result = relock_marker_classifications(blocks, clfs)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "block 1" in caplog.text
        assert result[0]["tag"] == "PMI"
        assert result[1]["tag"] == "PMI"

    def test_mixed_metric_counts_only_case_a(self, caplog):
        """leaked_to_llm metric counts only case A blocks."""
        blocks = [
            _block(1, "<CN>"),  # case A
            _block(2, "<CT>"),  # case B
            _block(3, "<REF>"),  # case A
        ]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True
        blocks[1]["_is_marker"] = True
        blocks[2]["_is_marker"] = True
        blocks[2]["skip_llm"] = True

        clfs = [
            _clf(1, "TXT", gated=False),
            _clf(2, "TXT", gated=False),
            _clf(3, "TXT", gated=False),
        ]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked_to_llm=2" in caplog.text


# ===================================================================
# Logging format tests
# ===================================================================

class TestLoggingFormat:
    """Verify structured logging format."""

    def test_pre_lock_logging(self, caplog):
        """Pre-lock emits MARKER_LOCK_PRE with markers_total."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "Normal"),
            _block(3, "<CT>"),
        ]

        with caplog.at_level("INFO"):
            lock_marker_blocks(blocks)

        # Should log "MARKER_LOCK_PRE markers_total=2"
        assert "MARKER_LOCK_PRE markers_total=2" in caplog.text

    def test_post_lock_logging(self, caplog):
        """Post-lock emits MARKER_LOCK with metrics."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "<CT>"),
            _block(3, "Normal"),
        ]
        for b in blocks[:2]:
            b["_is_marker"] = True

        clfs = [
            _clf(1, "TXT"),  # Wrong → relock
            _clf(2, "PMI"),  # Already correct
            _clf(3, "TXT"),  # Non-marker
        ]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        # Should log "MARKER_LOCK markers_total=2 relocked=1 leaked_to_llm=0"
        assert "MARKER_LOCK markers_total=2 relocked=1 leaked_to_llm=0" in caplog.text

    def test_post_lock_with_leaks(self, caplog):
        """Post-lock with case A leaked marker logs leaked_to_llm=1."""
        blocks = [
            _block(1, "<CN>"),
            _block(2, "<CT>"),
        ]
        for b in blocks:
            b["_is_marker"] = True
        blocks[0]["skip_llm"] = True  # block 1 had prior lock → case A

        clfs = [
            _clf(1, "TXT", reasoning="LLM output", gated=False),  # Case A leak
            _clf(2, "PMI", gated=True),  # Proper
        ]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        # leaked_to_llm=1
        assert "leaked_to_llm=1" in caplog.text

    def test_no_markers_no_logging(self, caplog):
        """No markers → no logging."""
        blocks = [_block(1, "Normal paragraph")]

        with caplog.at_level("INFO"):
            caplog.clear()
            lock_marker_blocks(blocks)

        # Should not log anything
        assert "MARKER_LOCK" not in caplog.text


# ===================================================================
# _is_marker_block helper tests
# ===================================================================

class TestIsMarkerBlock:
    """Test the _is_marker_block helper function."""

    def test_simple_marker(self):
        assert _is_marker_block("<CN>") is True
        assert _is_marker_block("<CT>") is True
        assert _is_marker_block("<REF>") is True

    def test_marker_with_whitespace(self):
        assert _is_marker_block("  <CN>  ") is True
        assert _is_marker_block("\t<CT>\n") is True

    def test_marker_with_content(self):
        assert _is_marker_block("<H1>Introduction") is False
        assert _is_marker_block("Prefix<CN>") is False

    def test_not_marker(self):
        assert _is_marker_block("Normal text") is False
        assert _is_marker_block("") is False
        assert _is_marker_block(None) is False
        assert _is_marker_block("   ") is False

    def test_invalid_markers(self):
        assert _is_marker_block("<<nested>>") is False
        assert _is_marker_block("<incomplete") is False
        assert _is_marker_block("<>") is False


# ===================================================================
# Provenance-based leak detection (llm_generated field)
# ===================================================================

class TestLlmGeneratedProvenance:
    """llm_generated=True is the canonical leak signal; reasoning alone is not."""

    def test_reasoning_alone_does_not_trigger_warning(self, caplog):
        """Deterministic output with reasoning but no gated=False / llm_generated → no warning."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        # Simulates a deterministic gate that adds reasoning text (gated=True)
        clfs = [_clf(1, "PMI", reasoning="Matched rule: marker=PMI", gated=True)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" not in caplog.text

    def test_llm_generated_true_triggers_case_a_warning(self, caplog):
        """llm_generated=True on a skip_llm block is a true Case A leak."""
        blocks = [_block(1, "<CT>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        # Simulates real LLM output: llm_generated=True, no gated field set
        clfs = [_clf(1, "TXT", llm_generated=True)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked to LLM" in caplog.text

    def test_llm_generated_true_counted_in_metric(self, caplog):
        """llm_generated=True leak increments leaked_to_llm counter."""
        blocks = [_block(1, "<REF>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "TXT", llm_generated=True)]

        with caplog.at_level("INFO"):
            relock_marker_classifications(blocks, clfs)

        assert "leaked_to_llm=1" in caplog.text

    def test_llm_generated_case_a_still_relocks_to_pmi(self):
        """PMI enforcement fires even when llm_generated leak is detected."""
        blocks = [_block(1, "<CN>")]
        blocks[0]["_is_marker"] = True
        blocks[0]["skip_llm"] = True

        clfs = [_clf(1, "H1", llm_generated=True)]

        result = relock_marker_classifications(blocks, clfs)

        assert result[0]["tag"] == "PMI"
        assert result[0].get("relocked") is True

    def test_llm_generated_without_skip_llm_no_warning(self, caplog):
        """llm_generated=True on a block without skip_llm is Case B — no WARNING."""
        blocks = [_block(1, "<TAB6.1>")]
        blocks[0]["_is_marker"] = True
        # skip_llm intentionally NOT set (Case B)

        clfs = [_clf(1, "TXT", llm_generated=True)]

        with caplog.at_level("WARNING"):
            relock_marker_classifications(blocks, clfs)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 0
        assert "leaked to LLM" not in caplog.text
