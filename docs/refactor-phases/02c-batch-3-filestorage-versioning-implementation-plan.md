# Batch 3 Implementation Plan: FileStorageService and VersioningService

No application code was modified. This document defines the implementation plan for Batch 3 of the Phase-2 extraction program: moving the remaining file storage and versioning behavior out of route handlers while preserving all current URLs, redirects, query messages, filenames, archive naming, and DB side effects.

Batch 2 extracted chapter CRUD, chapter ZIP generation, and initial path policy. The remaining route-owned storage logic now lives primarily in [app/routers/web.py](../../app/routers/web.py) inside:

- `POST /projects/{project_id}/chapter/{chapter_id}/upload`
- `GET /projects/files/{file_id}/download`
- `POST /projects/files/{file_id}/delete`
- `POST /projects/{project_id}/delete`

Batch 3 finishes the storage and versioning extraction for those workflows only. It does not change `processing.py`, WOPI behavior, auth, routes, or response contracts.

---

## 1. Batch Scope

### In-scope routes

- `POST /projects/{project_id}/chapter/{chapter_id}/upload`
- `GET /projects/files/{file_id}/download`
- `POST /projects/files/{file_id}/delete`
- `POST /projects/{project_id}/delete`

### In-scope behaviors

- write new file bytes into chapter/category storage
- overwrite existing file bytes in place
- archive current file on overwrite
- create `FileVersion` row during overwrite
- increment `File.version`
- update `uploaded_at` on overwrite
- preserve lock-release side effects on overwrite
- check file existence before download/delete
- build file-download response data
- delete file from storage
- delete project storage tree

### Shared behavior to design for now and reuse later

The service APIs introduced in this batch should be reusable by `processing.py` later, but `processing.py` itself is out of scope for modification in this batch.

Shared future-use concerns:

- archive path creation
- source-file existence checks
- overwrite-in-place semantics
- storage metadata for streaming/download
- project tree removal

### Explicitly out of scope

- `app/routers/processing.py`
- WOPI routes
- checkout/cancel checkout extraction
- auth/session changes
- route URL changes
- API/SSR response redesign
- unifying SSR and API project delete semantics

---

## 2. Current Logic Ownership

### `POST /projects/{project_id}/chapter/{chapter_id}/upload`

Current route ownership in [app/routers/web.py](../../app/routers/web.py):

| Concern | Current ownership |
|---|---|
| auth gate | route redirects to `/login` |
| project/chapter lookup | route queries `models.Project` and `models.Chapter` |
| upload dir existence | route calls `file_storage_service.ensure_chapter_upload_dir(...)` |
| duplicate file detection | route queries `models.File` by `chapter_id`, `category`, `filename` |
| lock check | route skips overwrite if file is checked out by another user |
| archive naming | route computes `name_only = filename.rsplit('.', 1)[0]`, then `f"{name_only}_v{old_version_num}.{old_ext}"` |
| archive path resolution | route calls `file_storage_service.build_archive_file_target(...)` |
| archive copy | route checks `os.path.exists(existing_file.path)` then `shutil.copy2(...)` |
| `FileVersion` creation | route instantiates `models.FileVersion(...)` directly |
| overwrite write | route opens `existing_file.path` in `wb` mode and copies upload bytes |
| overwrite version bump | route increments `existing_file.version += 1` |
| overwrite timestamp update | route sets `existing_file.uploaded_at = datetime.utcnow()` |
| overwrite lock release | route sets `is_checked_out = False`, `checked_out_by_id = None` |
| new file path | route calls `file_storage_service.build_chapter_upload_target(...)` |
| new file write | route opens target path and copies upload bytes |
| new `File` insert | route creates `models.File(...)` directly |
| commit boundary | one `db.commit()` after all uploads |
| redirect behavior | redirects to `/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=Files+Uploaded+Successfully` |

Important current behavior to preserve:

- overwrite is skipped silently for files locked by another user
- archive copy happens only if the old file physically exists
- `FileVersion` row is still created even if the old file is missing
- overwrite uses the existing path, not a new path
- `checked_out_at` is not cleared during overwrite
- new file extension is stored as lowercased suffix or empty string
- all file work commits once at the end of the route

### `GET /projects/files/{file_id}/download`

Current route ownership:

| Concern | Current ownership |
|---|---|
| auth gate | route redirects to `/login` |
| file lookup | route queries `models.File` |
| existence check | route checks `file_record.path` and `os.path.exists(file_record.path)` |
| missing behavior | raises `404` with `detail="File not found"` |
| response | returns `FileResponse(path=file_record.path, filename=file_record.filename, media_type='application/octet-stream')` |

Compatibility constraints:

- `filename` must remain `file_record.filename`
- media type must remain `application/octet-stream`
- route must still 404 if the DB row exists but the file is missing on disk

### `POST /projects/files/{file_id}/delete`

Current route ownership:

| Concern | Current ownership |
|---|---|
| auth gate | route redirects to `/login` |
| file lookup | route queries `models.File` |
| redirect context capture | route stores `project_id`, `chapter_id`, `category` before deletion |
| storage delete | route checks `os.path.exists(file_record.path)` and calls `os.remove(file_record.path)` |
| delete failure handling | route catches delete exception, prints error, continues |
| DB delete | route deletes `file_record` and commits |
| redirect | redirects to `/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=File+Deleted` |

Compatibility constraints:

- disk delete failure must not block DB delete or redirect
- redirect target must still be derived from the deleted row’s current values
- file delete remains SSR-specific behavior in this batch

### `POST /projects/{project_id}/delete`

Current route ownership:

| Concern | Current ownership |
|---|---|
| auth gate | route redirects to `/login` |
| project lookup | route queries `models.Project` |
| project folder path | route builds `f"{UPLOAD_DIR}/{project.code}"` |
| tree delete | route checks existence and calls `shutil.rmtree(project_path, ignore_errors=True)` |
| DB delete | route calls `db.delete(project)` then `db.commit()` |
| redirect | redirects to `/dashboard?msg=Book+Deleted` |

Compatibility constraints:

- storage tree path must remain `{UPLOAD_DIR}/{project.code}`
- tree delete must remain `ignore_errors=True`
- DB delete must remain the current SSR behavior, not the API delete behavior
- redirect must remain `/dashboard?msg=Book+Deleted`

---

## 3. FileStorageService Expansion

Batch 3 expands [app/services/file_storage_service.py](../../app/services/file_storage_service.py) so it owns the remaining direct file storage operations.

### `write_new_file(...)`

Purpose:

- write a brand-new uploaded file into chapter/category storage

Inputs:

```yaml
project_code: str
chapter_number: str
category: str
upload: UploadFile
```

Outputs:

```yaml
WriteNewFileResult:
  file_path: str
  file_type: str
```

Side effects:

- ensures target category directory exists
- writes upload bytes to `{UPLOAD_DIR}/{project_code}/{chapter_number}/{safe_category}/{upload.filename}`

Compatibility requirements:

- must reuse current category sanitization for upload paths: spaces become underscores
- must preserve exact file path shape
- must preserve lowercased extension extraction logic

### `overwrite_existing_file(...)`

Purpose:

- overwrite bytes at the existing stored file path

Inputs:

```yaml
existing_path: str
upload: UploadFile
```

Outputs:

```yaml
OverwriteExistingFileResult:
  file_path: str
```

Side effects:

- opens `existing_path` in `wb` mode
- copies uploaded bytes into that path

Compatibility requirements:

- must overwrite in place, not via temp file rename
- must not move the file to a new path

### `copy_to_archive(...)`

Purpose:

- copy the current physical file into the chapter/category `Archive` folder

Inputs:

```yaml
source_path: str
project_code: str
chapter_number: str
category: str
archive_filename: str
```

Outputs:

```yaml
CopyToArchiveResult:
  archive_path: str
  source_exists: bool
  copy_performed: bool
```

Side effects:

- ensures archive directory exists
- if `source_path` exists, copies it with `shutil.copy2`

Compatibility requirements:

- archive path must remain `{UPLOAD_DIR}/{project_code}/{chapter_number}/{safe_category}/Archive/{archive_filename}`
- must preserve current behavior where missing source file does not raise and does not block later DB actions

### `file_exists(...)`

Purpose:

- centralize storage existence check

Inputs:

```yaml
path: str | None
```

Outputs:

```yaml
bool
```

Compatibility requirements:

- treat `None` and empty path as missing
- use the same existence semantics the routes use now

### `build_download_response_data(...)`

Purpose:

- provide route-safe file response metadata without changing the response contract

Inputs:

```yaml
path: str
download_name: str
media_type: str = application/octet-stream
```

Outputs:

```yaml
DownloadResponseData:
  path: str
  filename: str
  media_type: str
```

Compatibility requirements:

- no filename rewriting
- no MIME inference changes

### `delete_file_from_storage(...)`

Purpose:

- delete a stored file path

Inputs:

```yaml
path: str | None
```

Outputs:

```yaml
DeleteFileResult:
  path: str | None
  existed: bool
  deleted: bool
  error: str | None
```

Side effects:

- checks existence
- calls `os.remove(path)` if present

Compatibility requirements:

- exceptions must be captured and reported, not raised by default
- route must remain free to preserve current “log and continue” behavior

### `delete_project_tree(...)`

Purpose:

- remove the project’s storage tree

Inputs:

```yaml
project_code: str
ignore_errors: bool = True
```

Outputs:

```yaml
DeleteProjectTreeResult:
  project_path: str
  existed: bool
  deleted: bool
```

Side effects:

- computes `{UPLOAD_DIR}/{project_code}`
- deletes with `shutil.rmtree(project_path, ignore_errors=ignore_errors)` when it exists

Compatibility requirements:

- must preserve exact path and `ignore_errors=True` default for SSR delete

### `open_file_stream_metadata(...)`

Purpose:

- build a single canonical storage check for download/serve use

Inputs:

```yaml
path: str | None
download_name: str
media_type: str
```

Outputs:

```yaml
OpenFileStreamMetadata:
  exists: bool
  path: str | None
  filename: str
  media_type: str
```

Compatibility requirements:

- no handle opening is required yet; this method is metadata-oriented so current `FileResponse` usage stays unchanged
- should be reusable by future processing and WOPI-adjacent code without altering this batch’s behavior

---

## 4. VersioningService Design

Batch 3 adds a new service module:

- `app/services/versioning_service.py`

`VersioningService` owns the DB + storage semantics around archiving and version bookkeeping. It does not own route redirects or auth.

### `archive_current_file_version(...)`

Purpose:

- archive the current file version into `Archive`

Inputs:

```yaml
db: Session
file_record: models.File
project_code: str
chapter_number: str
category: str
```

Outputs:

```yaml
ArchivedVersionResult:
  old_version_num: int | None
  archive_filename: str
  archive_path: str
  source_existed: bool
  copy_performed: bool
```

DB dependencies:

- none directly required beyond `file_record` access

Filesystem dependencies:

- `FileStorageService.copy_to_archive(...)`

Compatibility constraints:

- archive filename must remain `"{name_only}_v{old_version_num}.{old_ext}"`
- `old_ext` extraction must preserve current edge cases, including empty extension behavior

### `increment_file_version(...)`

Purpose:

- apply the current overwrite-side DB mutations to a `File` row

Inputs:

```yaml
file_record: models.File
timestamp: datetime
release_lock: bool = True
```

Outputs:

```yaml
IncrementFileVersionResult:
  new_version: int
```

DB dependencies:

- mutates `models.File`

Filesystem dependencies:

- none

Compatibility constraints:

- increment by exactly `+1`
- set `uploaded_at` to the provided timestamp
- set `is_checked_out = False`
- set `checked_out_by_id = None`
- do not modify `checked_out_at`

### `create_file_version_record(...)`

Purpose:

- create the historical `FileVersion` row for the version being replaced

Inputs:

```yaml
db: Session
file_record: models.File
version_num: int | None
archive_path: str
uploaded_by_id: int
```

Outputs:

```yaml
models.FileVersion
```

DB dependencies:

- `models.FileVersion`
- active `Session`

Filesystem dependencies:

- none

Compatibility constraints:

- `file_id` must point to the current `File`
- `version_num` must be the pre-increment version
- `path` must be the archive path even if the physical copy did not occur
- `uploaded_by_id` must remain the current route user id

### `prepare_overwrite_versioning(...)`

Purpose:

- orchestration helper for the current overwrite flow

Inputs:

```yaml
db: Session
file_record: models.File
project_code: str
chapter_number: str
category: str
uploaded_by_id: int
timestamp: datetime
```

Outputs:

```yaml
PrepareOverwriteVersioningResult:
  archive_path: str
  old_version_num: int | None
  version_entry: models.FileVersion
  updated_file_record: models.File
  source_existed: bool
```

DB dependencies:

- `models.File`
- `models.FileVersion`
- active `Session`

Filesystem dependencies:

- `FileStorageService.copy_to_archive(...)`

Compatibility constraints:

- must preserve the current order of effects:
  1. compute archive filename/path
  2. copy source if present
  3. add `FileVersion`
  4. later route or wrapper overwrites bytes in place
  5. increment file version/timestamp/lock state
- route commit boundary stays external in this batch

---

## 5. Compatibility Wrapper Plan

Routes remain HTTP wrappers. Service extraction in Batch 3 must not change user-visible flow.

### `POST /projects/{project_id}/chapter/{chapter_id}/upload`

Route keeps:

- auth gate and `/login` redirect
- project/chapter lookup and 404
- existing-file lookup query
- skip-if-locked behavior
- final redirect string and status code
- single `db.commit()` after the loop

Route delegates:

- new-file write to `FileStorageService.write_new_file(...)`
- overwrite archive prep to `VersioningService.prepare_overwrite_versioning(...)`
- overwrite byte write to `FileStorageService.overwrite_existing_file(...)`
- new-file metadata extraction through storage service result

Wrapper compatibility rules:

- redirect remains `/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=Files+Uploaded+Successfully`
- skipped locked files continue to produce a successful overall redirect
- `models.File` insert shape remains unchanged
- `models.FileVersion` semantics remain unchanged

### `GET /projects/files/{file_id}/download`

Route keeps:

- auth gate
- file row lookup
- 404 contract

Route delegates:

- storage existence check and response metadata assembly to `FileStorageService.open_file_stream_metadata(...)` or `build_download_response_data(...)`

Wrapper compatibility rules:

- `FileResponse` still uses the same `path`, `filename`, and `application/octet-stream`

### `POST /projects/files/{file_id}/delete`

Route keeps:

- auth gate
- file row lookup
- redirect context capture
- DB delete and commit

Route delegates:

- physical file deletion to `FileStorageService.delete_file_from_storage(...)`

Wrapper compatibility rules:

- delete errors remain non-fatal
- redirect remains `/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=File+Deleted`

### `POST /projects/{project_id}/delete`

Route keeps:

- auth gate
- not-found behavior
- final redirect

Route delegates:

- tree deletion to `FileStorageService.delete_project_tree(...)`
- DB deletion to a project-service method that preserves current SSR semantics

Wrapper compatibility rules:

- redirect remains `/dashboard?msg=Book+Deleted`
- do not switch to `delete_project_v2(...)` unless its behavior is proven identical for this SSR path

---

## 6. Project Delete Extraction

Project delete crosses two boundaries:

- storage boundary: project tree deletion
- DB boundary: project row deletion

### Target ownership

`FileStorageService` should own:

- project root resolution from `project.code`
- existence check
- `shutil.rmtree(..., ignore_errors=True)`

`ProjectService` should own:

- project lookup or deletion helper for the SSR path
- DB delete + commit

### Recommended extraction shape

Add a dedicated SSR-preserving helper in [app/services/project_service.py](../../app/services/project_service.py), for example:

- `delete_project_ssr(db, project_id)`

This helper should preserve the route’s current DB semantics rather than reusing API-oriented delete helpers with different behavior.

### Compatibility requirements

- project folder path remains `{UPLOAD_DIR}/{project.code}`
- tree delete uses `ignore_errors=True`
- DB delete remains equivalent to `db.delete(project); db.commit()`
- redirect remains `/dashboard?msg=Book+Deleted`

### What not to do in Batch 3

- do not unify API and SSR delete semantics
- do not route SSR delete through `/api/v1/projects/{id}`
- do not introduce new error messaging

---

## 7. Regression Test Plan

### Upload new file

Setup:

- existing project, chapter, empty category

Assertions:

- file written to the same storage path shape as today
- `File` row created with `version=1`
- redirect remains unchanged

### Overwrite existing file

Setup:

- existing `File` row and physical file

Assertions:

- bytes at the original path are replaced
- no new primary `File` row is created
- redirect remains unchanged

### Archive copy naming

Setup:

- existing file named `test.docx` with version `3`

Assertions:

- archived filename is `test_v3.docx`
- archive location remains `{category}/Archive/...`

### `File.version` increment

Assertions:

- pre-overwrite version `N` becomes `N+1`
- update happens only for overwritten files

### `FileVersion` row creation

Assertions:

- one `FileVersion` row created for each overwritten file
- `version_num` equals the pre-increment version
- `path` equals the computed archive path
- `uploaded_by_id` equals the current user id

### Locked overwrite skip

Setup:

- existing file checked out by another user

Assertions:

- file is not overwritten
- no archive copy
- no `FileVersion` row
- route still redirects with the current success message

### Download existing file

Assertions:

- `FileResponse` filename matches `file_record.filename`
- missing-on-disk still returns `404 File not found`

### Delete existing file

Assertions:

- physical file removed if present
- DB row deleted
- redirect remains unchanged

### Delete file when physical file is already missing

Assertions:

- no exception escapes route
- DB row still deleted
- redirect remains unchanged

### Project delete removes tree

Assertions:

- `{UPLOAD_DIR}/{project.code}` is removed recursively
- DB project row is deleted

### Project delete preserves redirect

Assertions:

- redirect remains `/dashboard?msg=Book+Deleted`

### Chapter upload redirect/query compatibility

Assertions:

- route still redirects to the same chapter tab
- `msg=Files+Uploaded+Successfully` remains unchanged

---

## 8. File-Level Change Plan

### [app/routers/web.py](../../app/routers/web.py)

Why it changes:

- replace direct file copy/write/delete logic with service calls
- keep route wrappers, lookups, redirects, and response shapes

Expected edits:

- upload route calls storage/versioning helpers
- download route uses storage metadata helper
- file delete route uses storage delete helper
- project delete route uses storage tree delete helper and project-service DB delete helper

### [app/services/file_storage_service.py](../../app/services/file_storage_service.py)

Why it changes:

- expand from path policy into actual file IO ownership

Expected edits:

- add new file-write, copy, delete, exists, and response-metadata helpers
- keep current path conventions intact

### `app/services/versioning_service.py`

Why it changes:

- centralize archive naming, `FileVersion` creation, and file version increment semantics

Expected edits:

- new service module
- methods for archive, version-row creation, and overwrite-version prep

### [app/services/project_service.py](../../app/services/project_service.py)

Why it may change:

- add an SSR-preserving project-delete helper to remove DB delete logic from the route without changing semantics

Expected edits:

- separate SSR delete helper from API delete helpers
- no API behavior changes in this batch

### Tests

Expected new or updated tests:

- route-level regression tests for upload/download/delete/project-delete
- service-level tests for file storage and versioning helpers

---

## 9. Safe Stopping Point

Batch 3 is complete when all of the following are true:

- `app/routers/web.py` no longer performs direct file write, overwrite, archive copy, file delete, or project tree delete logic for the in-scope workflows
- archive/version logic is centralized in `VersioningService`
- storage existence, write, copy, delete, and download metadata logic is centralized in `FileStorageService`
- download, file delete, and project delete routes are thin wrappers
- chapter upload route still returns the exact same redirect and query message
- file download still returns the same `FileResponse` shape
- project delete still removes the same storage tree and redirects to `/dashboard?msg=Book+Deleted`
- no processing routes were changed
- no WOPI routes were changed

### Explicit non-goals at the stopping point

- no processing-route adoption of the new storage/versioning helpers yet
- no checkout/lock extraction yet
- no auth/session changes
- no response contract redesign

### Recommended next step after Batch 3

After this batch lands, the next extraction target should be the checkout/lock and processing orchestration boundary, using the now-centralized storage/versioning helpers as dependencies rather than duplicating storage semantics again.
