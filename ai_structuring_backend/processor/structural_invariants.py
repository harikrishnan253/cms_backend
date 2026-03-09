"""
Centralized structural integrity invariants and lightweight stage assertions.

Structural invariants (hard gates downstream must preserve):
- Paragraph count and order (same paragraph index mapping)
- List semantics at each paragraph index (`is_list`, `list_level`, `list_id`)
- Heading level at each paragraph index
- Table row/column counts
- Section count and break types

Block-level transform contract (default for normalizers/locks):
- Preserve block count
- Preserve ordered block IDs
- Preserve block text unless the stage explicitly allows text edits
- Preserve block IDs (no rewrites)

These checks are deterministic and cheap (O(n)); they are intended for
pre/post assertions around risky pipeline stages to localize the first stage
that introduced structural mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


# Metadata keys that commonly mirror document structure and are useful in
# diagnostics. These are not enforced here (some stages may add/fix them), but
# we include them in snapshots so failures are immediately actionable.
STRUCTURAL_METADATA_KEYS = (
    "heading_level",
    "is_list",
    "list_level",
    "list_id",
    "in_table",
    "section_index",
    "skip_llm",
    "lock_style",
)


@dataclass(frozen=True)
class BlockTransformPolicy:
    """Policy for validating a block transform stage."""

    allow_length_change: bool = False
    allow_reorder: bool = False
    allow_id_rewrite: bool = False
    allow_text_changes: bool = True
    stage_type: str = "block_transform"


STYLE_TAG_ONLY_POLICY = BlockTransformPolicy(
    allow_length_change=False,
    allow_reorder=False,
    allow_id_rewrite=False,
    allow_text_changes=False,
    stage_type="style_tag_only",
)


def describe_structural_invariants() -> str:
    """Return a human-readable summary of the centralized invariants contract."""
    return (
        "Structural invariants: paragraph count/order, list status/level/id, "
        "heading levels, table row/col counts, section count/break types. "
        "Block transforms must preserve count and ordered IDs by default."
    )


def snapshot_block_ordered_ids(blocks: Sequence[dict]) -> list[object]:
    """Return ordered block IDs for a sequence (cheap pre/post snapshot)."""
    return [block.get("id") for block in blocks]


def snapshot_blocks_for_contract(blocks: Sequence[dict]) -> list[dict]:
    """Create a lightweight immutable snapshot for pre/post contract checks."""
    snapshots: list[dict] = []
    for block in blocks:
        meta = block.get("metadata")
        meta_copy = dict(meta) if isinstance(meta, dict) else meta
        snapshots.append(
            {
                "id": block.get("id"),
                "text": block.get("text", ""),
                "tag": block.get("tag"),
                "metadata": meta_copy,
            }
        )
    return snapshots


def validate_block_transform_contract(
    before_blocks: Sequence[dict],
    after_blocks: Sequence[dict],
    *,
    stage: str,
    policy: BlockTransformPolicy = STYLE_TAG_ONLY_POLICY,
) -> None:
    """Validate the structural contract for a block-transform stage.

    Raises
    ------
    AssertionError
        If the transform violates the configured contract.
    """
    before_len = len(before_blocks)
    after_len = len(after_blocks)
    if not policy.allow_length_change and before_len != after_len:
        raise AssertionError(
            f"BLOCK_STRUCTURE_CONTRACT_FAIL stage={stage} reason=length_changed "
            f"policy={policy.stage_type} input_len={before_len} output_len={after_len}"
        )

    min_len = min(before_len, after_len)
    before_ids = [before_blocks[i].get("id") for i in range(min_len)]
    after_ids = [after_blocks[i].get("id") for i in range(min_len)]

    if not policy.allow_reorder:
        if before_ids != after_ids:
            idx = _first_index_diff(before_ids, after_ids)
            raise AssertionError(
                _format_contract_failure(
                    stage=stage,
                    reason="ordered_ids_changed",
                    policy=policy,
                    index=idx,
                    before_block=before_blocks[idx] if idx is not None and idx < before_len else None,
                    after_block=after_blocks[idx] if idx is not None and idx < after_len else None,
                )
            )
    elif not policy.allow_id_rewrite:
        if sorted(_safe_str_list(before_ids)) != sorted(_safe_str_list(after_ids)):
            raise AssertionError(
                f"BLOCK_STRUCTURE_CONTRACT_FAIL stage={stage} reason=id_set_changed "
                f"policy={policy.stage_type}"
            )

    if not policy.allow_id_rewrite and policy.allow_reorder:
        for idx in range(min_len):
            if before_blocks[idx].get("id") != after_blocks[idx].get("id"):
                # Reorder is allowed, so only detect explicit ID rewrites by keying on text/position
                # is not meaningful here. Skip per-index check.
                break
    elif not policy.allow_id_rewrite:
        for idx in range(min_len):
            if before_blocks[idx].get("id") != after_blocks[idx].get("id"):
                raise AssertionError(
                    _format_contract_failure(
                        stage=stage,
                        reason="id_rewritten",
                        policy=policy,
                        index=idx,
                        before_block=before_blocks[idx],
                        after_block=after_blocks[idx],
                    )
                )

    if not policy.allow_text_changes:
        for idx in range(min_len):
            before_text = str(before_blocks[idx].get("text", ""))
            after_text = str(after_blocks[idx].get("text", ""))
            if before_text != after_text:
                raise AssertionError(
                    _format_contract_failure(
                        stage=stage,
                        reason="text_changed",
                        policy=policy,
                        index=idx,
                        before_block=before_blocks[idx],
                        after_block=after_blocks[idx],
                    )
                )


def assert_style_tag_only_block_transform(
    before_blocks: Sequence[dict],
    after_blocks: Sequence[dict],
    *,
    stage: str,
) -> None:
    """Shared helper for tests and normalizers enforcing style/tag-only edits."""
    validate_block_transform_contract(
        before_blocks,
        after_blocks,
        stage=stage,
        policy=STYLE_TAG_ONLY_POLICY,
    )


def _first_index_diff(left: Sequence[object], right: Sequence[object]) -> int | None:
    for idx, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return idx
    if len(left) != len(right):
        return min(len(left), len(right))
    return None


def _safe_str_list(values: Iterable[object]) -> list[str]:
    return [str(v) for v in values]


def _format_contract_failure(
    *,
    stage: str,
    reason: str,
    policy: BlockTransformPolicy,
    index: int | None,
    before_block: dict | None,
    after_block: dict | None,
) -> str:
    return (
        f"BLOCK_STRUCTURE_CONTRACT_FAIL stage={stage} reason={reason} "
        f"policy={policy.stage_type} index={index if index is not None else 'n/a'} "
        f"before={_block_snapshot(before_block)} after={_block_snapshot(after_block)}"
    )


def _block_snapshot(block: dict | None) -> dict | None:
    if block is None:
        return None
    meta = block.get("metadata", {}) if isinstance(block.get("metadata"), dict) else {}
    meta_struct = {k: meta.get(k) for k in STRUCTURAL_METADATA_KEYS if k in meta}
    snapshot = {
        "id": block.get("id"),
        "tag": block.get("tag"),
        "text": _text_preview(block.get("text", "")),
    }
    if meta_struct:
        snapshot["metadata"] = meta_struct
    return snapshot


def _text_preview(text: object, limit: int = 80) -> str:
    s = str(text or "")
    return s if len(s) <= limit else (s[: limit - 3] + "...")
