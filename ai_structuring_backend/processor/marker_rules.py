"""
Deterministic marker-token rules that override LLM / heuristic classification.

If a paragraph's text starts with a recognised marker token, the style is
resolved here and the classification is overwritten.  This module is intended
to be called from the pipeline as a single post-pass **after**
``validate_and_repair`` so that marker rules have the final word, while still
respecting zone constraints.

Feature-flag: this module is always active (marker rules are deterministic
correctness fixes, not diagnostics).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from .ingestion import validate_style_for_zone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Marker token regex – matches a leading ``<TOKEN>`` at the start of text.
# Captures the full token string including angle brackets.
# ---------------------------------------------------------------------------
_MARKER_TOKEN_RE = re.compile(
    r"^\s*(</?[A-Za-z][A-Za-z0-9 _-]*>)",
    re.IGNORECASE,
)

# Text remaining after stripping the leading marker token.
_AFTER_MARKER_RE = re.compile(
    r"^\s*</?[A-Za-z][A-Za-z0-9 _-]*>\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)


def parse_marker_token(text: str) -> str | None:
    """Return the leading marker token (lower-cased) or *None*.

    >>> parse_marker_token("<H1-INTRO>Introduction")
    '<h1-intro>'
    >>> parse_marker_token("Normal paragraph") is None
    True
    """
    m = _MARKER_TOKEN_RE.match(text or "")
    if m:
        return m.group(1).lower()
    return None


def _text_after_marker(text: str) -> str:
    """Return the portion of *text* that follows the leading marker token."""
    m = _AFTER_MARKER_RE.match(text or "")
    return m.group(1).strip() if m else text.strip()


def _is_marker_only(text: str) -> bool:
    """True when the paragraph contains *only* a marker token (+ whitespace)."""
    return _text_after_marker(text) == ""


def resolve_marker_style(
    token: str,
    text: str,
    meta: dict | None = None,
) -> str | None:
    """Map a marker *token* (lower-cased) to a style tag, or *None*.

    Parameters
    ----------
    token : str
        Lower-cased marker token, e.g. ``"<h1-intro>"``.
    text : str
        Full paragraph text (used for secondary content checks).
    meta : dict, optional
        Block metadata (``context_zone``, etc.).

    Returns
    -------
    str or None
        Resolved style tag, or *None* if no rule matches.
    """
    remainder = _text_after_marker(text).lower()

    # Rule 1: <H1-INTRO> => SP-H1
    if token == "<h1-intro>":
        return "SP-H1"

    # Rule 2: <SUM> + text containing SUMMARY heading => EOC-H1
    if token == "<sum>":
        if "summary" in remainder or "summary" in token:
            return "EOC-H1"
        # Marker-only <SUM> without SUMMARY text → PMI
        if _is_marker_only(text):
            return "PMI"
        return None

    # Rule 3: <H1> + heading text "REFERENCES" (case-insensitive) => REFH1
    if token == "<h1>":
        if re.match(r"^\s*references\s*$", remainder, re.IGNORECASE):
            return "REFH1"
        # Other <H1> cases are already handled by the validator's
        # _inline_heading_tag logic; do not double-override here.
        return None

    # Rule 4: generic marker-only paragraphs → PMI
    if _is_marker_only(text):
        return "PMI"

    return None


def apply_marker_overrides(
    blocks: Sequence[dict],
    classifications: list[dict],
) -> list[dict]:
    """Apply deterministic marker-token overrides to *classifications*.

    Called once in the pipeline after ``validate_and_repair``.  Iterates
    through every block, looks for a leading marker token, resolves a style,
    checks zone validity, and overwrites the classification entry when a rule
    fires.

    Returns a **new** list (shallow copies of dicts that changed; originals
    for those that did not).
    """
    block_lookup = {b["id"]: b for b in blocks}
    result: list[dict] = []

    for clf in classifications:
        para_id = clf.get("id")
        block = block_lookup.get(para_id, {})
        text = block.get("text", "")
        meta = block.get("metadata", {})

        token = parse_marker_token(text)
        if token is None:
            result.append(clf)
            continue

        style = resolve_marker_style(token, text, meta)
        if style is None:
            result.append(clf)
            continue

        # Zone safety: PMI is universally valid; for non-PMI styles, check
        # that the resolved style is valid in the block's zone.  If not,
        # skip the override so we don't break zone/list logic.
        zone = meta.get("context_zone", "BODY")
        if style != "PMI" and not validate_style_for_zone(style, zone):
            logger.debug(
                "marker-override skipped: %s not valid in zone %s (para %s)",
                style,
                zone,
                para_id,
            )
            result.append(clf)
            continue

        # Apply the override.
        new_clf = {
            **clf,
            "tag": style,
            "confidence": max(float(clf.get("confidence", 0)), 0.99),
            "repaired": True,
            "repair_reason": (
                (clf.get("repair_reason") or "") + ",marker-override"
            ).lstrip(","),
        }
        logger.info(
            "marker-override: para %s  %s -> %s  (token=%s)",
            para_id,
            clf.get("tag"),
            style,
            token,
        )
        result.append(new_clf)

    return result
