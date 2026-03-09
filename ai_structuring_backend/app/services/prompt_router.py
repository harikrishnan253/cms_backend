"""
Prompt routing for Option 2 retry ladder.
"""

from __future__ import annotations

from pathlib import Path
import re

from .allowed_styles import load_allowed_styles


ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"
BASE_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"


def _load_base_prompt() -> str:
    if not BASE_PROMPT_PATH.exists():
        return ""
    return BASE_PROMPT_PATH.read_text(encoding="utf-8")


def _allowed_list_str() -> str:
    styles = sorted(load_allowed_styles())
    return ", ".join(styles)


REFERENCE_REGEX = r"(^\\d+\\.|\\[\\d+\\]|\\(\\d{4}\\))"


def route_profile(blocks: list[dict], features: dict | None = None) -> str:
    """
    Route to a profile based on generic features.
    """
    total = max(1, len(blocks))
    table_count = 0
    box_count = 0
    ref_count = 0
    ref_token_hits = 0

    for b in blocks:
        meta = b.get("metadata", {})
        text = b.get("text", "")
        text_l = text.lower()

        if meta.get("is_table"):
            table_count += 1
        if meta.get("context_zone", "").startswith("BOX_") or meta.get("box_marker"):
            box_count += 1

        if text_l:
            if re.search(REFERENCE_REGEX, text_l):
                ref_token_hits += 1
            if "doi" in text_l or "et al" in text_l or "journal" in text_l:
                ref_count += 1
            if "references" in text_l or "bibliography" in text_l:
                ref_count += 1

        if features and features.get("expected_styles"):
            if any(str(s).startswith("BX") or str(s).startswith("NBX") for s in features["expected_styles"]):
                box_count += 2

        if "box" in text_l or "key points" in text_l or "clinical pearl" in text_l or "skill" in text_l or "case" in text_l:
            box_count += 1

    table_ratio = table_count / total
    box_ratio = box_count / total
    ref_ratio = (ref_count + ref_token_hits) / total

    if ref_ratio >= 0.06:
        return "reference_heavy"
    if table_ratio >= 0.10:
        return "table_heavy"
    if box_ratio >= 0.05:
        return "box_heavy"
    return "default"


def route_prompt(blocks: list[dict], features: dict | None = None) -> tuple[str, str]:
    """
    Route to a prompt variant based on block cues.
    """
    profile = route_profile(blocks, features)
    base_prompt = _load_base_prompt()
    allowed = _allowed_list_str()

    if profile == "reference_heavy":
        variant_hint = (
            "Focus on reference-heavy sections. Prefer REF-* and SR* styles for citations and lists. "
            "Do NOT output UL-* styles in reference-heavy content."
        )
    elif profile == "table_heavy":
        variant_hint = (
            "Focus on table-heavy content. Use T1/T2/T/T4/TBL/TFN/TSN appropriately. "
            "Do NOT use BL-* inside table zones."
        )
    elif profile == "box_heavy":
        variant_hint = (
            "Focus on boxed content. Use BX*/NBX* styles as applicable. "
            "Do NOT map box content to T/T2/T4 table styles."
        )
    else:
        variant_hint = "Use the default WK template guidance."

    prompt_text = (
        base_prompt
        + "\n\n"
        + f"PROFILE: {profile}\n"
        + variant_hint
        + "\n\n"
        + "IMPORTANT: Output strict JSON only. Valid tags are restricted to allowed_styles.json.\n"
        + "VALID TAGS: "
        + allowed
    )

    return profile, prompt_text
