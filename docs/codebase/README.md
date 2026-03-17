# CMS Platform - Technical Documentation

## Quick Summary

- This repository is a FastAPI-based CMS backend with a React + TypeScript frontend.
- `/ui` is the primary user interface and consumes the backend’s `/api/v2` contracts.
- The backend remains the system of record for auth, business logic, storage, processing, and review flows.
- Backend code is organized around `app/core`, `app/domains`, `app/integrations`, retained compatibility wrappers, and limited SSR fallback routes.
- Authentication is cookie-based and backend-issued; the frontend does not own tokens.
- WOPI/Collabora editor launch and callback handling remain backend-owned.

## Architecture Snapshot

The frontend under `frontend/` owns the `/ui` user experience and calls `/api/v2` through a typed client layer. The backend under `app/` owns the `/api/v2` contracts, domain services, database writes, file storage, processing orchestration, and review/export behavior.

The backend structure reflects the current refactor state:
- `app/core` for shared runtime concerns
- `app/domains/*` for business/service ownership
- `app/integrations/*` for external boundaries such as WOPI, Collabora config, storage, and AI structuring
- retained wrappers in `app/services`, `app/routers`, and top-level modules for compatibility

Auth remains backend-owned and cookie-based. The frontend now owns `/ui/login` and `/ui/register`, while SSR auth routes remain fallback-only. The WOPI/editor boundary is still backend-owned and should be treated as an integration surface, not a frontend feature.

## How To Use This Documentation

- [OVERVIEW.md](./OVERVIEW.md) -> system purpose and runtime surfaces
- [ARCHITECTURE.md](./ARCHITECTURE.md) -> system design and ownership model
- [BACKEND.md](./BACKEND.md) -> backend structure and router/service roles
- [FRONTEND.md](./FRONTEND.md) -> frontend structure and route ownership
- [AUTH_AND_SESSION.md](./AUTH_AND_SESSION.md) -> auth flow and session model
- [PROJECT_AND_FILE_WORKFLOWS.md](./PROJECT_AND_FILE_WORKFLOWS.md) -> project, chapter, file, upload, lock, and version workflows
- [PROCESSING_AND_REVIEW.md](./PROCESSING_AND_REVIEW.md) -> processing, technical review, and structuring review flows
- [WOPI_AND_EDITOR_BOUNDARY.md](./WOPI_AND_EDITOR_BOUNDARY.md) -> editor/WOPI integration boundary
- [API_V2_REFERENCE.md](./API_V2_REFERENCE.md) -> current `/api/v2` contract surface
- [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md) -> local setup and run instructions
- [TESTING_AND_RELEASE.md](./TESTING_AND_RELEASE.md) -> validation, testing, and release guidance
- [KNOWN_BOUNDARIES_AND_TECH_DEBT.md](./KNOWN_BOUNDARIES_AND_TECH_DEBT.md) -> retained limitations, wrappers, and cleanup debt

## Current System Status

- frontend-owned auth is active through `/ui/login` and `/ui/register`
- SSR auth is retained as fallback only
- domain/integration refactor is complete enough for current release scope
- current documented release position is ready for internal release

## Important Boundaries

- frontend owns user experience
- backend owns business logic
- backend owns auth and session issuance
- backend owns WOPI/editor launch and callbacks
- SSR is fallback only, except for retained backend-owned editor and error surfaces

## Getting Started (Developer)

Start with [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md).

Current local workflow:
- start PostgreSQL on `localhost:5433`
- run the backend with Uvicorn on `localhost:8000`
- run the frontend with Vite on `localhost:5173`

## Warning

- Do not remove compatibility wrappers yet.
- Do not remove SSR auth routes yet.
- Do not change the auth/session model without a dedicated migration step.
- Do not modify the WOPI/editor boundary as part of normal feature work.
