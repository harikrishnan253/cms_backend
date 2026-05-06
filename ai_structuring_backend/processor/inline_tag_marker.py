"""
Inline tag marker locking.

When a paragraph's text begins with a literal ``<TAG>`` marker AND is
followed by content (``<CJC-TTL>Clinical Judgment Case``,
``<TBL-MID>1. Foo``, ``<UNT-T3>Onset``, ``<H2>Pain Control Theories``),
the author has authoritatively asserted the tag for that paragraph. The
classifier should respect the assertion instead of re-deriving the tag
from text content.

This module generalises the historical ``<H1>``-``<H6>`` inline-heading
override to any style in ``allowed_styles.json`` — e.g. ``<T2>``,
``<CJC-TTL>``, ``<TBL-MID>``, ``<UNT-T3>``, ``<NBX-TTL>``, ``<CST>``.

Blocks whose text is exactly ``<TAG>`` (no following content) are out of
scope here — :mod:`.marker_lock` already locks them to ``PMI`` (page
marker instruction). This module only fires when the paragraph carries
content after the marker.

Pipeline integration: runs as a Stage 1b pre-classification lock
alongside :func:`marker_lock.lock_marker_blocks`. Sets the existing
``lock_style`` / ``allowed_styles`` / ``skip_llm`` triple so the
deterministic gate in the classifier emits the marker tag at confidence
99, bypassing the LLM. Sets ``_inline_tag_override`` on the block so the
overlay layer skips it and the reconstruction layer can strip the
marker text from the output paragraph.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

# Canonical inline-marker pattern.
#
# - Anchored at paragraph start (allowing leading whitespace).
# - Tag name is uppercase alphanumeric with optional dash-separated
#   segments: ``H1``, ``T2``, ``CJC-TTL``, ``CJC-NN-TXT-FIRST``, ``BX1-CS``,
#   ``UNT-TXT-3``. Case-insensitive in the regex; canonicalisation against
#   ``allowed_styles`` is handled in :func:`extract_inline_tag`.
# - REQUIRES non-empty (non-whitespace) content after the closing ``>``.
#   A bare ``<TAG>`` paragraph is left to :func:`marker_lock.lock_marker_blocks`.
# - Excludes closing markers (``</TAG>``) — those are also handled by
#   :mod:`.marker_lock` as PMI.
INLINE_TAG_MARKER_RE = re.compile(
    r"^\s*<(?P<tag>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)>(?P<rest>.*\S.*)$",
    re.IGNORECASE | re.DOTALL,
)

# Authoritative-marker prefix — used by :mod:`structure_guard` and
# :mod:`integrity` to strip an inline tag marker from comparison text
# (reconstruction's marker strip is a legal style-only mutation, not a
# content change).
#
# Case-insensitive to mirror :data:`INLINE_TAG_MARKER_RE`, since authors
# occasionally write lowercase markers (e.g. "<h2>Central Nervous System"
# in `for table.docx`). The trailing ``(?=\S)`` lookahead requires
# non-whitespace content after the marker, so structural fences that
# appear alone on a paragraph ("<body-open>", "<front-close>") still
# survive normalization — those are deliberately preserved by the engine.
LEADING_INLINE_TAG_MARKER_RE = re.compile(
    r"^\s*<[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*>\s?(?=\S)",
)


def extract_inline_tag(
    text: str,
    allowed_styles: Iterable[str],
) -> tuple[str | None, str, str]:
    """Detect an authoritative inline tag marker at paragraph start.

    Returns ``(tag, marker_str, stripped_text)`` when ``text`` begins with
    a marker whose tag (case-insensitive) is present in ``allowed_styles``.
    Returns ``(None, "", text)`` otherwise.

    ``marker_str`` is the literal substring that should be removed from
    the source text on reconstruction (e.g. ``"<CJC-TTL>"`` — without
    surrounding whitespace).

    ``stripped_text`` is the text with the marker (and any single
    trailing space) removed; provided for callers that need the cleaned
    body. Marker stripping at reconstruction time should consult the
    block's first run rather than this string, because runs carry
    formatting that whole-text stripping would lose.
    """
    if not text:
        return None, "", text or ""
    m = INLINE_TAG_MARKER_RE.match(text)
    if not m:
        return None, "", text
    raw_tag = m.group("tag") or ""
    canon = _canonicalise_against_allowed(raw_tag, _build_allowed_lookup(allowed_styles))
    if canon is None:
        return None, "", text
    leading_ws_len = len(text) - len(text.lstrip())
    marker_str = text[leading_ws_len : leading_ws_len + len(raw_tag) + 2]  # <TAG>
    rest = text[leading_ws_len + len(raw_tag) + 2 :]
    if rest.startswith(" "):
        rest = rest[1:]
    return canon, marker_str, rest


def _build_allowed_lookup(allowed_styles: Iterable[str]) -> dict[str, str]:
    """Return an uppercase-key -> canonical-style dict for O(1) lookup.

    When the same dict is reused across many calls (the typical case
    inside :func:`lock_inline_tag_blocks`), pass it directly to
    :func:`_canonicalise_against_allowed` instead of paying the build
    cost per block.
    """
    if isinstance(allowed_styles, dict):
        return allowed_styles
    return {s.upper(): s for s in allowed_styles if s}


def _canonicalise_against_allowed(
    raw_tag: str,
    allowed_lookup: dict[str, str] | Iterable[str],
) -> str | None:
    """Return the canonical form of ``raw_tag`` if it matches an allowed
    style under case-insensitive comparison or alias normalisation;
    otherwise return ``None``.

    Handles common alias forms — e.g. the source might use ``REF-H1`` while
    the canonical vocabulary entry is ``REFH1``. ``normalize_style`` resolves
    the alias.
    """
    if not raw_tag:
        return None
    lookup = (
        allowed_lookup if isinstance(allowed_lookup, dict)
        else _build_allowed_lookup(allowed_lookup)
    )
    hit = lookup.get(raw_tag.upper())
    if hit is not None:
        return hit
    try:
        from app.services.style_normalizer import normalize_style
        normalised = normalize_style(raw_tag)
        if normalised:
            return lookup.get(normalised.upper())
    except Exception:
        pass
    return None


def lock_inline_tag_blocks(
    blocks: Sequence[dict],
    allowed_styles: Iterable[str],
) -> list[dict]:
    """Lock paragraphs whose text begins with an authoritative ``<TAG>``
    marker so the classifier emits the asserted tag deterministically.

    For each matching block, sets:

    * ``block["lock_style"]``           → ``True``
    * ``block["allowed_styles"]``       → ``[<extracted tag>]``
    * ``block["skip_llm"]``             → ``True``
    * ``block["_inline_tag_override"]`` → ``<extracted tag>`` (diagnostic
      flag also consumed by overlays + reconstruction)
    * ``block["_inline_tag_marker"]``   → literal marker substring
      (consumed by reconstruction to strip the marker from output text)

    Skipped:
    - Blocks whose text is empty or whitespace-only.
    - Marker-only blocks (text is exactly ``<TAG>``) — :mod:`.marker_lock`
      handles those as PMI.
    - Blocks whose marker tag is not in ``allowed_styles``.
    - Blocks already locked by an earlier stage (``lock_style is True``)
      to avoid stomping on the marker_lock PMI lock.
    """
    blocks_list = list(blocks)
    if not blocks_list:
        return blocks_list
    allowed_lookup = _build_allowed_lookup(allowed_styles or [])

    locked = 0
    for block in blocks_list:
        if block.get("lock_style") is True:
            continue
        text = block.get("text", "")
        if not text or not text.strip():
            continue
        tag, marker_str, _stripped = extract_inline_tag(text, allowed_lookup)
        if tag is None:
            continue
        block["lock_style"] = True
        block["allowed_styles"] = [tag]
        block["skip_llm"] = True
        block["_inline_tag_override"] = tag
        block["_inline_tag_marker"] = marker_str
        locked += 1

    if locked > 0:
        logger.info("INLINE_TAG_MARKER_LOCK locked=%d", locked)

    return blocks_list


def propagate_inline_marker_info(source: dict, target: dict) -> None:
    """Copy inline marker fields from a locked block to a classification dict.

    Used by both the deterministic gate and the classifier's skip-llm path
    so the marker info reaches reconstruction (which strips the leading
    ``<TAG>`` from the output text). No-op when the source has no
    override set.
    """
    if not source.get("_inline_tag_override"):
        return
    target["_inline_tag_override"] = source["_inline_tag_override"]
    target["_inline_tag_marker"] = source.get("_inline_tag_marker") or ""
