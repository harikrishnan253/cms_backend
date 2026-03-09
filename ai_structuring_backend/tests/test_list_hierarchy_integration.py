"""
Regression tests for list-hierarchy pipeline integration.

Covers the end-to-end path:
  extract_blocks() -> _enrich_list_metadata() -> list_hierarchy.py (pre-LLM lock)
  -> list_preservation.py (post-LLM enforcement)

Focus scenarios
---------------
* Nested bullet lists (ilvl 1/2) collapse to BL-MID  (the reported bug)
* Style-based bullets (no OOXML numPr) with indent evidence get correct level
* TABLE-zone items are never locked as list styles
* Numbered nested lists (NL2, NL3) are preserved correctly
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.list_hierarchy import enforce_list_hierarchy_from_word_xml
from processor.list_preservation import enforce_list_hierarchy_from_word_xml as preserve_list_hierarchy
from processor.blocks import _enrich_list_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block(pid: int, text: str = "List item", **meta_overrides) -> dict:
    meta = {"context_zone": "BODY"}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


def _clf(pid: int, tag: str) -> dict:
    return {"id": pid, "tag": tag}


# ===========================================================================
# _enrich_list_metadata — unit tests (no real DOCX needed)
# ===========================================================================

class TestEnrichListMetadata:
    """_enrich_list_metadata adds list_style_prefix & semantic_level."""

    def test_bullet_with_xml_list_level_gets_prefix(self):
        """xml_list_level=1 + has_bullet → list_style_prefix='BL2-'."""
        paragraphs = [
            {
                "id": 1,
                "text": "• Nested item",
                "metadata": {
                    "context_zone": "BODY",
                    "xml_list_level": 1,
                    "ooxml_ilvl": 1,     # alias already present
                    "has_bullet": True,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "BL2-"
        assert meta.get("semantic_level") == 1

    def test_bullet_level_0_gets_bl_prefix(self):
        paragraphs = [
            {
                "id": 1,
                "text": "• Top level",
                "metadata": {
                    "context_zone": "BODY",
                    "xml_list_level": 0,
                    "ooxml_ilvl": 0,
                    "has_bullet": True,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "BL-"
        assert meta.get("semantic_level") == 0

    def test_level_2_bullet_gets_bl3_prefix(self):
        paragraphs = [
            {
                "id": 1,
                "text": "• Deep nested",
                "metadata": {
                    "context_zone": "BODY",
                    "xml_list_level": 2,
                    "ooxml_ilvl": 2,
                    "has_bullet": True,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "BL3-"

    def test_indent_twips_level1_gets_bl2_prefix(self):
        """No xml_list_level; indent_twips=720 (level 1) → BL2-."""
        paragraphs = [
            {
                "id": 1,
                "text": "• Indented bullet",
                "metadata": {
                    "context_zone": "BODY",
                    "has_bullet": True,
                    "indent_twips": 720,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "BL2-"
        assert meta.get("indent_source") == "ooxml_ind"

    def test_tab_indent_level1_gets_bl2_prefix(self):
        """No xml_list_level; tab-indented text bullet → BL2-."""
        paragraphs = [
            {
                "id": 1,
                "text": "\t• Indented via tab",
                "metadata": {"context_zone": "BODY", "has_bullet": True},
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "BL2-"

    def test_existing_list_style_prefix_not_overwritten(self):
        """If list_style_prefix is already set, it must not be changed."""
        paragraphs = [
            {
                "id": 1,
                "text": "• Item",
                "metadata": {
                    "context_zone": "BODY",
                    "has_bullet": True,
                    "xml_list_level": 1,
                    "ooxml_ilvl": 1,
                    "list_style_prefix": "KT-BL2-",  # already set externally
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        # Must not overwrite
        assert result[0]["metadata"]["list_style_prefix"] == "KT-BL2-"

    def test_xml_keys_never_overwritten(self):
        """xml_list_level, xml_num_id, has_bullet, has_numbering are unchanged."""
        paragraphs = [
            {
                "id": 1,
                "text": "• Item",
                "metadata": {
                    "context_zone": "BODY",
                    "xml_list_level": 1,
                    "xml_num_id": 5,
                    "has_bullet": True,
                    "has_numbering": False,
                    "has_xml_list": False,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta["xml_list_level"] == 1
        assert meta["xml_num_id"] == 5
        assert meta["has_bullet"] is True
        assert meta["has_numbering"] is False

    def test_non_list_paragraph_untouched(self):
        """Regular body text paragraphs receive no list metadata."""
        paragraphs = [
            {
                "id": 1,
                "text": "Regular body text without any bullet.",
                "metadata": {"context_zone": "BODY"},
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert "list_style_prefix" not in meta
        assert "semantic_level" not in meta

    def test_numbered_list_level1_gets_nl2_prefix(self):
        """Numbered list with xml_list_level=1 → list_style_prefix='NL2-'."""
        paragraphs = [
            {
                "id": 1,
                "text": "1. Sub-item",
                "metadata": {
                    "context_zone": "BODY",
                    "xml_list_level": 1,
                    "ooxml_ilvl": 1,
                    "has_numbering": True,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "NL2-"


# ===========================================================================
# list_hierarchy.py — list_style_prefix fallback (pre-LLM lock)
# ===========================================================================

class TestListHierarchyPrefixFallback:
    """enforce_list_hierarchy_from_word_xml locks using list_style_prefix
    when xml_list_level is absent."""

    def test_bl2_prefix_locks_to_bl2_mid(self):
        """list_style_prefix='BL2-' without xml_list_level → locked to BL2-MID."""
        blocks = [
            _block(
                1,
                "• Nested bullet",
                has_bullet=True,
                list_style_prefix="BL2-",
            )
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["lock_style"] is True
        assert result[0]["allowed_styles"] == ["BL2-MID"]
        assert result[0]["skip_llm"] is True

    def test_bl3_prefix_locks_to_bl3_mid(self):
        blocks = [
            _block(1, "• Deeply nested", has_bullet=True, list_style_prefix="BL3-")
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL3-MID"]

    def test_bl_prefix_locks_to_bl_mid(self):
        blocks = [_block(1, "• Top", has_bullet=True, list_style_prefix="BL-")]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["BL-MID"]

    def test_nl2_prefix_locks_to_nl2_mid(self):
        blocks = [
            _block(1, "1. Sub", has_numbering=True, list_style_prefix="NL2-")
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0]["allowed_styles"] == ["NL2-MID"]

    def test_no_prefix_and_no_xml_level_not_locked(self):
        """Without both xml_list_level and list_style_prefix → not locked."""
        blocks = [_block(1, "• Item", has_bullet=True)]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True

    def test_xml_level_takes_priority_over_prefix(self):
        """When xml_list_level is present, OOXML path runs (ignores prefix)."""
        blocks = [
            _block(
                1,
                "• Item",
                has_bullet=True,
                xml_list_level=1,          # OOXML says level 1
                list_style_prefix="BL-",   # prefix says level 0 (different)
            )
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        # OOXML wins: BL2-MID, NOT BL-MID
        assert result[0]["allowed_styles"] == ["BL2-MID"]

    def test_table_zone_never_locked_via_prefix(self):
        """TABLE zone paragraphs must not be locked even with list_style_prefix."""
        blocks = [
            _block(
                1,
                "• Cell bullet",
                context_zone="TABLE",
                has_bullet=True,
                list_style_prefix="BL2-",
            )
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True

    def test_table_zone_never_locked_via_xml_level(self):
        """TABLE zone paragraphs are skipped even when xml_list_level is set."""
        blocks = [
            _block(
                1,
                "• Cell bullet",
                context_zone="TABLE",
                has_bullet=True,
                xml_list_level=1,
            )
        ]
        result = enforce_list_hierarchy_from_word_xml(blocks)
        assert result[0].get("lock_style") is not True


# ===========================================================================
# list_preservation.py — list_style_prefix fallback (post-LLM correction)
# ===========================================================================

class TestListPreservationPrefixFallback:
    """enforce_list_hierarchy_from_word_xml (preservation version) corrects
    LLM-misclassified tags using list_style_prefix when xml_list_level absent."""

    def test_bl_mid_corrected_to_bl2_mid_via_prefix(self):
        """LLM said BL-MID for a level-1 item; prefix says BL2-; should correct."""
        blocks = [
            _block(
                1,
                "• Nested item",
                has_bullet=True,
                list_style_prefix="BL2-",
            )
        ]
        classifications = [_clf(1, "BL-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "BL2-MID"
        assert result[0].get("list_preserved") is True

    def test_already_correct_not_overridden(self):
        """BL2-MID is already compatible with list_style_prefix='BL2-'."""
        blocks = [
            _block(1, "• Nested", has_bullet=True, list_style_prefix="BL2-")
        ]
        classifications = [_clf(1, "BL2-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "BL2-MID"
        assert result[0].get("list_preserved") is not True

    def test_bl_first_corrected_to_bl2_first_via_prefix(self):
        """Position suffix preserved when correcting family."""
        blocks = [
            _block(1, "• First nested", has_bullet=True, list_style_prefix="BL2-")
        ]
        classifications = [_clf(1, "BL-FIRST")]
        result = preserve_list_hierarchy(blocks, classifications)
        # Should be BL2-FIRST (preserve position, fix family)
        assert result[0]["tag"] == "BL2-FIRST"

    def test_nl_mid_corrected_to_nl2_mid_via_prefix(self):
        blocks = [
            _block(1, "1. Sub", has_numbering=True, list_style_prefix="NL2-")
        ]
        classifications = [_clf(1, "NL-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "NL2-MID"

    def test_no_prefix_no_xml_level_not_corrected(self):
        """Without prefix or xml_list_level, classification is unchanged."""
        blocks = [_block(1, "• Item", has_bullet=True)]
        classifications = [_clf(1, "TXT")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "TXT"

    def test_xml_level_path_still_works(self):
        """Original OOXML path still works: xml_list_level=1 → BL2-MID."""
        blocks = [
            _block(1, "• Nested", has_bullet=True, xml_list_level=1)
        ]
        classifications = [_clf(1, "TXT")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "BL2-MID"


# ===========================================================================
# End-to-end: "flattened BL-MID" prevention scenarios
# ===========================================================================

class TestFlattenedBLMIDPrevention:
    """Full-path tests: enrichment → pre-LLM lock → post-LLM preservation."""

    def _enrich_and_lock(self, blocks):
        """Simulate extract_blocks enrichment then list_hierarchy lock."""
        # Manually apply enrichment (no real DOCX; metadata pre-populated)
        enriched = _enrich_list_metadata(blocks, docx_path=None)
        return enforce_list_hierarchy_from_word_xml(enriched)

    def test_three_level_hierarchy_all_locked_correctly(self):
        """A 3-level OOXML list is locked at correct BL/BL2/BL3 levels."""
        blocks = [
            _block(1, "• Top", has_bullet=True, xml_list_level=0),
            _block(2, "• Nested", has_bullet=True, xml_list_level=1),
            _block(3, "• Deep nested", has_bullet=True, xml_list_level=2),
            _block(4, "Body text"),   # non-list
        ]
        result = self._enrich_and_lock(blocks)

        assert result[0]["allowed_styles"] == ["BL-MID"]
        assert result[1]["allowed_styles"] == ["BL2-MID"]
        assert result[2]["allowed_styles"] == ["BL3-MID"]
        assert result[3].get("lock_style") is not True

    def test_indent_only_nested_list_locked_correctly(self):
        """Style-based bullet (no OOXML numPr) with tab indent gets BL2-MID."""
        blocks = [
            _block(1, "• Top level", has_bullet=True),
            _block(2, "\t• Nested via tab", has_bullet=True),
        ]
        result = self._enrich_and_lock(blocks)

        assert result[0]["allowed_styles"] == ["BL-MID"]
        assert result[1]["allowed_styles"] == ["BL2-MID"]

    def test_indent_twips_nested_list_locked_correctly(self):
        """Style-based bullet with indent_twips=720 (Level 1) → BL2-MID."""
        blocks = [
            _block(1, "• Top", has_bullet=True, indent_twips=0),
            _block(2, "• Nested", has_bullet=True, indent_twips=720),
        ]
        result = self._enrich_and_lock(blocks)

        assert result[0]["allowed_styles"] == ["BL-MID"]
        assert result[1]["allowed_styles"] == ["BL2-MID"]

    def test_no_generic_bl_mid_for_nested_ooxml_items(self):
        """Specifically: nested ilvl=1 items must never be locked to BL-MID."""
        blocks = [
            _block(1, "• Level 0", has_bullet=True, xml_list_level=0),
            _block(2, "• Level 1", has_bullet=True, xml_list_level=1),
            _block(3, "• Level 2", has_bullet=True, xml_list_level=2),
        ]
        result = self._enrich_and_lock(blocks)

        for b in result:
            # BL-MID must only appear for level-0 items
            if b["id"] != 1:
                assert b["allowed_styles"] != ["BL-MID"], (
                    f"Block {b['id']} (level {b['id'] - 1}) was wrongly assigned BL-MID"
                )

    def test_numbered_nested_no_generic_nl_mid(self):
        blocks = [
            _block(1, "1. Item", has_numbering=True, xml_list_level=0),
            _block(2, "a. Sub-item", has_numbering=True, xml_list_level=1),
        ]
        result = self._enrich_and_lock(blocks)

        assert result[0]["allowed_styles"] == ["NL-MID"]
        assert result[1]["allowed_styles"] == ["NL2-MID"]

    def test_table_zone_not_locked(self):
        """TABLE-zone list items must never receive lock_style regardless of level."""
        blocks = [
            _block(1, "• Table bullet", context_zone="TABLE",
                   has_bullet=True, xml_list_level=1, list_style_prefix="BL2-"),
        ]
        result = self._enrich_and_lock(blocks)
        assert result[0].get("lock_style") is not True

    def test_post_llm_correction_when_llm_flattened(self):
        """If LLM was not locked and returned BL-MID, preservation must fix it."""
        blocks = [
            _block(2, "• Nested", has_bullet=True, xml_list_level=1),
        ]
        # Simulate: enrichment sets list_style_prefix, but block NOT locked (no
        # lock_style set) — LLM classified it as BL-MID (wrong level)
        _enrich_list_metadata(blocks, docx_path=None)
        classifications = [_clf(2, "BL-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "BL2-MID"

    def test_xml_list_no_bullet_flag_gets_bl_default(self):
        """has_xml_list=True, no has_bullet/has_numbering, level 0 → BL-MID."""
        blocks = [_block(1, "XML list item", has_xml_list=True, xml_list_level=0)]
        result = self._enrich_and_lock(blocks)
        # OOXML path: family = UL (ambiguous); but note: this tests that it IS locked
        assert result[0].get("lock_style") is True


# ===========================================================================
# Regression: TABLE zone is never overridden by list_style_prefix fallback
# ===========================================================================

class TestTableZonePreservationFallback:
    """list_preservation.py must not override TABLE-zone tags via prefix fallback."""

    def test_table_tbl_mid_not_overridden_when_prefix_set(self):
        """TBL-MID must survive even if list_style_prefix='BL-' is present."""
        blocks = [
            _block(
                1,
                "• Cell item",
                context_zone="TABLE",
                has_bullet=True,
                list_style_prefix="BL-",   # hypothetically set by detector
            )
        ]
        classifications = [_clf(1, "TBL-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "TBL-MID"
        assert result[0].get("list_preserved") is not True

    def test_table_zone_nested_prefix_not_overridden(self):
        """TBL-MID must survive list_style_prefix='BL2-' in TABLE zone."""
        blocks = [
            _block(
                1,
                "• Cell item",
                context_zone="TABLE",
                has_bullet=True,
                list_style_prefix="BL2-",
            )
        ]
        classifications = [_clf(1, "TBL-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "TBL-MID"

    def test_table_zone_xml_level_path_also_skipped(self):
        """TABLE zone + xml_list_level set → TBL-MID must not become BL2-MID.

        The top-level TABLE guard now fires before the OOXML path, so even the
        contrived case of a TABLE paragraph with xml_list_level=1 is safe.
        """
        blocks = [
            _block(
                1,
                "• Cell",
                context_zone="TABLE",
                has_bullet=True,
                xml_list_level=1,
            )
        ]
        classifications = [_clf(1, "TBL-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        assert result[0]["tag"] == "TBL-MID"
        assert result[0].get("list_preserved") is not True


# ===========================================================================
# Text-without-bullet-glyph: OOXML-only detection
# ===========================================================================

class TestOoxmlOnlyDetection:
    """Paragraphs with no visible bullet glyph but OOXML numPr must be
    enriched and locked correctly."""

    def test_has_xml_list_level1_gets_bl2_prefix(self):
        """has_xml_list=True, xml_list_level=1 (no visible bullet) → BL2-."""
        paragraphs = [
            {
                "id": 1,
                "text": "Nested item without visible bullet glyph",
                "metadata": {
                    "context_zone": "BODY",
                    "has_xml_list": True,
                    "xml_list_level": 1,
                },
            }
        ]
        result = _enrich_list_metadata(paragraphs, docx_path=None)
        meta = result[0]["metadata"]
        assert meta.get("list_style_prefix") == "BL2-"
        assert meta.get("semantic_level") == 1
        assert meta.get("indent_source") == "ooxml_ilvl"

    def test_has_xml_list_level1_locked_to_bl2_mid(self):
        """End-to-end: no-glyph OOXML level 1 list → locked to UL2-MID (OOXML
        family) by list_hierarchy.py (has_xml_list → UL family)."""
        blocks = [
            _block(
                1,
                "Nested OOXML item",
                has_xml_list=True,
                xml_list_level=1,
            )
        ]
        from processor.blocks import _enrich_list_metadata
        enriched = _enrich_list_metadata(blocks, docx_path=None)
        from processor.list_hierarchy import enforce_list_hierarchy_from_word_xml
        locked = enforce_list_hierarchy_from_word_xml(enriched)
        # OOXML path uses has_xml_list → UL family → UL2-MID
        assert locked[0]["allowed_styles"] == ["UL2-MID"]
        assert locked[0]["skip_llm"] is True

    def test_has_xml_list_level1_preservation_corrects_to_bl2(self):
        """Post-LLM: UL2-MID (from lock) is accepted by preservation as-is
        because _determine_list_type('has_xml_list') → 'bullet' → expected BL2-MID,
        but UL2-MID is NOT compatible with BL2-MID → corrected to BL2-MID."""
        blocks = [
            _block(
                1,
                "Nested OOXML item",
                has_xml_list=True,
                xml_list_level=1,
            )
        ]
        # After deterministic gate assigned UL2-MID (99% confidence):
        classifications = [_clf(1, "UL2-MID")]
        result = preserve_list_hierarchy(blocks, classifications)
        # list_preservation: xml_level=1, list_type='bullet' → expected BL2-MID
        # UL2-MID is not compatible with BL2-MID → corrected
        assert result[0]["tag"] == "BL2-MID"
