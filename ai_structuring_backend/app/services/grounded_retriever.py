"""
Grounded Retriever - Retrieves similar examples from ground truth dataset.

Uses TF-IDF for fast similarity search without heavy dependencies.
Provides few-shot examples to ground the LLM in actual manual-tagged data.
"""

from __future__ import annotations

import json
import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Any
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

# Path to ground truth dataset
ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH_PATH = ROOT / "backend" / "data" / "ground_truth.jsonl"

# ---------------------------------------------------------------------------
# Runtime toggle — controlled entirely by environment variables.
#
#   ENABLE_GROUNDED_RETRIEVER   default: false
#       Master switch.  When false the retriever is never loaded and
#       ground_truth.jsonl is never opened at runtime.
#
#   GROUNDED_RETRIEVER_MODE     default: prompt_examples
#       What the retriever is used for (only relevant when enabled).
#       Accepted values:
#         off                 — load nothing (same effect as disabling master toggle)
#         prompt_examples     — inject few-shot examples into the LLM prompt
#         invalid_tag_fallback — apply similarity-based tag override for unknown tags
# ---------------------------------------------------------------------------
_ENABLE_RETRIEVER: bool = (
    os.getenv("ENABLE_GROUNDED_RETRIEVER", "false").lower() in ("1", "true", "yes")
)
_RETRIEVER_MODE: str = os.getenv("GROUNDED_RETRIEVER_MODE", "prompt_examples").lower()


def is_prompt_examples_enabled() -> bool:
    """Return True if the retriever should inject few-shot examples into prompts."""
    return _ENABLE_RETRIEVER and _RETRIEVER_MODE == "prompt_examples"


def is_invalid_tag_fallback_enabled() -> bool:
    """Return True if the retriever should be used as an invalid-tag fallback."""
    return _ENABLE_RETRIEVER and _RETRIEVER_MODE == "invalid_tag_fallback"


# Text normalization
WS_RE = re.compile(r"\s+")


class GroundedRetriever:
    """
    Retrieves similar examples from ground truth dataset for few-shot prompting.

    Uses TF-IDF similarity for fast retrieval without heavy dependencies.
    Caches loaded data for performance.
    """

    def __init__(self, ground_truth_path: Path | None = None):
        """Initialize retriever with ground truth dataset."""
        self.ground_truth_path = ground_truth_path or GROUND_TRUTH_PATH

        # Load dataset
        self.examples: list[dict[str, Any]] = []
        self.examples_by_doc: dict[str, list[dict]] = defaultdict(list)
        self.vocab: set[str] = set()
        self.idf_scores: dict[str, float] = {}
        self.example_vectors: list[dict[str, float]] = []

        self._load_dataset()
        self._build_index()

        logger.info(f"Loaded {len(self.examples)} examples from ground truth dataset")

    def _load_dataset(self):
        """Load ground truth dataset from JSONL file."""
        if not self.ground_truth_path.exists():
            logger.warning(f"Ground truth dataset not found: {self.ground_truth_path}")
            return

        with open(self.ground_truth_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    example = json.loads(line)

                    # Filter out UNMAPPED examples (alignment failures)
                    if example.get("canonical_gold_tag") == "UNMAPPED":
                        continue

                    # Only include high-quality alignments
                    if example.get("alignment_score", 0) < 0.75:
                        continue

                    self.examples.append(example)

                    # Index by document for same-book retrieval preference
                    doc_id = example.get("doc_id", "")
                    if doc_id:
                        self.examples_by_doc[doc_id].append(example)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse line: {e}")
                    continue

        logger.info(f"Loaded {len(self.examples)} high-quality examples from {len(self.examples_by_doc)} documents")

    def _build_index(self):
        """Build TF-IDF index for similarity search."""
        if not self.examples:
            return

        # Build vocabulary and document frequency
        doc_freq: Counter[str] = Counter()

        for example in self.examples:
            text = self._normalize_text(example.get("text", ""))
            tokens = self._tokenize(text)
            unique_tokens = set(tokens)

            for token in unique_tokens:
                doc_freq[token] += 1

            self.vocab.update(tokens)

        # Calculate IDF scores
        num_docs = len(self.examples)
        for token, freq in doc_freq.items():
            # IDF = log(total_docs / doc_freq)
            self.idf_scores[token] = (num_docs / freq) if freq > 0 else 0.0

        # Build TF-IDF vectors for each example
        for example in self.examples:
            text = self._normalize_text(example.get("text", ""))
            tokens = self._tokenize(text)

            # Calculate term frequency
            tf: Counter[str] = Counter(tokens)

            # Build TF-IDF vector
            vector: dict[str, float] = {}
            for token, count in tf.items():
                tf_score = count / len(tokens) if tokens else 0.0
                idf_score = self.idf_scores.get(token, 0.0)
                vector[token] = tf_score * idf_score

            self.example_vectors.append(vector)

        logger.debug(f"Built TF-IDF index with {len(self.vocab)} tokens")

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        # Remove common markers and normalize whitespace
        text = re.sub(r"<[^>]+>", " ", text)  # Remove inline tags
        text = WS_RE.sub(" ", text).strip().lower()
        return text

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization."""
        # Split on word boundaries, keep alphanumeric; discard pure-digit tokens
        # (section/figure numbers like "3", "10", "2" carry no semantic meaning
        # and cause false similarity matches between "Figure 10.2" and "Table 2.1").
        tokens = re.findall(r"\b\w+\b", text.lower())
        return [t for t in tokens if not t.isdigit()]

    def _cosine_similarity(self, vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """Calculate cosine similarity between two TF-IDF vectors."""
        if not vec1 or not vec2:
            return 0.0

        # Dot product
        dot_product = sum(vec1.get(token, 0.0) * vec2.get(token, 0.0) for token in vec1.keys() & vec2.keys())

        # Magnitudes
        mag1 = sum(v * v for v in vec1.values()) ** 0.5
        mag2 = sum(v * v for v in vec2.values()) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def _build_query_vector(self, text: str) -> dict[str, float]:
        """Build TF-IDF vector for query text."""
        normalized = self._normalize_text(text)
        tokens = self._tokenize(normalized)

        if not tokens:
            return {}

        # Calculate term frequency
        tf: Counter[str] = Counter(tokens)

        # Build TF-IDF vector
        vector: dict[str, float] = {}
        for token, count in tf.items():
            if token in self.idf_scores:
                tf_score = count / len(tokens)
                idf_score = self.idf_scores[token]
                vector[token] = tf_score * idf_score

        return vector

    def retrieve_examples(
        self,
        text: str,
        k: int = 8,
        doc_id: str | None = None,
        zone: str | None = None,
        canonical_tag: str | None = None,
        metadata: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve top-k most similar examples from ground truth.

        Args:
            text: Target text to find similar examples for
            k: Number of examples to retrieve
            doc_id: Optional document ID for same-book preference
            zone: Optional zone filter (e.g., "BODY", "TABLE")
            canonical_tag: Optional tag filter to retrieve examples of specific tag

        Returns:
            List of similar examples with scores
        """
        # Allow callers to pass metadata dict instead of zone directly
        if zone is None and metadata:
            zone = metadata.get("context_zone")

        if not self.examples:
            logger.warning("No ground truth examples loaded")
            return []

        # Build query vector
        query_vec = self._build_query_vector(text)

        if not query_vec:
            # Fallback to random diverse examples
            return self._get_diverse_examples(k)

        # Calculate similarities
        similarities: list[tuple[float, int]] = []

        for i, example in enumerate(self.examples):
            # Apply filters
            if zone and example.get("zone") != zone:
                continue

            if canonical_tag and example.get("canonical_gold_tag") != canonical_tag:
                continue

            # Calculate similarity
            example_vec = self.example_vectors[i]
            score = self._cosine_similarity(query_vec, example_vec)

            # Boost score for same document
            if doc_id and example.get("doc_id", "").startswith(doc_id.split("_")[0]):
                score *= 1.2  # 20% boost for same book

            similarities.append((score, i))

        # Sort by similarity (descending)
        similarities.sort(reverse=True)

        # Get top-k
        top_k = similarities[:k]

        # Build result list
        results = []
        for score, idx in top_k:
            example = self.examples[idx].copy()
            example["similarity_score"] = round(score, 4)
            results.append(example)

        return results

    def _get_diverse_examples(self, k: int) -> list[dict[str, Any]]:
        """Get diverse examples when no good matches found."""
        if not self.examples:
            return []

        # Sample evenly across different tags
        examples_by_tag: dict[str, list[dict]] = defaultdict(list)
        for example in self.examples:
            tag = example.get("canonical_gold_tag", "")
            if tag and tag != "UNMAPPED":
                examples_by_tag[tag].append(example)

        # Get one example per tag up to k
        diverse = []
        tags = sorted(examples_by_tag.keys())

        for tag in tags:
            if len(diverse) >= k:
                break
            if examples_by_tag[tag]:
                diverse.append(examples_by_tag[tag][0].copy())

        # Fill remaining with high-alignment examples
        if len(diverse) < k:
            sorted_examples = sorted(
                self.examples,
                key=lambda x: x.get("alignment_score", 0),
                reverse=True
            )
            for ex in sorted_examples:
                if len(diverse) >= k:
                    break
                if ex not in diverse:
                    diverse.append(ex.copy())

        return diverse[:k]

    def suggest_teacher_forced_tag(
        self,
        text: str,
        metadata: dict,
        allowed_styles: set[str],
    ) -> str | None:
        """Return a high-confidence corpus-grounded tag suggestion, or None.

        Retrieves the top-k most similar corpus examples and performs a
        majority vote among those whose tag is present in *allowed_styles*.
        Returns the winning tag only when:
          - at least 2 of the top-k examples agree on the same tag, OR
          - the single top-ranked example exceeds a 0.5 similarity threshold.

        This is intentionally conservative — it is only for cases where the
        corpus clearly and repeatedly maps the same pattern to a single tag.

        Args:
            text:           Paragraph text to classify.
            metadata:       Block metadata dict (used for context_zone).
            allowed_styles: Set of tags valid for this paragraph's zone.

        Returns:
            Canonical tag string if a high-confidence match is found,
            otherwise None.
        """
        if not self.examples or not allowed_styles:
            return None

        zone = (metadata or {}).get("context_zone")
        examples = self.retrieve_examples(text, k=5, zone=zone)

        if not examples:
            return None

        # Majority vote among allowed tags
        tag_votes: Counter[str] = Counter()
        for ex in examples:
            tag = ex.get("canonical_gold_tag", "")
            if tag and tag in allowed_styles:
                tag_votes[tag] += 1

        if tag_votes:
            top_tag, top_count = tag_votes.most_common(1)[0]
            if top_count >= 2:
                return top_tag

        # Single-example fallback: only when similarity is high enough
        top_tag = examples[0].get("canonical_gold_tag", "")
        top_sim = examples[0].get("similarity_score", 0.0)
        if top_tag in allowed_styles and top_sim >= 0.5:
            return top_tag

        return None

    def format_examples_for_prompt(self, examples: list[dict[str, Any]]) -> str:
        """
        Format retrieved examples for inclusion in LLM prompt.

        Args:
            examples: List of retrieved examples

        Returns:
            Formatted string for prompt injection
        """
        if not examples:
            return ""

        lines = ["# GROUND TRUTH EXAMPLES (from manual-tagged training data)"]
        lines.append("# Use these as reference patterns for your classifications:\n")

        for i, ex in enumerate(examples, 1):
            text = ex.get("text", "")[:150]  # Truncate long texts
            tag = ex.get("canonical_gold_tag", "")
            doc_id = ex.get("doc_id", "")
            zone = ex.get("zone", "")

            # Format: [book] TEXT => TAG (zone)
            book_prefix = doc_id.split("_")[0][:15] if doc_id else "?"
            zone_suffix = f" [{zone}]" if zone else ""

            lines.append(f"{i}. [{book_prefix}] {text} => {tag}{zone_suffix}")

        lines.append("")  # Blank line separator
        return "\n".join(lines)

    def get_tag_distribution(self) -> dict[str, int]:
        """Get distribution of tags in ground truth dataset."""
        tag_counts: Counter[str] = Counter()

        for example in self.examples:
            tag = example.get("canonical_gold_tag", "")
            if tag and tag != "UNMAPPED":
                tag_counts[tag] += 1

        return dict(tag_counts)

    def get_stats(self) -> dict[str, Any]:
        """Get retriever statistics."""
        return {
            "total_examples": len(self.examples),
            "num_documents": len(self.examples_by_doc),
            "vocab_size": len(self.vocab),
            "avg_alignment_score": sum(ex.get("alignment_score", 0) for ex in self.examples) / len(self.examples) if self.examples else 0,
            "top_tags": dict(Counter(ex.get("canonical_gold_tag") for ex in self.examples).most_common(20))
        }


# Singleton instance
_retriever_instance: GroundedRetriever | None = None


def get_retriever() -> GroundedRetriever | None:
    """
    Return the singleton GroundedRetriever, or None when retrieval is disabled.

    Disabled when ENABLE_GROUNDED_RETRIEVER is not set/false, or when
    GROUNDED_RETRIEVER_MODE is 'off'.  In the disabled case ground_truth.jsonl
    is never opened and there is no runtime dependency on the corpus file.
    """
    if not _ENABLE_RETRIEVER or _RETRIEVER_MODE == "off":
        return None

    global _retriever_instance

    if _retriever_instance is None:
        _retriever_instance = GroundedRetriever()

    return _retriever_instance


if __name__ == "__main__":
    # Test retrieval — set ENABLE_GROUNDED_RETRIEVER=true to activate.
    retriever = get_retriever()
    if retriever is None:
        print("Retriever disabled. Set ENABLE_GROUNDED_RETRIEVER=true to run this test.")
        raise SystemExit(0)
    print(f"Loaded {len(retriever.examples)} examples")
    print("\nRetriever stats:")
    stats = retriever.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Test retrieval
    print("\nTest retrieval for 'Introduction':")
    examples = retriever.retrieve_examples("Introduction", k=5)
    for ex in examples:
        print(f"  {ex['text'][:60]} => {ex['canonical_gold_tag']} (score: {ex.get('similarity_score', 0):.3f})")
