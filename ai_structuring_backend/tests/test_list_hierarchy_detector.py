"""
Tests for indent-based list hierarchy detection.

Key principle under test: INDENTATION determines list level, NOT bullet symbol.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Ensure backend is importable
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from processor.list_hierarchy_detector import (
    ListHierarchyDetector,
    ListItemInfo,
    ParentContextTracker,
    assign_list_positions,
    process_list_hierarchy,
    BULLET_CHARACTERS,
    INDENT_THRESHOLDS,
)


# =============================================================================
# ListHierarchyDetector.detect() tests
# =============================================================================

class TestBulletDetection:
    """Test that bullet characters are detected regardless of symbol."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_filled_circle_bullet(self):
        info = self.detector.detect("\u2022 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u2022"

    def test_open_circle_bullet(self):
        info = self.detector.detect("\u25cb Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u25cb"

    def test_square_bullet(self):
        info = self.detector.detect("\u25a0 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u25a0"

    def test_triangle_bullet(self):
        info = self.detector.detect("\u25b2 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u25b2"

    def test_diamond_bullet(self):
        info = self.detector.detect("\u25c6 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u25c6"

    def test_arrow_bullet(self):
        info = self.detector.detect("\u27a2 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u27a2"

    def test_checkmark_bullet(self):
        info = self.detector.detect("\u2713 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u2713"

    def test_dash_bullet(self):
        info = self.detector.detect("- Item text")
        assert info.is_list is True
        assert info.bullet_char == "-"

    def test_wingdings_bullet(self):
        info = self.detector.detect("\uf0b7 Item text")
        assert info.is_list is True
        assert info.bullet_char == "\uf0b7"

    def test_not_a_list(self):
        info = self.detector.detect("Regular paragraph text without bullet")
        assert info.is_list is False

    def test_empty_text(self):
        info = self.detector.detect("")
        assert info.is_list is False

    def test_whitespace_only(self):
        info = self.detector.detect("   ")
        assert info.is_list is False

    def test_o_space_circle_bullet(self):
        """Word sometimes uses lowercase 'o' + space for circle bullets."""
        info = self.detector.detect("o Item text")
        assert info.is_list is True
        assert info.bullet_char == "\u25cb"


class TestNumberedListDetection:
    """Test numbered list prefix detection."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_decimal_dot(self):
        info = self.detector.detect("1. First item")
        assert info.is_list is True
        assert info.is_numbered is True
        assert info.number_format == "decimal"

    def test_decimal_paren(self):
        info = self.detector.detect("1) First item")
        assert info.is_list is True
        assert info.is_numbered is True
        assert info.number_format == "decimal_paren"

    def test_decimal_both_parens(self):
        info = self.detector.detect("(1) First item")
        assert info.is_list is True
        assert info.is_numbered is True
        assert info.number_format == "decimal_both"

    def test_lower_alpha(self):
        info = self.detector.detect("a. First item")
        assert info.is_list is True
        assert info.is_numbered is True
        assert info.number_format == "lower_alpha"

    def test_lower_alpha_paren(self):
        info = self.detector.detect("a) First item")
        assert info.is_list is True
        assert info.is_numbered is True
        assert info.number_format == "lower_alpha_paren"

    def test_upper_alpha(self):
        info = self.detector.detect("A. First item")
        assert info.is_list is True
        assert info.is_numbered is True
        assert info.number_format == "upper_alpha"

    def test_lower_roman(self):
        info = self.detector.detect("iii. Third item")
        assert info.is_list is True
        assert info.is_numbered is True

    def test_upper_roman(self):
        info = self.detector.detect("IV. Fourth item")
        assert info.is_list is True
        assert info.is_numbered is True


class TestIndentLevelFromWhitespace:
    """Test that indentation (tabs/spaces) determines the level, not the bullet symbol."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_no_indent_is_level_0(self):
        info = self.detector.detect("\u2022 Level 0 item")
        assert info.indent_level == 0
        assert info.style_prefix == "BL-"

    def test_one_tab_is_level_1(self):
        info = self.detector.detect("\t\u2022 Level 1 item")
        assert info.indent_level == 1
        assert info.style_prefix == "BL2-"

    def test_two_tabs_is_level_2(self):
        info = self.detector.detect("\t\t\u2022 Level 2 item")
        assert info.indent_level == 2
        assert info.style_prefix == "BL3-"

    def test_four_spaces_is_level_1(self):
        info = self.detector.detect("    \u2022 Level 1 item")
        assert info.indent_level == 1
        assert info.style_prefix == "BL2-"

    def test_eight_spaces_is_level_2(self):
        info = self.detector.detect("        \u2022 Level 2 item")
        assert info.indent_level == 2
        assert info.style_prefix == "BL3-"

    def test_level_capped_at_2(self):
        """More than 2 levels still maps to level 2."""
        info = self.detector.detect("\t\t\t\u2022 Deep item")
        assert info.indent_level == 2

    def test_bullet_symbol_does_not_determine_level(self):
        """The SAME bullet symbol at different indents -> different levels."""
        info_0 = self.detector.detect("\u25a0 Item at level 0")
        info_1 = self.detector.detect("\t\u25a0 Item at level 1")
        info_2 = self.detector.detect("\t\t\u25a0 Item at level 2")

        assert info_0.indent_level == 0
        assert info_1.indent_level == 1
        assert info_2.indent_level == 2

        # All have the same bullet char
        assert info_0.bullet_char == info_1.bullet_char == info_2.bullet_char == "\u25a0"

    def test_different_bullets_same_indent_same_level(self):
        """Different bullet symbols at the same indent -> same level."""
        info_circle = self.detector.detect("\t\u25cf Item")
        info_square = self.detector.detect("\t\u25a0 Item")
        info_arrow = self.detector.detect("\t\u27a2 Item")

        assert info_circle.indent_level == info_square.indent_level == info_arrow.indent_level == 1


class TestIndentLevelFromMetadata:
    """Test indent detection from OOXML metadata."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_ooxml_ilvl_0(self):
        info = self.detector.detect(
            "\u2022 Item",
            metadata={'has_bullet': True, 'ooxml_ilvl': 0}
        )
        assert info.indent_level == 0
        assert info.indent_source == 'ooxml_ilvl'

    def test_ooxml_ilvl_1(self):
        info = self.detector.detect(
            "\u2022 Item",
            metadata={'has_bullet': True, 'ooxml_ilvl': 1}
        )
        assert info.indent_level == 1
        assert info.indent_source == 'ooxml_ilvl'

    def test_ooxml_ilvl_2(self):
        info = self.detector.detect(
            "\u2022 Item",
            metadata={'has_bullet': True, 'ooxml_ilvl': 2}
        )
        assert info.indent_level == 2
        assert info.indent_source == 'ooxml_ilvl'

    def test_ooxml_ilvl_capped_at_2(self):
        info = self.detector.detect(
            "\u2022 Item",
            metadata={'has_bullet': True, 'ooxml_ilvl': 5}
        )
        assert info.indent_level == 2  # Capped

    def test_xml_list_detection(self):
        """Items marked as XML lists in metadata are detected."""
        info = self.detector.detect(
            "Item without visible bullet",
            metadata={'has_xml_list': True}
        )
        assert info.is_list is True


class TestTwipsToLevel:
    """Test twips-to-level conversion."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_zero_twips_is_level_0(self):
        assert self.detector._twips_to_level(0) == 0

    def test_360_twips_is_level_0(self):
        assert self.detector._twips_to_level(360) == 0

    def test_361_twips_is_level_1(self):
        assert self.detector._twips_to_level(361) == 1

    def test_720_twips_is_level_1(self):
        assert self.detector._twips_to_level(720) == 1

    def test_1080_twips_is_level_1(self):
        assert self.detector._twips_to_level(1080) == 1

    def test_1081_twips_is_level_2(self):
        assert self.detector._twips_to_level(1081) == 2

    def test_1440_twips_is_level_2(self):
        assert self.detector._twips_to_level(1440) == 2


class TestStylePrefix:
    """Test that style prefix is set correctly based on level and type."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_bullet_level_0_prefix(self):
        info = self.detector.detect("\u2022 Item")
        assert info.style_prefix == "BL-"

    def test_bullet_level_1_prefix(self):
        info = self.detector.detect("\t\u2022 Item")
        assert info.style_prefix == "BL2-"

    def test_bullet_level_2_prefix(self):
        info = self.detector.detect("\t\t\u2022 Item")
        assert info.style_prefix == "BL3-"

    def test_numbered_level_0_prefix(self):
        info = self.detector.detect("1. Item")
        assert info.style_prefix == "NL-"

    def test_numbered_level_1_prefix(self):
        info = self.detector.detect("\t1. Item")
        assert info.style_prefix == "NL2-"

    def test_numbered_level_2_prefix(self):
        info = self.detector.detect("\t\t1. Item")
        assert info.style_prefix == "NL3-"


# =============================================================================
# ParentContextTracker tests
# =============================================================================

class TestParentContextTracker:
    """Test parent context promotion logic."""

    def test_no_promotion_without_parent(self):
        tracker = ParentContextTracker()
        info = ListItemInfo(is_list=True, semantic_level=1)
        level = tracker.update(info)
        assert level == 1

    def test_parent_trigger_activates_promotion(self):
        tracker = ParentContextTracker()

        # Parent trigger at level 1
        parent = ListItemInfo(is_list=True, semantic_level=1, is_parent_trigger=True)
        level = tracker.update(parent)
        assert level == 1  # Parent stays at 1

        # Child at level 1 should be promoted to 2
        child = ListItemInfo(is_list=True, semantic_level=1, is_parent_trigger=False)
        level = tracker.update(child)
        assert level == 2  # Promoted!

    def test_level_0_resets_context(self):
        tracker = ParentContextTracker()

        # Activate parent
        parent = ListItemInfo(is_list=True, semantic_level=1, is_parent_trigger=True)
        tracker.update(parent)

        # Level 0 resets
        level0 = ListItemInfo(is_list=True, semantic_level=0)
        tracker.update(level0)

        # Next level 1 should NOT be promoted
        child = ListItemInfo(is_list=True, semantic_level=1, is_parent_trigger=False)
        level = tracker.update(child)
        assert level == 1  # Not promoted

    def test_heading_resets_context(self):
        tracker = ParentContextTracker()

        # Activate parent
        parent = ListItemInfo(is_list=True, semantic_level=1, is_parent_trigger=True)
        tracker.update(parent)

        # Heading resets
        heading = ListItemInfo(is_list=False, semantic_level=0)
        tracker.update(heading, is_heading=True)

        # Next level 1 should NOT be promoted
        child = ListItemInfo(is_list=True, semantic_level=1, is_parent_trigger=False)
        level = tracker.update(child)
        assert level == 1

    def test_level_2_stays_at_2(self):
        tracker = ParentContextTracker()
        info = ListItemInfo(is_list=True, semantic_level=2)
        level = tracker.update(info)
        assert level == 2

    def test_level_0_parent_trigger(self):
        tracker = ParentContextTracker()

        # Level 0 parent trigger
        parent = ListItemInfo(is_list=True, semantic_level=0, is_parent_trigger=True)
        level = tracker.update(parent)
        assert level == 0
        assert tracker.parent_active is True
        assert tracker.parent_level == 0


# =============================================================================
# ParentTrigger detection tests
# =============================================================================

class TestParentTrigger:
    """Test parent trigger detection in list items."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_colon_ending_short_text(self):
        info = self.detector.detect("\u2022 Grading:")
        assert info.is_parent_trigger is True

    def test_diagnosis_colon(self):
        info = self.detector.detect("\u2022 Diagnosis:")
        assert info.is_parent_trigger is True

    def test_management_colon(self):
        info = self.detector.detect("\u2022 Management:")
        assert info.is_parent_trigger is True

    def test_treatment_colon(self):
        info = self.detector.detect("\u2022 Treatment:")
        assert info.is_parent_trigger is True

    def test_types_colon(self):
        info = self.detector.detect("\u2022 Types:")
        assert info.is_parent_trigger is True

    def test_classification_pattern(self):
        info = self.detector.detect("\u2022 Staging (TNM 8.0)")
        assert info.is_parent_trigger is True

    def test_long_text_not_trigger(self):
        info = self.detector.detect(
            "\u2022 This is a very long list item that contains a lot of detail about something important and should not be treated as a parent trigger"
        )
        assert info.is_parent_trigger is False

    def test_normal_item_not_trigger(self):
        info = self.detector.detect("\u2022 Administer 500mg oral medication daily")
        assert info.is_parent_trigger is False


# =============================================================================
# assign_list_positions() tests
# =============================================================================

class TestAssignListPositions:
    """Test FIRST/MID/LAST position assignment for Level 0 items."""

    def test_single_item_gets_first(self):
        paragraphs = [{'id': 1, 'text': 'Item 1'}]
        classifications = [{'id': 1, 'tag': 'BL-MID'}]

        result = assign_list_positions(paragraphs, classifications)
        assert result[0]['tag'] == 'BL-FIRST'

    def test_two_items_first_and_last(self):
        paragraphs = [
            {'id': 1, 'text': 'Item 1'},
            {'id': 2, 'text': 'Item 2'},
        ]
        classifications = [
            {'id': 1, 'tag': 'BL-MID'},
            {'id': 2, 'tag': 'BL-MID'},
        ]

        result = assign_list_positions(paragraphs, classifications)
        assert result[0]['tag'] == 'BL-FIRST'
        assert result[1]['tag'] == 'BL-LAST'

    def test_three_items_first_mid_last(self):
        paragraphs = [
            {'id': 1, 'text': 'Item 1'},
            {'id': 2, 'text': 'Item 2'},
            {'id': 3, 'text': 'Item 3'},
        ]
        classifications = [
            {'id': 1, 'tag': 'BL-MID'},
            {'id': 2, 'tag': 'BL-MID'},
            {'id': 3, 'tag': 'BL-MID'},
        ]

        result = assign_list_positions(paragraphs, classifications)
        assert result[0]['tag'] == 'BL-FIRST'
        assert result[1]['tag'] == 'BL-MID'
        assert result[2]['tag'] == 'BL-LAST'

    def test_h1_starts_new_section(self):
        paragraphs = [
            {'id': 1, 'text': 'Item 1'},
            {'id': 2, 'text': 'Section'},
            {'id': 3, 'text': 'Item 2'},
        ]
        classifications = [
            {'id': 1, 'tag': 'BL-MID'},
            {'id': 2, 'tag': 'H1'},
            {'id': 3, 'tag': 'BL-MID'},
        ]

        result = assign_list_positions(paragraphs, classifications)
        assert result[0]['tag'] == 'BL-FIRST'  # Only item in section 1
        assert result[2]['tag'] == 'BL-FIRST'  # Only item in section 2

    def test_nested_items_not_affected(self):
        """BL2/BL3 items should not get FIRST/LAST positions."""
        paragraphs = [
            {'id': 1, 'text': 'Item 1'},
            {'id': 2, 'text': 'Sub item'},
            {'id': 3, 'text': 'Item 2'},
        ]
        classifications = [
            {'id': 1, 'tag': 'BL-MID'},
            {'id': 2, 'tag': 'BL2-MID'},
            {'id': 3, 'tag': 'BL-MID'},
        ]

        result = assign_list_positions(paragraphs, classifications)
        assert result[0]['tag'] == 'BL-FIRST'
        assert result[1]['tag'] == 'BL2-MID'  # Unchanged
        assert result[2]['tag'] == 'BL-LAST'

    def test_numbered_list_positions(self):
        paragraphs = [
            {'id': 1, 'text': '1. Item 1'},
            {'id': 2, 'text': '2. Item 2'},
            {'id': 3, 'text': '3. Item 3'},
        ]
        classifications = [
            {'id': 1, 'tag': 'NL-MID'},
            {'id': 2, 'tag': 'NL-MID'},
            {'id': 3, 'tag': 'NL-MID'},
        ]

        result = assign_list_positions(paragraphs, classifications)
        assert result[0]['tag'] == 'NL-FIRST'
        assert result[1]['tag'] == 'NL-MID'
        assert result[2]['tag'] == 'NL-LAST'

    def test_run_in_headings_excluded(self):
        """Run-in headings like 'Definitions' should not participate in position assignment."""
        paragraphs = [
            {'id': 1, 'text': 'Definitions'},
            {'id': 2, 'text': 'Item 1'},
            {'id': 3, 'text': 'Item 2'},
        ]
        classifications = [
            {'id': 1, 'tag': 'BL-MID'},
            {'id': 2, 'tag': 'BL-MID'},
            {'id': 3, 'tag': 'BL-MID'},
        ]

        result = assign_list_positions(paragraphs, classifications)
        # 'Definitions' is excluded from position assignment
        assert result[0]['tag'] == 'BL-MID'  # Excluded - unchanged
        assert result[1]['tag'] == 'BL-FIRST'
        assert result[2]['tag'] == 'BL-LAST'


# =============================================================================
# process_list_hierarchy() integration tests
# =============================================================================

class TestProcessListHierarchy:
    """Integration tests for the full pipeline."""

    def test_basic_flat_list(self):
        paragraphs = [
            {'id': 1, 'text': '\u2022 Item 1', 'metadata': {}},
            {'id': 2, 'text': '\u2022 Item 2', 'metadata': {}},
            {'id': 3, 'text': '\u2022 Item 3', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        for para in result:
            meta = para['metadata']
            assert meta['is_list'] is True
            assert meta['semantic_level'] == 0
            assert meta['list_style_prefix'] == 'BL-'

    def test_nested_list_by_indent(self):
        paragraphs = [
            {'id': 1, 'text': '\u2022 Parent item', 'metadata': {}},
            {'id': 2, 'text': '\t\u2022 Child item', 'metadata': {}},
            {'id': 3, 'text': '\t\t\u2022 Grandchild item', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        assert result[0]['metadata']['semantic_level'] == 0
        assert result[0]['metadata']['list_style_prefix'] == 'BL-'
        assert result[1]['metadata']['semantic_level'] == 1
        assert result[1]['metadata']['list_style_prefix'] == 'BL2-'
        assert result[2]['metadata']['semantic_level'] == 2
        assert result[2]['metadata']['list_style_prefix'] == 'BL3-'

    def test_mixed_bullet_symbols_same_indent(self):
        """Different bullet symbols at same indent = same level."""
        paragraphs = [
            {'id': 1, 'text': '\u25cf Item with filled circle', 'metadata': {}},
            {'id': 2, 'text': '\u25a0 Item with square', 'metadata': {}},
            {'id': 3, 'text': '\u25b2 Item with triangle', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        for para in result:
            assert para['metadata']['semantic_level'] == 0

    def test_same_bullet_different_indents(self):
        """Same bullet symbol at different indents = different levels."""
        paragraphs = [
            {'id': 1, 'text': '\u25cf Level 0', 'metadata': {}},
            {'id': 2, 'text': '\t\u25cf Level 1', 'metadata': {}},
            {'id': 3, 'text': '\u25cf Back to Level 0', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        assert result[0]['metadata']['semantic_level'] == 0
        assert result[1]['metadata']['semantic_level'] == 1
        assert result[2]['metadata']['semantic_level'] == 0

    def test_non_list_paragraphs_pass_through(self):
        paragraphs = [
            {'id': 1, 'text': 'Regular paragraph', 'metadata': {}},
            {'id': 2, 'text': '\u2022 List item', 'metadata': {}},
            {'id': 3, 'text': 'Another paragraph', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        assert result[0]['metadata']['is_list'] is False
        assert result[1]['metadata']['is_list'] is True
        assert result[2]['metadata']['is_list'] is False

    def test_heading_resets_parent_context(self):
        paragraphs = [
            {'id': 1, 'text': '\u2022 Grading:', 'metadata': {}},
            {'id': 2, 'text': '\t\u2022 Sub item', 'metadata': {}},
            {'id': 3, 'text': '<h1>New Section', 'metadata': {}},
            {'id': 4, 'text': '\t\u2022 Should not be promoted', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        # After heading, level 1 items should NOT be promoted
        assert result[3]['metadata']['semantic_level'] == 1

    def test_numbered_list_detection(self):
        paragraphs = [
            {'id': 1, 'text': '1. First item', 'metadata': {}},
            {'id': 2, 'text': '2. Second item', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        for para in result:
            meta = para['metadata']
            assert meta['is_list'] is True
            assert meta['is_numbered'] is True
            assert meta['list_style_prefix'] == 'NL-'
            assert meta['list_kind'] == 'numbered'

    def test_xml_list_metadata_detection(self):
        """Items with has_bullet in metadata are detected even without visible bullet."""
        paragraphs = [
            {'id': 1, 'text': 'XML list item', 'metadata': {'has_bullet': True}},
        ]

        result = process_list_hierarchy(paragraphs)
        assert result[0]['metadata']['is_list'] is True

    def test_metadata_preserved(self):
        """Original metadata fields are preserved."""
        paragraphs = [
            {
                'id': 1,
                'text': '\u2022 Item',
                'metadata': {
                    'style_name': 'List Bullet',
                    'context_zone': 'BODY',
                    'custom_field': 'preserved',
                }
            },
        ]

        result = process_list_hierarchy(paragraphs)
        meta = result[0]['metadata']
        assert meta['style_name'] == 'List Bullet'
        assert meta['context_zone'] == 'BODY'
        assert meta['custom_field'] == 'preserved'
        assert meta['is_list'] is True


# =============================================================================
# BULLET_CHARACTERS constant tests
# =============================================================================

class TestBulletCharacters:
    """Verify bullet characters set is complete."""

    def test_common_bullets_included(self):
        assert '\u2022' in BULLET_CHARACTERS  # bullet
        assert '\u25cf' in BULLET_CHARACTERS  # filled circle
        assert '\u25cb' in BULLET_CHARACTERS  # open circle
        assert '\u25a0' in BULLET_CHARACTERS  # filled square
        assert '\u25b2' in BULLET_CHARACTERS  # triangle
        assert '\u25c6' in BULLET_CHARACTERS  # diamond
        assert '\u2713' in BULLET_CHARACTERS  # checkmark
        assert '\u27a2' in BULLET_CHARACTERS  # arrow
        assert '-' in BULLET_CHARACTERS       # dash

    def test_wingdings_included(self):
        assert '\uf0b7' in BULLET_CHARACTERS
        assert '\uf0a7' in BULLET_CHARACTERS
        assert '\uf0fc' in BULLET_CHARACTERS


# =============================================================================
# INDENT_THRESHOLDS constant tests
# =============================================================================

class TestIndentThresholds:
    """Verify threshold values."""

    def test_level_0_max(self):
        assert INDENT_THRESHOLDS['level_0_max'] == 360

    def test_level_1_max(self):
        assert INDENT_THRESHOLDS['level_1_max'] == 1080


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_bullet_with_no_text_after(self):
        info = self.detector.detect("\u2022")
        assert info.is_list is True

    def test_none_text(self):
        info = self.detector.detect(None)
        assert info.is_list is False

    def test_very_long_text(self):
        info = self.detector.detect("\u2022 " + "x" * 10000)
        assert info.is_list is True

    def test_mixed_tabs_and_spaces(self):
        info = self.detector.detect("\t  \u2022 Item")  # 1 tab + 2 spaces
        assert info.indent_level == 1  # tab counts as 1 level

    def test_process_empty_list(self):
        result = process_list_hierarchy([])
        assert result == []

    def test_process_no_lists(self):
        paragraphs = [
            {'id': 1, 'text': 'No lists here', 'metadata': {}},
            {'id': 2, 'text': 'Just plain text', 'metadata': {}},
        ]
        result = process_list_hierarchy(paragraphs)
        assert all(p['metadata']['is_list'] is False for p in result)


# =============================================================================
# Bittner document scenario tests (ooxml_ilvl priority)
# =============================================================================

class TestOoxmlIlvlPriority:
    """
    Tests matching the Bittner document analysis.
    ooxml_ilvl from metadata MUST take priority over paragraph index lookup.
    """

    def setup_method(self):
        self.detector = ListHierarchyDetector()

    def test_ilvl_0_maps_to_level_0(self):
        """ilvl=0 from OOXML -> BL-* (Level 0)."""
        info = self.detector.detect(
            "Definitions",
            metadata={'has_bullet': True, 'ooxml_ilvl': 0}
        )
        assert info.is_list is True
        assert info.indent_level == 0
        assert info.indent_source == 'ooxml_ilvl'
        assert info.style_prefix == 'BL-'

    def test_ilvl_1_maps_to_level_1(self):
        """ilvl=1 from OOXML -> BL2-* (Level 1)."""
        info = self.detector.detect(
            "Grading diarrhea (CTCAE 5.0)",
            metadata={'has_bullet': True, 'ooxml_ilvl': 1}
        )
        assert info.is_list is True
        assert info.indent_level == 1
        assert info.indent_source == 'ooxml_ilvl'
        assert info.style_prefix == 'BL2-'

    def test_ilvl_2_maps_to_level_2(self):
        """ilvl=2 from OOXML -> BL3-* (Level 2)."""
        info = self.detector.detect(
            "Grade 1: Increase of <4 stools per day",
            metadata={'has_bullet': True, 'ooxml_ilvl': 2}
        )
        assert info.is_list is True
        assert info.indent_level == 2
        assert info.indent_source == 'ooxml_ilvl'
        assert info.style_prefix == 'BL3-'

    def test_ilvl_overrides_whitespace(self):
        """ooxml_ilvl takes priority even when text has no indentation."""
        info = self.detector.detect(
            "Grading diarrhea (CTCAE 5.0)",  # no tabs/spaces
            metadata={'has_bullet': True, 'ooxml_ilvl': 1}
        )
        # Should be level 1 from ilvl, NOT level 0 from whitespace
        assert info.indent_level == 1
        assert info.indent_source == 'ooxml_ilvl'

    def test_ilvl_zero_takes_priority_over_para_index(self):
        """ooxml_ilvl=0 takes priority even if _paragraph_indents would say level 1."""
        info = self.detector.detect(
            "Definitions",
            para_index=5,  # might match a wrong paragraph indent
            metadata={'has_bullet': True, 'ooxml_ilvl': 0}
        )
        assert info.indent_level == 0
        assert info.indent_source == 'ooxml_ilvl'

    def test_indent_twips_from_metadata(self):
        """indent_twips from metadata (ingestion) used when ilvl not available."""
        info = self.detector.detect(
            "Some list item",
            metadata={'has_bullet': True, 'indent_twips': 720}
        )
        assert info.is_list is True
        assert info.indent_level == 1  # 720 twips = level 1
        assert info.indent_source == 'ooxml_ind'


class TestBittnerFullPipeline:
    """Integration tests simulating the Bittner document structure."""

    def test_three_level_hierarchy_from_ilvl(self):
        """Simulate Bittner: triangle=L0, circle=L1, wingdings=L2."""
        paragraphs = [
            {'id': 1, 'text': 'Definitions', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 0}},
            {'id': 2, 'text': 'Grading diarrhea (CTCAE 5.0)', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 1}},
            {'id': 3, 'text': 'Grade 1: Increase of <4 stools', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 2}},
            {'id': 4, 'text': 'Grade 2: Increase of 4-6 stools', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 2}},
            {'id': 5, 'text': 'Grade 3: Increase of >=7 stools', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 2}},
            {'id': 6, 'text': 'Work-up (imaging)', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 1}},
            {'id': 7, 'text': 'Review concomitant medications', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 2}},
            {'id': 8, 'text': 'Blood (CBC, CMP, and TSH)', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 2}},
            {'id': 9, 'text': 'Epidemiology', 'metadata': {'has_bullet': True, 'ooxml_ilvl': 0}},
        ]

        result = process_list_hierarchy(paragraphs)

        # Level 0 items
        assert result[0]['metadata']['semantic_level'] == 0
        assert result[0]['metadata']['list_style_prefix'] == 'BL-'
        assert result[8]['metadata']['semantic_level'] == 0
        assert result[8]['metadata']['list_style_prefix'] == 'BL-'

        # Level 1 items
        assert result[1]['metadata']['semantic_level'] == 1
        assert result[1]['metadata']['list_style_prefix'] == 'BL2-'
        assert result[5]['metadata']['semantic_level'] == 1
        assert result[5]['metadata']['list_style_prefix'] == 'BL2-'

        # Level 2 items
        for idx in [2, 3, 4, 6, 7]:
            assert result[idx]['metadata']['semantic_level'] == 2
            assert result[idx]['metadata']['list_style_prefix'] == 'BL3-'

    def test_back_matter_references_vs_suggested_readings(self):
        """Numbered items in BACK_MATTER should get SR (via classifier, not detector)."""
        paragraphs = [
            {'id': 1, 'text': '1. Brahmer JR et al. J Clin Oncol. 2018',
             'metadata': {'context_zone': 'BACK_MATTER'}},
            {'id': 2, 'text': '2. Thompson JA et al. NCCN Guidelines. 2022',
             'metadata': {'context_zone': 'BACK_MATTER'}},
        ]

        result = process_list_hierarchy(paragraphs)
        # These are numbered lists detected in back matter
        for para in result:
            assert para['metadata']['is_list'] is True
            assert para['metadata']['is_numbered'] is True

    def test_mixed_levels_no_ilvl_falls_back_to_whitespace(self):
        """Without ooxml_ilvl, falls back to text whitespace for level."""
        paragraphs = [
            {'id': 1, 'text': '\u25b2 Definitions', 'metadata': {}},
            {'id': 2, 'text': '\t\u25cb Grading', 'metadata': {}},
            {'id': 3, 'text': '\t\t\uf0b7 Grade 1', 'metadata': {}},
        ]

        result = process_list_hierarchy(paragraphs)

        assert result[0]['metadata']['semantic_level'] == 0
        assert result[0]['metadata']['indent_source'] == 'text_whitespace'
        assert result[1]['metadata']['semantic_level'] == 1
        assert result[2]['metadata']['semantic_level'] == 2
