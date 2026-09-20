# Backend implementation audit

Audited against `IMPLEMENTATION_PLAN.md` on 2026-09-19.

| Planned backend capability | Status before this change | Status now | Evidence |
| --- | --- | --- | --- |
| FastAPI application and route modules | Missing | Partially implemented | `app/main.py` exposes the live data routes; campaign and dispute routes remain unimplemented. |
| NPPES live enrichment | Missing | Implemented | `app/services/nppes_service.py` calls the official NPPES v2.1 API and normalizes legal name, taxonomy, and location. |
| CMS Open Payments ingestion | Seed-only | Implemented for live reads | `app/services/cms_open_payments_service.py` reads generic, paginated CMS datastore pages; each record includes its recipient NPI. |
| NPPES cache in Tiger Data | Missing | Not yet implemented | The live routes intentionally return the fresh source response; write-through cache is a separate database integration task. |
| Tiger Data tables and hypertable | Present but unverified | Migrated and live-ingested | CMS payment records are retained with source identities and ingestion-run provenance; the application does not seed synthetic payment or physician rows. |
| Local CMS record CRUD | Missing | Implemented and verified | The ingestion job creates records idempotently; `GET`, `PATCH`, and `DELETE` routes operate on local copies only. Replaying a 100-record page skipped all 100 duplicates; deleting one copy then replaying restored only that one record. |
| Frontend pull-and-ingest action | Missing | Implemented and verified | `POST /api/ingestions/cms` pulls a bounded CMS page and persists new rows in one request. A one-row request inserted 1 row; replaying it inserted 0 and skipped 1. |
| Synthetic CMS seed | Removed | Not applicable | The application ingests only CMS API records. |
| Timescale velocity service | Missing | Missing | No `timescale_service.py` exists. |
| pgvector mismatch service | Missing | Missing | No `vector_service.py` exists. |
| Campaign dispatch persistence/endpoints | Partial helpers only | Still partial | `campaign_service.py` has token SQL/helpers but no route or persistence call site. |
| Dispute generator/endpoints | Missing | Missing | No dispute service or API route exists. |

## Live source contract

`GET /api/payments` requests a generic page from the CMS feed and returns the NPI present on each payment record. `GET /api/doctors/enrich/{npi}` enriches a selected provider from NPPES. Neither route falls back to the synthetic seed dataset.

- NPPES: `https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi}`
- CMS Open Payments: `https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset-id}/0`, paginated with optional state, manufacturer, payment-nature, and recipient-type filters

The default dataset is CMS Open Payments General Payment program year 2025 (`fb0b1734-1410-429d-92f6-3f4b35218e5e`). CMS publishes a new dataset identifier each year, so it is environment-configured rather than hard-coded in a route.

## Verification completed

- Unit tests: `python3 -m pytest tests -q` (3 passed).
- Live NPPES client: NPI `1659344299` returned primary taxonomy `1223G0001X`.
- Live CMS Open Payments client: the same NPI returned 3 matching records; a limited request returned the expected first two records.

See `samples/nppes_normalized_provider.schema.json` for the response contract and `samples/nppes_normalized_provider.sample.json` for a concrete public-record example.
