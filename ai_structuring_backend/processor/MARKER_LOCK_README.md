# Marker Block Locking System

## Overview

The marker lock system ensures structural marker paragraphs (e.g., `<CN>`, `<REF>`, `<TAB6.1>`) are never altered by heuristics, LLM classification, or downstream normalization passes.

**SOURCE OF TRUTH**: Marker text must remain byte-for-byte identical. Only metadata/style tags are modified.

## What are Marker Blocks?

Marker blocks are paragraphs containing **only** structural directive tokens used by the workflow:

- `<CN>` (chapter number)
- `<CT>` (chapter title)
- `<REF>` (reference section)
- `<TAB6.1>` (table marker with ID)
- `<H1-INTRO>` (heading marker)
- `<INSERT FIG...>` (figure insertion directive)
- `<INSERT TAB...>` (table insertion directive)
- Any all-caps angle-bracket directive token

**Pattern**: `^<[^<>]+>$` (angle-bracketed content, no nested brackets, no trailing content)

### Examples

**Matched as markers**:
- `<CN>` ✓
- `<CT>` ✓
- `  <REF>  ` ✓ (whitespace trimmed for matching)
- `<TAB6.1>` ✓
- `<H1-INTRO>` ✓

**NOT matched** (has content or invalid format):
- `<H1>Introduction` ✗ (has content after marker)
- `<<nested>>` ✗ (nested brackets)
- `<incomplete` ✗ (missing closing bracket)

## Two-Phase Locking Architecture

### Phase 1: Pre-LLM Lock (Stage 1b)

**Function**: `lock_marker_blocks(blocks) -> list[dict]`

**When**: BEFORE LLM classification (Stage 1b in pipeline)

**Purpose**: Mark marker blocks so they skip LLM entirely

**Actions**:
1. Identifies marker-only paragraphs using pattern `^<[^<>]+>$`
2. Sets metadata flags:
   - `block["lock_style"] = True`
   - `block["allowed_styles"] = ["PMI"]`
   - `block["skip_llm"] = True`
   - `block["_is_marker"] = True` (tracking flag)
3. Emits: `MARKER_LOCK_PRE markers_total=<int>`

**Effect**: Deterministic gate (Rule 0) assigns PMI at 99% confidence, bypassing LLM

### Phase 2: Post-Classification Re-lock (Stage 3.5)

**Function**: `relock_marker_classifications(blocks, classifications) -> list[dict]`

**When**: AFTER LLM classification, BEFORE reconstruction (Stage 3.5 in pipeline)

**Purpose**: Enforce PMI tag on markers even if downstream passes changed them

**Actions**:
1. Identifies marker blocks (via `_is_marker` flag OR text pattern)
2. Checks if classification tag is PMI
3. Overrides non-PMI tags back to PMI
4. Detects leaks (markers that reached LLM despite `skip_llm=True`)
5. Emits: `MARKER_LOCK markers_total=<int> relocked=<int> leaked_to_llm=<int>`

**Effect**: Markers are ALWAYS PMI in final output, regardless of what happened in between

## Rules (STRICT)

1. **Marker blocks must have PMI style** in final output (not MARKER - PMI is the canonical tag in this codebase)
2. **Excluded from**:
   - LLM classification eligibility (`skip_llm=True`)
   - Heuristics style inference
   - List/table enforcement (except adjacency rules that explicitly rely on markers)
3. **Marker text must not be edited, reflowed, normalized, or stripped** - byte-for-byte preservation
4. **Idempotent**: Running lock functions multiple times produces same result

## Pipeline Integration

```python
# Stage 1b: Pre-LLM locks
blocks = lock_marker_blocks(blocks)  # Phase 1
blocks = enforce_table_title_rules(blocks)
blocks = normalize_reference_numbering(blocks)
blocks = enforce_list_hierarchy_from_word_xml(blocks)
blocks = restrict_allowed_styles_per_zone(blocks)

# Stage 2: Classification
classifications, token_usage = classify_blocks_with_prompt(...)

# Stage 3.5: Post-classification normalization
blocks = normalize_reference_labels(blocks)
blocks = normalize_table_titles(blocks)
blocks = normalize_reference_format(blocks)

# Sync block tags to classifications
block_tags = {b["id"]: b.get("tag") for b in blocks if "tag" in b}
for clf in classifications:
    if clf["id"] in block_tags and block_tags[clf["id"]]:
        clf["tag"] = block_tags[clf["id"]]

# Enforce list hierarchy
classifications = preserve_list_hierarchy(blocks, classifications)

# Re-lock markers (FINAL AUTHORITY) - Phase 2
classifications = relock_marker_classifications(blocks, classifications)
```

## Logging

### Pre-LLM Lock (Stage 1b)
```
MARKER_LOCK_PRE markers_total=5
```

- `markers_total`: Number of marker blocks found and locked

### Post-Classification Re-lock (Stage 3.5)
```
MARKER_LOCK markers_total=5 relocked=2 leaked_to_llm=0
```

- `markers_total`: Total marker blocks in document
- `relocked`: Markers that were changed by downstream passes and re-locked to PMI
- `leaked_to_llm`: Markers that were sent to LLM despite `skip_llm=True` flag (indicates bug)

### Leak Warning
```
WARNING: marker-lock: block 42 leaked to LLM despite skip_llm flag (text='<CN>')
```

Emitted when a marker block has:
- `gated=False` (should be `True` for gated blocks)
- `reasoning` field present (indicates LLM processed it)

## API

### `lock_marker_blocks(blocks: Sequence[dict]) -> list[dict]`

Pre-LLM lock function.

**Parameters**:
- `blocks`: Block list from `extract_blocks()`. Modified **in-place**.

**Returns**:
- Same block objects (identity), for chaining convenience.

**Side effects**:
- Sets `lock_style`, `allowed_styles`, `skip_llm`, `_is_marker` on marker blocks

### `relock_marker_classifications(blocks, classifications) -> list[dict]`

Post-classification re-lock function.

**Parameters**:
- `blocks`: Block list with text and metadata
- `classifications`: Classification list that may need correction

**Returns**:
- Corrected classifications with marker blocks enforced to PMI

**Side effects**:
- Modifies classification dicts to set `tag="PMI"`, `confidence=99`, `relocked=True`

### `_is_marker_block(text: str) -> bool`

Helper to check if text matches marker pattern.

**Parameters**:
- `text`: Paragraph text

**Returns**:
- `True` if marker-only paragraph, `False` otherwise

## Examples

### Example 1: LLM Misclassifies Marker as Text

**Input (from ingestion)**:
```python
Block: {id: 1, text: "<CN>", metadata: {...}}
```

**After Pre-LLM Lock**:
```python
Block: {
    id: 1,
    text: "<CN>",
    lock_style: True,
    allowed_styles: ["PMI"],
    skip_llm: True,
    _is_marker: True,
    metadata: {...}
}
```

**Deterministic Gate** (Rule 0):
```python
Classification: {id: 1, tag: "PMI", confidence: 99, gated: True, gate_rule: "gate-locked-style"}
# Never sent to LLM
```

### Example 2: Downstream Normalizer Changes Marker Tag

**Input (after some normalizer)**:
```python
Block: {id: 1, text: "<REF>", _is_marker: True}
Classification: {id: 1, tag: "TXT", confidence: 85}  # Changed by normalizer
```

**After Post-Classification Re-lock**:
```python
Classification: {
    id: 1,
    tag: "PMI",          # Corrected
    confidence: 99,
    relocked: True,
    original_tag: "TXT"
}
```

**Log Output**:
```
MARKER_LOCK markers_total=1 relocked=1 leaked_to_llm=0
```

### Example 3: Marker Leaked to LLM (Bug Detection)

**Input (marker somehow reached LLM)**:
```python
Classification: {
    id: 1,
    tag: "H1",
    confidence: 85,
    reasoning: "This appears to be a chapter marker.",  # LLM output
    gated: False  # Should have been gated
}
```

**After Re-lock**:
```python
Classification: {
    id: 1,
    tag: "PMI",          # Corrected
    confidence: 99,
    relocked: True,
    original_tag: "H1"
}
```

**Log Output**:
```
WARNING: marker-lock: block 1 leaked to LLM despite skip_llm flag (text='<CN>')
MARKER_LOCK markers_total=1 relocked=1 leaked_to_llm=1
```

## Testing

**63 comprehensive tests** covering:

### Pre-LLM Lock
- ✓ Simple markers (CN, CT, REF, TAB6.1, H1-INTRO)
- ✓ Markers with hyphens, dots, underscores, numbers, spaces
- ✓ Lowercase and mixed case markers
- ✓ Multiple markers in document
- ✓ Whitespace handling (leading, trailing, surrounding)
- ✓ Text preservation (byte-for-byte)
- ✓ Negative cases (marker with content, nested brackets, incomplete)
- ✓ Edge cases (empty blocks, None text, identity preservation)

### Gate Integration
- ✓ Locked markers gated by deterministic gate (Rule 0)
- ✓ Locked markers never sent to LLM
- ✓ End-to-end lock → gate pipeline

### Idempotency
- ✓ Running lock_marker_blocks twice produces same result
- ✓ Running relock_marker_classifications twice produces same result
- ✓ Text preserved across multiple lock passes

### Post-Classification Re-lock
- ✓ Marker misclassified as TXT → relocked to PMI
- ✓ Marker misclassified as heading → relocked to PMI
- ✓ Marker already PMI → unchanged
- ✓ Non-marker blocks → unchanged
- ✓ Mixed markers and non-markers → only markers relocked
- ✓ Detects markers without _is_marker flag (based on text pattern)
- ✓ Multiple markers all relocked
- ✓ Empty classifications handled gracefully
- ✓ Mismatched IDs skipped

### Leak Detection
- ✓ Marker with LLM reasoning → leak detected
- ✓ Marker with gated=False → leak detected
- ✓ Marker properly gated → no leak
- ✓ Multiple leaked markers all detected

### Logging
- ✓ Pre-lock emits `MARKER_LOCK_PRE markers_total=X`
- ✓ Post-lock emits `MARKER_LOCK markers_total=X relocked=Y leaked_to_llm=Z`
- ✓ No markers → no logging

### Helper Function
- ✓ `_is_marker_block()` correctly identifies markers
- ✓ Handles whitespace, invalid markers, edge cases

Run tests:
```bash
pytest backend/tests/test_marker_lock.py -v
```

## Design Decisions

### Why Two Phases?

**Pre-LLM lock** prevents unnecessary LLM calls (saves tokens/cost) and ensures LLM never sees or misinterprets markers.

**Post-classification re-lock** acts as FINAL AUTHORITY to catch:
- Cases where pre-LLM lock wasn't applied (shouldn't happen but defensive)
- Downstream normalizers that modified marker tags (bugs in normalizers)
- Any other leaks in the pipeline

### Why PMI Instead of MARKER?

The spec requested `MARKER` as the tag, but `MARKER` does not exist in the WK Template allowed-styles vocabulary. `PMI` (Page Marker Instruction) is the established canonical tag for marker-only paragraphs in this codebase.

### Why Not Modify During Reconstruction?

Modifying DOCX during reconstruction would:
- Require complex paragraph matching/hashing
- Risk misaligning text with formatting
- Be harder to test and debug

Instead, we correct classifications (which have stable IDs matching blocks), then reconstruction uses the corrected tags.

### Why `_is_marker` Flag?

The `_is_marker` flag provides fast lookup in post-classification pass without re-parsing text patterns. It's a performance optimization and defensive check (both flag AND pattern matching are checked).

## Files Modified/Created

### Created
- `backend/processor/marker_lock.py` - Main implementation (180 lines)
  - `MarkerLockMetrics` dataclass
  - `_is_marker_block()` helper
  - `lock_marker_blocks()` - pre-LLM lock
  - `relock_marker_classifications()` - post-classification re-lock
- `backend/tests/test_marker_lock.py` - Comprehensive tests (63 tests, 670+ lines)
- `backend/processor/MARKER_LOCK_README.md` - This documentation

### Modified
- `backend/processor/pipeline.py` - Integrated into pipeline:
  - Stage 1b: `lock_marker_blocks()` call (pre-LLM)
  - Stage 3.5: `relock_marker_classifications()` call (post-classification)
  - Added import for `relock_marker_classifications`

## Non-Negotiable Rules (Satisfied)

✓ **Rule 1**: Marker blocks have dedicated PMI style (pre-LLM + post-classification)
✓ **Rule 2**: Excluded from LLM classification (`skip_llm=True` + deterministic gate)
✓ **Rule 3**: Excluded from heuristics style inference (locked before heuristics run)
✓ **Rule 4**: Excluded from list/table enforcement (PMI is exempt from zone/list rules)
✓ **Rule 5**: Marker text never modified (byte-for-byte preservation verified in tests)
✓ **Rule 6**: Block eligibility filter respects `skip_llm=True` (deterministic gate)

## Commit Message

```
feat: add two-phase marker block locking system

Implements pre-LLM and post-classification marker locking to ensure
structural marker paragraphs (<CN>, <REF>, <TAB6.1>) are never altered
by heuristics, LLM, or downstream normalization.

Two-phase architecture:
- Phase 1 (pre-LLM): Marks markers with skip_llm=True, bypasses LLM via deterministic gate
- Phase 2 (post-classification): Re-locks markers to PMI as final authority

Key features:
- Byte-for-byte text preservation
- Leak detection (markers that reached LLM despite skip_llm)
- Structured logging: MARKER_LOCK_PRE, MARKER_LOCK with metrics
- 63 comprehensive tests covering all edge cases
- Idempotent operations

Closes: marker block locking requirement
```
