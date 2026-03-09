from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import database, schemas
from app.services import team_service
from app.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.TeamCreate) # Ideally response schema should be different (TeamOut)
def create_team(
    data: schemas.TeamCreate, 
    db: Session = Depends(database.get_db),
    current_user = Depends(get_current_user)
):
    try:
        # Assuming the creator is the owner
        return team_service.create_team(db, data, owner_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/")
def read_teams(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(database.get_db),
    current_user = Depends(get_current_user)
):
    return team_service.get_teams(db, skip=skip, limit=limit)
