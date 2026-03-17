# Engineering Rules

## 1. Purpose

This file defines non-negotiable engineering rules for the CMS platform.

## 2. Ownership Rules

### Frontend owns
- Own all `/ui` routes.
- Own user interaction.
- Own navigation.

### Backend owns
- Own all `/api/v2` contracts.
- Own business logic.
- Own database access.
- Own file storage.
- Own processing pipelines.

### Backend exclusively owns
- Own authentication.
- Own session cookies.
- Own WOPI/editor integration.

## 3. Auth Rules

- Do not implement token-based auth in the frontend.
- Do not store auth state in `localStorage`.
- Do not store auth state in `sessionStorage`.
- Always use backend-issued cookie auth.
- Always use `/api/v2/session` as the frontend session source of truth.
- Do not bypass `/api/v2/session`.

## 4. API Rules

- Route all frontend communication through `/api/v2`.
- Do not couple frontend code directly to database or backend service internals.
- Do not add hidden endpoints for frontend use.
- Do not call legacy SSR routes from the frontend for normal application behavior.

## 5. SSR Rules

- Treat SSR as fallback-only.
- Do not add new SSR pages.
- Allow SSR only for:
  - login/register, temporarily
  - editor launch
  - error pages

## 6. WOPI / Editor Rules

- Never move WOPI logic to the frontend.
- Never expose editor tokens to the frontend.
- Never move WOPI callbacks out of the backend.
- Always originate editor launch from the backend.

## 7. Structure Rules

- Put new backend features in `app/domains/*`.
- Put new integration code in `app/integrations/*`.
- Do not add new business logic to `app/services`.
- Do not add new business logic to `app/routers`.
- Treat `app/services` as legacy compatibility wrappers unless a planned cleanup says otherwise.
- Treat legacy wrapper routers as compatibility surfaces, not new feature homes.

## 8. Compatibility Rules

- Do not delete compatibility wrappers yet.
- Do not change import paths used in tests without a planned migration.
- Plan and validate wrapper removal explicitly before implementation.
- Preserve current compatibility behavior until removal is approved.

## 9. Testing Rules

- Add a backend test for every new feature.
- Add a frontend test for every new feature.
- Use `pytest` for backend coverage.
- Use `vitest` for frontend coverage.
- Do not add untested endpoints.

## 10. Forbidden Actions

- Do not make direct database calls from routers.
- Do not let frontend code call non-`/api/v2` routes for normal product flows.
- Do not duplicate backend business logic in the frontend.
- Do not break the current auth/session model.
- Do not move editor ownership into the frontend.

## 11. Change Control

- Document any auth change before implementation.
- Document any WOPI/editor change before implementation.
- Document any API contract change before implementation.
- Do not implement changes to auth, WOPI/editor, or API contracts without an explicit written plan.
