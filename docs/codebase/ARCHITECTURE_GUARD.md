# Architecture Guard

## 1. Purpose

This file defines how architecture rules are enforced during development and review.

## 2. Enforcement Layers

### a) Code Review Enforcement

Check every PR for:
- no direct DB calls in routers
- no frontend calls outside `/api/v2`
- no business logic in frontend
- no new SSR routes
- no auth/session changes without prior documentation

Reject PRs that violate any item above.

### b) Linting / Static Checks (to be implemented)

Flag:
- imports from `app/services` in new files
- direct DB usage in routers
- frontend usage of non-API endpoints for product flows

Add:
- ESLint rule for API-call boundaries
- Python import guard for backend ownership boundaries

Do not treat these checks as optional once implemented.

### c) Test Enforcement

- Require `pytest` coverage for any new API.
- Require `vitest` coverage for any new UI flow.
- Block merge on missing required tests.

## 3. High-Risk Change Triggers

Require explicit approval for any change touching:
- auth/session
- WOPI/editor
- `/api/v2` contracts
- database schema
- compatibility wrapper removal

Do not proceed on these areas without explicit approval.

## 4. Migration Guardrails

- Remove SSR only in documented phases.
- Remove wrappers only through a documented removal plan.
- Do not run bulk refactors without validation.
- Do not combine structural cleanup with behavior changes unless explicitly planned.

## 5. Local Developer Checklist

Before committing:
- backend tests pass
- frontend tests pass
- typecheck passes
- build passes
- no architecture rule violations introduced

## 6. CI Expectations (future)

- `pytest` must pass
- `vitest` must pass
- typecheck must pass
- build must pass
- architecture checks must pass once implemented

## 7. Failure Handling

If a rule is violated:
- stop implementation
- document the reason
- get approval
- then proceed
