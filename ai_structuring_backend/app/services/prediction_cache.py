"""
Prediction Cache - Caches LLM predictions to avoid repeated API calls.

Reduces API costs and 429 rate limit errors by caching predictions
based on normalized text hash and document context.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache directory
ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "backend" / "data" / "_prediction_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Text normalization for cache keys
WS_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")


class PredictionCache:
    """
    Simple file-based cache for LLM predictions.

    Cache key: hash(doc_id + para_index + normalized_text + zone)
    Cache value: {tag, confidence, timestamp}
    """

    def __init__(self, cache_dir: Path | None = None, ttl_days: int = 30):
        """
        Initialize cache.

        Args:
            cache_dir: Directory for cache files
            ttl_days: Time-to-live for cache entries in days
        """
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days

        # In-memory cache for current session
        self.memory_cache: dict[str, dict[str, Any]] = {}

        # Stats
        self.hits = 0
        self.misses = 0

        logger.info(f"Initialized prediction cache at {self.cache_dir} (TTL: {ttl_days} days)")

    def _normalize_text(self, text: str) -> str:
        """Normalize text for cache key generation."""
        # Remove inline tags
        text = TAG_RE.sub(" ", text)
        # Normalize whitespace
        text = WS_RE.sub(" ", text).strip().lower()
        return text

    def _generate_key(
        self,
        doc_id: str,
        para_index: int,
        text: str,
        zone: str = "BODY"
    ) -> str:
        """Generate cache key from inputs."""
        normalized = self._normalize_text(text)

        # Create composite key
        key_data = f"{doc_id}:{para_index}:{normalized}:{zone}"

        # Hash for compact key
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]

        return key_hash

    def get(
        self,
        doc_id: str,
        para_index: int,
        text: str,
        zone: str = "BODY"
    ) -> dict[str, Any] | None:
        """
        Get cached prediction if available.

        Returns:
            Cached prediction dict or None if not found/expired
        """
        key = self._generate_key(doc_id, para_index, text, zone)

        # Check memory cache first
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if self._is_valid(entry):
                self.hits += 1
                logger.debug(f"Cache HIT (memory) for {doc_id}:{para_index}")
                return entry["prediction"]
            else:
                # Expired
                del self.memory_cache[key]

        # Check disk cache
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    entry = json.load(f)

                if self._is_valid(entry):
                    # Load into memory cache
                    self.memory_cache[key] = entry
                    self.hits += 1
                    logger.debug(f"Cache HIT (disk) for {doc_id}:{para_index}")
                    return entry["prediction"]
                else:
                    # Expired - delete
                    cache_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to load cache entry {key}: {e}")

        self.misses += 1
        return None

    def set(
        self,
        doc_id: str,
        para_index: int,
        text: str,
        prediction: dict[str, Any],
        zone: str = "BODY"
    ):
        """
        Cache a prediction.

        Args:
            doc_id: Document identifier
            para_index: Paragraph index
            text: Paragraph text
            prediction: Prediction dict with tag, confidence, etc.
            zone: Context zone
        """
        key = self._generate_key(doc_id, para_index, text, zone)

        entry = {
            "prediction": prediction,
            "timestamp": datetime.now().isoformat(),
            "doc_id": doc_id,
            "para_index": para_index,
            "zone": zone
        }

        # Save to memory cache
        self.memory_cache[key] = entry

        # Save to disk cache
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
            logger.debug(f"Cached prediction for {doc_id}:{para_index}")
        except Exception as e:
            logger.warning(f"Failed to write cache entry {key}: {e}")

    def _is_valid(self, entry: dict[str, Any]) -> bool:
        """Check if cache entry is still valid (not expired)."""
        timestamp_str = entry.get("timestamp")
        if not timestamp_str:
            return False

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            age = datetime.now() - timestamp
            return age < timedelta(days=self.ttl_days)
        except Exception:
            return False

    def clear(self):
        """Clear all cache entries."""
        # Clear memory
        self.memory_cache.clear()

        # Clear disk
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete cache file {cache_file}: {e}")

        logger.info("Cleared prediction cache")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0

        disk_entries = len(list(self.cache_dir.glob("*.json")))

        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_queries": total,
            "hit_rate": f"{hit_rate:.1f}%",
            "memory_entries": len(self.memory_cache),
            "disk_entries": disk_entries,
            "ttl_days": self.ttl_days
        }


# Singleton instance
_cache_instance: PredictionCache | None = None


def get_cache() -> PredictionCache:
    """Get or create singleton cache instance."""
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = PredictionCache()

    return _cache_instance


if __name__ == "__main__":
    # Test cache
    cache = get_cache()

    # Test set/get
    cache.set("test_doc", 1, "This is a test paragraph.", {"tag": "TXT", "confidence": 95})

    result = cache.get("test_doc", 1, "This is a test paragraph.")
    print(f"Cached result: {result}")

    # Test normalization (should hit cache despite whitespace differences)
    result2 = cache.get("test_doc", 1, "This  is  a   test    paragraph.")
    print(f"Normalized hit: {result2}")

    # Stats
    print(f"\nCache stats: {cache.get_stats()}")
