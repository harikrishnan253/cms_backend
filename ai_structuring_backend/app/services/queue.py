"""
Queue Service - Supports both Threading (simple) and Celery (production) modes.
Set QUEUE_MODE environment variable to 'threading' or 'celery'.
All timestamps are in IST (India Standard Time - UTC+5:30)
"""

import os
import uuid
import shutil
import logging
import threading
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

from ..models.database import db, Batch, Job, JobStatus, get_ist_now, IST

logger = logging.getLogger(__name__)

# Queue mode: 'threading' (simple) or 'celery' (production)
QUEUE_MODE = os.getenv('QUEUE_MODE', 'threading')


def _pipeline_failure_details(result: dict) -> dict | None:
    """Parse a structured pipeline failure result, if present."""
    if not isinstance(result, dict):
        return None

    status = str(result.get("status", "")).upper()
    if status != "FAILED":
        return None

    error_code = str(result.get("error") or "PIPELINE_FAILED").strip() or "PIPELINE_FAILED"
    stage = result.get("stage")
    diagnostics = None

    if stage:
        diagnostics = result.get(stage)
        if diagnostics is None and "diagnostics" in result:
            diagnostics = result.get("diagnostics")
    elif "structure_guard" in result:
        stage = "structure_guard"
        diagnostics = result.get("structure_guard")
    elif "integrity_check" in result:
        stage = "integrity_check"
        diagnostics = result.get("integrity_check")
    else:
        stage = "pipeline"

    message = str(result.get("message") or error_code).strip() or error_code
    diag_text = ""
    if isinstance(diagnostics, dict):
        diag_text = str(
            diagnostics.get("error")
            or diagnostics.get("message")
            or diagnostics.get("status")
            or ""
        ).strip()
    elif diagnostics is not None:
        diag_text = str(diagnostics).strip()

    error_message = f"{error_code} [stage={stage}] {message}"
    if diag_text and diag_text not in error_message:
        error_message = f"{error_message} | diagnostics={diag_text}"

    return {
        "error_code": error_code,
        "stage": stage,
        "message": message,
        "diagnostics": diagnostics,
        "error_message": error_message[:4000],
    }


class QueueService:
    """Manages document processing queue."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.app = None
        self.upload_folder = Path('uploads')
        self.output_folder = Path('outputs')
        self.queue_mode = QUEUE_MODE
        
        # Threading mode
        self._processing_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_processing = False
        self._current_job_id: Optional[str] = None
        
        self._initialized = True
        logger.info(f"QueueService initialized in {self.queue_mode} mode")
    
    def init_app(self, app):
        """Initialize with Flask app."""
        self.app = app
        self.upload_folder = Path(app.config.get('UPLOAD_FOLDER', 'uploads'))
        self.output_folder = Path(app.config.get('OUTPUT_FOLDER', 'outputs'))
        
        self.upload_folder.mkdir(exist_ok=True)
        self.output_folder.mkdir(exist_ok=True)
        
        # Start processing based on mode
        if self.queue_mode == 'threading':
            self.start_processing()
        # Celery mode doesn't need to start anything here
    
    def start_processing(self):
        """Start background processing thread (threading mode only)."""
        if self.queue_mode != 'threading':
            return
            
        if self._processing_thread is None or not self._processing_thread.is_alive():
            self._stop_event.clear()
            self._processing_thread = threading.Thread(target=self._process_loop, daemon=True)
            self._processing_thread.start()
            logger.info("Queue processing thread started")
    
    def stop_processing(self):
        """Stop processing thread."""
        self._stop_event.set()
        if self._processing_thread:
            self._processing_thread.join(timeout=30)
    
    def create_batch(
        self,
        files: List[tuple],
        document_type: str = "Academic Document",
        use_markers: bool = False,
        batch_name: Optional[str] = None
    ) -> Batch:
        """Create a new batch with multiple files."""
        batch_id = str(uuid.uuid4())
        
        # Create output folder with IST timestamp
        ist_now = get_ist_now()
        timestamp = ist_now.strftime("%Y%m%d_%H%M%S")
        folder_name = f"batch_{timestamp}_{batch_id[:8]}"
        if batch_name:
            safe_name = "".join(c for c in batch_name if c.isalnum() or c in ' -_').strip()[:50]
            folder_name = f"{safe_name.replace(' ', '_')}_{timestamp}"
        
        batch_output_folder = self.output_folder / folder_name
        batch_output_folder.mkdir(exist_ok=True)
        (batch_output_folder / "processed").mkdir(exist_ok=True)
        (batch_output_folder / "review").mkdir(exist_ok=True)
        (batch_output_folder / "json").mkdir(exist_ok=True)
        
        # Create batch record
        batch = Batch(
            batch_id=batch_id,
            name=batch_name or f"Batch {timestamp}",
            document_type=document_type,
            use_markers=use_markers,
            output_folder=str(batch_output_folder),
            total_jobs=len(files)
        )
        db.session.add(batch)
        db.session.flush()
        
        # Create upload folder
        batch_upload_folder = self.upload_folder / batch_id
        batch_upload_folder.mkdir(exist_ok=True)
        
        # Create jobs
        job_ids = []
        for idx, (filename, file_storage) in enumerate(files):
            safe_filename = self._sanitize_filename(filename)
            input_path = batch_upload_folder / safe_filename
            file_storage.save(str(input_path))
            
            job = Job(
                job_id=str(uuid.uuid4()),
                batch_id=batch.id,
                original_filename=filename,
                input_path=str(input_path),
                document_type=document_type,
                use_markers=use_markers,
                status=JobStatus.PENDING,
                queue_position=idx + 1
            )
            db.session.add(job)
            job_ids.append(job.job_id)
        
        db.session.commit()
        logger.info(f"Created batch {batch_id} with {len(files)} jobs")
        
        # Queue jobs in Celery mode
        if self.queue_mode == 'celery':
            self._queue_celery_jobs(job_ids)
        
        return batch
    
    def _queue_celery_jobs(self, job_ids: List[str]):
        """Queue jobs to Celery."""
        try:
            from celery_worker import process_document_task
            for job_id in job_ids:
                process_document_task.delay(job_id)
                logger.info(f"Queued job {job_id} to Celery")
        except Exception as e:
            logger.error(f"Failed to queue jobs to Celery: {e}")
    
    def get_batch(self, batch_id: str) -> Optional[Batch]:
        return Batch.query.filter_by(batch_id=batch_id).first()
    
    def get_batch_jobs(self, batch_id: str) -> List[Job]:
        batch = self.get_batch(batch_id)
        if not batch:
            return []
        return Job.query.filter_by(batch_id=batch.id).order_by(Job.queue_position).all()
    
    def get_all_batches(self, limit: int = 50) -> List[Batch]:
        return Batch.query.order_by(Batch.created_at.desc()).limit(limit).all()
    
    def recalculate_batch_stats(self, batch_id: str) -> bool:
        """Recalculate batch statistics from actual job statuses."""
        batch = self.get_batch(batch_id)
        if not batch:
            return False
        
        # Count actual job statuses
        completed_count = Job.query.filter_by(
            batch_id=batch.id,
            status=JobStatus.COMPLETED
        ).count()
        
        failed_count = Job.query.filter_by(
            batch_id=batch.id,
            status=JobStatus.FAILED
        ).count()
        
        # Update batch counters
        batch.completed_jobs = completed_count
        batch.failed_jobs = failed_count
        
        # Update completion status with IST
        if batch.completed_jobs + batch.failed_jobs == batch.total_jobs:
            if not batch.completed_at:
                batch.completed_at = get_ist_now()
        else:
            batch.completed_at = None
        
        db.session.commit()
        return True
    
    def get_queue_status(self) -> dict:
        pending = Job.query.filter_by(status=JobStatus.PENDING).count()
        processing = Job.query.filter_by(status=JobStatus.PROCESSING).count()
        completed = Job.query.filter_by(status=JobStatus.COMPLETED).count()
        failed = Job.query.filter_by(status=JobStatus.FAILED).count()
        
        return {
            'pending': pending,
            'processing': processing,
            'completed': completed,
            'failed': failed,
            'total': pending + processing + completed + failed,
            'is_processing': self._is_processing,
            'current_job_id': self._current_job_id,
            'queue_mode': self.queue_mode,
        }
    
    def get_token_stats(self) -> dict:
        """Get aggregated token statistics."""
        from sqlalchemy import func
        
        # Total tokens across all jobs
        totals = db.session.query(
            func.sum(Job.input_tokens).label('total_input'),
            func.sum(Job.output_tokens).label('total_output'),
            func.sum(Job.total_tokens).label('total_tokens'),
            func.count(Job.id).label('total_jobs')
        ).filter(Job.status == JobStatus.COMPLETED).first()
        
        # Today's tokens (using IST date)
        ist_now = get_ist_now()
        today = ist_now.date()
        today_stats = db.session.query(
            func.sum(Job.input_tokens).label('input'),
            func.sum(Job.output_tokens).label('output'),
            func.sum(Job.total_tokens).label('total')
        ).filter(
            Job.status == JobStatus.COMPLETED,
            func.date(Job.completed_at) == today
        ).first()
        
        return {
            'all_time': {
                'input_tokens': totals.total_input or 0,
                'output_tokens': totals.total_output or 0,
                'total_tokens': totals.total_tokens or 0,
                'total_jobs': totals.total_jobs or 0,
            },
            'today': {
                'input_tokens': today_stats.input or 0,
                'output_tokens': today_stats.output or 0,
                'total_tokens': today_stats.total or 0,
            },
            'timezone': 'IST',
            'current_time': ist_now.isoformat(),
        }
    
    def cancel_job(self, job_id: str) -> bool:
        job = Job.query.filter_by(job_id=job_id).first()
        if job and job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            db.session.commit()
            return True
        return False
    
    def retry_job(self, job_id: str) -> bool:
        job = Job.query.filter_by(job_id=job_id).first()
        if job and job.status == JobStatus.FAILED:
            job.status = JobStatus.PENDING
            job.error_message = None
            job.started_at = None
            job.completed_at = None
            db.session.commit()
            
            # Re-queue in Celery mode
            if self.queue_mode == 'celery':
                self._queue_celery_jobs([job_id])
            
            return True
        return False
    
    def retry_batch_failed(self, batch_id: str) -> int:
        batch = self.get_batch(batch_id)
        if not batch:
            return 0
        
        failed_jobs = Job.query.filter_by(
            batch_id=batch.id,
            status=JobStatus.FAILED
        ).all()
        
        job_ids = []
        for job in failed_jobs:
            job.status = JobStatus.PENDING
            job.error_message = None
            job.started_at = None
            job.completed_at = None
            job_ids.append(job.job_id)
        
        # Decrement failed_jobs counter since they're now pending again
        retry_count = len(job_ids)
        if retry_count > 0:
            batch.failed_jobs = max(0, batch.failed_jobs - retry_count)
            batch.completed_at = None  # Reset completion since we're re-processing
        
        db.session.commit()
        
        # Re-queue in Celery mode
        if self.queue_mode == 'celery' and job_ids:
            self._queue_celery_jobs(job_ids)
        
        return retry_count
    
    def stop_batch(self, batch_id: str) -> int:
        """Emergency stop - cancel all pending and processing jobs in batch."""
        batch = self.get_batch(batch_id)
        if not batch:
            return 0
        
        # Find all pending and processing jobs
        stoppable_jobs = Job.query.filter(
            Job.batch_id == batch.id,
            Job.status.in_([JobStatus.PENDING, JobStatus.PROCESSING])
        ).all()
        
        cancelled_count = 0
        for job in stoppable_jobs:
            job.status = JobStatus.CANCELLED
            job.error_message = "Stopped by user"
            cancelled_count += 1
        
        # Update batch status
        if cancelled_count > 0:
            # Mark batch as completed (with cancellations)
            batch.completed_at = get_ist_now()
        
        db.session.commit()
        
        logger.info(f"Emergency stop: Cancelled {cancelled_count} jobs in batch {batch_id}")
        return cancelled_count
    
    def delete_batch(self, batch_id: str) -> bool:
        batch = self.get_batch(batch_id)
        if not batch:
            return False
        
        # Delete folders
        batch_upload_folder = self.upload_folder / batch_id
        if batch_upload_folder.exists():
            shutil.rmtree(batch_upload_folder)
        
        if batch.output_folder and Path(batch.output_folder).exists():
            shutil.rmtree(batch.output_folder)
        
        db.session.delete(batch)
        db.session.commit()
        return True
    
    def _process_loop(self):
        """Background processing loop (threading mode only)."""
        logger.info("Processing loop started")
        
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    job = Job.query.filter_by(status=JobStatus.PENDING).order_by(
                        Job.created_at, Job.queue_position
                    ).first()
                    
                    if job:
                        self._process_job(job)
                    else:
                        time.sleep(2)
                        
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                time.sleep(5)
    
    def _process_job(self, job: Job):
        """Process a single job (threading mode) with content integrity verification."""
        logger.info(f"Processing job {job.job_id}: {job.original_filename}")
        
        self._is_processing = True
        self._current_job_id = job.job_id
        
        job.status = JobStatus.PROCESSING
        job.started_at = get_ist_now()
        # Clear stale failure text from previous attempts while the retry is running.
        job.error_message = None
        db.session.commit()
        
        start_time = time.time()
        
        try:
            from processor.pipeline import process_document
            
            batch = job.batch
            
            # Calculate content hash BEFORE processing for integrity verification
            original_content_hash = self._calculate_content_hash(job.input_path)
            
            result = process_document(
                input_path=job.input_path,
                output_folder=batch.output_folder,
                document_type=job.document_type or batch.document_type,
                use_markers=job.use_markers if job.use_markers is not None else batch.use_markers,
                job_id=job.job_id,
            )

            pipeline_failure = _pipeline_failure_details(result)
            if pipeline_failure:
                ist_now = get_ist_now()
                job.status = JobStatus.FAILED
                job.error_message = pipeline_failure["error_message"]
                job.completed_at = ist_now
                job.processing_time_seconds = time.time() - start_time

                # Preserve useful stats when the pipeline failed after partial execution.
                job.total_paragraphs = result.get('total_paragraphs')
                job.input_tokens = result.get('input_tokens')
                job.output_tokens = result.get('output_tokens')
                job.total_tokens = result.get('total_tokens')
                job.content_hash = original_content_hash

                batch.failed_jobs += 1
                if batch.completed_jobs + batch.failed_jobs == batch.total_jobs:
                    batch.completed_at = ist_now

                db.session.commit()
                logger.warning(
                    "Pipeline failed for job %s (%s): %s",
                    job.job_id,
                    pipeline_failure["stage"],
                    pipeline_failure["error_message"],
                )
                return
             
            # Validate output_path before marking completed
            output_path = result.get('output_path')
            if not output_path:
                raise RuntimeError(
                    "OUTPUT_MISSING: Processed DOCX was not generated; output_path is empty."
                )

            # Update job with results - using IST
            ist_now = get_ist_now()
            job.status = JobStatus.COMPLETED
            # Successful completion must not retain a prior failure message from retries.
            job.error_message = None
            job.completed_at = ist_now
            job.processing_time_seconds = time.time() - start_time
            job.output_path = output_path
            job.review_path = result.get('review_path')
            job.json_path = result.get('json_path')
            job.total_paragraphs = result.get('total_paragraphs')
            job.auto_applied = result.get('auto_applied')
            job.needs_review = result.get('needs_review')
            job.input_tokens = result.get('input_tokens')
            job.output_tokens = result.get('output_tokens')
            job.total_tokens = result.get('total_tokens')

            # Content integrity tracking
            job.original_paragraph_count = result.get('total_paragraphs')
            job.processed_paragraph_count = result.get('total_paragraphs')
            job.content_hash = original_content_hash

            batch.completed_jobs += 1
            if batch.completed_jobs + batch.failed_jobs == batch.total_jobs:
                batch.completed_at = ist_now
            
            db.session.commit()
            logger.info(f"Completed job {job.job_id} in {job.processing_time_seconds:.1f}s (IST: {ist_now.strftime('%Y-%m-%d %H:%M:%S')})")
            
        except Exception as e:
            logger.error(f"Error processing job {job.job_id}: {e}", exc_info=True)
            
            ist_now = get_ist_now()
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = ist_now
            job.processing_time_seconds = time.time() - start_time
            
            batch = job.batch
            batch.failed_jobs += 1
            if batch.completed_jobs + batch.failed_jobs == batch.total_jobs:
                batch.completed_at = ist_now
            
            db.session.commit()
        
        finally:
            self._is_processing = False
            self._current_job_id = None
    
    def _calculate_content_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file content for integrity verification."""
        try:
            from docx import Document
            doc = Document(file_path)
            
            # Hash all paragraph text content
            content = ""
            for para in doc.paragraphs:
                content += para.text
            
            return hashlib.sha256(content.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.warning(f"Could not calculate content hash: {e}")
            return ""
    
    def _sanitize_filename(self, filename: str) -> str:
        filename = Path(filename).name
        safe_chars = "".join(c for c in filename if c.isalnum() or c in '.-_ ')
        return safe_chars or "document.docx"


queue_service = QueueService()
