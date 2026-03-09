"""Shared style registry package."""

from .allowed_styles import (
    compute_allowed_style_hash,
    get_allowed_style_stats,
    get_allowed_styles,
    get_style_alias_map,
)
from .normalization import normalize_style

__all__ = [
    "get_allowed_styles",
    "get_style_alias_map",
    "get_allowed_style_stats",
    "compute_allowed_style_hash",
    "normalize_style",
]
