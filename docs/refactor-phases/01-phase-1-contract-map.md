# Phase 1 Contract Map and Service Boundary Definition

No application code was modified. This phase defines the current contract baseline, the service boundaries required for refactor safety, and the normalization work that must happen before frontend modernization.

## Purpose

Phase-0 identified where routing, templates, background execution, filesystem rules, and integrations are tightly coupled. Phase-1 turns that inventory into a contract map:

- what must remain backward compatible
- what route behavior is already stable enough to preserve
- what must be normalized before introducing a new frontend surface
- what service boundaries should own business rules instead of route handlers

## Contract Baseline

The following behaviors are compatibility constraints unless explicitly normalized behind a compatibility wrapper:

1. Browser routes must continue to resolve at the current URLs during migration.
2. Redirect outcomes must remain unchanged for login, logout, create, delete, checkout, and upload flows.
3. Filesystem naming conventions must remain intact:
   - chapter folders: `UPLOAD_DIR/{project_code}/{chapter_number}/{category}`
   - archive versions: `{filename_base}_v{N}.{ext}`
   - structuring output: `{filename_base}_Processed.docx`
   - technical output: `{filename_base}_TechEdited{ext}`
4. WOPI callback paths and payload shape must remain Collabora-compatible.
5. Existing lock behavior and version side effects must remain correct even if extracted into services.
6. Mixed auth behavior is part of the current baseline and must be normalized through compatibility layers, not broken by route rewrites.

---

## 1. Route Contract Map

### Auth

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/login` | GET | Render login page | Public | SSR | stable | keep as-is | SSR-only | Must continue rendering the same form route for browser users |
| `/login` | POST | Validate credentials, issue cookie, redirect to dashboard | Public | redirect / SSR on error | needs normalization | wrap with service layer | SSR shell + API endpoints | Must keep `access_token` cookie name, invalid-credentials error rendering, and success redirect to `/dashboard` |
| `/logout` | GET | Clear cookie and redirect to login | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR-only | Must keep cookie clear behavior and redirect to `/login` |
| `/register` | GET | Render registration page | Public | SSR | stable | keep as-is | SSR-only | Must continue serving browser registration flow |
| `/register` | POST | Create user, bootstrap roles if needed, assign first-user admin | Public | redirect / SSR on error | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve first-user admin behavior, duplicate-user validation, and redirect to `/login?msg=...` |
| `/api/v1/users/` | POST | API user creation | Public | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve duplicate-username rejection and returned identity fields until consumers migrate |
| `/api/v1/users/login` | POST | Bearer token login | Public | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve `access_token` and `token_type` fields for current API consumers |
| `/api/v1/users/me` | GET | Return current bearer-auth user info | Bearer JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve ability to derive username, email, and role names from bearer auth |

### Admin

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/admin` | GET | Render admin dashboard with inline counts | Cookie JWT + inline admin gate | SSR | needs normalization | wrap with service layer | SSR-only | Must continue redirecting non-admin users away from the page |
| `/admin/users` | GET | Render user and role management page | Cookie JWT + inline admin gate | SSR | needs normalization | wrap with service layer | SSR-only | Must preserve current user list and role-display behavior |
| `/admin/users/create` | GET | Render create-user page | Cookie JWT + inline admin gate | SSR | stable | keep as-is | SSR-only | Must continue serving the form at the current URL |
| `/admin/users/create` | POST | Create a user with a selected role | Cookie JWT + inline admin gate | redirect / SSR on error | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve uniqueness checks, role assignment, and redirect/query-message behavior |
| `/admin/users/{user_id}/role` | POST | Change a user's role | Cookie JWT + inline admin gate | redirect / SSR on edge-case error | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve last-admin protection and current redirect destinations |
| `/admin/users/{user_id}/status` | POST | Toggle user active status | Cookie JWT + inline admin gate | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve current toggle semantics and redirect outcome |
| `/admin/stats` | GET | Render admin statistics page | Cookie JWT + inline admin gate | SSR | needs normalization | wrap with service layer | SSR-only | Must continue rendering summary counts without changing URL |
| `/admin/users/{user_id}/edit` | GET | Render user edit page | Cookie JWT only | SSR | needs normalization | wrap with service layer | SSR-only | Must preserve current URL and field population, but admin authorization must be normalized behind the route |
| `/admin/users/{user_id}/edit` | POST | Update user email | Cookie JWT only | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve redirect query message behavior |
| `/admin/users/{user_id}/password` | GET | Render password change page | Two handlers: `Cookie JWT + inline admin gate` and `Cookie JWT only` | SSR | duplicate | deprecate later | SSR-only | Must preserve page URL while duplicate handlers are collapsed behind one contract |
| `/admin/users/{user_id}/password` | POST | Change user password | Two handlers with different validation and auth gates | redirect / SSR on error | duplicate | deprecate later | SSR shell + API endpoints | Must preserve minimum current validation behavior and redirect/query messaging until unified |
| `/admin/users/{user_id}/delete` | POST | Delete user | Two handlers; both cookie-auth, neither fully admin-normalized | redirect | duplicate | deprecate later | SSR shell + API endpoints | Must preserve self-delete prevention in the later handler and current URL shape |

### Projects

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/dashboard` | GET | Render dashboard summary and project listing | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must keep current dashboard URL and page access rules |
| `/projects` | GET | Render project list page | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must preserve list page URL and current delete affordance while API normalizes |
| `/projects/create` | GET | Render project creation page | Cookie JWT | SSR | stable | keep as-is | SSR-only | Must continue to serve current form page |
| `/projects/create_with_files` | POST | Create project, chapters, folder tree, and optional initial files in one route | Cookie JWT | redirect | candidate for split | wrap with service layer | SSR shell + API endpoints | Must preserve project code, chapter numbering, initial upload behavior, and redirect to `/dashboard` |
| `/api/v1/projects/` | GET | List projects | Bearer JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve `skip` and `limit` semantics for current callers |
| `/api/v1/projects/` | POST | Create project metadata | Bearer JWT + ProjectManager role | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve project creation permissions and core fields already accepted by the schema |
| `/api/v1/projects/{project_id}/status` | PUT | Change project status | Bearer JWT + ProjectManager role | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve allowed status update flow and 404 on missing project |
| `/api/v1/projects/{project_id}` | DELETE | Delete project from DB only | Cookie JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve current API path while delete semantics are unified with SSR delete |
| `/projects/{project_id}/delete` | POST | Delete project including folder tree | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve filesystem cleanup and redirect to `/dashboard?msg=Book+Deleted` |

### Chapters

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/projects/{project_id}` | GET | Render project chapter list | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must preserve ability to open project chapter listing at this URL |
| `/projects/{project_id}/chapters` | GET | Alias of project chapter list | Cookie JWT | SSR | stable | keep as-is | SSR-only | Must remain a compatible alias during migration |
| `/projects/{project_id}/chapters/create` | POST | Create chapter and directories | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve chapter numbering rules and redirect target |
| `/projects/{project_id}/chapter/{chapter_id}/rename` | POST | Rename chapter number/title and directory | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve directory rename behavior if chapter number changes |
| `/projects/{project_id}/chapter/{chapter_id}/download` | GET | Download chapter directory as ZIP | Cookie JWT | file | stable | keep as-is | API-only | Must preserve ZIP contents and current route path |
| `/projects/{project_id}/chapter/{chapter_id}/delete` | POST | Delete chapter and folder tree | Cookie JWT | redirect | duplicate | deprecate later | SSR shell + API endpoints | Must preserve folder deletion and redirect query message while duplicate definitions are collapsed |
| `/projects/{project_id}/chapter/{chapter_id}` | GET | Render chapter workspace | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must preserve tab-driven chapter view and current URL shape |

### Files

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/api/v1/files/` | POST | Upload file against project using flat storage service | Bearer JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve ability to upload by API while path leakage is removed from contract |
| `/projects/{project_id}/chapter/{chapter_id}/upload` | POST | Upload or replace chapter files with versioning side effects | Cookie JWT | redirect | candidate for split | wrap with service layer | SSR shell + API endpoints | Must preserve category-based storage, archive behavior, and tab redirect semantics |
| `/projects/files/{file_id}/download` | GET | Download individual file | Cookie JWT | file | stable | keep as-is | API-only | Must preserve file bytes and download filename |
| `/projects/files/{file_id}/delete` | POST | Delete file from disk and DB | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve disk delete plus redirect to chapter tab |
| `/projects/files/{file_id}/checkout` | POST | Lock file for current user | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve lock-owner checks and current success/error redirects |
| `/projects/files/{file_id}/cancel_checkout` | POST | Release current user's file lock | Cookie JWT | redirect | needs normalization | wrap with service layer | SSR shell + API endpoints | Must preserve no-op behavior when lock is absent or owned by another user |

### Processing

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/api/v1/processing/files/{file_id}/process/{process_type}` | POST | Lock file, archive version, dispatch background processing | Cookie JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve lock acquisition, backup version creation, engine dispatch, and current `status=processing` response for existing JS |
| `/api/v1/processing/files/{file_id}/structuring_status` | GET | Poll for structuring completion by looking for `_Processed` file | Cookie JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve current completion semantics until a real job-status model is adopted |

### Structuring

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/api/v1/files/{file_id}/structuring/review` | GET | Render structuring review shell for processed document | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must preserve current review URL, processed-file resolution logic, and redirect/login behavior |
| `/api/v1/files/{file_id}/structuring/save` | POST | Apply explicit structuring changes to processed DOCX | Cookie JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve support for current `{"changes": {...}}` request body until clients are migrated |
| `/api/v1/files/{file_id}/structuring/review/export` | GET | Export processed document | Cookie JWT | file | stable | keep as-is | API-only | Must preserve output filename and processed-file targeting |

### Technical editor

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/files/{file_id}/technical/edit` | GET | Render technical-editor page shell | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must preserve current chapter-back navigation and page URL |
| `/api/v1/processing/files/{file_id}/technical/scan` | GET | Analyze DOCX and return technical suggestions | Cookie JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve current suggestion availability for the page JS |
| `/api/v1/processing/files/{file_id}/technical/apply` | POST | Apply selected technical edits and register output file | Cookie JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve `_TechEdited` naming and returned `new_file_id` |

### WOPI endpoints

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/files/{file_id}/edit` | GET | Render generic WOPI editor shell | Cookie JWT | SSR | candidate for split | split into API + page shell | SSR shell + API endpoints | Must preserve editor shell URL and Collabora iframe behavior |
| `/wopi/files/{file_id}` | GET | WOPI CheckFileInfo for original file | None app-level | WOPI / JSON | integration endpoint | keep as-is | integration endpoint | Must preserve WOPI field names and 200/404 behavior expected by Collabora |
| `/wopi/files/{file_id}/contents` | GET | WOPI GetFile for original file | None app-level | WOPI / file | integration endpoint | keep as-is | integration endpoint | Must preserve binary payload and content type |
| `/wopi/files/{file_id}/contents` | POST | WOPI PutFile for original file | None app-level | WOPI / mixed | integration endpoint | keep as-is | integration endpoint | Must preserve raw body write semantics and 200 response on success |
| `/wopi/files/{file_id}/structuring` | GET | WOPI CheckFileInfo for processed file | None app-level | WOPI / JSON | integration endpoint | keep as-is | integration endpoint | Must preserve processed-file lookup and WOPI metadata fields |
| `/wopi/files/{file_id}/structuring/contents` | GET | WOPI GetFile for processed file | None app-level | WOPI / file | integration endpoint | keep as-is | integration endpoint | Must preserve processed document bytes |
| `/wopi/files/{file_id}/structuring/contents` | POST | WOPI PutFile for processed file | None app-level | WOPI / mixed | integration endpoint | keep as-is | integration endpoint | Must preserve save-back semantics to the `_Processed` file |

### Utility APIs and root ownership

| Route path | Method(s) | Current purpose | Current auth | Current response type | Stability | Recommended migration action | Target contract type | Backward compatibility constraints |
|---|---|---|---|---|---|---|---|---|
| `/` (`web.home`) | GET | Browser landing redirect | Cookie JWT optional | redirect | duplicate | deprecate later | SSR-only | Must preserve anonymous redirect to `/login` and authenticated redirect to `/dashboard` until root ownership is finalized |
| `/` (`main.read_root`) | GET | API greeting endpoint | Public | JSON | duplicate | deprecate later | JSON API for frontend module | Must preserve root API response only if any automation depends on it; ownership must be made explicit first |
| `/api/notifications` | GET | Return recent file notifications for layout shell | Cookie JWT optional | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve empty-array behavior for unauthenticated layout requests until auth contract is normalized |
| `/api/v1/teams/` | GET | List teams | Bearer JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve current bearer-auth access path while schema drift is fixed |
| `/api/v1/teams/` | POST | Create team | Bearer JWT | JSON | needs normalization | wrap with service layer | JSON API for frontend module | Must preserve duplicate-name validation semantics, but contract cannot stay ORM-shaped |

---

## 2. Request and Response Schema Map

### Contract normalization rules

These rules apply across all JSON and mixed endpoints before new frontend modules rely on them:

1. Every JSON endpoint should have an explicit request schema, response schema, and error schema.
2. Legacy routes may keep their current path and fields temporarily, but service-layer contracts must be typed and stable.
3. List endpoints should normalize around `items` plus `meta`; bare arrays are compatibility outputs, not canonical contracts.
4. File and WOPI endpoints remain binary/integration contracts and should not be wrapped in generic JSON envelopes.
5. Processing and polling endpoints need an explicit job-status model rather than filename inference.

### Canonical normalized error shape

```json
{
  "error": {
    "code": "not_authenticated",
    "message": "Not authenticated",
    "details": {},
    "retryable": false
  }
}
```

Compatibility note: existing FastAPI `{ "detail": "..." }` error payloads remain valid until all callers are migrated.

### Canonical normalized list/meta shape

```json
{
  "items": [],
  "meta": {
    "skip": 0,
    "limit": 100,
    "returned": 0,
    "total": null
  }
}
```

### Auth JSON APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `POST /api/v1/users/` | JSON body `UserCreate { username, email, password }` | `{ "id": int, "username": str }` | No role info returned; public route; password hashed in service | `200`, `400` duplicate username |
| `POST /api/v1/users/login` | `OAuth2PasswordRequestForm` form fields `username`, `password` | `{ "access_token": str, "token_type": "bearer" }` | Bearer-only API login; no cookie set | `200`, `401` invalid credentials |
| `GET /api/v1/users/me` | none | `{ "username": str, "email": str, "roles": [str] }` | Requires `Authorization: Bearer ...` | `200`, `401` |

**Risks**

- SSR login and API login are two different contracts for the same business capability.
- Registration logic is split between SSR route and JSON API route.
- User create and login responses are ad hoc and incomplete for typed clients.
- No canonical session response exists that works across cookie and bearer modes.

**Proposed normalized contract**

```json
// UserCreateRequest
{
  "username": "editor1",
  "email": "editor@example.com",
  "password": "secret123"
}
```

```json
// SessionTokenResponse
{
  "user": {
    "id": 12,
    "username": "editor1",
    "email": "editor@example.com",
    "roles": ["Editor"]
  },
  "token": {
    "access_token": "jwt",
    "token_type": "bearer",
    "expires_in": 3600
  }
}
```

Normalization requirements:

- `POST /api/v1/users/login` remains bearer-compatible.
- SSR `/login` should call the same `AuthService.authenticate()` contract but still set the legacy cookie.
- `GET /api/v1/users/me` should normalize to `{"user": ...}` internally, while legacy flat keys can be preserved temporarily.

### Team APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `POST /api/v1/teams/` | JSON body `TeamCreate { name, description? }` | raw ORM-like team object | Requires bearer user; service writes fields not present in `Team` model (`description`, `owner_id`) | `200`, `500`-class drift risk |
| `GET /api/v1/teams/` | query `skip`, `limit` implicit defaults in service | bare array of team objects | Requires bearer auth | `200` |

**Risks**

- Service/model schema drift means the route contract is not reliable.
- Response shape depends on ORM serialization rather than explicit schema.
- This route family is not ready to be consumed by a frontend module.

**Proposed normalized contract**

```json
// TeamCreateRequest
{
  "name": "Production",
  "description": "Production group"
}
```

```json
// TeamResponse
{
  "id": 7,
  "name": "Production"
}
```

Normalization requirements:

- Stabilize model and service fields first.
- Return `items/meta` for list responses.
- Keep current routes API-only and internal until schema drift is resolved.

### Project APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `POST /api/v1/projects/` | JSON `ProjectCreate { team_id, code, title, xml_standard }` | raw project ORM object | Bearer auth + ProjectManager role; no `client_name`; no chapters/files | `200`, `403` |
| `GET /api/v1/projects/` | query `skip`, `limit` | bare project array | Bearer auth | `200` |
| `PUT /api/v1/projects/{project_id}/status` | path `project_id`, query `status` | raw project ORM object | Bearer auth + ProjectManager role | `200`, `404` |
| `DELETE /api/v1/projects/{project_id}` | path `project_id` | `{ "message": "Project deleted successfully" }` | Cookie auth inside `/api/v1`; DB-only delete | `200`, `404` |

**Risks**

- Create, list, and update use bearer auth, but delete uses cookie auth.
- API delete does not clean the filesystem; SSR delete does.
- Project create API cannot represent the full SSR create-with-files behavior.
- ORM-shaped responses leak persistence details and do not define stable frontend fields.

**Proposed normalized contract**

```json
// ProjectCreateRequest
{
  "team_id": 3,
  "code": "BK-1001",
  "title": "Sample Book",
  "client_name": "Publisher X",
  "xml_standard": "NLM"
}
```

```json
// ProjectSummary
{
  "id": 42,
  "code": "BK-1001",
  "title": "Sample Book",
  "client_name": "Publisher X",
  "xml_standard": "NLM",
  "status": "RECEIVED",
  "chapter_count": 12
}
```

```json
// ProjectListResponse
{
  "items": [{ "id": 42, "code": "BK-1001", "title": "Sample Book", "client_name": "Publisher X", "xml_standard": "NLM", "status": "RECEIVED", "chapter_count": 12 }],
  "meta": { "skip": 0, "limit": 100, "returned": 1, "total": null }
}
```

```json
// ProjectStatusUpdateRequest
{
  "status": "PROCESSING"
}
```

```json
// DeleteProjectResponse
{
  "project_id": 42,
  "deleted": true,
  "storage_deleted": true
}
```

Normalization requirements:

- Unify delete semantics behind one service contract before changing clients.
- Keep `skip/limit` query behavior stable.
- Keep current `/api/v1/projects/*` paths while response DTOs become explicit.

### File upload and binary delivery APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `POST /api/v1/files/` | multipart `project_id`, `file` | `{ "file_id": int, "path": str }` | Bearer auth; path is leaked; no chapter/category in contract | `200` |
| `GET /projects/{project_id}/chapter/{chapter_id}/download` | path params | ZIP file | Cookie auth | `200`, `404` |
| `GET /projects/files/{file_id}/download` | path param | file bytes | Cookie auth | `200`, `404` |
| `GET /api/v1/files/{file_id}/structuring/review/export` | path param | processed DOCX file | Cookie auth | `200`, `404` |

**Risks**

- File upload API and chapter upload route use different storage policies.
- The API leaks internal storage paths.
- Download behavior depends on current file naming and current processed-file resolution rules.

**Proposed normalized contract**

```json
// FileUploadResponse
{
  "items": [
    {
      "file_id": 88,
      "filename": "chapter1.docx",
      "category": "Manuscript",
      "version": 1
    }
  ],
  "meta": {
    "uploaded": 1,
    "replaced": 0,
    "skipped": 0
  }
}
```

Normalization requirements:

- Do not return raw storage paths in canonical JSON contracts.
- Keep binary routes as file endpoints, not generic JSON envelopes.
- Preserve download filenames and processed/export resolution logic.

### Notifications API

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `GET /api/notifications` | none | array of `{ title, desc, time, icon, color }` | Returns `[]` instead of `401` when unauthenticated | `200` always in practice |

**Risks**

- This API encodes presentation fields directly (`icon`, `color`) instead of domain state.
- Authentication behavior differs from other protected endpoints.
- Relative time strings are pre-rendered server-side and not typed as data.

**Proposed normalized contract**

```json
{
  "items": [
    {
      "type": "file_uploaded",
      "title": "File Uploaded",
      "description": "chapter1.docx",
      "occurred_at": "2026-03-09T10:15:00Z",
      "ui_hint": {
        "icon": "fa-file-upload",
        "color": "text-primary"
      }
    }
  ]
}
```

Normalization requirements:

- Preserve current empty-array behavior until layout shell authentication is normalized.
- Separate domain timestamp from UI formatting.

### Processing start and status APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `POST /api/v1/processing/files/{file_id}/process/{process_type}` | path `file_id`, path `process_type`, query `mode=style`, optional JSON body ignored in most flows | `{ "message": "...", "status": "processing" }` | Cookie auth inside `/api/v1`; lock acquisition, version backup, and task dispatch happen as side effects | `200`, `401`, `403`, `404`, `400`, `501` |
| `GET /api/v1/processing/files/{file_id}/structuring_status` | path `file_id` | `{ "status": "processing" }` or `{ "status": "completed", "new_file_id": int }` | Cookie auth; status inferred by looking for a `_Processed` file in DB | `200`, `401`, `404` |

**Risks**

- `process_type` is an open string contract but actual support and permission mapping are inconsistent.
- No job identifier exists.
- Failure state is not returned to the UI; absence of `_Processed` is treated as still processing.
- The route mutates lock and version state before background processing begins.

**Proposed normalized contract**

```json
// ProcessingStartRequest
{
  "options": {
    "mode": "style"
  }
}
```

```json
// ProcessingStartResponse
{
  "job": {
    "id": "proc_01HXYZ",
    "type": "structuring",
    "status": "queued"
  },
  "file": {
    "id": 55,
    "lock_state": "checked_out",
    "version": 4
  },
  "compatibility": {
    "message": "Structuring started in background. The file is locked and will be updated shortly.",
    "status": "processing"
  }
}
```

```json
// ProcessingStatusResponse
{
  "job": {
    "id": "proc_01HXYZ",
    "type": "structuring",
    "status": "running"
  },
  "result": {
    "output_file_id": null
  },
  "progress": {
    "percent": null,
    "message": "Waiting for worker result"
  }
}
```

Normalization requirements:

- Keep legacy `status` and `new_file_id` fields for existing chapter-detail polling until callers migrate.
- Introduce a canonical persisted job state behind the route before any new frontend relies on it.
- Treat `file_id + process_type + options` as the canonical service request, even if path params stay unchanged.

### Technical editor APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `GET /api/v1/processing/files/{file_id}/technical/scan` | path `file_id` | opaque JSON object keyed by issue key; each item contains fields such as `label`, `category`, `count`, `found`, `options` | Cookie auth; permission checked with `technical` role map; reads source DOCX directly from file path | `200`, `401`, `403`, `404`, `500` |
| `POST /api/v1/processing/files/{file_id}/technical/apply` | path `file_id`, JSON body `{ replacement_key: selected_option }` | `{ "status": "completed", "new_file_id": int }` | Cookie auth; output filename derived automatically as `_TechEdited` | `200`, `401`, `403`, `404`, `500` |

**Risks**

- Scan response shape is engine-defined, not route-defined.
- Apply request schema is implicit and unvalidated.
- Output file registration is a side effect of a route-level implementation rather than a typed workflow contract.

**Proposed normalized contract**

```json
// TechnicalScanResponse
{
  "items": [
    {
      "key": "xray_hyphenation",
      "label": "X-ray casing",
      "category": "Medical terms",
      "count": 4,
      "found": ["xray", "x-ray"],
      "options": ["X-ray", "Xray"]
    }
  ]
}
```

```json
// TechnicalApplyRequest
{
  "replacements": {
    "xray_hyphenation": "X-ray"
  }
}
```

```json
// TechnicalApplyResponse
{
  "status": "completed",
  "new_file_id": 91,
  "output": {
    "file_id": 91,
    "filename": "chapter1_TechEdited.docx"
  }
}
```

Normalization requirements:

- Keep current `new_file_id` for compatibility.
- Convert scan result to an explicit `items[]` schema internally, even if legacy callers still receive the current object form.
- Keep `_TechEdited` filename derivation stable.

### Structuring APIs

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `POST /api/v1/files/{file_id}/structuring/save` | JSON body currently expected as `{ "changes": { "node_id": "STYLE" } }` | `{ "status": "success" }` | Cookie auth; route resolves processed file from original filename/path conventions | `200`, `401`, `404`, `500` |
| `GET /api/v1/files/{file_id}/structuring/review/export` | path `file_id` | processed DOCX file | Cookie auth; returns redirect to `/login` if user missing | `200`, `302`, `404` |

**Risks**

- The active UI no longer uses the save endpoint directly; the route is drifting from the active workflow.
- Processed document resolution is implicit and filename-based.
- Export is a file contract hidden under an API path that also serves HTML.

**Proposed normalized contract**

```json
// StructuringSaveRequest
{
  "changes": [
    { "node_id": "p-100", "style": "H1" },
    { "node_id": "p-101", "style": "TXT" }
  ]
}
```

```json
// StructuringSaveResponse
{
  "status": "completed",
  "document": {
    "file_id": 77,
    "filename": "chapter1_Processed.docx"
  }
}
```

Normalization requirements:

- Preserve the current `{ "changes": { ... } }` body as a compatibility shape.
- Formalize processed-document resolution inside a service, not in each route.
- Keep export as a stable binary endpoint even if review UI moves.

### WOPI integration endpoints

**Current contract**

| Endpoint family | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `GET /wopi/files/{file_id}` and `GET /wopi/files/{file_id}/structuring` | path `file_id` | WOPI JSON metadata including `BaseFileName`, `Size`, `Version`, `UserCanWrite`, `SupportsUpdate` | No app auth; trust is network/path based | `200`, `404` |
| `GET /wopi/files/{file_id}/contents` and structuring equivalent | path `file_id` | DOCX bytes | No app auth | `200`, `404` |
| `POST /wopi/files/{file_id}/contents` and structuring equivalent | path `file_id`, raw request body | empty `200` on success | No app auth; file written in place | `200`, `404`, `500` |

**Risks**

- These are protocol contracts, not app-defined APIs.
- Any field-name change or route move can break Collabora immediately.
- Security assumptions are externalized to network topology and WOPI host trust.

**Proposed normalized contract**

Normalization here means an adapter boundary, not a payload rewrite:

- `WOPIAdapterService.get_file_info(file_id, mode)`
- `WOPIAdapterService.get_file_bytes(file_id, mode)`
- `WOPIAdapterService.put_file_bytes(file_id, mode, body)`

Adapter invariants:

1. Preserve current WOPI route paths.
2. Preserve current WOPI field names.
3. Preserve current original-vs-structuring path resolution.
4. Preserve `200` on successful write and `404` for missing files.

### Root and mixed-ownership endpoints

**Current contract**

| Endpoint | Request inputs | Current response | Implicit fields / auth assumptions | Current status codes |
|---|---|---|---|---|
| `GET /` (`main.read_root`) | none | `{ "message": "Welcome to the Publishing CMS API" }` | Public JSON root exists alongside browser root redirect | `200` |
| `GET /` (`web.home`) | cookie presence | redirect to `/dashboard` or `/login` | Browser entry route shares same path with JSON route | `302` |

**Risks**

- Root ownership is undefined for future frontend routing.
- Browser and API expectations are both attached to `/`.

**Proposed normalized contract**

- Choose one canonical owner for `/` before frontend work starts.
- Keep the losing behavior on a compatibility route if anything depends on it.
- Do not introduce a new frontend root shell until this ownership is explicit.

---

## 3. Page State Contract Map

### Login page

- Template: `login.html`
- Route(s): `GET /login`, `POST /login`
- Current context variables: `request`, optional `error`
- Page responsibilities: collect credentials, render login error, hand off to cookie-based session creation
- Backend data sources: `User` lookup, password verification, JWT issue
- Embedded API calls: none

`LoginPageStateDTO`

```yaml
auth:
  mode: login
  error: string|null
  flash_message: string|null
ui:
  action_url: /login
  success_redirect: /dashboard
```

- Must remain server-rendered: page shell and initial form rendering
- Should become API-driven: optional async credential submission only after session contract is normalized
- Frontend migration target: `keep SSR`

### Register page

- Template: `register.html`
- Route(s): `GET /register`, `POST /register`
- Current context variables: `request`, optional `error`
- Page responsibilities: collect registration fields, display validation errors, trigger first-user/bootstrap behavior
- Backend data sources: `User`, `Role`, `UserRole`
- Embedded API calls: none

`RegisterPageStateDTO`

```yaml
auth:
  mode: register
  error: string|null
ui:
  action_url: /register
  success_redirect: /login
```

- Must remain server-rendered: page shell and basic form workflow
- Should become API-driven: field validation and submission only after registration/service contract is unified
- Frontend migration target: `keep SSR`

### Dashboard page

- Template: `dashboard.html`
- Route(s): `GET /dashboard`
- Current context variables: `request`, `user`, `projects`, `dashboard_stats`
- Page responsibilities: show dashboard summary, list project data, expose placeholder project actions
- Backend data sources: `ProjectService.get_projects()`, route-computed summary stats
- Embedded API calls: no active production API contract; JS currently contains placeholder actions

`DashboardPageStateDTO`

```yaml
user:
  id: int
  username: string
  email: string|null
  roles: [string]
summary:
  total_projects: int
  on_time_rate: number|null
  avg_days: number|null
  delayed_count: int
projects:
  - id: int
    code: string
    title: string
    status: string
permissions:
  can_create_project: bool
ui_flags:
  show_admin_shortcuts: bool
```

- Must remain server-rendered: navigation shell and initial auth gate
- Should become API-driven: summary cards and project list data
- Frontend migration target: `SSR + JS island`

### Projects list page

- Template: `projects.html`
- Route(s): `GET /projects`
- Current context variables: `request`, `user`, `projects`
- Page responsibilities: list projects, link into project detail, trigger delete via API
- Backend data sources: `ProjectService.get_projects()`
- Embedded API calls: `DELETE /api/v1/projects/{project_id}`

`ProjectsListPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
projects:
  - id: int
    code: string
    title: string
    status: string
permissions:
  can_create: bool
  can_delete: bool
routes:
  create: /projects/create
  detail_template: /projects/{project_id}
```

- Must remain server-rendered: page entry and navigation shell
- Should become API-driven: project table data and delete action
- Frontend migration target: `SSR + JS island`

### Project create page

- Template: `project_create.html`
- Route(s): `GET /projects/create`, `POST /projects/create_with_files`
- Current context variables: `request`, `user`
- Page responsibilities: collect project metadata, optional initial files, chapter count, and XML standard
- Backend data sources: none on GET; POST writes `Project`, `Chapter`, `File`, filesystem
- Embedded API calls: none

`ProjectCreatePageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
form:
  fields:
    - code
    - title
    - client_name
    - xml_standard
    - chapter_count
    - files[]
options:
  xml_standards: [string]
permissions:
  can_create_project: bool
```

- Must remain server-rendered: multipart form shell unless/until upload API is normalized
- Should become API-driven: project metadata validation and upload progress only after create/upload contracts are separated
- Frontend migration target: `keep SSR`

### Project chapters page

- Template: `project_chapters.html`
- Route(s): `GET /projects/{project_id}`, `GET /projects/{project_id}/chapters`
- Current context variables: `request`, `user`, `project`, `chapters`
- Page responsibilities: show chapter inventory, chapter completeness flags, create/rename/delete actions, chapter ZIP download
- Backend data sources: `Project`, `Chapter`, `File`
- Embedded API calls: none; actions are SSR form posts and file links

`ProjectChaptersPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
project:
  id: int
  code: string
  title: string
chapters:
  - id: int
    number: string
    title: string
    category_counts:
      Art: int
      Manuscript: int
      InDesign: int
      Proof: int
      XML: int
permissions:
  can_create_chapter: bool
  can_rename_chapter: bool
  can_delete_chapter: bool
```

- Must remain server-rendered: initial page shell and chapter modal markup
- Should become API-driven: chapter inventory data and create/rename/delete actions
- Frontend migration target: `SSR + JS island`

### Chapter detail page

- Template: `chapter_detail.html`
- Route(s): `GET /projects/{project_id}/chapter/{chapter_id}`
- Current context variables: `request`, `project`, `chapter`, `files`, `active_tab`, `user`
- Page responsibilities: category navigation, uploads, download/delete, checkout/cancel, processing trigger, processing poll, technical-editor entry, structuring-review entry, WOPI edit entry
- Backend data sources: `Project`, `Chapter`, `File`, lock state, version state
- Embedded API calls:
  - `POST /api/v1/processing/files/{file_id}/process/{process_type}`
  - `GET /api/v1/processing/files/{file_id}/structuring_status`

`ChapterDetailPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
project:
  id: int
  code: string
  title: string
chapter:
  id: int
  number: string
  title: string
files_by_category:
  Art: []
  Manuscript: []
  InDesign: []
  Proof: []
  XML: []
permissions:
  can_upload: bool
  can_checkout: bool
  can_process:
    language: bool
    technical: bool
    structuring: bool
    ppd: bool
locks:
  file_id_to_lock_state: {}
endpoints:
  upload: string
  download_template: string
  process_template: string
  status_template: string
ui_flags:
  active_tab: string
```

- Must remain server-rendered: auth gate, base layout, initial shell
- Should become API-driven: file grid/list data, uploads, lock actions, processing controls, status polling
- Frontend migration target: `typed frontend module`

### Activities page

- Template: `activities.html`
- Route(s): `GET /activities`
- Current context variables: `request`, `user`, `activities`, `today_count`
- Page responsibilities: show recent uploads and version-history events
- Backend data sources: `File`, `FileVersion`, `Project`, `Chapter`
- Embedded API calls: none

`ActivitiesPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
activities:
  - type: upload|version
    title: string
    description: string
    project: string
    chapter: string
    category: string
    occurred_at: datetime
summary:
  today_count: int
```

- Must remain server-rendered: page shell and first paint
- Should become API-driven: activity list feed and summary
- Frontend migration target: `SSR + JS island`

### Admin page family

| Template | Route(s) | Current context variables | Page responsibilities | Backend data sources | Embedded API calls |
|---|---|---|---|---|---|
| `admin_dashboard.html` | `GET /admin` | `request`, `user`, `admin_stats` | render admin summary | `User`, `File` counts | none |
| `admin_users.html` | `GET /admin/users` | `request`, `user`, `current_user`, `users`, `all_roles`, optional `error` | user listing, role change, delete navigation | `User`, `Role`, `UserRole` | none; uses SSR form posts |
| `admin_create_user.html` | `GET/POST /admin/users/create` | `request`, `user`, `roles`, optional `error` | create user with selected role | `Role`, `User` | none |
| `admin_edit_user.html` | `GET/POST /admin/users/{user_id}/edit` | `request`, `user`, `target`, `roles` | edit user email | `User`, `Role` | none |
| `admin_change_password.html` | `GET/POST /admin/users/{user_id}/password` | `request`, `user`, `target_user` or `target`, optional `error` | change password | `User` | none |
| `admin_stats.html` | `GET /admin/stats` | `request`, `user`, `stats` | render admin metrics | `User`, `Project`, `Chapter`, `File`, `Role`, `UserRole` | none |

`AdminDashboardPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
summary:
  total_users: int
  total_files: int
  total_validations: int|null
  total_macro: int|null
permissions:
  is_admin: bool
```

`AdminUsersPageStateDTO`

```yaml
current_user:
  id: int
  username: string
users:
  - id: int
    username: string
    email: string
    is_active: bool
    roles: [string]
available_roles:
  - id: int
    name: string
permissions:
  can_manage_users: bool
messages:
  error: string|null
  flash: string|null
```

`AdminUserFormPageStateDTO`

```yaml
user_form:
  mode: create|edit|password
  target_user:
    id: int|null
    username: string|null
    email: string|null
roles:
  - id: int
    name: string
permissions:
  can_manage_users: bool
errors:
  form: string|null
```

`AdminStatsPageStateDTO`

```yaml
stats:
  total_users: int
  total_projects: int
  total_chapters: int
  total_files: int
  by_role: []
permissions:
  is_admin: bool
```

- Must remain server-rendered: admin auth gate and base forms
- Should become API-driven: user table actions, stats payloads, role/status mutations
- Frontend migration target: `HTMX enhancement` for forms and tables, with typed APIs behind them

### Technical editor page

- Template: `technical_editor_form.html`
- Route(s): `GET /files/{file_id}/technical/edit`
- Current context variables: `request`, `user`, `file`
- Page responsibilities: load scan results, render technical choices, submit replacements, redirect back to chapter
- Backend data sources: `File`, technical scan/apply APIs
- Embedded API calls:
  - `GET /api/v1/processing/files/{file_id}/technical/scan`
  - `POST /api/v1/processing/files/{file_id}/technical/apply`

`TechnicalEditorPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
file:
  id: int
  project_id: int
  chapter_id: int
  filename: string
scan:
  items: []
permissions:
  can_scan: bool
  can_apply: bool
endpoints:
  scan: string
  apply: string
  return_to_chapter: string
```

- Must remain server-rendered: shell and initial auth gate
- Should become API-driven: full scan/apply interaction
- Frontend migration target: `typed frontend module`

### Structuring review page

- Template: `structuring_review.html`
- Route(s): `GET /api/v1/files/{file_id}/structuring/review`
- Current context variables: `request`, `user`, `file`, `filename`, `collabora_url`
- Page responsibilities: host Collabora review session for processed DOCX, save-and-exit, export
- Backend data sources: `File`, processed-file path resolution, WOPI URL builder
- Embedded API calls: none direct in active template; relies on WOPI and export link

`StructuringReviewPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
file:
  id: int
  project_id: int|null
  chapter_id: int|null
  filename: string
review:
  processed_filename: string
  collabora_url: string|null
routes:
  export: string
  save_and_exit: string
ui_flags:
  collabora_available: bool
```

- Must remain server-rendered: WOPI wrapper shell and export link
- Should become API-driven: optional document metadata and review status only
- Frontend migration target: `SSR + JS island`

### Generic editor page (WOPI shell)

- Template: `editor.html`
- Route(s): `GET /files/{file_id}/edit`
- Current context variables: `request`, `user`, `file`, `filename`, `collabora_url`
- Page responsibilities: host Collabora session for original file editing
- Backend data sources: `File`, WOPI URL builder
- Embedded API calls: none direct in template; relies on WOPI callbacks

`EditorPageStateDTO`

```yaml
user:
  id: int
  username: string
  roles: [string]
file:
  id: int
  project_id: int|null
  chapter_id: int|null
  filename: string
editor:
  collabora_url: string|null
  mode: original
ui_flags:
  collabora_available: bool
```

- Must remain server-rendered: iframe shell and auth gate
- Should become API-driven: minimal metadata only; the editing session itself stays WOPI-driven
- Frontend migration target: `keep SSR`

---

## 4. Service Extraction Map

### AuthService

- Responsibilities: authenticate credentials, issue JWTs, issue/clear cookie sessions, register users, bootstrap first-user/admin behavior, resolve current session user, centralize auth-mode policy
- Inputs: login credentials, registration payload, auth mode (`cookie` or `bearer`), request token/cookie
- Outputs: authenticated user DTO, token payload, registration result, logout result, auth error
- Database dependencies: `User`, `Role`, `UserRole`
- Filesystem dependencies: none
- External integrations: JWT encode/decode, bcrypt hashing
- Routes currently containing this logic: `web.login_submit`, `web.logout`, `web.register_submit`, `users.login`, `users.create_user`, `auth.get_current_user`, `auth.get_current_user_from_cookie`, `rbac.require_role`

### ProjectService

- Responsibilities: create/update/delete projects, list projects, expose project summary DTOs, coordinate project-level workflow creation and deletion
- Inputs: project create/update/delete commands, pagination filters, requester identity
- Outputs: project DTOs, delete result, list result
- Database dependencies: `Project`, `Chapter`, `File`, `FileVersion`
- Filesystem dependencies: project root directory lifecycle for project bundle create/delete
- External integrations: none directly
- Routes currently containing this logic: `projects.create_project`, `projects.read_projects`, `projects.update_project_status`, `projects.delete_project`, `web.dashboard`, `web.projects_list`, `web.create_project_with_files`, `web.delete_project`

### ChapterService

- Responsibilities: create chapter, rename chapter, delete chapter, list chapter inventory and category completeness, manage chapter numbering rules
- Inputs: project id/code, chapter id, number, title, requester identity
- Outputs: chapter DTOs, list DTOs, delete result
- Database dependencies: `Project`, `Chapter`, `File`
- Filesystem dependencies: chapter directory creation, rename, deletion, ZIP assembly input
- External integrations: none
- Routes currently containing this logic: `web.project_chapters`, `web.create_chapter`, `web.rename_chapter`, both `web.delete_chapter` handlers, `web.download_chapter_zip`

### FileStorageService

- Responsibilities: resolve canonical storage paths, save uploads, stream downloads, remove files/directories, derive processed/output targets, prevent path leakage from route contracts
- Inputs: project code/id, chapter number/id, category, filename, upload stream, storage mode (`original`, `processed`, `archive`)
- Outputs: storage location descriptor, saved file metadata, delete result, file stream descriptor
- Database dependencies: `Project`, `Chapter`, `File` for path resolution context
- Filesystem dependencies: `UPLOAD_DIR`, category directories, archive directories, project/chapter tree, ZIP temp files
- External integrations: local filesystem only
- Routes currently containing this logic: `file_service.create_file_record`, `web.create_project_with_files`, `web.create_chapter`, `web.rename_chapter`, `web.upload_chapter_files`, `web.download_chapter_zip`, `web.download_file`, `web.delete_file`, `web.delete_project`, `processing.run_file_process`, `structuring.review_structuring`, `structuring.export_structuring`, `wopi._get_target_path`

### VersioningService

- Responsibilities: archive previous file state, create `FileVersion` rows, compute version numbers, preserve archive naming conventions
- Inputs: target file record, actor id, replacement source, reason (`upload`, `processing`)
- Outputs: new version number, archive metadata, `FileVersion` record
- Database dependencies: `File`, `FileVersion`, optionally `Project`, `Chapter`
- Filesystem dependencies: archive folder, original file path, backup copy
- External integrations: none
- Routes currently containing this logic: `web.upload_chapter_files`, `processing.run_file_process`

### CheckoutLockService

- Responsibilities: lock/unlock files, validate lock owner, expose lock state to UI and workflows, prevent stale lock misuse
- Inputs: file id, actor id, requested operation (`checkout`, `cancel`, `processing-start`, `upload-replace`)
- Outputs: lock state result, denial reason, lock metadata
- Database dependencies: `File`, `User`
- Filesystem dependencies: none
- External integrations: none
- Routes currently containing this logic: `web.checkout_file`, `web.cancel_checkout`, `web.upload_chapter_files`, `processing.run_file_process`, `processing.background_processing_task`

### ProcessingWorkflowService

- Responsibilities: validate processing permissions, create processing job record, coordinate lock + backup + engine dispatch + output registration + unlock, normalize processing status
- Inputs: file id, process type, options (for example `mode=style`), actor identity
- Outputs: processing start result, processing status result, generated output metadata, failure result
- Database dependencies: `File`, `FileVersion`, `Project`, `Chapter`, `User`, `Role`
- Filesystem dependencies: original file path, archive path, generated output paths
- External integrations: legacy processing engines, optional `AIStructuringClient`, FastAPI background tasks today and future task adapter
- Routes currently containing this logic: `processing.run_file_process`, `processing.background_processing_task`, `processing.check_structuring_status`

### StructuringReviewService

- Responsibilities: resolve processed document target, prepare review shell state, apply structured changes, export processed document, isolate filename/path inference
- Inputs: file id, review changes, actor identity
- Outputs: review page DTO, save result, export descriptor
- Database dependencies: `File`, `User`
- Filesystem dependencies: processed DOCX path resolution and persistence
- External integrations: rules loader, document structure extraction/update helpers, WOPI URL composition
- Routes currently containing this logic: `structuring.review_structuring`, `structuring.save_structuring_changes`, `structuring.export_structuring`

### TechnicalEditorService

- Responsibilities: scan DOCX for technical issues, normalize suggestion DTOs, apply replacements, register generated technical-edit file
- Inputs: file id, replacement map, actor identity
- Outputs: scan result DTO, apply result DTO, generated file metadata
- Database dependencies: `File`, `User`
- Filesystem dependencies: source DOCX read, `_TechEdited` output write
- External integrations: legacy `TechnicalEditor` engine
- Routes currently containing this logic: `processing.scan_technical_errors`, `processing.apply_technical_edits`, `web.technical_editor_page`

### AdminUserService

- Responsibilities: list users/roles, create users, update emails, change passwords, toggle status, change roles, enforce last-admin and self-delete protections
- Inputs: admin actor, target user id, role change command, password change command, create/edit form payloads
- Outputs: admin page DTOs, mutation results, validation errors
- Database dependencies: `User`, `Role`, `UserRole`
- Filesystem dependencies: none
- External integrations: password hashing
- Routes currently containing this logic: `web.admin_dashboard`, `web.admin_users`, `web.admin_create_user_page`, `web.admin_create_user_submit`, `web.update_user_role`, `web.toggle_user_status`, `web.admin_stats`, `web.admin_edit_user_page`, `web.admin_edit_user`, both password handlers, both delete handlers

### WOPIAdapterService

- Responsibilities: convert CMS file records into WOPI-compatible original/processed targets, produce CheckFileInfo payloads, stream file bytes, persist PutFile writes, isolate WOPI-specific invariants
- Inputs: file id, mode (`original` or `structuring`), raw request body for saves
- Outputs: WOPI metadata payload, file stream descriptor, write result
- Database dependencies: `File`
- Filesystem dependencies: original and processed file paths
- External integrations: Collabora / WOPI protocol
- Routes currently containing this logic: `wopi.edit_file_page`, `wopi.wopi_check_file_info`, `wopi.wopi_get_file`, `wopi.wopi_put_file`, `wopi.wopi_check_file_info_structuring`, `wopi.wopi_get_file_structuring`, `wopi.wopi_put_file_structuring`, plus WOPI URL generation in `structuring.review_structuring`

---

## 5. Canonical Workflow Contracts

### Login / logout / session check

- Source of truth: JWT payload plus current `User` record and role membership
- Canonical route(s): compatibility `GET/POST /login`, `GET /logout`, `POST /api/v1/users/login`, `GET /api/v1/users/me`
- Service owner: `AuthService`
- State transitions: anonymous -> authenticated session issued -> authenticated session resolved -> session cleared
- Side effects: DB read from `User`/`Role`; set `access_token` cookie for SSR flow; return bearer token for API flow
- Backward compatibility requirements: preserve cookie name, redirect destinations, bearer payload keys, and current invalid-credential behavior

### Project create

- Source of truth: `Project`, `Chapter`, and optional `File` rows plus project/chapter/category directories on disk
- Canonical route(s): compatibility `POST /projects/create_with_files` and `POST /api/v1/projects/`
- Service owner: `ProjectService` with `ChapterService` and `FileStorageService`
- State transitions: request accepted -> project row created -> chapter rows created -> directory tree created -> optional initial files saved -> success redirect/response
- Side effects: DB inserts, directory creation, file writes
- Backward compatibility requirements: preserve `client_name`, project code uniqueness, chapter numbering, filename-to-chapter inference, and redirect to `/dashboard`

### Chapter create

- Source of truth: `Chapter` row plus chapter category directories
- Canonical route(s): compatibility `POST /projects/{project_id}/chapters/create`
- Service owner: `ChapterService`
- State transitions: chapter validated -> chapter row inserted -> chapter directories created -> redirect
- Side effects: DB insert, directory creation
- Backward compatibility requirements: preserve chapter numbering format and redirect back to the project chapter list

### Chapter rename

- Source of truth: `Chapter.number`, `Chapter.title`, and corresponding chapter directory name
- Canonical route(s): compatibility `POST /projects/{project_id}/chapter/{chapter_id}/rename`
- Service owner: `ChapterService`
- State transitions: rename validated -> chapter fields updated -> directory renamed if number changed -> redirect
- Side effects: DB update, directory rename
- Backward compatibility requirements: preserve current rename semantics and folder-rename behavior

### Chapter delete

- Source of truth: `Chapter` row, related `File` rows, and chapter directory tree
- Canonical route(s): compatibility `POST /projects/{project_id}/chapter/{chapter_id}/delete`
- Service owner: `ChapterService` with `FileStorageService`
- State transitions: delete requested -> chapter directory deleted -> DB delete committed -> redirect
- Side effects: filesystem tree removal, DB delete cascade/cleanup
- Backward compatibility requirements: preserve current route path and redirect/query-message behavior while duplicate handlers are collapsed

### File upload

- Source of truth: current `File` row plus stored file bytes at category path
- Canonical route(s): compatibility `POST /projects/{project_id}/chapter/{chapter_id}/upload`, secondary API `POST /api/v1/files/`
- Service owner: `FileStorageService`
- State transitions: upload accepted -> storage path resolved -> file saved or routed to versioning -> DB record created/updated -> redirect/response
- Side effects: filesystem writes, DB insert/update
- Backward compatibility requirements: preserve category path rules, upload field names, and tab-based redirect query parameters

### File versioning

- Source of truth: `File.version`, `FileVersion` rows, archive files under `Archive/`
- Canonical route(s): compatibility inside upload and processing routes
- Service owner: `VersioningService`
- State transitions: current version resolved -> archive copy created -> version row inserted -> current file version incremented
- Side effects: archive file copy, DB insert/update
- Backward compatibility requirements: preserve `_v{N}` archive naming, version increments, and uploaded-by linkage behavior

### Checkout / cancel checkout

- Source of truth: `File.is_checked_out`, `checked_out_by_id`, `checked_out_at`
- Canonical route(s): compatibility `POST /projects/files/{file_id}/checkout`, `POST /projects/files/{file_id}/cancel_checkout`
- Service owner: `CheckoutLockService`
- State transitions: unlocked -> locked by user -> unlocked by same user
- Side effects: DB updates only
- Backward compatibility requirements: preserve current redirects and the rule that only the lock owner can cancel the checkout

### Processing start

- Source of truth: processing job intent plus current file lock/version/output records
- Canonical route(s): compatibility `POST /api/v1/processing/files/{file_id}/process/{process_type}`
- Service owner: `ProcessingWorkflowService`
- State transitions: requested -> permission validated -> file locked -> backup created -> job dispatched -> outputs registered -> file unlocked
- Side effects: DB updates, archive writes, background task dispatch, output file writes, optional external AI structuring call
- Backward compatibility requirements: preserve current role gating, lock behavior, backup behavior, and legacy `status=processing` response

### Processing status

- Source of truth: today, inferred output file presence; target state, persisted job record
- Canonical route(s): compatibility `GET /api/v1/processing/files/{file_id}/structuring_status`
- Service owner: `ProcessingWorkflowService`
- State transitions: queued/running -> completed or failed
- Side effects: DB read today; target state should not depend on filename lookup alone
- Backward compatibility requirements: preserve `completed + new_file_id` and `processing` until chapter-detail callers migrate

### Technical scan

- Source of truth: current source DOCX plus technical-editor engine output
- Canonical route(s): compatibility `GET /api/v1/processing/files/{file_id}/technical/scan`
- Service owner: `TechnicalEditorService`
- State transitions: file loaded -> scan executed -> suggestions normalized -> response returned
- Side effects: filesystem read only
- Backward compatibility requirements: preserve availability on the current route and keep suggestion fidelity unchanged

### Technical apply

- Source of truth: current source DOCX, generated `_TechEdited` output, and new `File` row
- Canonical route(s): compatibility `POST /api/v1/processing/files/{file_id}/technical/apply`
- Service owner: `TechnicalEditorService`
- State transitions: replacements validated -> output DOCX generated -> new file registered -> response returned
- Side effects: filesystem write, DB insert
- Backward compatibility requirements: preserve `_TechEdited` filename, output category, and `new_file_id`

### Structuring review

- Source of truth: processed DOCX and review page wrapper state
- Canonical route(s): compatibility `GET /api/v1/files/{file_id}/structuring/review`
- Service owner: `StructuringReviewService`
- State transitions: processed file resolved -> review shell built -> Collabora session launched -> save-and-exit navigation
- Side effects: filesystem read, WOPI URL generation
- Backward compatibility requirements: preserve current URL, processed-file inference, and chapter/project return navigation

### Structuring export

- Source of truth: processed DOCX on disk
- Canonical route(s): compatibility `GET /api/v1/files/{file_id}/structuring/review/export`
- Service owner: `StructuringReviewService`
- State transitions: processed file resolved -> file streamed
- Side effects: filesystem read
- Backward compatibility requirements: preserve output filename and current export URL

### Project delete

- Source of truth: `Project`, `Chapter`, `File`, `FileVersion` rows plus project folder tree
- Canonical route(s): compatibility `POST /projects/{project_id}/delete` and `DELETE /api/v1/projects/{project_id}`
- Service owner: `ProjectService` with `FileStorageService`
- State transitions: delete requested -> dependent data removed -> filesystem cleanup performed -> response/redirect returned
- Side effects: DB delete cascade/cleanup, filesystem tree removal
- Backward compatibility requirements: unify semantics behind the scenes before changing either route contract

### File delete

- Source of truth: `File` row and file path on disk
- Canonical route(s): compatibility `POST /projects/files/{file_id}/delete`
- Service owner: `FileStorageService`
- State transitions: file located -> physical file removed -> DB row removed -> redirect returned
- Side effects: filesystem delete, DB delete
- Backward compatibility requirements: preserve chapter-tab redirect and current success message

### WOPI edit lifecycle

- Source of truth: target file bytes on disk plus WOPI metadata derived from the current file record
- Canonical route(s): compatibility `GET /files/{file_id}/edit`, `GET /wopi/files/{file_id}`, `GET/POST /wopi/files/{file_id}/contents`, structuring equivalents
- Service owner: `WOPIAdapterService`
- State transitions: editor shell opened -> CheckFileInfo -> GetFile -> PutFile save-back -> local file updated
- Side effects: filesystem reads/writes, Collabora callback traffic
- Backward compatibility requirements: preserve exact WOPI route paths, field names, and in-place write semantics

---

## 6. Normalization Priorities

| Contract to normalize first | Why it must stabilize before frontend modernization |
|---|---|
| Auth/session contract | The app currently mixes cookie-auth SSR routes, cookie-auth `/api/v1` routes, and bearer-auth APIs. A new frontend cannot safely choose request semantics until one canonical auth policy exists behind compatibility wrappers. |
| Duplicate route cleanup | Duplicate `GET/POST /admin/users/{id}/password`, duplicate `POST /admin/users/{id}/delete`, duplicate chapter delete, and duplicate root ownership make route behavior ambiguous. Service extraction cannot safely proceed while multiple handlers claim the same contract. |
| Project/file delete consistency | SSR delete and API delete do different things today. A frontend refactor will create data loss or orphaned storage unless delete semantics are unified first. |
| File upload/versioning contract | Upload, replace, archive, version bump, and lock release are intertwined. If this stays implicit, any new frontend will accidentally break version history or overwrite rules. |
| Processing status contract | Current polling infers completion from `_Processed` output presence and cannot surface failure. A typed frontend module needs explicit job state before replacing the current chapter-detail JS. |
| Root route ownership | Both browser redirect and API greeting use `/`. Frontend entry routing cannot be planned safely until one owner is chosen. |
| WOPI integration boundary | Collabora depends on exact path and payload semantics. This boundary must be isolated before any UI refactor touches editor-related routes. |
| Filesystem path policy | Project code, chapter number, category, archive naming, and processed-file inference are all encoded in paths. Route cleanup and service extraction will remain fragile until path policy is centralized. |

Recommended stabilization order inside these priorities:

1. Auth/session contract
2. Root route ownership and duplicate route cleanup
3. Filesystem path policy
4. File upload/versioning contract
5. Project/file delete consistency
6. Processing status contract
7. WOPI integration boundary

---

## 7. Refactor Readiness Assessment

### Safe modules to refactor first

- Dashboard page after project list/read contract is normalized
- Projects list page after project list and delete contracts are stabilized
- Activities page after activity DTO contract is extracted
- Admin dashboard and stats pages after admin auth gate and DTOs are centralized
- Login and register pages only after the shared `AuthService` contract is in place

### High-risk modules

- Project create bundle (`/projects/create_with_files`)
- Chapter detail workspace
- Chapter upload/versioning
- Checkout/lock flows
- Project delete and file delete
- Processing start/status
- Technical scan/apply
- Structuring review/export
- WOPI endpoints and editor shells

### Contracts that must stabilize before frontend work

- Shared auth/session model for cookie and bearer flows
- Duplicate-route resolution for root and admin paths
- Canonical storage/path policy
- Canonical delete semantics
- Canonical upload/versioning semantics
- Canonical processing job/status contract
- WOPI adapter boundary

### Recommended next phase

`02-phase-2-service-extraction-plan.md`

That phase should define:

1. Extraction order for `AuthService`, `ProjectService`, `ChapterService`, `FileStorageService`, `VersioningService`, and `CheckoutLockService`
2. Route-by-route service handoff plan without changing URLs
3. Compatibility shims needed so SSR pages keep working while typed API contracts are introduced
