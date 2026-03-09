# List Hierarchy Preservation from Word XML

## Overview

The `list_preservation.py` module enforces list structure from the original Word document after LLM classification, preventing the LLM from flattening or corrupting list hierarchy.

**Source of Truth**: Word numbering properties (`w:numPr`, `w:ilvl`, `w:numId`) from the input DOCX, NOT the LLM's classification.

## Problem Statement

LLMs often misclassify list items, leading to:
- Nested lists being flattened to top-level
- List items tagged as body text
- Bullet lists tagged as numbered (or vice versa)
- Loss of list sequence grouping

This module ensures the original list structure is preserved regardless of LLM output.

## How It Works

### Phase 1: Ingestion (in `ingestion.py`)

During document ingestion, Word XML numbering properties are extracted for each paragraph:

```python
# From para._p.pPr.numPr in Word XML:
metadata['xml_list_level'] = ilvl     # 0-based nesting level (0=top)
metadata['xml_num_id'] = numId        # List sequence ID (groups continuations)
metadata['has_bullet'] = True         # Bullet list indicator
metadata['has_numbering'] = True      # Numbered list indicator
```

### Phase 2: Post-Classification Enforcement (in `list_preservation.py`)

After LLM classification (Stage 3.5), the module:

1. **Identifies** paragraphs that were lists in the original document
2. **Verifies** LLM classification matches expected list style
3. **Overrides** misclassified items back to correct style
4. **Preserves**:
   - List level (ilvl)
   - Ordered vs unordered type
   - List sequence grouping (numId)

### Tag Mapping

```python
Bullet Lists:
  Level 0 → BL-MID
  Level 1 → BL2-MID
  Level 2 → BL3-MID
  Level 3 → BL4-MID

Numbered Lists:
  Level 0 → NL-MID
  Level 1 → NL2-MID
  Level 2 → NL3-MID
  Level 3 → NL4-MID
```

## API

```python
def enforce_list_hierarchy_from_word_xml(
    blocks: Sequence[dict],
    classifications: Sequence[dict],
) -> list[dict]:
    """Enforce list hierarchy from Word XML after classification.

    Parameters
    ----------
    blocks : sequence of dict
        Block list with Word XML metadata (xml_list_level, xml_num_id).
    classifications : sequence of dict
        LLM classifications that may need correction.

    Returns
    -------
    list of dict
        Corrected classifications with list hierarchy enforced.
    """
```

## Examples

### Example 1: LLM Misclassifies Nested List as Body Text

**Input (from Word)**:
```
• Top-level item         (xml_list_level=0, has_bullet=True)
  • Nested item          (xml_list_level=1, has_bullet=True)
  • Another nested       (xml_list_level=1, has_bullet=True)
```

**LLM Classification** (wrong):
```
tag: "TXT"
tag: "TXT"
tag: "TXT"
```

**After Enforcement** (corrected):
```
tag: "BL-MID"
tag: "BL2-MID"
tag: "BL2-MID"
```

### Example 2: Wrong List Level

**Input**:
```
• Top-level              (xml_list_level=0, has_bullet=True)
  • Nested               (xml_list_level=1, has_bullet=True)
```

**LLM Classification** (wrong):
```
tag: "BL-MID"
tag: "BL-MID"          ← Should be BL2-MID
```

**After Enforcement** (corrected):
```
tag: "BL-MID"
tag: "BL2-MID"         ← Corrected to nested level
```

### Example 3: Wrong List Type

**Input**:
```
1. First item            (xml_list_level=0, has_numbering=True)
2. Second item           (xml_list_level=0, has_numbering=True)
```

**LLM Classification** (wrong):
```
tag: "BL-MID"          ← Bullet tag for numbered list
tag: "BL-MID"
```

**After Enforcement** (corrected):
```
tag: "NL-MID"          ← Corrected to numbered
tag: "NL-MID"
```

## Logging

Emits structured log line:

```
LIST_HIERARCHY_ENFORCEMENT list_paras=<int> restored=<int> overrides=<int> unmatched=<int>
```

Where:
- `list_paras`: Total paragraphs that were lists in Word
- `restored`: Already correctly classified (no change needed)
- `overrides`: Corrected by this module
- `unmatched`: Could not determine correct tag (missing metadata)

## Pipeline Integration

Called in **Stage 3.5** (Post-classification normalization), after:
- Text normalizers (reference_label_normalizer, table_title_normalizer, reference_numbering_normalizer)
- Tag synchronization from blocks to classifications

And before:
- Quality scoring
- Reconstruction

```python
# Stage 3.5: Post-classification text/placement normalization
blocks = normalize_reference_labels(blocks)
blocks = normalize_table_titles(blocks)
blocks = normalize_reference_format(blocks)

# Sync block tags back to classifications
block_tags = {b["id"]: b.get("tag") for b in blocks if "tag" in b}
for clf in classifications:
    if clf["id"] in block_tags and block_tags[clf["id"]]:
        clf["tag"] = block_tags[clf["id"]]

# Enforce list hierarchy (FINAL AUTHORITY on list structure)
classifications = preserve_list_hierarchy(blocks, classifications)
```

## Design Decisions

### Why Post-Classification Instead of Pre-LLM Lock?

Two complementary approaches exist:
1. **Pre-LLM lock** (`list_hierarchy.py`): Sets `lock_style=True` before LLM to skip classification
2. **Post-classification enforcement** (`list_preservation.py`): Corrects LLM output after classification

Post-classification enforcement is the FINAL authority because:
- Handles cases where pre-LLM lock wasn't applied
- Corrects LLM misclassifications that bypassed locks
- Ensures output always matches Word structure

### Why Not Modify During Reconstruction?

Modifying the DOCX during reconstruction would:
- Require complex paragraph matching/hashing
- Risk misaligning text with formatting
- Be harder to test and debug

Instead, we correct classifications (which have stable IDs matching blocks), then reconstruction uses the corrected tags.

### Ambiguous List Type Handling

When Word XML indicates a list (`xml_list_level` present) but type is unclear:
- Default to **bullet** (safer than defaulting to numbered)
- Log as `unmatched` to flag for review
- Do not override (preserve LLM classification if reasonable)

## Testing

**22 comprehensive tests** covering:
- ✓ Nested bullets stay nested (2, 3, 4 levels)
- ✓ Numbered lists stay numbered (flat and nested)
- ✓ Mixed lists (bullets + numbering) preserved
- ✓ LLM misclassifications corrected (TXT→list, wrong level, wrong type)
- ✓ Non-list paragraphs unchanged
- ✓ Edge cases (empty, mismatched IDs, level clamping, ambiguous type)
- ✓ List sequences (numId) tracked
- ✓ Structured logging

Run tests:
```bash
pytest backend/tests/test_list_preservation.py -v
```

## Non-Negotiable Rules (Satisfied)

✓ **Rule 1**: Word XML (`w:numPr`, `w:ilvl`, `w:numId`) is source of truth
✓ **Rule 2**: Preserves list level, type, and continuity
✓ **Rule 3**: Output respects semantic styles but maintains structure
✓ **Rule 4**: Overrides LLM misclassifications
✓ **Rule 5**: No invention, merging, or splitting of list items

## Files Modified/Created

### Created
- `backend/processor/list_preservation.py` - Main implementation (200 lines)
- `backend/tests/test_list_preservation.py` - Comprehensive tests (22 tests, 400+ lines)
- `backend/processor/LIST_PRESERVATION_README.md` - This documentation

### Modified
- `backend/processor/ingestion.py` - Added `xml_num_id` extraction (6 lines)
- `backend/processor/pipeline.py` - Integrated into Stage 3.5 (3 lines)

## Future Enhancements

Potential improvements:
1. **Smart type detection**: Use document numbering definitions to determine bullet vs numbered when metadata is ambiguous
2. **List continuation validation**: Verify numId sequences are properly continued
3. **Paragraph matching**: Add hash-based matching for cases where block IDs don't align (currently not needed due to stable IDs)
4. **Formatting preservation**: Preserve list indentation and numbering format (currently relies on reconstruction)

## Commit Message

```
feat: preserve list hierarchy from Word XML

Implements post-classification enforcement of list structure from
original Word document, preventing LLM from flattening or corrupting
list hierarchy.

- Captures Word numbering properties (ilvl, numId) during ingestion
- Enforces list level, type, and grouping after classification
- Overrides LLM misclassifications (list→TXT, wrong level, wrong type)
- 22 comprehensive tests covering nested, numbered, mixed lists

Closes: list hierarchy preservation requirement
```
