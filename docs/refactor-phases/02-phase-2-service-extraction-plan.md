# Phase 2 Service Extraction Plan

No application code was modified. This phase defines the exact extraction sequence for moving business logic out of route handlers while preserving all current URLs, redirects, SSR pages, file naming rules, lock/version side effects, and integration behavior.

## Scope

This plan assumes:

- Phase-0 inventory is the baseline behavior record.
- Phase-1 contract map is the target service-boundary contract.
- No frontend migration starts in this phase.
- No auth redesign starts in this phase.
- No Celery migration starts in this phase.
- All route paths remain stable during extraction.

## Outcome of Phase 2

At the end of the implementation work described here, the codebase should still behave the same from the user’s perspective, but route handlers should no longer be the source of truth for business rules. Instead:

- routes should translate HTTP concerns only
- services should own business workflows
- compatibility wrappers should preserve legacy responses
- duplicate route logic should be ready for safe collapse
- storage, versioning, locks, processing orchestration, and WOPI path resolution should be isolated behind service boundaries

---

## 1. Extraction Principles

### Core rules

1. No URL changes in this phase.
2. No user-visible behavior changes in this phase.
3. No redirect target changes in this phase.
4. No query-message changes in this phase.
5. No file naming changes in this phase.
6. No lock/version side-effect changes in this phase.
7. No API path changes in this phase.
8. No WOPI payload redesign in this phase.

### Route-thinning rules

- Route handlers remain responsible for:
  - reading path/query/form/body/file inputs
  - resolving auth dependencies already used by the route
  - choosing template vs redirect vs JSON vs file response
  - translating service outcomes into existing legacy outputs
- Route handlers stop owning:
  - validation rules beyond HTTP-shape validation
  - cross-model business workflows
  - filesystem path construction
  - archive/version creation
  - lock orchestration
  - output registration
  - processed-file path inference
  - admin role/change guards

### Service-source-of-truth rules

- Each business workflow must have one service owner.
- If multiple routes trigger the same workflow, they must call the same service method before any route deduplication is attempted.
- Services may return normalized result objects internally even when routes still expose legacy response shapes.
- Compatibility logic belongs in route wrappers, not in the service core.

### Compatibility-wrapper rules

Compatibility wrappers must preserve:

- existing redirects
- existing query params such as `?msg=...`
- existing template names and template context keys
- current API response keys used by JS
- current status codes where callers rely on them
- current filename conventions
- current archive placement
- current output registration behavior
- current unlock-on-error behavior

### Deduplication safety rules

- Do not collapse duplicate routes until their shared logic is already centralized in a service.
- Do not combine extraction and behavior correction in the same batch.
- Where duplicate handlers contain different logic, preserve the active runtime behavior first, then queue corrections for a later normalization phase.

### WOPI rule

WOPI endpoints are excluded from payload redesign. In this phase they only get adapter isolation:

- path resolution moves behind a service
- CheckFileInfo/GetFile/PutFile payloads remain byte-for-byte compatible
- no route path changes
- no field renaming
- no auth redesign

---

## 2. Route-to-Service Handoff Map

### Auth routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /login`, `POST /login`, `GET /logout`, `GET /register`, `POST /register`, `POST /api/v1/users/login`, `POST /api/v1/users/`, `GET /api/v1/users/me` | user lookup, password verification, JWT issue, cookie issue/clear, registration, first-user admin bootstrap, role bootstrap | `AuthService` | form/query parsing, cookie set/delete, redirect/template/JSON selection | credential validation, token issue, registration, session resolution | role bootstrap extraction from SSR register into a shared registration workflow | SSR wrappers keep template errors and redirects; API wrappers keep existing JSON payloads |

### Admin routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `/admin`, `/admin/users`, `/admin/users/create`, `/admin/users/{id}/role`, `/admin/users/{id}/status`, `/admin/users/{id}/edit`, `/admin/users/{id}/password`, `/admin/users/{id}/delete`, `/admin/stats` | user listing, role listing, user creation, role change guard, last-admin protection, email update, password update, self-delete protection, summary stats | `AdminUserService` | auth dependency already attached to route, template rendering, redirects/query messages | list users/roles, create user, update role, change password, toggle status, delete user, build admin DTOs | admin route consolidation and auth hardening after compatibility coverage is complete | wrapper preserves current template names, query params, and legacy message strings |

### Dashboard and projects routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /dashboard`, `GET /projects`, `GET /api/v1/projects/`, `POST /api/v1/projects/`, `PUT /api/v1/projects/{id}/status`, `DELETE /api/v1/projects/{id}`, `GET /api/notifications`, `GET /activities` | project list, dashboard stats, project status update, delete semantics, activity/notification aggregation | `ProjectService` plus `AdminUserService` for admin-only counts where needed | page rendering, file/JSON responses, pagination query parsing | project list/read/update/delete orchestration, dashboard/activity DTO assembly | notifications/activity move into dedicated read services later if needed | wrappers preserve flat arrays, current `message` payloads, and current dashboard/activity template contexts |

### Project create route

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /projects/create`, `POST /projects/create_with_files` | project create, client name patch, chapter creation loop, filename chapter inference, category inference, directory creation, initial file save | `ProjectService` orchestrating `ChapterService` and `FileStorageService` | multipart/form parsing, redirect to `/dashboard`, GET page rendering | project creation workflow command, chapter creation workflow, initial file save workflow | creation-request normalization and optional async upload later | wrapper preserves form field names, default team assignment, redirect, and fallback chapter assignment behavior |

### Chapter routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /projects/{project_id}`, `GET /projects/{project_id}/chapters`, `POST /projects/{project_id}/chapters/create`, `POST /projects/{project_id}/chapter/{chapter_id}/rename`, `POST /projects/{project_id}/chapter/{chapter_id}/delete`, `GET /projects/{project_id}/chapter/{chapter_id}/download` | chapter read aggregation, category completeness, chapter create, directory create, chapter rename, directory rename, chapter delete, directory delete, ZIP build | `ChapterService` and `FileStorageService` | template rendering, redirect selection, file response for ZIP | chapter CRUD operations and chapter inventory DTO assembly | alias cleanup and duplicate delete collapse | wrapper preserves current URLs, success messages, ZIP filename `"{project.code}_Chapter_{chapter.number}.zip"` and path-based delete behavior |

### File upload, delete, and download routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `POST /projects/{project_id}/chapter/{chapter_id}/upload`, `POST /api/v1/files/`, `GET /projects/files/{file_id}/download`, `POST /projects/files/{file_id}/delete` | storage path construction, category normalization, replace-vs-new-file detection, overwrite, disk delete, stream file | `FileStorageService` with `VersioningService` for replace path | multipart parsing, file response, redirect/JSON selection | canonical path resolution, save/replace/delete/download operations | API upload contract cleanup and path-leak removal later | wrapper preserves redirect with `tab={category}&msg=...`, current file response names, and current API `path` field temporarily |

### Checkout and cancel-checkout routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `POST /projects/files/{file_id}/checkout`, `POST /projects/files/{file_id}/cancel_checkout` | lock acquisition, lock owner check, lock release, redirect messaging | `CheckoutLockService` | auth dependency, redirect generation | lock/unlock business rules and lock-state result mapping | stale-lock policy and broader permission model later | wrapper preserves current success/error redirect destinations and message strings |

### Processing routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `POST /api/v1/processing/files/{file_id}/process/{process_type}`, `GET /api/v1/processing/files/{file_id}/structuring_status` | permission checks, file existence check, lock orchestration, backup/version creation, background task dispatch, output registration, unlock-on-error, status polling by filename | `ProcessingWorkflowService` | path/query/body parsing, BackgroundTasks injection, JSON response formatting | permission/lock/version/orchestration logic and polling rules | persisted job model later, executor abstraction later | wrapper preserves legacy `message`/`status` start response and `completed/new_file_id` polling response |

### Technical editor routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /files/{file_id}/technical/edit`, `GET /api/v1/processing/files/{file_id}/technical/scan`, `POST /api/v1/processing/files/{file_id}/technical/apply` | file lookup, scan execution, apply execution, output registration | `TechnicalEditorService` | SSR page rendering, auth dependency, JSON response formatting | scan/apply logic and result registration | normalized suggestion DTOs later | wrapper preserves page template, current scan payload shape for the existing page JS, and `new_file_id` on apply |

### Structuring routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /api/v1/files/{file_id}/structuring/review`, `POST /api/v1/files/{file_id}/structuring/save`, `GET /api/v1/files/{file_id}/structuring/review/export` | processed-file resolution, structure extraction, Collabora URL build, explicit save-to-processed-docx, export | `StructuringReviewService` | template rendering, login redirect, JSON/file response selection | processed path resolution, export/save logic, review page DTO build | save contract normalization later, optional review metadata API later | wrapper preserves route paths, template context keys, export filename, and current `{ "status": "success" }` save response |

### WOPI routes

| Current route(s) | Current embedded business logic | Target service owner | What stays in route handler | What moves first | What moves later | Required compatibility shim |
|---|---|---|---|---|---|---|
| `GET /files/{file_id}/edit`, `GET /wopi/files/{file_id}`, `GET/POST /wopi/files/{file_id}/contents`, `GET/POST /wopi/files/{file_id}/structuring*` | target-path resolution, CheckFileInfo payload build, file byte streaming, raw body save | `WOPIAdapterService` | route paths, raw `Request` handling, direct WOPI response types | target-path resolution and metadata assembly | editor shell state preparation could share review/editor service later | wrapper preserves exact WOPI field names, status codes, and raw save behavior |

---

## 3. Service Extraction Order

### 1. AuthService

- Why at this stage:
  - every major route group depends on auth state
  - SSR and API auth already diverge, but extraction can unify business logic without redesigning auth
  - admin and project routes should not continue duplicating user lookup, credential validation, and registration logic
- Dependencies:
  - none beyond current `User`, `Role`, `UserRole` models and JWT/hash helpers
- Blockers:
  - must preserve separate cookie and bearer entry points
  - must not change how `get_current_user` and `get_current_user_from_cookie` are used yet
- Risks if extracted too early:
  - if extraction also tries to normalize auth policy, cookie/bearer behavior will drift
  - if route wrappers are not preserved, redirects and cookie issuance can break

### 2. ChapterService

- Why at this stage:
  - chapter create/rename/delete logic is isolated enough to extract without touching processing
  - chapter flows are heavily coupled to the filesystem and need a clear owner before project create and chapter detail cleanup
- Dependencies:
  - `AuthService` only for actor context, not for auth redesign
  - temporary path helpers until `FileStorageService` is extracted
- Blockers:
  - duplicate chapter delete route must not be collapsed yet
  - path policy is still route-local at the start of this step
- Risks if extracted too early:
  - if storage/path logic is moved at the same time, it becomes hard to distinguish workflow errors from path-policy errors

### 3. FileStorageService

- Why at this stage:
  - chapter and project workflows depend on stable directory resolution
  - file upload, delete, download, processed-path resolution, and ZIP operations cannot be normalized until storage policy is centralized
- Dependencies:
  - chapter/project context lookups
  - route behavior inventory from Phase-0
- Blockers:
  - must preserve category path names and current `safe_cat = category.replace(" ", "_")` behavior
  - must preserve download/export path choices
- Risks if extracted too early:
  - any path mismatch causes silent file loss, broken review flows, or broken WOPI sessions

### 4. VersioningService

- Why at this stage:
  - upload overwrite and processing start both create archives and bump versions
  - versioning is a shared workflow and should not remain duplicated
- Dependencies:
  - `FileStorageService`
  - `Project`/`Chapter` context lookup
- Blockers:
  - archive path rules must be centralized first
  - existing overwrite behavior must be frozen by tests first
- Risks if extracted too early:
  - archive naming or version-number drift breaks rollback history and activity views

### 5. CheckoutLockService

- Why at this stage:
  - file locks are mutated by checkout routes, upload overwrite, and processing start
  - lock behavior must be owned by one service before processing extraction
- Dependencies:
  - `VersioningService` not strictly required, but sequencing after it reduces intertwined mutations
  - `File` and `User` models
- Blockers:
  - current redirect messaging must stay route-specific
  - current “only owner can cancel” rule must not be loosened
- Risks if extracted too early:
  - processing and upload flows may still bypass the lock service and leave split lock semantics

### 6. ProjectService

- Why at this stage:
  - project create/delete/list/status depend on chapter and storage services
  - SSR and API project routes can only share a service after chapter/storage/versioning primitives exist
- Dependencies:
  - `ChapterService`
  - `FileStorageService`
  - `VersioningService` for delete cleanup awareness
- Blockers:
  - project delete behavior differs between SSR and API routes and must be wrapped carefully
  - project create SSR route includes optional initial uploads
- Risks if extracted too early:
  - SSR/API delete inconsistency will be accidentally cemented or changed unintentionally

### 7. AdminUserService

- Why at this stage:
  - auth helpers exist by now
  - admin routes are numerous but mostly database and validation logic, not storage or processing
  - this step also prepares duplicate admin route collapse
- Dependencies:
  - `AuthService`
- Blockers:
  - duplicate password/delete routes must stay public-compatible until tests lock behavior
  - current admin auth inconsistencies must not be “fixed” in the extraction step
- Risks if extracted too early:
  - security cleanup and service extraction can get mixed together, causing behavior changes

### 8. ProcessingWorkflowService

- Why at this stage:
  - by now storage, versioning, locks, and project/file context are centralized
  - processing is the highest-risk orchestration and depends on those lower-level services
- Dependencies:
  - `FileStorageService`
  - `VersioningService`
  - `CheckoutLockService`
  - `ProjectService` for project/chapter context
- Blockers:
  - current FastAPI `BackgroundTasks` execution must remain
  - no new job backend may be introduced here
- Risks if extracted too early:
  - output registration, unlock-on-error, and polling compatibility are likely to regress

### 9. TechnicalEditorService

- Why at this stage:
  - technical scan/apply are specialized processing-adjacent workflows
  - they reuse file context and output registration patterns but are simpler than the full processing route
- Dependencies:
  - `FileStorageService`
  - `ProjectService`/file context access
  - optionally shared output-registration helpers from `ProcessingWorkflowService`
- Blockers:
  - current JS expects the existing scan payload
- Risks if extracted too early:
  - page JS will break if the scan payload changes before a compatibility shim is in place

### 10. StructuringReviewService

- Why at this stage:
  - structuring review depends on processed naming and storage rules
  - export/save wrappers can only be centralized after processed-path resolution is stable
- Dependencies:
  - `FileStorageService`
  - `ProcessingWorkflowService` for processed-output expectations
  - optional shared WOPI URL helper
- Blockers:
  - active review flow relies on Collabora auto-save, not the manual save endpoint
- Risks if extracted too early:
  - review shell and export may diverge from actual processed-file placement

### 11. WOPIAdapterService

- Why at this stage:
  - WOPI is the most brittle integration surface
  - it should be isolated only after storage and processed-path policy are already stable
- Dependencies:
  - `FileStorageService`
  - shared processed/original target resolution from `StructuringReviewService` or a common storage policy helper
- Blockers:
  - CheckFileInfo/GetFile/PutFile contracts must remain exact
- Risks if extracted too early:
  - immediate Collabora breakage
  - hidden save failures against original or processed targets

---

## 4. Compatibility Shim Plan

Compatibility shims are temporary route-facing adapters that keep legacy inputs and outputs stable while service contracts become cleaner internally.

### AuthService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | `/login` POST sets `access_token` cookie and redirects to `/dashboard`; `/logout` clears cookie and redirects to `/login`; `/register` preserves first-user admin behavior and current template errors |
| Temporary wrapper/adaptor needed | `web.login_submit`, `web.logout`, `web.register_submit`, and `users.login` call a shared service result and translate it into either cookie+redirect or bearer JSON |
| Old inputs vs normalized service inputs | Old: form fields or OAuth2 form; New internal: `AuthenticateCommand(username, password, mode)` and `RegisterCommand(username, email, password, confirm_password, mode)` |
| Old outputs vs normalized service outputs | Old: redirect or `{access_token, token_type}`; New internal: `AuthResult(user, token, error_code, error_message)` |
| Redirect/query-message compatibility rules | Keep `/dashboard`, `/login`, `/login?msg=Registration successful! Please login.` exactly |
| API response compatibility rules | `POST /api/v1/users/login` still returns `access_token` and `token_type`; `GET /api/v1/users/me` still exposes current flat fields until later normalization |

### ChapterService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | create/rename/delete still redirect to `/projects/{id}` with the current query messages; chapter download still returns ZIP |
| Temporary wrapper/adaptor needed | route wrappers build `CreateChapterCommand`, `RenameChapterCommand`, `DeleteChapterCommand`, then convert service result to current redirects |
| Old inputs vs normalized service inputs | Old: form fields `number`, `title`; New internal: typed chapter commands with `project_id`, `chapter_id`, actor id, and redirect context omitted |
| Old outputs vs normalized service outputs | Old: redirect only; New internal: `ChapterMutationResult(project_id, chapter_id, old_number, new_number, deleted)` |
| Redirect/query-message compatibility rules | Preserve `Chapter+Created+Successfully`, `Chapter+Renamed+Successfully`, and the tested active delete message |
| API response compatibility rules | none yet; these routes stay SSR wrappers in this phase |

### FileStorageService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | chapter upload stores files in the same directories; file delete removes current file bytes; project/chapter ZIP downloads keep the same filenames and contents |
| Temporary wrapper/adaptor needed | route wrappers continue to parse uploads and return redirects/files; service methods return storage operation results without HTTP concerns |
| Old inputs vs normalized service inputs | Old: ad hoc path building with `project.code`, `chapter.number`, `category`, `upload`; New internal: `StorageTarget(project_code, chapter_number, category, filename, mode)` and upload/delete/download commands |
| Old outputs vs normalized service outputs | Old: redirects, file responses, API `{"file_id","path"}`; New internal: `StorageResult(path, filename, category, exists, bytes_written)` |
| Redirect/query-message compatibility rules | preserve `?tab={category}&msg=Files+Uploaded+Successfully` and file-delete redirect behavior |
| API response compatibility rules | `POST /api/v1/files/` may keep returning `path` temporarily even if service contract treats path as internal-only |

### VersioningService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | overwrite during upload and processing must create archive files with the same names and bump the same version fields |
| Temporary wrapper/adaptor needed | upload and processing routes call `VersioningService.archive_current_version(...)` before overwriting or processing |
| Old inputs vs normalized service inputs | Old: current `file_record`, `user`, file path, project/chapter lookup; New internal: `VersionArchiveCommand(file_id, actor_id, strategy)` |
| Old outputs vs normalized service outputs | Old: no explicit output; New internal: `VersionArchiveResult(version_num, archive_path, backup_created)` |
| Redirect/query-message compatibility rules | none directly; route wrappers continue existing redirects |
| API response compatibility rules | processing route still returns legacy start payload; upload route still redirects only |

### CheckoutLockService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | lock conflict redirects with the same message; cancel checkout remains a no-op if the user does not own the lock |
| Temporary wrapper/adaptor needed | route wrappers translate service lock outcomes into current redirects; upload and processing routes use the same lock service internally |
| Old inputs vs normalized service inputs | Old: ad hoc mutation on `File`; New internal: `LockCommand(file_id, actor_id, operation)` |
| Old outputs vs normalized service outputs | Old: redirect only or `HTTPException`; New internal: `LockResult(acquired, released, owner_id, reason)` |
| Redirect/query-message compatibility rules | preserve `File+Locked+By+Other`, `File+Checked+Out`, and `Checkout+Cancelled` |
| API response compatibility rules | processing route still maps lock-denial to current `400` with the current detail message |

### ProjectService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | dashboard/project pages still render, API list keeps current pagination, API delete keeps current JSON message, SSR delete keeps redirect and disk cleanup |
| Temporary wrapper/adaptor needed | route wrappers call service for list/create/status/delete but preserve page contexts and JSON message shapes |
| Old inputs vs normalized service inputs | Old: mixed form/query/JSON arguments; New internal: `CreateProjectCommand`, `ListProjectsQuery`, `UpdateProjectStatusCommand`, `DeleteProjectCommand(mode='api'|'ssr')` |
| Old outputs vs normalized service outputs | Old: raw ORM objects, JSON message, redirects; New internal: typed result DTOs plus delete outcome flags |
| Redirect/query-message compatibility rules | preserve `/dashboard?msg=Book+Deleted` and project-create redirect to `/dashboard` |
| API response compatibility rules | keep current flat arrays and `"message": "Project deleted successfully"` until API normalization is explicitly scheduled |

### AdminUserService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | admin pages still render the same templates; user create/edit/password/delete actions still use current redirects and query messages |
| Temporary wrapper/adaptor needed | route wrappers translate service results into current template contexts and redirects |
| Old inputs vs normalized service inputs | Old: form fields, path ids, current user from cookie; New internal: typed admin commands (`CreateUserCommand`, `ChangePasswordCommand`, `DeleteUserCommand`, `ToggleStatusCommand`, `ChangeRoleCommand`) |
| Old outputs vs normalized service outputs | Old: redirects/templates only; New internal: `AdminMutationResult(success, code, message, target_user_id)` |
| Redirect/query-message compatibility rules | preserve current success and error query params; preserve current in-template password error rendering |
| API response compatibility rules | none in this phase; admin stays SSR-wrapped |

### ProcessingWorkflowService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | processing start still returns current JSON `message/status`; structuring polling still returns `processing` or `completed + new_file_id` |
| Temporary wrapper/adaptor needed | route wrapper constructs `StartProcessingCommand` and calls service; background task calls service execution method; poll route calls service status adapter that still uses filename fallback |
| Old inputs vs normalized service inputs | Old: path params + `mode` query + optional JSON body + `BackgroundTasks`; New internal: `StartProcessingCommand(file_id, process_type, mode, actor_id)` |
| Old outputs vs normalized service outputs | Old: `{message,status}` and poll result; New internal: `ProcessingStartResult(job_ref, lock_result, version_result)` and `ProcessingStatusResult(state, output_file_id)` |
| Redirect/query-message compatibility rules | none; current processing flow is JSON + client-side redirect |
| API response compatibility rules | preserve current key names and current error detail strings where JS relies on them |

### TechnicalEditorService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | scan route must still feed the current page JS; apply route must still return `status` and `new_file_id`; page route must still render `technical_editor_form.html` |
| Temporary wrapper/adaptor needed | page route stays SSR shell; API wrappers translate service DTOs back into the current scan object and apply response |
| Old inputs vs normalized service inputs | Old: `file_id`, JSON object of replacements; New internal: `TechnicalScanCommand(file_id, actor_id)` and `TechnicalApplyCommand(file_id, actor_id, replacements)` |
| Old outputs vs normalized service outputs | Old: engine-defined scan object and `{status,new_file_id}`; New internal: normalized `items[]` plus output metadata |
| Redirect/query-message compatibility rules | page still redirects back to chapter detail after apply through existing JS |
| API response compatibility rules | keep the current scan payload shape until the page is migrated to a typed DTO |

### StructuringReviewService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | review page still renders the same template and context keys; export still streams the same processed file; save still accepts the current request shape |
| Temporary wrapper/adaptor needed | route wrapper maps service DTO to `TemplateResponse` context and converts save result to `{ "status": "success" }` |
| Old inputs vs normalized service inputs | Old: path `file_id`, arbitrary `changes` dict; New internal: `LoadStructuringReviewCommand`, `SaveStructuringChangesCommand`, `ExportStructuringCommand` |
| Old outputs vs normalized service outputs | Old: `TemplateResponse`, `{status:"success"}`, file response; New internal: typed review state and mutation/export results |
| Redirect/query-message compatibility rules | unauthenticated review/export keep redirecting to `/login` |
| API response compatibility rules | keep current save response and current 404/500 error behavior |

### WOPIAdapterService shim

| Item | Plan |
|---|---|
| Legacy route behavior that must remain unchanged | WOPI endpoints must remain path-for-path and payload-for-payload compatible with Collabora |
| Temporary wrapper/adaptor needed | current routes become thin WOPI protocol wrappers calling adapter methods for file info, bytes, and save |
| Old inputs vs normalized service inputs | Old: path `file_id`, raw request body, implicit `mode`; New internal: `WOPITarget(file_id, mode)` plus `PutFileCommand(bytes)` |
| Old outputs vs normalized service outputs | Old: WOPI JSON/file/empty 200 responses; New internal: metadata DTO, byte stream descriptor, write result |
| Redirect/query-message compatibility rules | editor shell route `/files/{file_id}/edit` keeps current login redirect and template |
| API response compatibility rules | preserve exact WOPI field names and `200/404/500` behavior |

---

## 5. Route Deduplication Plan

Route deduplication must happen only after the relevant service has already absorbed the business logic. The goal is to remove ambiguity without changing public behavior.

### Root route ownership

| Item | Plan |
|---|---|
| Duplicate set | `GET /` in `web.home` and `main.read_root` |
| Canonical handler target | `web.home` becomes the canonical public `/` owner because the application is currently user-facing and SSR-rooted |
| Logic to preserve | anonymous users redirect to `/login`; authenticated users redirect to `/dashboard`; if any automation relies on the API greeting, preserve it on an explicit compatibility endpoint before removing the duplicate root |
| Deprecation path | 1. Add regression coverage for current `/` behavior. 2. Confirm whether JSON root is externally used. 3. Move API greeting to an explicit non-conflicting endpoint only after confirming compatibility. 4. Remove duplicate `/` registration. |
| Required regression tests before collapsing | browser anonymous GET `/` -> `302 /login`; authenticated GET `/` -> `302 /dashboard`; any retained API greeting endpoint returns the same message if kept |

### Duplicate admin password handlers

| Item | Plan |
|---|---|
| Duplicate set | two `GET /admin/users/{user_id}/password` handlers and two `POST /admin/users/{user_id}/password` handlers |
| Canonical handler target | one route wrapper backed by `AdminUserService.change_password()` |
| Logic to preserve | target user lookup, password hash update, current template rendering on error, minimum length validation observed in the later handler, and the active redirect behavior observed by regression tests |
| Deprecation path | 1. Put both route bodies behind one service method. 2. Lock active runtime behavior with tests. 3. Remove the non-canonical duplicate registration. 4. Queue auth hardening for Phase-3, not this phase. |
| Required regression tests before collapsing | GET password page renders for current accessible path; invalid short password returns page error if that is the active runtime behavior; valid password updates hash and redirects to the currently active destination; not-found still returns current error/redirect behavior |

### Duplicate admin delete handlers

| Item | Plan |
|---|---|
| Duplicate set | two `POST /admin/users/{user_id}/delete` handlers |
| Canonical handler target | one route wrapper backed by `AdminUserService.delete_user()` |
| Logic to preserve | delete target user, preserve self-delete prevention if active, preserve current query-message behavior, and do not change auth policy during extraction |
| Deprecation path | 1. Centralize deletion logic in the service. 2. Test current runtime behavior. 3. Remove duplicate registration. 4. Move auth tightening to Phase-3. |
| Required regression tests before collapsing | delete non-self user behaves as currently observed; deleting self is blocked if active runtime handler enforces it; missing target produces current redirect/message behavior |

### Duplicate chapter delete handlers

| Item | Plan |
|---|---|
| Duplicate set | two `POST /projects/{project_id}/chapter/{chapter_id}/delete` handlers |
| Canonical handler target | one route wrapper backed by `ChapterService.delete_chapter()` and `FileStorageService.delete_chapter_tree()` |
| Logic to preserve | chapter directory removal, DB delete, and the active redirect query message currently observed at runtime |
| Deprecation path | 1. Move both implementations behind one service. 2. Capture the actual active redirect message with tests. 3. Remove the unused duplicate registration. |
| Required regression tests before collapsing | chapter folder removed, chapter row removed, redirect target preserved exactly, query message preserved exactly |

---

## 6. Filesystem and Versioning Extraction Plan

### Extraction objective

Centralize filesystem rules without changing the resulting paths, filenames, ZIP contents, or cleanup behavior.

### Step 1: introduce a storage policy layer inside `FileStorageService`

The first extraction is read-only path centralization. No route behavior changes yet.

The storage policy must provide canonical helpers for:

- project root: `UPLOAD_DIR/{project.code}`
- chapter root: `UPLOAD_DIR/{project.code}/{chapter.number}`
- category directory: `UPLOAD_DIR/{project.code}/{chapter.number}/{safe_category}`
- safe category rule: `category.replace(" ", "_")`
- archive directory for uploads: `{category_dir}/Archive`
- archive directory for processing: same category `Archive` if project/chapter exists, otherwise sibling `Archive`
- processed file path:
  - if current path already ends with `_Processed.docx`, use it
  - otherwise use `{name_only}_Processed.docx` in the same directory
- technical output path:
  - `{name_only}_TechEdited{ext}` in the same directory
- chapter ZIP filename:
  - `"{project.code}_Chapter_{chapter.number}.zip"`

### Step 2: move directory creation into `FileStorageService`

The following operations move next:

- project root creation during `create_project_with_files`
- chapter category directory creation during chapter create
- per-file chapter/category directory creation during upload
- chapter-number-based directory rename during chapter rename

Behavior that must remain bit-for-bit compatible:

1. chapter directories must continue to use `project.code` and `chapter.number`
2. category directories must continue to use the current raw category names on create:
   - `Manuscript`
   - `Art`
   - `InDesign`
   - `Proof`
   - `XML`
3. upload path must continue using the space-normalized `safe_cat` value
4. upload of initial project files must continue defaulting unmatched chapter numbers to `01`

### Step 3: move archive/version path generation into `VersioningService`

Rules that must remain compatible:

- archive directory name: `Archive`
- upload overwrite archive name:
  - `{existing_file_base}_v{old_version}.{ext}`
- processing backup archive name:
  - `{file_base}_v{current_version}.{ext}`
- current file remains at the same active path after upload overwrite
- `File.version` must increment the same way it does today
- `FileVersion.version_num` must store the previous active version number

### Step 4: move output naming into `FileStorageService`

Rules that must remain compatible:

- structuring output: same directory, same base name, suffix `_Processed.docx`
- technical output: same directory, same base name, suffix `_TechEdited{ext}`
- generated processing outputs from engines continue to be registered using the filenames returned by those engines

### Step 5: move ZIP generation into `FileStorageService`

Rules that must remain compatible:

- ZIP archive filename: `"{project.code}_Chapter_{chapter.number}.zip"`
- ZIP content root must remain relative to the chapter directory, not the project directory
- ZIP must include the same files and folder layout currently traversed by `os.walk(chapter_dir)`

### Step 6: move delete cleanup into `FileStorageService`

Operations to centralize:

- file delete from disk
- chapter directory tree delete
- project directory tree delete

Rules that must remain compatible:

- file delete ignores disk deletion failure and still deletes DB row if the current route does
- chapter delete removes the chapter folder before/alongside DB delete
- SSR project delete removes the project folder tree
- API project delete remains DB-only until delete semantics are unified behind `ProjectService`

### Storage compatibility guardrails

- no path separators or path casing assumptions should change beyond the current `os.path` behavior
- do not rename categories, normalize extensions, or deduplicate files differently in this phase
- do not expose storage paths more broadly than they are already exposed
- do not switch processed-file detection away from filename convention in this phase

---

## 7. Processing Orchestration Extraction Plan

### Objective

Extract processing logic from `app/routers/processing.py` into `ProcessingWorkflowService` while preserving:

- permission checks
- lock behavior
- archive/version creation
- current FastAPI `BackgroundTasks` execution
- output registration
- unlock-on-error
- current polling semantics

No executor migration happens here.

### Current processing responsibilities to move

1. process-type permission mapping
2. physical file existence validation
3. lock acquisition during process start
4. backup/version creation before processing
5. background execution dispatch
6. processor selection by `process_type`
7. generated output registration as `File` rows
8. unlock-on-success
9. unlock-on-error
10. polling by processed output lookup

### Extraction sequence

#### Step A: move preflight checks into `ProcessingWorkflowService.start_processing()`

This service method should own:

- permission evaluation
- file lookup
- physical file lookup
- lock-or-reject logic
- backup/version archive call
- background task registration payload creation

The route keeps:

- `BackgroundTasks` object injection
- parsing `file_id`, `process_type`, and `mode`
- translating service result into the current JSON payload

#### Step B: move background execution into `ProcessingWorkflowService.execute_processing_job()`

This service method should own:

- creating a fresh DB session if invoked in background context
- loading file record by id
- resolving source path
- selecting the engine by `process_type`
- calling the engine
- registering returned output files
- unlocking the source file on success
- unlocking the source file on failure

The background task wrapper keeps:

- passing primitive arguments into the service
- no business rules

#### Step C: move output registration into a helper used by all processors

This helper should own:

- MIME inference exactly as currently implemented
- creation of `models.File` rows for each generated path
- assignment of `project_id`, `chapter_id`, and `category` from the source file

#### Step D: move status polling into `ProcessingWorkflowService.get_structuring_status()`

This method must keep the current interim compatibility model:

- derive processed filename as `OriginalName_Processed.{ext}`
- query for matching `File` in same project/chapter
- return `processing` if not found
- return `completed + new_file_id` if found

### Interim compatibility model

Until a persisted job model exists:

- the start route still returns:

```json
{
  "message": "<ProcessType> started in background. The file is locked and will be updated shortly.",
  "status": "processing"
}
```

- the polling route still returns:

```json
{ "status": "processing" }
```

or

```json
{ "status": "completed", "new_file_id": 123 }
```

- failures still surface through the absence of a completed file plus current server-side logs

### Extraction do-not-change list

- do not replace `BackgroundTasks`
- do not introduce Celery here
- do not change processor names or permission mappings
- do not change output filename conventions
- do not change lock release timing
- do not add new client-visible status codes unless preserved behind compatibility response mapping

---

## 8. Regression Test Requirements

Service extraction work should not be accepted unless the relevant regression suite for that stage passes. The baseline test set should be created before the first code change and expanded as services are extracted.

### Baseline test requirement before any extraction

Create a compatibility test suite that locks:

- route status codes
- redirect destinations
- query-message strings
- template names rendered
- current file naming and archive naming
- lock state transitions
- WOPI response fields

### Stage-specific regression requirements

| Extraction stage | Required regression tests before merge |
|---|---|
| `AuthService` | `login/logout/register`: successful login sets `access_token` cookie with `Bearer ` prefix and redirects to `/dashboard`; failed login re-renders login page with error; logout clears cookie and redirects to `/login`; first registration assigns admin; second registration does not; `POST /api/v1/users/login` still returns `access_token` + `token_type`; `GET /api/v1/users/me` still returns current user data under bearer auth |
| `ChapterService` | `project create with files`: chapter rows created for `01..N`; fallback chapter assignment to `01`; `chapter create/rename/delete`: directories created, renamed, and deleted exactly; `chapter download`: ZIP filename remains `{project.code}_Chapter_{chapter.number}.zip` and archive contents remain relative to chapter directory |
| `FileStorageService` | `file upload new`: new file written to category directory and DB row created; `file download`: bytes and filename preserved; `file delete`: disk file removed and redirect goes back to chapter tab; `project create with files`: category inference and chapter inference unchanged |
| `VersioningService` | `upload/version overwrite`: overwriting an existing file creates `Archive/{base}_v{old_version}.{ext}`, inserts `FileVersion`, increments active version, and keeps active path stable; `processing backup`: processing start creates same archive naming and version row behavior |
| `CheckoutLockService` | `checkout/cancel checkout`: owner checkout succeeds, non-owner conflict returns current redirect message, owner cancel unlocks, non-owner cancel is a no-op; `upload overwrite` still releases lock exactly as today; `processing start` still rejects when another user holds the lock |
| `ProjectService` | `dashboard/projects`: dashboard and project list still render with current context expectations; `project create with files` remains intact; `project delete SSR`: project directory removed and redirect remains `/dashboard?msg=Book+Deleted`; `project delete API`: JSON message preserved and current DB-only semantics remain until unified later |
| `AdminUserService` | `admin password/delete flows`: active password route renders page, invalid password shows current error behavior, valid password updates hash, delete flow preserves current self-delete and missing-user handling; `admin create/edit/role/status` flows preserve template rendering and redirect/query messages |
| `ProcessingWorkflowService` | `processing start/status`: start returns legacy `{message,status}`; permission denial still produces current `403`; missing file still produces current `404`; backup/version still created; lock released on success and on error; status route still returns `processing` until `_Processed` file record exists, then `completed/new_file_id` |
| `TechnicalEditorService` | `technical scan`: response shape still feeds current page JS; `technical apply`: `_TechEdited` file is created in the same directory, new `File` row registered, response still returns `status` + `new_file_id`, page redirect path remains valid |
| `StructuringReviewService` | `structuring review`: review page resolves processed path the same way, missing processed file renders current error template, save endpoint still accepts current request shape, export still streams the processed DOCX with the same filename |
| `WOPIAdapterService` | `WOPI open/save`: CheckFileInfo returns current required fields; GetFile returns exact bytes; PutFile overwrites file and returns `200`; structuring mode endpoints target `_Processed.docx`; editor shell and structuring review still generate valid Collabora URLs |
| `Route deduplication` | `root route ownership`: `/` behavior remains exactly as locked by tests; duplicate admin password/delete routes still behave the same after collapse; duplicate chapter delete route still deletes folder and DB row and returns the active redirect/message |

### Mandatory named regression flows

The following flows must exist as executable regression coverage before the full extraction program is considered safe:

1. login/logout/register
2. admin password/delete flows
3. project create with files
4. chapter create/rename/delete
5. upload/version overwrite
6. checkout/cancel checkout
7. processing start/status
8. technical scan/apply
9. structuring review/export
10. WOPI open/save
11. project delete and file delete

---

## 9. Deliverable Batches

The safest implementation approach is a batch model where each batch ends at a stable stopping point and leaves the application deployable.

### Batch 1

| Item | Value |
|---|---|
| Target service(s) | `AuthService` |
| Route files touched | `app/auth.py`, `app/rbac.py`, `app/routers/web.py`, `app/routers/users.py` |
| Risk level | Medium |
| Required tests | login/logout/register; bearer login; `/api/v1/users/me` |
| Expected outcome | all auth workflows call `AuthService`, but routes still set cookies, render templates, and return current JSON payloads |
| Safe stopping point | cookie and bearer routes share service logic, but route signatures and auth dependencies are unchanged |

### Batch 2

| Item | Value |
|---|---|
| Target service(s) | `ChapterService`, initial `FileStorageService` path policy |
| Route files touched | `app/routers/web.py`, `app/services/file_service.py` or new storage service module |
| Risk level | High |
| Required tests | project create with files; chapter create/rename/delete; chapter ZIP download |
| Expected outcome | chapter CRUD and chapter-path generation are service-owned, but redirects and ZIP/file outputs remain identical |
| Safe stopping point | chapter routes are thin wrappers; upload/versioning logic still partly route-owned |

### Batch 3

| Item | Value |
|---|---|
| Target service(s) | full `FileStorageService`, `VersioningService` |
| Route files touched | `app/routers/web.py`, `app/routers/processing.py`, `app/services/file_service.py` or replacement modules |
| Risk level | High |
| Required tests | file upload new; upload/version overwrite; file download; file delete; project create with files regression |
| Expected outcome | storage path resolution, archive naming, delete cleanup, and download/ZIP helpers are centralized |
| Safe stopping point | file operations and versioning are shared services; checkout and processing still use route wrappers |

### Batch 4

| Item | Value |
|---|---|
| Target service(s) | `CheckoutLockService` |
| Route files touched | `app/routers/web.py`, `app/routers/processing.py` |
| Risk level | High |
| Required tests | checkout/cancel checkout; upload overwrite with lock; processing start lock conflict |
| Expected outcome | all lock acquisition/release flows call one service, but current redirects and error details remain unchanged |
| Safe stopping point | lock state is no longer mutated directly in route code except through the service |

### Batch 5

| Item | Value |
|---|---|
| Target service(s) | `ProjectService` |
| Route files touched | `app/services/project_service.py`, `app/routers/projects.py`, `app/routers/web.py` |
| Risk level | Medium-High |
| Required tests | dashboard/projects pages; project API list/create/status/delete; SSR project delete; project create with files regression |
| Expected outcome | project list/create/status/delete workflows are centralized without changing page URLs or current API shapes |
| Safe stopping point | SSR and API project routes call `ProjectService`, but delete semantics are still compatibility-wrapped if not yet unified |

### Batch 6

| Item | Value |
|---|---|
| Target service(s) | `AdminUserService` |
| Route files touched | `app/routers/web.py` |
| Risk level | Medium |
| Required tests | admin dashboard/users/stats; create/edit/password/delete; role/status change |
| Expected outcome | admin mutations and page DTO assembly move to `AdminUserService`; duplicate admin route bodies can now call one service |
| Safe stopping point | duplicate route registrations still exist if desired, but they are delegating to the same service logic |

### Batch 7

| Item | Value |
|---|---|
| Target service(s) | `ProcessingWorkflowService`, `TechnicalEditorService` |
| Route files touched | `app/routers/processing.py`, `app/routers/web.py` |
| Risk level | Very High |
| Required tests | processing start/status; archive/version on processing; unlock-on-error; technical scan/apply |
| Expected outcome | processing route and background task become orchestration wrappers; technical scan/apply logic is service-owned; current `BackgroundTasks` model remains |
| Safe stopping point | processing remains operational with the same JSON contracts and the same filename-based polling |

### Batch 8

| Item | Value |
|---|---|
| Target service(s) | `StructuringReviewService`, `WOPIAdapterService` |
| Route files touched | `app/routers/structuring.py`, `app/routers/wopi.py`, optionally `app/routers/web.py` for shared shell helpers |
| Risk level | Very High |
| Required tests | structuring review/export/save; WOPI open/save for original and processed files |
| Expected outcome | processed-file resolution and WOPI target resolution are isolated without changing route paths or payloads |
| Safe stopping point | review/export/editor shells remain SSR wrappers; WOPI endpoints remain protocol-compatible |

### Batch 9

| Item | Value |
|---|---|
| Target service(s) | route deduplication using already-extracted services |
| Route files touched | `app/main.py`, `app/routers/web.py` |
| Risk level | High |
| Required tests | root route ownership; admin password/delete duplicates; chapter delete duplicate; full smoke suite across earlier extracted flows |
| Expected outcome | one canonical handler per duplicate route path, with identical public behavior validated by regression tests |
| Safe stopping point | duplicate handlers are removed, but auth policy and broader contract normalization are still deferred to the next phase |

### Batch delivery rule

Do not start a higher-risk batch unless:

1. the previous batch has regression coverage in place
2. service ownership is already established for the lower-level dependency
3. the application is deployable at the end of the batch

---

## 10. Recommended Next Phase

The next document should be:

`03-phase-3-auth-normalization-plan.md`

### Why Phase-3 should focus on auth/session normalization

After service extraction:

- auth logic will be centralized
- duplicate route bodies will be reduced or ready for reduction
- SSR and API routes will already call shared services

That is the correct point to define:

- the canonical session model
- cookie vs bearer policy
- CORS tightening
- CSRF strategy
- route-level auth consistency
- admin-route authorization normalization

### What Phase-3 should not do yet

- no frontend scaffolding
- no execution-backend migration
- no global API path rewrite
- no template removal

### Phase-3 starting assumption

By the end of Phase-2 implementation, route handlers should be thin enough that auth normalization can happen as a contract exercise, not as a route-rewrite exercise.

