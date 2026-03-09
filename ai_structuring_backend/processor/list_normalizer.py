"""
List-run position normalization.

After classification, validation, marker overrides, and box normalization,
the tag sequence may still have broken position continuity within list runs.
This pass walks classifications in document order, identifies contiguous runs
of same-family list tags, and rewrites their position suffixes to form correct
FIRST / MID / LAST sequences.

Two important refinements over strict contiguity matching:

1. **Nested-level transparency** (Fix B): Sub-level items (e.g. ``BL2``, ``BL3``)
   are treated as transparent to an enclosing outer-level run (e.g. ``BL``).
   This means an outer list that wraps a sub-list correctly produces
   FIRST … MID … LAST across the outer items, rather than fragmenting into
   multiple single-item FIRST runs every time a sub-level interrupts.

2. **PMI-bridge transparency** (Fix C): A ``PMI``-tagged block that sits
   between two same-family list items and whose source text is empty or is a
   structural marker token (e.g. ``</BL>``, ``<NOTE>``) is treated as
   transparent when building runs.  The PMI tag itself is never modified.

Runs after ``normalize_box_styles`` and before ``emit_style_tag_trace``.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

_POSITION_RE = re.compile(r"^(.+)-(FIRST|MID|LAST)$")
# Structural marker pattern (same as marker_lock.py): <ANYTHING>
_MARKER_RE = re.compile(r"^<[^<>]+>$")


def _list_family(tag: str) -> str | None:
    """Extract the family prefix from a position-suffixed tag.

    Returns the family string (e.g. ``"BL"``, ``"BX1-BL"``, ``"KT-BL2"``) or
    *None* if *tag* does not carry a ``-FIRST``, ``-MID``, or ``-LAST`` suffix.

    >>> _list_family("BL-FIRST")
    'BL'
    >>> _list_family("BX1-BL-MID")
    'BX1-BL'
    >>> _list_family("KT-BL2-LAST")
    'KT-BL2'
    >>> _list_family("TXT")
    """
    m = _POSITION_RE.match(tag or "")
    return m.group(1) if m else None


def _family_base(family: str) -> str:
    """Strip trailing digit(s) from a family string to get the base family.

    This is used to determine whether two families are at different nesting
    levels within the same logical list tree.

    >>> _family_base("BL")
    'BL'
    >>> _family_base("BL2")
    'BL'
    >>> _family_base("KT-BL2")
    'KT-BL'
    >>> _family_base("BX1-NL3")
    'BX1-NL'
    """
    return re.sub(r"\d+$", "", family)


def _is_deeper_family(outer: str, candidate: str) -> bool:
    """Return True if *candidate* is a deeper nesting level of *outer*.

    A deeper family shares the same base (after stripping trailing digits) but
    has a higher numeric suffix, OR a suffix where outer has none.

    Examples::

        _is_deeper_family("BL",    "BL2")    → True
        _is_deeper_family("BL",    "BL3")    → True
        _is_deeper_family("KT-BL", "KT-BL2") → True
        _is_deeper_family("BL2",   "BL")     → False  (BL is shallower)
        _is_deeper_family("BL",    "BL")     → False  (same level)
        _is_deeper_family("BL",    "NL")     → False  (different family tree)
    """
    if outer == candidate:
        return False
    base_outer = _family_base(outer)
    base_candidate = _family_base(candidate)
    if base_outer != base_candidate:
        return False
    # Same base → candidate is deeper when it has a suffix and outer does not,
    # or when candidate's numeric suffix is greater than outer's.
    outer_num = re.search(r"\d+$", outer)
    cand_num = re.search(r"\d+$", candidate)
    outer_level = int(outer_num.group()) if outer_num else 0
    cand_level = int(cand_num.group()) if cand_num else 0
    return cand_level > outer_level


def _is_pmi_bridge(
    i: int,
    families: list[str | None],
    classifications: list[dict],
    blocks: Sequence[dict],
) -> bool:
    """Return True if position *i* is a PMI that should be transparent to run
    grouping.

    A PMI is bridgeable when ALL of the following hold:

    * Its tag is ``PMI``.
    * Its source text is empty/whitespace OR matches the structural marker
      pattern (``^<[^<>]+>$``).  This excludes list-scope-closing markers
      (``</BL>``, ``</NL>``, ``</UL>``) — those intentionally end lists.
    * It sits between two positions that both have a list family.
    * The list family on both sides shares the same *base* (e.g. ``BL`` on
      left, ``BL`` or ``BL2`` on right).

    The PMI block is never modified; this flag only affects run-length math.
    """
    clf = classifications[i]
    if clf.get("tag") != "PMI":
        return False

    # Find corresponding block text (blocks may be shorter if lists differ)
    block_text = ""
    clf_id = clf.get("id")
    for b in blocks:
        if b.get("id") == clf_id:
            block_text = b.get("text", "")
            break

    stripped = block_text.strip()

    # Non-empty, non-marker text is meaningful content — don't bridge it.
    if stripped and not _MARKER_RE.match(stripped):
        return False

    # Closing list-scope markers intentionally end a list — never bridge them.
    if re.match(r"^</?(BL|NL|UL|LL)\d*>$", stripped, re.IGNORECASE):
        return False

    # Require a list family on both sides (within window of ±1 non-bridge).
    # Scan left for nearest list family.
    left_family = None
    for li in range(i - 1, -1, -1):
        if families[li] is not None:
            left_family = families[li]
            break
        # If we hit another non-bridge PMI or non-list tag, stop.
        if classifications[li].get("tag") not in ("PMI",):
            break

    right_family = None
    for ri in range(i + 1, len(families)):
        if families[ri] is not None:
            right_family = families[ri]
            break
        if classifications[ri].get("tag") not in ("PMI",):
            break

    if left_family is None or right_family is None:
        return False

    # Bridge only when both sides share the same base family tree.
    return _family_base(left_family) == _family_base(right_family)


def normalize_list_runs(
    blocks: Sequence[dict],
    classifications: list[dict],
    allowed_styles: Iterable[str] | None = None,
) -> list[dict]:
    """Rewrite list-position suffixes so contiguous same-family runs
    have correct FIRST / MID / LAST continuity.

    Parameters
    ----------
    blocks : sequence of dict
        Block list, used to look up paragraph text for PMI-bridge detection.
    classifications : list of dict
        Current classification dicts, in document order.
    allowed_styles : iterable of str, optional
        Valid style tags.  When a rewritten tag is not in this set the
        original tag is kept.  Pass *None* to skip validation.

    Returns
    -------
    list of dict
        New classification list (shallow copies for changed entries,
        originals for unchanged).

    Algorithm
    ---------
    Two refinements over strict contiguity:

    * **Nested-level transparency**: An inner family (e.g. ``BL2``) that
      interrupts an outer run (e.g. ``BL``) does not terminate the outer run.
      The outer run "resumes" after the inner sub-run.  Inner sub-runs are
      processed independently for their own FIRST/MID/LAST.

    * **PMI-bridge transparency**: Empty or marker-only PMI entries between
      same-tree list entries are skipped for run-boundary purposes.  The PMI
      tag is never modified.
    """
    if not classifications:
        return classifications

    allowed: set[str] | None = (
        set(allowed_styles) if allowed_styles is not None else None
    )

    n = len(classifications)
    result: list[dict] = list(classifications)

    # Extract family for every entry up-front.
    families: list[str | None] = [
        _list_family(c.get("tag", "")) for c in classifications
    ]

    # Pre-compute PMI-bridge flags (only bridgeable PMI positions).
    bridges: list[bool] = [False] * n
    for i in range(n):
        if families[i] is None:
            bridges[i] = _is_pmi_bridge(i, families, classifications, blocks)

    # -----------------------------------------------------------------------
    # Two-pass algorithm:
    #
    # Pass 1 – identify outer-level run extents.
    #   An outer run starts at index i with family F and extends until we see
    #   a tag that is neither:
    #     • the same family F, nor
    #     • a deeper family of F (shares base with F), nor
    #     • a PMI bridge.
    #
    # Pass 2 – within each outer run, identify and assign positions to the
    #   outer-family segments (ignoring deeper entries for outer position math)
    #   and recursively assign positions to each inner sub-run.
    # -----------------------------------------------------------------------

    def _assign_run(indices: list[int], desired_positions: list[str]) -> None:
        """Write desired positions for a flat list of same-family indices."""
        for k, pos in zip(indices, desired_positions):
            family = families[k]
            if family is None:
                continue
            new_tag = f"{family}-{pos}"
            old_tag = classifications[k].get("tag", "")
            if new_tag == old_tag:
                continue
            if allowed is not None and new_tag not in allowed:
                logger.debug(
                    "list-run-norm: skip para %s  %s -> %s (not in allowed_styles)",
                    classifications[k].get("id"),
                    old_tag,
                    new_tag,
                )
                continue
            result[k] = {
                **classifications[k],
                "tag": new_tag,
                "repaired": True,
                "repair_reason": (
                    (classifications[k].get("repair_reason") or "")
                    + ",list-run-norm"
                ).lstrip(","),
            }
            logger.debug(
                "list-run-norm: para %s  %s -> %s",
                result[k].get("id"),
                old_tag,
                new_tag,
            )

    def _positions_for_count(count: int) -> list[str]:
        if count == 1:
            return ["FIRST"]
        return ["FIRST"] + ["MID"] * (count - 2) + ["LAST"]

    def _process_outer_run(start: int, end: int, outer_family: str) -> None:
        """Process a run from *start* to *end* (exclusive) rooted at *outer_family*.

        Outer-family indices get FIRST/MID/LAST based on their count among
        outer-family positions within this span.  Any inner-level spans are
        processed recursively.
        """
        # Collect outer-family index positions (ignoring bridges and deeper families)
        outer_indices: list[int] = []
        for idx in range(start, end):
            fam = families[idx]
            if fam is None:
                continue  # PMI bridge or non-list
            if fam == outer_family:
                outer_indices.append(idx)
            # Deeper families are handled below in inner sub-run processing

        # Assign FIRST/MID/LAST to the outer-family entries
        _assign_run(outer_indices, _positions_for_count(len(outer_indices)))

        # Now process inner sub-runs (deeper families) within this span.
        # Collect contiguous runs of each deeper family.
        i = start
        while i < end:
            fam = families[i]
            if fam is None or fam == outer_family or not _is_deeper_family(outer_family, fam):
                i += 1
                continue
            # Start of an inner run at level fam
            inner_family = fam
            j = i + 1
            while j < end:
                f = families[j]
                if f == inner_family:
                    j += 1
                elif f is None and bridges[j]:
                    j += 1  # transparent PMI inside inner run
                elif f is not None and _is_deeper_family(inner_family, f):
                    j += 1  # even deeper nesting inside this inner run
                else:
                    break
            # Recursively process the inner sub-run
            _process_outer_run(i, j, inner_family)
            i = j

    # Main loop: find top-level outer runs
    i = 0
    while i < n:
        fam = families[i]

        # Skip non-list entries (including PMI bridges at the start/end of doc)
        if fam is None:
            i += 1
            continue

        # Determine the extent of this outer run.
        # An outer run extends while we see:
        #   • same family, OR
        #   • deeper family, OR
        #   • PMI bridge (transparent).
        j = i + 1
        while j < n:
            f = families[j]
            if f == fam:
                j += 1
            elif f is None and bridges[j]:
                j += 1  # transparent PMI gap
            elif f is not None and _is_deeper_family(fam, f):
                j += 1  # deeper nesting within this outer run
            else:
                break

        _process_outer_run(i, j, fam)
        i = j

    return result
