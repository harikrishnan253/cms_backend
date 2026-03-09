"""
Celery Worker for S4Carlisle Pre-Editor v3
Production-ready task queue with Redis backend.
"""

import os
import time
import logging
from datetime import datetime
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis connection
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'pre_editor',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Task settings
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # Soft limit at 9 minutes
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Process one at a time per worker
    worker_concurrency=2,  # 2 concurrent workers
    
    # Reliability
    task_acks_late=True,  # Acknowledge after completion
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    
    # Result backend
    result_expires=86400,  # Results expire after 24 hours
    
    # Retry policy
    task_default_retry_delay=60,  # 1 minute between retries
    task_max_retries=3,
)


@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def process_document_task(self, job_id: str):
    """
    Process a single document job.
    
    Args:
        job_id: UUID of the job to process
        
    Returns:
        dict with processing results
    """
    logger.info(f"Starting task for job {job_id}")
    
    # Import here to avoid circular imports
    from app import create_app
    from app.models import db, Job, Batch, JobStatus
    from processor.pipeline import process_document
    
    app = create_app()
    
    with app.app_context():
        # Get job
        job = Job.query.filter_by(job_id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return {'success': False, 'error': f'Job {job_id} not found'}
        
        if job.status != JobStatus.PENDING:
            logger.warning(f"Job {job_id} is not pending (status: {job.status})")
            return {'success': False, 'error': f'Job is not pending'}
        
        # Update status to processing
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.utcnow()
        db.session.commit()
        
        start_time = time.time()
        
        try:
            batch = job.batch
            
            logger.info(f"Processing {job.original_filename}")
            
            # Process the document
            result = process_document(
                input_path=job.input_path,
                output_folder=batch.output_folder,
                document_type=job.document_type or batch.document_type,
                use_markers=job.use_markers if job.use_markers is not None else batch.use_markers
            )
            
            # Validate output_path before marking completed
            output_path = result.get('output_path')
            if not output_path:
                raise RuntimeError(
                    "OUTPUT_MISSING: Processed DOCX was not generated; output_path is empty."
                )

            # Update job with results
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
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
            
            # Update batch counters
            batch.completed_jobs += 1
            if batch.completed_jobs + batch.failed_jobs == batch.total_jobs:
                batch.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            logger.info(f"Completed job {job_id} in {job.processing_time_seconds:.1f}s")
            
            return {
                'success': True,
                'job_id': job_id,
                'filename': job.original_filename,
                'processing_time': job.processing_time_seconds,
                'total_paragraphs': job.total_paragraphs,
            }
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
            
            # Update job with error
            job.status = JobStatus.FAILED
            job.error_message = str(e)[:500]  # Truncate long errors
            job.completed_at = datetime.utcnow()
            job.processing_time_seconds = time.time() - start_time
            
            # Update batch counters
            batch = job.batch
            batch.failed_jobs += 1
            if batch.completed_jobs + batch.failed_jobs == batch.total_jobs:
                batch.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # Re-raise for Celery retry mechanism
            raise


@celery_app.task
def cleanup_old_batches(days: int = 30):
    """
    Cleanup batches older than specified days.
    Can be scheduled with Celery Beat.
    """
    from app import create_app
    from app.models import db, Batch
    from datetime import timedelta
    import shutil
    from pathlib import Path
    
    app = create_app()
    
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=days)
        old_batches = Batch.query.filter(Batch.completed_at < cutoff).all()
        
        deleted_count = 0
        for batch in old_batches:
            try:
                # Delete output folder
                if batch.output_folder and Path(batch.output_folder).exists():
                    shutil.rmtree(batch.output_folder)
                
                # Delete from database
                db.session.delete(batch)
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Error deleting batch {batch.batch_id}: {e}")
        
        db.session.commit()
        logger.info(f"Cleaned up {deleted_count} old batches")
        
        return {'deleted': deleted_count}


# Health check task
@celery_app.task
def health_check():
    """Simple health check task."""
    return {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}
