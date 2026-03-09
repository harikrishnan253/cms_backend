from sqlalchemy.orm import Session
from app import models, schemas

def create_team(db: Session, team: schemas.TeamCreate, owner_id: int):
    # Check if team name exists
    existing = db.query(models.Team).filter(models.Team.name == team.name).first()
    if existing:
        raise ValueError("Team name already exists")
    
    db_team = models.Team(
        name=team.name,
        description=team.description,
        owner_id=owner_id
    )
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    return db_team

def get_teams(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Team).offset(skip).limit(limit).all()
