"""Thin Gemini client wrapper using google.genai SDK."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - import guard
    genai = None
    types = None

logger = logging.getLogger(__name__)

ALLOWED_STYLES_PATH = Path(__file__).resolve().parents[1] / "config" / "allowed_styles.json"


def _load_allowed_styles() -> set[str]:
    try:
        with ALLOWED_STYLES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}
    except Exception:
        pass
    return {"TXT"}


ALLOWED_STYLES = _load_allowed_styles()


class GeminiClient:
    """Gemini LLM wrapper with transient retry and JSON label parsing."""

    def __init__(
        self,
        api_key: str | None = None,
        provider: str = "gemini",
        model_name: str = "gemini-2.5-pro",
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_output_tokens: int = 65536,
        system_instruction: Optional[str] = None,
        max_retries: int = 5,
        retry_delay: int = 2,
        timeout: int = 120,
    ):
        if genai is None or types is None:
            raise ImportError("google-genai is not installed.")

        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        if not resolved_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        if provider == "gemini":
            assert model_name == "gemini-2.5-pro", (
                f"Gemini provider requires model_name='gemini-2.5-pro', got '{model_name}'"
            )

        self.provider = provider
        self.model_name = model_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.client = genai.Client(api_key=resolved_key)
        self.generation_config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            system_instruction=system_instruction,
        )
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0
        self._token_usage_available = False
        self.total_latency_ms = 0
        self.request_count = 0
        self._last_usage: Dict[str, Any] = {}
        self._last_latency_ms = 0

    def _is_transient(self, err: Exception) -> bool:
        text = str(err)
        return (
            "429" in text
            or "ResourceExhausted" in text
            or "RESOURCE_EXHAUSTED" in text
            or "ServiceUnavailable" in text
            or "UNAVAILABLE" in text
            or "DeadlineExceeded" in text
            or "DEADLINE_EXCEEDED" in text
        )

    @staticmethod
    def parse_usage(resp: Any) -> tuple[int | None, int | None]:
        """Parse usage tokens from SDK response object or dict response shape."""
        input_tokens = None
        output_tokens = None

        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            prompt = getattr(usage, "prompt_token_count", None)
            candidates = getattr(usage, "candidates_token_count", None)
            if prompt is not None:
                try:
                    input_tokens = int(prompt)
                except Exception:
                    input_tokens = None
            if candidates is not None:
                try:
                    output_tokens = int(candidates)
                except Exception:
                    output_tokens = None

        if input_tokens is None or output_tokens is None:
            usage_dict = None
            try:
                if isinstance(resp, dict):
                    usage_dict = resp.get("usage_metadata")
                elif hasattr(resp, "__getitem__"):
                    usage_dict = resp["usage_metadata"]
            except Exception:
                usage_dict = None
            if isinstance(usage_dict, dict):
                prompt = usage_dict.get("prompt_token_count")
                candidates = usage_dict.get("candidates_token_count")
                if input_tokens is None and prompt is not None:
                    try:
                        input_tokens = int(prompt)
                    except Exception:
                        input_tokens = None
                if output_tokens is None and candidates is not None:
                    try:
                        output_tokens = int(candidates)
                    except Exception:
                        output_tokens = None

        return input_tokens, output_tokens

    def generate_content(
        self,
        prompt: str,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        retries = max_retries or self.max_retries
        _ = timeout or self.timeout
        last_error: Exception | None = None
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]

        for attempt in range(retries):
            try:
                start = time.perf_counter()
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=self.generation_config,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                self.total_latency_ms += latency_ms
                self._last_latency_ms = latency_ms
                self.request_count += 1
                input_tokens, output_tokens = self.parse_usage(response)
                total_tokens = (
                    input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None
                    else None
                )
                if input_tokens is not None:
                    self.total_input_tokens += input_tokens
                    self._token_usage_available = True
                if output_tokens is not None:
                    self.total_output_tokens += output_tokens
                    self._token_usage_available = True
                if total_tokens is not None:
                    self.total_tokens += total_tokens
                    self._token_usage_available = True
                self._last_usage = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "latency_ms": latency_ms,
                    "provider": self.provider,
                    "model": self.model_name,
                }
                return response
            except Exception as e:
                last_error = e
                if not self._is_transient(e) or attempt >= retries - 1:
                    raise
                base_wait = min(self.retry_delay * (2 ** attempt), 30)
                jitter = random.uniform(0.0, min(1.0, base_wait * 0.2))
                time.sleep(base_wait + jitter)

        raise last_error or RuntimeError("Gemini call failed")

    def _parse_json(self, text: str) -> list[dict]:
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        match = re.search(r"\[[\s\S]*\]", text or "")
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []

    def _enforce_allowed(self, labels: list[dict], allowed_styles: Iterable[str] | None = None) -> list[dict]:
        allowed = set(allowed_styles or ALLOWED_STYLES)
        fallback = "TXT" if "TXT" in allowed else (next(iter(allowed)) if allowed else "TXT")
        out = []
        for row in labels:
            if not isinstance(row, dict):
                continue
            tag = str(row.get("tag", "")).strip()
            row["tag"] = tag if tag in allowed else fallback
            out.append(row)
        return out

    def generate_labels(
        self,
        prompt: str,
        allowed_styles: Iterable[str] | None = None,
    ) -> list[dict]:
        response = self.generate_content(prompt)
        text = getattr(response, "text", "") or ""
        labels = self._parse_json(text)
        return self._enforce_allowed(labels, allowed_styles)

    def generate_with_metrics(self, prompt: str) -> dict:
        """Return response text plus normalized metrics for observability."""
        response = self.generate_content(prompt)
        usage = self.get_last_usage()
        return {
            "text": getattr(response, "text", "") or "",
            "latency_ms": usage.get("latency_ms"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "provider": usage.get("provider", self.provider),
            "model": usage.get("model", self.model_name),
            "response": response,
        }

    def get_token_usage(self) -> Dict[str, Any]:
        usage = {
            "total_input_tokens": self.total_input_tokens if self._token_usage_available else None,
            "total_output_tokens": self.total_output_tokens if self._token_usage_available else None,
            "total_tokens": self.total_tokens if self._token_usage_available else None,
            "total_latency_ms": self.total_latency_ms,
            "request_count": self.request_count,
        }
        if self.request_count > 0 and not self._token_usage_available:
            logger.warning("Gemini usage metadata unavailable across all requests.")
        return usage

    def get_last_usage(self) -> Dict[str, Any]:
        return self._last_usage.copy()
