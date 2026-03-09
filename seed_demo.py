from app.database import SessionLocal
from app.models import Project, Chapter, File
from app.services import project_service

def seed_demo_data():
    db = SessionLocal()
    try:
        # Create Project (Book)
        project = db.query(Project).filter(Project.code == "B001").first()
        if not project:
            print("Creating Demo Book...")
            project = Project(title="Advanced AI Algorithms", code="B001", xml_standard="JATS", team_id=1, status="PROCESSING")
            db.add(project)
            db.commit()
            db.refresh(project)

        # Create Chapters
        chapters_data = ["01", "02", "03", "04", "05", "06", "07", "08"]
        for ch_num in chapters_data:
            existing = db.query(Chapter).filter(Chapter.project_id == project.id, Chapter.number == ch_num).first()
            if not existing:
                print(f"Adding Chapter {ch_num}")
                chapter = Chapter(project_id=project.id, number=ch_num, title=f"Chapter {ch_num}")
                db.add(chapter)
                db.commit()
                
                # Add dummy files
                cats = ["Manuscript", "Art", "InDesign"]
                for cat in cats:
                    f = File(
                        project_id=project.id, 
                        chapter_id=chapter.id, 
                        filename=f"CH{ch_num}_{cat}.docx", 
                        file_type="test", 
                        category=cat
                    )
                    db.add(f)
        
        db.commit()
        print("Demo data seeded.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo_data()
