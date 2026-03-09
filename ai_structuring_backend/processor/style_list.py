"""
Style list loader for WK Book Template 1.1.
Loads allowed styles from backend/config/allowed_styles.json via shared services.
"""

from __future__ import annotations

from typing import Iterable

from app.services.allowed_styles import load_allowed_styles
from app.services.style_normalizer import normalize_style


ALLOWED_STYLES = load_allowed_styles()


def is_allowed_style(tag: str, allowed: Iterable[str]) -> bool:
    return normalize_style(tag) in allowed
