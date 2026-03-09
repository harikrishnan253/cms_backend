"""Tests for FORCE_LLM mechanism - guarantees LLM invocation for evaluation runs."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import pytest
from processor.classifier import GeminiClassifier


def _block(pid, text="Test paragraph", zone="BODY", **extras):
    """Create a test block/paragraph."""
    return {
        "id": pid,
        "text": text,
        "metadata": {"context_zone": zone},
        **extras,
    }


# ===================================================================
# FORCE_LLM bypasses cache short-circuit
# ===================================================================

class TestForceLlmCacheBypass:
    """Test that FORCE_LLM bypasses cache short-circuit."""

    @patch.dict(os.environ, {"FORCE_LLM": "true"})
    def test_force_llm_bypasses_all_cached(self, caplog):
        """When all paragraphs are cached, FORCE_LLM forces LLM call anyway."""
        # Setup: Create classifier with mocked cache that returns everything as cached
        with patch("processor.classifier.get_cache") as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get.return_value = {
                "id": 1,
                "tag": "TXT",
                "confidence": 85,
            }
            mock_cache.get_stats.return_value = {
                "hits": 1,
                "misses": 0,
            }
            mock_get_cache.return_value = mock_cache

            # Mock the LLM client
            with patch("processor.classifier.GeminiClient") as MockClient:
                mock_client = Mock()
                mock_client.generate_content.return_value = Mock(
                    text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Body text"}]'
                )
                mock_client.get_token_usage.return_value = {
                    "total_input_tokens": 100,
                    "total_output_tokens": 50,
                    "total_tokens": 150,
                }
                mock_client.get_last_usage.return_value = {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                }
                MockClient.return_value = mock_client

                # Create classifier
                classifier = GeminiClassifier(
                    api_key="test_key",
                    model_name="gemini-2.5-flash-lite",
                )

                # Classify with all cached paragraphs
                paragraphs = [_block(1, "This is a test paragraph")]

                with caplog.at_level("INFO"):
                    results = classifier.classify(paragraphs, "test_doc")

                # Assert: LLM call was made despite cache
                assert "FORCE_LLM mode enabled" in caplog.text
                assert "forcing LLM call" in caplog.text
                mock_client.generate_content.assert_called()

    @patch.dict(os.environ, {"FORCE_LLM": "false"})
    def test_no_force_llm_respects_cache(self, caplog):
        """Without FORCE_LLM, all cached paragraphs skip LLM call."""
        # Setup: Create classifier with mocked cache
        with patch("processor.classifier.get_cache") as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get.return_value = {
                "id": 1,
                "tag": "TXT",
                "confidence": 85,
            }
            mock_get_cache.return_value = mock_cache

            # Mock the LLM client
            with patch("processor.classifier.GeminiClient") as MockClient:
                mock_client = Mock()
                MockClient.return_value = mock_client

                # Create classifier
                classifier = GeminiClassifier(
                    api_key="test_key",
                    model_name="gemini-2.5-flash-lite",
                )

                # Classify with all cached paragraphs
                paragraphs = [_block(1, "This is a test paragraph")]

                with caplog.at_level("INFO"):
                    results = classifier.classify(paragraphs, "test_doc")

                # Assert: LLM call was NOT made
                assert "All paragraphs found in cache, skipping API call" in caplog.text
                mock_client.generate_content.assert_not_called()


# ===================================================================
# FORCE_LLM bypasses rule-based short-circuit
# ===================================================================

class TestForceLlmRuleBypass:
    """Test that FORCE_LLM bypasses rule-based classification short-circuit."""

    @patch.dict(os.environ, {"FORCE_LLM": "true"})
    def test_force_llm_bypasses_all_rules(self, caplog):
        """When all paragraphs classified by rules, FORCE_LLM forces LLM call."""
        # Mock the LLM client
        with patch("processor.classifier.GeminiClient") as MockClient:
            mock_client = Mock()
            mock_client.generate_content.return_value = Mock(
                text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Body text"}]'
            )
            mock_client.get_token_usage.return_value = {
                "total_input_tokens": 100,
                "total_output_tokens": 50,
                "total_tokens": 150,
            }
            mock_client.get_last_usage.return_value = {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
            MockClient.return_value = mock_client

            # Mock cache to return nothing (no cache hits)
            with patch("processor.classifier.get_cache") as mock_get_cache:
                mock_cache = Mock()
                mock_cache.get.return_value = None
                mock_cache.get_stats.return_value = {
                    "hits": 0,
                    "misses": 1,
                }
                mock_get_cache.return_value = mock_cache

                # Create classifier with rule learner that classifies everything
                classifier = GeminiClassifier(
                    api_key="test_key",
                    model_name="gemini-2.5-flash-lite",
                )

                # Mock rule learner to classify all paragraphs
                mock_rule_learner = Mock()
                mock_rule_learner.rules = [(".*", "TXT", 0.9)]
                classifier.rule_learner = mock_rule_learner

                # Mock _apply_rules to return all as rule-classified
                def mock_apply_rules(paras, min_confidence=0.80):
                    results = [{"id": p["id"], "tag": "TXT", "confidence": 90} for p in paras]
                    return results, [], results  # All classified, none need LLM

                classifier._apply_rules = mock_apply_rules

                # Classify paragraphs
                paragraphs = [_block(1, "This is a test paragraph")]

                with caplog.at_level("INFO"):
                    results = classifier.classify(paragraphs, "test_doc")

                # Assert: LLM call was made despite rules
                assert "FORCE_LLM mode enabled" in caplog.text
                assert "forcing LLM call" in caplog.text
                mock_client.generate_content.assert_called()

    @patch.dict(os.environ, {"FORCE_LLM": "false"})
    def test_no_force_llm_respects_rules(self, caplog):
        """Without FORCE_LLM, all rule-classified paragraphs skip LLM."""
        # Mock the LLM client
        with patch("processor.classifier.GeminiClient") as MockClient:
            mock_client = Mock()
            MockClient.return_value = mock_client

            # Mock cache to return nothing (no cache hits)
            with patch("processor.classifier.get_cache") as mock_get_cache:
                mock_cache = Mock()
                mock_cache.get.return_value = None
                mock_get_cache.return_value = mock_cache

                # Create classifier
                classifier = GeminiClassifier(
                    api_key="test_key",
                    model_name="gemini-2.5-flash-lite",
                )

                # Mock rule learner to classify all paragraphs
                mock_rule_learner = Mock()
                mock_rule_learner.rules = [(".*", "TXT", 0.9)]
                classifier.rule_learner = mock_rule_learner

                # Mock _apply_rules to return all as rule-classified
                def mock_apply_rules(paras, min_confidence=0.80):
                    results = [{"id": p["id"], "tag": "TXT", "confidence": 90} for p in paras]
                    return results, [], results  # All classified, none need LLM

                classifier._apply_rules = mock_apply_rules

                # Classify paragraphs
                paragraphs = [_block(1, "This is a test paragraph")]

                with caplog.at_level("INFO"):
                    results = classifier.classify(paragraphs, "test_doc")

                # Assert: LLM call was NOT made
                assert "classified by rules" in caplog.text
                assert "skipping LLM" in caplog.text
                mock_client.generate_content.assert_not_called()


# ===================================================================
# FORCE_LLM guarantees LLM invocation
# ===================================================================

class TestForceLlmGuarantee:
    """Test that FORCE_LLM guarantees at least one LLM call when enabled."""

    @patch.dict(os.environ, {"FORCE_LLM": "true"})
    def test_force_llm_makes_provider_call(self):
        """When FORCE_LLM is set, at least one provider call occurs."""
        llm_called = False

        # Mock the LLM client to track calls
        with patch("processor.classifier.GeminiClient") as MockClient:
            mock_client = Mock()

            def mock_generate(*args, **kwargs):
                nonlocal llm_called
                llm_called = True
                return Mock(text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Body text"}]')

            mock_client.generate_content = mock_generate
            mock_client.get_token_usage.return_value = {
                "total_input_tokens": 100,
                "total_output_tokens": 50,
                "total_tokens": 150,
            }
            mock_client.get_last_usage.return_value = {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
            MockClient.return_value = mock_client

            # Create classifier with no cache
            classifier = GeminiClassifier(
                api_key="test_key",
                model_name="gemini-2.5-flash-lite",
            )

            # Disable rule learner
            classifier.rule_learner = None

            # Classify
            paragraphs = [_block(1, "Test paragraph")]
            results = classifier.classify(paragraphs, "test_doc")

            # Assert: LLM was called
            assert llm_called, "FORCE_LLM should guarantee LLM invocation"

    @patch.dict(os.environ, {"FORCE_LLM": "false"})
    def test_no_force_llm_may_skip_provider_call(self):
        """Without FORCE_LLM, provider call may be skipped if cached/rules."""
        llm_called = False

        # Mock the LLM client to track calls
        with patch("processor.classifier.GeminiClient") as MockClient:
            mock_client = Mock()

            def mock_generate(*args, **kwargs):
                nonlocal llm_called
                llm_called = True
                return Mock(text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Body text"}]')

            mock_client.generate_content = mock_generate
            MockClient.return_value = mock_client

            # Create classifier with cache
            with patch("processor.classifier.get_cache") as mock_get_cache:
                mock_cache = Mock()
                mock_cache.get.return_value = {
                    "id": 1,
                    "tag": "TXT",
                    "confidence": 85,
                }
                mock_get_cache.return_value = mock_cache

                classifier = GeminiClassifier(
                    api_key="test_key",
                    model_name="gemini-2.5-flash-lite",
                )

                # Classify
                paragraphs = [_block(1, "Test paragraph")]
                results = classifier.classify(paragraphs, "test_doc")

                # Assert: LLM was NOT called (cached)
                assert not llm_called, "Without FORCE_LLM, cached paragraphs should skip LLM"


# ===================================================================
# LLM_CALL telemetry logging tests
# ===================================================================

class TestLlmCallTelemetry:
    """Test LLM_CALL structured telemetry logging."""

    @patch.dict(os.environ, {"FORCE_LLM": "true"})
    def test_llm_call_telemetry_emitted(self, caplog):
        """LLM_CALL telemetry is emitted with all required fields."""
        # Mock the LLM client
        with patch("processor.classifier.GeminiClient") as MockClient:
            mock_client = Mock()
            mock_client.generate_content.return_value = Mock(
                text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Body text"}]'
            )
            mock_client.get_token_usage.return_value = {
                "total_input_tokens": 100,
                "total_output_tokens": 50,
                "total_tokens": 150,
                "api_calls": 1,
            }
            mock_client.get_last_usage.return_value = {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
            MockClient.return_value = mock_client

            # Create classifier
            classifier = GeminiClassifier(
                api_key="test_key",
                model_name="gemini-2.5-flash-lite",
            )

            # Disable rule learner
            classifier.rule_learner = None

            # Classify
            paragraphs = [_block(1, "Test paragraph")]

            with caplog.at_level("INFO"):
                results = classifier.classify(paragraphs, "test_doc")

            # Assert: LLM_CALL telemetry was logged
            assert "LLM_CALL" in caplog.text
            assert "provider=gemini" in caplog.text
            assert "model=gemini-2.5-flash-lite" in caplog.text
            assert "request_count=" in caplog.text
            assert "blocks_sent=" in caplog.text
            assert "tokens_in=" in caplog.text
            assert "tokens_out=" in caplog.text
            assert "cache_hit_rate=" in caplog.text

    @patch.dict(os.environ, {"FORCE_LLM": "true"})
    def test_llm_call_telemetry_null_fields(self, caplog):
        """LLM_CALL telemetry uses 'null' for missing fields."""
        # Mock the LLM client with no token usage returned
        with patch("processor.classifier.GeminiClient") as MockClient:
            mock_client = Mock()
            mock_client.generate_content.return_value = Mock(
                text='[{"id": 1, "tag": "TXT", "confidence": 85, "reasoning": "Body text"}]'
            )
            # Return minimal usage (no api_calls field)
            mock_client.get_token_usage.return_value = {
                "total_input_tokens": None,
                "total_output_tokens": None,
            }
            mock_client.get_last_usage.return_value = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
            MockClient.return_value = mock_client

            # Mock cache with stats
            with patch("processor.classifier.get_cache") as mock_get_cache:
                mock_cache = Mock()
                mock_cache.get.return_value = {
                    "id": 1,
                    "tag": "TXT",
                    "confidence": 85,
                }
                mock_cache.get_stats.return_value = {
                    "hits": 1,
                    "misses": 0,
                }
                mock_get_cache.return_value = mock_cache

                # Create classifier without cache
                classifier = GeminiClassifier(
                    api_key="test_key",
                    model_name="gemini-2.5-flash-lite",
                )

                # Disable rule learner
                classifier.rule_learner = None

                # Classify
                paragraphs = [_block(1, "Test paragraph")]

                with caplog.at_level("INFO"):
                    results = classifier.classify(paragraphs, "test_doc")

                # Assert: Null fields are present
                assert "LLM_CALL" in caplog.text
                # Check for null values (should appear as "null" in log)
                log_line = [line for line in caplog.text.split("\n") if "LLM_CALL" in line][0]
                assert "tokens_in=null" in log_line or "tokens_in=0" in log_line
                assert "cache_hit_rate=" in log_line  # Should have cache_hit_rate field


# ===================================================================
# Environment variable parsing tests
# ===================================================================

class TestForceLlmEnvironmentVariable:
    """Test FORCE_LLM environment variable parsing."""

    @patch.dict(os.environ, {"FORCE_LLM": "true"})
    def test_force_llm_true_lowercase(self):
        """FORCE_LLM=true (lowercase) enables forcing."""
        force_llm = os.getenv("FORCE_LLM", "false").lower() == "true"
        assert force_llm is True

    @patch.dict(os.environ, {"FORCE_LLM": "TRUE"})
    def test_force_llm_true_uppercase(self):
        """FORCE_LLM=TRUE (uppercase) enables forcing."""
        force_llm = os.getenv("FORCE_LLM", "false").lower() == "true"
        assert force_llm is True

    @patch.dict(os.environ, {"FORCE_LLM": "True"})
    def test_force_llm_true_mixed_case(self):
        """FORCE_LLM=True (mixed case) enables forcing."""
        force_llm = os.getenv("FORCE_LLM", "false").lower() == "true"
        assert force_llm is True

    @patch.dict(os.environ, {"FORCE_LLM": "false"})
    def test_force_llm_false(self):
        """FORCE_LLM=false disables forcing."""
        force_llm = os.getenv("FORCE_LLM", "false").lower() == "true"
        assert force_llm is False

    @patch.dict(os.environ, {}, clear=True)
    def test_force_llm_not_set(self):
        """FORCE_LLM not set defaults to false."""
        force_llm = os.getenv("FORCE_LLM", "false").lower() == "true"
        assert force_llm is False

    @patch.dict(os.environ, {"FORCE_LLM": "1"})
    def test_force_llm_invalid_value(self):
        """FORCE_LLM=1 (invalid) defaults to false."""
        force_llm = os.getenv("FORCE_LLM", "false").lower() == "true"
        assert force_llm is False
