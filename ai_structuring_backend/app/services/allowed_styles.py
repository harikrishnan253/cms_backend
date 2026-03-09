"""Allowed styles loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .style_normalizer import normalize_style


INVALID_ENTRIES = {
    "H2 after H1",
    "H3 after H2",
    "NL-MID following L1",
}


def _default_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "allowed_styles.json"


def load_allowed_styles(path: str | None = None) -> set[str]:
    file_path = Path(path) if path else _default_path()
    if not file_path.exists():
        raise FileNotFoundError(f"Allowed styles file not found: {file_path}")

    data = json.loads(file_path.read_text(encoding="utf-8"))
    styles = set()
    for item in data:
        norm = normalize_style(str(item))
        if not norm:
            continue
        if norm in INVALID_ENTRIES:
            continue
        styles.add(norm)

    if "PMI" not in styles:
        raise ValueError("PMI is required in allowed styles but was not found.")

    return styles
