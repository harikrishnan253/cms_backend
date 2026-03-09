"""
WOPI (Web Application Open Platform Interface) endpoints for LibreOffice Online / Collabora.

Endpoints:
  GET  /wopi/files/{file_id}           → CheckFileInfo
  GET  /wopi/files/{file_id}/contents  → GetFile (serve bytes)
  POST /wopi/files/{file_id}/contents  → PutFile (save bytes back)
"""

import os
import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import database
from app.auth import get_current_user_from_cookie
from app.models import File, User
from fastapi.templating import Jinja2Templates
from app.routers.structuring import COLLABORA_BASE_URL, COLLABORA_PUBLIC_URL, WOPI_BASE_URL

logger = logging.getLogger("app.routers.wopi")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def _get_target_path(file_record: File, mode: str = "original"):
    """
    Return the path to edit based on mode.
    mode='original': Edit the file at file_record.path
    mode='structuring': Edit the _Processed.docx version
    """
    original_path = file_record.path
    
    if mode == "structuring":
        # Force _Processed.docx
        if original_path.endswith("_Processed.docx"):
            return original_path, os.path.basename(original_path)
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        name_only = os.path.splitext(base_name)[0]
        processed_filename = f"{name_only}_Processed.docx"
        processed_path = os.path.join(dir_name, processed_filename)
        return processed_path, processed_filename
    
    # Default: Edit the exact file record
    return original_path, os.path.basename(original_path)


# ---------------------------------------------------------------------------
# Generic Editor UI
# ---------------------------------------------------------------------------
@router.get("/files/{file_id}/edit")
async def edit_file_page(
    request: Request,
    file_id: int,
    db: Session = Depends(database.get_db),
    user: User = Depends(get_current_user_from_cookie)
):
    """
    Generic Collabora Editor page for any file.
    """
    if not user: return RedirectResponse(url="/login")
    
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Build Collabora URL
    import urllib.parse
    # Standard WOPI route (not structuring)
    wopi_src = f"{WOPI_BASE_URL}/wopi/files/{file_id}"
    wopi_src_encoded = urllib.parse.quote(wopi_src, safe="")
    collabora_url = (
        f"{COLLABORA_PUBLIC_URL}/browser/dist/cool.html"
        f"?WOPISrc={wopi_src_encoded}"
        f"&lang=en"
    )
    

    return templates.TemplateResponse("editor.html", {
        "request": request,
        "file": file_record,
        "filename": os.path.basename(file_record.path),
        "collabora_url": collabora_url,
        "user": user
    })





# ---------------------------------------------------------------------------
# CheckFileInfo
# ---------------------------------------------------------------------------
@router.get("/wopi/files/{file_id}")
async def wopi_check_file_info(
    file_id: int,
    db: Session = Depends(database.get_db),
):
    """
    WOPI CheckFileInfo – returns metadata about the file.
    Collabora calls this first to learn about the file.
    """
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Standard mode: Edit original
    file_path, filename = _get_target_path(file_record, mode="original")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    stat = os.stat(file_path)
    size = stat.st_size
    mtime = datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Compute SHA-256 for version token
    with open(file_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    return JSONResponse({
        "BaseFileName": filename,
        "Size": size,
        "LastModifiedTime": mtime,
        "Version": sha[:16],
        "OwnerId": str(file_record.project_id or "cms"),
        "UserId": "cms-user",
        "UserFriendlyName": "CMS User",
        "UserCanWrite": True,
        "UserCanNotWriteRelative": True,
        "SupportsUpdate": True,
        "SupportsLocks": False,
        "DisableExport": False,
        "DisablePrint": False,
        "HideSaveOption": False,
    })


# ---------------------------------------------------------------------------
# GetFile
# ---------------------------------------------------------------------------
@router.get("/wopi/files/{file_id}/contents")
async def wopi_get_file(
    file_id: int,
    db: Session = Depends(database.get_db),
):
    """
    WOPI GetFile – serve the raw .docx bytes to Collabora.
    """
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    file_path, filename = _get_target_path(file_record, mode="original")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/wopi/files/{file_id}/contents")
async def wopi_put_file(
    file_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
):
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    file_path, filename = _get_target_path(file_record, mode="original")

    body = await request.body()
    if not body:
        return Response(status_code=200)

    try:
        with open(file_path, "wb") as f:
            f.write(body)
        logger.info(f"WOPI PutFile: saved {filename} ({len(body)} bytes)")
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"WOPI PutFile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Structuring Mode WOPI Endpoints (Prefix: /structuring)
# ---------------------------------------------------------------------------

@router.get("/wopi/files/{file_id}/structuring")
async def wopi_check_file_info_structuring(file_id: int, db: Session = Depends(database.get_db)):
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record: raise HTTPException(status_code=404)
    
    file_path, filename = _get_target_path(file_record, mode="structuring")
    if not os.path.exists(file_path): raise HTTPException(status_code=404)

    stat = os.stat(file_path)
    with open(file_path, "rb") as f: sha = hashlib.sha256(f.read()).hexdigest()

    return JSONResponse({
        "BaseFileName": filename,
        "Size": stat.st_size,
        "LastModifiedTime": datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": sha[:16],
        "OwnerId": str(file_record.project_id or "cms"),
        "UserId": "cms-user",
        "UserFriendlyName": "CMS User",
        "UserCanWrite": True,
        "SupportsUpdate": True,
    })

@router.get("/wopi/files/{file_id}/structuring/contents")
async def wopi_get_file_structuring(file_id: int, db: Session = Depends(database.get_db)):
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record: raise HTTPException(status_code=404)
    
    file_path, filename = _get_target_path(file_record, mode="structuring")
    if not os.path.exists(file_path): raise HTTPException(status_code=404)

    return FileResponse(path=file_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@router.post("/wopi/files/{file_id}/structuring/contents")
async def wopi_put_file_structuring(file_id: int, request: Request, db: Session = Depends(database.get_db)):
    file_record = db.query(File).filter(File.id == file_id).first()
    if not file_record: raise HTTPException(status_code=404)
    
    file_path, filename = _get_target_path(file_record, mode="structuring")
    
    body = await request.body()
    if not body: return Response(status_code=200)

    try:
        with open(file_path, "wb") as f: f.write(body)
        logger.info(f"WOPI PutFile (Structuring): saved {filename}")
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
