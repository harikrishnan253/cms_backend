"""
STAGE 3: Confidence Filtering
- High Confidence (≥85%) → Auto-apply tags
- Low Confidence (<85%) → Flag for review (store alternatives)

Separates results into auto-apply and review queues.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Single paragraph classification result."""
    id: int
    tag: str
    confidence: int
    reasoning: Optional[str] = None
    original_text: str = ""
    alternatives: list[str] = field(default_factory=list)
    
    @property
    def needs_review(self) -> bool:
        """Check if this result needs human review."""
        return self.confidence < 85
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        d = {
            "id": self.id,
            "tag": self.tag,
            "confidence": self.confidence,
            "original_text": self.original_text,
            "needs_review": self.needs_review,
        }
        if self.reasoning:
            d["reasoning"] = self.reasoning
        if self.alternatives:
            d["alternatives"] = self.alternatives
        return d


@dataclass
class FilteredResults:
    """Container for filtered classification results."""
    auto_apply: list[ClassificationResult]
    needs_review: list[ClassificationResult]
    
    @property
    def total_count(self) -> int:
        return len(self.auto_apply) + len(self.needs_review)
    
    @property
    def auto_apply_count(self) -> int:
        return len(self.auto_apply)
    
    @property
    def review_count(self) -> int:
        return len(self.needs_review)
    
    @property
    def auto_apply_percentage(self) -> float:
        if self.total_count == 0:
            return 0.0
        return (self.auto_apply_count / self.total_count) * 100
    
    def get_summary(self) -> dict:
        """Get summary statistics."""
        return {
            "total_paragraphs": self.total_count,
            "auto_applied": self.auto_apply_count,
            "needs_review": self.review_count,
            "auto_apply_percentage": round(self.auto_apply_percentage, 1),
            "average_confidence": self._avg_confidence(),
        }
    
    def _avg_confidence(self) -> float:
        all_results = self.auto_apply + self.needs_review
        if not all_results:
            return 0.0
        return sum(r.confidence for r in all_results) / len(all_results)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "summary": self.get_summary(),
            "auto_apply": [r.to_dict() for r in self.auto_apply],
            "needs_review": [r.to_dict() for r in self.needs_review],
        }


class ConfidenceFilter:
    """
    Filter classification results by confidence threshold.
    """
    
    def __init__(self, threshold: int = 85):
        """
        Initialize the filter.
        
        Args:
            threshold: Confidence threshold (0-100). Below this = needs review.
        """
        self.threshold = threshold
    
    def filter(
        self,
        classifications: list[dict],
        paragraphs: list[dict]
    ) -> FilteredResults:
        """
        Filter classifications into auto-apply and review queues.
        
        Args:
            classifications: List of classification results from Gemini
            paragraphs: Original paragraphs (for context)
            
        Returns:
            FilteredResults with separated queues
        """
        # Create paragraph lookup
        para_lookup = {p["id"]: p for p in paragraphs}
        
        auto_apply = []
        needs_review = []
        
        for clf in classifications:
            para_id = clf["id"]
            original_text = para_lookup.get(para_id, {}).get("text", "")
            
            result = ClassificationResult(
                id=para_id,
                tag=clf["tag"],
                confidence=clf.get("confidence", 85),
                reasoning=clf.get("reasoning"),
                original_text=original_text[:100] + "..." if len(original_text) > 100 else original_text,
                alternatives=self._suggest_alternatives(clf)
            )
            
            if result.needs_review:
                needs_review.append(result)
            else:
                auto_apply.append(result)
        
        logger.info(
            f"Filtered {len(classifications)} results: "
            f"{len(auto_apply)} auto-apply, {len(needs_review)} needs review"
        )
        
        return FilteredResults(
            auto_apply=sorted(auto_apply, key=lambda x: x.id),
            needs_review=sorted(needs_review, key=lambda x: x.confidence)
        )
    
    def _suggest_alternatives(self, clf: dict) -> list[str]:
        """
        Suggest alternative tags based on the classification.
        
        Args:
            clf: Classification result
            
        Returns:
            List of alternative tag suggestions
        """
        tag = clf["tag"]
        confidence = clf.get("confidence", 85)
        
        # Only suggest alternatives for low confidence
        if confidence >= self.threshold:
            return []
        
        # Common alternatives based on tag type
        alternatives_map = {
            # Headings - could be different levels
            "H1": ["H2", "CT", "SP-H1"],
            "H2": ["H1", "H3", "REFH2"],
            "H3": ["H2", "H4"],
            "H4": ["H3", "H5"],
            
            # Text - could be flush or regular
            "TXT": ["TXT-FLUSH", "BX1-TXT-FIRST", "CS-TXT"],
            "TXT-FLUSH": ["TXT", "NBX1-TXT-FLUSH"],
            
            # Lists - position confusion
            "BL-FIRST": ["BL-MID", "NBX1-BL-FIRST"],
            "BL-MID": ["BL-FIRST", "BL-LAST"],
            "BL-LAST": ["BL-MID", "BL-FIRST"],
            "NL-FIRST": ["NL-MID", "EOC-NL-FIRST"],
            "NL-MID": ["NL-FIRST", "NL-LAST"],
            "NL-LAST": ["NL-MID"],
            
            # Tables
            "T2": ["T3", "TBL-MID"],
            "T3": ["T2", "TBL-MID"],
            "TBL-MID": ["T2", "T3"],
            
            # References
            "REF-N": ["NL-FIRST", "NL-MID"],
        }
        
        return alternatives_map.get(tag, [])
    
    def get_review_report(self, filtered: FilteredResults) -> str:
        """
        Generate a human-readable review report.
        
        Args:
            filtered: FilteredResults object
            
        Returns:
            Formatted report string
        """
        lines = [
            "=" * 60,
            "CLASSIFICATION REVIEW REPORT",
            "=" * 60,
            "",
            f"Total Paragraphs: {filtered.total_count}",
            f"Auto-Applied: {filtered.auto_apply_count} ({filtered.auto_apply_percentage:.1f}%)",
            f"Needs Review: {filtered.review_count}",
            "",
        ]
        
        if filtered.needs_review:
            lines.extend([
                "-" * 60,
                "ITEMS REQUIRING REVIEW",
                "-" * 60,
                "",
            ])
            
            for item in filtered.needs_review:
                lines.extend([
                    f"Paragraph {item.id}:",
                    f"  Text: \"{item.original_text}\"",
                    f"  Suggested Tag: {item.tag} (Confidence: {item.confidence}%)",
                ])
                if item.reasoning:
                    lines.append(f"  Reasoning: {item.reasoning}")
                if item.alternatives:
                    lines.append(f"  Alternatives: {', '.join(item.alternatives)}")
                lines.append("")
        
        return "\n".join(lines)


def filter_classifications(
    classifications: list[dict],
    paragraphs: list[dict],
    threshold: int = 85
) -> FilteredResults:
    """
    Convenience function to filter classifications.
    
    Args:
        classifications: Classification results
        paragraphs: Original paragraphs
        threshold: Confidence threshold
        
    Returns:
        FilteredResults
    """
    filter = ConfidenceFilter(threshold)
    return filter.filter(classifications, paragraphs)


if __name__ == "__main__":
    # Test with sample data
    sample_classifications = [
        {"id": 1, "tag": "CN", "confidence": 99},
        {"id": 2, "tag": "CT", "confidence": 98},
        {"id": 3, "tag": "H1", "confidence": 75, "reasoning": "Could be H2"},
        {"id": 4, "tag": "TXT-FLUSH", "confidence": 92},
        {"id": 5, "tag": "BL-FIRST", "confidence": 60, "reasoning": "Might be NL-FIRST"},
    ]
    
    sample_paragraphs = [
        {"id": 1, "text": "CHAPTER 1"},
        {"id": 2, "text": "Introduction to the Topic"},
        {"id": 3, "text": "Overview"},
        {"id": 4, "text": "This chapter covers important concepts..."},
        {"id": 5, "text": "1. First item in the list"},
    ]
    
    results = filter_classifications(sample_classifications, sample_paragraphs)
    
    print(results.get_summary())
    print("\n" + ConfidenceFilter().get_review_report(results))
