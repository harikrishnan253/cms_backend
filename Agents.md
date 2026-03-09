## Frontend Modernization Principle
The project does not require a mandatory React rewrite. Choose the frontend approach based on the complexity of each module and the need for interactivity, while preserving all existing functionality.

Preferred decision order:
1. Keep stable server-rendered pages where they are sufficient.
2. Use lightweight progressive enhancement for moderately interactive workflows.
3. Use a typed frontend module only for highly interactive areas where it provides clear maintainability benefits.

Accepted frontend patterns:
- Server-rendered HTML templates for simple/stable admin flows
- HTMX or Alpine.js for progressive enhancement
- React + TypeScript or Vue + TypeScript for highly interactive modules

Do not introduce a frontend framework unless it provides a clear architectural advantage for that module.

## Mandatory Stability Rules
- Preserve all existing user-visible functionality
- Do not break legacy routes before parity is verified
- Separate business logic from route rendering
- Expose stable JSON APIs for any new frontend module
- Use typed contracts between backend and frontend
- Keep auth, file handling, and background-job flows backward compatible during migration

## Migration Rule

Migrate module-by-module, not by full rewrite. Use the lowest-risk frontend approach that achieves maintainability, testability, and future extensibility.