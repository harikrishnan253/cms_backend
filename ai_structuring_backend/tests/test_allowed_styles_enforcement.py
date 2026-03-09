import sys
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from processor.validator import validate_and_repair


def test_high_confidence_allowed_tag_is_preserved():
    blocks = [
        {"id": 1, "text": "Suggested Reading", "metadata": {"context_zone": "BACK_MATTER", "list_kind": "unordered", "list_position": "FIRST"}},
    ]
    classifications = [
        {"id": 1, "tag": "SR", "confidence": 0.95},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"SR", "TXT"})
    assert repaired[0]["tag"] == "SR"


def test_not_allowed_tag_downgrades_to_txt():
    blocks = [
        {"id": 1, "text": "Some text", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "NOT-A-STYLE", "confidence": 0.95},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TXT"})
    assert repaired[0]["tag"] == "TXT"
    assert repaired[0].get("repair_reason") is not None


# -----------------------------------------------------------------------
# Task-4 regression: unsuffixed positional family must prefer MID
# -----------------------------------------------------------------------

# allowed set that contains all three positional variants of ANS-UL / ANS-NL
# so the test verifies MID is chosen, not FIRST or LAST
_ANS_ALLOWED = {
    "TXT",
    "ANS-UL-FIRST", "ANS-UL-MID", "ANS-UL-LAST",
    "ANS-NL-FIRST", "ANS-NL-MID", "ANS-NL-LAST",
}


def test_ans_ul_unsuffixed_repairs_to_mid():
    """ANS-UL (unsuffixed) must resolve deterministically to ANS-UL-MID, not FIRST."""
    blocks = [
        {"id": 1, "text": "Bullet item", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "ANS-UL", "confidence": 0.85},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles=_ANS_ALLOWED)
    assert repaired[0]["tag"] == "ANS-UL-MID", (
        f"Expected ANS-UL-MID but got {repaired[0]['tag']!r} — "
        "unsuffixed list families must prefer MID over FIRST"
    )


def test_ans_nl_unsuffixed_repairs_to_mid():
    """ANS-NL (unsuffixed) must resolve deterministically to ANS-NL-MID, not FIRST."""
    blocks = [
        {"id": 1, "text": "Numbered item", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "ANS-NL", "confidence": 0.85},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles=_ANS_ALLOWED)
    assert repaired[0]["tag"] == "ANS-NL-MID", (
        f"Expected ANS-NL-MID but got {repaired[0]['tag']!r} — "
        "unsuffixed list families must prefer MID over FIRST"
    )


def test_completely_unknown_tag_still_downgrades_to_txt():
    """A tag with no family relation at all must still fall back to TXT.

    Confirms existing generic-fallback behavior is preserved after Task-4 fix,
    even when a richer allowed set is present.
    """
    blocks = [
        {"id": 1, "text": "Some text", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "XYZZY-TOTALLY-UNKNOWN", "confidence": 0.85},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles=_ANS_ALLOWED)
    assert repaired[0]["tag"] == "TXT"
    assert repaired[0].get("repair_reason") is not None


# -----------------------------------------------------------------------
# Task-8 regression: TUL alias + log-level semantics
# -----------------------------------------------------------------------

_TUL_ALLOWED = {"TXT", "TUL-FIRST", "TUL-MID", "TUL-LAST"}


def test_tul_unsuffixed_repairs_to_mid():
    """Unsuffixed TUL (via alias) must map to TUL-MID, not TUL-FIRST."""
    blocks = [
        {"id": 1, "text": "Table unordered item", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [
        {"id": 1, "tag": "TUL", "confidence": 0.85},
    ]
    repaired = validate_and_repair(classifications, blocks, allowed_styles=_TUL_ALLOWED)
    assert repaired[0]["tag"] == "TUL-MID", (
        f"Expected TUL-MID but got {repaired[0]['tag']!r} — "
        "unsuffixed TUL must resolve via alias to TUL-MID"
    )


def test_tul_last_alias_repairs_to_mid():
    """TUL-LAST alias must map to TUL-MID when only MID is in allowed set."""
    blocks = [
        {"id": 1, "text": "Table unordered item", "metadata": {"context_zone": "TABLE"}},
    ]
    classifications = [
        {"id": 1, "tag": "TUL-LAST", "confidence": 0.85},
    ]
    # Allowed set intentionally excludes TUL-LAST to test alias → MID mapping
    repaired = validate_and_repair(classifications, blocks, allowed_styles={"TXT", "TUL-MID"})
    assert repaired[0]["tag"] == "TUL-MID", (
        f"Expected TUL-MID but got {repaired[0]['tag']!r} — "
        "TUL-LAST alias must resolve to TUL-MID"
    )


def _capture_validator_logs(classifications, blocks, allowed_styles):
    """Run validate_and_repair and return all log messages from processor.validator."""
    messages = []

    class _Cap(logging.Handler):
        def emit(self, record):
            messages.append((record.levelno, record.getMessage()))

    cap = _Cap()
    cap.setLevel(logging.DEBUG)
    lg = logging.getLogger("processor.validator")
    prev_level = lg.level
    lg.setLevel(logging.DEBUG)
    lg.addHandler(cap)
    try:
        result = validate_and_repair(classifications, blocks, allowed_styles=allowed_styles)
    finally:
        lg.removeHandler(cap)
        lg.setLevel(prev_level)
    return result, messages


def test_semantic_repair_logs_info_not_warning():
    """Semantic repair to a specific tag must log at INFO, not WARNING.

    'downgraded' must not appear in the message; 'semantic-repair' must.
    """
    blocks = [
        {"id": 1, "text": "Answer bullet", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "ANS-UL-FIRST", "confidence": 0.85},
    ]
    # allowed set without ANS-UL-FIRST → forces semantic repair to ANS-UL-MID
    allowed = {"TXT", "ANS-UL-MID", "ANS-UL-LAST"}
    result, msgs = _capture_validator_logs(classifications, blocks, allowed)

    assert result[0]["tag"] == "ANS-UL-MID"

    repair_msgs = [(lvl, m) for lvl, m in msgs if "not allowed" in m]
    assert repair_msgs, "Expected at least one 'not allowed' log message"

    for lvl, m in repair_msgs:
        assert "downgraded" not in m, (
            f"Semantic repair must not log 'downgraded'; got: {m!r}"
        )
        assert "semantic-repair" in m, (
            f"Semantic repair must log 'semantic-repair'; got: {m!r}"
        )
        assert lvl == logging.INFO, (
            f"Semantic repair must log at INFO, got level {lvl}; msg: {m!r}"
        )


def test_unknown_tag_logs_warning_on_downgrade():
    """True hard-fallback downgrade to TXT must log at WARNING with 'downgraded'."""
    blocks = [
        {"id": 1, "text": "Some text", "metadata": {"context_zone": "BODY"}},
    ]
    classifications = [
        {"id": 1, "tag": "XYZZY-TOTALLY-UNKNOWN", "confidence": 0.85},
    ]
    result, msgs = _capture_validator_logs(classifications, blocks, {"TXT"})

    assert result[0]["tag"] == "TXT"

    warning_msgs = [m for lvl, m in msgs if lvl == logging.WARNING and "downgraded" in m]
    assert warning_msgs, (
        "Hard fallback to TXT must emit a WARNING with 'downgraded'"
    )
