"""
Tests for LLM execution guardrails - ensuring LLM is invoked when it should be
and never silently skipped when eligible blocks exist.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock, Mock
from backend.processor.classifier import GeminiClassifier


@pytest.fixture
def mock_gemini_client():
    """Mock GeminiClient for testing."""
    with patch('backend.processor.classifier.GeminiClient') as mock_client:
        # Setup mock instance
        mock_instance = MagicMock()
        mock_instance.generate_content.return_value = MagicMock(
            text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Test"}]'
        )
        mock_instance.get_last_usage.return_value = {
            'input_tokens': 1000,
            'output_tokens': 500,
            'total_tokens': 1500
        }
        mock_instance.get_token_usage.return_value = {
            'total_input_tokens': 1000,
            'total_output_tokens': 500,
            'total_tokens': 1500,
            'api_calls': 1
        }
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def classifier(mock_gemini_client):
    """Create classifier instance for testing."""
    return GeminiClassifier(api_key="test-key", model_name="gemini-2.5-pro")


def _block(pid, text, zone="BODY", **meta_overrides):
    """Create test block with metadata."""
    meta = {"context_zone": zone}
    meta.update(meta_overrides)
    return {"id": pid, "text": text, "metadata": meta}


class TestPartialCacheTrigger:
    def test_partial_cache_forces_llm_invocation(self, classifier, mock_gemini_client, caplog):
        """Partial cache (cache_hits < total_eligible) must trigger LLM."""
        caplog.set_level(logging.INFO)

        # Setup: 3 blocks, 1 cached, 2 uncached
        blocks = [
            _block(1, "First paragraph", "BODY"),
            _block(2, "Second paragraph", "BODY"),
            _block(3, "Third paragraph", "BODY"),
        ]

        # Mock cache: only first block cached
        mock_cache = MagicMock()
        mock_cache.get.side_effect = lambda doc_id, para_index, text, zone: (
            {"id": 1, "tag": "TXT", "confidence": 90, "reasoning": "Cached"}
            if para_index == 1 else None
        )
        mock_cache.get_stats.return_value = {"hits": 1, "misses": 2}
        classifier.cache = mock_cache

        # Disable rule learner to force LLM path
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify LLM was invoked
        assert mock_gemini_client.generate_content.called, "LLM should be invoked with partial cache"

        # Verify LLM_EXECUTION_TRACE logging
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0, "LLM_EXECUTION_TRACE should be logged"

        trace_log = llm_trace_logs[0].message
        assert "eligible=3" in trace_log, "Should have 3 total eligible blocks"
        assert "cache_hits=1" in trace_log, "Should have 1 cache hit"
        assert "invoked=True" in trace_log, "LLM should be marked as invoked"

    def test_all_cached_skips_llm(self, classifier, mock_gemini_client, caplog):
        """All blocks cached (cache_hits == total_eligible) can skip LLM."""
        caplog.set_level(logging.INFO)

        blocks = [
            _block(1, "First paragraph", "BODY"),
            _block(2, "Second paragraph", "BODY"),
        ]

        # Mock cache: all blocks cached
        mock_cache = MagicMock()
        mock_cache.get.return_value = {"id": 1, "tag": "TXT", "confidence": 90, "reasoning": "Cached"}
        classifier.cache = mock_cache

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify LLM was NOT invoked
        assert not mock_gemini_client.generate_content.called, "LLM should not be invoked when all cached"

        # Verify LLM_EXECUTION_TRACE logging
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0, "LLM_EXECUTION_TRACE should be logged"

        trace_log = llm_trace_logs[0].message
        assert "eligible=2" in trace_log, "Should have 2 total eligible blocks"
        assert "cache_hits=2" in trace_log, "Should have 2 cache hits"
        assert "invoked=False" in trace_log, "LLM should not be marked as invoked"


class TestCacheIntegrityValidation:
    def test_cache_integrity_error_detected(self, classifier, mock_gemini_client, caplog):
        """Cache integrity error: This test verifies partial cache triggers LLM invocation."""
        caplog.set_level(logging.INFO)

        blocks = [
            _block(1, "First paragraph", "BODY"),
            _block(2, "Second paragraph", "BODY"),
        ]

        # Mock cache: partial cache (only 1 of 2 blocks cached)
        mock_cache = MagicMock()
        mock_cache.get.side_effect = lambda doc_id, para_index, text, zone: (
            {"id": 1, "tag": "TXT", "confidence": 90, "reasoning": "Cached"}
            if para_index == 1 else None
        )
        mock_cache.get_stats.return_value = {"hits": 1, "misses": 1}
        classifier.cache = mock_cache

        # Disable rule learner
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify LLM was invoked (partial cache must trigger LLM)
        assert mock_gemini_client.generate_content.called, "LLM should be invoked with partial cache"

        # Verify LLM_EXECUTION_TRACE shows partial cache
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0
        trace_log = llm_trace_logs[0].message
        assert "cache_hits=1" in trace_log, "Should show 1 cache hit"
        assert "invoked=True" in trace_log, "LLM should be invoked with partial cache"


class TestNoEligibleBlocksSkip:
    def test_no_eligible_blocks_skips_llm_correctly(self, classifier, caplog):
        """No eligible blocks (empty input) should skip LLM correctly."""
        caplog.set_level(logging.INFO)

        blocks = []

        # Call classify with empty blocks
        results = classifier.classify(blocks, "test_doc")

        # Should return empty results
        assert results == []

        # No LLM_EXECUTION_TRACE should be logged for empty input
        # (or it should show eligible=0 invoked=False)


class TestLLMExecutionLogging:
    def test_llm_execution_trace_contains_all_metrics(self, classifier, mock_gemini_client, caplog):
        """LLM_EXECUTION_TRACE should contain all required metrics."""
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Test paragraph", "BODY")]

        # Disable cache and rules to force LLM
        classifier.cache = None
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify LLM_EXECUTION_TRACE logging
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0, "LLM_EXECUTION_TRACE should be logged"

        trace_log = llm_trace_logs[0].message

        # Verify all required metrics
        assert "eligible=" in trace_log, "Should have eligible count"
        assert "invoked=" in trace_log, "Should have invoked flag"
        assert "attempted=" in trace_log, "Should have attempted flag"
        assert "successful=" in trace_log, "Should have successful flag"
        assert "cache_hits=" in trace_log, "Should have cache_hits count"
        assert "provider=" in trace_log, "Should have provider"
        assert "model=" in trace_log, "Should have model name"
        assert "token_count=" in trace_log, "Should have token count"

    def test_llm_invoked_flag_set_when_llm_runs(self, classifier, mock_gemini_client, caplog):
        """invoked flag should be True when LLM actually runs."""
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Test paragraph", "BODY")]

        # Disable cache and rules
        classifier.cache = None
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify invoked=True in trace log
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0
        assert "invoked=True" in llm_trace_logs[0].message, "invoked should be True when LLM runs"
        assert "attempted=True" in llm_trace_logs[0].message, "attempted should be True when LLM runs"
        assert "successful=True" in llm_trace_logs[0].message, "successful should be True when LLM returns results"


class TestTokenCountValidation:
    def test_token_count_greater_than_zero_when_invoked(self, classifier, mock_gemini_client, caplog):
        """Token count must be > 0 when LLM is invoked."""
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Test paragraph", "BODY")]

        # Disable cache and rules
        classifier.cache = None
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify token_count > 0 in trace log
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0

        trace_log = llm_trace_logs[0].message
        # Extract token_count value
        import re
        token_match = re.search(r'token_count=(\d+)', trace_log)
        assert token_match, "token_count should be present in trace log"
        token_count = int(token_match.group(1))
        assert token_count > 0, "token_count should be > 0 when LLM invoked"

    def test_token_count_zero_triggers_warning(self, classifier, mock_gemini_client, caplog):
        """Token count = 0 when LLM invoked should trigger warning."""
        caplog.set_level(logging.WARNING)

        blocks = [_block(1, "Test paragraph", "BODY")]

        # Mock get_last_usage to return 0 tokens
        mock_gemini_client.get_last_usage.return_value = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0
        }

        # Disable cache and rules
        classifier.cache = None
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify warning was logged
        token_warnings = [r for r in caplog.records if "LLM_TOKEN_COUNT_ERROR" in r.message]
        assert len(token_warnings) > 0, "LLM_TOKEN_COUNT_ERROR should be logged when token_count=0"


class TestRuleClassifiedPath:
    def test_rules_classify_all_blocks_skips_llm(self, classifier, mock_gemini_client, caplog):
        """All blocks classified by rules should skip LLM correctly."""
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Test paragraph", "BODY")]

        # Mock rule learner to classify all blocks
        mock_rule_learner = MagicMock()
        mock_rule_learner.rules = [{"condition": {}, "target": "TXT", "confidence": 0.9}]
        mock_rule_learner.apply_rules.return_value = "TXT"

        # Mock feature extractor
        mock_extractor = MagicMock()
        mock_extractor.extract_features.return_value = {}
        mock_rule_learner.feature_extractor = mock_extractor
        mock_rule_learner._feature_matches.return_value = True

        classifier.rule_learner = mock_rule_learner
        classifier.cache = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify LLM was NOT invoked
        assert not mock_gemini_client.generate_content.called, "LLM should not be invoked when rules handle all blocks"

        # Verify LLM_EXECUTION_TRACE shows invoked=False
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0
        assert "invoked=False" in llm_trace_logs[0].message, "invoked should be False when rules handle all"
        assert "attempted=False" in llm_trace_logs[0].message, "attempted should be False when LLM is skipped"
        assert "successful=False" in llm_trace_logs[0].message, "successful should be False when LLM is skipped"
        assert "rule_classified=1" in llm_trace_logs[0].message, "Should show 1 block classified by rules"


class TestProviderModelTracking:
    def test_provider_and_model_logged(self, classifier, mock_gemini_client, caplog):
        """Provider and model should be logged in LLM_EXECUTION_TRACE."""
        caplog.set_level(logging.INFO)

        blocks = [_block(1, "Test paragraph", "BODY")]

        # Disable cache and rules
        classifier.cache = None
        classifier.rule_learner = None

        # Call classify
        results = classifier.classify(blocks, "test_doc")

        # Verify provider and model in trace log
        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert len(llm_trace_logs) > 0

        trace_log = llm_trace_logs[0].message
        assert "provider=google-gemini" in trace_log, "Should log provider"
        assert "model=gemini-2.5-pro" in trace_log, "Should log model name"


class TestSkipLlmExclusion:
    def test_skip_llm_excluded_before_cache_and_llm(self, classifier, mock_gemini_client, caplog):
        """skip_llm blocks must bypass cache/rules/LLM eligibility and still return deterministic output."""
        caplog.set_level(logging.INFO)

        marker = _block(70, "<INSERT FIGURE 7.1 HERE>", "BODY")
        marker["skip_llm"] = True
        blocks = [
            marker,
            _block(71, "Regular paragraph text", "BODY"),
        ]

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.get_stats.return_value = {"hits": 0, "misses": 1}
        classifier.cache = mock_cache
        classifier.rule_learner = None

        results = classifier.classify(blocks, "test_doc")

        checked_ids = [call.kwargs["para_index"] for call in mock_cache.get.call_args_list]
        assert checked_ids == [71], "skip_llm block should not be checked in cache"

        assert mock_gemini_client.generate_content.called, "Non-skip block should still reach LLM"
        payload = mock_gemini_client.generate_content.call_args.args[0]
        assert "<INSERT FIGURE 7.1 HERE>" not in payload, "skip_llm marker must not enter LLM payload"

        result_by_id = {r["id"]: r for r in results}
        assert result_by_id[70]["tag"] == "PMI"
        assert result_by_id[70]["gated"] is True
        assert result_by_id[70]["gate_rule"] == "skip-llm"
        assert "skip-llm: excluding 1/2 blocks" in caplog.text

    def test_skip_llm_survives_rules_only_branch(self, classifier, mock_gemini_client, caplog):
        """skip_llm blocks should survive when remaining blocks are rule-classified and LLM is skipped."""
        caplog.set_level(logging.INFO)

        marker = _block(118, "<INSERT FIGURE 7.2>", "BODY")
        marker["skip_llm"] = True
        blocks = [marker, _block(119, "Rule-classified paragraph", "BODY")]

        mock_rule_learner = MagicMock()
        mock_rule_learner.rules = [{"condition": {}, "target": "TXT", "confidence": 0.9}]
        mock_rule_learner.apply_rules.return_value = "TXT"
        mock_extractor = MagicMock()
        mock_extractor.extract_features.return_value = {}
        mock_rule_learner.feature_extractor = mock_extractor
        mock_rule_learner._feature_matches.return_value = True

        classifier.rule_learner = mock_rule_learner
        classifier.cache = None

        results = classifier.classify(blocks, "test_doc")

        assert not mock_gemini_client.generate_content.called, "LLM should remain skipped in rules-only branch"
        result_by_id = {r["id"]: r for r in results}
        assert result_by_id[118]["tag"] == "PMI"
        assert result_by_id[118]["gate_rule"] == "skip-llm"
        assert result_by_id[119]["tag"] == "TXT"

        llm_trace_logs = [r for r in caplog.records if "LLM_EXECUTION_TRACE" in r.message]
        assert llm_trace_logs, "LLM_EXECUTION_TRACE should be emitted"
        assert "eligible=1" in llm_trace_logs[0].message, "skip_llm block must not count as LLM-eligible"

    def test_skip_llm_in_chunk_payload_path_raises(self, classifier, caplog):
        """Hard guard: skip_llm block reaching chunk payload builder should warn and raise."""
        caplog.set_level(logging.WARNING)

        marker = _block(999, "<INSERT FIGURE 7.1 HERE>", "BODY")
        marker["skip_llm"] = True

        with pytest.raises(AssertionError, match="skip_llm blocks reached LLM payload build path"):
            classifier._classify_chunk([marker], "test_doc", "Academic Document")

        assert "reached LLM payload build path" in caplog.text


class TestLlmGeneratedProvenance:
    """_classify_chunk sets llm_generated=True; skip_llm path does not."""

    def test_classify_chunk_sets_llm_generated_true(self, classifier, mock_gemini_client):
        """All results returned by _classify_chunk must carry llm_generated=True."""
        block = _block(1, "Regular paragraph text", "BODY")
        results = classifier._classify_chunk([block], "test_doc", "Academic Document")
        assert len(results) > 0
        for r in results:
            assert r.get("llm_generated") is True, (
                f"result id={r.get('id')} missing llm_generated=True"
            )

    def test_skip_llm_result_has_no_llm_generated(self, classifier):
        """Results built by _build_skip_llm_result must NOT carry llm_generated=True."""
        marker = _block(70, "<CN>", "BODY")
        marker["skip_llm"] = True
        marker["allowed_styles"] = ["PMI"]
        result = classifier._build_skip_llm_result(marker)
        assert result.get("llm_generated") is not True

    def test_skip_llm_blocks_excluded_from_llm_path_no_llm_generated(
        self, classifier, mock_gemini_client
    ):
        """In classify(), skip_llm blocks get gated=True / gate_rule=skip-llm,
        never llm_generated=True."""
        marker = _block(5, "<INSERT TABLE 2.1 HERE>", "BODY")
        marker["skip_llm"] = True
        normal = _block(6, "Body paragraph", "BODY")

        classifier.cache = None
        classifier.rule_learner = None

        results = classifier.classify([marker, normal], "test_doc")
        result_by_id = {r["id"]: r for r in results}

        # skip_llm result: gated path, no llm_generated
        skip_result = result_by_id[5]
        assert skip_result["tag"] == "PMI"
        assert skip_result.get("gated") is True
        assert skip_result.get("llm_generated") is not True

        # Normal result: LLM path, llm_generated=True
        normal_result = result_by_id[6]
        assert normal_result.get("llm_generated") is True
