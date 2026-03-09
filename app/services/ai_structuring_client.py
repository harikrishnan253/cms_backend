import os
import time
import zipfile
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List

import requests

logger = logging.getLogger("app.services.ai_structuring")

@dataclass
class AIStructuringSettings:
    base_url: str
    api_key: str = ""
    document_type: str = "Academic Document"
    use_markers: bool = False
    poll_interval_seconds: int = 2
    max_wait_seconds: int = 900
    request_timeout_seconds: int = 30

class AIStructuringClient:
    """
    Thin HTTP client for the external AI Structuring service.
    The service is expected to expose:
      - POST /api/queue/batch  (multipart upload)
      - GET  /api/queue/batch/{batch_id}
      - GET  /api/download/{batch_id}/zip
      - (optional) GET /api/download/{batch_id}/{file_type}/{filename}
    """
    def __init__(self, settings: AIStructuringSettings):
        if not settings.base_url:
            raise ValueError("AIStructuringClient requires a non-empty base_url")
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")

    def _headers(self) -> dict:
        if self.settings.api_key:
            return {"X-API-Key": self.settings.api_key}
        return {}

    def submit_batch(self, file_path: str, batch_name: str) -> str:
        url = f"{self.base_url}/api/queue/batch"
        with open(file_path, "rb") as f:
            files = [("files", (os.path.basename(file_path), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))]
            data = {
                "batch_name": batch_name,
                "document_type": self.settings.document_type,
                "use_markers": str(self.settings.use_markers).lower(),
            }
            resp = requests.post(url, files=files, data=data, headers=self._headers(), timeout=self.settings.request_timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
        # Support both {batch:{batch_id:..}} and {batch_id:..}
        batch_id = None
        if isinstance(payload, dict):
            batch_id = payload.get("batch_id") or (payload.get("batch", {}) or {}).get("batch_id")
        if not batch_id:
            raise RuntimeError(f"AI structuring: batch_id not found in response: {payload}")
        return batch_id

    def get_batch(self, batch_id: str) -> dict:
        url = f"{self.base_url}/api/queue/batch/{batch_id}"
        resp = requests.get(url, headers=self._headers(), timeout=self.settings.request_timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def wait_for_completion(self, batch_id: str) -> dict:
        start = time.time()
        last_payload = None
        while True:
            last_payload = self.get_batch(batch_id)
            # Try multiple possible locations for status/progress
            batch_obj = last_payload.get("batch", last_payload) if isinstance(last_payload, dict) else {}
            status = batch_obj.get("status") or batch_obj.get("state") or ""
            progress = batch_obj.get("progress_percent")
            if isinstance(progress, (int, float)) and progress >= 100:
                # continue to terminal check below
                pass

            terminal = status in {"completed", "failed", "cancelled", "completed_with_errors", "error", "done"}
            if terminal:
                return last_payload

            if time.time() - start > self.settings.max_wait_seconds:
                raise TimeoutError(f"AI structuring: batch {batch_id} did not complete within {self.settings.max_wait_seconds}s")

            time.sleep(self.settings.poll_interval_seconds)

    def download_zip(self, batch_id: str, out_zip_path: str) -> str:
        url = f"{self.base_url}/api/download/{batch_id}/zip"
        with requests.get(url, headers=self._headers(), stream=True, timeout=self.settings.request_timeout_seconds) as r:
            r.raise_for_status()
            with open(out_zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return out_zip_path

    @staticmethod
    def extract_first_processed_docx(zip_path: str, extract_to_dir: str) -> str:
        """
        Extracts the first .docx found under a 'processed' folder in the zip.
        If not found, extracts the first .docx anywhere in the zip.
        """
        os.makedirs(extract_to_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            processed_docx = [n for n in names if n.lower().endswith(".docx") and ("processed/" in n.lower() or "processed\\" in n.lower())]
            candidates = processed_docx or [n for n in names if n.lower().endswith(".docx")]
            if not candidates:
                raise RuntimeError("AI structuring: no DOCX found in output zip")
            target = candidates[0]
            z.extract(target, path=extract_to_dir)
            return os.path.join(extract_to_dir, target)

