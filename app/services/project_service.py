from sqlalchemy.orm import Session
from app import models, schemas

def create_project(db: Session, project: schemas.ProjectCreate):
    db_project = models.Project(**project.dict(), status="RECEIVED")
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def update_project_status(db: Session, project_id: int, status: str):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project:
        project.status = status
        db.commit()
        db.refresh(project)
    return project

def get_projects(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Project).offset(skip).limit(limit).all()

def delete_project(db, project_id: int):
    from app.models import Project, Chapter, File
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    # Delete in correct order respecting foreign keys
    for chapter in db.query(Chapter).filter(Chapter.project_id == project_id).all():
        for file in db.query(File).filter(File.chapter_id == chapter.id).all():
            db.execute(db.bind.connect().execution_options(autocommit=True) if False else __import__('sqlalchemy').text("DELETE FROM file_versions WHERE file_id = :fid"), {"fid": file.id})
            db.execute(__import__('sqlalchemy').text("DELETE FROM processing_results WHERE file_id = :fid"), {"fid": file.id})
        db.query(File).filter(File.chapter_id == chapter.id).delete()
    db.query(Chapter).filter(Chapter.project_id == project_id).delete()
    db.delete(project)
    db.commit()
    return True


def delete_project_v2(db, project_id: int):
    from app.models import Project, Chapter, File
    from sqlalchemy import text
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    for chapter in db.query(Chapter).filter(Chapter.project_id == project_id).all():
        for file in db.query(File).filter(File.chapter_id == chapter.id).all():
            db.execute(text("DELETE FROM file_versions WHERE file_id = :fid"), {"fid": file.id})
            db.delete(file)
        db.flush()
        db.delete(chapter)
    db.flush()
    db.delete(project)
    db.commit()
    return True


def delete_project_ssr(db: Session, project: models.Project):
    db.delete(project)
    db.commit()
    return True
