from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.services.file_storage_service import FileStorageService


@dataclass
class ArchivedVersionResult:
    old_version_num: int | None
    archive_filename: str
    archive_path: str
    source_existed: bool
    copy_performed: bool


@dataclass
class IncrementFileVersionResult:
    new_version: int | None


@dataclass
class PrepareOverwriteVersioningResult:
    archive_path: str
    old_version_num: int | None
    version_entry: models.FileVersion
    source_existed: bool
    copy_performed: bool


class VersioningService:
    def __init__(self, storage_service: FileStorageService | None = None):
        self.storage_service = storage_service or FileStorageService()

    def archive_current_file_version(
        self,
        file_record: models.File,
        project_code: str,
        chapter_number: str,
        category: str,
    ) -> ArchivedVersionResult:
        old_version_num = file_record.version
        old_ext = file_record.filename.split(".")[-1] if "." in file_record.filename else ""
        name_only = file_record.filename.rsplit(".", 1)[0]
        archive_filename = f"{name_only}_v{old_version_num}.{old_ext}"

        archive_copy = self.storage_service.copy_to_archive(
            file_record.path,
            project_code,
            chapter_number,
            category,
            archive_filename,
        )

        return ArchivedVersionResult(
            old_version_num=old_version_num,
            archive_filename=archive_filename,
            archive_path=archive_copy.archive_path,
            source_existed=archive_copy.source_exists,
            copy_performed=archive_copy.copy_performed,
        )

    def increment_file_version(
        self,
        file_record: models.File,
        timestamp: datetime,
    ) -> IncrementFileVersionResult:
        file_record.version += 1
        file_record.uploaded_at = timestamp

        return IncrementFileVersionResult(new_version=file_record.version)

    def create_file_version_record(
        self,
        db: Session,
        file_record: models.File,
        version_num: int | None,
        archive_path: str,
        uploaded_by_id: int,
    ) -> models.FileVersion:
        version_entry = models.FileVersion(
            file_id=file_record.id,
            version_num=version_num,
            path=archive_path,
            uploaded_by_id=uploaded_by_id,
        )
        db.add(version_entry)
        return version_entry

    def prepare_overwrite_versioning(
        self,
        db: Session,
        file_record: models.File,
        project_code: str,
        chapter_number: str,
        category: str,
        uploaded_by_id: int,
    ) -> PrepareOverwriteVersioningResult:
        archived_version = self.archive_current_file_version(
            file_record,
            project_code,
            chapter_number,
            category,
        )
        version_entry = self.create_file_version_record(
            db,
            file_record,
            archived_version.old_version_num,
            archived_version.archive_path,
            uploaded_by_id,
        )

        return PrepareOverwriteVersioningResult(
            archive_path=archived_version.archive_path,
            old_version_num=archived_version.old_version_num,
            version_entry=version_entry,
            source_existed=archived_version.source_existed,
            copy_performed=archived_version.copy_performed,
        )
