from app.utils.timezone import now_ist_naive
from sqlalchemy.orm import Session
from fastapi import UploadFile
from app import models
import shutil
import os
from datetime import datetime

from app.core.paths import UPLOADS_DIR
UPLOAD_DIR = str(UPLOADS_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_upload_file(upload_file: UploadFile, destination: str):
    try:
        with open(destination, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
    finally:
        upload_file.file.close()

def create_file_record(db: Session, project_id: int, file: UploadFile):
    # Determine local path (mocking S3 for now)
    # Using timestamp to avoid collisions
    timestamp = now_ist_naive().strftime("%Y%m%d%H%M%S")
    filename = f"{project_id}_{timestamp}_{file.filename}"
    path = os.path.join(UPLOAD_DIR, filename)
    
    save_upload_file(file, path)
    
    db_file = models.File(
        project_id=project_id,
        path=path,
        file_type=file.content_type,
        version=1 # Logic for version bumping can be added here
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file
