from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from jose import jwt, JWTError
from datetime import datetime

from app import database, models, schemas
from app.auth import create_access_token, verify_password, hash_password, oauth2_scheme, get_current_user_from_cookie
from app.core.config import get_settings
from app.services import project_service
from app.services.chapter_service import ChapterNotFoundError, ChapterService, ProjectNotFoundError
from app.services.checkout_lock_service import CheckoutLockService
from app.services.file_storage_service import ChapterDirectoryNotFoundError, FileStorageService
from app.services.versioning_service import VersioningService

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
router = APIRouter()
file_storage_service = FileStorageService()
chapter_service = ChapterService(file_storage_service)
checkout_lock_service = CheckoutLockService()
versioning_service = VersioningService(file_storage_service)

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user=Depends(get_current_user_from_cookie)):
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
        
        access_token = create_access_token(data={"sub": user.username})
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
        return response
    except Exception as e:
         return templates.TemplateResponse("login.html", {"request": request, "error": str(e)})

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    try:
        if password != confirm_password:
             return templates.TemplateResponse("register.html", {"request": request, "error": "Passwords do not match"})
        
        # Check existing user
        existing_user = db.query(models.User).filter(
            (models.User.username == username) | (models.User.email == email)
        ).first()
        if existing_user:
             return templates.TemplateResponse("register.html", {"request": request, "error": "Username or email already exists"})

        # Create user
        hashed_pw = hash_password(password)
        new_user = models.User(username=username, email=email, password_hash=hashed_pw, is_active=True)
        
        # Assign default 'Viewer' role if it exists
        # Ensure Roles Exist
        viewer_role = db.query(models.Role).filter(models.Role.name == "Viewer").first()
        admin_role = None
        
        if not viewer_role:
             # Base Roles
             viewer_role = models.Role(name="Viewer", description="Read-only access")
             editor_role = models.Role(name="Editor", description="General editing access")
             manager_role = models.Role(name="ProjectManager", description="Can manage projects")
             admin_role = models.Role(name="Admin", description="Full access")
             
             # Specialized Roles
             tagger_role = models.Role(name="Tagger", description="Responsible for XML/content tagging")
             copyeditor_role = models.Role(name="CopyEditor", description="Reviews and edits manuscripts")
             graphic_role = models.Role(name="GraphicDesigner", description="Manages art and visual assets")
             typesetter_role = models.Role(name="Typesetter", description="Formats layout for publication")
             qc_role = models.Role(name="QCPerson", description="Quality control assurance")
             ppd_role = models.Role(name="PPD", description="Pre-press and production")
             permissions_role = models.Role(name="PermissionsManager", description="Manages rights and permissions")
             
             db.add_all([
                 viewer_role, editor_role, manager_role, admin_role,
                 tagger_role, copyeditor_role, graphic_role, typesetter_role,
                 qc_role, ppd_role, permissions_role
             ])
             db.commit()
             db.refresh(viewer_role)
             db.refresh(admin_role)
        else:
             admin_role = db.query(models.Role).filter(models.Role.name == "Admin").first()
        
        # Determine Role: First user is Admin, others are Viewers
        is_first_user = db.query(models.User).count() == 0
        target_role = admin_role if is_first_user else viewer_role
        
        new_user.roles.append(target_role)
        db.add(new_user)
        db.commit()
        
        return RedirectResponse(url="/login?msg=Registration successful! Please login.", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
         return templates.TemplateResponse("register.html", {"request": request, "error": str(e)})

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, 
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # Fetch projects
    projects = project_service.get_projects(db, skip=0, limit=100)

    # Calculate Dashboard Stats
    total_projects = len(projects)
    
    # In a real app, these would come from DB calculations
    # For now, we move hardcoded values from Template to Controller
    stats = {
        "total_projects": total_projects,
        "on_time_rate": 94, # Placeholder
        "on_time_trend": "+12%",
        "avg_days": 8.5,
        "avg_days_trend": "-2 days",
        "delayed_count": 0,
        "delayed_trend": "0" 
    }

    # Pass user roles to template for permission checks
    user_data = {
        "username": user.username,
        "roles": [r.name for r in user.roles],
        "email": user.email,
        "id": user.id
    }
    
    return templates.TemplateResponse(
        "dashboard.html", 
        {"request": request, "user": user_data, "projects": projects, "dashboard_stats": stats}
    )

@router.get("/projects", response_class=HTMLResponse)
async def projects_list(
    request: Request, 
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    projects = project_service.get_projects(db, skip=0, limit=100)
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "projects.html", 
        {"request": request, "user": user_data, "projects": projects}
    )

@router.get("/projects/create", response_class=HTMLResponse)
async def create_project_page(
    request: Request,
    user=Depends(get_current_user_from_cookie)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "project_create.html",
        {"request": request, "user": user_data}
    )

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user or "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=302)
        
    # Calculate Stats
    total_users = db.query(models.User).count()
    total_files = db.query(models.File).count()
    
    admin_stats = {
        "total_users": total_users,
        "total_files": total_files,
        "total_validations": 0, # Placeholder
        "total_macro": 0 # Placeholder
    }
    
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "user": user_data, "admin_stats": admin_stats}
    )

@router.get("/admin/users/create", response_class=HTMLResponse)
async def admin_create_user_page(
    request: Request,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user or "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    roles = db.query(models.Role).all()
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    
    return templates.TemplateResponse(
        "admin_create_user.html",
        {"request": request, "user": user_data, "roles": roles}
    )

@router.post("/admin/users/create", response_class=HTMLResponse)
async def admin_create_user_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role_id: int = Form(...),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user or "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=302)
        
    try:
        if db.query(models.User).filter((models.User.username == username) | (models.User.email == email)).first():
            raise Exception("Username or Email already exists")
            
        hashed_pw = hash_password(password)
        new_user = models.User(username=username, email=email, password_hash=hashed_pw, is_active=True)
        
        target_role = db.query(models.Role).filter(models.Role.id == role_id).first()
        if target_role:
            new_user.roles.append(target_role)
            
        db.add(new_user)
        db.commit()
        return RedirectResponse(url="/admin/users", status_code=302)
    except Exception as e:
        roles = db.query(models.Role).all()
        user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
        return templates.TemplateResponse(
            "admin_create_user.html",
            {"request": request, "user": user_data, "roles": roles, "error": str(e)}
        )

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # Check if admin
    user_roles = [r.name for r in user.roles]
    if "Admin" not in user_roles:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    users = db.query(models.User).all()
    all_roles = db.query(models.Role).all()
    
    # Pass user_data compatible with base.html
    user_data = {"username": user.username, "roles": user_roles, "email": user.email, "id": user.id}
    
    return templates.TemplateResponse(
        "admin_users.html", 
        {
            "request": request, 
            "user": user_data, 
            "current_user": user, 
            "users": users, 
            "all_roles": all_roles
        }
    )

@router.post("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role_id: int = Form(...),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    new_role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not target_user or not new_role:
        return RedirectResponse(url="/admin/users?msg=Invalid+user+or+role", status_code=status.HTTP_302_FOUND)

    # Prevent removing the last Admin
    admin_role = db.query(models.Role).filter(models.Role.name == 'Admin').first()
    if admin_role:
        # count users who have Admin role
        admin_count = db.query(models.UserRole).filter(models.UserRole.role_id == admin_role.id).count()

        # if the target currently has Admin and new role is not Admin and admin_count == 1 -> block
        target_has_admin = any(r.name == 'Admin' for r in target_user.roles)
        if target_has_admin and new_role.name != 'Admin' and admin_count <= 1:
            # Re-render admin users page with an error message
            users = db.query(models.User).all()
            all_roles = db.query(models.Role).all()
            user_data = {"username": user.username, "roles": [r.name for r in user.roles], "email": user.email, "id": user.id}
            return templates.TemplateResponse(
                "admin_users.html",
                {"request": request, "user": user_data, "current_user": user, "users": users, "all_roles": all_roles, "error": "Cannot remove the last Admin role."}
            )

    # Apply role change
    target_user.roles = [new_role] # Replace existing roles
    db.commit()
    return RedirectResponse(url="/admin/users?msg=Role+Updated", status_code=status.HTTP_302_FOUND)


@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models import User
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin/users?msg=User+not+found", status_code=302)
    if target.username == user.username:
        return RedirectResponse(url="/admin/users?msg=Cannot+delete+yourself", status_code=302)
    db.delete(target)
    db.commit()
    return RedirectResponse(url="/admin/users?msg=User+deleted", status_code=302)

@router.post("/admin/users/{user_id}/status")
async def toggle_user_status(
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if target_user and target_user.id != user.id: # Prevent self-lockout
        target_user.is_active = not target_user.is_active
        db.commit()
        
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@router.get("/admin/stats", response_class=HTMLResponse)
async def admin_stats(
    request: Request,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user or "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    # Calculate Stats
    total_users = db.query(models.User).count()
    total_projects = db.query(models.Project).count()
    total_chapters = db.query(models.Chapter).count()
    total_files = db.query(models.File).count()
    
    # Role Breakdown
    roles = db.query(models.Role).all()
    role_breakdown = {}
    for r in roles:
         count = db.query(models.UserRole).filter(models.UserRole.role_id == r.id).count()
         if count > 0:
             role_breakdown[r.name] = count
            
    stats = {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_chapters": total_chapters,
        "total_files": total_files,
        "role_breakdown": role_breakdown
    }
    
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "admin_stats.html",
        {"request": request, "user": user_data, "stats": stats}
    )

@router.get("/admin/users/{user_id}/password", response_class=HTMLResponse)
async def admin_change_password_page(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user or "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=302)
        
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/admin/users", status_code=302)
        
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "admin_change_password.html",
        {"request": request, "user": user_data, "target_user": target_user}
    )

@router.post("/admin/users/{user_id}/password")
async def admin_change_password_submit(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user or "Admin" not in [r.name for r in user.roles]:
        return RedirectResponse(url="/dashboard", status_code=302)

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if target_user:
        target_user.password_hash = hash_password(new_password)
        db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=302)

from fastapi import UploadFile, File as FastAPIFile

# ... existing imports ...

@router.post("/projects/create_with_files")
async def create_project_with_files(
    request: Request,
    code: str = Form(...),
    title: str = Form(...),
    client_name: str = Form(None),  # Optional client name
    xml_standard: str = Form(...),
    chapter_count: int = Form(...),
    files: list[UploadFile] = FastAPIFile(None),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=302)

    new_project = schemas.ProjectCreate(
        title=title, code=code, xml_standard=xml_standard, team_id=1
    )
    db_project = project_service.create_project(db, new_project)
    
    # Update client_name if provided
    if client_name:
        db_project.client_name = client_name
        db.commit()
        db.refresh(db_project)
    chapter_service.initialize_project_chapters_and_files(db, db_project, chapter_count, files)

    return RedirectResponse(url="/dashboard", status_code=302)

@router.get("/projects/{project_id}", response_class=HTMLResponse)
@router.get("/projects/{project_id}/chapters", response_class=HTMLResponse)
async def project_chapters(
    request: Request,
    project_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")

    try:
        project, processed_chapters = chapter_service.build_chapter_inventory(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404)

    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "project_chapters.html", 
        {"request": request, "project": project, "chapters": processed_chapters, "user": user_data}
    )

@router.post("/projects/{project_id}/chapters/create")
async def create_chapter(
    project_id: int,
    number: str = Form(...),
    title: str = Form(...),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=302)

    try:
        chapter_service.create_chapter(db, project_id, number, title)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")

    return RedirectResponse(
        url=f"/projects/{project_id}?msg=Chapter+Created+Successfully",
        status_code=302
    )

@router.post("/projects/{project_id}/chapter/{chapter_id}/rename")
async def rename_chapter(
    project_id: int,
    chapter_id: int,
    number: str = Form(...),
    title: str = Form(...),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=302)

    try:
        chapter_service.rename_chapter(db, project_id, chapter_id, number, title)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="Chapter or Project not found")

    return RedirectResponse(
        url=f"/projects/{project_id}?msg=Chapter+Renamed+Successfully",
        status_code=302
    )

@router.get("/projects/{project_id}/chapter/{chapter_id}/download")
async def download_chapter_zip(
    project_id: int,
    chapter_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=302)

    try:
        zip_bundle = chapter_service.generate_chapter_zip(db, project_id, chapter_id)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="Chapter or Project not found")
    except ChapterDirectoryNotFoundError:
        raise HTTPException(status_code=404, detail="Chapter directory not found")

    return FileResponse(
        zip_bundle.temp_path,
        media_type='application/zip',
        filename=zip_bundle.filename,
        headers={"Content-Disposition": f"attachment; filename={zip_bundle.filename}"}
    )

@router.post("/projects/{project_id}/chapter/{chapter_id}/delete")
async def delete_chapter(
    project_id: int,
    chapter_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login", status_code=302)

    try:
        chapter_service.delete_chapter(db, project_id, chapter_id)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="Chapter or Project not found")

    return RedirectResponse(
        url=f"/projects/{project_id}?msg=Chapter+Deleted+Successfully",
        status_code=302
    )

@router.get("/projects/{project_id}/chapter/{chapter_id}", response_class=HTMLResponse)
async def chapter_detail(
    request: Request,
    project_id: int,
    chapter_id: int,
    tab: str = "Manuscript",
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
    
    if not chapter or chapter.project_id != project_id:
        raise HTTPException(status_code=404)
        
    files = db.query(models.File).filter(
        models.File.chapter_id == chapter_id
    ).all()
    
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "chapter_detail.html", 
        {"request": request, "project": project, "chapter": chapter, "files": files, "active_tab": tab, "user": user_data}
    )

@router.post("/projects/{project_id}/chapter/{chapter_id}/upload")
async def upload_chapter_files(
    request: Request,
    project_id: int,
    chapter_id: int,
    category: str = Form(...),
    files: list[UploadFile] = FastAPIFile(...),
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
    
    if not project or not chapter:
        raise HTTPException(status_code=404, detail="Project or Chapter not found")

    file_storage_service.ensure_chapter_upload_dir(
        project.code,
        chapter.number,
        category,
    )

    for upload in files:
        if not upload.filename: continue
        
        # Check if file exists
        existing_file = db.query(models.File).filter(
            models.File.chapter_id == chapter_id,
            models.File.category == category,
            models.File.filename == upload.filename
        ).first()

        if existing_file:
            lock_availability = checkout_lock_service.assert_lock_available(existing_file, user.id)
            if lock_availability.locked_by_other:
                continue 

            versioning_service.prepare_overwrite_versioning(
                db,
                existing_file,
                project.code,
                chapter.number,
                category,
                user.id,
            )
            file_storage_service.overwrite_existing_file(existing_file.path, upload)
            versioning_service.increment_file_version(existing_file, datetime.utcnow())
            checkout_lock_service.finalize_overwrite_lock_state(existing_file)
            
        else:
            write_result = file_storage_service.write_new_file(
                project.code,
                chapter.number,
                category,
                upload,
            )
            db_file = models.File(
                project_id=project_id,
                chapter_id=chapter_id,
                filename=upload.filename,
                file_type=write_result.file_type,
                category=category,
                path=write_result.file_path,
                version=1
            )
            db.add(db_file)
    
    db.commit()
    
    # Redirect back to the same tab
    return RedirectResponse(
        url=f"/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=Files+Uploaded+Successfully", 
        status_code=302
    )

@router.get("/projects/files/{file_id}/download")
async def download_file(
    file_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    stream_metadata = file_storage_service.open_file_stream_metadata(
        file_record.path,
        file_record.filename,
    )
    if not stream_metadata.exists:
        raise HTTPException(status_code=404, detail="File not found")

    download_response = file_storage_service.build_download_response_data(
        stream_metadata.path,
        stream_metadata.filename,
        stream_metadata.media_type,
    )
    return FileResponse(
        path=download_response.path, 
        filename=download_response.filename, 
        media_type=download_response.media_type
    )

@router.post("/projects/files/{file_id}/delete")
async def delete_file(
    file_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
        
    # Capture info for redirect before deleting
    project_id = file_record.project_id
    chapter_id = file_record.chapter_id
    category = file_record.category

    delete_result = file_storage_service.delete_file_from_storage(file_record.path)
    if delete_result.error:
        print(f"Error deleting file on disk: {delete_result.error}")

    # Delete from DB
    db.delete(file_record)
    db.commit()
    
    return RedirectResponse(
        url=f"/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=File+Deleted", 
        status_code=302
    )

@router.post("/projects/{project_id}/delete")
async def delete_project(
    project_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project: raise HTTPException(status_code=404)

    file_storage_service.delete_project_tree(project.code, ignore_errors=True)
    project_service.delete_project_ssr(db, project)
    
    return RedirectResponse(url="/dashboard?msg=Book+Deleted", status_code=302)

@router.post("/projects/{project_id}/chapter/{chapter_id}/delete")
async def delete_chapter(
    project_id: int,
    chapter_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")

    try:
        chapter_service.delete_chapter(db, project_id, chapter_id, ignore_errors=True)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404)
    
    return RedirectResponse(url=f"/projects/{project_id}?msg=Chapter+Deleted", status_code=302)

@router.post("/projects/files/{file_id}/checkout")
async def checkout_file(
    file_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record: raise HTTPException(status_code=404)

    lock_result = checkout_lock_service.checkout_file(file_record, user.id, datetime.utcnow())
    if lock_result.code == "LOCKED_BY_OTHER":
        return RedirectResponse(
            url=f"/projects/{file_record.project_id}/chapter/{file_record.chapter_id}?tab={file_record.category}&msg=File+Locked+By+Other", 
            status_code=302
        )

    db.commit()
    
    return RedirectResponse(
        url=f"/projects/{file_record.project_id}/chapter/{file_record.chapter_id}?tab={file_record.category}&msg=File+Checked+Out", 
        status_code=302
    )

@router.post("/projects/files/{file_id}/cancel_checkout")
async def cancel_checkout(
    file_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record: raise HTTPException(status_code=404)

    lock_result = checkout_lock_service.cancel_checkout(file_record, user.id)
    if lock_result.lock_changed:
        db.commit()
        
    return RedirectResponse(
        url=f"/projects/{file_record.project_id}/chapter/{file_record.chapter_id}?tab={file_record.category}&msg=Checkout+Cancelled", 
        status_code=302
    )
    
@router.get("/api/notifications")
async def get_notifications_data(
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie)
):
    if not user:
        return []
    
    # Fetch recent 5 files as notifications
    recent_files = db.query(models.File).order_by(models.File.uploaded_at.desc()).limit(5).all()
    
    data = []
    for f in recent_files:
        # Calculate time ago
        delta = datetime.utcnow() - f.uploaded_at
        if delta.days > 0:
            ago = f"{delta.days}d ago"
        elif delta.seconds > 3600:
            ago = f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            ago = f"{delta.seconds // 60}m ago"
        else:
            ago = "Just now"

        data.append({
            "title": "File Uploaded",
            "desc": f"{f.filename}",
            "time": ago,
            "icon": "fa-file-upload",
            "color": "text-primary"
        })
        
    return data

@router.get("/activities", response_class=HTMLResponse)
async def activities_page(
    request: Request,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    # Fetch recent file activities (uploads, updates)
    recent_files = db.query(models.File).order_by(models.File.uploaded_at.desc()).limit(50).all()
    
    # Fetch recent file versions (processing activities)
    recent_versions = db.query(models.FileVersion).order_by(models.FileVersion.uploaded_at.desc()).limit(50).all()
    
    # Combine and sort activities
    activities = []
    
    for f in recent_files:
        delta = datetime.utcnow() - f.uploaded_at
        if delta.days > 0:
            ago = f"{delta.days}d ago"
        elif delta.seconds > 3600:
            ago = f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            ago = f"{delta.seconds // 60}m ago"
        else:
            ago = "Just now"
        
        # Get project and chapter info
        project = db.query(models.Project).filter(models.Project.id == f.project_id).first()
        chapter = db.query(models.Chapter).filter(models.Chapter.id == f.chapter_id).first();
        
        activities.append({
            "type": "upload",
            "title": "File Uploaded",
            "description": f"{f.filename}",
            "project": project.title if project else "Unknown",
            "chapter": chapter.title if chapter else "Unknown",
            "category": f.category,
            "time": ago,
            "timestamp": f.uploaded_at,
            "icon": "fa-file-upload",
            "color": "text-primary"
        })
    
    for v in recent_versions:
        delta = datetime.utcnow() - v.uploaded_at
        if delta.days > 0:
            ago = f"{delta.days}d ago"
        elif delta.seconds > 3600:
            ago = f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            ago = f"{delta.seconds // 60}m ago"
        else:
            ago = "Just now"
        
        file_record = db.query(models.File).filter(models.File.id == v.file_id).first()
        if file_record:
            project = db.query(models.Project).filter(models.Project.id == file_record.project_id).first()
            chapter = db.query(models.Chapter).filter(models.Chapter.id == file_record.chapter_id).first()
            
            activities.append({
                "type": "version",
                "title": "File Processed",
                "description": f"{file_record.filename} (v{v.version_num})",
                "project": project.title if project else "Unknown",
                "chapter": chapter.title if chapter else "Unknown",
                "category": file_record.category,
                "time": ago,
                "timestamp": v.uploaded_at,
                "icon": "fa-cogs",
                "color": "text-success"
            })
    
    # Sort by timestamp (most recent first)
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Calculate today's activities (within last 24 hours)
    from datetime import timedelta
    today_cutoff = datetime.utcnow() - timedelta(days=1)
    today_count = sum(1 for a in activities if a["timestamp"] > today_cutoff)
    
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    return templates.TemplateResponse(
        "activities.html",
        {"request": request, "user": user_data, "activities": activities, "today_count": today_count}
    )

@router.get("/files/{file_id}/technical/edit", response_class=HTMLResponse)
async def technical_editor_page(
    request: Request,
    file_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user: return RedirectResponse(url="/login")
    
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
        
    user_data = {"username": user.username, "roles": [r.name for r in user.roles], "id": user.id}
    
    return templates.TemplateResponse(
        "technical_editor_form.html",
        {"request": request, "file": file_record, "user": user_data}
    )


@router.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
async def admin_edit_user_page(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models import User, Role
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    roles = db.query(Role).all()
    return templates.TemplateResponse("admin_edit_user.html", {
        "request": request, "user": user, "target": target, "roles": roles
    })


@router.post("/admin/users/{user_id}/edit")
async def admin_edit_user(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models import User, Role
    form = await request.form()
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if form.get("email"):
        target.email = form["email"]
    db.commit()
    return RedirectResponse(url="/admin/users?msg=User+updated", status_code=302)


@router.get("/admin/users/{user_id}/password", response_class=HTMLResponse)
async def admin_change_password_page(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models import User
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    return templates.TemplateResponse("admin_change_password.html", {
        "request": request, "user": user, "target": target
    })


@router.post("/admin/users/{user_id}/password")
async def admin_change_password(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models import User
    from app.auth import hash_password
    form = await request.form()
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_password = form.get("new_password", "")
    if len(new_password) < 6:
        return templates.TemplateResponse("admin_change_password.html", {
            "request": request, "user": user, "target": target,
            "error": "Password must be at least 6 characters"
        })
    target.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse(url="/admin/users?msg=Password+changed", status_code=302)


@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    request: Request,
    user_id: int,
    user=Depends(get_current_user_from_cookie),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models import User
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin/users?msg=User+not+found", status_code=302)
    if target.username == user.username:
        return RedirectResponse(url="/admin/users?msg=Cannot+delete+yourself", status_code=302)
    db.delete(target)
    db.commit()
    return RedirectResponse(url="/admin/users?msg=User+deleted", status_code=302)
