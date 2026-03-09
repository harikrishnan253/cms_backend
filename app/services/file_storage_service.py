from __future__ import annotations

from dataclasses import dataclass
import os
import re
import shutil
import tempfile
import zipfile
from typing import Mapping, Sequence

from fastapi import UploadFile

from app.services.file_service import UPLOAD_DIR


DEFAULT_CHAPTER_CATEGORIES = ["Manuscript", "Art", "InDesign", "Proof", "XML"]


class ChapterDirectoryNotFoundError(FileNotFoundError):
    pass


@dataclass
class ChapterZipBundle:
    temp_path: str
    filename: str


@dataclass
class WriteFileResult:
    file_path: str
    file_type: str


@dataclass
class ArchiveCopyResult:
    archive_path: str
    source_exists: bool
    copy_performed: bool


@dataclass
class DownloadResponseData:
    path: str
    filename: str
    media_type: str


@dataclass
class OpenFileStreamMetadata:
    exists: bool
    path: str | None
    filename: str
    media_type: str


@dataclass
class DeleteFileResult:
    path: str | None
    existed: bool
    deleted: bool
    error: str | None = None


@dataclass
class DeleteProjectTreeResult:
    project_path: str
    existed: bool
    deleted: bool


class FileStorageService:
    def get_project_root(self, project_code: str) -> str:
        return f"{UPLOAD_DIR}/{project_code}"

    def ensure_project_root(self, project_code: str) -> str:
        project_root = self.get_project_root(project_code)
        os.makedirs(project_root, exist_ok=True)
        return project_root

    def get_chapter_dir(self, project_code: str, chapter_number: str) -> str:
        return f"{UPLOAD_DIR}/{project_code}/{chapter_number}"

    def get_category_dir(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        sanitize_spaces: bool = True,
    ) -> str:
        category_name = category.replace(" ", "_") if sanitize_spaces else category
        return f"{UPLOAD_DIR}/{project_code}/{chapter_number}/{category_name}"

    def ensure_category_dir(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        sanitize_spaces: bool = True,
    ) -> str:
        category_dir = self.get_category_dir(
            project_code,
            chapter_number,
            category,
            sanitize_spaces=sanitize_spaces,
        )
        os.makedirs(category_dir, exist_ok=True)
        return category_dir

    def ensure_chapter_upload_dir(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
    ) -> str:
        return self.ensure_category_dir(
            project_code,
            chapter_number,
            category,
            sanitize_spaces=True,
        )

    def get_archive_dir(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
    ) -> str:
        category_dir = self.get_category_dir(
            project_code,
            chapter_number,
            category,
            sanitize_spaces=True,
        )
        return f"{category_dir}/Archive"

    def ensure_archive_dir(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
    ) -> str:
        archive_dir = self.get_archive_dir(project_code, chapter_number, category)
        os.makedirs(archive_dir, exist_ok=True)
        return archive_dir

    def ensure_chapter_category_tree(
        self,
        project_code: str,
        chapter_number: str,
        categories: Sequence[str] | None = None,
        sanitize_spaces: bool = False,
    ) -> list[str]:
        created_dirs = []
        for category in categories or DEFAULT_CHAPTER_CATEGORIES:
            created_dirs.append(
                self.ensure_category_dir(
                    project_code,
                    chapter_number,
                    category,
                    sanitize_spaces=sanitize_spaces,
                )
            )
        return created_dirs

    def rename_chapter_dir(self, project_code: str, old_number: str, new_number: str) -> bool:
        if old_number == new_number:
            return False

        old_dir = self.get_chapter_dir(project_code, old_number)
        new_dir = self.get_chapter_dir(project_code, new_number)
        if not os.path.exists(old_dir):
            return False

        os.rename(old_dir, new_dir)
        return True

    def delete_chapter_dir(
        self,
        project_code: str,
        chapter_number: str,
        ignore_errors: bool = False,
    ) -> bool:
        chapter_dir = self.get_chapter_dir(project_code, chapter_number)
        if not os.path.exists(chapter_dir):
            return False

        shutil.rmtree(chapter_dir, ignore_errors=ignore_errors)
        return True

    def infer_initial_upload_category(self, filename: str) -> tuple[str, str]:
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        category = "Miscellaneous"
        if ext in ["doc", "docx"]:
            category = "Manuscript"
        elif ext in ["indd", "idml"]:
            category = "InDesign"
        elif ext in ["jpg", "png", "tif", "eps"]:
            category = "Art"
        elif ext in ["pdf"]:
            category = "Proof"
        elif ext in ["xml"]:
            category = "XML"
        return category, ext

    def infer_initial_upload_chapter(
        self,
        filename: str,
        created_chapters: Mapping[str, int],
    ) -> tuple[str, int | None]:
        target_ch_num = "01"
        chapter_id = None

        match = re.search(r"(?:ch|chap|chapter|^|_)?\s*(\d+)", filename.lower())
        if match:
            num_str = match.group(1)
            formatted_num = f"{int(num_str):02d}"
            if formatted_num in created_chapters:
                chapter_id = created_chapters[formatted_num]
                target_ch_num = formatted_num

        if not chapter_id and "01" in created_chapters:
            chapter_id = created_chapters["01"]
            target_ch_num = "01"

        return target_ch_num, chapter_id

    def build_initial_upload_target(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        filename: str,
    ) -> str:
        category_dir = self.ensure_chapter_upload_dir(
            project_code,
            chapter_number,
            category,
        )
        return f"{category_dir}/{filename}"

    def build_chapter_upload_target(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        filename: str,
    ) -> str:
        return self.build_initial_upload_target(
            project_code,
            chapter_number,
            category,
            filename,
        )

    def build_archive_file_target(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        filename: str,
    ) -> str:
        archive_dir = self.ensure_archive_dir(project_code, chapter_number, category)
        return f"{archive_dir}/{filename}"

    def write_new_file(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        upload: UploadFile,
    ) -> WriteFileResult:
        file_path = self.build_chapter_upload_target(
            project_code,
            chapter_number,
            category,
            upload.filename,
        )
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)

        file_type = upload.filename.split(".")[-1].lower() if "." in upload.filename else ""
        return WriteFileResult(file_path=file_path, file_type=file_type)

    def overwrite_existing_file(
        self,
        existing_path: str,
        upload: UploadFile,
    ) -> WriteFileResult:
        with open(existing_path, "wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)

        file_type = upload.filename.split(".")[-1].lower() if "." in upload.filename else ""
        return WriteFileResult(file_path=existing_path, file_type=file_type)

    def copy_to_archive(
        self,
        source_path: str | None,
        project_code: str,
        chapter_number: str,
        category: str,
        archive_filename: str,
    ) -> ArchiveCopyResult:
        archive_path = self.build_archive_file_target(
            project_code,
            chapter_number,
            category,
            archive_filename,
        )
        source_exists = self.file_exists(source_path)
        if source_exists:
            shutil.copy2(source_path, archive_path)

        return ArchiveCopyResult(
            archive_path=archive_path,
            source_exists=source_exists,
            copy_performed=source_exists,
        )

    def file_exists(self, path: str | None) -> bool:
        return bool(path) and os.path.exists(path)

    def build_download_response_data(
        self,
        path: str,
        download_name: str,
        media_type: str = "application/octet-stream",
    ) -> DownloadResponseData:
        return DownloadResponseData(
            path=path,
            filename=download_name,
            media_type=media_type,
        )

    def delete_file_from_storage(self, path: str | None) -> DeleteFileResult:
        if not path:
            return DeleteFileResult(path=path, existed=False, deleted=False)

        if not os.path.exists(path):
            return DeleteFileResult(path=path, existed=False, deleted=False)

        try:
            os.remove(path)
            return DeleteFileResult(path=path, existed=True, deleted=True)
        except Exception as exc:
            return DeleteFileResult(
                path=path,
                existed=True,
                deleted=False,
                error=str(exc),
            )

    def delete_project_tree(
        self,
        project_code: str,
        ignore_errors: bool = True,
    ) -> DeleteProjectTreeResult:
        project_path = self.get_project_root(project_code)
        existed = os.path.exists(project_path)
        if existed:
            shutil.rmtree(project_path, ignore_errors=ignore_errors)

        return DeleteProjectTreeResult(
            project_path=project_path,
            existed=existed,
            deleted=existed,
        )

    def open_file_stream_metadata(
        self,
        path: str | None,
        download_name: str,
        media_type: str = "application/octet-stream",
    ) -> OpenFileStreamMetadata:
        return OpenFileStreamMetadata(
            exists=self.file_exists(path),
            path=path,
            filename=download_name,
            media_type=media_type,
        )

    def save_initial_upload(
        self,
        project_code: str,
        chapter_number: str,
        category: str,
        upload: UploadFile,
    ) -> tuple[str, str]:
        write_result = self.write_new_file(
            project_code,
            chapter_number,
            category,
            upload,
        )
        return write_result.file_path, write_result.file_type

    def create_chapter_zip(self, project_code: str, chapter_number: str) -> ChapterZipBundle:
        chapter_dir = self.get_chapter_dir(project_code, chapter_number)
        if not os.path.exists(chapter_dir):
            raise ChapterDirectoryNotFoundError("Chapter directory not found")

        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        zip_filename = f"{project_code}_Chapter_{chapter_number}.zip"

        with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(chapter_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    arcname = os.path.relpath(file_path, chapter_dir)
                    zipf.write(file_path, arcname)

        return ChapterZipBundle(temp_path=temp_zip.name, filename=zip_filename)

    def resolve_processed_file_path(self, file_path: str) -> str:
        if file_path.endswith("_Processed.docx"):
            return file_path

        dir_name = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        name_only = os.path.splitext(base_name)[0]
        return os.path.join(dir_name, f"{name_only}_Processed.docx")

    def resolve_technical_output_path(self, file_path: str) -> str:
        dir_name = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        name_only, ext = os.path.splitext(base_name)
        return os.path.join(dir_name, f"{name_only}_TechEdited{ext}")
