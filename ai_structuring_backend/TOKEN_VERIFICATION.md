# Token Counting Verification

## Flow Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. GEMINI API CALL (classifier.py)                                 │
├─────────────────────────────────────────────────────────────────────┤
│ response = model.generate_content(user_prompt)                      │
│                                                                     │
│ Token data extracted from:                                          │
│   response.usage_metadata.prompt_token_count      → input_tokens    │
│   response.usage_metadata.candidates_token_count  → output_tokens   │
│   response.usage_metadata.total_token_count       → total_tokens    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. CLASSIFIER ACCUMULATION (classifier.py)                         │
├─────────────────────────────────────────────────────────────────────┤
│ For chunked documents (>75 paragraphs), tokens accumulate:          │
│                                                                     │
│   self.total_input_tokens += input_tokens   (per chunk)             │
│   self.total_output_tokens += output_tokens (per chunk)             │
│   self.total_tokens += total_tokens         (per chunk)             │
│                                                                     │
│ get_token_usage() returns accumulated totals                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. PIPELINE RETURN (pipeline.py)                                   │
├─────────────────────────────────────────────────────────────────────┤
│ result = {                                                          │
│     'input_tokens': token_usage.get('input_tokens', 0),             │
│     'output_tokens': token_usage.get('output_tokens', 0),           │
│     'total_tokens': token_usage.get('total_tokens', 0),             │
│ }                                                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. DATABASE STORAGE (queue.py)                                     │
├─────────────────────────────────────────────────────────────────────┤
│ Job model columns:                                                  │
│   job.input_tokens = result.get('input_tokens')                     │
│   job.output_tokens = result.get('output_tokens')                   │
│   job.total_tokens = result.get('total_tokens')                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. COST CALCULATION (api.py)                                       │
├─────────────────────────────────────────────────────────────────────┤
│ Model: gemini-2.5-flash                                             │
│                                                                     │
│ Pricing:                                                            │
│   Input:  $0.15 per 1M tokens                                       │
│   Output: $0.60 per 1M tokens                                       │
│                                                                     │
│ Formula:                                                            │
│   input_cost = (input_tokens / 1,000,000) × 0.15                    │
│   output_cost = (output_tokens / 1,000,000) × 0.60                  │
│   total_cost = input_cost + output_cost                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Verification Points

### ✅ Token Extraction
- Uses official Gemini API `usage_metadata` attributes
- `prompt_token_count` = input tokens (includes system prompt)
- `candidates_token_count` = output tokens
- `total_token_count` = total (may include additional overhead)

### ✅ Chunking Accumulation
- Large documents (>75 paragraphs) are chunked
- Tokens from each chunk are accumulated correctly
- Final count = sum of all chunk tokens

### ✅ Database Storage
- Tokens stored as Integer columns in SQLite
- Separate columns for input, output, total
- Supports NULL for failed/cancelled jobs

### ✅ Cost Calculation
- Uses current Gemini 2.5 Flash pricing
- Separate input/output rates
- Rounded to 6 decimal places

## Potential Issues to Watch

### 1. System Prompt Tokens
The `prompt_token_count` includes BOTH:
- System prompt (~800 lines = ~15,000-20,000 tokens)
- User prompt (paragraphs being classified)

This means the first chunk of each document includes the system prompt tokens.
For chunked documents, each chunk re-sends the system prompt.

**Impact:** Token count may be higher than expected due to system prompt overhead.

### 2. Retry Handling
If API call fails and retries:
- Failed calls don't add tokens (no response)
- Successful retry adds tokens normally
- No double-counting occurs

### 3. Null Token Values
If `usage_metadata` is not available:
- Tokens default to 0
- Warning logged but job continues
- Cost will show $0.0000

## Verification Commands

Run this in your terminal to verify tokens for a specific job:

```python
# In Python shell with backend context
from app.models.database import Job, db

# Get a completed job
job = Job.query.filter_by(status='completed').first()
print(f"Job: {job.original_filename}")
print(f"Input Tokens: {job.input_tokens:,}")
print(f"Output Tokens: {job.output_tokens:,}")
print(f"Total Tokens: {job.total_tokens:,}")
print(f"Paragraphs: {job.total_paragraphs}")

# Calculate expected output (rough estimate)
# Output ≈ paragraphs × 25 tokens per classification
expected_output = job.total_paragraphs * 25
print(f"Expected Output (estimate): {expected_output:,}")
```

## Cost Examples

| Document Size | Input Tokens | Output Tokens | Total Cost |
|--------------|--------------|---------------|------------|
| 50 paras     | ~20,000      | ~1,250        | $0.0038    |
| 200 paras    | ~40,000      | ~5,000        | $0.0090    |
| 500 paras    | ~80,000      | ~12,500       | $0.0195    |
| 1000 paras   | ~150,000     | ~25,000       | $0.0375    |

Note: Input tokens include system prompt (~15,000 tokens per chunk)
