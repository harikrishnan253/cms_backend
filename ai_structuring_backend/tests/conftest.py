"""Test path setup for backend package imports."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The package was historically called "backend" and many tests still import
# from that name; it now lives at ai_structuring_backend/.
BACKEND = ROOT / "ai_structuring_backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Preserve the legacy `from backend.xxx import ...` import form by exposing a
# namespace-package-style module whose __path__ points at the real location.
if "backend" not in sys.modules:
    _backend = types.ModuleType("backend")
    _backend.__path__ = [str(BACKEND)]  # type: ignore[attr-defined]
    sys.modules["backend"] = _backend


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (run with --slow flag or -m slow)",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run slow performance tests",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return  # Run everything
    skip_slow = __import__("pytest").mark.skip(reason="Pass --slow to run performance tests")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
