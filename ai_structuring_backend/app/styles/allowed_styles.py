"""Canonical allowed styles and alias map loader."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.services.style_normalizer import normalize_style

INVALID_ENTRIES = {
    "H2 after H1",
    "H3 after H2",
    "NL-MID following L1",
}


def _allowed_path(document_type: str | None = None) -> Path:
    _ = document_type
    return Path(__file__).resolve().parents[2] / "config" / "allowed_styles.json"


def _alias_path(document_type: str | None = None) -> Path:
    _ = document_type
    return Path(__file__).resolve().parents[2] / "config" / "style_aliases.json"


def _cache_key(document_type: str | None) -> str:
    return (document_type or "").strip().lower()


@lru_cache(maxsize=16)
def _load_allowed_cached(cache_key: str) -> frozenset[str]:
    path = _allowed_path(cache_key)
    if not path.exists():
        raise FileNotFoundError(f"Allowed styles file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    styles: set[str] = set()
    for item in raw:
        norm = normalize_style(str(item))
        if not norm or norm in INVALID_ENTRIES:
            continue
        styles.add(norm)

    if "PMI" not in styles:
        raise ValueError("PMI is required in allowed styles but was not found.")
    return frozenset(styles)


@lru_cache(maxsize=16)
def _load_alias_cached(cache_key: str) -> dict[str, str]:
    path = _alias_path(cache_key)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def get_allowed_styles(document_type: str | None = None) -> set[str]:
    """Return canonical allowed styles for the given document type."""
    return set(_load_allowed_cached(_cache_key(document_type)))


def get_style_alias_map(document_type: str | None = None) -> dict[str, str]:
    """Return alias->canonical style map for the given document type."""
    return dict(_load_alias_cached(_cache_key(document_type)))


def compute_allowed_style_hash(styles: Iterable[str]) -> str:
    """Return a stable sha256 hash for a style collection."""
    canonical = sorted(
        {
            normalize_style(str(s))
            for s in styles
            if normalize_style(str(s))
        }
    )
    payload = "\n".join(canonical)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@lru_cache(maxsize=16)
def _allowed_style_stats_cached(cache_key: str) -> tuple[int, str]:
    allowed = _load_allowed_cached(cache_key)
    return len(allowed), compute_allowed_style_hash(allowed)


def get_allowed_style_stats(document_type: str | None = None) -> dict[str, int | str]:
    """Return cached allowed style metadata for diagnostics endpoints."""
    count, style_hash = _allowed_style_stats_cached(_cache_key(document_type))
    return {
        "allowed_style_count": count,
        "allowed_style_hash": style_hash,
    }
