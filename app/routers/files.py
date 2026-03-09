from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from app import database
from app.services import file_service
from app.auth import get_current_user

router = APIRouter()

@router.post("/")
def upload_file(
    project_id: int, 
    file: UploadFile = File(...), 
    db: Session = Depends(database.get_db),
    current_user = Depends(get_current_user)
):
    cms_file = file_service.create_file_record(db, project_id, file)
    return {"file_id": cms_file.id, "path": cms_file.path}
