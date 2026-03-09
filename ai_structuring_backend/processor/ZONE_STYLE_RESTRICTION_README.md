# Zone-Based Style Restriction Enforcement

## Overview

The zone-based style restriction system ensures the output never contains unknown/invalid styles, preventing quality_score from failing with "Unknown styles detected in output."

**FINAL SAFETY NET**: `enforce_zone_style_restrictions()` runs immediately before quality scoring to catch any unknown styles or zone violations that slipped through earlier validation layers.

## Problem Statement

Even with comprehensive zone validation in the classifier and validator, issues can still reach quality scoring:

1. **LLM hallucinations**: LLM generates style names that don't exist (e.g., "BODY_TEXT", "TABLE_TITLE", "REF_ITEM")
2. **Zone violations**: Valid styles used in wrong zones (e.g., BL-MID in TABLE zone)
3. **Validator gaps**: Edge cases that bypass earlier validation

These cause quality_score to fail with "Unknown styles detected in output," blocking the pipeline.

## Two-Phase Architecture

### Phase 1: Pre-Classification Hints (Stage 1b)

**Function**: `restrict_allowed_styles_per_zone(blocks) -> list[dict]`

**Purpose**: Set metadata hints to guide LLM towards zone-valid styles

**Actions**:
- Reads `block["metadata"]["context_zone"]`
- Looks up valid styles from `ZONE_VALID_STYLES[zone]`
- Stores in `metadata["zone_allowed_styles"]` for reference

**Effect**: Provides early guidance but doesn't enforce (classifier still validates)

### Phase 2: Post-Classification Enforcement (Stage 3.5)

**Function**: `enforce_zone_style_restrictions(blocks, allowed_styles) -> list[dict]`

**Purpose**: **FINAL AUTHORITY** that ensures output never contains unknown/invalid styles

**Actions**:
1. Checks each block's style against global `allowed_styles` vocabulary
2. Checks each block's style against zone-specific allowlist
3. Replaces invalid styles with zone-specific fallbacks
4. Tracks and logs all replacements with structured metrics

**Effect**: Quality_score never sees unknown or zone-invalid styles

## Zone Structure

Based on `ZONE_VALID_STYLES` from [ingestion.py](ingestion.py:162-493):

| Zone | Description | Fallback Style |
|------|-------------|----------------|
| `METADATA` | Pre-press info before chapter | `PMI` |
| `FRONT_MATTER` | Chapter opener through objectives | `TXT` |
| `BODY` | Main chapter content (allows ALL styles) | `TXT` |
| `TABLE` | Word table content | `T` |
| `BOX_NBX` | Informational boxes (NOTE, TIP) | `NBX-TXT` |
| `BOX_BX1` | Clinical/practical boxes | `BX1-TXT` |
| `BOX_BX2` | Warning boxes (RED FLAG) | `BX2-TXT` |
| `BOX_BX3` | Reflection/discussion boxes | `BX3-TXT` |
| `BOX_BX4` | Procedure/case study boxes | `BX4-TXT` |
| `BOX_BX6` | Resource boxes | `BX6-TXT` |
| `BOX_BX7` | Case study boxes | `BX7-TXT` |
| `BOX_BX15` | Special boxes | `BX15-TXT` |
| `BOX_BX16` | Boxes with unnumbered tables | `BX16-UNT` |
| `BACK_MATTER` | References, figures, appendix | `PMI` |
| `EXERCISE` | Exercise/workbook content | `PMI` |

**Note**: `BODY` zone has no restrictions (`ZONE_VALID_STYLES['BODY'] = None`), allowing all styles.

## Replacement Strategy

For each block:

```python
1. Check globally valid: style in allowed_styles?
   - NO → unknown_from_llm++ (LLM hallucination)
   - YES → continue

2. Check zone valid: validate_style_for_zone(style, zone)?
   - NO → zone violation
   - YES → no action needed

3. Replace with fallback: _ZONE_FALLBACKS[zone]
```

### Examples of Replacements

**LLM Hallucination**:
```python
Input:  {tag: "BODY_TEXT", zone: "BODY"}    # Style doesn't exist
Output: {tag: "TXT", zone_restricted: True, original_tag: "BODY_TEXT"}
```

**Zone Violation**:
```python
Input:  {tag: "BL-MID", zone: "TABLE"}       # Valid style, wrong zone
Output: {tag: "T", zone_restricted: True, original_tag: "BL-MID"}
```

**Valid Style** (unchanged):
```python
Input:  {tag: "TXT", zone: "BODY"}           # Valid style, correct zone
Output: {tag: "TXT"}                         # No change
```

## API

### `enforce_zone_style_restrictions(blocks, allowed_styles=None) -> list[dict]`

Post-classification enforcement function.

**Parameters**:
- `blocks`: Block list with `tag` and `metadata["context_zone"]`. Modified **in-place**.
- `allowed_styles`: Global allowed styles vocabulary. If `None`, loads from config.

**Returns**:
- Same block objects (identity), for chaining convenience.

**Side effects**:
- Modifies blocks to set `tag`, `zone_restricted=True`, `original_tag`

### `restrict_allowed_styles_per_zone(blocks) -> list[dict]`

Pre-classification hint function (already existed).

**Parameters**:
- `blocks`: Block list from `extract_blocks()`. Modified **in-place**.

**Returns**:
- Same block objects (identity), for chaining convenience.

**Side effects**:
- Sets `metadata["zone_allowed_styles"]` for guidance

## Pipeline Integration

```python
# Stage 1b: Pre-classification hints
blocks = lock_marker_blocks(blocks)
blocks = enforce_table_title_rules(blocks)
blocks = normalize_reference_numbering(blocks)
blocks = enforce_list_hierarchy_from_word_xml(blocks)
blocks = restrict_allowed_styles_per_zone(blocks)  # Phase 1

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

# Re-lock markers
classifications = relock_marker_classifications(blocks, classifications)

# Merge classifications into scored_blocks
scored_blocks = []
clf_by_id = {c["id"]: c for c in classifications}
for b in blocks:
    c = clf_by_id.get(b["id"], {})
    scored_blocks.append({
        **b,
        "tag": c.get("tag", "TXT"),
        "confidence": c.get("confidence", 0),
        "repaired": c.get("repaired", False),
        "repair_reason": c.get("repair_reason"),
    })

# Enforce zone style restrictions (FINAL SAFETY NET) - Phase 2
scored_blocks = enforce_zone_style_restrictions(scored_blocks, allowed_styles)

# Quality scoring (should never see unknown/invalid styles)
quality_score, quality_metrics, quality_action = score_document(scored_blocks, allowed_styles)
```

## Logging

### Structured Format

```
ZONE_STYLE_RESTRICTION total=<int> replaced=<int> unknown_from_llm=<int> by_zone={...}
```

**Metrics**:
- `total`: Total blocks processed
- `replaced`: Blocks with styles replaced
- `unknown_from_llm`: Styles that don't exist in global allowed styles
- `by_zone`: Replacement count breakdown by zone (dict)

### Example Log Output

```
WARNING: zone-restriction: block 1 has unknown style 'BODY_TEXT' (zone=BODY), replacing with TXT
WARNING: zone-restriction: block 2 has unknown style 'TABLE_TITLE' (zone=TABLE), replacing with T
INFO: ZONE_STYLE_RESTRICTION total=10 replaced=4 unknown_from_llm=2 by_zone={'BODY': 1, 'TABLE': 2, 'FRONT_MATTER': 1}
WARNING: zone-restriction: unknown styles encountered: {'BODY_TEXT': 1, 'TABLE_TITLE': 1}
```

### Log Levels

- **WARNING**: Unknown styles, zone violations (per-block details)
- **INFO**: Summary metrics (structured format)
- **DEBUG**: Zone validation checks

## Testing

**33 comprehensive tests** covering:

### Unknown Style Replacement (LLM Hallucinations)
- ✓ Unknown style replaced with zone fallback
- ✓ Unknown styles in different zones (TABLE, BOX_NBX)
- ✓ Multiple unknown styles all replaced
- ✓ Logging includes unknown_from_llm count

### Zone Violation Replacement
- ✓ Bullet list (BL-MID) in TABLE zone → replaced with T
- ✓ Table style (T1) in BODY zone → allowed (BODY has no restrictions)
- ✓ Heading (H1) in TABLE zone → replaced with T
- ✓ Box style in FRONT_MATTER → replaced with TXT

### Valid Styles Unchanged
- ✓ TXT in BODY → unchanged
- ✓ T1 in TABLE → unchanged
- ✓ NBX-TXT in BOX_NBX → unchanged
- ✓ PMI in valid zones → unchanged
- ✓ Mixed valid and invalid → only invalid replaced

### Logging Format
- ✓ Structured log with metrics
- ✓ by_zone breakdown includes all zones
- ✓ No replacements → no log
- ✓ Unknown styles logged separately with counts

### Edge Cases
- ✓ Empty blocks list
- ✓ Block without tag field → skipped
- ✓ Block without zone → defaults to BODY
- ✓ allowed_styles=None → loads from config
- ✓ Identity preserved (in-place modification)

### Idempotency
- ✓ Running enforcement twice produces same result
- ✓ Already restricted blocks unchanged

### Quality Scoring Integration
- ✓ Unknown style replaced before quality check
- ✓ Multiple unknown styles all fixed
- ✓ quality_score passes (no unknown styles)

### Zone Fallback Mapping
- ✓ Each zone has correct fallback style
- ✓ BODY → TXT, TABLE → T, BOX_NBX → NBX-TXT, etc.

### Comprehensive Integration
- ✓ Complex document with all issue types
- ✓ Valid styles unchanged
- ✓ Unknown styles replaced
- ✓ Zone violations replaced
- ✓ Logging accurate

Run tests:
```bash
pytest backend/tests/test_zone_style_enforcement.py -v
```

## Design Decisions

### Why Post-Classification Instead of Pre-LLM?

**Pre-classification hints** guide the LLM but don't enforce (LLM can still hallucinate).

**Post-classification enforcement** is the **FINAL AUTHORITY** that:
- Catches LLM hallucinations
- Fixes validator gaps
- Ensures quality_score never fails

### Why Modify Blocks, Not Classifications?

The function modifies `scored_blocks` (which are blocks merged with classifications) immediately before quality scoring. This ensures:
- Simple integration point (one call before score_document)
- Direct modification of final output
- No need to re-merge classifications

### Why Zone Fallbacks Instead of Generic TXT?

Zone-specific fallbacks (e.g., `T` for TABLE, `NBX-TXT` for BOX_NBX) preserve more semantic meaning than defaulting everything to `TXT`.

### Why Track unknown_from_llm Separately?

Distinguishes:
- **LLM hallucinations** (style doesn't exist globally) → indicates LLM quality issues
- **Zone violations** (style exists but wrong zone) → indicates classifier/validator gaps

This helps diagnose pipeline issues.

## Files Modified/Created

### Created
- `backend/processor/zone_style_restriction.py` - Implementation (370 lines)
  - `ZoneRestrictionMetrics` dataclass
  - `_ZONE_FALLBACKS` mapping
  - `enforce_zone_style_restrictions()` - post-classification enforcement
  - Updated module docstring
- `backend/tests/test_zone_style_enforcement.py` - Comprehensive tests (33 tests, 550+ lines)
- `backend/processor/ZONE_STYLE_RESTRICTION_README.md` - This documentation

### Modified
- `backend/processor/pipeline.py` - Integrated into Stage 3.5:
  - Added import for `enforce_zone_style_restrictions`
  - Called in both classifier_override and normal LLM paths
  - Positioned immediately before `score_document()`

## Non-Negotiable Rules (Satisfied)

✓ **Rule 1**: Explicit allowlist of styles per zone (uses `ZONE_VALID_STYLES` from ingestion.py)
✓ **Rule 2**: Invalid styles replaced with safe fallbacks (zone-specific fallbacks defined)
✓ **Rule 3**: Final DOCX contains only valid styles (enforcement runs before quality scoring)
✓ **Rule 4**: Runs immediately before quality scoring (Stage 3.5, after all normalizers)
✓ **Rule 5**: LLM unknown styles mapped to valid styles (unknown_from_llm tracked and replaced)
✓ **Rule 6**: Structured logging with metrics (ZONE_STYLE_RESTRICTION format)
✓ **Rule 7**: Idempotent (tested)

## Commit Message

```
feat: add zone-based style restriction enforcement

Implements post-classification enforcement to ensure output never contains
unknown/invalid styles, preventing quality_score failures.

Two-phase architecture:
- Phase 1 (pre-classification): Sets metadata hints to guide LLM
- Phase 2 (post-classification): Final authority that replaces invalid styles

Key features:
- Replaces LLM hallucinations (unknown styles) with zone fallbacks
- Fixes zone violations (valid styles in wrong zones)
- Runs immediately before quality scoring as final safety net
- Structured logging: ZONE_STYLE_RESTRICTION with metrics
- 33 comprehensive tests covering all edge cases
- Idempotent operations

Closes: zone style restriction requirement
```
