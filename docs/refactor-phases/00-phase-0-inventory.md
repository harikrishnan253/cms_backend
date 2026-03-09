# Phase 0 Inventory

No code changes were made.

## Scope
This Phase-0 inventory covers the FastAPI app mounted in `app/main.py`, the route modules under `app/routers`, the templates under `app/templates`, and runtime/background integration points. It does not inventory Flask routes inside `ai_structuring_backend` as first-class app routes, but it does document where the FastAPI CMS depends on that service.

## Legend
- Auth: `P` public, `C` cookie JWT via `get_current_user_from_cookie`, `C+A` cookie JWT plus inline admin gate, `B` bearer JWT via `get_current_user`, `B+R` bearer JWT plus `require_role`, `-` no auth / integration callback
- Type: `SSR` template/redirect flow, `JSON` JSON response, `Mixed` file/binary/WOPI/integration endpoint
- Migration target tags are inventory tags only: `keep SSR`, `hybrid`, `typed FE module`, `API-only`, `n/a inactive`

## 1. Route Inventory

### Routes from `app/main.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/` | GET | `main.py::read_root` | JSON | P | - | none; duplicate root registered after `web.home` | - | - | - | - | API-only |

### Routes from `app/routers/users.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/v1/users/` | POST | `users.py::create_user` | JSON | P | - | `user_service.get_user_by_username`; `user_service.create_user` | `User` | - | - | - | API-only |
| `/api/v1/users/login` | POST | `users.py::login` | JSON | P | - | `user_service.get_user_by_username`; `verify_password`; `create_access_token` | `User` | - | - | - | API-only |
| `/api/v1/users/me` | GET | `users.py::read_users_me` | JSON | B | - | `get_current_user` | `User`, `Role` | - | - | - | API-only |

### Routes from `app/routers/teams.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/v1/teams/` | POST | `teams.py::create_team` | JSON | B | - | `team_service.create_team` | `Team`, `User(auth)` | - | - | - | API-only |
| `/api/v1/teams/` | GET | `teams.py::read_teams` | JSON | B | - | `team_service.get_teams` | `Team`, `User(auth)` | - | - | - | API-only |

### Routes from `app/routers/projects.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/v1/projects/` | POST | `projects.py::create_project` | JSON | B+R(ProjectManager) | - | `project_service.create_project` | `Project` | - | - | - | API-only |
| `/api/v1/projects/` | GET | `projects.py::read_projects` | JSON | B | - | `project_service.get_projects` | `Project` | - | - | - | API-only |
| `/api/v1/projects/{project_id}/status` | PUT | `projects.py::update_project_status` | JSON | B+R(ProjectManager) | - | `project_service.update_project_status` | `Project` | - | - | - | API-only |
| `/api/v1/projects/{project_id}` | DELETE | `projects.py::delete_project` | JSON | C | - | `project_service.delete_project_v2` | `Project`, `Chapter`, `File`, `FileVersion`, `User(auth)` | DB delete only; no disk cleanup | - | - | API-only |

### Routes from `app/routers/files.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/v1/files/` | POST | `files.py::upload_file` | JSON | B | - | `file_service.create_file_record` | `File`, `User(auth)` | saves flat upload under runtime `UPLOAD_DIR` | - | - | API-only |

### Routes from `app/routers/processing.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/v1/processing/files/{file_id}/process/{process_type}` | POST | `processing.py::run_file_process` | JSON | C | - | `check_permission`; file lock logic; archive/version logic; `background_processing_task` dispatch | `User`, `Role`, `File`, `FileVersion`, `Project`, `Chapter` | reads source file; creates `Archive`; writes versions; registers outputs | `FastAPI BackgroundTasks` | legacy processors; optional AI structuring HTTP; Gemini; LibreOffice; Perl/Java Word2XML | API-only |
| `/api/v1/processing/files/{file_id}/structuring_status` | GET | `processing.py::check_structuring_status` | JSON | C | - | processed-file lookup by naming convention | `User`, `File` | no direct disk scan; DB lookup by `_Processed` filename | - | - | API-only |
| `/api/v1/processing/files/{file_id}/technical/scan` | GET | `processing.py::scan_technical_errors` | JSON | C | - | `check_permission`; `TechnicalEditor.scan` | `User`, `Role`, `File` | reads DOCX from file path | - | - | API-only |
| `/api/v1/processing/files/{file_id}/technical/apply` | POST | `processing.py::apply_technical_edits` | JSON | C | - | `check_permission`; `TechnicalEditor.process` | `User`, `Role`, `File` plus new `File` row | writes `_TechEdited` DOCX beside original | - | - | API-only |

### Routes from `app/routers/structuring.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/v1/files/{file_id}/structuring/review` | GET | `structuring.py::review_structuring` | SSR | C | `structuring_review.html` or `error.html` | `extract_document_structure`; `get_rules_loader`; WOPI URL builder | `User`, `File` | resolves original vs `_Processed` file path | - | Collabora/WOPI | hybrid |
| `/api/v1/files/{file_id}/structuring/save` | POST | `structuring.py::save_structuring_changes` | JSON | C | - | `update_document_structure` | `User`, `File` | updates processed DOCX in place | - | - | API-only |
| `/api/v1/files/{file_id}/structuring/review/export` | GET | `structuring.py::export_structuring` | Mixed | C | - | file export helper | `User`, `File` | streams processed DOCX | - | - | API-only |

### Routes from `app/routers/web.py`: auth and landing

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/` | GET | `web.py::home` | SSR | C(optional) | - | redirect logic via `get_current_user_from_cookie`; duplicates `main.read_root` | `User(auth)` | - | - | - | keep SSR |
| `/login` | GET | `web.py::login_page` | SSR | P | `login.html` | none | - | - | - | - | keep SSR |
| `/login` | POST | `web.py::login_submit` | SSR | P | `login.html` on error; redirect on success | `db.query(User)`; `verify_password`; `create_access_token`; `response.set_cookie` | `User` | sets auth cookie only | - | - | keep SSR |
| `/logout` | GET | `web.py::logout` | SSR | C | - | clears cookie; redirect | - | deletes auth cookie only | - | - | keep SSR |
| `/register` | GET | `web.py::register_page` | SSR | P | `register.html` | none | - | - | - | - | keep SSR |
| `/register` | POST | `web.py::register_submit` | SSR | P | `register.html` on error; redirect on success | password confirm; user uniqueness; inline role bootstrap; `hash_password` | `User`, `Role` | - | - | - | keep SSR |

### Routes from `app/routers/web.py`: dashboard and admin

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/dashboard` | GET | `web.py::dashboard` | SSR | C | `dashboard.html` | `project_service.get_projects`; inline stats assembly | `User(auth)`, `Project` | - | - | - | hybrid |
| `/projects` | GET | `web.py::projects_list` | SSR | C | `projects.html` | `project_service.get_projects` | `User(auth)`, `Project` | - | - | - | hybrid |
| `/projects/create` | GET | `web.py::create_project_page` | SSR | C | `project_create.html` | none | `User(auth)` | - | - | - | hybrid |
| `/admin` | GET | `web.py::admin_dashboard` | SSR | C+A | `admin_dashboard.html` | inline counts | `User(auth)`, `User`, `File` | - | - | - | keep SSR |
| `/admin/users/create` | GET | `web.py::admin_create_user_page` | SSR | C+A | `admin_create_user.html` | role lookup | `User(auth)`, `Role` | - | - | - | keep SSR |
| `/admin/users/create` | POST | `web.py::admin_create_user_submit` | SSR | C+A | `admin_create_user.html` on error; redirect on success | uniqueness check; `hash_password`; role assignment | `User(auth)`, `User`, `Role` | - | - | - | keep SSR |
| `/admin/users` | GET | `web.py::admin_users` | SSR | C+A | `admin_users.html` | inline user/role queries | `User(auth)`, `User`, `Role` | - | - | - | keep SSR |
| `/admin/users/{user_id}/role` | POST | `web.py::update_user_role` | SSR | C+A | `admin_users.html` on last-admin error; redirect otherwise | target user/role lookup; last-admin protection | `User(auth)`, `User`, `Role`, `UserRole` | - | - | - | keep SSR |
| `/admin/users/{user_id}/delete` | POST | `web.py::admin_delete_user` (first) | SSR | C | - | delete target user; no admin gate | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/users/{user_id}/status` | POST | `web.py::toggle_user_status` | SSR | C+A | - | toggle `is_active` | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/stats` | GET | `web.py::admin_stats` | SSR | C+A | `admin_stats.html` | inline aggregate counts and role breakdown | `User(auth)`, `User`, `Project`, `Chapter`, `File`, `Role`, `UserRole` | - | - | - | keep SSR |
| `/admin/users/{user_id}/password` | GET | `web.py::admin_change_password_page` (first) | SSR | C+A | `admin_change_password.html` | target user lookup | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/users/{user_id}/password` | POST | `web.py::admin_change_password_submit` (first) | SSR | C+A | - | `hash_password`; redirect | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/users/{user_id}/edit` | GET | `web.py::admin_edit_user_page` | SSR | C | `admin_edit_user.html` | target user + roles lookup; no admin gate | `User(auth)`, `User`, `Role` | - | - | - | keep SSR |
| `/admin/users/{user_id}/edit` | POST | `web.py::admin_edit_user` | SSR | C | - | `await request.form()`; email update; no admin gate | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/users/{user_id}/password` | GET | `web.py::admin_change_password_page` (second duplicate) | SSR | C | `admin_change_password.html` | target user lookup; duplicate route registration | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/users/{user_id}/password` | POST | `web.py::admin_change_password` (second duplicate) | SSR | C | `admin_change_password.html` on short password; redirect otherwise | `await request.form()`; min-length check; duplicate route registration | `User(auth)`, `User` | - | - | - | keep SSR |
| `/admin/users/{user_id}/delete` | POST | `web.py::admin_delete_user` (second duplicate) | SSR | C | - | duplicate route registration | `User(auth)`, `User` | - | - | - | keep SSR |

### Routes from `app/routers/web.py`: project, chapter, file workspace

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/projects/create_with_files` | POST | `web.py::create_project_with_files` | SSR | C | - | `project_service.create_project`; filename chapter-number inference | `User(auth)`, `Project`, `Chapter`, `File` | creates project/chapter/category folders; saves initial uploads | - | - | hybrid |
| `/projects/{project_id}` / `/projects/{project_id}/chapters` | GET | `web.py::project_chapters` | SSR | C | `project_chapters.html` | inline chapter/category aggregation | `User(auth)`, `Project`, `Chapter`, `File` | - | - | - | hybrid |
| `/projects/{project_id}/chapters/create` | POST | `web.py::create_chapter` | SSR | C | - | inline chapter create | `User(auth)`, `Project`, `Chapter` | creates chapter category dirs | - | - | hybrid |
| `/projects/{project_id}/chapter/{chapter_id}/rename` | POST | `web.py::rename_chapter` | SSR | C | - | inline rename | `User(auth)`, `Project`, `Chapter` | renames chapter folder if number changed | - | - | hybrid |
| `/projects/{project_id}/chapter/{chapter_id}/download` | GET | `web.py::download_chapter_zip` | Mixed | C | - | temp ZIP creation | `User(auth)`, `Project`, `Chapter` | zips entire chapter directory and streams it | - | - | API-only |
| `/projects/{project_id}/chapter/{chapter_id}/delete` | POST | `web.py::delete_chapter` (first) | SSR | C | - | delete chapter then redirect | `User(auth)`, `Project`, `Chapter` | deletes chapter folder tree | - | - | hybrid |
| `/projects/{project_id}/chapter/{chapter_id}` | GET | `web.py::chapter_detail` | SSR | C | `chapter_detail.html` | file listing by chapter; tab state | `User(auth)`, `Project`, `Chapter`, `File` | - | - | - | typed FE module |
| `/projects/{project_id}/chapter/{chapter_id}/upload` | POST | `web.py::upload_chapter_files` | SSR | C | - | inline upload/version/archive/check-in logic | `User(auth)`, `Project`, `Chapter`, `File`, `FileVersion` | saves uploads by category; archives old versions; overwrites current files | - | - | typed FE module |
| `/projects/files/{file_id}/download` | GET | `web.py::download_file` | Mixed | C | - | file lookup + stream | `User(auth)`, `File` | streams file path | - | - | API-only |
| `/projects/files/{file_id}/delete` | POST | `web.py::delete_file` | SSR | C | - | delete row then redirect | `User(auth)`, `File` | removes file from disk if present | - | - | typed FE module |
| `/projects/{project_id}/delete` | POST | `web.py::delete_project` | SSR | C | - | inline project delete | `User(auth)`, `Project` | deletes project folder tree; DB delete via relationship cascade | - | - | hybrid |
| `/projects/{project_id}/chapter/{chapter_id}/delete` | POST | `web.py::delete_chapter` (second duplicate) | SSR | C | - | duplicate route registration | `User(auth)`, `Project`, `Chapter` | deletes chapter folder tree | - | - | hybrid |
| `/projects/files/{file_id}/checkout` | POST | `web.py::checkout_file` | SSR | C | - | inline lock assignment | `User(auth)`, `File` | - | - | - | typed FE module |
| `/projects/files/{file_id}/cancel_checkout` | POST | `web.py::cancel_checkout` | SSR | C | - | inline unlock | `User(auth)`, `File` | - | - | - | typed FE module |

### Routes from `app/routers/web.py`: utilities and editor entry points

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/notifications` | GET | `web.py::get_notifications_data` | JSON | C | - | recent file query; time-ago formatting | `User(auth)`, `File` | - | - | - | API-only |
| `/activities` | GET | `web.py::activities_page` | SSR | C | `activities.html` | recent file + version queries; inline merge/sort | `User(auth)`, `File`, `FileVersion`, `Project`, `Chapter` | - | - | - | hybrid |
| `/files/{file_id}/technical/edit` | GET | `web.py::technical_editor_page` | SSR | C | `technical_editor_form.html` | file lookup only; page relies on processing APIs after load | `User(auth)`, `File` | - | - | - | typed FE module |

### Routes from `app/routers/wopi.py`

| Path | Method | Fn | Type | Auth | Template | Backend deps | DB models touched | FS/storage | BG/queue | External | Target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/files/{file_id}/edit` | GET | `wopi.py::edit_file_page` | SSR | C | `editor.html` | WOPI URL builder | `User(auth)`, `File` | - | - | Collabora/WOPI | hybrid |
| `/wopi/files/{file_id}` | GET | `wopi.py::wopi_check_file_info` | JSON | - | - | `_get_target_path`; stat; SHA-256 version token | `File` | reads file metadata/hash | - | Collabora/WOPI | API-only |
| `/wopi/files/{file_id}/contents` | GET | `wopi.py::wopi_get_file` | Mixed | - | - | `_get_target_path` | `File` | streams original file bytes | - | Collabora/WOPI | API-only |
| `/wopi/files/{file_id}/contents` | POST | `wopi.py::wopi_put_file` | Mixed | - | - | `_get_target_path`; raw body write | `File` | overwrites original file bytes | - | Collabora/WOPI | API-only |
| `/wopi/files/{file_id}/structuring` | GET | `wopi.py::wopi_check_file_info_structuring` | JSON | - | - | `_get_target_path(mode='structuring')`; stat; SHA-256 | `File` | reads processed file metadata/hash | - | Collabora/WOPI | API-only |
| `/wopi/files/{file_id}/structuring/contents` | GET | `wopi.py::wopi_get_file_structuring` | Mixed | - | - | `_get_target_path(mode='structuring')` | `File` | streams processed file bytes | - | Collabora/WOPI | API-only |
| `/wopi/files/{file_id}/structuring/contents` | POST | `wopi.py::wopi_put_file_structuring` | Mixed | - | - | `_get_target_path(mode='structuring')`; raw body write | `File` | overwrites processed file bytes | - | Collabora/WOPI | API-only |

## 2. Template Inventory

### Layouts and active templates

| Template | Routes that render it | Parent layout | Context variables expected | Forms / actions / URLs used | Embedded JS dependencies | Coupling risks | Migration target |
|---|---|---|---|---|---|---|---|
| `base.html` | not rendered directly; parent for `admin_edit_user.html` and many `.bak` files | standalone layout | `request`, `user`, optional `error` | nav links `/dashboard`, `/activities`, `/admin`, `/logout`; notifications link | Bootstrap CDN, Font Awesome, Chart.js, `fetch('/api/notifications')` | older layout stack; hardcoded URLs; only partly aligned with active Tailwind UI | keep SSR |
| `base_tailwind.html` | not rendered directly; parent for most active pages | standalone layout | `request`, `user` | sidebar links `/dashboard`, `/projects`, `/activities`, `/admin*`, `/logout`, dead link `/reports` | Tailwind CDN, Font Awesome, inline `showToast`, sidebar state | global nav hardcodes route paths and admin assumptions; dead route links; page shell owns app IA | keep SSR |
| `login.html` | `/login` GET; `/login` POST on failure | standalone | `request`, optional `error` | form POST `/login`; link `/register` | Tailwind CDN, Font Awesome | cookie login flow is hardcoded; query-string success message contract | keep SSR |
| `register.html` | `/register` GET; `/register` POST on failure | standalone | optional `error` | form POST `/register`; link `/login` | Tailwind CDN, Font Awesome | role bootstrap and first-user admin semantics live in route, not template, but template depends on same form fields | keep SSR |
| `dashboard.html` | `/dashboard` | `base_tailwind.html` | `request`, `user`, `projects`, `dashboard_stats`, `initial_view?` | links to `/admin*`, project detail links, JS modal with no real POST action | large inline JS; local view state; `showToast`; placeholder create/edit/delete | expects injected data shape and `initial_view` that route does not supply; placeholder backend actions; mixed server/client state | hybrid |
| `projects.html` | `/projects` | `base_tailwind.html` | `request`, `user`, `projects` | link `/projects/create`; links `/projects/{id}`; JS delete hits `/api/v1/projects/{id}` | inline `fetch(...DELETE...)` | hardcoded API path, delete depends on cookie-auth API despite `api/v1` namespace | hybrid |
| `project_create.html` | `/projects/create` | `base_tailwind.html` | `request`, `user` | form POST `/projects/create_with_files`; back link `/projects` | inline file-list preview JS | field names, client list, XML options, and upload contract are all route-coupled | hybrid |
| `project_chapters.html` | `/projects/{project_id}` and `/projects/{project_id}/chapters` | `base_tailwind.html` | `request`, `user`, `project`, `chapters`, `current_date?` | form POST `/projects/{id}/chapters/create`; rename form posts `/projects/{id}/chapter/{id}/rename`; delete form; download ZIP links | inline view toggle, modal open/close, context-menu JS | expects `current_date` that route does not provide; hardcoded path strings; chapter operations assume filesystem naming | hybrid |
| `chapter_detail.html` | `/projects/{project_id}/chapter/{chapter_id}` | `base_tailwind.html` | `request`, `user`, `project`, `chapter`, `files`, `active_tab` | file download/delete/checkout/cancel routes; upload forms; links `/files/{id}/edit`; `/files/{id}/technical/edit` | heavy inline JS; `fetch` to `/api/v1/processing/...`; status polling; redirect to structuring review | most coupled template in repo: category-specific UI duplication, hardcoded URLs, implicit cookie auth, polling contract, lock/version semantics in UI | typed FE module |
| `activities.html` | `/activities` | `base_tailwind.html` | `request`, `user`, `activities`, `today_count` | back link `/dashboard` | minimal inline behavior | display depends on route assembling merged activity DTOs, not reusable API | hybrid |
| `admin_dashboard.html` | `/admin` | `base_tailwind.html` | `request`, `user`, `admin_stats` | links `/admin/users`, `/admin/stats` | none beyond layout JS | admin counts and shortcuts depend entirely on route-side inline aggregation | keep SSR |
| `admin_users.html` | `/admin/users`; `/admin/users/{id}/role` on error | `base_tailwind.html` | `request`, `user`, `current_user`, `users`, `all_roles`, optional `error` | form POST `/admin/users/{id}/role`; link `/admin/users/create`; link `/admin/users/{id}/edit`; link `/admin/users/{id}/password`; form POST `/admin/users/{id}/delete` | conditional toast script using query params / `error` | tightly bound to inline admin role semantics; uses server redirects and query-string messages as state transport | keep SSR |
| `admin_create_user.html` | `/admin/users/create` GET and POST on error | `base_tailwind.html` | `request`, `user`, `roles`, optional `error` | form POST `/admin/users/create`; back link `/admin/users` | none beyond layout JS | role dropdown contract tied to route-provided `roles`; no client/API separation | keep SSR |
| `admin_edit_user.html` | `/admin/users/{id}/edit` GET | `base.html` | `user`, `target` | form POST `/admin/users/{id}/edit`; link `/admin/users` | only `base.html` JS | only active page still on old Bootstrap base; auth assumptions differ from rest of admin area | keep SSR |
| `admin_change_password.html` | `/admin/users/{id}/password` GET; second duplicate GET; second duplicate POST on error | `base_tailwind.html` | `request`, `user`, `target_user` | form POST `/admin/users/{id}/password`; back link `/admin/users` | none beyond layout JS | duplicate handlers use different context variable names (`target_user` vs `target`) and authorization gates | keep SSR |
| `admin_stats.html` | `/admin/stats` | `base_tailwind.html` | `request`, `user`, `stats` | back link `/dashboard` | none beyond layout JS | chart/card data is route-assembled and not available as standalone API | keep SSR |
| `editor.html` | `/files/{file_id}/edit` | `base_tailwind.html` | `request`, `user`, `file`, `filename`, `collabora_url` | exit button only; iframe points to Collabora URL | iframe-based WOPI shell | route/template contract depends on exact WOPI URL building and env config | hybrid |
| `structuring_review.html` | `/api/v1/files/{id}/structuring/review` | `base_tailwind.html` | `request`, `user`, `file`, `filename`, `collabora_url` | export link via `url_for('export_structuring')`; save/exit redirects to chapter/project | minimal JS; relies on Collabora auto-save | active template no longer uses manual `save` API even though backend route exists; path is HTML under API prefix | hybrid |
| `technical_editor_form.html` | `/files/{file_id}/technical/edit` | `base_tailwind.html` | `request`, `user`, `file` | back link to chapter; fetch scan/apply endpoints under `/api/v1/processing/files/...` | inline fetch/render/apply JS | explicit dependency on processing API payload shape; page is already a client module embedded in Jinja shell | typed FE module |
| `error.html` | structuring review errors | `base_tailwind.html` | `request`, `error_message` | back via browser history | none | generic fallback only; error contract is string-based | keep SSR |

### Inactive drafts and backups

| Template | Routes that render it | Parent layout | Context variables expected | Forms / actions / URLs used | Embedded JS dependencies | Coupling risks | Migration target |
|---|---|---|---|---|---|---|---|
| `dashboard_New.html` | none | standalone | broadly same as `dashboard.html` | same dashboard/project links and placeholder actions | large inline dashboard JS | unrendered draft can diverge from active dashboard behavior | n/a inactive |
| `activities.html.bak` | none | `base.html` | same domain data as active `activities.html` | same activity navigation pattern | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `admin_change_password.html.bak` | none | `base.html` | same as active password page | same password POST route | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `admin_create_user.html.bak` | none | `base.html` | same as active create-user page | same create-user POST route | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `admin_dashboard.html.bak` | none | `base.html` | same as active admin dashboard | same admin links | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `admin_stats.html.bak` | none | `base.html` | same as active admin stats | same admin links | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `admin_users.html.bak` | none | `base.html` | same as active admin users page | same user role/status/delete routes | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `chapter_detail.html.bak` | none | `base.html` | same as active chapter detail page | same file actions and processing fetches | older Bootstrap/vanilla JS | stale duplicate of most complex page | n/a inactive |
| `dashboard.html.bak` | none | standalone | same as active dashboard plus draft-only fields | placeholder modal JS | large standalone JS bundle | unrendered duplicate with placeholder backend calls | n/a inactive |
| `login.html.bak` | none | `base.html` | same as active login page | form POST `/login` | older Bootstrap/vanilla JS | stale duplicate of auth page | n/a inactive |
| `project_chapters.html.bak` | none | `base.html` | same as active project chapters page | same chapter create/rename/delete routes | older Bootstrap/vanilla JS | stale duplicate of active page | n/a inactive |
| `register.html.bak` | none | `base.html` | same as active register page | form POST `/register` | older Bootstrap/vanilla JS | stale duplicate of auth page | n/a inactive |
| `structuring_review.html.bak` | none | standalone | `file`, review structure data, request | manual form/fetch to `/api/v1/files/{id}/structuring/save`; download/go-back links | legacy manual review JS | stale UI still reflects older save model than active Collabora-only review | n/a inactive |

## 3. Workflow Inventory

### Login / logout / register
1. `GET /login` renders `login.html`.
2. `POST /login` reads `username` and `password`, loads `User`, verifies bcrypt hash, creates JWT, stores it in `access_token` cookie as `Bearer <jwt>`, then redirects to `/dashboard`.
3. Failed login re-renders `login.html` with `error`.
4. `GET /logout` clears `access_token` cookie and redirects to `/login`.
5. `GET /register` renders `register.html`.
6. `POST /register` validates password match and username/email uniqueness, bootstraps core roles if needed, creates `User`, assigns `Admin` to first user or `Viewer` otherwise, then redirects to `/login?msg=...`.

### Dashboard / projects
1. `GET /dashboard` requires cookie auth.
2. Route loads up to 100 projects via `project_service.get_projects`.
3. Route computes placeholder dashboard metrics in memory and passes `user`, `projects`, `dashboard_stats` to `dashboard.html`.
4. `dashboard.html` renders summary cards and project list data, but create/edit/delete actions are still placeholder JS and do not call real backend handlers.
5. `GET /projects` requires cookie auth, loads projects, and renders `projects.html`.
6. `projects.html` links to project detail pages and deletes projects through `fetch('/api/v1/projects/{id}', { method: 'DELETE', credentials: 'include' })`.

### Project creation
1. `GET /projects/create` renders `project_create.html`.
2. User submits form to `POST /projects/create_with_files` with `code`, `title`, `client_name`, `xml_standard`, `chapter_count`, and optional files.
3. Route creates `Project` through `project_service.create_project`, then writes `client_name` directly afterward.
4. Route creates numbered `Chapter` rows `01..N`.
5. Route creates directory tree `UPLOAD_DIR/{project_code}/{chapter}/{category}`.
6. Route infers category from extension and chapter number from filename regex.
7. Route writes uploaded files to disk and inserts `File` rows.
8. Route redirects to `/dashboard`.

### Chapter creation and management
1. `GET /projects/{project_id}` or `/projects/{project_id}/chapters` loads `Project` and related `Chapter` rows.
2. Route computes per-chapter category flags (`has_art`, `has_ms`, `has_ind`, `has_proof`, `has_xml`) in Python and renders `project_chapters.html`.
3. New chapter modal posts to `POST /projects/{project_id}/chapters/create`.
4. Create route inserts `Chapter`, creates category folders for that chapter, and redirects back.
5. Rename modal posts to `POST /projects/{project_id}/chapter/{chapter_id}/rename`.
6. Rename route updates chapter number/title and renames chapter directory if the number changed.
7. Delete action posts to `/projects/{project_id}/chapter/{chapter_id}/delete`; there are two duplicate route registrations for this path.
8. Download ZIP action hits `GET /projects/{project_id}/chapter/{chapter_id}/download`, which zips the chapter folder dynamically.

### File upload / versioning
1. Chapter detail page submits uploads to `POST /projects/{project_id}/chapter/{chapter_id}/upload` with `category` and multiple files.
2. Route creates `UPLOAD_DIR/{project_code}/{chapter_number}/{category}` if missing.
3. For each uploaded file, route checks for an existing `File` with same chapter/category/name.
4. If existing and not locked by another user, route copies current file into `Archive`, inserts `FileVersion`, overwrites current file in place, increments version, updates upload timestamp, and auto-checks the file back in.
5. If new, route writes file to disk and inserts a new `File` row.
6. Route commits and redirects back to the chapter tab with `msg=Files Uploaded Successfully`.
7. Separate API upload route `POST /api/v1/files/` exists, but uses a different flat-storage pattern and is not the main UI upload path.

### Checkout / lock / cancel checkout
1. Chapter detail posts to `POST /projects/files/{file_id}/checkout`.
2. Route loads `File`; if already locked by another user it redirects back with `msg=File Locked By Other`.
3. Otherwise it sets `is_checked_out`, `checked_out_by_id`, `checked_out_at`, commits, and redirects back.
4. Cancel checkout posts to `POST /projects/files/{file_id}/cancel_checkout`.
5. Route only unlocks if current user owns the lock, then redirects back.
6. Upload overwrite flow and background processing flow both also modify lock state, so lock ownership is not isolated to checkout routes.

### Processing trigger
1. Chapter detail JS calls `POST /api/v1/processing/files/{file_id}/process/{process_type}` with cookie credentials.
2. Route verifies cookie auth, checks hardcoded role map in `PROCESS_PERMISSIONS`, then loads `File`.
3. Route refuses processing if the physical file is missing.
4. Route locks the file if not already locked by another user.
5. Route creates an archive backup, inserts `FileVersion`, and increments the current `File.version`.
6. Route enqueues `background_processing_task` via FastAPI `BackgroundTasks`.
7. Response is immediate JSON: `status=processing`.
8. Background task opens its own DB session, dispatches the requested engine, registers generated output files as new `File` rows, and unlocks the source file.
9. On error, background task logs the exception and still unlocks the file; no persistent processing-status row is written.

### Processing status polling
1. Chapter detail JS polls `GET /api/v1/processing/files/{file_id}/structuring_status`.
2. Route derives expected processed filename as `OriginalName_Processed.ext`.
3. Route looks up a `File` row with matching project, chapter, and processed filename.
4. If found, route returns `{"status": "completed", "new_file_id": ...}`.
5. If not found, route returns `{"status": "processing"}`.
6. This status model only covers structuring and only infers completion from file creation, not task state.

### Technical editor
1. User opens `GET /files/{file_id}/technical/edit`, which renders `technical_editor_form.html`.
2. On page load, JS calls `GET /api/v1/processing/files/{file_id}/technical/scan`.
3. Scan route runs `TechnicalEditor.scan` against the DOCX and returns grouped suggestions.
4. Page renders replacement options client-side.
5. User clicks Apply Changes; JS posts selected replacements to `POST /api/v1/processing/files/{file_id}/technical/apply`.
6. Apply route runs `TechnicalEditor.process`, writes a `_TechEdited` DOCX beside the source file, inserts a new `File` row, and returns `new_file_id`.
7. Page shows success state and redirects back to chapter detail.

### Structuring review
1. User starts structuring from chapter detail JS, which triggers the generic processing API with `process_type=structuring`.
2. After polling completion, page redirects to `GET /api/v1/files/{new_file_id}/structuring/review`.
3. Review route resolves the processed DOCX path, extracts document structure anyway, builds a Collabora WOPI URL, and renders `structuring_review.html`.
4. Active review page is essentially a Collabora iframe shell with Export and Save & Exit.
5. Save happens through Collabora WOPI auto-save, not through the manual `POST /api/v1/files/{id}/structuring/save` route.
6. Export downloads the processed DOCX from `/api/v1/files/{id}/structuring/review/export`.

### WOPI / Collabora editing
1. Generic edit starts at `GET /files/{file_id}/edit`, which builds `collabora_url` pointing Collabora at `/wopi/files/{file_id}`.
2. Collabora calls `GET /wopi/files/{file_id}` for `CheckFileInfo`.
3. CMS returns metadata including `BaseFileName`, `Size`, `Version`, and write capabilities.
4. Collabora calls `GET /wopi/files/{file_id}/contents` to fetch bytes.
5. On save, Collabora POSTs new bytes to `/wopi/files/{file_id}/contents`.
6. Structuring edit follows the same pattern, but uses `/wopi/files/{file_id}/structuring` and `/structuring/contents` to target `_Processed.docx`.
7. WOPI callbacks have no CMS auth; trust is path- and network-based.

### Admin user management
1. `GET /admin` renders summary counts.
2. `GET /admin/users` loads all users and roles and renders `admin_users.html`.
3. Role change submits form to `POST /admin/users/{user_id}/role`; route enforces "cannot remove last Admin".
4. Create user flow is `GET /admin/users/create` -> `POST /admin/users/create`.
5. Edit user flow is `GET /admin/users/{id}/edit` -> `POST /admin/users/{id}/edit`; these handlers do not enforce admin role.
6. Change password flow is `GET /admin/users/{id}/password` -> `POST /admin/users/{id}/password`; duplicate handlers exist with different validations and auth gates.
7. Delete user posts to `/admin/users/{id}/delete`; duplicate handlers exist and neither enforces admin role.
8. Status toggle posts to `/admin/users/{id}/status` and flips `is_active`.

## 4. Auth And Session Map

| Area | Routes | Credential form | Notes | Frontend implications |
|---|---|---|---|---|
| Cookie-based SSR | most of `web.py`; `/files/{id}/edit`; `/api/notifications`; processing routes; structuring routes; API delete `/api/v1/projects/{id}` | `access_token` cookie containing `Bearer <jwt>` | cookie is set with `httponly=True`; no visible `secure`, `samesite`, or CSRF token | same-origin pages work today; any decoupled frontend must either stay same-origin or add CSRF and cookie policy hardening |
| Bearer-token API | `/api/v1/users/me`; `/api/v1/projects/` GET/POST/PUT; `/api/v1/files/`; `/api/v1/teams/` | OAuth2 bearer token from `/api/v1/users/login` | `get_current_user` reads `Authorization: Bearer ...` | suitable for typed API clients, but not consistently used by browser pages |
| Mixed API namespace | `/api/v1/processing/...`; `/api/v1/files/{id}/structuring/...`; `/api/v1/projects/{id}` DELETE | cookie auth inside `/api/v1` endpoints | API prefix does not imply bearer auth in this codebase | frontend migration cannot infer auth model from path; contracts must be normalized first |
| CORS | global app middleware | `allow_origins=["*"]`, `allow_credentials=True`, all methods/headers | very broad CORS policy | cross-origin frontend work is unsafe/inconsistent until origin policy is tightened |
| CSRF | all form POSTs and cookie-auth fetches | none visible | no CSRF tokens, no anti-forgery middleware, no double-submit cookie | any continued cookie-auth frontend must stay same-origin or add CSRF protection before expansion |
| WOPI callbacks | `/wopi/...` | no app auth | intended for Collabora server-to-server callbacks | must preserve path/response contract exactly; cannot casually front these with normal app auth |

## 5. Background Execution Map

| Mechanism | Where used | Trigger path | Status tracking | Retry / failure handling | Notes |
|---|---|---|---|---|---|
| FastAPI `BackgroundTasks` | main CMS processing orchestration in `app/routers/processing.py` | `POST /api/v1/processing/files/{file_id}/process/{process_type}` | no task row; structuring status inferred by looking for `_Processed` file row | no retry; exceptions are logged; file lock is cleared on failure | this is the active document-processing mechanism in the FastAPI app |
| In-process background worker function | `background_processing_task` in `processing.py` | queued by the route above | side effects only: new `File` rows, unlocked source file | best-effort only; no persisted failure state returned to UI | dispatches `PPDEngine`, `PermissionsEngine`, `TechnicalEngine`, `ReferencesEngine`, `StructuringEngine`, `BiasEngine`, `AIExtractorEngine`, `XMLEngine` |
| Main CMS Celery | `app/core/celery_app.py` and `app/worker.py` | no current FastAPI route dispatches it | Celery result backend available in Redis, but unused by web flows | Celery task itself has standard worker semantics | infrastructure exists in Docker, but current CMS route path does not use it for normal processing |
| External AI structuring call | `app/processing/structuring_engine.py` via `app/services/ai_structuring_client.py` | inside `background_processing_task` when `AI_STRUCTURING_BASE_URL` is set | hidden behind main processing route; user only sees eventual file appearance | failures fall back to local structuring | submit -> poll -> download ZIP -> extract processed DOCX |
| `ai_structuring_backend` queue service | external Flask service under `ai_structuring_backend/app/services/queue.py` and `ai_structuring_backend/celery_worker.py` | called over HTTP by `AIStructuringClient` | explicit `Batch`/`Job` status models, queue position, token stats, cost tracking | queue API supports retry/stop/recalculate; Celery worker has retries/backoff | this system is much more formal than the main CMS background model, but it is external to FastAPI |
| WOPI save callbacks | `app/routers/wopi.py` | Collabora POST to `/wopi/.../contents` | implicit; latest bytes overwrite source/processed DOCX | no retry logic in CMS; errors return 500 to Collabora | not a queue, but it is asynchronous external write traffic that must be preserved |

## 6. Risk Register

| High-risk route / workflow | Why it is risky | What must be preserved | What must be extracted first | What should not be changed early |
|---|---|---|---|---|
| Root `/` (`web.home` and `main.read_root`) | duplicate route registration with different behavior | logged-in redirect behavior and any external expectation of `/` | explicit route ownership and canonical root contract | do not change `/` behavior without deciding whether UI or JSON root wins |
| Mixed auth surface | cookie-auth and bearer-auth are interleaved across UI and `/api/v1` | current login cookie, bearer login, and browser fetch success paths | auth contract map, shared user/session service, route-by-route auth normalization | do not switch all APIs to bearer or all pages to token storage in one step |
| Admin duplicate routes in `web.py` | same paths registered twice; different auth/validation behavior | current accessible admin URLs and password/delete flows | route deduplication inventory; admin authorization service | do not rename admin URLs or merge handlers before parity checks |
| `create_project_with_files` | project creation, chapter creation, filename parsing, category inference, DB writes, and disk layout are all one transaction-like block | folder structure, chapter numbering, initial file placement, `client_name` handling | project creation service and storage/path policy service | do not alter naming conventions or chapter-number inference early |
| Chapter upload/versioning | overwrite path, archive naming, version rows, and lock reset happen together | archive file names, version increments, overwrite behavior, redirect targets | file versioning service and storage service | do not change archive path or version suffix patterns early |
| Processing trigger route | permissions, locking, backup, task dispatch, output registration, and unlock-on-error are coupled | lock semantics, generated file registration, suffix naming, role gating | processing workflow service; task status model | do not swap task backend or processor dispatch shape without preserving current side effects |
| Structuring status polling | completion is inferred from existence of a `_Processed` file row | current polling behavior and redirect to structuring review | explicit task/result status contract | do not remove filename-based fallback until a real status API exists and is adopted |
| WOPI / Collabora integration | path shapes, response payloads, and raw file writes are tightly coupled to Collabora expectations | exact WOPI endpoints, fields, and save paths | WOPI adapter boundary and file-target resolution helper | do not move or rename `/wopi/...` endpoints early |
| Structuring review route | HTML page is under `/api/v1`; active page relies on WOPI save, not manual save endpoint | review URL, export URL, save-and-exit redirect, `_Processed` targeting | structuring review page contract and WOPI wrapper separation | do not remove the page shell or change the path prefix early |
| API project delete vs SSR project delete | API delete cleans DB only; SSR delete also removes filesystem tree | both current behaviors until one canonical delete contract exists | shared delete service that handles DB + filesystem consistently | do not point UI at a new delete path before behavior is unified |
| Main CMS background model | active processing is in-process `BackgroundTasks`; Celery exists but is unused by routes | current completion side effects and lock clearing | explicit task orchestration boundary and status persistence | do not redirect active processing to Celery without reproducing current DB/file updates |
| Schema/service drift | `team_service` expects fields absent from `Team`; `audit.py` references missing `AuditLog`; old code references `processing_results` | currently working user-visible paths | schema inventory and service/data contract audit | do not assume all existing services are safe to reuse as-is |
| Template contract drift | templates reference `initial_view`, `current_date`, dead `/reports`, placeholder dashboard actions | current rendered pages and route URLs | template-to-route context contract list | do not replace templates blindly before context expectations are documented |
