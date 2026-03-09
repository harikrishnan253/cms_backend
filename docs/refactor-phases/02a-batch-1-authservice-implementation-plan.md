# Batch 1 Implementation Plan: AuthService Extraction

No application code was modified. This document defines the exact implementation plan for Batch 1 of the Phase-2 extraction program: centralizing auth business logic into `AuthService` while preserving all current route behavior.

## Scope

Batch 1 is intentionally narrow. It does not redesign auth, cookies, bearer usage, CSRF, CORS, or route signatures. It only extracts business logic so the existing auth surface stops being owned by route bodies and compatibility helpers.

The batch must leave the application behaviorally identical from the browser and API caller perspective.

---

## 1. Batch Scope

### In-scope routes

- `GET /login`
- `POST /login`
- `GET /logout`
- `GET /register`
- `POST /register`
- `POST /api/v1/users/login`
- `POST /api/v1/users/`
- `GET /api/v1/users/me`

### In-scope helpers and dependencies

- current auth helpers in `app/auth.py`
  - `hash_password`
  - `verify_password`
  - `create_access_token`
  - `get_current_user`
  - `get_current_user_from_cookie`
  - `oauth2_scheme`
- related role/auth helper in `app/rbac.py`
  - `require_role`

### Files directly in scope

- `app/auth.py`
- `app/rbac.py`
- `app/routers/web.py`
- `app/routers/users.py`
- new service module(s) for auth extraction
- regression tests for auth behavior

### Explicitly out of scope

- any route URL change
- any route signature change
- any cookie-name change
- any auth-policy redesign
- any change to how protected non-auth routes consume cookie auth
- any change to how protected API routes consume bearer auth
- any admin-route cleanup beyond preserving current auth helpers
- any frontend change

---

## 2. Current Logic Ownership

### Route-by-route ownership map

| Route | Current logic inside route | Auth/helper dependencies | DB/model access | Token/cookie behavior | Current response behavior | What moves into AuthService | What stays in route wrapper |
|---|---|---|---|---|---|---|---|
| `GET /login` | none beyond template render | none | none | none | renders `login.html` | nothing | template render |
| `POST /login` | user lookup by username, password verification, token creation, cookie session issue, error handling | `verify_password`, `create_access_token` | `User` query | sets cookie `access_token` to `Bearer {jwt}` with `httponly=True` | success: redirect to `/dashboard`; invalid credentials: re-render `login.html` with `error="Invalid credentials"`; exception: re-render same template with `error=str(e)` | credential validation, token issue, auth result creation | form parsing, `RedirectResponse`, `TemplateResponse`, `set_cookie` call |
| `GET /logout` | cookie delete intent is inline | none | none | deletes `access_token` cookie | redirect to `/login` | logout intent object | `RedirectResponse`, `delete_cookie` call |
| `GET /register` | none beyond template render | none | none | none | renders `register.html` | nothing | template render |
| `POST /register` | password confirmation validation, username/email uniqueness check, password hash generation, new user creation, role bootstrap if missing, first-user admin assignment, non-first-user viewer assignment, commit and redirect, exception-to-template-error handling | `hash_password` | `User`, `Role` | none | success: redirect to `/login?msg=Registration successful! Please login.`; mismatch/duplicate/exception: re-render `register.html` with `error` | all registration rules and role bootstrap logic | form parsing, `RedirectResponse`, `TemplateResponse` |
| `POST /api/v1/users/login` | user lookup by username, password verification, token creation, invalid-credentials HTTP error | `verify_password`, `create_access_token` | `User` via `user_service.get_user_by_username` | bearer token returned in JSON only | success: `{access_token, token_type}`; failure: `401` with `WWW-Authenticate: Bearer` | credential validation and bearer-token result creation | form dependency parsing, HTTPException mapping only if preserved in route |
| `POST /api/v1/users/` | duplicate username check, user creation | `user_service.get_user_by_username`, `user_service.create_user` | `User` | none | success: `{id, username}`; duplicate username: `400 Username already registered` | API-user creation command | JSON response formatting |
| `GET /api/v1/users/me` | none; returns current bearer-auth user fields | `get_current_user` | `User`, `Role` via dependency | none | returns `{username,email,roles}` | user-resolution logic from bearer token dependency | final JSON shape |

### Current helper ownership map

| Helper | Current ownership | Current behavior | What should remain here | What should move behind AuthService |
|---|---|---|---|---|
| `hash_password` in `app/auth.py` | low-level auth helper | bcrypt hash string | keep as low-level crypto primitive | none |
| `verify_password` in `app/auth.py` | low-level auth helper | bcrypt check | keep as low-level crypto primitive | none |
| `create_access_token` in `app/auth.py` | low-level auth helper | JWT encode using `settings.SECRET_KEY`, `settings.ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | keep as low-level token primitive | none |
| `get_current_user` in `app/auth.py` | FastAPI bearer dependency | decode bearer token, load user, raise `401` on failure | keep dependency signature | token decoding + user resolution should delegate to AuthService |
| `get_current_user_from_cookie` in `app/auth.py` | FastAPI cookie dependency | read `access_token` cookie, strip optional `Bearer ` prefix, decode JWT, load user, return `None` on failure | keep dependency signature and return contract | token decoding + user resolution should delegate to AuthService |
| `require_role` in `app/rbac.py` | FastAPI role gate | depends on `get_current_user`, raises `403` if role missing | keep dependency signature and current `403` detail message | optional shared role check helper can come from AuthService, but route-facing behavior stays identical |

### Current logic constraints that must survive extraction

1. SSR login and API login are separate route contracts and must remain separate route contracts.
2. SSR register is not the same as `POST /api/v1/users/`; the two flows must not be merged behaviorally in Batch 1.
3. `POST /register` currently checks username or email uniqueness, but `POST /api/v1/users/` checks username only. That mismatch must remain in Batch 1 unless wrapped explicitly and compatibly.
4. Cookie auth currently stores a bearer-formatted string in the cookie value: `Bearer <jwt>`. That formatting must remain unchanged.
5. `get_current_user_from_cookie` currently returns `None` instead of raising on auth failure. That contract must remain.
6. `get_current_user` currently raises `401` with `WWW-Authenticate: Bearer`. That contract must remain.

---

## 3. Proposed AuthService Design

### Service responsibilities

`AuthService` should own auth business workflows but not HTTP response construction.

It should be the source of truth for:

- validating credentials
- issuing access tokens
- creating SSR-login auth result
- creating bearer-login auth result
- registering self-service users through the SSR register flow
- creating API users through the current API-user flow
- ensuring required roles exist for SSR registration bootstrap
- determining first-user admin assignment
- resolving current user from bearer token
- resolving current user from cookie token
- building a logout session intent
- optionally exposing small role inspection helpers for `rbac.py`

It should not own:

- `RedirectResponse`
- `TemplateResponse`
- `set_cookie` / `delete_cookie` side effects directly
- `HTTPException` formatting unless route wrappers choose to map service errors to exceptions
- route-specific template error messages beyond returning codes/messages for wrappers to use

### Proposed service location

Recommended new file:

- `app/services/auth_service.py`

Optional small factory/provider:

- not required if the service is stateless and created per use with `db`

### Dependency model

`AuthService` should depend on:

- `Session`
- `models.User`
- `models.Role`
- `models.UserRole`
- low-level helpers from `app/auth.py`
  - `hash_password`
  - `verify_password`
  - `create_access_token`
- current settings already consumed by the token helper

To avoid circular imports:

- keep crypto/token primitives in `app/auth.py`
- move workflow logic into `app/services/auth_service.py`
- let `app/auth.py` dependency functions call into `AuthService` for user resolution

### Public methods

Minimum required public methods:

1. `authenticate_for_cookie_session`
2. `authenticate_for_bearer_token`
3. `register_user`
4. `resolve_current_user_context`
5. `logout_session_intent`

Recommended additional public method for current API behavior preservation:

6. `create_api_user`

Recommended additional internal/private helpers:

- `_get_user_by_username`
- `_get_user_by_username_or_email`
- `_ensure_core_roles_exist_for_registration`
- `_determine_registration_role`
- `_decode_token_payload`
- `_build_user_context`

### Command / query objects

These are internal service-facing objects. They do not change route signatures.

#### Commands

```yaml
CookieLoginCommand:
  username: str
  password: str

BearerLoginCommand:
  username: str
  password: str

RegisterUserCommand:
  username: str
  email: str
  password: str
  confirm_password: str

CreateApiUserCommand:
  username: str
  email: str
  password: str

LogoutSessionIntentCommand:
  session_kind: cookie
```

#### Queries

```yaml
ResolveCurrentUserContextQuery:
  auth_mode: bearer|cookie
  token_value: str
```

### Result / return objects

Use explicit result objects internally even if routes continue returning legacy responses.

#### Authentication results

```yaml
AuthenticationResult:
  ok: bool
  code: SUCCESS|INVALID_CREDENTIALS|USER_NOT_FOUND|TOKEN_INVALID|USER_INACTIVE|UNEXPECTED_ERROR
  message: str|null
  user: User|null
  access_token: str|null
```

#### Registration results

```yaml
RegistrationResult:
  ok: bool
  code: SUCCESS|PASSWORD_MISMATCH|USERNAME_OR_EMAIL_EXISTS|ROLE_BOOTSTRAP_FAILED|ADMIN_ROLE_MISSING|DEFAULT_ROLE_MISSING|UNEXPECTED_ERROR
  message: str|null
  user: User|null
  assigned_role: str|null
  is_first_user: bool|null
```

#### API create-user results

```yaml
ApiUserCreateResult:
  ok: bool
  code: SUCCESS|USERNAME_ALREADY_REGISTERED|UNEXPECTED_ERROR
  message: str|null
  user: User|null
```

#### User-context results

```yaml
ResolveUserContextResult:
  ok: bool
  code: SUCCESS|TOKEN_MISSING|TOKEN_INVALID|USER_NOT_FOUND
  user: User|null
  token_subject: str|null
```

#### Logout intent result

```yaml
LogoutSessionIntentResult:
  ok: bool
  cookie_name: access_token
  delete_cookie: true
```

### Error / result codes

Recommended stable internal codes for this batch:

- `SUCCESS`
- `INVALID_CREDENTIALS`
- `PASSWORD_MISMATCH`
- `USERNAME_ALREADY_REGISTERED`
- `USERNAME_OR_EMAIL_EXISTS`
- `TOKEN_MISSING`
- `TOKEN_INVALID`
- `USER_NOT_FOUND`
- `USER_INACTIVE`
- `ROLE_BOOTSTRAP_FAILED`
- `ADMIN_ROLE_MISSING`
- `DEFAULT_ROLE_MISSING`
- `UNEXPECTED_ERROR`

### Method-level design

#### `authenticate_for_cookie_session(command, db)`

- Input: `CookieLoginCommand`
- Output: `AuthenticationResult`
- Responsibilities:
  - load user by username
  - verify password
  - create access token
  - return result object only
- Must not:
  - set cookies
  - build redirects
  - render templates

#### `authenticate_for_bearer_token(command, db)`

- Input: `BearerLoginCommand`
- Output: `AuthenticationResult`
- Responsibilities:
  - same credential validation as SSR login
  - token creation
  - return service result
- Must not:
  - raise HTTPException directly unless route chooses to use that mapping

#### `register_user(command, db)`

- Input: `RegisterUserCommand`
- Output: `RegistrationResult`
- Responsibilities:
  - confirm passwords match
  - check username/email uniqueness
  - hash password
  - ensure required roles exist if missing
  - determine whether the registering user is the first user
  - assign `Admin` for first user, `Viewer` otherwise
  - persist user and role assignment
- Must preserve:
  - current role bootstrap list
  - current first-user logic
  - current redirect success message behavior through route wrapper

#### `create_api_user(command, db)`

- Input: `CreateApiUserCommand`
- Output: `ApiUserCreateResult`
- Responsibilities:
  - preserve current API route behavior
  - check duplicate username only
  - hash password
  - create user
- Must not:
  - assign default role
  - run self-registration bootstrap unless explicitly requested later

#### `resolve_current_user_context(query, db)`

- Input: `ResolveCurrentUserContextQuery`
- Output: `ResolveUserContextResult`
- Responsibilities:
  - decode JWT token
  - read `sub`
  - load `User` by username
  - return `None`-style or error-code result for wrappers to translate
- Must support:
  - bearer raw token
  - cookie token values that may begin with `Bearer `

#### `logout_session_intent(command=None)`

- Input: optional `LogoutSessionIntentCommand`
- Output: `LogoutSessionIntentResult`
- Responsibilities:
  - express that the `access_token` cookie should be cleared
- Must not:
  - return a response object

### Boundary between AuthService and route wrappers

| Concern | Owner |
|---|---|
| credential check | `AuthService` |
| token creation | `AuthService` using existing helper |
| token decode and current-user lookup | `AuthService` exposed through `app/auth.py` wrappers |
| password hashing | low-level helper in `app/auth.py`, called by `AuthService` |
| role bootstrap | `AuthService` |
| first-user role assignment | `AuthService` |
| cookie set/delete | route wrapper only |
| redirect target selection | route wrapper only |
| template render selection | route wrapper only |
| HTTPException selection | route wrapper or dependency wrapper only |

---

## 4. Compatibility Wrapper Plan

### `GET /login`

| Item | Plan |
|---|---|
| Old input shape | no inputs beyond request |
| Normalized service input | none |
| Normalized service output | none |
| Route wrapper translation back to legacy behavior | unchanged route returns `TemplateResponse("login.html", {"request": request})` |
| Exact cookie behavior to preserve | none |
| Exact redirect behavior to preserve | none |
| Exact JSON response shape to preserve | n/a |
| Exact template error behavior to preserve | template remains render-only; no added auth logic |

### `POST /login`

| Item | Plan |
|---|---|
| Old input shape | form fields `username`, `password` |
| Normalized service input | `CookieLoginCommand(username, password)` |
| Normalized service output | `AuthenticationResult(ok, code, message, user, access_token)` |
| Route wrapper translation back to legacy behavior | on success: create `RedirectResponse("/dashboard", 302)` and call `set_cookie`; on invalid credentials: render `login.html` with `error="Invalid credentials"`; on unexpected exception: render `login.html` with `error=str(e)` to preserve current behavior |
| Exact cookie behavior to preserve | `key="access_token"`, `value=f"Bearer {access_token}"`, `httponly=True`; do not add or change `secure`, `samesite`, `max_age`, or domain/path in this batch |
| Exact redirect behavior to preserve | success redirects to `/dashboard` with `302` |
| Exact JSON response shape to preserve | n/a |
| Exact template error behavior to preserve | invalid credentials must continue to show `Invalid credentials`; unexpected exception path must continue to pass `str(e)` |

### `GET /logout`

| Item | Plan |
|---|---|
| Old input shape | none |
| Normalized service input | optional `LogoutSessionIntentCommand(session_kind="cookie")` |
| Normalized service output | `LogoutSessionIntentResult(cookie_name="access_token", delete_cookie=True)` |
| Route wrapper translation back to legacy behavior | build `RedirectResponse("/login", 302)` and call `delete_cookie(result.cookie_name)` |
| Exact cookie behavior to preserve | delete cookie named `access_token` only |
| Exact redirect behavior to preserve | `/login` with `302` |
| Exact JSON response shape to preserve | n/a |
| Exact template error behavior to preserve | n/a |

### `GET /register`

| Item | Plan |
|---|---|
| Old input shape | none |
| Normalized service input | none |
| Normalized service output | none |
| Route wrapper translation back to legacy behavior | unchanged route renders `register.html` |
| Exact cookie behavior to preserve | none |
| Exact redirect behavior to preserve | none |
| Exact JSON response shape to preserve | n/a |
| Exact template error behavior to preserve | render-only route remains unchanged |

### `POST /register`

| Item | Plan |
|---|---|
| Old input shape | form fields `username`, `email`, `password`, `confirm_password` |
| Normalized service input | `RegisterUserCommand(username, email, password, confirm_password)` |
| Normalized service output | `RegistrationResult(ok, code, message, user, assigned_role, is_first_user)` |
| Route wrapper translation back to legacy behavior | on success: `RedirectResponse("/login?msg=Registration successful! Please login.", 302)`; on validation or service failure: render `register.html` with `error=result.message`; on unexpected exception path, preserve current `error=str(e)` behavior if service raises unexpectedly |
| Exact cookie behavior to preserve | none; register does not authenticate user automatically |
| Exact redirect behavior to preserve | redirect to `/login?msg=Registration successful! Please login.` |
| Exact JSON response shape to preserve | n/a |
| Exact template error behavior to preserve | mismatch must show `Passwords do not match`; duplicate must show `Username or email already exists`; unexpected errors still surface via `error=str(e)` if they do today |

### `POST /api/v1/users/login`

| Item | Plan |
|---|---|
| Old input shape | `OAuth2PasswordRequestForm` with `username`, `password` |
| Normalized service input | `BearerLoginCommand(username, password)` |
| Normalized service output | `AuthenticationResult(ok, code, message, user, access_token)` |
| Route wrapper translation back to legacy behavior | on success: return `{ "access_token": result.access_token, "token_type": "bearer" }`; on invalid credentials: raise `HTTPException(401, detail="Incorrect username or password", headers={"WWW-Authenticate":"Bearer"})` |
| Exact cookie behavior to preserve | none; API login must not set cookies in this batch |
| Exact redirect behavior to preserve | none |
| Exact JSON response shape to preserve | exactly `{ "access_token": "<jwt>", "token_type": "bearer" }` |
| Exact template error behavior to preserve | n/a |

### `POST /api/v1/users/`

| Item | Plan |
|---|---|
| Old input shape | JSON body `UserCreate { username, email, password }` |
| Normalized service input | `CreateApiUserCommand(username, email, password)` |
| Normalized service output | `ApiUserCreateResult(ok, code, message, user)` |
| Route wrapper translation back to legacy behavior | on success: return `{ "id": user.id, "username": user.username }`; on duplicate username: raise `HTTPException(400, detail="Username already registered")` |
| Exact cookie behavior to preserve | none |
| Exact redirect behavior to preserve | none |
| Exact JSON response shape to preserve | exactly `{ "id": int, "username": str }` |
| Exact template error behavior to preserve | n/a |

### `GET /api/v1/users/me`

| Item | Plan |
|---|---|
| Old input shape | bearer token via dependency |
| Normalized service input | `ResolveCurrentUserContextQuery(auth_mode="bearer", token_value=token)` via `get_current_user` wrapper |
| Normalized service output | `ResolveUserContextResult(ok, code, user)` then route returns current JSON shape |
| Route wrapper translation back to legacy behavior | dependency still injects `current_user`; route returns `{ "username": current_user.username, "email": current_user.email, "roles": [r.name for r in current_user.roles] }` |
| Exact cookie behavior to preserve | none |
| Exact redirect behavior to preserve | none |
| Exact JSON response shape to preserve | exactly current flat `username/email/roles` object |
| Exact template error behavior to preserve | n/a |

### `app/auth.py` compatibility wrappers

#### `get_current_user`

- Old input shape:
  - bearer token string from `oauth2_scheme`
- Normalized service input:
  - `ResolveCurrentUserContextQuery(auth_mode="bearer", token_value=token)`
- Normalized service output:
  - `ResolveUserContextResult`
- Wrapper behavior to preserve:
  - raise `401`
  - `detail="Could not validate credentials"`
  - `headers={"WWW-Authenticate":"Bearer"}`

#### `get_current_user_from_cookie`

- Old input shape:
  - raw cookie value from `request.cookies["access_token"]`
- Normalized service input:
  - `ResolveCurrentUserContextQuery(auth_mode="cookie", token_value=cookie_value)`
- Normalized service output:
  - `ResolveUserContextResult`
- Wrapper behavior to preserve:
  - return `None` when cookie missing
  - return `None` on token decode failure
  - return `None` if user lookup fails
  - continue stripping optional `Bearer ` prefix from the cookie value before decode

### `app/rbac.py` compatibility wrapper

- `require_role` must preserve:
  - dependency on `get_current_user`
  - current `403` error
  - current error detail format: `Operation requires {role_name} role`
- Optional internal change:
  - role-name comparison can call a small helper provided by `AuthService`
- Route-facing behavior:
  - unchanged

---

## 5. Registration Bootstrap Rules

Batch 1 must preserve the existing SSR self-registration behavior exactly, even if that logic is moved wholesale into `AuthService.register_user()`.

### Rules to preserve

#### 1. Username/email uniqueness validation

Current behavior in `POST /register`:

- query `User` where username matches OR email matches
- if a matching record exists, render `register.html` with:
  - `error="Username or email already exists"`

Preservation rule:

- `AuthService.register_user()` must keep the same combined uniqueness check
- route wrapper must keep the same template error text

#### 2. Password confirmation validation

Current behavior:

- compare `password` and `confirm_password`
- on mismatch, render:
  - `register.html` with `error="Passwords do not match"`

Preservation rule:

- service performs the check
- route wrapper preserves the exact error text in the template context

#### 3. Role bootstrap if missing

Current route behavior:

- if `Viewer` role is missing, create the full role set:
  - Viewer
  - Editor
  - ProjectManager
  - Admin
  - Tagger
  - CopyEditor
  - GraphicDesigner
  - Typesetter
  - QCPerson
  - PPD
  - PermissionsManager

Preservation rule:

- `AuthService.register_user()` must preserve this fallback bootstrap path
- do not assume startup bootstrap always ran successfully
- do not reduce or rename the role list in this batch

#### 4. First-user admin assignment

Current route behavior:

- `is_first_user = db.query(models.User).count() == 0`
- first registered user gets `Admin`

Preservation rule:

- keep the same first-user detection logic
- keep `Admin` assignment behavior exactly

#### 5. Non-first-user default role assignment

Current route behavior:

- subsequent users receive `Viewer`

Preservation rule:

- keep `Viewer` as the default self-registration role
- do not infer roles from any other source in this batch

#### 6. Success redirect and query-string message

Current route behavior:

- `RedirectResponse(url="/login?msg=Registration successful! Please login.", status_code=302)`

Preservation rule:

- keep the exact URL string and redirect status code
- do not move the success message into flash storage or JSON

### Important non-goal

Do not normalize the API user-create route to use SSR self-registration behavior in Batch 1. The API create-user route must keep its current narrower behavior unless explicitly changed in a later contract phase.

---

## 6. Token and Session Preservation

### Cookie preservation rules

The SSR login/logout flow must preserve:

- cookie name:
  - `access_token`
- cookie value format:
  - `Bearer <jwt>`
- cookie write behavior:
  - `httponly=True`
- cookie clear behavior:
  - `response.delete_cookie("access_token")`

Do not change in this batch:

- secure flag
- samesite
- domain
- path
- max-age
- expiration policy at the cookie level

### Bearer token preservation rules

The API login flow must preserve:

- JSON response keys:
  - `access_token`
  - `token_type`
- `token_type` literal:
  - `"bearer"`
- invalid login failure:
  - `401`
  - `detail="Incorrect username or password"`
  - `WWW-Authenticate: Bearer`

### Token creation preservation rules

`create_access_token` behavior must remain unchanged:

- token includes the original `data` payload
- `exp` claim still derived from:
  - explicit `expires_delta` if provided
  - otherwise `settings.ACCESS_TOKEN_EXPIRE_MINUTES`
- JWT still uses:
  - `settings.SECRET_KEY`
  - `settings.ALGORITHM`

### Current-user resolution preservation rules

#### `get_current_user`

Must preserve:

- bearer token source from `oauth2_scheme`
- `401` on invalid token
- `detail="Could not validate credentials"`
- `WWW-Authenticate: Bearer`
- query by `username == payload["sub"]`

#### `get_current_user_from_cookie`

Must preserve:

- cookie source: `request.cookies.get("access_token")`
- `None` on missing cookie
- strip optional `Bearer ` prefix
- decode with the same secret and algorithm
- return `None` on any failure instead of raising

### No auth-policy redesign rule

Batch 1 must not:

- convert cookie auth to bearer-only auth
- convert bearer auth to cookie-based auth
- add CSRF tokens
- change CORS
- change role gating rules
- change route dependency signatures
- normalize inactive-user handling unless it already exists in the current behavior

---

## 7. Refactor Steps

Batch 1 should be implemented in the following sequence and should remain deployable after each step.

### Step 1: create `AuthService` shell

Create a new service module, recommended as:

- `app/services/auth_service.py`

Initial contents should include:

- service class skeleton
- result-code enum or string constants
- command/result data structures
- method stubs for:
  - `authenticate_for_cookie_session`
  - `authenticate_for_bearer_token`
  - `register_user`
  - `create_api_user`
  - `resolve_current_user_context`
  - `logout_session_intent`

No route behavior changes should happen in this step.

### Step 2: move shared auth logic

Move into `AuthService`:

- username lookup
- username/email lookup for self-registration
- password verification
- token creation call
- token decode and user resolution
- registration password confirmation
- role bootstrap logic
- first-user admin assignment
- API create-user logic

Keep in `app/auth.py`:

- `hash_password`
- `verify_password`
- `create_access_token`
- `oauth2_scheme`

Reason:

- avoids crypto helper churn
- avoids circular import risk
- keeps dependency signatures stable

### Step 3: adapt SSR routes

Update `app/routers/web.py` so:

- `POST /login` calls `AuthService.authenticate_for_cookie_session`
- `GET /logout` calls `AuthService.logout_session_intent`
- `POST /register` calls `AuthService.register_user`

Do not change:

- route signatures
- template names
- redirect destinations
- cookie name/value format
- template error strings

### Step 4: adapt API routes

Update `app/routers/users.py` so:

- `POST /api/v1/users/login` calls `AuthService.authenticate_for_bearer_token`
- `POST /api/v1/users/` calls `AuthService.create_api_user`
- `GET /api/v1/users/me` continues using `get_current_user`, but `get_current_user` is now service-backed internally

Do not change:

- JSON field names
- HTTP status codes
- `WWW-Authenticate` header behavior

### Step 5: centralize registration logic

Move the entire registration workflow from `web.register_submit` into `AuthService.register_user`, including:

- password mismatch check
- username/email uniqueness check
- role bootstrap fallback
- first-user admin assignment
- non-first-user viewer assignment
- user creation and role linking

Important:

- do not silently merge API create-user behavior into this flow
- keep API create-user separate unless a dedicated compatibility path is preserved

### Step 6: preserve compatibility wrappers

Update `app/auth.py` and `app/rbac.py` only so far as needed to delegate to the service while preserving current dependency contracts:

- `get_current_user` remains a FastAPI dependency and still raises `401`
- `get_current_user_from_cookie` remains a FastAPI dependency and still returns `None` on failure
- `require_role` remains a FastAPI dependency factory and still raises the current `403`

### Step 7: run regression tests

Do not consider Batch 1 complete until:

- route-level regression tests pass
- helper compatibility tests pass
- cookie and bearer behavior both remain intact

---

## 8. Regression Test Plan

Batch 1 should ship only with explicit regression coverage around the moved auth behaviors.

### Pre-extraction test baseline

Before code changes:

- capture current SSR redirect behavior
- capture current cookie contents/presence
- capture current API login payload
- capture current registration bootstrap behavior
- capture current dependency behavior for bearer and cookie auth

### Required tests

#### 1. Successful SSR login

Test:

- submit valid `username` and `password` to `POST /login`

Verify:

- response is `302`
- redirect target is `/dashboard`
- cookie named `access_token` is set
- cookie value starts with `Bearer `
- cookie is set with `httponly=True`

#### 2. Failed SSR login

Test:

- submit invalid credentials to `POST /login`

Verify:

- no redirect to `/dashboard`
- `login.html` is rendered
- template context or response body contains `Invalid credentials`
- no auth cookie is set

#### 3. Logout

Test:

- call `GET /logout`

Verify:

- response is `302`
- redirect target is `/login`
- `access_token` cookie delete behavior is present

#### 4. `GET /register`

Test:

- call `GET /register`

Verify:

- response renders `register.html`
- no unexpected auth dependency is introduced

#### 5. Successful register for first user

Setup:

- no users in DB

Test:

- post valid registration data to `POST /register`

Verify:

- response redirects to `/login?msg=Registration successful! Please login.`
- created user exists
- created user has `Admin` role
- role bootstrap occurs if roles were absent

#### 6. Successful register for subsequent user

Setup:

- one existing user already exists

Test:

- post valid registration data to `POST /register`

Verify:

- response redirects to the same login URL with message
- created user has `Viewer` role

#### 7. Duplicate username/email

Setup:

- existing user with same username or email

Test:

- post registration data to `POST /register`

Verify:

- `register.html` re-renders
- error text is exactly `Username or email already exists`

#### 8. Password mismatch

Test:

- submit different `password` and `confirm_password`

Verify:

- `register.html` re-renders
- error text is exactly `Passwords do not match`

#### 9. Bearer login API

Test:

- submit valid OAuth2 form data to `POST /api/v1/users/login`

Verify:

- response is `200`
- JSON includes `access_token`
- JSON includes `token_type`
- `token_type == "bearer"`
- no cookie is set by this route

Also verify failure case:

- invalid credentials produce `401`
- `detail == "Incorrect username or password"`
- `WWW-Authenticate == Bearer`

#### 10. `/api/v1/users/me` under bearer auth

Test:

- call `GET /api/v1/users/me` with a valid bearer token

Verify:

- response contains current fields:
  - `username`
  - `email`
  - `roles`

Also verify invalid bearer token:

- returns `401`
- `detail == "Could not validate credentials"`

#### 11. Cookie-auth compatibility for existing SSR routes

Test:

- issue a valid `access_token` cookie in the current format (`Bearer <jwt>`)
- hit an SSR route that depends on `get_current_user_from_cookie`, such as `/dashboard`

Verify:

- SSR route continues recognizing the current cookie format
- missing/invalid cookie still behaves as before

### Additional helper-level tests

Recommended helper/dependency tests:

- `get_current_user_from_cookie` returns `None` for:
  - missing cookie
  - malformed cookie
  - invalid JWT
  - token with missing `sub`
  - token for nonexistent user
- `get_current_user` raises `401` for the same bearer-side invalid cases
- `require_role("ProjectManager")` still raises the current `403` detail for users without that role

---

## 9. File-Level Change Plan

### Expected files to touch

#### `app/auth.py`

Why:

- keep low-level token/hash helpers in place
- convert `get_current_user` into a thin compatibility dependency backed by `AuthService.resolve_current_user_context`
- convert `get_current_user_from_cookie` into a thin compatibility dependency backed by the same service

Expected change type:

- internal delegation only
- no signature changes
- no response-contract changes

#### `app/rbac.py`

Why:

- keep `require_role` compatible while optionally delegating role inspection to a shared auth service helper
- align role checks with the now-centralized user-resolution path

Expected change type:

- minimal wrapper refactor
- preserve current dependency signature and `403` detail text

#### `app/routers/web.py`

Why:

- replace inline login/register/logout business logic with calls into `AuthService`
- preserve SSR template and redirect wrappers

Expected change type:

- thin wrapper conversion only
- no route path or form-field changes

#### `app/routers/users.py`

Why:

- replace inline API login and user-create business logic with `AuthService`
- keep API `/me` route using a compatibility dependency

Expected change type:

- thin wrapper conversion only
- preserve JSON outputs and HTTP errors

#### `app/services/auth_service.py` (new)

Why:

- new source of truth for auth workflows in Batch 1

Expected contents:

- service class
- command/result objects
- auth result/error codes
- registration bootstrap logic
- current-user resolution helpers

#### Optional `app/services/__init__.py`

Why:

- only if the codebase convention exports services from package init

Expected change type:

- import/export wiring only

#### Test files

Expected new or updated test coverage:

- auth route tests
- auth helper/dependency tests
- role gate compatibility tests

Potential locations depend on existing repo test conventions, but the Batch-1 plan should expect at minimum:

- one test module for SSR auth routes
- one test module for API auth routes
- one test module for auth helper/dependency compatibility

### Files that should remain untouched unless strictly necessary

- `app/main.py`
- project/chapter/file/processing routers
- templates
- CORS config
- WOPI routes

If any of those need to change during Batch 1, the change is likely leaking beyond scope.

---

## 10. Safe Stopping Point

Batch 1 is done when all of the following are true:

1. `AuthService` exists and is the source of truth for:
   - SSR login credential validation
   - API login credential validation
   - SSR registration workflow
   - API user-create workflow
   - current-user resolution from bearer token
   - current-user resolution from cookie token
   - logout cookie-delete intent
2. `app/routers/web.py` no longer owns inline login/register business rules beyond HTTP wrapper concerns.
3. `app/routers/users.py` no longer owns inline login/create-user business rules beyond HTTP wrapper concerns.
4. `app/auth.py` remains compatibility-safe:
   - same helper names
   - same dependency signatures
   - same bearer vs cookie behavior
5. `app/rbac.py` still exposes the same `require_role` behavior.
6. No route paths changed.
7. No route signatures changed.
8. No cookie name changed.
9. No JSON response shape changed.
10. No redirect destination changed.
11. No template error string changed.
12. Regression tests listed in Section 8 pass.

### Explicit not-done conditions

Batch 1 is not complete if any of the following happens:

- auth redesign begins
- cookie policy changes
- bearer/cookie contracts are unified publicly
- admin route cleanup starts
- root-route ownership is changed
- registration behavior is normalized across SSR and API routes
- role gating is redesigned
- non-auth routes are modified to consume a different auth contract

### Batch-1 completion statement

The correct stopping point is:

"Auth workflows are service-owned, route wrappers are thin, helpers stay compatibility-safe, and every observable SSR/API auth behavior remains unchanged."

