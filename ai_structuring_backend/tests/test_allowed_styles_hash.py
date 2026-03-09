import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.styles.allowed_styles import compute_allowed_style_hash


def test_allowed_style_hash_stable_for_fixture_list():
    fixture_a = ["TXT", "H1", "REF-N"]
    fixture_b = ["REF-N", "TXT", "H1"]
    expected = "e77423b76e86107d7684cf61a0de4b659c10c98eff93f3c6b99127c663043528"
    assert compute_allowed_style_hash(fixture_a) == expected
    assert compute_allowed_style_hash(fixture_b) == expected
