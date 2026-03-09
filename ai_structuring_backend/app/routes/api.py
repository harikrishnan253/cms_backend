"""
API Routes for queue management with token tracking and cost calculation.
"""

from flask import Blueprint, request, jsonify, send_file, current_app
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import func
import zipfile
import io

from ..services.queue import queue_service
from ..models.database import db, Job, Batch, JobStatus

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ============================================
# Gemini Pricing (Official - Jan 2025)
# Per 1 million tokens
# Source: https://ai.google.dev/gemini-api/docs/pricing
# NOTE: Output prices INCLUDE thinking tokens
# ============================================
PRICING = {
    'gemini-2.5-flash': {
        'input_per_million': 0.30,    # $0.30 per 1M input tokens (text/image/video)
        'output_per_million': 2.50,   # $2.50 per 1M output tokens (includes thinking)
    },
    'gemini-2.5-flash-lite': {
        'input_per_million': 0.10,    # $0.10 per 1M input tokens (text/image/video)
        'output_per_million': 0.40,   # $0.40 per 1M output tokens (includes thinking)
    },
    'gemini-2.5-pro': {
        'input_per_million': 1.25,    # $1.25 per 1M input tokens
        'output_per_million': 10.00,  # $10.00 per 1M output tokens (includes thinking)
    },
    'gemini-2.0-flash': {
        'input_per_million': 0.10,    # $0.10 per 1M input tokens
        'output_per_million': 0.40,   # $0.40 per 1M output tokens
    },
    'gemini-2.0-flash-lite': {
        'input_per_million': 0.075,   # $0.075 per 1M input tokens
        'output_per_million': 0.30,   # $0.30 per 1M output tokens
    },
    'gemini-1.5-flash': {
        'input_per_million': 0.075,   # $0.075 per 1M input tokens
        'output_per_million': 0.30,   # $0.30 per 1M output tokens
    },
    'gemini-1.5-pro': {
        'input_per_million': 1.25,    # $1.25 per 1M input tokens
        'output_per_million': 5.00,   # $5.00 per 1M output tokens
    },
}

# Current model being used
# Using gemini-2.5-flash-lite for cost-effective at-scale processing
CURRENT_MODEL = 'gemini-2.5-flash-lite'


def calculate_cost(input_tokens: int, output_tokens: int, model: str = CURRENT_MODEL) -> dict:
    """
    Calculate cost based on token usage.
    
    NOTE: For Gemini 2.5 models, output_tokens include thinking tokens
    (which are billed at output rates). The classifier handles this automatically.
    """
    pricing = PRICING.get(model, PRICING['gemini-2.5-flash-lite'])
    
    input_cost = (input_tokens / 1_000_000) * pricing['input_per_million']
    output_cost = (output_tokens / 1_000_000) * pricing['output_per_million']
    total_cost = input_cost + output_cost
    
    return {
        'input_cost': round(input_cost, 6),
        'output_cost': round(output_cost, 6),
        'total_cost': round(total_cost, 6),
        'model': model,
        'note': 'Output tokens include thinking tokens for Gemini 2.5 models'
    }


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'docx'


# ============================================
# Batch Endpoints
# ============================================

@api_bp.route('/queue/batch', methods=['POST'])
def create_batch():
    """Create a new batch with multiple files."""
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    
    valid_files = [
        (f.filename, f) for f in files
        if f.filename and allowed_file(f.filename)
    ]
    
    if not valid_files:
        return jsonify({'error': 'No valid DOCX files provided'}), 400
    
    document_type = request.form.get('document_type', 'Academic Document')
    use_markers = request.form.get('use_markers', 'false').lower() == 'true'
    batch_name = request.form.get('batch_name', '').strip() or None
    
    try:
        batch = queue_service.create_batch(
            files=valid_files,
            document_type=document_type,
            use_markers=use_markers,
            batch_name=batch_name
        )
        
        return jsonify({
            'success': True,
            'batch': batch.to_dict(),
            'message': f'Created batch with {len(valid_files)} files'
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error creating batch: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/queue/batch/<batch_id>', methods=['GET'])
def get_batch(batch_id: str):
    """Get batch details with jobs and cost information."""
    batch = queue_service.get_batch(batch_id)
    
    if not batch:
        return jsonify({'error': 'Batch not found'}), 404
    
    jobs = queue_service.get_batch_jobs(batch_id)
    
    # Auto-recalculate stats if they seem inconsistent
    actual_completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
    actual_failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
    
    if batch.completed_jobs != actual_completed or batch.failed_jobs != actual_failed:
        batch.completed_jobs = actual_completed
        batch.failed_jobs = actual_failed
        db.session.commit()
    
    # Calculate batch totals
    total_input_tokens = sum(j.input_tokens or 0 for j in jobs)
    total_output_tokens = sum(j.output_tokens or 0 for j in jobs)
    total_tokens = sum(j.total_tokens or 0 for j in jobs)
    total_processing_time = sum(j.processing_time_seconds or 0 for j in jobs)
    
    # Calculate costs
    cost_info = calculate_cost(total_input_tokens, total_output_tokens)
    
    # Add cost to each job
    jobs_with_cost = []
    for job in jobs:
        job_dict = job.to_dict()
        if job.input_tokens and job.output_tokens:
            job_cost = calculate_cost(job.input_tokens, job.output_tokens)
            job_dict['cost'] = job_cost
        else:
            job_dict['cost'] = None
        jobs_with_cost.append(job_dict)
    
    return jsonify({
        'batch': batch.to_dict(),
        'jobs': jobs_with_cost,
        'stats': {
            'total_input_tokens': total_input_tokens,
            'total_output_tokens': total_output_tokens,
            'total_tokens': total_tokens,
            'total_processing_time': round(total_processing_time, 2),
            'cost': cost_info,
        }
    })


@api_bp.route('/queue/batch/<batch_id>', methods=['DELETE'])
def delete_batch(batch_id: str):
    """Delete a batch."""
    if queue_service.delete_batch(batch_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Batch not found'}), 404


@api_bp.route('/queue/batch/<batch_id>/retry', methods=['POST'])
def retry_batch(batch_id: str):
    """Retry failed jobs in batch."""
    retried = queue_service.retry_batch_failed(batch_id)
    return jsonify({'success': True, 'retried_jobs': retried})


@api_bp.route('/queue/batch/<batch_id>/stop', methods=['POST'])
def stop_batch(batch_id: str):
    """Emergency stop - cancel all pending jobs in batch."""
    cancelled = queue_service.stop_batch(batch_id)
    return jsonify({
        'success': True, 
        'cancelled_jobs': cancelled,
        'message': f'Stopped batch: {cancelled} pending jobs cancelled'
    })


@api_bp.route('/queue/batch/<batch_id>/recalculate', methods=['POST'])
def recalculate_batch(batch_id: str):
    """Recalculate batch statistics from actual job statuses."""
    success = queue_service.recalculate_batch_stats(batch_id)
    if success:
        batch = queue_service.get_batch(batch_id)
        return jsonify({
            'success': True,
            'batch': batch.to_dict() if batch else None
        })
    return jsonify({'error': 'Batch not found'}), 404


@api_bp.route('/queue/batches', methods=['GET'])
def list_batches():
    """List all batches with summary stats."""
    limit = request.args.get('limit', 50, type=int)
    batches = queue_service.get_all_batches(limit=limit)
    
    batches_with_stats = []
    for batch in batches:
        # Auto-recalculate stats if they seem inconsistent
        jobs = Job.query.filter_by(batch_id=batch.id).all()
        actual_completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        actual_failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
        
        # Fix stats if they don't match actual job statuses
        if batch.completed_jobs != actual_completed or batch.failed_jobs != actual_failed:
            batch.completed_jobs = actual_completed
            batch.failed_jobs = actual_failed
            db.session.commit()
        
        batch_dict = batch.to_dict()
        
        # Get token totals for this batch
        total_tokens = sum(j.total_tokens or 0 for j in jobs)
        total_input = sum(j.input_tokens or 0 for j in jobs)
        total_output = sum(j.output_tokens or 0 for j in jobs)
        
        batch_dict['total_tokens'] = total_tokens
        if total_input > 0 or total_output > 0:
            batch_dict['cost'] = calculate_cost(total_input, total_output)
        else:
            batch_dict['cost'] = None
            
        batches_with_stats.append(batch_dict)
    
    return jsonify({
        'batches': batches_with_stats,
        'total': len(batches)
    })


# ============================================
# Job Endpoints
# ============================================

@api_bp.route('/queue/job/<job_id>', methods=['GET'])
def get_job(job_id: str):
    """Get job details with cost."""
    job = Job.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    job_dict = job.to_dict()
    if job.input_tokens and job.output_tokens:
        job_dict['cost'] = calculate_cost(job.input_tokens, job.output_tokens)
    
    return jsonify({'job': job_dict})


@api_bp.route('/queue/job/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id: str):
    """Cancel a pending job."""
    if queue_service.cancel_job(job_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Job not found or not pending'}), 400


@api_bp.route('/queue/job/<job_id>/retry', methods=['POST'])
def retry_job(job_id: str):
    """Retry a failed job."""
    if queue_service.retry_job(job_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Job not found or not failed'}), 400


# ============================================
# Queue Status & Statistics
# ============================================

@api_bp.route('/queue/status', methods=['GET'])
def queue_status():
    """Get queue statistics."""
    return jsonify(queue_service.get_queue_status())


@api_bp.route('/queue/stats/tokens', methods=['GET'])
def token_stats():
    """Get detailed token usage statistics with cost breakdown."""
    stats = queue_service.get_token_stats()
    
    # Add cost calculations
    all_time_cost = calculate_cost(
        stats['all_time']['input_tokens'],
        stats['all_time']['output_tokens']
    )
    today_cost = calculate_cost(
        stats['today']['input_tokens'],
        stats['today']['output_tokens']
    )
    
    stats['all_time']['cost'] = all_time_cost
    stats['today']['cost'] = today_cost
    
    # Calculate averages
    if stats['all_time']['total_jobs'] > 0:
        avg_tokens = stats['all_time']['total_tokens'] / stats['all_time']['total_jobs']
        avg_cost = all_time_cost['total_cost'] / stats['all_time']['total_jobs']
        stats['averages'] = {
            'tokens_per_job': round(avg_tokens, 0),
            'cost_per_job': round(avg_cost, 6),
        }
    else:
        stats['averages'] = {
            'tokens_per_job': 0,
            'cost_per_job': 0,
        }
    
    # Add pricing info with thinking tokens note
    stats['pricing'] = {
        'model': CURRENT_MODEL,
        'rates': PRICING[CURRENT_MODEL],
        'thinking_tokens_note': 'Output tokens include thinking tokens (Gemini 2.5 feature)',
    }
    
    return jsonify(stats)


@api_bp.route('/queue/stats/daily', methods=['GET'])
def daily_stats():
    """Get daily token usage for the last 30 days."""
    days = request.args.get('days', 30, type=int)
    
    results = []
    for i in range(days):
        date = datetime.utcnow().date() - timedelta(days=i)
        
        day_stats = db.session.query(
            func.sum(Job.input_tokens).label('input'),
            func.sum(Job.output_tokens).label('output'),
            func.sum(Job.total_tokens).label('total'),
            func.count(Job.id).label('jobs')
        ).filter(
            Job.status == JobStatus.COMPLETED,
            func.date(Job.completed_at) == date
        ).first()
        
        input_tokens = day_stats.input or 0
        output_tokens = day_stats.output or 0
        
        results.append({
            'date': date.isoformat(),
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': day_stats.total or 0,
            'jobs_completed': day_stats.jobs or 0,
            'cost': calculate_cost(input_tokens, output_tokens),
        })
    
    return jsonify({
        'daily_stats': results,
        'period_days': days,
    })


# ============================================
# Downloads
# ============================================

@api_bp.route('/download/<batch_id>/<file_type>/<filename>', methods=['GET'])
def download_file(batch_id: str, file_type: str, filename: str):
    """Download a specific output file."""
    batch = queue_service.get_batch(batch_id)
    if not batch or not batch.output_folder:
        return jsonify({'error': 'Batch not found'}), 404
    
    if file_type not in ['processed', 'review', 'json']:
        return jsonify({'error': 'Invalid file type'}), 400
    
    file_path = Path(batch.output_folder) / file_type / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(file_path, as_attachment=True)


@api_bp.route('/download/<batch_id>/zip', methods=['GET'])
def download_batch_zip(batch_id: str):
    """Download all batch outputs as ZIP."""
    batch = queue_service.get_batch(batch_id)
    if not batch or not batch.output_folder:
        return jsonify({'error': 'Batch not found'}), 404
    
    output_folder = Path(batch.output_folder)
    if not output_folder.exists():
        return jsonify({'error': 'Output folder not found'}), 404
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for folder in ['processed', 'review', 'json', 'html']:
            folder_path = output_folder / folder
            if folder_path.exists():
                for file_path in folder_path.iterdir():
                    if file_path.is_file():
                        arcname = f"{folder}/{file_path.name}"
                        zf.write(file_path, arcname)
    
    zip_buffer.seek(0)
    
    zip_name = f"{batch.name or batch_id}.zip".replace(' ', '_')
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_name
    )
