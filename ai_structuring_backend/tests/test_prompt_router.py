import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services.prompt_router import route_profile


def test_route_reference_heavy():
    blocks = [
        {"text": "1. Smith et al. (2020). Journal of Testing.", "metadata": {}},
        {"text": "[2] Doe, J. doi:10.1000/xyz", "metadata": {}},
    ]
    profile = route_profile(blocks, {})
    assert profile == "reference_heavy"


def test_route_table_heavy():
    blocks = [
        {"text": "Table 1.1 Sample", "metadata": {"is_table": True}},
        {"text": "Cell", "metadata": {"is_table": True}},
        {"text": "Cell", "metadata": {"is_table": True}},
    ]
    profile = route_profile(blocks, {})
    assert profile == "table_heavy"


def test_route_box_heavy():
    blocks = [
        {"text": "Box: Clinical Pearl", "metadata": {"context_zone": "BOX_NBX"}},
        {"text": "Key Points", "metadata": {}},
    ]
    profile = route_profile(blocks, {})
    assert profile == "box_heavy"


def test_route_default():
    blocks = [
        {"text": "Introduction", "metadata": {}},
        {"text": "Body text", "metadata": {}},
    ]
    profile = route_profile(blocks, {})
    assert profile == "default"
