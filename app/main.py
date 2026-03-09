from app.core.paths import ensure_runtime_dirs
ensure_runtime_dirs()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.routers import users, teams, projects, files, web
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.PROJECT_NAME)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# UI Router (Root)
app.include_router(web.router, tags=["Web UI"])

# API Routers
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["Users"])
app.include_router(teams.router, prefix=f"{settings.API_V1_STR}/teams", tags=["Teams"])
app.include_router(projects.router, prefix=f"{settings.API_V1_STR}/projects", tags=["Projects"])
app.include_router(files.router, prefix=f"{settings.API_V1_STR}/files", tags=["Files"])
# Processing Router
from app.routers import processing
app.include_router(processing.router, prefix=f"{settings.API_V1_STR}/processing", tags=["Processing"])
# Structuring (Book Styler) Router
from app.routers import structuring
app.include_router(structuring.router, prefix=f"{settings.API_V1_STR}", tags=["Structuring"])
# WOPI Router (LibreOffice Online / Collabora)
from app.routers import wopi
app.include_router(wopi.router, tags=["WOPI"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Publishing CMS API"}

@app.on_event("startup")
def init_data():
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    try:
        # Define all required roles
        roles = [
            {"name": "Viewer", "description": "Read-only access"},
            {"name": "Editor", "description": "General editing access"},
            {"name": "ProjectManager", "description": "Can manage projects"},
            {"name": "Admin", "description": "Full access"},
            {"name": "Tagger", "description": "Responsible for XML/content tagging"},
            {"name": "CopyEditor", "description": "Reviews and edits manuscripts"},
            {"name": "GraphicDesigner", "description": "Manages art and visual assets"},
            {"name": "Typesetter", "description": "Formats layout for publication"},
            {"name": "QCPerson", "description": "Quality control assurance"},
            {"name": "PPD", "description": "Pre-press and production"},
            {"name": "PermissionsManager", "description": "Manages rights and permissions"}
        ]
        
        for r_data in roles:
            role = db.query(models.Role).filter(models.Role.name == r_data["name"]).first()
            if not role:
                new_role = models.Role(name=r_data["name"], description=r_data["description"])
                db.add(new_role)
        
        db.commit()
    finally:
        db.close()
