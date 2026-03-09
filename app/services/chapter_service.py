from __future__ import annotations

from typing import Iterable, Mapping

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app import models
from app.services.file_storage_service import (
    ChapterDirectoryNotFoundError,
    ChapterZipBundle,
    FileStorageService,
)


class ProjectNotFoundError(LookupError):
    pass


class ChapterNotFoundError(LookupError):
    pass


class ChapterService:
    def __init__(self, storage_service: FileStorageService | None = None):
        self.storage_service = storage_service or FileStorageService()

    def list_chapters(self, db: Session, project_id: int) -> tuple[models.Project, list[models.Chapter]]:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project:
            raise ProjectNotFoundError("Project not found")
        return project, list(project.chapters)

    def build_chapter_inventory(
        self,
        db: Session,
        project_id: int,
    ) -> tuple[models.Project, list[models.Chapter]]:
        project, chapters = self.list_chapters(db, project_id)

        processed_chapters = []
        for chapter in chapters:
            chapter.has_art = any(file.category == "Art" for file in chapter.files)
            chapter.has_ms = any(file.category == "Manuscript" for file in chapter.files)
            chapter.has_ind = any(file.category == "InDesign" for file in chapter.files)
            chapter.has_proof = any(file.category == "Proof" for file in chapter.files)
            chapter.has_xml = any(file.category == "XML" for file in chapter.files)
            processed_chapters.append(chapter)

        return project, processed_chapters

    def create_chapter(
        self,
        db: Session,
        project_id: int,
        number: str,
        title: str,
    ) -> tuple[models.Project, models.Chapter]:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project:
            raise ProjectNotFoundError("Project not found")

        chapter = models.Chapter(project_id=project_id, number=number, title=title)
        db.add(chapter)
        db.commit()
        db.refresh(chapter)

        self.storage_service.ensure_chapter_category_tree(project.code, number, sanitize_spaces=False)
        return project, chapter

    def rename_chapter(
        self,
        db: Session,
        project_id: int,
        chapter_id: int,
        number: str,
        title: str,
    ) -> tuple[models.Project, models.Chapter]:
        chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not chapter or not project:
            raise ChapterNotFoundError("Chapter or Project not found")

        old_number = chapter.number
        chapter.number = number
        chapter.title = title
        db.commit()

        self.storage_service.rename_chapter_dir(project.code, old_number, number)
        return project, chapter

    def delete_chapter(
        self,
        db: Session,
        project_id: int,
        chapter_id: int,
        ignore_errors: bool = False,
    ) -> tuple[models.Project, models.Chapter]:
        chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not chapter or not project:
            raise ChapterNotFoundError("Chapter or Project not found")

        self.storage_service.delete_chapter_dir(
            project.code,
            chapter.number,
            ignore_errors=ignore_errors,
        )
        db.delete(chapter)
        db.commit()
        return project, chapter

    def generate_chapter_zip(
        self,
        db: Session,
        project_id: int,
        chapter_id: int,
    ) -> ChapterZipBundle:
        chapter = db.query(models.Chapter).filter(models.Chapter.id == chapter_id).first()
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not chapter or not project:
            raise ChapterNotFoundError("Chapter or Project not found")

        return self.storage_service.create_chapter_zip(project.code, chapter.number)

    def create_project_chapters(
        self,
        db: Session,
        project_id: int,
        chapter_count: int,
    ) -> dict[str, int]:
        created_chapters: dict[str, int] = {}

        for index in range(1, chapter_count + 1):
            chapter_number = f"{index:02d}"
            chapter = models.Chapter(
                project_id=project_id,
                number=chapter_number,
                title=f"Chapter {chapter_number}",
            )
            db.add(chapter)
            db.commit()
            db.refresh(chapter)
            created_chapters[chapter_number] = chapter.id

        return created_chapters

    def initialize_project_chapters_and_files(
        self,
        db: Session,
        project: models.Project,
        chapter_count: int,
        files: list[UploadFile] | None,
    ) -> dict[str, int]:
        created_chapters = self.create_project_chapters(db, project.id, chapter_count)

        if files:
            self.storage_service.ensure_project_root(project.code)

            for upload in files:
                if not upload.filename:
                    continue

                category, ext = self.storage_service.infer_initial_upload_category(upload.filename)
                target_ch_num, chapter_id = self.storage_service.infer_initial_upload_chapter(
                    upload.filename,
                    created_chapters,
                )
                file_path, _ = self.storage_service.save_initial_upload(
                    project.code,
                    target_ch_num,
                    category,
                    upload,
                )

                db.add(
                    models.File(
                        project_id=project.id,
                        chapter_id=chapter_id,
                        filename=upload.filename,
                        file_type=ext,
                        category=category,
                        path=file_path,
                    )
                )

            db.commit()

        return created_chapters
