import os
import tempfile
import zipfile
from datetime import datetime
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File as FastAPIFile, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app import database, models, schemas_v2
from app.auth import get_current_user_from_cookie
from app.core.config import get_settings
from app.services import (
    activity_service,
    admin_user_service,
    auth_service,
    chapter_service,
    checkout_service,
    dashboard_service,
    file_service,
    notification_service,
    project_service,
    project_read_service,
    processing_service,
    session_service,
    structuring_review_service,
    technical_editor_service,
    version_service,
)
from app.utils.timezone import now_ist_naive
from app.utils.inject_styles import inject_publisher_styles
from app.processing.ppd_engine import PPDEngine
from app.processing.permissions_engine import PermissionsEngine
from app.processing.technical_engine import TechnicalEngine
from app.processing.legacy.highlighter.technical_editor import TechnicalEditor
from app.processing.references_engine import ReferencesEngine
from app.processing.structuring_engine import StructuringEngine
from app.processing.bias_engine import BiasEngine
from app.processing.ai_extractor_engine import AIExtractorEngine
from app.processing.xml_engine import XMLEngine
from app.processing.structuring_lib.doc_utils import extract_document_structure, update_document_structure
from app.processing.structuring_lib.rules_loader import get_rules_loader
from app.integrations.collabora.config import COLLABORA_PUBLIC_URL, WOPI_BASE_URL
from app.integrations.wopi import service as wopi_service

settings = get_settings()
router = APIRouter()
logger = logging.getLogger("app.processing")
logger.setLevel(logging.INFO)

_STANDARD_FILE_ACTIONS = ["download", "delete", "edit", "technical_edit"]


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    field_errors: dict[str, str] | None = None,
    details: dict[str, str | int | float | bool | None] | None = None,
):
    payload = schemas_v2.ErrorResponse(
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _strip_bearer_prefix(token_value: str | None):
    if not token_value:
        return None
    normalized = token_value.strip().strip('"')
    scheme, _, param = normalized.partition(" ")
    if scheme.lower() == "bearer" and param:
        return param
    return normalized


def _decode_token_payload(token: str | None):
    if not token:
        return None
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def _resolve_session(request: Request, db: Session):
    cookie_payload = _decode_token_payload(
        _strip_bearer_prefix(request.cookies.get(session_service.ACCESS_TOKEN_COOKIE_NAME))
    )
    if cookie_payload:
        username = cookie_payload.get("sub")
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            return user, "cookie", cookie_payload.get("exp")

    authorization = request.headers.get("Authorization")
    scheme, _, param = authorization.partition(" ") if authorization else ("", "", "")
    if authorization and scheme.lower() == "bearer" and param:
        bearer_payload = _decode_token_payload(param)
        if bearer_payload:
            username = bearer_payload.get("sub")
            user = db.query(models.User).filter(models.User.username == username).first()
            if user:
                return user, "bearer", bearer_payload.get("exp")

    return None, None, None


def _require_cookie_user(user):
    if user:
        return user
    return None


def _has_admin_role(user: models.User):
    return "Admin" in [role.name for role in user.roles]


def _serialize_admin_role(role: models.Role):
    return schemas_v2.AdminRole(id=role.id, name=role.name, description=role.description)


def _serialize_admin_user(user: models.User):
    return schemas_v2.AdminUser(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        roles=[schemas_v2.AdminUserRole(id=role.id, name=role.name) for role in user.roles],
    )


def _serialize_viewer(user: models.User):
    return schemas_v2.Viewer(
        id=user.id,
        username=user.username,
        email=user.email,
        roles=[role.name for role in user.roles],
        is_active=user.is_active,
    )


def _serialize_project_summary(project: models.Project):
    return schemas_v2.ProjectSummary(
        id=project.id,
        code=project.code,
        title=project.title,
        client_name=project.client_name,
        xml_standard=project.xml_standard,
        status=project.status,
        team_id=project.team_id,
        chapter_count=len(project.chapters),
        file_count=len(project.files),
    )


def _serialize_chapter_summary(chapter: models.Chapter):
    has_art = bool(getattr(chapter, "has_art", any(file.category == "Art" for file in chapter.files)))
    has_ms = bool(getattr(chapter, "has_ms", any(file.category == "Manuscript" for file in chapter.files)))
    has_ind = bool(getattr(chapter, "has_ind", any(file.category == "InDesign" for file in chapter.files)))
    has_proof = bool(
        getattr(chapter, "has_proof", any(file.category == "Proof" for file in chapter.files))
    )
    has_xml = bool(getattr(chapter, "has_xml", any(file.category == "XML" for file in chapter.files)))
    return schemas_v2.ChapterSummary(
        id=chapter.id,
        project_id=chapter.project_id,
        number=chapter.number,
        title=chapter.title,
        has_art=has_art,
        has_manuscript=has_ms,
        has_indesign=has_ind,
        has_proof=has_proof,
        has_xml=has_xml,
    )


def _serialize_lock(file_record: models.File):
    checked_out_by_username = None
    if file_record.checked_out_by is not None:
        checked_out_by_username = file_record.checked_out_by.username
    return schemas_v2.LockState(
        is_checked_out=file_record.is_checked_out,
        checked_out_by_id=file_record.checked_out_by_id,
        checked_out_by_username=checked_out_by_username,
        checked_out_at=file_record.checked_out_at,
    )


def _serialize_file_record(file_record: models.File, *, viewer: models.User):
    actions = list(_STANDARD_FILE_ACTIONS)
    if file_record.is_checked_out:
        if file_record.checked_out_by_id == viewer.id:
            actions.append("cancel_checkout")
    else:
        actions.append("checkout")
    return schemas_v2.FileRecord(
        id=file_record.id,
        project_id=file_record.project_id,
        chapter_id=file_record.chapter_id,
        filename=file_record.filename,
        file_type=file_record.file_type,
        category=file_record.category,
        uploaded_at=file_record.uploaded_at,
        version=file_record.version,
        lock=_serialize_lock(file_record),
        available_actions=actions,
    )


def _build_category_counts(files: list[models.File]):
    counts = {
        "Art": 0,
        "Manuscript": 0,
        "InDesign": 0,
        "Proof": 0,
        "XML": 0,
        "Miscellaneous": 0,
    }
    for file_record in files:
        if file_record.category in counts:
            counts[file_record.category] += 1
        else:
            counts["Miscellaneous"] += 1
    return schemas_v2.ChapterCategoryCounts(**counts)


def _serialize_chapter_detail(chapter: models.Chapter, files: list[models.File]):
    summary = _serialize_chapter_summary(chapter)
    return schemas_v2.ChapterDetail(
        **summary.model_dump(),
        category_counts=_build_category_counts(files),
    )


def _exp_to_datetime(exp_value):
    if exp_value is None:
        return None
    try:
        return datetime.utcfromtimestamp(exp_value)
    except (TypeError, ValueError, OSError):
        return None


def _build_chapter_tab_redirect(file_record: models.File, message: str):
    return (
        f"/projects/{file_record.project_id}/chapter/{file_record.chapter_id}"
        f"?tab={file_record.category}&msg={message}"
    )


def _build_structuring_return_action(file_record: models.File):
    if file_record.project_id and file_record.chapter_id:
        return {
            "return_href": f"/projects/{file_record.project_id}/chapter/{file_record.chapter_id}?tab=Manuscript",
            "return_mode": "route",
        }
    if file_record.project_id:
        return {
            "return_href": f"/projects/{file_record.project_id}",
            "return_mode": "route",
        }
    return {"return_href": None, "return_mode": "history"}


def _serialize_upload_result(upload_result: dict, *, viewer: models.User):
    archive_entry = upload_result.get("archive_entry")
    archive_path = archive_entry.path if archive_entry else None
    archived_version_num = archive_entry.version_num if archive_entry else None
    return schemas_v2.UploadResultItem(
        file=_serialize_file_record(upload_result["file"], viewer=viewer),
        operation=upload_result["operation"],
        archive_path=archive_path,
        archived_version_num=archived_version_num,
    )


def _serialize_version_record(version_entry: models.FileVersion):
    return schemas_v2.VersionRecord(
        id=version_entry.id,
        file_id=version_entry.file_id,
        version_num=version_entry.version_num,
        archived_filename=version_service.get_archived_filename(version_entry),
        archived_path=version_entry.path,
        uploaded_at=version_entry.uploaded_at,
        uploaded_by_id=version_entry.uploaded_by_id,
    )


def _processing_check_permission(user, process_type: str):
    return processing_service.check_permission(user, process_type, logger=logger)


def _api_v2_background_processing_task(
    file_id: int,
    process_type: str,
    user_id: int,
    user_username: str,
    mode: str = "style",
):
    return processing_service.background_processing_task(
        file_id=file_id,
        process_type=process_type,
        user_id=user_id,
        user_username=user_username,
        mode=mode,
        logger=logger,
        inject_publisher_styles_func=inject_publisher_styles,
        permissions_engine_cls=PermissionsEngine,
        ppd_engine_cls=PPDEngine,
        technical_engine_cls=TechnicalEngine,
        references_engine_cls=ReferencesEngine,
        structuring_engine_cls=StructuringEngine,
        bias_engine_cls=BiasEngine,
        ai_extractor_engine_cls=AIExtractorEngine,
        xml_engine_cls=XMLEngine,
    )


def _serialize_technical_issue(key: str, issue_data: dict[str, Any]):
    return schemas_v2.TechnicalIssue(
        key=key,
        label=issue_data.get("label", key),
        category=issue_data.get("category"),
        count=issue_data.get("count", 0),
        found=list(issue_data.get("found", [])),
        options=list(issue_data.get("options", [])),
    )


@router.post("/session/login", response_model=schemas_v2.SessionLoginResponse)
def api_v2_session_login(
    payload: schemas_v2.SessionLoginRequest,
    db: Session = Depends(database.get_db),
):
    try:
        auth_result = auth_service.authenticate_browser_user(db, payload.username, payload.password)
    except ValueError as exc:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message=str(exc),
        )

    redirect_to = payload.redirect_to or "/dashboard"
    response_payload = schemas_v2.SessionLoginResponse(
        session=schemas_v2.SessionState(
            authenticated=True,
            auth_mode="cookie",
            expires_at=_exp_to_datetime(
                _decode_token_payload(auth_result["access_token"]).get("exp")
                if _decode_token_payload(auth_result["access_token"])
                else None
            ),
        ),
        viewer=_serialize_viewer(auth_result["user"]),
        redirect_to=redirect_to,
    )
    response = JSONResponse(status_code=status.HTTP_200_OK, content=response_payload.model_dump(mode="json"))
    session_service.set_access_token_cookie(response, auth_result["access_token"])
    return response


@router.post("/session/register", response_model=schemas_v2.SessionRegisterResponse)
def api_v2_session_register(
    payload: schemas_v2.SessionRegisterRequest,
    db: Session = Depends(database.get_db),
):
    try:
        registered_user = auth_service.register_browser_user(
            db,
            username=payload.username,
            email=payload.email,
            password=payload.password,
            confirm_password=payload.confirm_password,
        )
    except ValueError as exc:
        message = str(exc)
        code = "REGISTRATION_FAILED"
        field_errors = None
        if message == "Passwords do not match":
            code = "PASSWORD_MISMATCH"
            field_errors = {"confirm_password": message}
        elif message == "Username or email already exists":
            code = "DUPLICATE_USER"
            field_errors = {
                "username": message,
                "email": message,
            }
        return _error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=code,
            message=message,
            field_errors=field_errors,
        )

    return schemas_v2.SessionRegisterResponse(
        user=_serialize_viewer(registered_user),
        redirect_to=payload.redirect_to or "/ui/login",
    )


@router.get("/session", response_model=schemas_v2.SessionGetResponse)
def api_v2_get_session(
    request: Request,
    db: Session = Depends(database.get_db),
):
    user, auth_mode, exp_value = _resolve_session(request, db)
    if not user:
        return schemas_v2.SessionGetResponse(
            authenticated=False,
            viewer=None,
            auth=schemas_v2.SessionAuth(mode=None, expires_at=None),
        )

    return schemas_v2.SessionGetResponse(
        authenticated=True,
        viewer=_serialize_viewer(user),
        auth=schemas_v2.SessionAuth(mode=auth_mode, expires_at=_exp_to_datetime(exp_value)),
    )


@router.delete("/session", response_model=schemas_v2.SessionDeleteResponse)
def api_v2_delete_session():
    payload = schemas_v2.SessionDeleteResponse(redirect_to="/login")
    response = JSONResponse(status_code=status.HTTP_200_OK, content=payload.model_dump(mode="json"))
    session_service.clear_access_token_cookie(response)
    return response


@router.get("/dashboard", response_model=schemas_v2.DashboardResponse)
def api_v2_dashboard(
    include_projects: bool = True,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    page_data = dashboard_service.get_dashboard_page_data(db, skip=0, limit=100)
    projects = [_serialize_project_summary(project) for project in page_data["projects"]] if include_projects else []
    return schemas_v2.DashboardResponse(
        viewer=_serialize_viewer(viewer),
        stats=schemas_v2.DashboardStats(**page_data["dashboard_stats"]),
        projects=projects,
    )


@router.get("/projects", response_model=schemas_v2.ProjectsListResponse)
def api_v2_projects(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    page_data = project_read_service.get_projects_page_data(db, skip=offset, limit=limit)
    total = db.query(models.Project).count()
    return schemas_v2.ProjectsListResponse(
        projects=[_serialize_project_summary(project) for project in page_data["projects"]],
        pagination=schemas_v2.ProjectsPagination(offset=offset, limit=limit, total=total),
    )


@router.get("/projects/{project_id}", response_model=schemas_v2.ProjectDetailResponse)
def api_v2_project_detail(
    project_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    page_data = project_read_service.get_project_chapters_page_data(db, project_id)
    project = page_data["project"]
    if not project:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PROJECT_NOT_FOUND",
            message="Project not found.",
        )

    project_summary = _serialize_project_summary(project)
    return schemas_v2.ProjectDetailResponse(
        project=schemas_v2.ProjectDetail(
            **project_summary.model_dump(),
            chapters=[_serialize_chapter_summary(chapter) for chapter in page_data["chapters"]],
        )
    )


@router.get("/projects/{project_id}/chapters", response_model=schemas_v2.ProjectChaptersResponse)
def api_v2_project_chapters(
    project_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    page_data = project_read_service.get_project_chapters_page_data(db, project_id)
    project = page_data["project"]
    if not project:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PROJECT_NOT_FOUND",
            message="Project not found.",
        )

    return schemas_v2.ProjectChaptersResponse(
        project=_serialize_project_summary(project),
        chapters=[_serialize_chapter_summary(chapter) for chapter in page_data["chapters"]],
    )


@router.get(
    "/projects/{project_id}/chapters/{chapter_id}",
    response_model=schemas_v2.ChapterDetailResponse,
)
def api_v2_chapter_detail(
    project_id: int,
    chapter_id: int,
    tab: str = "Manuscript",
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    page_data = project_read_service.get_chapter_detail_page_data(db, project_id, chapter_id)
    project = page_data["project"]
    chapter = page_data["chapter"]
    if not chapter or chapter.project_id != project_id or not project:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHAPTER_NOT_FOUND",
            message="Chapter not found.",
        )

    return schemas_v2.ChapterDetailResponse(
        project=_serialize_project_summary(project),
        chapter=_serialize_chapter_detail(chapter, page_data["files"]),
        active_tab=tab,
        viewer=_serialize_viewer(viewer),
    )


@router.get(
    "/projects/{project_id}/chapters/{chapter_id}/files",
    response_model=schemas_v2.ChapterFilesResponse,
)
def api_v2_chapter_files(
    project_id: int,
    chapter_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    page_data = project_read_service.get_chapter_detail_page_data(db, project_id, chapter_id)
    project = page_data["project"]
    chapter = page_data["chapter"]
    if not chapter or chapter.project_id != project_id or not project:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHAPTER_NOT_FOUND",
            message="Chapter not found.",
        )

    files = db.query(models.File).filter(models.File.chapter_id == chapter_id).all()
    return schemas_v2.ChapterFilesResponse(
        project=_serialize_project_summary(project),
        chapter=_serialize_chapter_detail(chapter, files),
        files=[_serialize_file_record(file_record, viewer=viewer) for file_record in files],
        viewer=_serialize_viewer(viewer),
    )


@router.get("/notifications", response_model=schemas_v2.NotificationsResponse)
def api_v2_notifications(
    limit: int = Query(5, ge=1),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    recent_files = db.query(models.File).order_by(models.File.uploaded_at.desc()).limit(limit).all()
    notifications = [
        schemas_v2.NotificationItem(
            id=f"file:{file_record.id}:upload",
            type="file_upload",
            title="File Uploaded",
            description=file_record.filename,
            relative_time=notification_service._format_relative_time(file_record.uploaded_at),
            icon="fa-file-upload",
            color="text-primary",
            file_id=file_record.id,
            project_id=file_record.project_id,
            chapter_id=file_record.chapter_id,
        )
        for file_record in recent_files
    ]
    return schemas_v2.NotificationsResponse(
        notifications=notifications,
        refreshed_at=now_ist_naive(),
    )


@router.get("/activities", response_model=schemas_v2.ActivitiesResponse)
def api_v2_activities(
    limit: int = Query(50, ge=1),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    activities, today_count = activity_service.get_recent_activities(db, file_limit=limit, version_limit=limit)
    activity_items = [
        schemas_v2.ActivityItem(
            id=f"activity:{activity['type']}:{index}",
            type=activity["type"],
            title=activity["title"],
            description=activity["description"],
            project=schemas_v2.ActivityEntityRef(title=activity["project"]),
            chapter=schemas_v2.ActivityEntityRef(title=activity["chapter"]),
            category=activity["category"],
            timestamp=activity["timestamp"],
            relative_time=activity["time"],
            icon=activity["icon"],
            color=activity["color"],
        )
        for index, activity in enumerate(activities[:limit], start=1)
    ]
    return schemas_v2.ActivitiesResponse(
        summary=schemas_v2.ActivitiesSummary(total=len(activity_items), today=today_count),
        activities=activity_items,
    )


@router.post("/projects/bootstrap", response_model=schemas_v2.ProjectBootstrapResponse)
def api_v2_project_bootstrap(
    code: str = Form(...),
    title: str = Form(...),
    client_name: str | None = Form(None),
    xml_standard: str = Form(...),
    chapter_count: int = Form(...),
    files: list[UploadFile] | None = FastAPIFile(None),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    try:
        project = project_service.create_project_with_initial_files(
            db,
            code=code,
            title=title,
            client_name=client_name,
            xml_standard=xml_standard,
            chapter_count=chapter_count,
            files=files,
            upload_dir=file_service.UPLOAD_DIR,
        )
    except project_service.ProjectBootstrapValidationError as exc:
        return _error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="PROJECT_BOOTSTRAP_VALIDATION_ERROR",
            message=str(exc),
        )

    chapters = (
        db.query(models.Chapter)
        .filter(models.Chapter.project_id == project.id)
        .order_by(models.Chapter.number.asc())
        .all()
    )
    ingested_files = (
        db.query(models.File)
        .filter(models.File.project_id == project.id)
        .order_by(models.File.id.asc())
        .all()
    )
    db.refresh(project)
    return schemas_v2.ProjectBootstrapResponse(
        project=_serialize_project_summary(project),
        chapters=[_serialize_chapter_summary(chapter) for chapter in chapters],
        ingested_files=[_serialize_file_record(file_record, viewer=viewer) for file_record in ingested_files],
        redirect_to="/dashboard",
    )


@router.delete("/projects/{project_id}", response_model=schemas_v2.ProjectDeleteResponse)
def api_v2_delete_project(
    project_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    project = project_service.delete_project_with_filesystem(
        db,
        project_id=project_id,
        upload_dir=file_service.UPLOAD_DIR,
    )
    if not project:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PROJECT_NOT_FOUND",
            message="Project not found.",
        )

    return schemas_v2.ProjectDeleteResponse(
        deleted=schemas_v2.ProjectDeleteInfo(
            project_id=project.id,
            code=project.code,
            db_cleanup=True,
            filesystem_cleanup=True,
        ),
        redirect_to="/dashboard?msg=Book+Deleted",
    )


@router.post("/projects/{project_id}/chapters", response_model=schemas_v2.ChapterCreateResponse)
def api_v2_create_chapter(
    project_id: int,
    payload: schemas_v2.ChapterCreateRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    result = chapter_service.create_chapter(
        db,
        project_id=project_id,
        number=payload.number,
        title=payload.title,
        upload_dir=file_service.UPLOAD_DIR,
    )
    if not result["project"]:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PROJECT_NOT_FOUND",
            message="Project not found.",
        )

    return schemas_v2.ChapterCreateResponse(
        chapter=_serialize_chapter_summary(result["chapter"]),
        redirect_to=f"/projects/{project_id}?msg=Chapter+Created+Successfully",
    )


@router.patch("/projects/{project_id}/chapters/{chapter_id}", response_model=schemas_v2.ChapterRenameResponse)
def api_v2_rename_chapter(
    project_id: int,
    chapter_id: int,
    payload: schemas_v2.ChapterRenameRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    original_chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
    previous_number = original_chapter.number if original_chapter else ""
    result = chapter_service.rename_chapter(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        number=payload.number,
        title=payload.title,
        upload_dir=file_service.UPLOAD_DIR,
    )
    if not result["project"] or not result["chapter"]:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHAPTER_OR_PROJECT_NOT_FOUND",
            message="Chapter or project not found.",
        )

    return schemas_v2.ChapterRenameResponse(
        chapter=_serialize_chapter_summary(result["chapter"]),
        previous_number=previous_number,
        redirect_to=f"/projects/{project_id}?msg=Chapter+Renamed+Successfully",
    )


@router.delete("/projects/{project_id}/chapters/{chapter_id}", response_model=schemas_v2.ChapterDeleteResponse)
def api_v2_delete_chapter(
    project_id: int,
    chapter_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
    chapter_number = chapter.number if chapter else ""
    result = chapter_service.delete_chapter_primary(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        upload_dir=file_service.UPLOAD_DIR,
    )
    if not result["project"] or not result["chapter"]:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHAPTER_OR_PROJECT_NOT_FOUND",
            message="Chapter or project not found.",
        )

    return schemas_v2.ChapterDeleteResponse(
        deleted=schemas_v2.ChapterDeleteInfo(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
        ),
        redirect_to=f"/projects/{project_id}?msg=Chapter+Deleted+Successfully",
    )


@router.get("/projects/{project_id}/chapters/{chapter_id}/package")
def api_v2_download_chapter_package(
    project_id: int,
    chapter_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not chapter or not project:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHAPTER_OR_PROJECT_NOT_FOUND",
            message="Chapter or project not found.",
        )

    chapter_dir = f"{file_service.UPLOAD_DIR}/{project.code}/{chapter.number}"
    if not os.path.exists(chapter_dir):
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHAPTER_DIRECTORY_NOT_FOUND",
            message="Chapter directory not found.",
        )

    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    zip_filename = f"{project.code}_Chapter_{chapter.number}.zip"
    with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _dirs, files in os.walk(chapter_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, chapter_dir)
                zipf.write(file_path, arcname)

    return FileResponse(
        temp_zip.name,
        media_type="application/zip",
        filename=zip_filename,
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
    )


@router.get("/files/{file_id}/download")
def api_v2_download_file(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    file_record = file_service.get_file_for_download(db, file_id=file_id)
    if not file_record:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FILE_NOT_FOUND",
            message="File not found.",
        )

    return FileResponse(
        path=file_record.path,
        filename=file_record.filename,
        media_type="application/octet-stream",
    )


@router.delete("/files/{file_id}", response_model=schemas_v2.FileDeleteResponse)
def api_v2_delete_file(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FILE_NOT_FOUND",
            message="File not found.",
        )

    deleted_info = schemas_v2.FileDeleteInfo(
        file_id=file_record.id,
        filename=file_record.filename,
        category=file_record.category,
        project_id=file_record.project_id,
        chapter_id=file_record.chapter_id,
    )
    redirect_to = (
        f"/projects/{file_record.project_id}/chapter/{file_record.chapter_id}"
        f"?tab={file_record.category}&msg=File+Deleted"
    )
    file_service.delete_file_and_capture_context(db, file_id=file_id)
    return schemas_v2.FileDeleteResponse(deleted=deleted_info, redirect_to=redirect_to)


@router.post("/files/{file_id}/checkout", response_model=schemas_v2.FileCheckoutResponse)
def api_v2_checkout_file(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FILE_NOT_FOUND",
            message="File not found.",
        )

    result = checkout_service.checkout_file(db, file_record=file_record, actor_user_id=viewer.id)
    if result["status"] == "locked_by_other":
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="LOCKED_BY_OTHER",
            message="File locked by other user.",
            details={"checked_out_by_id": file_record.checked_out_by_id},
        )

    db.refresh(file_record)
    return schemas_v2.FileCheckoutResponse(
        file_id=file_record.id,
        lock=_serialize_lock(file_record),
        redirect_to=_build_chapter_tab_redirect(file_record, "File+Checked+Out"),
    )


@router.delete("/files/{file_id}/checkout", response_model=schemas_v2.FileCheckoutResponse)
def api_v2_cancel_checkout(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FILE_NOT_FOUND",
            message="File not found.",
        )

    checkout_service.cancel_checkout(db, file_record=file_record, actor_user_id=viewer.id)
    db.refresh(file_record)
    return schemas_v2.FileCheckoutResponse(
        file_id=file_record.id,
        lock=_serialize_lock(file_record),
        redirect_to=_build_chapter_tab_redirect(file_record, "Checkout+Cancelled"),
    )


@router.post(
    "/projects/{project_id}/chapters/{chapter_id}/files/upload",
    response_model=schemas_v2.FileUploadResponse,
)
def api_v2_upload_chapter_files(
    project_id: int,
    chapter_id: int,
    category: str = Form(...),
    files: list[UploadFile] = FastAPIFile(...),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    upload_result = file_service.upload_chapter_files(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        category=category,
        files=files,
        actor_user_id=viewer.id,
        upload_dir=file_service.UPLOAD_DIR,
    )
    if not upload_result["project"] or not upload_result["chapter"]:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PROJECT_OR_CHAPTER_NOT_FOUND",
            message="Project or chapter not found.",
        )

    return schemas_v2.FileUploadResponse(
        uploaded=[_serialize_upload_result(item, viewer=viewer) for item in upload_result["uploaded"]],
        skipped=[schemas_v2.UploadSkippedItem(**item) for item in upload_result["skipped"]],
        redirect_to=(
            f"/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=Files+Uploaded+Successfully"
        ),
    )




@router.get("/files/{file_id}/editor")
def api_v2_file_editor(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    """Return Collabora editor URL for a file."""
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    import logging as _logging
    _logging.getLogger("app.editor").warning(f"EDITOR_DEBUG: viewer={viewer}, file_id={file_id}")
    from app.models import File as _File
    _test = db.query(_File).filter(_File.id == file_id).first()
    _logging.getLogger("app.editor").warning(f"EDITOR_DEBUG: direct_query={_test}, path={_test.path if _test else None}")
    from fastapi import HTTPException as _HTTPException
    try:
        page_state = wopi_service.build_editor_page_state(
            db,
            file_id=file_id,
            collabora_public_url=COLLABORA_PUBLIC_URL,
            wopi_base_url=WOPI_BASE_URL,
        )
        return {"collabora_url": page_state["collabora_url"], "filename": page_state["filename"]}
    except _HTTPException:
        raise
    except Exception as e:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FILE_NOT_FOUND",
            message=str(e),
        )

@router.get("/files/{file_id}/versions", response_model=schemas_v2.FileVersionsResponse)
def api_v2_file_versions(
    file_id: int,
    limit: int = Query(50, ge=1),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FILE_NOT_FOUND",
            message="File not found.",
        )

    versions = version_service.get_versions_for_file(db, file_id=file_id, limit=limit)
    return schemas_v2.FileVersionsResponse(
        file=schemas_v2.FileVersionsFile(
            id=file_record.id,
            filename=file_record.filename,
            current_version=file_record.version,
        ),
        versions=[_serialize_version_record(version_entry) for version_entry in versions],
    )


@router.get("/files/{file_id}/versions/{version_id}/download")
def api_v2_download_file_version(
    file_id: int,
    version_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    version_entry = version_service.get_version_for_download(db, file_id=file_id, version_id=version_id)
    if not version_entry:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="VERSION_NOT_FOUND",
            message="Version not found.",
        )

    return FileResponse(
        path=version_entry.path,
        filename=version_service.get_archived_filename(version_entry),
        media_type="application/octet-stream",
    )


@router.post("/files/{file_id}/processing-jobs", response_model=schemas_v2.ProcessingStartResponse)
def api_v2_start_processing(
    file_id: int,
    payload: schemas_v2.ProcessingStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Not authenticated",
        )

    try:
        response = processing_service.start_process(
            db,
            file_id=file_id,
            process_type=payload.process_type,
            background_tasks=background_tasks,
            mode=payload.mode,
            user=viewer,
            upload_dir=file_service.UPLOAD_DIR,
            logger=logger,
            background_task_callable=_api_v2_background_processing_task,
        )
    except HTTPException as exc:
        code = "PROCESSING_START_FAILED"
        if exc.status_code == 401:
            code = "AUTH_REQUIRED"
        elif exc.status_code == 403:
            code = "PERMISSION_DENIED"
        elif exc.status_code == 404:
            code = "FILE_NOT_FOUND"
        elif exc.status_code == 400:
            code = "FILE_LOCKED"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )

    _ = response  # side effects already performed by the service
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    return schemas_v2.ProcessingStartResponse(
        message=(
            f"{payload.process_type.capitalize()} started in background. "
            "The file is locked and will be updated shortly."
        ),
        source_file_id=file_id,
        process_type=payload.process_type,
        mode=payload.mode,
        source_version=file_record.version,
        lock=_serialize_lock(file_record),
        status_endpoint=(
            f"/api/v2/files/{file_id}/processing-status?process_type=structuring"
            if payload.process_type == "structuring"
            else None
        ),
    )


@router.get("/files/{file_id}/processing-status", response_model=schemas_v2.ProcessingStatusResponse)
def api_v2_processing_status(
    file_id: int,
    process_type: str = "structuring",
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Not authenticated",
        )

    if process_type != "structuring":
        return _error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="STATUS_UNSUPPORTED",
            message="Only structuring status is currently supported.",
        )

    try:
        status_payload = processing_service.get_structuring_status(db, file_id=file_id, user=viewer)
    except HTTPException as exc:
        code = "PROCESSING_STATUS_FAILED"
        if exc.status_code == 401:
            code = "AUTH_REQUIRED"
        elif exc.status_code == 404:
            code = "FILE_NOT_FOUND"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    derived_file_id = status_payload.get("new_file_id")
    derived_filename = None
    if derived_file_id is not None:
        derived_file = db.query(models.File).filter(models.File.id == derived_file_id).first()
        if derived_file:
            derived_filename = derived_file.filename

    return schemas_v2.ProcessingStatusResponse(
        status=status_payload["status"],
        source_file_id=file_id,
        process_type=process_type,
        derived_file_id=derived_file_id,
        derived_filename=derived_filename,
        compatibility_status=status_payload["status"],
        legacy_status_endpoint=f"/api/v1/processing/files/{file_id}/structuring_status",
    )


@router.get("/files/{file_id}/technical-review", response_model=schemas_v2.TechnicalScanResponse)
def api_v2_technical_scan(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Not authenticated",
        )

    try:
        _processing_check_permission(viewer, "technical")
        raw_scan = technical_editor_service.scan_errors(
            db,
            file_id=file_id,
            logger=logger,
            technical_editor_cls=TechnicalEditor,
        )
    except HTTPException as exc:
        code = "TECHNICAL_SCAN_FAILED"
        if exc.status_code == 401:
            code = "AUTH_REQUIRED"
        elif exc.status_code == 403:
            code = "PERMISSION_DENIED"
        elif exc.status_code == 404:
            code = "FILE_NOT_FOUND"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    return schemas_v2.TechnicalScanResponse(
        file=_serialize_file_record(file_record, viewer=viewer),
        issues=[_serialize_technical_issue(key, issue_data) for key, issue_data in raw_scan.items()],
        raw_scan=raw_scan,
    )


@router.post("/files/{file_id}/technical-review/apply", response_model=schemas_v2.TechnicalApplyResponse)
def api_v2_technical_apply(
    file_id: int,
    payload: schemas_v2.TechnicalApplyRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Not authenticated",
        )

    try:
        _processing_check_permission(viewer, "technical")
        apply_result = technical_editor_service.apply_edits(
            db,
            file_id=file_id,
            replacements=payload.replacements,
            username=viewer.username,
            logger=logger,
            technical_editor_cls=TechnicalEditor,
        )
    except HTTPException as exc:
        code = "TECHNICAL_APPLY_FAILED"
        if exc.status_code == 401:
            code = "AUTH_REQUIRED"
        elif exc.status_code == 403:
            code = "PERMISSION_DENIED"
        elif exc.status_code == 404:
            code = "FILE_NOT_FOUND"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )

    new_file = db.query(models.File).filter(models.File.id == apply_result["new_file_id"]).first()
    return schemas_v2.TechnicalApplyResponse(
        source_file_id=file_id,
        new_file_id=apply_result["new_file_id"],
        new_file=_serialize_file_record(new_file, viewer=viewer),
    )


@router.get(
    "/files/{file_id}/structuring-review",
    response_model=schemas_v2.StructuringReviewResponse,
)
def api_v2_structuring_review(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Not authenticated",
        )

    try:
        page_state = structuring_review_service.build_review_page_state(
            db,
            file_id=file_id,
            collabora_public_url=COLLABORA_PUBLIC_URL,
            wopi_base_url=WOPI_BASE_URL,
            extract_document_structure_func=extract_document_structure,
            get_rules_loader_func=get_rules_loader,
        )
    except HTTPException as exc:
        code = "STRUCTURING_REVIEW_FAILED"
        if exc.status_code == 404:
            code = "FILE_NOT_FOUND"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )
    except Exception as exc:
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="STRUCTURING_REVIEW_FAILED",
            message=f"Error loading document structure: {str(exc)}",
        )

    if page_state["status"] == "error":
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PROCESSED_FILE_MISSING",
            message=page_state["error_message"],
        )

    file_record = page_state["file"]
    return_action = _build_structuring_return_action(file_record)
    return schemas_v2.StructuringReviewResponse(
        viewer=_serialize_viewer(viewer),
        file=_serialize_file_record(file_record, viewer=viewer),
        processed_file=schemas_v2.StructuringProcessedFile(filename=page_state["filename"]),
        editor=schemas_v2.StructuringReviewEditor(collabora_url=page_state["collabora_url"]),
        actions=schemas_v2.StructuringReviewActions(
            save_endpoint=f"/api/v2/files/{file_id}/structuring-review/save",
            export_href=f"/api/v2/files/{file_id}/structuring-review/export",
            **return_action,
        ),
        styles=page_state["styles"],
    )


@router.post(
    "/files/{file_id}/structuring-review/save",
    response_model=schemas_v2.StructuringSaveResponse,
)
def api_v2_structuring_save(
    file_id: int,
    payload: schemas_v2.StructuringSaveRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Unauthorized",
        )

    try:
        resolved = structuring_review_service.resolve_processed_target(db, file_id=file_id)
        structuring_review_service.save_changes(
            db,
            file_id=file_id,
            changes={"changes": payload.changes},
            update_document_structure_func=update_document_structure,
            logger=logger,
        )
    except HTTPException as exc:
        code = "STRUCTURING_SAVE_FAILED"
        detail_message = str(exc.detail)
        if exc.status_code == 404:
            code = "PROCESSED_FILE_MISSING" if "Processed file not found" in detail_message else "FILE_NOT_FOUND"
        elif exc.status_code == 401:
            code = "AUTH_REQUIRED"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=detail_message,
        )

    return schemas_v2.StructuringSaveResponse(
        file_id=file_id,
        saved_change_count=len(payload.changes),
        target_filename=resolved["processed_filename"],
    )


@router.get("/files/{file_id}/structuring-review/export")
def api_v2_structuring_export(
    file_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Not authenticated",
        )

    try:
        export_payload = structuring_review_service.get_export_payload(
            db,
            file_id=file_id,
            logger=logger,
        )
    except HTTPException as exc:
        code = "STRUCTURING_EXPORT_FAILED"
        detail_message = str(exc.detail)
        if exc.status_code == 404:
            code = "PROCESSED_FILE_MISSING" if "Processed file not found" in detail_message else "FILE_NOT_FOUND"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=detail_message,
        )

    return FileResponse(
        path=export_payload["path"],
        filename=export_payload["filename"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/admin/dashboard", response_model=schemas_v2.AdminDashboardResponse)
def api_v2_admin_dashboard(
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    return schemas_v2.AdminDashboardResponse(
        viewer=_serialize_viewer(viewer),
        stats=schemas_v2.AdminDashboardStats(**admin_user_service.get_admin_dashboard_stats(db)),
    )


@router.get("/admin/users", response_model=schemas_v2.AdminUsersResponse)
def api_v2_admin_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    page_data = admin_user_service.get_admin_users_page_data(db)
    all_users = page_data["users"]
    window = all_users[offset : offset + limit]
    return schemas_v2.AdminUsersResponse(
        users=[_serialize_admin_user(target_user) for target_user in window],
        roles=[_serialize_admin_role(role) for role in page_data["all_roles"]],
        pagination=schemas_v2.AdminUsersPagination(offset=offset, limit=limit, total=len(all_users)),
    )


@router.get("/admin/roles", response_model=schemas_v2.AdminRolesResponse)
def api_v2_admin_roles(
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    return schemas_v2.AdminRolesResponse(
        roles=[_serialize_admin_role(role) for role in admin_user_service.get_available_roles(db)]
    )


@router.post("/admin/users", response_model=schemas_v2.AdminCreateUserResponse)
def api_v2_admin_create_user(
    payload: schemas_v2.AdminCreateUserRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    try:
        created_user = admin_user_service.create_admin_user(
            db,
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role_id=payload.role_id,
        )
    except ValueError as exc:
        return _error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="DUPLICATE_USER",
            message=str(exc),
        )

    return schemas_v2.AdminCreateUserResponse(
        user=_serialize_admin_user(created_user),
        redirect_to="/admin/users",
    )


@router.put("/admin/users/{user_id}/role", response_model=schemas_v2.AdminUpdateRoleResponse)
def api_v2_admin_update_user_role(
    user_id: int,
    payload: schemas_v2.AdminUpdateRoleRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    previous_role_ids = [role.id for role in target_user.roles] if target_user else []
    result = admin_user_service.replace_user_role(db, user_id=user_id, role_id=payload.role_id)
    if result["status"] == "invalid":
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVALID_USER_OR_ROLE",
            message="Invalid user or role.",
        )
    if result["status"] == "last_admin_blocked":
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="LAST_ADMIN_PROTECTED",
            message="Cannot remove the last Admin role.",
        )

    db.refresh(target_user)
    return schemas_v2.AdminUpdateRoleResponse(
        user=_serialize_admin_user(target_user),
        previous_role_ids=previous_role_ids,
        redirect_to="/admin/users?msg=Role+Updated",
    )


@router.put("/admin/users/{user_id}/status", response_model=schemas_v2.AdminUpdateStatusResponse)
def api_v2_admin_update_user_status(
    user_id: int,
    payload: schemas_v2.AdminUpdateStatusRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found.",
        )
    if target_user.id == viewer.id and payload.is_active is False:
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SELF_LOCKOUT_BLOCKED",
            message="Cannot disable your own account.",
        )
    if target_user.is_active != payload.is_active:
        admin_user_service.toggle_user_status(db, user_id=user_id, actor_user_id=viewer.id)
        db.refresh(target_user)

    return schemas_v2.AdminUpdateStatusResponse(
        user=schemas_v2.AdminStatusUser(id=target_user.id, is_active=target_user.is_active),
        redirect_to="/admin/users",
    )


@router.patch("/admin/users/{user_id}", response_model=schemas_v2.AdminEditUserResponse)
def api_v2_admin_edit_user(
    user_id: int,
    payload: schemas_v2.AdminEditUserRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    try:
        target_user = admin_user_service.update_user_email(db, user_id=user_id, email=payload.email)
    except LookupError:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found.",
        )

    return schemas_v2.AdminEditUserResponse(
        user=_serialize_admin_user(target_user),
        redirect_to="/admin/users?msg=User+updated",
    )


@router.put("/admin/users/{user_id}/password", response_model=schemas_v2.AdminPasswordUpdateResponse)
def api_v2_admin_change_password(
    user_id: int,
    payload: schemas_v2.AdminPasswordUpdateRequest,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )
    if not _has_admin_role(viewer):
        return _error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Admin access required.",
        )

    target_user = admin_user_service.change_password_first_handler(
        db,
        user_id=user_id,
        new_password=payload.new_password,
    )
    if not target_user:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found.",
        )

    return schemas_v2.AdminPasswordUpdateResponse(
        user=schemas_v2.AdminPasswordUser(id=user_id),
        password_updated=True,
        redirect_to="/admin/users",
    )


@router.delete("/admin/users/{user_id}", response_model=schemas_v2.AdminDeleteUserResponse)
def api_v2_admin_delete_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    user=Depends(get_current_user_from_cookie),
):
    viewer = _require_cookie_user(user)
    if not viewer:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Authentication required.",
        )

    delete_result = admin_user_service.delete_user(db, user_id=user_id, actor_username=viewer.username)
    if delete_result["status"] == "not_found":
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found.",
        )
    if delete_result["status"] == "self_delete_blocked":
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SELF_DELETE_BLOCKED",
            message="Cannot delete yourself.",
        )

    return schemas_v2.AdminDeleteUserResponse(
        deleted=schemas_v2.AdminDeleteUser(user_id=user_id),
        redirect_to="/admin/users?msg=User+deleted",
    )
