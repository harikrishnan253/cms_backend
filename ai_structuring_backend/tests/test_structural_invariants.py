"""Tests for shared structural invariant helpers."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.structural_invariants import (
    BlockTransformPolicy,
    assert_style_tag_only_block_transform,
    describe_structural_invariants,
    validate_block_transform_contract,
)


def _block(block_id, text, tag="TXT", **meta):
    return {
        "id": block_id,
        "text": text,
        "tag": tag,
        "metadata": meta or {"tag": tag},
    }


def test_describe_invariants_mentions_core_structures():
    text = describe_structural_invariants()
    assert "paragraph count/order" in text
    assert "list status/level/id" in text
    assert "heading levels" in text
    assert "table row/col counts" in text
    assert "section count/break types" in text


def test_style_tag_only_allows_tag_changes_only():
    before = [_block(1, "A", "TXT"), _block(2, "B", "H1")]
    after = [_block(1, "A", "PMI"), _block(2, "B", "TXT")]

    assert_style_tag_only_block_transform(before, after, stage="test-normalizer")


def test_style_tag_only_fails_on_length_change():
    before = [_block(1, "A"), _block(2, "B")]
    after = [_block(1, "A")]

    with pytest.raises(AssertionError, match="length_changed"):
        assert_style_tag_only_block_transform(before, after, stage="test-normalizer")


def test_style_tag_only_fails_on_reorder_and_includes_index_and_id():
    before = [_block(1, "A"), _block(2, "B")]
    after = [_block(2, "B"), _block(1, "A")]

    with pytest.raises(AssertionError) as exc:
        assert_style_tag_only_block_transform(before, after, stage="test-normalizer")

    msg = str(exc.value)
    assert "ordered_ids_changed" in msg
    assert "stage=test-normalizer" in msg
    assert "index=0" in msg
    assert "'id': 1" in msg or '"id": 1' in msg


def test_style_tag_only_fails_on_text_change():
    before = [_block(1, "A"), _block(2, "B")]
    after = [_block(1, "A changed"), _block(2, "B")]

    with pytest.raises(AssertionError, match="text_changed"):
        assert_style_tag_only_block_transform(before, after, stage="test-normalizer")


def test_policy_can_allow_text_changes_but_not_reorder():
    before = [_block(1, "Table 1.1"), _block(2, "<TAB1.1>", "PMI")]
    after = [_block(1, "Table 1.1:"), _block(2, "<TAB1.1>", "PMI")]
    policy = BlockTransformPolicy(allow_text_changes=True, stage_type="text_normalizer")

    validate_block_transform_contract(before, after, stage="reference-format", policy=policy)

