"""Test path setup for backend package imports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


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
