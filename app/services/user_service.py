from sqlalchemy.orm import Session
from app import models, schemas
from app.auth import hash_password

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = hash_password(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def assign_role(db: Session, user_id: int, role_name: str):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    role = db.query(models.Role).filter(models.Role.name == role_name).first()
    if user and role:
        user.roles.append(role)
        db.commit()
    return user
