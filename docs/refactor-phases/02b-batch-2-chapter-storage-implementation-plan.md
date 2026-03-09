# Batch 2 Implementation Plan: ChapterService and Initial FileStorageService

No application code was modified. This document defines the exact implementation plan for Batch 2 of the Phase-2 extraction program: moving chapter CRUD and initial directory/path logic out of route handlers while preserving all current URLs, redirects, templates, and filesystem behavior.

## Scope

Batch 2 extracts:

- chapter CRUD workflow ownership into `ChapterService`
- initial path policy and directory mutation logic into `FileStorageService`
- chapter ZIP generation into a centralized storage helper/service method
- project-create chapter/directory setup logic into service-owned workflows

It does not yet extract:

- chapter detail file upload/versioning logic in full
- file delete/download routes
- checkout/lock orchestration
- processing orchestration
- WOPI behavior
- template redesign

---

## 1. Batch Scope

### In-scope routes

- `GET /projects/{project_id}`
- `GET /projects/{project_id}/chapters`
- `POST /projects/{project_id}/chapters/create`
- `POST /projects/{project_id}/chapter/{chapter_id}/rename`
- `POST /projects/{project_id}/chapter/{chapter_id}/delete`
- `GET /projects/{project_id}/chapter/{chapter_id}/download`

### Project creation workflow also in scope

- `GET /projects/create`
- `POST /projects/create_with_files`

### In-scope responsibilities

- chapter list/query assembly
- chapter inventory flags (`has_art`, `has_ms`, `has_ind`, `has_proof`, `has_xml`)
- chapter create DB insert
- chapter directory creation
- chapter rename DB update
- chapter directory rename
- chapter delete DB delete
- chapter directory deletion
- chapter ZIP creation
- project-create chapter loop
- initial project-create file chapter/category path placement

### Out of scope for Batch 2

- `GET /projects/{project_id}/chapter/{chapter_id}` page extraction
- `POST /projects/{project_id}/chapter/{chapter_id}/upload`
- `GET /projects/files/{file_id}/download`
- `POST /projects/files/{file_id}/delete`
- checkout/cancel checkout flows
- versioning service extraction in full
- processing and technical routes

---

## 2. Current Route Logic Ownership

### `GET /projects/{project_id}` and `GET /projects/{project_id}/chapters`

| Concern | Current ownership |
|---|---|
| auth gate | `get_current_user_from_cookie` in route |
| project lookup | route queries `models.Project` by id |
| missing project handling | route raises `404` |
| chapter list source | `project.chapters` relationship |
| inventory flag generation | route loops over each chapter and computes `has_art`, `has_ms`, `has_ind`, `has_proof`, `has_xml` by inspecting `ch.files` |
| template context generation | route builds `processed_chapters`, `user_data`, and passes `request`, `project`, `chapters`, `user` to `project_chapters.html` |
| redirect behavior | unauthenticated user redirects to `/login` |

Filesystem operations:

- none directly

Database operations:

- read `Project`
- read chapters via relationship
- read files via relationship on chapters

### `POST /projects/{project_id}/chapters/create`

| Concern | Current ownership |
|---|---|
| auth gate | route |
| project existence check | route queries `Project` |
| chapter creation | route constructs `models.Chapter(project_id, number, title)` and commits |
| chapter numbering logic | route trusts submitted `number`; no normalization beyond using provided form value |
| directory creation | route creates `UPLOAD_DIR/{project.code}/{number}/{category}` for `Manuscript`, `Art`, `InDesign`, `Proof`, `XML` |
| redirect behavior | redirect to `/projects/{project_id}?msg=Chapter+Created+Successfully` |

Filesystem operations:

- create chapter base directory implicitly through category directory creation
- create five category directories

Database operations:

- insert `Chapter`

### `POST /projects/{project_id}/chapter/{chapter_id}/rename`

| Concern | Current ownership |
|---|---|
| auth gate | route |
| chapter/project lookup | route queries `Chapter` and `Project` |
| DB rename | route updates `chapter.number` and `chapter.title`, then commits |
| directory rename logic | route computes old directory as `UPLOAD_DIR/{project.code}/{old_number}` and new directory as `UPLOAD_DIR/{project.code}/{number}` and calls `os.rename` if old dir exists |
| redirect behavior | redirect to `/projects/{project_id}?msg=Chapter+Renamed+Successfully` |

Filesystem operations:

- rename chapter directory if chapter number changed and old directory exists

Database operations:

- update `Chapter.number`
- update `Chapter.title`

### `POST /projects/{project_id}/chapter/{chapter_id}/delete`

| Concern | Current ownership |
|---|---|
| auth gate | route |
| chapter/project lookup | route queries `Chapter` and `Project` |
| directory deletion | route computes `chapter_dir = f"{UPLOAD_DIR}/{project.code}/{chapter.number}"` and removes it with `shutil.rmtree` if present |
| DB delete | route deletes `chapter` and commits |
| redirect behavior | redirect to `/projects/{project_id}?msg=Chapter+Deleted+Successfully` in one route body; duplicate route elsewhere returns a slightly different message |

Filesystem operations:

- recursive delete of chapter directory tree

Database operations:

- delete `Chapter`

### `GET /projects/{project_id}/chapter/{chapter_id}/download`

| Concern | Current ownership |
|---|---|
| auth gate | route |
| chapter/project lookup | route queries `Chapter` and `Project` |
| path resolution | route computes chapter dir as `UPLOAD_DIR/{project.code}/{chapter.number}` |
| missing directory handling | `404 Chapter directory not found` |
| ZIP generation logic | route creates `NamedTemporaryFile`, traverses `os.walk(chapter_dir)`, adds each file with `arcname = os.path.relpath(file_path, chapter_dir)` |
| download response | `FileResponse(temp_zip.name, media_type='application/zip', filename=zip_filename, headers={"Content-Disposition": ...})` |

Filesystem operations:

- read full chapter tree
- create temp zip file

Database operations:

- read `Project`
- read `Chapter`

### `GET /projects/create`

| Concern | Current ownership |
|---|---|
| auth gate | route |
| template context generation | route builds `user_data` and renders `project_create.html` |

Filesystem operations:

- none

Database operations:

- none

### `POST /projects/create_with_files`

| Concern | Current ownership |
|---|---|
| auth gate | route |
| project creation | route builds `schemas.ProjectCreate(title, code, xml_standard, team_id=1)` and calls `project_service.create_project` |
| client name patch | route mutates `db_project.client_name` and commits again if provided |
| chapter creation loop | route creates `01..N` chapters in a loop, committing each one separately |
| chapter numbering logic | zero-padded 2-digit numbering via `f"{i:02d}"` |
| initial upload category inference | extension-based mapping: doc/docx -> Manuscript; indd/idml -> InDesign; jpg/png/tif/eps -> Art; pdf -> Proof; xml -> XML; otherwise Miscellaneous |
| initial upload chapter inference | regex search `r'(?:ch|chap|chapter|^|_)?\s*(\d+)'` against filename; if matched and chapter exists use zero-padded chapter number; else fallback to chapter `01` if available |
| initial directory creation | `UPLOAD_DIR/{code}`, then per file `UPLOAD_DIR/{code}/{target_ch_num}/{safe_cat}` |
| initial file persistence | write upload bytes directly to resolved path and insert `models.File` row |
| redirect behavior | redirect to `/dashboard` |

Filesystem operations:

- create project root if files are present
- create chapter/category directory per uploaded file
- write uploaded files

Database operations:

- create `Project`
- optional update of `client_name`
- insert `Chapter` rows
- insert `File` rows

### Observed template context compatibility constraints

`project_chapters.html` currently expects:

- `request`
- `project`
- `chapters`
- `user`

Where `chapters` is not a pure DTO yet; the route mutates chapter objects with transient attributes:

- `has_art`
- `has_ms`
- `has_ind`
- `has_proof`
- `has_xml`

Batch 2 must preserve these context keys and the effective truthiness of those attributes.

---

## 3. ChapterService Design

### Service ownership goal

`ChapterService` becomes the source of truth for chapter-level workflows and inventory assembly, while `FileStorageService` becomes the source of truth for path and directory operations that those workflows depend on.

Recommended new module:

- `app/services/chapter_service.py`

### Service API

Minimum public methods:

- `create_chapter`
- `rename_chapter`
- `delete_chapter`
- `list_chapters`
- `build_chapter_inventory`
- `generate_chapter_zip`

### `create_chapter`

#### Inputs

```yaml
CreateChapterCommand:
  project_id: int
  number: str
  title: str
  actor_id: int|null
```

#### Outputs

```yaml
CreateChapterResult:
  ok: bool
  chapter: Chapter|null
  project: Project|null
  directory_created: bool
  code: SUCCESS|PROJECT_NOT_FOUND|DIRECTORY_CREATE_FAILED|UNEXPECTED_ERROR
  message: str|null
```

#### Dependencies

- `Session`
- `Project`
- `Chapter`
- `FileStorageService`

#### Error cases

- project not found
- DB insert failure
- directory creation failure

#### Side effects

- insert `Chapter`
- create chapter category directory structure

### `rename_chapter`

#### Inputs

```yaml
RenameChapterCommand:
  project_id: int
  chapter_id: int
  number: str
  title: str
  actor_id: int|null
```

#### Outputs

```yaml
RenameChapterResult:
  ok: bool
  chapter: Chapter|null
  project: Project|null
  old_number: str|null
  new_number: str|null
  directory_renamed: bool
  code: SUCCESS|CHAPTER_NOT_FOUND|PROJECT_NOT_FOUND|DIRECTORY_RENAME_FAILED|UNEXPECTED_ERROR
  message: str|null
```

#### Dependencies

- `Session`
- `Project`
- `Chapter`
- `FileStorageService`

#### Error cases

- chapter not found
- project not found
- DB update failure
- directory rename failure

#### Side effects

- update chapter number/title
- rename chapter directory when number changes

### `delete_chapter`

#### Inputs

```yaml
DeleteChapterCommand:
  project_id: int
  chapter_id: int
  actor_id: int|null
```

#### Outputs

```yaml
DeleteChapterResult:
  ok: bool
  project: Project|null
  chapter_number: str|null
  directory_deleted: bool
  code: SUCCESS|CHAPTER_NOT_FOUND|PROJECT_NOT_FOUND|DIRECTORY_DELETE_FAILED|UNEXPECTED_ERROR
  message: str|null
```

#### Dependencies

- `Session`
- `Project`
- `Chapter`
- `FileStorageService`

#### Error cases

- chapter not found
- project not found
- directory delete failure
- DB delete failure

#### Side effects

- delete chapter directory tree
- delete chapter DB row

### `list_chapters`

#### Inputs

```yaml
ListChaptersQuery:
  project_id: int
```

#### Outputs

```yaml
ListChaptersResult:
  ok: bool
  project: Project|null
  chapters: list[Chapter]
  code: SUCCESS|PROJECT_NOT_FOUND
```

#### Dependencies

- `Session`
- `Project`

#### Error cases

- project not found

#### Side effects

- none

### `build_chapter_inventory`

#### Inputs

```yaml
BuildChapterInventoryQuery:
  project_id: int
```

#### Outputs

```yaml
ChapterInventoryResult:
  ok: bool
  project: Project|null
  chapters: list[ChapterInventoryItem]
  code: SUCCESS|PROJECT_NOT_FOUND
```

Where `ChapterInventoryItem` preserves current template compatibility:

```yaml
ChapterInventoryItem:
  chapter: Chapter
  has_art: bool
  has_ms: bool
  has_ind: bool
  has_proof: bool
  has_xml: bool
```

#### Dependencies

- `Session`
- `Project`
- chapter/file relationships

#### Error cases

- project not found

#### Side effects

- none

Important compatibility note:

- route wrapper may still need to attach `has_art`, `has_ms`, `has_ind`, `has_proof`, `has_xml` onto chapter-like objects or provide DTOs that the template can access with the same field names

### `generate_chapter_zip`

#### Inputs

```yaml
GenerateChapterZipCommand:
  project_id: int
  chapter_id: int
```

#### Outputs

```yaml
GenerateChapterZipResult:
  ok: bool
  temp_zip_path: str|null
  download_filename: str|null
  media_type: application/zip
  code: SUCCESS|PROJECT_NOT_FOUND|CHAPTER_NOT_FOUND|CHAPTER_DIRECTORY_NOT_FOUND|ZIP_CREATE_FAILED
  message: str|null
```

#### Dependencies

- `Session`
- `Project`
- `Chapter`
- `FileStorageService`

#### Error cases

- chapter/project not found
- chapter directory not found
- temp zip create failure

#### Side effects

- create temp zip file on disk

