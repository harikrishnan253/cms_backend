"""API tests for terminal integrity failure status visibility."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.database import Batch, Job, JobStatus
from app.routes.api import api_bp
import app.routes.api as api_module


def _make_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(api_bp)
    return app


class _FakeBatch:
    def __init__(self, *, total_jobs=1, completed_jobs=0, failed_jobs=1, status="completed_with_errors"):
        self.id = 1
        self.batch_id = "batch-123"
        self.name = "Test Batch"
        self.created_at = None
        self.completed_at = None
        self.document_type = "Academic Document"
        self.use_markers = False
        self.total_jobs = total_jobs
        self.completed_jobs = completed_jobs
        self.failed_jobs = failed_jobs
        self.output_folder = "outputs/batch-123"
        self.status = status
        self.progress_percent = 100

    def to_dict(self):
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "name": self.name,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "document_type": self.document_type,
            "use_markers": self.use_markers,
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "status": self.status,
            "is_terminal": True,
            "progress_percent": self.progress_percent,
            "output_folder": self.output_folder,
            "timezone": "IST",
        }


def _failed_integrity_job(*, diagnostics_len: int = 700) -> Job:
    job = Job(
        id=1,
        job_id="job-123",
        batch_id=1,
        original_filename="integrity_fail.docx",
        input_path="uploads/integrity_fail.docx",
        status=JobStatus.FAILED,
        queue_position=1,
        error_message=(
            "INTEGRITY_TRIGGER_FAIL [stage=integrity_check] Integrity verification failed. "
            "See logs for details. | diagnostics=" + ("X" * diagnostics_len)
        ),
        total_paragraphs=244,
    )
    return job


class TestQueueApiFailedIntegrityVisibility:
    def test_batch_model_to_dict_handles_string_status_property(self):
        batch = Batch(
            id=1,
            batch_id="batch-x",
            total_jobs=1,
            completed_jobs=0,
            failed_jobs=1,
            output_folder="outputs/batch-x",
        )

        payload = batch.to_dict()
        assert payload["status"] == "completed_with_errors"
        assert payload["is_terminal"] is True

    def test_batch_endpoint_returns_terminal_failed_job_with_stage_and_diagnostics(self):
        app = _make_app()
        client = app.test_client()

        batch = _FakeBatch()
        failed_job = _failed_integrity_job()

        with (
            patch.object(api_module.queue_service, "get_batch", return_value=batch),
            patch.object(api_module.queue_service, "get_batch_jobs", return_value=[failed_job]),
            patch.object(api_module.db, "session", SimpleNamespace(commit=Mock())),
        ):
            resp = client.get("/api/queue/batch/batch-123")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["batch"]["status"] == "completed_with_errors"
        assert payload["batch"]["is_terminal"] is True
        assert len(payload["jobs"]) == 1

        job = payload["jobs"][0]
        assert job["status"] == "failed"
        assert job["is_terminal"] is True
        assert job["stage"] == "integrity_check"
        assert job["error"] == "INTEGRITY_TRIGGER_FAIL"
        assert "Integrity verification failed" in (job["failure_message"] or "")
        assert isinstance(job["diagnostics"], str)
        assert len(job["diagnostics"]) <= 500
        assert job["diagnostics_truncated"] is True

    def test_job_endpoint_returns_structured_integrity_failure_fields(self):
        app = _make_app()
        client = app.test_client()

        failed_job = _failed_integrity_job(diagnostics_len=50)
        fake_job_model = SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **kwargs: SimpleNamespace(first=lambda: failed_job)
            )
        )

        with patch.object(api_module, "Job", fake_job_model):
            resp = client.get("/api/queue/job/job-123")

        assert resp.status_code == 200
        payload = resp.get_json()
        job = payload["job"]
        assert job["status"] == "failed"
        assert job["stage"] == "integrity_check"
        assert job["error"] == "INTEGRITY_TRIGGER_FAIL"
        assert job["diagnostics"] == "X" * 50
        assert job["diagnostics_truncated"] is False
