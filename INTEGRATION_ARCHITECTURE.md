# Frontend–Backend Integration Architecture

## Decision summary

Build the product around a versioned REST contract (`/api/v1`) and treat the backend as the sole source of truth. The UI renders loading, error, and empty states from that contract; it never replaces a failed API call with mock records.

The current frontend is a polished prototype and already identifies the main user journeys. The backend has the database initializer and token helpers, but does not yet include the FastAPI entrypoint, API routers, ORM models, migrations, data services, or backend tests. This document defines the seam between them before those pieces are implemented.

## System architecture

```text
Next.js application
  app/                         route shells and metadata
  features/campaign/           roster, filters, dispatch workflow
  features/audit/              tokenized audit and dispute workflow
  lib/api/                     generated contract types + HTTP client
             │ HTTPS JSON / Server-Sent Events
             ▼
FastAPI application
  api/                         thin versioned route handlers
  schemas/                     Pydantic request/response contracts
  services/                    campaign, audit, NPPES, analytics, disputes
  repositories/                SQLAlchemy persistence boundary
  workers/                     ingestion/enrichment (not request handlers)
             │
             ▼
Tiger PostgreSQL
  PostgreSQL                   system-of-record tables and transactions
  TimescaleDB                  payment hypertable and monthly rollups
  pgvector                     specialty/payment similarity calculations
```

The admin/campaign console and the tokenized clinician audit portal have different authorization boundaries. Administrative routes require a staff session; the audit portal is limited to the capabilities of an unguessable, expiring, revocable audit-link token. A link is not proof of clinician identity, so a production submission or enrollment needs explicit identity and consent handling. The dispute endpoint creates a reviewable draft only; it does not send a legal notice automatically.

## Frontend architecture and schema

Keep `app/` focused on routing. Each feature owns its presentation components, view model, and tests. `lib/api` owns transport concerns only: base URL, authentication headers, response parsing, and normalized errors.

```text
src/
  app/
    page.tsx                   Campaign console route
    audit/[token]/page.tsx     Secure audit route shell (no mock lookup)
  features/
    campaign/{components,hooks,queries,tests}/
    audit/{components,hooks,queries,tests}/
  lib/
    api/client.ts              Typed fetch wrapper
    api/generated.ts           Generated from FastAPI OpenAPI
    api/errors.ts              Problem Details -> UI error model
    config.ts                  API URL
```

The existing `Physician`, `CmsPayment`, `AuditCardData`, and `DisputeNotice` types are a useful prototype vocabulary. Replace their handwritten copies with types generated from the backend OpenAPI document and validate untrusted responses at runtime. The browser-only state is deliberately small:

| State | Owner | Persistent source |
| --- | --- | --- |
| selected NPI and active table filters | campaign feature | URL/query state when shareable |
| roster, audit data, campaign metrics | query cache | API |
| modal open/closed and current form input | component | browser only |
| audit/dispute/protection status | audit feature | API, refreshed after mutations |
| link token | audit route parameter | URL; never local storage |

Recommended UI state model: `idle -> loading -> ready | error` for every query, and `idle -> submitting -> success | error` for every mutation. Do not optimistically increment funnel totals: use the mutation response or invalidate the metrics query. A failed request is visible to the user and test suite.

## Backend architecture and database schema

Use Alembic migrations instead of provisioning application tables directly from the initialization script. The script can remain responsible for extensions in local infrastructure; migrations own schema evolution.

### Core relational model

| Table | Key fields | Purpose and invariants |
| --- | --- | --- |
| `physicians` | `npi PK`, names, credential, taxonomy, practice address, `specialty_embedding`, NPPES timestamps | NPI is exactly 10 digits and is normalized before persistence. NPPES is a cached enrichment, not an authority for application state. |
| `cms_payments` (hypertable on `payment_date`) | `(id, payment_date) PK`, `physician_npi FK`, CMS source ID, manufacturer, amount, review status, product embedding, mismatch score | Money is `NUMERIC(12,2)`, never float. Idempotent ingestion uses a source-record fingerprint. Timescale unique indexes must include `payment_date`. |
| `audit_links` | `id UUID PK`, `token_hash UNIQUE`, `physician_npi FK`, `expires_at`, `revoked_at`, `created_by`, `created_at` | Store only SHA-256/HMAC hashes of random URL-safe tokens. A token is never logged in plaintext. |
| `audit_events` | `id UUID PK`, `audit_link_id FK`, `event_type`, `occurred_at`, `metadata JSONB` | Append-only lifecycle evidence: `dispatched`, `opened`, `dispute_drafted`, `protected`. Metrics derive from this history. |
| `disputes` | `id UUID PK`, `audit_link_id FK`, `physician_npi FK`, manufacturer, draft body, `status`, timestamps | A draft is distinct from a submitted dispute. Status transitions are validated. |
| `dispute_items` | `(dispute_id, payment_id, payment_date) PK` | Normalized selection of disputed payments; composite payment reference preserves Timescale integrity. |
| `campaigns` (optional for hackathon) | `id UUID PK`, name, audience criteria, created metadata | Add only if multiple named outreach campaigns are in scope. A link can reference a campaign. |

`audit_links` replaces the current raw `audit_tokens` model. It fixes two issues in the prototype: a generated token is 73 characters (`8 + 1 + 64`) but the current column is `VARCHAR(64)`, and raw bearer tokens should not be stored in the database. The HMAC prefix is not useful without a database lookup; hashing the full random token is simpler and safer.

### Service boundaries

- `NppesService` calls CMS with a timeout, maps a result to the normalized physician schema, and caches a successful response. Requests never fail a roster query just because live enrichment is unavailable.
- `PaymentAnalyticsService` calculates aggregates, Timescale monthly buckets, and deterministic risk signals. A risk signal is an evidence flag, not a finding of fraud.
- `AuditLinkService` creates, hashes, resolves, expires, revokes, and records lifecycle events atomically.
- `DisputeService` verifies that each requested payment belongs to the token's physician and is eligible, then produces a draft notice.
- `CampaignMetricsService` reads append-only event data. SSE broadcasts a small, non-sensitive event only after the transaction commits.

## Public API contract

Publish OpenAPI at `/openapi.json`, keep an `openapi.json` snapshot in version control, and generate the frontend types from it in CI. All endpoints return `application/problem+json` for errors (`code`, `title`, `status`, `detail`, `request_id`). Monetary values are strings in JSON (`"3840.00"`) to avoid binary floating-point drift; the UI converts them only for display.

| Method and path | Request | Response / behavior |
| --- | --- | --- |
| `GET /api/v1/health` | — | service and dependency health |
| `GET /api/v1/physicians?query=&risk=&cursor=` | admin auth | paginated roster, aggregate risk fields, and cursor |
| `GET /api/v1/physicians/{npi}` | admin auth | one physician summary |
| `POST /api/v1/physicians/{npi}/enrich` | admin auth | cached-or-live NPPES enrichment result |
| `GET /api/v1/physicians/{npi}/audit-summary` | admin auth | payment aggregates, monthly buckets, manufacturer totals, signals |
| `POST /api/v1/audit-links` | `{ npi, campaign_id? }` plus `Idempotency-Key` | `201` link ID, plaintext URL/token once, expiry, and dispatch event |
| `GET /api/v1/audits/{token}` | bearer token in path | token-scoped audit view; records a single `opened` event |
| `POST /api/v1/audits/{token}/disputes` | `{ payment_refs, physician_attestation }` | `201` draft notice and `dispute_drafted` event |
| `POST /api/v1/audits/{token}/protection-enrollments` | `{ consent_version, accepted_at }` | `201` enrollment result and `protected` event |
| `GET /api/v1/campaign-metrics` | admin auth | counts based on event history |
| `GET /api/v1/campaign-events` | admin auth | SSE notifications; refetch the affected query on receipt |

For the first integration pass, keep the existing UI labels but map them to the above resources: “Create review link” creates an audit link; “Open review” uses the returned URL; “Dispute” creates a draft; “Start ongoing monitoring” records explicit consent. The standalone `/audit/[token]` page fetches the token-scoped audit endpoint.

## TDD-first implementation sequence

1. **Freeze the contract.** Add Pydantic schemas, route stubs, OpenAPI snapshot generation, and frontend generated types. Write contract tests first for success, validation, `401/403`, `404`, `409` idempotency conflicts, and expired-token `410` responses.
2. **Create repeatable test infrastructure.** Add backend `pytest`, `pytest-asyncio`, `httpx`, and a dedicated `TEST_DATABASE_URL`. Apply migrations to an isolated Tiger/Postgres test database, use test-only fixtures, and truncate/roll back between tests. CI must verify that both `timescaledb` and `vector` extensions exist and that `cms_payments` is a hypertable.
3. **Implement the roster vertical slice.** Start with failing API and UI tests for a paginated roster and error state. Implement repository, analytics summary, `GET /physicians`, frontend query hook, then remove fallback mocks from normal mode.
4. **Implement audit links and audit read.** Write integration tests for a valid link, a tampered/missing/expired/revoked link, and exactly-once `opened` event recording. Then wire the modal and `/audit/[token]` route to the real resource.
5. **Implement dispute drafts.** Test invalid ownership, reviewed payments, duplicate selections, amount totals, draft persistence, and immutable payment references. Wire the notice modal only after the endpoint passes.
6. **Implement enrollment and metrics.** Test required consent version and valid lifecycle transitions. Calculate metrics from events, add the SSE event after commit, and make the frontend refetch rather than mutate counts locally.
7. **Add live NPPES enrichment and production concerns.** Test the service with recorded HTTP fixtures (not CMS in every CI run), cache behavior, timeout fallback, audit logging/redaction, rate limiting, CORS allowlists, and configuration validation.
8. **Prove the full system.** Run browser tests against the real frontend, FastAPI server, migrations, and API-sourced test records—no mocked network in this suite. Keep unit tests isolated, but add a separate real-stack suite as the release gate.

## Test matrix

| Layer | Tooling | Required examples |
| --- | --- | --- |
| Pure unit | Vitest; pytest | NPI normalization/checksum, money formatting, token hashing, state-transition rules, risk classification |
| Component | Testing Library + MSW | loading/error/empty UI, modal submits correct payload, error message is visible, no mock fallback in production mode |
| API contract | pytest + `httpx.AsyncClient` | schema matches OpenAPI, pagination, problem responses, auth scopes, idempotency |
| DB/service integration | pytest against test database | migrations, extensions, hypertable, time buckets, vector similarity, token lookup, transactional events |
| External adapter | pytest + `respx`/recorded fixtures | NPPES mapping, cache hit, timeout and malformed response |
| Browser end-to-end | Playwright real stack | admin queue -> link -> portal -> draft -> consent -> metrics, plus expired/tampered link and backend outage paths |

Tests describe user-visible behavior first. For example, before implementing dispatch, write: “posting the same idempotency key creates one audit link and one dispatched event”; before implementing the portal, write: “an expired link shows an expiry message and exposes no physician data.” This prevents the integration from becoming a collection of frontend-specific shortcuts.

## Definition of done for each slice

- Request and response schema is documented in OpenAPI and generated frontend types are current.
- Backend unit, API integration, and affected frontend component tests pass.
- At least one Playwright scenario exercises the real endpoint for the slice.
- Migrations are reversible/tested and test data is deterministic.
- Loading, empty, error, retry, and authorization states are designed—not replaced with fixture data.
- Logs, analytics events, and error payloads do not expose bearer tokens or unnecessary clinician data.
