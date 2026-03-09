"""
Reviewer bundle export.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


def _decision_preview(text: str, limit: int = 160) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def create_review_bundle(
    job_id: str,
    input_docx_path: str,
    output_docx_path: str,
    decisions: list[dict],
    quality_metrics: dict,
) -> str:
    root = Path("outputs") / "review_bundles" / str(job_id)
    root.mkdir(parents=True, exist_ok=True)

    bundle_path = root / "bundle.zip"

    decisions_payload = []
    for d in decisions:
        decisions_payload.append(
            {
                "id": d.get("id"),
                "text_preview": _decision_preview(d.get("text", "")),
                "tag": d.get("tag"),
                "confidence": d.get("confidence"),
                "repaired": d.get("repaired", False),
                "repair_reason": d.get("repair_reason"),
            }
        )

    quality_payload = quality_metrics

    suspicious = sorted(
        decisions_payload,
        key=lambda x: (x.get("confidence", 1), 0 if x.get("tag") == "TXT" else 1),
    )[:50]

    diff_hint_lines = []
    for item in suspicious:
        diff_hint_lines.append(
            f"{item.get('id')}\t{item.get('tag')}\t{item.get('confidence')}\t{item.get('repair_reason')}\t{item.get('text_preview')}"
        )

    diff_hint_text = "\n".join(diff_hint_lines)

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(input_docx_path, "input_original.docx")
        zf.write(output_docx_path, "output_tagged.docx")
        zf.writestr("decisions.json", json.dumps(decisions_payload, indent=2))
        zf.writestr("quality_report.json", json.dumps(quality_payload, indent=2))
        zf.writestr("diff_hint.txt", diff_hint_text)

    return str(bundle_path)
