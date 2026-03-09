"""Queue service failure reporting tests."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.models.database import JobStatus
from app.services import queue as queue_module


def _make_job(tmp_path):
    batch = SimpleNamespace(
        output_folder=str(tmp_path / "batch_out"),
        document_type="Academic Document",
        use_markers=False,
        completed_jobs=0,
        failed_jobs=0,
        total_jobs=1,
        completed_at=None,
    )
    job = SimpleNamespace(
        job_id="job-123",
        original_filename="input.docx",
        input_path=str(tmp_path / "input.docx"),
        document_type=None,
        use_markers=None,
        batch=batch,
        status=JobStatus.PENDING,
        started_at=None,
        completed_at=None,
        processing_time_seconds=None,
        output_path=None,
        review_path=None,
        json_path=None,
        error_message=None,
        total_paragraphs=None,
        auto_applied=None,
        needs_review=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        original_paragraph_count=None,
        processed_paragraph_count=None,
        content_hash=None,
    )
    return job


def _mock_db():
    return SimpleNamespace(session=SimpleNamespace(commit=Mock()))


class TestQueuePipelineFailureReporting:
    def test_pipeline_failed_result_with_empty_output_surfaces_true_reason(self, tmp_path, caplog):
        caplog.set_level(logging.INFO)
        job = _make_job(tmp_path)
        svc = queue_module.QueueService()

        pipeline_result = {
            "status": "FAILED",
            "error": "STRUCTURE_GUARD_FAIL",
            "message": "Structure guard failed: processor mutated document structure.",
            "structure_guard": {
                "status": "FAIL",
                "error": "STRUCTURE_GUARD_FAIL: list status/level/id changed",
            },
            "total_paragraphs": 12,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "output_path": "",
        }

        with (
            patch.object(queue_module, "db", _mock_db()),
            patch.object(queue_module.QueueService, "_calculate_content_hash", return_value="hash123"),
            patch("processor.pipeline.process_document", return_value=pipeline_result),
        ):
            svc._process_job(job)

        assert job.status == JobStatus.FAILED
        assert "STRUCTURE_GUARD_FAIL" in (job.error_message or "")
        assert "stage=structure_guard" in (job.error_message or "")
        assert "OUTPUT_MISSING" not in (job.error_message or "")
        assert job.total_paragraphs == 12
        assert job.total_tokens == 15
        assert job.batch.failed_jobs == 1
        assert job.batch.completed_jobs == 0

        # Expected pipeline failures should not be logged as exception traces.
        assert not any(
            rec.levelno >= logging.ERROR and "Error processing job" in rec.message
            for rec in caplog.records
        )
        assert any(
            rec.levelno == logging.WARNING and "Pipeline failed for job" in rec.message
            for rec in caplog.records
        )

    def test_output_missing_only_for_success_without_output(self, tmp_path):
        job = _make_job(tmp_path)
        svc = queue_module.QueueService()

        pipeline_result = {
            "status": "SUCCESS",
            "total_paragraphs": 3,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            # output_path intentionally missing
        }

        with (
            patch.object(queue_module, "db", _mock_db()),
            patch.object(queue_module.QueueService, "_calculate_content_hash", return_value="hash123"),
            patch("processor.pipeline.process_document", return_value=pipeline_result),
        ):
            svc._process_job(job)

        assert job.status == JobStatus.FAILED
        assert "OUTPUT_MISSING" in (job.error_message or "")

    def test_pipeline_failed_result_preserves_explicit_integrity_stage(self, tmp_path):
        job = _make_job(tmp_path)
        svc = queue_module.QueueService()

        pipeline_result = {
            "status": "FAILED",
            "error": "INTEGRITY_TRIGGER_FAIL",
            "stage": "integrity_check",
            "message": "Integrity verification failed. See logs for details.",
            "diagnostics": {
                "status": "FAIL",
                "structural_integrity": {
                    "status": "FAIL",
                    "first_difference": {
                        "stage": "integrity_check",
                        "paragraph_index": 22,
                        "message": "Heading level mismatch at para 22",
                    },
                },
            },
            "integrity_check": {
                "status": "ERROR",
                "error": "INTEGRITY_TRIGGER_FAIL: Heading level mismatch at para 22",
            },
            "total_paragraphs": 244,
            "output_path": "",
        }

        with (
            patch.object(queue_module, "db", _mock_db()),
            patch.object(queue_module.QueueService, "_calculate_content_hash", return_value="hash123"),
            patch("processor.pipeline.process_document", return_value=pipeline_result),
        ):
            svc._process_job(job)

        assert job.status == JobStatus.FAILED
        assert "INTEGRITY_TRIGGER_FAIL" in (job.error_message or "")
        assert "stage=integrity_check" in (job.error_message or "")
        assert "OUTPUT_MISSING" not in (job.error_message or "")

    def test_successful_retry_clears_stale_error_message(self, tmp_path):
        job = _make_job(tmp_path)
        job.error_message = "[Errno 13] Permission denied: 'C:\\\\Users\\\\harikrishnam\\\\Downloads\\\\x.docx'"
        svc = queue_module.QueueService()

        pipeline_result = {
            "status": "SUCCESS",
            "output_path": str(tmp_path / "out.docx"),
            "review_path": str(tmp_path / "review.docx"),
            "json_path": str(tmp_path / "out.json"),
            "total_paragraphs": 10,
            "auto_applied": 8,
            "needs_review": 2,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        with (
            patch.object(queue_module, "db", _mock_db()),
            patch.object(queue_module.QueueService, "_calculate_content_hash", return_value="hash123"),
            patch("processor.pipeline.process_document", return_value=pipeline_result),
        ):
            svc._process_job(job)

        assert job.status == JobStatus.COMPLETED
        assert job.error_message is None
        assert job.output_path == pipeline_result["output_path"]
