# UI Parity Migration Plan

## Purpose

This plan defines the controlled SSR-to-React parity migration for the current CMS UI. The target is visual and structural parity with the existing backend-rendered pages while preserving:

- current React routes under `/ui`
- current `/api/v2` contracts
- backend-owned auth/session issuance
- backend-owned WOPI/editor launch and callback ownership

This is not a redesign plan. The SSR templates under [app/templates](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates) are the visual source of truth.

## 1. SSR Templates and Pages to Replicate

### In Scope for React Parity

| Phase | SSR route(s) | SSR template(s) | Current React route | Notes |
| --- | --- | --- | --- | --- |
| 1 | `/login` | `login.html` | `/ui/login` | Standalone auth card, not `base_tailwind.html` shell |
| 2 | `/register` | `register.html` | `/ui/register` | Standalone auth card, same auth chrome as login |
| 3 | `/dashboard` | `dashboard.html`, `base_tailwind.html` | `/ui/dashboard` | Sidebar shell, metrics row, admin shortcuts, project summary area |
| 4 | `/projects` | `projects.html`, `base_tailwind.html` | `/ui/projects` | Breadcrumb header, project cards, create-project handoff |
| 5 | `/projects/{project_id}`, `/projects/{project_id}/chapters` | `project_chapters.html`, `base_tailwind.html` | `/ui/projects/:projectId` | Windows Explorer-like header, left tree, chapter grid/list, create/rename/delete |
| 6 | `/projects/{project_id}/chapter/{chapter_id}` | `chapter_detail.html`, `base_tailwind.html` | `/ui/projects/:projectId/chapters/:chapterId` | Explorer shell, category navigation, upload/actions, processing entry points |
| 7 | `/admin` | `admin_dashboard.html`, `base_tailwind.html` | `/ui/admin` | Admin stats cards and management links |
| 8 | `/admin/users`, `/admin/users/create`, `/admin/users/{user_id}/edit`, `/admin/users/{user_id}/password` | `admin_users.html`, `admin_create_user.html`, `admin_edit_user.html`, `admin_change_password.html`, `base_tailwind.html` | `/ui/admin/users` | React route is consolidated; SSR source spans table plus create/edit/password forms |
| 9 | `/files/{file_id}/technical/edit` | `technical_editor_form.html`, `base_tailwind.html` | `/ui/projects/:projectId/chapters/:chapterId/files/:fileId/technical-review` | Technical scan/apply shell only, no WOPI dependency |
| 10 | `/files/{file_id}/structuring/review` | `structuring_review.html`, `base_tailwind.html` | `/ui/projects/:projectId/chapters/:chapterId/files/:fileId/structuring-review` | Review shell parity only; editor remains backend-owned |

### Explicitly Out of Scope for This Parity Sequence

| SSR route(s) | Template(s) | Status |
| --- | --- | --- |
| `/projects/create` | `project_create.html` | Retained SSR fallback; not part of the requested parity order |
| `/activities` | `activities.html` | Still SSR-only; no `/ui/activities` route exists |
| `/files/{file_id}/edit` | `editor.html` | Retained backend-owned editor/WOPI launch wrapper |
| `/error`-style fallback renders from review/editor flows | `error.html` | Retained backend-owned fallback surface |

## 2. Current React Pages Mapped to SSR Equivalents

| React page | File | SSR source template(s) | Current parity state |
| --- | --- | --- | --- |
| Login page | [LoginPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/LoginPage.tsx) | [login.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/login.html) | Functional, not visually aligned |
| Register page | [RegisterPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/RegisterPage.tsx) | [register.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/register.html) | Functional, not visually aligned |
| Dashboard page | [DashboardPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/DashboardPage.tsx) | [dashboard.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/dashboard.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Data parity, low visual parity |
| Projects list | [ProjectsPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/ProjectsPage.tsx) | [projects.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/projects.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Data parity, low visual parity |
| Project detail | [ProjectDetailPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/ProjectDetailPage.tsx) | [project_chapters.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/project_chapters.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Workflow parity, low visual parity |
| Chapter detail | [ChapterDetailPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/ChapterDetailPage.tsx) | [chapter_detail.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/chapter_detail.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Broad workflow parity, low visual parity |
| Admin dashboard | [AdminDashboardPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/AdminDashboardPage.tsx) | [admin_dashboard.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/admin_dashboard.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Functional, not visually aligned |
| Admin users | [AdminUsersPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/AdminUsersPage.tsx) | [admin_users.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/admin_users.html), [admin_create_user.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/admin_create_user.html), [admin_edit_user.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/admin_edit_user.html), [admin_change_password.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/admin_change_password.html) | Functional, route-consolidated, not visually aligned |
| Technical review | [TechnicalReviewPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/TechnicalReviewPage.tsx) | [technical_editor_form.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/technical_editor_form.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Functional, not visually aligned |
| Structuring review | [StructuringReviewPage.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/pages/StructuringReviewPage.tsx) | [structuring_review.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/structuring_review.html), [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) | Metadata parity only; editor parity intentionally limited |

## 3. Screens with Exact Parity Feasible

### Exact or Near-Exact Parity Feasible

These screens can be made visually equivalent without backend changes or boundary changes:

- Login
- Register
- Dashboard
- Projects list
- Project detail / chapter explorer page
- Chapter detail
- Admin dashboard
- Technical review

### High Parity Feasible with Route/Form Consolidation Caveat

- Admin users

Notes:

- The backend SSR flow spreads user management across `admin_users.html`, `admin_create_user.html`, `admin_edit_user.html`, and `admin_change_password.html`.
- The React UI currently owns a single route, `/ui/admin/users`.
- Visual parity is feasible for the table, action affordances, create form, edit form, password form, and status messaging, but route-level parity is intentionally not exact unless additional `/ui/admin/users/...` routes are added later.

### Parity-Limited by Backend-Owned Editor/WOPI Boundary

- Structuring review shell

Limits:

- [structuring_review.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/structuring_review.html) embeds the live Collabora iframe and relies on backend-generated `collabora_url`.
- The current React page intentionally stops at `/api/v2` metadata, save, export, and return actions.
- Exact SSR parity is not possible unless frontend ownership expands into embedded editor shell rendering, which is explicitly out of scope.

Practical target for phase 10:

- match toolbar, filename, save/export/return placement, status text, and empty/error presentation
- keep actual editor launch as backend-owned handoff

## 4. Recommended Execution Order

The user-requested order should be preserved. Add one preparation wave before phase 1.

### Preparation Wave

1. Restyle the shared React foundation to match [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html) and the standalone auth templates.
2. Replace the current generic `index.css` visual language with SSR-derived tokens:
   - DM Sans
   - slate/emerald palette
   - rounded card scale
   - sidebar/topbar treatment
   - alert/button/form styles
3. Keep current routes, hooks, and `/api/v2` data flow unchanged.

### Screen Execution Order

1. Login
2. Register
3. Dashboard
4. Projects list
5. Project detail
6. Chapter detail
7. Admin dashboard
8. Admin users
9. Technical review
10. Structuring review shell

### Stop Conditions Per Phase

Do not start the next screen until the current screen has:

- side-by-side SSR/React visual review completed
- route behavior unchanged
- existing frontend tests still green
- `npm.cmd run typecheck` and `npm.cmd run build` green
- no backend contract changes introduced for parity only

## 5. Component Reuse Strategy

### Reuse and Restyle Existing React Components

| Area | Current React component(s) | Planned parity action |
| --- | --- | --- |
| Shared shell | [AppLayout.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/components/layout/AppLayout.tsx) | Restyle to match `base_tailwind.html` sidebar, nav states, footer user card, and logout placement |
| Shared states | [LoadingState.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/components/ui/LoadingState.tsx), [ErrorState.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/components/ui/ErrorState.tsx), [EmptyState.tsx](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/components/ui/EmptyState.tsx) | Restyle to match SSR alerts, empty-folder states, and embedded error blocks |
| Dashboard | `DashboardStatsGrid`, `DashboardProjectGrid` | Keep data wiring; restyle cards, headings, admin shortcuts, and project section to mirror `dashboard.html` |
| Projects list | `ProjectsTable` | Convert from generic table feel to SSR card grid with delete affordance placement matching `projects.html` |
| Project detail | `ProjectMetadataPanel`, `ProjectChaptersTable`, `ChapterCreateForm` | Recompose into explorer chrome, left tree, grid/list chapter view, modals/context menus from `project_chapters.html` |
| Chapter detail | `ChapterMetadataPanel`, `ChapterCategorySummary`, `ChapterFilesTable`, `ChapterUploadPanel`, `ProcessingStatusPanel` | Recompose into command bar, address bar, left folder nav, folder tiles, and category-specific file grids/tables from `chapter_detail.html` |
| Admin | `AdminStatsGrid`, `AdminUsersTable`, `AdminCreateUserForm` | Restyle to match admin cards and user table; likely split form sections visually even if route stays consolidated |
| Technical review | `TechnicalIssuesForm` | Restyle into SSR review shell with sticky header, loading/error blocks, and grouped issue sections |
| Structuring review | `StructuringMetadataPanel`, `StructuringSaveForm`, `StructuringReturnAction` | Restyle toolbar and fallback shell only; keep backend-owned editor launch boundary |
| Notifications | `NotificationBell` | Align icon, placement, and dropdown tone to the retained shell styling |

### New Shared Components Allowed for Parity

Create only if they reduce duplication across the parity phases:

- `AuthCard`
- `SidebarShell`
- `CommandBar`
- `AddressBar`
- `ExplorerNavPane`
- `MetricCard`
- `StatusAlert`
- `FolderTile`
- `ContextMenu`
- `FormCard`

These should be visual extractions of SSR patterns, not a new design system.

## 6. Styling Strategy

### Source of Truth

Use these files as the styling reference, in order:

1. [base_tailwind.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/base_tailwind.html)
2. [login.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/login.html)
3. [register.html](C:/Users/harikrishnam/Desktop/cms_backend-codex/app/templates/register.html)
4. the screen-specific SSR template for the page being migrated

### Non-Negotiable Styling Rules

- Keep DM Sans as the primary typeface.
- Match the slate/emerald visual system already in the SSR templates.
- Preserve sidebar width, header spacing, card radius, and shadow density before adjusting anything else.
- Match existing button hierarchy:
  - primary emerald action
  - secondary white bordered action
  - destructive red affordance
- Preserve existing icon placement and visual weight where icons are part of comprehension.
- Prefer reproducing SSR spacing and layout structure over reusing current generic frontend spacing.

### Implementation Guidance

- Do not redesign with new gradients, nav shapes, or brand treatment.
- Replace the current generic frontend shell in [index.css](C:/Users/harikrishnam/Desktop/cms_backend-codex/frontend/src/index.css) incrementally.
- Use the SSR templates to define CSS variables or utility class groupings for repeated values.
- Keep state wiring, hooks, and queries intact; parity work should be mostly component composition and styling.

## 7. Validation Checklist Per Screen

Use side-by-side comparison against the live SSR page with the same authenticated user and the same seeded dataset.

| Screen | Visual parity checks | Workflow parity checks |
| --- | --- | --- |
| Login | Logo placement, heading/subheading, card width, form field spacing, error/success alert styling, CTA placement | Invalid credentials render in-page error; success lands on `/ui/dashboard`; already-authenticated user is redirected away |
| Register | Same standalone auth card treatment as SSR, field order, button width, error block, link back to login | Password confirmation errors and duplicate-user errors render in-page; success lands on `/ui/login`; already-authenticated user is redirected away |
| Dashboard | Sidebar, page title/subtitle, metric-card styling, admin shortcuts block, project section spacing | Same stats and project counts as SSR contract; admin shortcuts visible only for admins; SSR project-create fallback still reachable |
| Projects list | Breadcrumb row, new-project action placement, project card grid, delete affordance placement, empty-state card | Search/filter must not change backend data semantics; project cards navigate correctly; delete action still uses current contract behavior |
| Project detail | Explorer command bar, address bar, left tree, chapter tile/list view, create/rename/delete affordances | Chapter create/rename/delete and package download still behave exactly as current frontend/backend contracts; breadcrumbs and navigation match SSR expectations |
| Chapter detail | Command bar, address bar, left category nav, overview folder tiles, category file display, status banners | Upload, checkout, cancel checkout, download, delete, processing start, technical-review entry, and structuring-review entry remain unchanged behaviorally |
| Admin dashboard | Title block, stats cards, back-link placement, management-link cards | Admin-only access unchanged; counts match `/api/v2/admin/dashboard`; navigation to admin users unchanged |
| Admin users | Table columns, badges, action icons, create-user form, edit/password presentation, success/error messaging | Create, role update, status toggle, edit, password change, and delete remain current-contract accurate; no new auth behavior introduced |
| Technical review | Sticky header, filename context, loading/error panels, grouped issue sections, apply button placement | Scan result rendering and apply action behavior unchanged; resulting `_TechEdited` file still appears after invalidation/refetch |
| Structuring review shell | Toolbar layout, filename display, save/export/return action placement, fallback state layout | Save, export, and return behavior remain current-contract accurate; backend-owned editor handoff remains unchanged |

## 8. Execution Constraints and Parity Rules

- Do not change `/api/v2` contracts to make the UI easier to style.
- Do not move business logic into the frontend.
- Do not replace backend-owned WOPI/editor launch with frontend-owned embedding.
- Do not remove SSR fallback pages during parity work.
- Do not redesign route structure just to mirror SSR URLs.

## 9. Practical Definition of Done

The parity migration is complete for a screen when:

- the React screen matches the corresponding SSR template closely enough that users do not perceive a layout shift
- all existing data and actions continue to flow through the current `/api/v2` contracts
- backend-owned auth/session and WOPI/editor ownership remain unchanged
- SSR fallback links still work
- automated tests, typecheck, and build remain green

## 10. Recommended Next Implementation Step

Start with the shared parity foundation plus phase 1 login in the same implementation slice:

1. restyle the shared auth visual primitives from `login.html`
2. apply the same auth-card structure to `register`
3. then restyle the shared app shell from `base_tailwind.html`

This keeps the first visible change small, reversible, and anchored to the simplest SSR source pages.
