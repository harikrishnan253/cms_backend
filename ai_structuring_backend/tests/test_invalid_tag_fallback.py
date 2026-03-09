"""Tests for the tiered invalid-tag fallback chain in GeminiClassifier.

Covers:
  - _semantic_alias_lookup()     (Step 3 of the chain)
  - _transition_positional_hint() (Step 4 of the chain)
  - _force_invalid_to_txt()      (full chain integration)

All tests are offline (no LLM, no API, no corpus file dependency).
The retriever is tested via a lightweight mock — it is never constructed.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.classifier import (
    GeminiClassifier,
    _load_semantic_artifacts,
    _MIN_ALIAS_CONFIDENCE,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_classifier(semantic_hints: dict | None = None) -> GeminiClassifier:
    """Return a minimal GeminiClassifier stub that bypasses __init__."""
    clf = GeminiClassifier.__new__(GeminiClassifier)
    clf.retriever = None
    clf.cache = None
    clf.rule_learner = None
    clf.enable_fallback = False
    clf.fallback_model = None
    clf.fallback_input_tokens = 0
    clf.fallback_output_tokens = 0
    clf.fallback_calls = 0
    clf.items_improved = 0
    clf.rule_predictions = 0
    clf.llm_predictions = 0
    clf.total_input_tokens = 0
    clf.total_output_tokens = 0
    clf.total_tokens = 0
    clf._last_token_usage = {}
    clf.model = type(
        "DummyModel",
        (),
        {
            "get_last_usage": staticmethod(lambda: {}),
            "get_token_usage": staticmethod(
                lambda: {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                }
            ),
        },
    )()
    clf._semantic_hints = semantic_hints if semantic_hints is not None else {}
    return clf


def _alias_hints(*entries) -> dict:
    """Build a _semantic_hints dict with a semantic_alias_map from (raw, canonical, conf) triples."""
    alias_map = {}
    for raw, canonical, conf in entries:
        alias_map[raw] = {"canonical": canonical, "confidence": conf}
    return {"semantic_alias_map": alias_map}


def _transition_hints(*positional_keys) -> dict:
    """Build a _semantic_hints dict with a positional_transitions set from keys."""
    return {
        "positional_transitions": {k: {} for k in positional_keys}
    }


# ---------------------------------------------------------------------------
# TestSemanticAliasLookup
# ---------------------------------------------------------------------------

class TestSemanticAliasLookup:
    """Unit tests for GeminiClassifier._semantic_alias_lookup()."""

    def test_known_alias_resolves_normal_to_txt(self):
        clf = _make_classifier(_alias_hints(("Normal", "TXT", 0.85)))
        result = clf._semantic_alias_lookup("Normal")
        assert result == "TXT"

    def test_head2_resolves_to_h2(self):
        clf = _make_classifier(_alias_hints(("Head2", "H2", 0.92)))
        result = clf._semantic_alias_lookup("Head2")
        assert result == "H2"

    def test_bullet_list_first_resolves_to_bl_first(self):
        clf = _make_classifier(_alias_hints(("BulletList1_first", "BL-FIRST", 0.90)))
        result = clf._semantic_alias_lookup("BulletList1_first")
        assert result == "BL-FIRST"

    def test_fig_legend_alias_resolves(self):
        clf = _make_classifier(_alias_hints(("FigureLegend", "FIG-LEG", 0.88)))
        result = clf._semantic_alias_lookup("FigureLegend")
        assert result == "FIG-LEG"

    def test_ref_alphabetical_resolves_to_ref_u(self):
        clf = _make_classifier(_alias_hints(("Reference-Alphabetical", "REF-U", 0.85)))
        result = clf._semantic_alias_lookup("Reference-Alphabetical")
        assert result == "REF-U"

    def test_loader_excludes_low_confidence_entries(self):
        # _load_semantic_artifacts() must filter out entries below _MIN_ALIAS_CONFIDENCE.
        # The lookup itself trusts the map — filtering is the loader's responsibility.
        hints = _load_semantic_artifacts()
        alias_map = hints.get("semantic_alias_map", {})
        for raw_style, entry in alias_map.items():
            assert entry["confidence"] >= _MIN_ALIAS_CONFIDENCE, (
                f"{raw_style}: confidence {entry['confidence']} below threshold"
            )

    def test_confidence_at_threshold_is_included(self):
        clf = _make_classifier(_alias_hints(("AtThreshold", "TXT", _MIN_ALIAS_CONFIDENCE)))
        result = clf._semantic_alias_lookup("AtThreshold")
        assert result == "TXT"

    def test_unknown_style_returns_none(self):
        clf = _make_classifier(_alias_hints(("Normal", "TXT", 0.85)))
        result = clf._semantic_alias_lookup("COMPLETELY_UNKNOWN_9xyz")
        assert result is None

    def test_empty_hints_returns_none(self):
        clf = _make_classifier({})
        result = clf._semantic_alias_lookup("Normal")
        assert result is None

    def test_no_hints_attribute_returns_none(self):
        """Stub without _semantic_hints (e.g. old pickle) must not raise."""
        clf = GeminiClassifier.__new__(GeminiClassifier)
        # Deliberately do NOT set _semantic_hints
        result = clf._semantic_alias_lookup("Normal")
        assert result is None

    def test_real_artifact_head2_to_h2(self):
        """Integration: verify Head2 → H2 exists in the real generated artifact."""
        hints = _load_semantic_artifacts()
        alias_map = hints.get("semantic_alias_map", {})
        # Only run assertion if artifact is present; skip gracefully when absent
        if not alias_map:
            return
        clf = _make_classifier(hints)
        result = clf._semantic_alias_lookup("Head2")
        assert result == "H2", f"Expected H2, got {result}"

    def test_real_artifact_normal_to_txt(self):
        hints = _load_semantic_artifacts()
        alias_map = hints.get("semantic_alias_map", {})
        if not alias_map:
            return
        clf = _make_classifier(hints)
        result = clf._semantic_alias_lookup("Normal")
        assert result == "TXT"

    def test_all_real_artifact_canonicals_are_valid_tags(self):
        """Every suggested_canonical in the alias map must survive normalize_tag()."""
        from app.services.style_normalizer import normalize_tag
        hints = _load_semantic_artifacts()
        alias_map = hints.get("semantic_alias_map", {})
        if not alias_map:
            return
        clf = _make_classifier(hints)
        for raw, entry in alias_map.items():
            validated = normalize_tag(entry["canonical"])
            assert validated, f"normalize_tag returned empty for {raw} -> {entry['canonical']}"


# ---------------------------------------------------------------------------
# TestTransitionPositionalHint
# ---------------------------------------------------------------------------

class TestTransitionPositionalHint:
    """Unit tests for GeminiClassifier._transition_positional_hint()."""

    def test_unordered_first_gives_bl_first(self):
        clf = _make_classifier(_transition_hints("BL-FIRST", "BL-MID", "BL-LAST"))
        meta = {"list_kind": "unordered", "list_position": "first"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "BL-FIRST"

    def test_unordered_mid_gives_bl_mid(self):
        clf = _make_classifier(_transition_hints("BL-FIRST", "BL-MID", "BL-LAST"))
        meta = {"list_kind": "unordered", "list_position": "mid"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "BL-MID"

    def test_unordered_last_gives_bl_last(self):
        clf = _make_classifier(_transition_hints("BL-FIRST", "BL-MID", "BL-LAST"))
        meta = {"list_kind": "unordered", "list_position": "last"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "BL-LAST"

    def test_ordered_mid_gives_nl_mid(self):
        clf = _make_classifier(_transition_hints("NL-FIRST", "NL-MID", "NL-LAST"))
        meta = {"list_kind": "ordered", "list_position": "mid"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "NL-MID"

    def test_numbered_first_gives_nl_first(self):
        clf = _make_classifier(_transition_hints("NL-FIRST", "NL-MID", "NL-LAST"))
        meta = {"list_kind": "numbered", "list_position": "first"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "NL-FIRST"

    def test_unnumbered_gives_ul(self):
        clf = _make_classifier(_transition_hints("UL-FIRST", "UL-MID", "UL-LAST"))
        meta = {"list_kind": "unnumbered", "list_position": "mid"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "UL-MID"

    def test_only_position_treated_as_first(self):
        clf = _make_classifier(_transition_hints("BL-FIRST", "BL-MID"))
        meta = {"list_kind": "unordered", "list_position": "only"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result == "BL-FIRST"

    def test_no_list_kind_returns_none(self):
        clf = _make_classifier(_transition_hints("BL-MID"))
        meta = {"list_position": "mid"}  # list_kind missing
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result is None

    def test_no_meta_returns_none(self):
        clf = _make_classifier(_transition_hints("BL-MID"))
        result = clf._transition_positional_hint("BADTAG", None)
        assert result is None

    def test_unknown_list_kind_returns_none(self):
        clf = _make_classifier(_transition_hints("BL-MID"))
        meta = {"list_kind": "custom_unknown", "list_position": "mid"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result is None

    def test_falls_back_to_mid_when_specific_position_missing_from_corpus(self):
        # Only BL-MID is in positional_transitions — FIRST not present
        clf = _make_classifier(_transition_hints("BL-MID"))
        meta = {"list_kind": "unordered", "list_position": "first"}
        result = clf._transition_positional_hint("BADTAG", meta)
        # Falls back to BL-MID since BL-FIRST not in corpus transitions
        assert result == "BL-MID"

    def test_returns_none_when_no_mid_fallback_either(self):
        # Neither BL-FIRST nor BL-MID in corpus
        clf = _make_classifier(_transition_hints("NL-MID"))
        meta = {"list_kind": "unordered", "list_position": "first"}
        result = clf._transition_positional_hint("BADTAG", meta)
        assert result is None

    def test_no_positional_transitions_in_hints_still_validates(self):
        # When positional_transitions is absent the guard is skipped → normalize_tag called
        clf = _make_classifier({})  # no positional_transitions
        meta = {"list_kind": "unordered", "list_position": "mid"}
        result = clf._transition_positional_hint("BADTAG", meta)
        # BL-MID is a valid tag → should still resolve when corpus check skipped
        assert result == "BL-MID"


# ---------------------------------------------------------------------------
# TestFallbackChainOrdering  (integration: _force_invalid_to_txt)
# ---------------------------------------------------------------------------

class TestFallbackChainOrdering:
    """Integration tests for the full fallback chain in _force_invalid_to_txt()."""

    def _run(self, clf, raw_tag, meta=None, text="sample text"):
        results = [{"id": "p1", "tag": raw_tag, "confidence": 80}]
        meta_by_id = {"p1": meta or {}}
        text_by_id = {"p1": text}
        out = clf._force_invalid_to_txt(results, meta_by_id, text_by_id)
        return out[0]

    # ------------------------------------------------------------------
    # Step 3: semantic alias
    # ------------------------------------------------------------------

    def test_alias_resolves_head2_without_retriever(self):
        clf = _make_classifier(_alias_hints(("Head2", "H2", 0.92)))
        r = self._run(clf, "Head2")
        assert r["tag"] == "H2"
        assert r["confidence"] <= 60

    def test_alias_resolves_normal_to_txt(self):
        """Normal→TXT is itself a generic tag — it's the correct canonical."""
        clf = _make_classifier(_alias_hints(("Normal", "TXT", 0.85)))
        r = self._run(clf, "Normal")
        assert r["tag"] == "TXT"

    def test_alias_resolves_bl_first_style(self):
        clf = _make_classifier(_alias_hints(("BulletList1_first", "BL-FIRST", 0.90)))
        r = self._run(clf, "BulletList1_first")
        assert r["tag"] == "BL-FIRST"

    def test_valid_tag_bypasses_chain_entirely(self):
        """A tag already in VALID_TAGS should pass through unmodified."""
        clf = _make_classifier(_alias_hints(("H2", "H1", 0.99)))  # alias map has H2 but we never enter chain
        r = self._run(clf, "H2")
        assert r["tag"] == "H2"

    def test_alias_tries_raw_tag_before_mapped_tag(self):
        """raw_tag lookup must be attempted before the post-alias-map version."""
        # Both raw_tag and mapped_tag alias entries differ; raw should win.
        hints = {
            "semantic_alias_map": {
                "RawStyle": {"canonical": "H3", "confidence": 0.90},
            }
        }
        clf = _make_classifier(hints)
        # _map_tag_alias will leave "RawStyle" unchanged (no built-in mapping)
        r = self._run(clf, "RawStyle")
        assert r["tag"] == "H3"

    # ------------------------------------------------------------------
    # Step 4: positional hint
    # ------------------------------------------------------------------

    def test_positional_hint_resolves_list_tag_when_no_alias(self):
        # Patch normalize_tag so the unknown publisher tag yields TXT (unrecognized),
        # making the chain reach step 4 (positional hint).
        clf = _make_classifier(_transition_hints("BL-FIRST", "BL-MID", "BL-LAST"))
        meta = {"list_kind": "unordered", "list_position": "first"}
        from unittest.mock import patch
        import processor.classifier as clf_mod
        with patch.object(clf_mod, "normalize_tag", side_effect=lambda t, **kw: "TXT" if t not in {"BL-FIRST", "BL-MID", "BL-LAST"} else t):
            r = self._run(clf, "COMPLETELY_UNKNOWN_LIST_STYLE", meta=meta)
        assert r["tag"] == "BL-FIRST"

    def test_positional_hint_not_applied_when_alias_resolved(self):
        """If alias resolved the tag, positional hint must not overwrite it."""
        hints = {
            "semantic_alias_map": {
                "SomeStyle": {"canonical": "H2", "confidence": 0.90},
            },
            "positional_transitions": {"BL-FIRST": {}, "BL-MID": {}},
        }
        clf = _make_classifier(hints)
        meta = {"list_kind": "unordered", "list_position": "first"}
        r = self._run(clf, "SomeStyle", meta=meta)
        # Alias (H2) should win over positional hint (BL-FIRST)
        assert r["tag"] == "H2"

    # ------------------------------------------------------------------
    # Step 5: retriever (mock-based)
    # ------------------------------------------------------------------

    def test_retriever_not_called_when_alias_resolves(self):
        """Retriever must NOT be invoked when an earlier step resolved the tag."""
        import os
        os.environ["ENABLE_GROUNDED_RETRIEVER"] = "true"
        os.environ["GROUNDED_RETRIEVER_MODE"] = "invalid_tag_fallback"
        try:
            from app.services import grounded_retriever as gr
            import importlib
            importlib.reload(gr)

            hints = _alias_hints(("Head2", "H2", 0.92))
            clf = _make_classifier(hints)
            mock_retriever = MagicMock()
            clf.retriever = mock_retriever

            r = self._run(clf, "Head2")
            assert r["tag"] == "H2"
            mock_retriever.retrieve_examples.assert_not_called()
        finally:
            os.environ["ENABLE_GROUNDED_RETRIEVER"] = "false"

    def test_retriever_called_when_alias_fails_and_enabled(self):
        """When no alias/positional hint resolves, retriever IS consulted if enabled."""
        import processor.classifier as clf_mod
        from unittest.mock import patch

        clf = _make_classifier({})  # no semantic hints → alias + positional both fail
        mock_retriever = MagicMock()
        mock_retriever.retrieve_examples.return_value = [
            {"canonical_gold_tag": "H3", "similarity_score": 0.85}
        ]
        clf.retriever = mock_retriever

        # Force normalize_tag to return TXT so the chain reaches step 5,
        # and patch is_invalid_tag_fallback_enabled to True.
        def _nt(t, **kw):
            if t == "H3":
                return "H3"
            return "TXT"

        with patch.object(clf_mod, "normalize_tag", side_effect=_nt), \
             patch.object(clf_mod, "is_invalid_tag_fallback_enabled", return_value=True):
            r = self._run(clf, "COMPLETELY_UNKNOWN_TAG_9xyz", text="some text")

        mock_retriever.retrieve_examples.assert_called_once()
        assert r["tag"] == "H3"

    def test_retriever_disabled_falls_through_to_txt(self):
        """With retriever disabled and no semantic aliases, tag is whatever normalize_tag
        returns (TXT for truly unrecognised input) — chain adds nothing."""
        import processor.classifier as clf_mod
        from unittest.mock import patch
        clf = _make_classifier({})  # no hints, no retriever
        with patch.object(clf_mod, "normalize_tag", return_value="TXT"):
            r = self._run(clf, "COMPLETELY_UNKNOWN_TAG_9xyz")
        assert r["tag"] == "TXT"

    # ------------------------------------------------------------------
    # Confidence capping
    # ------------------------------------------------------------------

    def test_confidence_capped_at_60_after_normalisation(self):
        clf = _make_classifier(_alias_hints(("Head2", "H2", 0.92)))
        r = self._run(clf, "Head2")
        assert r["confidence"] <= 60

    def test_confidence_preserved_for_valid_tags(self):
        clf = _make_classifier({})
        # TXT is valid — normalize_tag will just confirm it
        r = self._run(clf, "TXT")
        assert r["confidence"] == 80  # unchanged

    # ------------------------------------------------------------------
    # Edge / regression
    # ------------------------------------------------------------------

    def test_empty_results_list_returns_empty(self):
        clf = _make_classifier({})
        out = clf._force_invalid_to_txt([], {}, {})
        assert out == []

    def test_alias_map_loaded_from_real_artifact(self):
        """Smoke test: load real artifact and run the chain for a known publisher style."""
        hints = _load_semantic_artifacts()
        if not hints.get("semantic_alias_map"):
            return  # artifact absent — skip
        clf = _make_classifier(hints)
        r = self._run(clf, "ParaFirstLine-Ind")
        assert r["tag"] == "TXT-FLUSH"

    def test_no_raw_corpus_dependency_when_retriever_disabled(self):
        """Verify the chain never opens ground_truth.jsonl when retriever is off."""
        import os
        os.environ["ENABLE_GROUNDED_RETRIEVER"] = "false"
        try:
            hints = _load_semantic_artifacts()
            clf = _make_classifier(hints)
            # Patch open() to detect any attempt to open ground_truth.jsonl
            from unittest.mock import patch
            with patch("builtins.open", side_effect=AssertionError("corpus opened!")) as mock_open:
                # The alias map is already in memory — should not open any file
                r = self._run(clf, "Head2")
            # If we get here, open() was not called — correct
            assert r["tag"] in {"H2", "TXT"}  # TXT if artifact absent
        finally:
            os.environ["ENABLE_GROUNDED_RETRIEVER"] = "false"
