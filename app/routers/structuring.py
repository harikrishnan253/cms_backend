
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
import os
import logging
from typing import Dict, Any, List

from app import database
from app.auth import get_current_user_from_cookie
from app.models import File, User
from app.processing.structuring_lib.doc_utils import load_document, save_document, extract_document_structure
from app.processing.structuring_lib.styler import process_docx
from app.processing.structuring_lib.rules_loader import get_rules_loader

# Collabora Online base URL (change if running on a different host/port)
# Container is running with ssl.enable=false; use 127.0.0.1 for reliability on Windows
COLLABORA_BASE_URL = os.environ.get("COLLABORA_URL", "http://127.0.0.1:9980")
COLLABORA_PUBLIC_URL = os.environ.get("COLLABORA_PUBLIC_URL", COLLABORA_BASE_URL)
# The public base URL of THIS FastAPI server (so Collabora can reach WOPI endpoints)
WOPI_BASE_URL = os.environ.get("WOPI_BASE_URL", "http://host.docker.internal:8000")

# Configure logger
logger = logging.getLogger("app.routers.structuring")


# Common styles requested for the dropdown
ADDITIONAL_REVIEW_STYLES = [
    "ACK1", "ACKTXT", "ANS-NL-FIRST", "ANS-NL-MID", "APX", "APX-TXT", "APX-TXT-FLUSH", "APXAU", 
    "ΑΡΧΗ1", "ΑΡΧΗ3", "ΑΡΧΝ", "APXST", "APXT", "TXT", "TXT-FLUSH",
    "BIB", "BIBH1", "BIBH2", "BL-FIRST", "BL-LAST", "BL-MID", "BL2-MID", "BL3-MID", "BL4-MID", "BL5-MID", "BL6-MID", 
    "BX1-BL-FIRST", "BX1-BL-LAST", "BX1-BL-MID", "BX1-BL2-MID", "BX1-EXT-ONLY", "BX1-EQ-FIRST", "BX1-EQ-MID", "BX1-EQ-LAST", "BX1-EQ-ONLY", 
    "BX1-FN", "BX1-H1", "BX1-H2", "BX1-H3", "BX1-L1", "BX1-MCUL-FIRST", "BX1-MCUL-LAST", "BX1-MCUL-MID", "BX1-NL-FIRST", "BX1-NL-LAST", "BX1-NL-MID", 
    "BX1-OUT1-FIRST", "BX1-OUT1-MID", "BX1-OUT2", "BX1-OUT2-LAST", "BX1-OUT3", "BX1-QUO", "BX1-QUO-AU", "BX1-TTL", "BX1-TXT", "BX1-TXT-DC", "BX1-TXT-FIRST", "BX1-TYPE", "BX1-UL-FIRST", "BX1-UL-LAST", "BX1-UL-MID", 
    "CAU", "CHAP", "CN", "COQ", "COQA", "COUT-1", "COUT-2", "COUT-BL", "COUTH1", "COUT-NL-FIRST", "COUT-NL-MID", "CPAU", "CPT", "CST", "CT", 
    "DIA-FIRST", "DIA-LAST", "DIA-MID", "EQ-FIRST", "EQ-LAST", "EQ-MID", "EQ-ONLY", "EQN-FIRST", "EQN-LAST", "EQN-MID", "EQN-ONLY", 
    "EXT-FIRST", "EXT-LAST", "EXT-MID", "EXT-ONLY", "FIG-CRED", "FIG-LEG", "FN", 
    "H1", "H2", "H3", "H4", "H5", "H6", 
    "KP1", "KP-BL-FIRST", "KP-BL-LAST", "KP-BL-MID", "KP-NL-FIRST", "KP-NL-LAST", "KP-NL-MID", "KT-BL-FIRST", "KT-NL-FIRST"
]

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

@router.get("/files/{file_id}/structuring/review", response_class=HTMLResponse)
async def review_structuring(
    request: Request,
    file_id: int,
    db: Session = Depends(database.get_db),
    user: User = Depends(get_current_user_from_cookie)
):
    """
    Serve the review interface for a processed file.
    Expects the file to be already processed (name_Processed.docx exists).
    """
    if not user:
        return RedirectResponse(url="/login")

    # Fetch file record
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Determine paths
    original_path = file_record.path
    
    if original_path.endswith('_Processed.docx'):
        processed_path = original_path
        processed_filename = os.path.basename(original_path)
    else:
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        name_only = os.path.splitext(base_name)[0]
        processed_filename = f"{name_only}_Processed.docx"
        processed_path = os.path.join(dir_name, processed_filename)

    if not os.path.exists(processed_path):
        # Fallback to original if processed doesn't exist (or show error)
        # For now, let's show error or redirect to process
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Processed file not found. Please run Structuring process first."
        })

    try:
        # Extract structure for the UI
        # Extract structure for the UI
        structure = extract_document_structure(processed_path)

        # Get available styles from rules
        rules_loader = get_rules_loader()
        # Collect all possible styles from paragraph rules and block headers
        styles = set()
        
        # From paragraph rules
        for rule in rules_loader.get_paragraphs():
            if "style" in rule:
                styles.add(rule["style"])
                
        # From block markers (implicit styles)
        # Add common styles that might not be in regex rules but are used
        styles.add("Normal")
        styles.add("Body Text")
        
        # Add requested detailed styles
        styles.update(ADDITIONAL_REVIEW_STYLES)
        
        # Sort for better UI
        style_list = sorted(list(styles))
        
        # Build Collabora iframe URL
        # We need to ensure the Collabora URL matches the browser's context to avoid CSP issues
        # If user is on localhost, use localhost. If 127.0.0.1, use 127.0.0.1.
        # But Collabora is on a fixed port. We will stick to the configured URL for now.
        
        # WOPI Src *must* be reachable by Collabora container.
        # So WOPI_BASE_URL=http://host.docker.internal:8000 is correct for the container to call back.
        
        import urllib.parse
        # Use specialized /structuring endpoint to edit the _Processed version
        wopi_src = f"{WOPI_BASE_URL}/wopi/files/{file_id}/structuring"
        wopi_src_encoded = urllib.parse.quote(wopi_src, safe="")
        collabora_url = (
            f"{COLLABORA_PUBLIC_URL}/browser/dist/cool.html"
            f"?WOPISrc={wopi_src_encoded}"
            f"&lang=en"
        )

        return templates.TemplateResponse("structuring_review.html", {
            "request": request,
            "file": file_record,
            "filename": processed_filename,
            "collabora_url": collabora_url,
            "user": user
        })
    except Exception as e:
        logger.error(f"Error loading review interface: {e}", exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": f"Error loading document structure: {str(e)}"
        })


@router.post("/files/{file_id}/structuring/save")
async def save_structuring_changes(
    file_id: int,
    changes: Dict[str, Any],
    db: Session = Depends(database.get_db),
    user: User = Depends(get_current_user_from_cookie)
):
    """Apply changes from the review interface."""
    logger.info(f"SAVE ENDPOINT HIT for file {file_id}")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Determine paths
    original_path = file_record.path
    if original_path.endswith('_Processed.docx'):
        processed_path = original_path
        processed_filename = os.path.basename(original_path)
    else:
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        name_only = os.path.splitext(base_name)[0]
        processed_filename = f"{name_only}_Processed.docx"
        processed_path = os.path.join(dir_name, processed_filename)

    if not os.path.exists(processed_path):
         logger.warning(f"Save failed: Processed file not found at {processed_path}")
         raise HTTPException(status_code=404, detail="Processed file not found")

    try:
        # Use util function to apply updates based on ID mapping
        # Frontend sends { changes: { id: style, ... } }
        # Pydantic/FastAPI receives this as changes={ "changes": { ... } }
        modifications = changes.get("changes", {})
        
        # We don't need to load_document here as update_document_structure handles it
        from app.processing.structuring_lib.doc_utils import update_document_structure
        
        success = update_document_structure(processed_path, processed_path, modifications)
        
        if success:
             logger.info(f"Successfully updated structure for {processed_filename}")
             return JSONResponse(content={"status": "success"})
        else:
             raise Exception("update_document_structure returned False")

    except Exception as e:
        logger.error(f"Error saving changes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save changes: {str(e)}")


@router.get("/files/{file_id}/structuring/review/export")
async def export_structuring(
    file_id: int,
    db: Session = Depends(database.get_db),
    user: User = Depends(get_current_user_from_cookie)
):
    """
    Download the processed document.
    """
    from fastapi.responses import FileResponse

    if not user:
        return RedirectResponse(url="/login")

    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Determine paths
    original_path = file_record.path
    if original_path.endswith('_Processed.docx'):
        processed_path = original_path
        processed_filename = os.path.basename(original_path)
    else:
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        name_only = os.path.splitext(base_name)[0]
        processed_filename = f"{name_only}_Processed.docx"
        processed_path = os.path.join(dir_name, processed_filename)

    if not os.path.exists(processed_path):
         logger.warning(f"Export failed: Processed file not found at {processed_path}")
         raise HTTPException(status_code=404, detail="Processed file not found")

    return FileResponse(
        path=processed_path,
        filename=processed_filename,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
