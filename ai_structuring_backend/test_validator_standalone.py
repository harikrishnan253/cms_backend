"""
Standalone test for validator without importing classifier.
This simulates the zone enforcement tests.
"""
import sys
import re
import logging
from pathlib import Path
from typing import Iterable

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.style_normalizer import normalize_style

# Copy constants from validator.py
ALLOWED_STYLES = []  # Not needed for these tests

def _allowed_set(allowed: Iterable[str] | None) -> set[str]:
    source = ALLOWED_STYLES if allowed is None or not list(allowed) else allowed
    return {normalize_style(s) for s in source if normalize_style(s)}

def _ensure_allowed(tag: str, allowed: set[str], fallback: str) -> str:
    normalized_tag = normalize_style(tag)
    if normalized_tag in allowed:
        return normalized_tag  # Return normalized version, not original
    normalized_fallback = normalize_style(fallback)
    if normalized_fallback in allowed:
        return normalized_fallback
    # Last resort: TXT if present
    if "TXT" in allowed:
        return "TXT"
    # Otherwise return normalized tag
    return normalized_tag

def simulate_validator_table_zone(
    tag: str,
    allowed_styles: Iterable[str],
    confidence: float = 0.8,
    zone: str = "TABLE"
) -> str:
    """
    Simulate the validator's table zone processing logic.
    """
    original_input_tag = tag  # Preserve original for table heading map lookup
    allowed = _allowed_set(allowed_styles)
    norm_tag = normalize_style(tag, meta={"context_zone": zone})

    # Check if locked (high confidence + in allowed)
    lock_tag = norm_tag in allowed and confidence >= 0.90

    # Canonicalize if not locked
    if not lock_tag and norm_tag and norm_tag != tag:
        tag = norm_tag

    # Table zone heading mappings (check original input tag for fallback logic)
    if not lock_tag and zone == "TABLE":
        table_heading_map = {
            "SK_H1": "TH1", "SK_H2": "TH2", "SK_H3": "TH3",
            "SK_H4": "TH4", "SK_H5": "TH5", "SK_H6": "TH6",
            "TBL-H1": "TH1", "TBL-H2": "TH2", "TBL-H3": "TH3",
            "TBL-H4": "TH4", "TBL-H5": "TH5", "TBL-H6": "TH6",
        }
        mapped_heading = table_heading_map.get(original_input_tag)
        if mapped_heading:
            if not allowed or mapped_heading in allowed:
                tag = mapped_heading
            else:
                tag = "T"

    # Ensure tag is in allowed styles
    fallback_tag = "TXT"
    ensured = _ensure_allowed(tag, allowed, fallback=fallback_tag)
    if ensured != tag:
        tag = ensured

    return tag

print("=" * 80)
print("Testing SK_H3 and TBL-H2 mappings")
print("=" * 80)

# Test 1: test_table_zone_skill_heading_to_th
print("\nTest 1: SK_H3 in TABLE zone with allowed={'TH3'}")
result = simulate_validator_table_zone("SK_H3", {"TH3"})
print(f"Input: SK_H3")
print(f"Expected: TH3")
print(f"Result: {result}")
print(f"Status: {'PASS' if result == 'TH3' else 'FAIL'}")

# Test 2: test_table_zone_tbl_h_to_th
print("\nTest 2: TBL-H2 in TABLE zone with allowed={'TH2'}")
result = simulate_validator_table_zone("TBL-H2", {"TH2"})
print(f"Input: TBL-H2")
print(f"Expected: TH2")
print(f"Result: {result}")
print(f"Status: {'PASS' if result == 'TH2' else 'FAIL'}")

# Test 3: test_table_zone_sk_h_fallback_to_t
print("\nTest 3: SK_H3 in TABLE zone with allowed={'T'}")
result = simulate_validator_table_zone("SK_H3", {"T"})
print(f"Input: SK_H3")
print(f"Expected: T")
print(f"Result: {result}")
print(f"Status: {'PASS' if result == 'T' else 'FAIL'}")

# Test 4: test_table_zone_skill_heading_to_t
print("\nTest 4: SK_H2 in TABLE zone with allowed={'T'}")
result = simulate_validator_table_zone("SK_H2", {"T"})
print(f"Input: SK_H2")
print(f"Expected: T")
print(f"Result: {result}")
print(f"Status: {'PASS' if result == 'T' else 'FAIL'}")

# Test 5: All SK_H* mappings
print("\n" + "=" * 80)
print("Testing all SK_H* and TBL-H* mappings")
print("=" * 80)

for i in range(1, 7):
    for prefix in ["SK_H", "TBL-H"]:
        tag = f"{prefix}{i}"
        expected = f"TH{i}"
        result = simulate_validator_table_zone(tag, {expected})
        status = 'PASS' if result == expected else 'FAIL'
        print(f"{tag:10s} -> {result:6s} (expected {expected:6s}) {status}")

print("\n" + "=" * 80)
print("All tests completed")
print("=" * 80)
