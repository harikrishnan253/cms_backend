from app.services.file_service import UPLOAD_DIR
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import os
import shutil
import logging
import traceback
from datetime import datetime

from app import models, database
from app.auth import get_current_user_from_cookie
from app.processing.ppd_engine import PPDEngine
from app.processing.permissions_engine import PermissionsEngine
from app.processing.technical_engine import TechnicalEngine
from app.processing.legacy.highlighter.technical_editor import TechnicalEditor
from app.processing.references_engine import ReferencesEngine
from app.processing.structuring_engine import StructuringEngine
from app.processing.bias_engine import BiasEngine
from app.processing.ai_extractor_engine import AIExtractorEngine
from app.processing.xml_engine import XMLEngine
from app.services.checkout_lock_service import CheckoutLockService

# Configure specialized logger for processing
logger = logging.getLogger("app.processing")
logger.setLevel(logging.INFO)

router = APIRouter()
checkout_lock_service = CheckoutLockService()

# Role Mappings
PROCESS_PERMISSIONS = {
    'language': ['Editor', 'CopyEditor', 'Admin'],
    'technical': ['Editor', 'CopyEditor', 'Admin'],
    'macro_processing': ['Editor', 'CopyEditor', 'Admin'],
    'ppd': ['PPD', 'ProjectManager', 'Admin'],
    'permissions': ['PermissionsManager', 'ProjectManager', 'Admin'],
    'reference_validation': ['Editor', 'CopyEditor', 'Admin'],
    'structuring': ['Editor', 'CopyEditor', 'Admin'],
    'bias_scan': ['Editor', 'CopyEditor', 'Admin', 'ProjectManager'],
    'credit_extractor_ai': ['PermissionsManager', 'ProjectManager', 'Admin'],
    'word_to_xml': ['PPD', 'ProjectManager', 'Admin']
}

def check_permission(user, process_type: str):
    allowed = PROCESS_PERMISSIONS.get(process_type, ['Admin'])
    user_role_names = [r.name for r in user.roles]
    if not any(role in user_role_names for role in allowed):
        logger.warning(f"Permission denied for user {user.username} on {process_type}. Roles: {user_role_names}")
        raise HTTPException(
            status_code=403, 
            detail=f"Permission denied. Required roles: {', '.join(allowed)}. Your roles: {', '.join(user_role_names)}"
        )

def background_processing_task(
    file_id: int,
    process_type: str,
    user_id: int,
    user_username: str,
    mode: str = "style" 
):
    """
    Background worker for file processing logic.
    """
    # Create a fresh DB session for the background task
    db = database.SessionLocal()
    try:
        logger.info(f"Background task started: File {file_id}, Type {process_type}, User {user_username}")
        
        file_record = db.query(models.File).filter(models.File.id == file_id).first()
        if not file_record:
            logger.error(f"File {file_id} not found in background task.")
            return

        file_path = os.path.abspath(file_record.path)
        
        # 1. Run Process
        success_msg = ""
        generated_files = []
        is_macro_fallback = False

        try:
            if process_type == 'permissions':
                generated_files = PermissionsEngine().process_document(file_path)
                success_msg = "Permissions Log generated successfully"

            elif process_type == 'ppd':
                generated_files = PPDEngine().process_document(file_path, user_username)
                success_msg = "PPD processing completed"
                
            elif process_type == 'technical':
                generated_files = TechnicalEngine().process_document(file_path)
                success_msg = "Technical Editing completed successfully"
                
            elif process_type in ['macro_processing', 'reference_validation', 'reference_number_validation', 
                                  'reference_apa_chicago_validation', 'reference_report_only', 'reference_structuring']:
                
                # Determine flags based on process_type
                run_struct = (process_type == 'reference_structuring')
                run_num = (process_type == 'reference_number_validation')
                run_apa = (process_type == 'reference_apa_chicago_validation')
                report_only = (process_type == 'reference_report_only')
                
                # If general validation or macro_processing, run all (default behavior)
                if process_type in ['reference_validation', 'macro_processing']:
                    run_struct = True
                    run_num = True
                    run_apa = True
                
                # If Report Only is selected, we run validations to get stats/report but flag report_only
                if report_only:
                    run_num = True
                    run_apa = True
                
                generated_files = ReferencesEngine().process_document(
                    file_path,
                    run_structuring=run_struct,
                    run_num_validation=run_num,
                    run_apa_validation=run_apa,
                    report_only=report_only
                )
                success_msg = f"References processing completed ({process_type})"

            elif process_type == 'structuring':
                generated_files = StructuringEngine().process_document(file_path, mode=mode)
                success_msg = f"Structuring completed (mode: {mode})"

            elif process_type == 'bias_scan':
                generated_files = BiasEngine().process_document(file_path)
                success_msg = "Bias Scan completed successfully"

            elif process_type == 'credit_extractor_ai':
                generated_files = AIExtractorEngine().process_document(file_path)
                success_msg = "AI Credit Extraction completed"

            elif process_type == 'word_to_xml':
                generated_files = XMLEngine().process_document(file_path)
                success_msg = "Word to XML conversion completed"

            else:
                # Word macro processing is not supported on Linux
                raise HTTPException(
                    status_code=501,
                    detail=f"Processing type '{process_type}' is not supported. Word macro processing is only available on Windows."
                )

            # 2. Register Generated Files
            if generated_files:
                logger.info(f"Processing generated {len(generated_files)} output files")
                for processed_path in generated_files:
                    p_filename = os.path.basename(processed_path)
                    logger.info(f"Processing output file: {processed_path}, Exists: {os.path.exists(processed_path)}")
                    
                    # We always add new files as outputs for tracking, unless same name exists in same category
                    # but usually these have suffixes like _Dashboard or _PermissionsLog
                    mime = "application/octet-stream"
                    if p_filename.endswith(".html"): mime = "text/html"
                    elif p_filename.endswith(".xlsx") or p_filename.endswith(".xls"): 
                        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    elif p_filename.endswith(".docx"): 
                        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    elif p_filename.endswith(".txt"): 
                        mime = "text/plain"
                    elif p_filename.endswith(".zip"):
                        mime = "application/zip"
                    elif p_filename.endswith(".xml"):
                        mime = "application/xml"
                    
                    new_rec = models.File(
                        filename=p_filename,
                        path=processed_path,
                        file_type=mime,
                        project_id=file_record.project_id,
                        chapter_id=file_record.chapter_id,
                        version=1,
                        category=file_record.category
                    )
                    db.add(new_rec)
                    logger.info(f"Registered result file: {p_filename} to category {file_record.category}")
            else:
                logger.warning(f"No generated files returned from {process_type} processing")
            
            # 3. Unlock (Check-in)
            checkout_lock_service.release_lock(file_record, clear_timestamp=True)
            
            # Update original file meta (it might have been modified in place)
            # Note: uploaded_at remains as the creation timestamp
            
            db.commit()
            logger.info(f"Processing success: {success_msg}")

        except Exception as e:
            logger.error(f"Processing FAILED for file {file_id}: {str(e)}")
            logger.error(traceback.format_exc())
            # Even on error, we unlock the file so it's not stuck
            # But we could also keep it locked for manual inspection
            checkout_lock_service.release_lock(file_record, clear_timestamp=False)
            db.commit()

    finally:
        db.close()

@router.post("/files/{file_id}/process/{process_type}")
async def run_file_process(
    file_id: int, 
    process_type: str,
    background_tasks: BackgroundTasks,
    item: Optional[Dict[str, Any]] = None, # Accept JSON body if sent (for mode etc)
    mode: str = "style", # or query param
    user=Depends(get_current_user_from_cookie), 
    db: Session = Depends(database.get_db)
):
    logger.info(f"Process triggered: {process_type} on file {file_id} by {user.username if user else 'Unknown'}")
    
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    # 1. Permission Check
    check_permission(user, process_type)
    
    # 2. Get File
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_path = os.path.abspath(file_record.path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Physical file missing: {file_path}")

    # 3. Checkout (Locking)
    lock_result = checkout_lock_service.acquire_processing_lock(
        file_record,
        user.id,
        datetime.utcnow(),
    )
    if lock_result.code == "LOCKED_BY_OTHER":
        raise HTTPException(
            status_code=400,
            detail=f"File is locked by {lock_result.owner_username}",
        )
    if lock_result.lock_changed:
        db.commit()

    # 4. Versioning (Auto-backup)
    try:
        version_num = (file_record.version or 1) + 1
        # Use simple structure: data/uploads/{CODE}/{CH}/Archive/filename_v{N}.ext
        # We try to find project code and chapter number
        project = db.query(models.Project).filter(models.Project.id == file_record.project_id).first()
        chapter = db.query(models.Chapter).filter(models.Chapter.id == file_record.chapter_id).first()
        
        if project and chapter:
            backup_dir = os.path.abspath(f"{UPLOAD_DIR}/{project.code}/{chapter.number}/{file_record.category}/Archive")
        else:
            backup_dir = os.path.join(os.path.dirname(file_path), "Archive")
            
        os.makedirs(backup_dir, exist_ok=True)
        
        name_only = file_record.filename.rsplit('.', 1)[0]
        ext = file_record.filename.rsplit('.', 1)[1] if '.' in file_record.filename else ''
        backup_filename = f"{name_only}_v{(file_record.version or 1)}.{ext}"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        shutil.copy2(file_path, backup_path)
        
        # Register Version
        new_version = models.FileVersion(
            file_id=file_record.id,
            version_num=(file_record.version or 1),
            path=backup_path,
            uploaded_by_id=user.id
        )
        db.add(new_version)
        file_record.version = version_num
        db.commit()
        logger.info(f"Auto-backup created: {backup_filename}")
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        # We continue even if backup fails? For now, yes, but log it.

    # 5. Dispatch to Background Task
    background_tasks.add_task(
        background_processing_task,
        file_id=file_id,
        process_type=process_type,
        user_id=user.id,
        user_username=user.username,
        mode=mode
    )

    return JSONResponse(content={
        "message": f"{process_type.capitalize()} started in background. The file is locked and will be updated shortly.",
        "status": "processing"
    })

@router.get("/files/{file_id}/structuring_status")
def check_structuring_status(
    file_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    """
    Check if the structuring process has completed (i.e., if _Processed file exists).
    Returns the ID of the new processed file if found.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Name convention: OriginalName_Processed.docx
    original_name = file_record.filename
    name_only = original_name.rsplit('.', 1)[0]
    ext = original_name.rsplit('.', 1)[1] if '.' in original_name else ''
    processed_name = f"{name_only}_Processed.{ext}"

    # Search for this file in the same project/chapter
    processed_file = db.query(models.File).filter(
        models.File.project_id == file_record.project_id,
        models.File.chapter_id == file_record.chapter_id,
        models.File.filename == processed_name
    ).order_by(models.File.uploaded_at.desc()).first()

    if processed_file:
        return {"status": "completed", "new_file_id": processed_file.id}
    else:
        return {"status": "processing"}

# ---------------------------
# Technical Editing Endpoints
# ---------------------------

@router.get("/files/{file_id}/technical/scan")
def scan_technical_errors(
    file_id: int,
    user=Depends(get_current_user_from_cookie), 
    db: Session = Depends(database.get_db)
):
    """
    Scans the document for technical editing patterns and returns found items.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    check_permission(user, 'technical')
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        logger.error(f"Scan failed: File ID {file_id} not found in DB")
        raise HTTPException(status_code=404, detail="File not found")
        
    file_path = os.path.abspath(file_record.path)
    if not os.path.exists(file_path):
        logger.error(f"Scan failed: Physical file missing at {file_path}")
        raise HTTPException(status_code=404, detail=f"Physical file missing: {file_path}")
        
    try:
        editor = TechnicalEditor()
        results = editor.scan(file_path)
        return results
    except Exception as e:
        logger.error(f"Technical Scan Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/files/{file_id}/technical/apply")
def apply_technical_edits(
    file_id: int,
    replacements: Dict[str, str],
    user=Depends(get_current_user_from_cookie), 
    db: Session = Depends(database.get_db)
):
    """
    Applies selected technical edits with Track Changes.
    replacements: {'xray': 'X-ray', 'percent': '%'}
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    check_permission(user, 'technical')
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_path = os.path.abspath(file_record.path)
    
    # Define output path
    # Name convention: OriginalName_TechEdited.docx
    base = os.path.splitext(file_record.filename)[0]
    ext = os.path.splitext(file_record.filename)[1]
    output_filename = f"{base}_TechEdited{ext}"
    
    # Save in same directory
    output_path = os.path.join(os.path.dirname(file_path), output_filename)
        
    try:
        editor = TechnicalEditor()
        editor.process(file_path, output_path, replacements, author=user.username)
        
        # Register new file
        if os.path.exists(output_path):
            new_rec = models.File(
                filename=output_filename,
                path=output_path,
                file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                project_id=file_record.project_id,
                chapter_id=file_record.chapter_id,
                version=1,
                category=file_record.category
            )
            db.add(new_rec)
            db.commit()
            
            return {"status": "completed", "new_file_id": new_rec.id}
        else:
            raise HTTPException(status_code=500, detail="Output file generation failed")
            
    except Exception as e:
        logger.error(f"Technical Apply Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
