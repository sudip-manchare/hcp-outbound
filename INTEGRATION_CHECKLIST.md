# Full-stack API integration checklist

The backend currently publishes these routes. This checklist is the execution
order and the release gate for the frontend integration.

- [x] 1. Inventory the API surface and identify legacy frontend calls that do
  not have a backend route.
- [x] 2. Add a typed frontend client operation for `GET /health` and surface
  typed, actionable HTTP failures instead of silently treating them as data.
- [x] 3. Connect the live NPPES lookup (`GET /api/doctors/enrich/{npi}`),
  including normalization of its source contract to the UI's provider shape.
- [x] 4. Connect CMS page preview (`GET /api/payments`) and the bounded CMS
  ingestion action (`POST /api/ingestions/cms`).
- [x] 5. Connect the local-payment collection and detail reads
  (`GET /api/stored-payments` and `GET /api/stored-payments/{record_id}`).
- [x] 6. Connect local review updates and removal (`PATCH` and `DELETE
  /api/stored-payments/{record_id}`) as explicit administrative client actions.
- [x] 7. Connect both risk-triage operations (`POST` to create and `GET` to
  read the current assessment) to the review experience.
- [x] 8. Keep the review queue (`GET /api/doctors`) as the primary campaign
  console data source and remove non-demo silent fallbacks.
- [x] 9. Restrict legacy frontend requests to explicit demo mode; in normal mode
  their existing UI error states are shown until server counterparts for
  `/api/campaign/*`, `/api/audit/*`, and `/api/dispute/*` are implemented.
- [x] 10. Add frontend transport integration tests covering every route,
  payload, query string, response mapping, and non-2xx error.
- [x] 11. Add FastAPI route-contract tests covering every route, validation,
  error translation, and database dependency boundary with mocked external
  services/repositories.
- [x] 12. Run backend and frontend suites, type checking, linting, and the
  browser flow in explicit demo mode; record any environment-only blockers.
