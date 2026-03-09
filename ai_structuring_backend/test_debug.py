"""Debug script for SK_H3 -> TH3 mapping"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Test normalize_style directly
from app.services.style_normalizer import normalize_style

print("=" * 80)
print("Testing normalize_style()")
print("=" * 80)

test_cases = [
    ("SK_H3", None),
    ("SK_H3", {"context_zone": "TABLE"}),
    ("SK_H3", {"context_zone": "BODY"}),
    ("TBL-H2", None),
    ("TBL-H2", {"context_zone": "TABLE"}),
    ("TH3", None),
]

for tag, meta in test_cases:
    result = normalize_style(tag, meta=meta)
    print(f"normalize_style('{tag}', meta={meta}) = '{result}'")

print("\n" + "=" * 80)
print("Testing _ensure_allowed()")
print("=" * 80)

# Manually test _ensure_allowed logic (UPDATED)
def _ensure_allowed(tag: str, allowed: set[str], fallback: str) -> str:
    normalized_tag = normalize_style(tag)
    print(f"  _ensure_allowed: normalize_style('{tag}') = '{normalized_tag}'")
    print(f"  _ensure_allowed: '{normalized_tag}' in {allowed} = {normalized_tag in allowed}")
    if normalized_tag in allowed:
        return normalized_tag  # Return normalized version, not original
    normalized_fallback = normalize_style(fallback)
    print(f"  _ensure_allowed: normalize_style('{fallback}') = '{normalized_fallback}'")
    if normalized_fallback in allowed:
        return normalized_fallback
    if "TXT" in allowed:
        return "TXT"
    return normalized_tag

print("\nTest 1: TH3 with allowed={'TH3'}")
result = _ensure_allowed("TH3", {"TH3"}, "TXT")
print(f"Result: '{result}'")

print("\nTest 2: SK_H3 with allowed={'TH3'}")
result = _ensure_allowed("SK_H3", {"TH3"}, "TXT")
print(f"Result: '{result}'")

print("\nTest 3: TBL-H2 with allowed={'TH2'}")
result = _ensure_allowed("TBL-H2", {"TH2"}, "TXT")
print(f"Result: '{result}'")
