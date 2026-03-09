from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from app import schemas, database
from app.services import user_service
from app.auth import create_access_token, verify_password, get_current_user

router = APIRouter()

@router.post("/", response_model=dict)
def create_user(data: schemas.UserCreate, db: Session = Depends(database.get_db)):
    existing = user_service.get_user_by_username(db, data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    user = user_service.create_user(db, data)
    return {"id": user.id, "username": user.username}

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = user_service.get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
def read_users_me(current_user = Depends(get_current_user)):
    return {"username": current_user.username, "email": current_user.email, "roles": [r.name for r in current_user.roles]}
