# Backend live-source integration

## Production container

From the repository root:

```bash
docker build -t falsepay-backend ./backend
docker run --rm --env-file backend/.env --env APP_ENV=production \
  --publish 127.0.0.1:8000:8000 falsepay-backend
```

Copy `.env.example` to `.env` if needed, and fill in the connection settings.
The image runs Uvicorn as a non-root user on `0.0.0.0`, defaults to port 8000,
and accepts a runtime `PORT` override. Configure `/health` as the hosting
provider's health-check path. This checks the API process, not database or
upstream availability. Environment files are excluded from the image.

For hosted deployment, set these runtime environment variables:

- `MONGODB_URI`: MongoDB Atlas connection string (`mongodb+srv://...`).
- `MONGODB_DB_NAME`: database name (default `hcp_outbound`).
- `CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID`: required; see `.env.example`.
- `APP_ENV=production` and a production `SECRET_KEY`.
- `CORS_ORIGINS=["https://your-frontend.example.com"]`: JSON array of allowed
  frontend origins, without paths or trailing slashes. Restart after changing it.
- `GEMINI_API_KEY`: optional, enables AI explanations; keep it on the backend.

Use a MongoDB Atlas cluster (Atlas Vector Search is required for specialty
mismatch scoring). In Atlas, create a database user and allow your host's IP
under Network Access, then put the connection string in `backend/.env`.
For a new database, run the initializer once before using ingestion:

```bash
docker run --rm --env-file backend/.env falsepay-backend \
  python -m scripts.init_mongo_db
```

It creates the `physicians`, `cms_payments`, `disputes`, `audit_tokens`,
`cms_ingestion_runs`, and `risk_assessments` collections; the unique
`(raw_cms_record_id, payment_date)` index; a TTL index that deletes
`audit_tokens` once `expires_at` passes; and the Atlas Vector Search index
`cms_payments_product_embedding` (384 dimensions, cosine similarity). The
command waits until the vector index is queryable.

Database initialization is an explicit administrative step, not a container
startup action. Do not use `localhost` as the database host inside a container
unless the database actually shares its network namespace.

## Data sources

- NPPES NPI Registry (live API call per request): `GET /api/doctors/enrich/{npi}`
- CMS Open Payments General Payments (served from MongoDB): `GET /api/payments?limit=100&offset=0`

Start it from `backend/` with `uvicorn app.main:app --reload`. Request handlers never call the CMS API; `GET /api/payments` pages through the `cms_payments` collection with the same response shape and filters (`recipient_state`, `manufacturer_id`, `payment_nature`, `recipient_type`). CMS data reaches MongoDB only through the ingestion script or `POST /api/ingestions/cms`. Each payment includes its recipient NPI; call NPPES only for the provider you want to inspect. Neither endpoint returns seed data.

CMS publishes a new Open Payments dataset identifier each reporting year. Update `CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID` and `CMS_OPEN_PAYMENTS_PROGRAM_YEAR` together after checking the official `https://openpaymentsdata.cms.gov/data.json` catalog. The current defaults target program year 2025.

## Database ingestion

The generic CMS API response is retained in MongoDB with its complete raw record and a normalized set of queryable fields. The default run is a one-time load of 10 pages × 100 = 1,000 live records; it does not attempt the 16-million-row annual dataset in one unbounded job, and it does not pre-fetch NPPES.

```bash
python -m scripts.ingest_cms_open_payments --reset
```

Records are written with motor bulk upserts (`$setOnInsert`) keyed on `(raw_cms_record_id, payment_date)`, so re-running never overwrites an existing local copy. Each payment stores a 384-dimension `product_embedding`. After loading, the script computes specialty-mismatch scores with Atlas `$vectorSearch` (the share of similar-product payments received by other specialties) and then retrains the Isolation Forest.

`cms_ingestion_runs` records the source dataset, filters, offset, and result count for each run. To continue, use a later `--start-offset`; to ingest a narrower cohort, use `--recipient-state OH`. A payment record keeps its `recipient_npi`, and NPPES enrichment remains an explicit later step for the providers selected from that feed.

### Frontend pull-and-ingest action

The frontend should call one backend endpoint rather than call CMS directly from the browser:

```http
POST /api/ingestions/cms
Content-Type: application/json

{ "limit": 100, "offset": 0 }
```

That one call first reads the page from the official CMS API, then creates only the new documents in MongoDB in the same backend request. Its response includes `records_seen`, `records_inserted`, `records_skipped`, and `next_offset`, so the button can report exactly what happened. `GET /api/payments` reads the retained data from MongoDB.

## Local CMS record CRUD

CMS ingestion is the create operation and uses the unique CMS source identity `(raw_cms_record_id, payment_date)`. If a batch contains an already-stored source record, it is skipped and the original local record is not overwritten.

Each ingestion run reports `records_seen`, `records_inserted`, and `records_skipped`, so a repeat page can be audited without guessing whether it changed the database.

- `GET /api/stored-payments` — page through retained records.
- `GET /api/stored-payments/{record_id}?payment_date=2025-07-24` — read one local record.
- `PATCH /api/stored-payments/{record_id}?payment_date=2025-07-24` — update only local `is_reviewed` and/or `mismatch_score` metadata.
- `DELETE /api/stored-payments/{record_id}?payment_date=2025-07-24` — delete the local copy. A later ingest can restore it from CMS.

To explicitly clear an existing local mismatch score, pass `"mismatch_score": null` in the PATCH body.

`samples/nppes_normalized_provider.schema.json` is the final NPPES response contract, and `samples/nppes_normalized_provider.sample.json` is a public NPI-1 example obtained from the official NPPES API, not a fabricated fixture.

## Explainable risk triage

After ingesting a payment, request a review-priority assessment with:

```http
POST /api/stored-payments/{record_id}/risk-triage?payment_date=2025-07-24
```

The response contains a `risk_score`, `risk_level`, model-input observations,
and a `plain_language_explanation` for the frontend. A vanilla scikit-learn
`IsolationForest` is retrained automatically after each CMS ingestion against
the retained dataset. It uses payment amount, payment count, 30-day recipient
activity and dollars, 90-day manufacturer concentration, and the available
specialty-mismatch score. It uses a fixed 5% contamination rate to create a
bounded review queue for each batch. An observation describes a value fed to the model;
it does not claim to be the cause of a prediction. The system only prioritizes
human review and never determines fraud or wrongdoing.

Every model result is retained in `risk_assessments`, with its observations embedded
as `risk_signals`; the current score is also copied onto each `cms_payments` document
(`current_risk_score`) so the review queue needs no join. A new
ingestion marks the prior batch stale, preserves it as audit history, retrains
the model, and persists a new current result for every retained payment. `GET`
on the same risk-triage URL reads that current stored result without re-scoring.

CLI ingestion also scores the complete retained dataset before reporting success.
To backfill older ingestions or refresh the model without fetching CMS data, run
`python -m scripts.score_cms_payments` from `backend/`. It embeds any payments
missing a vector, refreshes Atlas Vector Search mismatch scores, and replaces
current assessments while preserving their history. Reload the frontend afterward to
fetch the updated review queue.

## Gemini explanations

Set `GEMINI_API_KEY` in `backend/.env` and restart the backend. The key stays on
the server. `GEMINI_MODEL` defaults to `gemini-2.5-flash`; the request timeout is
controlled by `GEMINI_TIMEOUT_SECONDS` (30 seconds by default).

The frontend's **Explain this record** action uses the existing POST risk-triage
endpoint. It loads the selected retained payment and current Isolation Forest
assessment (building the batch only if needed), then calls Gemini's
[generateContent API](https://ai.google.dev/api/generate-content) with a structured
JSON response schema. The response adds `ai_explanation` alongside the unchanged
model score, decision and evidence. Gemini receives payment details, CMS-reported
specialty, model metadata and observations; it does not receive the full roster,
registry contact details or raw CMS payload.

The UI separates the model result from Gemini's qualitative context, possible
benign explanations, suggested checks and limitations. Interpretation is generated
on demand, is not persisted, and does not alter review status or risk scores.
There is no web research or live NPPES lookup in this explanation request.
Missing credentials, timeouts, provider failures and invalid/blocked responses
return an explicit AI availability status while retaining the deterministic
assessment. GET risk-triage remains a read of the stored model result only.
