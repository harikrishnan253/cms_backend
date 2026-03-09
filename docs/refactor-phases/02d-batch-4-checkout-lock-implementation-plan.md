# Batch 4 Implementation Plan: CheckoutLockService

No application code was modified. This document defines the implementation plan for Batch 4 of the Phase-2 extraction program: centralizing file lock acquisition and release behavior into a dedicated `CheckoutLockService` while preserving all current routes, redirects, query messages, lock semantics, and processing conflict behavior.

Batch 3 centralized file storage and overwrite versioning behavior. The next backend extraction target is lock ownership, which is still split across:

- SSR checkout routes in [app/routers/web.py](../../app/routers/web.py)
- upload overwrite preflight in [app/routers/web.py](../../app/routers/web.py)
- processing preflight and background-task unlocks in [app/routers/processing.py](../../app/routers/processing.py)

This batch does not redesign processing orchestration. It only centralizes lock business rules.

---

## 1. Batch Scope

### In-scope flows

- `POST /projects/files/{file_id}/checkout`
- `POST /projects/files/{file_id}/cancel_checkout`
- lock checks in `POST /projects/{project_id}/chapter/{chapter_id}/upload`
- lock/conflict handling used by processing start in [app/routers/processing.py](../../app/routers/processing.py)
- lock release after successful processing
- lock release after failed processing
- lock release after upload overwrite

### In-scope fields

Current source-of-truth lock fields on `models.File`:

- `is_checked_out`
- `checked_out_by_id`
- `checked_out_at`

### Out of scope

- processing engine dispatch redesign
- background task backend changes
- auth/session changes
- route URL changes
- response body redesign
- WOPI changes
- versioning redesign

---

## 2. Current Logic Ownership

### `POST /projects/files/{file_id}/checkout`

Current behavior in [app/routers/web.py](../../app/routers/web.py):

| Concern | Current ownership |
|---|---|
| auth gate | route redirects unauthenticated user to `/login` |
| file lookup | route queries `models.File` by id |
| missing file | raises `HTTPException(status_code=404)` |
| conflict rule | if `is_checked_out` and `checked_out_by_id != user.id`, redirect with `msg=File+Locked+By+Other` |
| idempotent owner behavior | if already locked by same user, route allows success path |
| lock acquisition | sets `is_checked_out=True`, `checked_out_by_id=user.id`, `checked_out_at=datetime.utcnow()` |
| commit | route commits immediately |
| success redirect | `/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=File+Checked+Out` |

Current lock fields mutated:

- `is_checked_out`
- `checked_out_by_id`
- `checked_out_at`

### `POST /projects/files/{file_id}/cancel_checkout`

Current behavior in [app/routers/web.py](../../app/routers/web.py):

| Concern | Current ownership |
|---|---|
| auth gate | route redirects unauthenticated user to `/login` |
| file lookup | route queries `models.File` by id |
| missing file | raises `HTTPException(status_code=404)` |
| owner-check behavior | only unlocks if `is_checked_out` and `checked_out_by_id == user.id` |
| non-owner behavior | no-op |
| unlock mutation | sets `is_checked_out=False`, `checked_out_by_id=None` |
| `checked_out_at` handling | not cleared |
| commit | only commits if owner unlock occurs |
| redirect | `/projects/{project_id}/chapter/{chapter_id}?tab={category}&msg=Checkout+Cancelled` |

Current compatibility note:

- non-owner cancel checkout does not raise an error
- non-owner cancel checkout still redirects with the normal cancellation message

### Lock checks in `POST /projects/{project_id}/chapter/{chapter_id}/upload`

Current behavior:

| Concern | Current ownership |
|---|---|
| duplicate detection | route queries for existing file by `chapter_id`, `category`, `filename` |
| conflict rule | if existing file is checked out and lock owner is not current user, route skips overwrite |
| conflict response | no error, no message, loop simply continues |
| overwrite lock finalization | after successful overwrite, `VersioningService.increment_file_version(...)` currently releases lock by setting `is_checked_out=False` and `checked_out_by_id=None` |
| `checked_out_at` handling | overwrite flow does not clear `checked_out_at` |

Current behavior to preserve:

- locked-by-other overwrite is silently skipped
- overwrite of unlocked file or self-locked file proceeds
- successful overwrite auto-checks the file in

### Processing preflight lock behavior

Current behavior in [app/routers/processing.py](../../app/routers/processing.py):

| Concern | Current ownership |
|---|---|
| preflight conflict check | if `file_record.is_checked_out` and owner is not current user, route raises `HTTPException(status_code=400, detail=f"File is locked by {file_record.checked_out_by.username}")` |
| self-owned lock behavior | if already locked by same user, processing continues |
| lock acquisition | if not already checked out, set `is_checked_out=True`, `checked_out_by_id=user.id`, `checked_out_at=datetime.utcnow()`, then `db.commit()` |
| success response | JSON says processing started and file is locked |

Current behavior to preserve:

- conflict remains an HTTP 400, not redirect
- detail string remains `File is locked by {username}`
- self-owned lock is accepted
- fresh lock acquisition commits before versioning/processing starts

### Processing success unlock behavior

Current behavior in the background task:

| Concern | Current ownership |
|---|---|
| unlock mutation | sets `is_checked_out=False`, `checked_out_by_id=None`, `checked_out_at=None` |
| commit | commits after unlock and result registration |

Current behavior to preserve:

- successful processing fully clears all three lock fields

### Processing failure unlock behavior

Current behavior in the background task exception handler:

| Concern | Current ownership |
|---|---|
| unlock mutation | sets `is_checked_out=False`, `checked_out_by_id=None` |
| `checked_out_at` handling | does not clear `checked_out_at` |
| commit | commits after unlock |

Current behavior to preserve:

- failed processing still releases the lock
- failed processing currently leaves `checked_out_at` unchanged

---

## 3. CheckoutLockService Design

Add a new service module:

- `app/services/checkout_lock_service.py`

The service owns lock business rules, not redirects or HTTP response formatting.

### Result / error model

Recommended result codes:

- `SUCCESS`
- `FILE_NOT_FOUND`
- `LOCKED_BY_OTHER`
- `ALREADY_LOCKED_BY_OWNER`
- `NOT_LOCKED`
- `NOT_LOCK_OWNER`
- `UNLOCKED`
- `NO_OP`

Recommended dataclasses:

```yaml
LockResult:
  ok: bool
  code: str
  file: models.File | None
  owner_id: int | None
  owner_username: str | None
  lock_changed: bool
```

```yaml
LockAvailabilityResult:
  available: bool
  locked_by_other: bool
  owner_id: int | None
  owner_username: str | None
```

### `checkout_file(...)`

Purpose:

- centralize SSR/manual checkout logic

Inputs:

```yaml
db: Session
file_record: models.File
user_id: int
timestamp: datetime
```

Outputs:

```yaml
LockResult
```

DB dependencies:

- mutates `models.File`

Compatibility constraints:

- if locked by another user, do not mutate lock fields
- if locked by same user, keep success behavior
- on success, set `is_checked_out=True`, `checked_out_by_id=user_id`, `checked_out_at=timestamp`
- commit stays in route wrapper in this batch unless explicitly centralized per-call

### `cancel_checkout(...)`

Purpose:

- centralize SSR cancel behavior

Inputs:

```yaml
db: Session
file_record: models.File
user_id: int
```

Outputs:

```yaml
LockResult
```

Compatibility constraints:

- only unlock if current user owns the lock
- if not owner, return no-op result
- when unlocking, set `is_checked_out=False`, `checked_out_by_id=None`
- do not clear `checked_out_at` for SSR cancel, because current route does not

### `assert_lock_available(...)`

Purpose:

- shared preflight for upload overwrite and similar non-processing flows

Inputs:

```yaml
file_record: models.File
user_id: int
```

Outputs:

```yaml
LockAvailabilityResult
```

Compatibility constraints:

- treat self-owned lock as available
- treat unlocked file as available
- treat other-owned lock as unavailable
- do not mutate DB state

### `acquire_processing_lock(...)`

Purpose:

- centralize processing preflight lock logic without redesigning processing flow

Inputs:

```yaml
file_record: models.File
user_id: int
timestamp: datetime
```

Outputs:

```yaml
LockResult
```

Compatibility constraints:

- if locked by another user, return result identifying other owner
- if locked by same user, do not change fields
- if unlocked, set `is_checked_out=True`, `checked_out_by_id=user_id`, `checked_out_at=timestamp`
- route keeps current HTTP 400 formatting and current commit timing

### `release_lock(...)`

Purpose:

- generic unlock helper for background flows

Inputs:

```yaml
file_record: models.File
clear_timestamp: bool = False
```

Outputs:

```yaml
LockResult
```

Compatibility constraints:

- always set `is_checked_out=False`, `checked_out_by_id=None`
- clear `checked_out_at` only when `clear_timestamp=True`

### `release_lock_if_owner(...)`

Purpose:

- owner-aware unlock helper for SSR cancel or guarded unlock flows

Inputs:

```yaml
file_record: models.File
user_id: int
clear_timestamp: bool = False
```

Outputs:

```yaml
LockResult
```

Compatibility constraints:

- if user is not owner, no-op
- if user is owner, unlock with current field rules

### `finalize_overwrite_lock_state(...)`

Purpose:

- capture the current upload-overwrite post-write lock behavior

Inputs:

```yaml
file_record: models.File
```

Outputs:

```yaml
LockResult
```

Compatibility constraints:

- set `is_checked_out=False`
- set `checked_out_by_id=None`
- do not clear `checked_out_at`
- use this helper from overwrite flows instead of embedding the rule in versioning or the route

---

## 4. Compatibility Wrapper Plan

### `POST /projects/files/{file_id}/checkout`

Route keeps:

- auth gate
- file lookup
- 404 behavior
- redirect destinations and query messages

Route delegates:

- lock decision and mutation to `CheckoutLockService.checkout_file(...)`

Wrapper compatibility rules:

- if service returns `LOCKED_BY_OTHER`, redirect to current chapter tab with `msg=File+Locked+By+Other`
- if service returns `SUCCESS` or `ALREADY_LOCKED_BY_OWNER`, redirect with `msg=File+Checked+Out`
- commit timing remains immediate

### `POST /projects/files/{file_id}/cancel_checkout`

Route keeps:

- auth gate
- file lookup
- 404 behavior
- redirect destination and query message

Route delegates:

- owner-aware unlock logic to `CheckoutLockService.cancel_checkout(...)` or `release_lock_if_owner(...)`

Wrapper compatibility rules:

- non-owner/no-op still redirects with `msg=Checkout+Cancelled`
- commit occurs only if actual unlock happens, preserving current behavior

### Upload overwrite lock preflight

Route keeps:

- existing-file lookup
- current loop structure
- current silent skip behavior for locked-by-other files

Route delegates:

- lock availability decision to `CheckoutLockService.assert_lock_available(...)`
- overwrite post-write unlock to `CheckoutLockService.finalize_overwrite_lock_state(...)`

Wrapper compatibility rules:

- other-owned lock remains silent skip
- overwrite still auto-checks in the file
- commit boundary stays unchanged

### Processing preflight

Processing route keeps:

- overall workflow shape
- current HTTP 400 response shape/detail
- current JSON success payload
- current commit boundaries

Processing route delegates:

- conflict detection and fresh lock acquisition to `CheckoutLockService.acquire_processing_lock(...)`
- background-task unlock behavior to `release_lock(...)`

Wrapper compatibility rules:

- conflict remains `HTTPException(status_code=400, detail=f"File is locked by {username}")`
- fresh lock acquisition still commits before versioning/processing starts

---

## 5. Lock State Rules

The service layer must treat the `File` row as the source of truth.

### When a file becomes checked out

- manual checkout: immediately when `checkout_file` succeeds
- processing start: immediately before processing/versioning continues, if file was not already self-locked

### Who may cancel checkout

- current owner only
- non-owner cancel remains a no-op

### What happens on overwrite

- if locked by another user: overwrite is skipped
- if unlocked or self-locked: overwrite proceeds
- after overwrite completes successfully: file is auto-unlocked by clearing `is_checked_out` and `checked_out_by_id`
- overwrite does not currently clear `checked_out_at`

### What happens when processing starts

- if locked by another user: processing is blocked with HTTP 400
- if already locked by the same user: processing continues without lock mutation
- if unlocked: processing acquires lock and commits

### What happens on processing conflict

- no DB mutation
- route returns HTTP 400 with current detail string

### What happens on successful processing

- file is unlocked
- `checked_out_at` is cleared

### What happens on failed processing

- file is unlocked
- `checked_out_at` is not currently cleared

These asymmetries must be preserved in Batch 4 even if they are not ideal.

---

## 6. Regression Test Plan

### Owner checkout succeeds

Assertions:

- lock fields set correctly
- commit occurs
- redirect remains `File+Checked+Out`

### Non-owner checkout conflict preserves current message

Assertions:

- no lock mutation
- redirect remains `File+Locked+By+Other`

### Owner cancel checkout succeeds

Assertions:

- `is_checked_out=False`
- `checked_out_by_id=None`
- redirect remains `Checkout+Cancelled`

### Non-owner cancel checkout remains no-op

Assertions:

- lock row unchanged
- redirect still `Checkout+Cancelled`

### Upload overwrite preserves current lock semantics

Assertions:

- locked-by-other file is skipped
- self-owned lock can be overwritten
- overwrite finalization unlocks file
- `checked_out_at` remains unchanged after overwrite finalization

### Processing start conflict preserves current behavior

Assertions:

- HTTP 400 returned
- detail string remains `File is locked by {username}`
- no lock mutation

### Processing lock acquisition preserves current behavior

Assertions:

- unlocked file becomes checked out by current user
- `checked_out_at` is set
- commit still occurs before processing continues

### Lock release after successful processing

Assertions:

- all three fields cleared

### Lock release after failed processing

Assertions:

- `is_checked_out=False`
- `checked_out_by_id=None`
- `checked_out_at` remains unchanged

---

## 7. File-Level Change Plan

### [app/routers/web.py](../../app/routers/web.py)

Purpose:

- remove checkout/cancel and upload-overwrite lock business rules from route bodies
- keep redirects, messages, and 404 behavior unchanged

Expected edits:

- checkout route calls `CheckoutLockService.checkout_file(...)`
- cancel route calls `CheckoutLockService.cancel_checkout(...)`
- upload route calls `assert_lock_available(...)` and `finalize_overwrite_lock_state(...)`

### [app/routers/processing.py](../../app/routers/processing.py)

Purpose:

- remove lock business rules from processing preflight and background-task unlock handling
- keep the current processing workflow shape intact

Expected edits:

- preflight uses `acquire_processing_lock(...)`
- success/failure unlock paths use `release_lock(...)`
- current exception/JSON behavior remains in the route/task wrapper

### `app/services/checkout_lock_service.py`

Purpose:

- centralize all lock mutation rules

Expected contents:

- result dataclasses / codes
- checkout, cancel, availability, processing-acquire, and release helpers

### Supporting helpers

Only if strictly needed:

- small utility dataclasses in the service module itself
- no broader infrastructure changes

---

## 8. Safe Stopping Point

Batch 4 is complete when all of the following are true:

- lock mutation logic is centralized in `CheckoutLockService`
- `web.py` checkout routes are thin wrappers
- upload overwrite no longer embeds lock business rules directly
- `processing.py` still has the same overall workflow shape but no longer owns lock business rules
- current redirect destinations and query messages remain unchanged
- current processing conflict behavior and error detail remain unchanged
- current overwrite auto-unlock behavior remains unchanged
- current success/failure processing unlock asymmetry remains unchanged

### Explicit non-goals at the stopping point

- no processing backend redesign
- no background task system changes
- no route changes
- no auth changes
- no WOPI changes
- no response contract changes

### Recommended next step after Batch 4

After Batch 4, the next extraction target should be processing orchestration proper: permission checks, task dispatch, status semantics, and output registration, using the already-centralized storage, versioning, and lock services as dependencies.
