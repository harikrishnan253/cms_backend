"""
Tests for question_ref_normalizer.py — post-classification enforcement
of canonical tags for numbered questions and references.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import pytest

from processor.question_ref_normalizer import (
    normalize_reference_numbering,
    _ANY_NUMBER_RE,
    _NUM_DOT_RE,
    _NUM_PAREN_RE,
    _NUM_RPAREN_RE,
    _Q_NUM_RE,
)


# ===================================================================
# Helpers
# ===================================================================

def _block(pid, text, zone="BODY", **meta_overrides):
    meta = {"context_zone": zone}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


def _clf(pid, tag, confidence=85):
    return {"id": pid, "tag": tag, "confidence": confidence}


ALLOWED = {
    "QUES-NL-FIRST", "QUES-NL-MID", "QUES-NL-LAST",
    "QUES-TXT-FLUSH",
    "REV-QUES-NL-FIRST", "REV-QUES-NL-MID", "REV-QUES-NL-LAST",
    "REF-N", "REF-N0", "REF-U",
    "TXT", "TXT-FLUSH", "NL-MID", "NL-FIRST", "NL-LAST",
    "H1", "H2", "PMI",
    "EXER-SA-NL-FIRST", "EXER-SA-NL-MID",
    "BL-FIRST", "BL-MID", "BL-LAST",
    "EOC-NL-FIRST", "EOC-NL-MID", "EOC-NL-LAST",
}


# ===================================================================
# Test: Pattern detection
# ===================================================================

class TestPatternDetection:

    def test_num_dot(self):
        assert _NUM_DOT_RE.match("1. What is the answer?")
        assert _NUM_DOT_RE.match("  12. Second question")

    def test_num_paren(self):
        assert _NUM_PAREN_RE.match("(1) What is the answer?")
        assert _NUM_PAREN_RE.match("  (12) Second question")

    def test_num_rparen(self):
        assert _NUM_RPAREN_RE.match("1) What is the answer?")
        assert _NUM_RPAREN_RE.match("  12) Second question")

    def test_q_num(self):
        assert _Q_NUM_RE.match("Q1. What is the answer?")
        assert _Q_NUM_RE.match("q12. Second question")

    def test_any_number_re(self):
        for text in [
            "1. First",
            "(2) Second",
            "3) Third",
            "Q4. Fourth",
        ]:
            assert _ANY_NUMBER_RE.match(text), f"Should match: {text}"

    def test_non_matching(self):
        for text in [
            "The result was 1.0 units",
            "See table (1) for details",
            "Question about method",
            "",
        ]:
            assert not _ANY_NUMBER_RE.match(text), f"Should NOT match: {text}"


# ===================================================================
# Test: Question number recognized (EXERCISE zone)
# ===================================================================

class TestQuestionNumberRecognized:

    def test_num_dot_in_exercise_becomes_ques_nl(self):
        """'1. What is X?' in EXERCISE zone → QUES-NL-MID."""
        blocks = [_block(1, "1. What is the primary organ?", zone="EXERCISE")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"

    def test_paren_in_exercise_becomes_ques_nl(self):
        """'(1) What is X?' in EXERCISE zone → QUES-NL-MID."""
        blocks = [_block(1, "(1) Describe the process.", zone="EXERCISE")]
        clfs = [_clf(1, "NL-MID")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"

    def test_rparen_in_exercise_becomes_ques_nl(self):
        """'1) What is X?' in EXERCISE zone → QUES-NL-MID."""
        blocks = [_block(1, "1) Define the term.", zone="EXERCISE")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"

    def test_q_num_in_exercise_becomes_ques_nl(self):
        """'Q1. What is X?' in EXERCISE zone → QUES-NL-MID."""
        blocks = [_block(1, "Q1. Name the three parts.", zone="EXERCISE")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"

    def test_already_canonical_unchanged(self):
        """Block already tagged QUES-NL-MID stays unchanged."""
        blocks = [_block(1, "1. What is X?", zone="EXERCISE")]
        clfs = [_clf(1, "QUES-NL-MID")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"
        # Should NOT have repaired flag since already correct
        assert result[0] is clfs[0]

    def test_question_context_from_neighbors_in_body(self):
        """Numbered text in BODY near QUES-* neighbors → QUES-NL-MID."""
        blocks = [
            _block(1, "Questions", zone="BODY"),
            _block(2, "1. What is the answer?", zone="BODY"),
            _block(3, "2. Describe the process.", zone="BODY"),
        ]
        clfs = [
            _clf(1, "H2"),
            _clf(2, "QUES-NL-FIRST"),
            _clf(3, "TXT"),  # LLM misclassified
        ]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        # Block 3 has numbered text and a QUES-NL-FIRST neighbor → corrected
        assert result[2]["tag"] == "QUES-NL-MID"


# ===================================================================
# Test: List-numbered paragraph NOT mistaken for question
# ===================================================================

class TestListNotMistakenForQuestion:

    def test_body_numbered_list_untouched(self):
        """Numbered list in BODY zone (no question context) → unchanged."""
        blocks = [
            _block(1, "Introduction", zone="BODY"),
            _block(2, "1. First step of procedure.", zone="BODY"),
            _block(3, "2. Second step of procedure.", zone="BODY"),
        ]
        clfs = [
            _clf(1, "H1"),
            _clf(2, "NL-FIRST"),
            _clf(3, "NL-LAST"),
        ]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[1]["tag"] == "NL-FIRST"
        assert result[2]["tag"] == "NL-LAST"

    def test_word_xml_numbered_list_in_body_untouched(self):
        """Word XML numbered list in BODY zone → not overridden."""
        blocks = [
            _block(1, "1. First point.", zone="BODY", has_numbering=True),
            _block(2, "2. Second point.", zone="BODY", has_numbering=True),
        ]
        clfs = [
            _clf(1, "NL-FIRST"),
            _clf(2, "NL-LAST"),
        ]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "NL-FIRST"
        assert result[1]["tag"] == "NL-LAST"

    def test_non_numbered_text_untouched(self):
        """Text without numbering pattern → unchanged."""
        blocks = [_block(1, "This is regular body text.", zone="BODY")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "TXT"
        assert result[0] is clfs[0]  # No copy made


# ===================================================================
# Test: Reference lines in BACK_MATTER → REF-N
# ===================================================================

class TestReferenceNormalization:

    def test_numbered_ref_in_back_matter(self):
        """'1. WHO Global Report.' in BACK_MATTER → REF-N."""
        blocks = [_block(1, "1. WHO. Global Report 2020.", zone="BACK_MATTER")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "REF-N"

    def test_paren_ref_in_back_matter(self):
        """'(1) WHO.' in BACK_MATTER → REF-N."""
        blocks = [_block(1, "(1) WHO. Global Report.", zone="BACK_MATTER")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "REF-N"

    def test_already_ref_n_unchanged(self):
        """Already REF-N → no change."""
        blocks = [_block(1, "1. WHO. Report.", zone="BACK_MATTER")]
        clfs = [_clf(1, "REF-N")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0] is clfs[0]

    def test_ref_u_not_overridden(self):
        """REF-U (unnumbered ref) stays REF-U even with numbered text."""
        blocks = [_block(1, "1. WHO. Report.", zone="BACK_MATTER")]
        clfs = [_clf(1, "REF-U")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        # REF-U is in _CANONICAL_REF → left unchanged
        assert result[0] is clfs[0]


# ===================================================================
# Test: Invalid tag repaired via alias
# ===================================================================

class TestAliasRepair:

    def test_ques_num_alias_resolved(self):
        """Tag 'QUES_NUM' (with underscore) → resolved to QUES-NL-MID."""
        blocks = [_block(1, "Content here", zone="BODY")]
        clfs = [_clf(1, "QUES_NUM")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"
        assert result[0]["repaired"] is True
        assert "alias-resolved" in result[0]["repair_reason"]

    def test_ques_txt_alias_resolved(self):
        """Tag 'QUES_TXT' → resolved to QUES-TXT-FLUSH."""
        blocks = [_block(1, "What is the process?", zone="BODY")]
        clfs = [_clf(1, "QUES_TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-TXT-FLUSH"

    def test_ref_txt_alias_resolved(self):
        """Tag 'REF_TXT' → resolved to REF-N."""
        blocks = [_block(1, "Smith et al. 2020.", zone="BACK_MATTER")]
        clfs = [_clf(1, "REF_TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "REF-N"


# ===================================================================
# Test: Idempotency
# ===================================================================

class TestIdempotency:

    def test_double_run_same_result(self):
        """Running normalization twice produces identical output."""
        blocks = [
            _block(1, "1. What is X?", zone="EXERCISE"),
            _block(2, "2. Describe Y.", zone="EXERCISE"),
            _block(3, "1. WHO Report.", zone="BACK_MATTER"),
            _block(4, "Regular text.", zone="BODY"),
        ]
        clfs = [
            _clf(1, "TXT"),
            _clf(2, "NL-MID"),
            _clf(3, "TXT"),
            _clf(4, "TXT"),
        ]

        first = normalize_reference_numbering(blocks, clfs, ALLOWED)
        second = normalize_reference_numbering(blocks, first, ALLOWED)

        for a, b in zip(first, second):
            assert a["tag"] == b["tag"]

    def test_already_correct_returns_originals(self):
        """When all tags are already correct, original objects are returned."""
        blocks = [
            _block(1, "1. What is X?", zone="EXERCISE"),
        ]
        clfs = [_clf(1, "QUES-NL-MID")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0] is clfs[0]


# ===================================================================
# Test: allowed_styles enforcement
# ===================================================================

class TestAllowedStyles:

    def test_tag_not_in_allowed_skipped(self):
        """If the target tag is not in allowed_styles, skip it."""
        restricted_allowed = {"TXT", "NL-MID"}  # No QUES-NL-MID
        blocks = [_block(1, "1. What is X?", zone="EXERCISE")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, restricted_allowed)
        assert result[0]["tag"] == "TXT"  # Unchanged

    def test_none_allowed_skips_validation(self):
        """allowed_styles=None disables validation."""
        blocks = [_block(1, "1. What is X?", zone="EXERCISE")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, None)
        assert result[0]["tag"] == "QUES-NL-MID"


# ===================================================================
# Test: Text never modified
# ===================================================================

class TestTextPreservation:

    def test_text_untouched(self):
        """Paragraph text must never be modified."""
        original_text = "  1. What is the primary organ?  "
        blocks = [_block(1, original_text, zone="EXERCISE")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert blocks[0]["text"] == original_text


# ===================================================================
# Test: Edge cases
# ===================================================================

class TestEdgeCases:

    def test_empty_classifications(self):
        result = normalize_reference_numbering([], [], ALLOWED)
        assert result == []

    def test_empty_text_ignored(self):
        blocks = [_block(1, "", zone="EXERCISE")]
        clfs = [_clf(1, "PMI")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "PMI"

    def test_repair_reason_appended(self):
        """If clf already has a repair_reason, new reason is appended."""
        blocks = [_block(1, "1. What is X?", zone="EXERCISE")]
        clfs = [{"id": 1, "tag": "TXT", "confidence": 85,
                 "repaired": True, "repair_reason": "prior-fix"}]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert result[0]["tag"] == "QUES-NL-MID"
        assert "prior-fix" in result[0]["repair_reason"]
        assert "ques-number-detected" in result[0]["repair_reason"]

    def test_returns_list(self):
        blocks = [_block(1, "text", zone="BODY")]
        clfs = [_clf(1, "TXT")]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)
        assert isinstance(result, list)


# ===================================================================
# Test: Mixed document flow
# ===================================================================

class TestMixedDocument:

    def test_mixed_zones(self):
        """Questions in EXERCISE, refs in BACK_MATTER, body lists unchanged."""
        blocks = [
            _block(1, "Introduction", zone="BODY"),
            _block(2, "1. First procedure step.", zone="BODY"),
            _block(3, "Exercise", zone="EXERCISE"),
            _block(4, "1. What is X?", zone="EXERCISE"),
            _block(5, "2. Describe Y.", zone="EXERCISE"),
            _block(6, "References", zone="BACK_MATTER"),
            _block(7, "1. WHO. Global Report.", zone="BACK_MATTER"),
            _block(8, "(2) CDC. Report.", zone="BACK_MATTER"),
        ]
        clfs = [
            _clf(1, "H1"),
            _clf(2, "NL-FIRST"),
            _clf(3, "H1"),
            _clf(4, "TXT"),
            _clf(5, "TXT"),
            _clf(6, "H1"),
            _clf(7, "TXT"),
            _clf(8, "TXT"),
        ]
        result = normalize_reference_numbering(blocks, clfs, ALLOWED)

        # Body list → unchanged
        assert result[1]["tag"] == "NL-FIRST"

        # Exercise questions → QUES-NL-MID
        assert result[3]["tag"] == "QUES-NL-MID"
        assert result[4]["tag"] == "QUES-NL-MID"

        # References → REF-N
        assert result[6]["tag"] == "REF-N"
        assert result[7]["tag"] == "REF-N"

        # Headings → unchanged
        assert result[0]["tag"] == "H1"
        assert result[2]["tag"] == "H1"
        assert result[5]["tag"] == "H1"
