import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services.grounded_retriever import GroundedRetriever


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _workspace_tmp_file(name: str) -> Path:
    p = ROOT / "backend" / "data" / name
    if p.exists():
        p.unlink()
    return p


def test_teacher_forced_figure_rule():
    gt = _workspace_tmp_file(f"_gt_teacher_{os.getpid()}.jsonl")
    rows = [
        {"doc_id": "A_tag", "text": "Figure 1.1 Alpha", "canonical_gold_tag": "FIG-LEG", "alignment_score": 1.0, "zone": "FLOATS"},
        {"doc_id": "B_tag", "text": "Figure 2.3 Beta", "canonical_gold_tag": "FIG-LEG", "alignment_score": 1.0, "zone": "FLOATS"},
        {"doc_id": "C_tag", "text": "Figure 4.5 Gamma", "canonical_gold_tag": "FIG-LEG", "alignment_score": 1.0, "zone": "FLOATS"},
        {"doc_id": "D_tag", "text": "Figure 8.1 Delta", "canonical_gold_tag": "FIG-LEG", "alignment_score": 1.0, "zone": "FLOATS"},
        {"doc_id": "E_tag", "text": "Figure 9.1 Epsilon", "canonical_gold_tag": "FIG-LEG", "alignment_score": 1.0, "zone": "FLOATS"},
    ]
    try:
        _write_jsonl(gt, rows)
        retriever = GroundedRetriever(gt)
        tag = retriever.suggest_teacher_forced_tag(
            text="Figure 74.1 Stages of replication.",
            metadata={"context_zone": "FLOATS"},
            allowed_styles={"FIG-LEG", "TXT"},
        )
        assert tag == "FIG-LEG"
    finally:
        if gt.exists():
            gt.unlink()


def test_retrieve_examples_prefers_zone_and_prefix():
    gt = _workspace_tmp_file(f"_gt_retriever_{os.getpid()}.jsonl")
    rows = [
        {"doc_id": "A_tag", "text": "Figure 3.1 Something", "canonical_gold_tag": "FIG-LEG", "alignment_score": 1.0, "zone": "FLOATS"},
        {"doc_id": "A_tag", "text": "Table 2.1 Something", "canonical_gold_tag": "T1", "alignment_score": 1.0, "zone": "FLOATS"},
        {"doc_id": "A_tag", "text": "References", "canonical_gold_tag": "REFH1", "alignment_score": 1.0, "zone": "REFERENCES"},
    ]
    try:
        _write_jsonl(gt, rows)
        retriever = GroundedRetriever(gt)
        examples = retriever.retrieve_examples(
            text="Figure 10.2 Test legend",
            k=1,
            zone="FLOATS",
            metadata={"context_zone": "FLOATS"},
        )
        assert examples
        assert examples[0]["canonical_gold_tag"] == "FIG-LEG"
    finally:
        if gt.exists():
            gt.unlink()
