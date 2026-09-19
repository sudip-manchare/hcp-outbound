# Implementation Plan - HCP Outbound: CMS Open Payments "Audit & Defense" Guard

Build the next-generation HCP outbound engagement engine that transforms CMS Open Payments anxiety into high-conversion physician relationships, powered by Tiger Data (PostgreSQL + TimescaleDB + pgvector), Live CMS NPPES Registry Enrichment, and an AI Sunshine Dispute Advocate.

---

## 1. Product Vision & Novel Functionality

### The Physician Hook
Under the federal Sunshine Act, pharmaceutical and medical device companies must report all transfers of value to physicians on the public CMS Open Payments database. Rogue sales reps frequently log phantom meals or speaking fees under physician NPIs without their consent. Doctors face a strict 45-day review window each spring to dispute entries before they become public record for patients, journalists, and malpractice lawyers to scrutinize.

### The Innovation Beyond Impiricus
While Impiricus currently facilitates clinical requests (samples, dosing info) to already-engaged physicians, cold outbound to doctors has historically suffered from sub-2% conversion rates.
**Our Invention: The AI Sunshine Dispute Advocate & Reverse Engagement Loop:**
1. **Live CMS NPPES NPI Registry Enrichment**: Open Payments data gives raw NPIs and payment amounts. Our engine queries the official CMS NPPES REST API (`https://npiregistry.cms.hhs.gov/api/`) in real time to resolve the physician's legal name, credential (MD, DO), official clinical taxonomy (primary specialty), and practice location.
2. **High-Urgency Outbound Dispatch**: The outbound engine generates targeted physician alerts regarding unreviewed transactions and specialty-mismatched entries under their NPI, providing a secure, 1-click audit portal link.
3. **Zero-Login Physician Audit Portal**: A dedicated web-based audit dashboard showing total dollars, meal count, reporting manufacturers, and flagged entries surfaced by pgvector & TimescaleDB.
4. **AI Sunshine Dispute Advocate (42 CFR § 403.908)**: With a single click ("Dispute Unreviewed Items"), the physician reviews flagged anomalies and auto-generates a formal federal dispute notice directed to the manufacturer's compliance contact.
5. **The Reverse Engagement Flip**: Impiricus acts as the permanent concierge shield. The pharma manufacturer corrects the entry and opens a compliant, trusted digital channel with a previously unreachable doctor.

---

## 2. Technical Architecture & Tiger Data Showcase

```
                                +-----------------------------------+
                                |   Official CMS NPPES API          |
                                |   (npiregistry.cms.hhs.gov/api)   |
                                +-----------------+-----------------+
                                                  ^
                                                  | Live NPI Enrichment
                                                  v
+-----------------------------------------------------------------------------+
|                      HCP Outbound Web Application (Next.js)                 |
|                                                                             |
|  [Campaign Command Console & HCP Roster]   [Physician Audit & Dispute Portal]
|   - Doctor Directory with Live NPI Search   - Zero-Login Tokenized Audit View|
|   - NPPES Verified Badges & Taxonomy        - Financial & Velocity Breakdown|
|   - Anomaly / Mismatch Risk Indicators      - Out-of-Specialty Anomaly Flags |
|   - Outbound Alert Dispatcher               - 1-Click AI Dispute Notice Gen |
|   - Live Pipeline Analytics & Conversion    - Concierge Shield Confirmation |
+-------------------------------------+---------------------------------------+
                                      | API calls (REST / SSE)
                                      v
+-----------------------------------------------------------------------------+
|                        Python FastAPI Backend                               |
|   - NPPES Service (Live CMS NPI Registry REST queries & taxonomy parsing)   |
|   - CMS Data Seed & Ingestion Engine                                        |
|   - TimescaleDB Time-Series Velocity Analytics (`time_bucket`)              |
|   - pgvector Semantic Mismatch Scorer (`cosine_distance`)                   |
|   - Campaign & Outbound Token Dispatch Service                              |
|   - AI Sunshine Dispute Notice Generator (42 CFR § 403.908)                |
+-------------------------------------+---------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------+
|               Tiger Data Managed PostgreSQL (Postgres 16+)                  |
|                                                                             |
|   [TimescaleDB Extension]                    [pgvector Extension]           |
|   - Hypertables: `cms_payments`              - Doctor specialty embeddings  |
|     (partitioned by `payment_date`)            (derived from NPPES taxonomy)|
|   - Velocity queries: time-bucket rollups    - Manufacturer product         |
|     detecting end-of-quarter meal dumps        embeddings                   |
|                                              - Cosine distance mismatch     |
+-----------------------------------------------------------------------------+
```

### Winning "Best Use of Tiger Data"
- **TimescaleDB**:
  - `cms_payments` is registered as a TimescaleDB hypertable (`create_hypertable('cms_payments', 'payment_date')`).
  - Time-series analytics via `time_bucket('1 month', payment_date)` detect sudden velocity spikes (e.g., sales reps logging multiple consecutive meals in December before reporting deadlines).
- **pgvector**:
  - Physician clinical taxonomies (from NPPES) and pharma product/study descriptions are vectorized.
  - Anomaly scoring via `<=>` (cosine distance): e.g., an Orthopedic Spine system payment logged against an Interventional Cardiologist triggers a high Specialty Mismatch Score (>0.85), proving algorithmic fraud detection.

---

## 3. Proposed Changes & Implementation Steps

### Directory Structure
```
hcp-outbound/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── campaign.py       # Outbound alert dispatch & pipeline management
│   │   │   ├── doctors.py        # HCP directory, live NPI search, audit card
│   │   │   └── dispute.py        # AI Sunshine Dispute Notice generator
│   │   ├── core/
│   │   │   ├── config.py         # Settings & env vars
│   │   │   └── database.py       # Tiger Data asyncpg / SQLAlchemy connection
│   │   ├── models/
│   │   │   └── schema.py         # Physician, Payment (Timescale), Dispute schemas
│   │   ├── services/
│   │   │   ├── nppes_service.py     # Live CMS NPPES Registry API enrichment
│   │   │   ├── timescale_service.py # Time-bucket velocity queries
│   │   │   ├── vector_service.py    # pgvector embeddings & cosine scoring
│   │   │   └── campaign_service.py  # Secure audit token generation & outreach dispatch
│   │   └── main.py               # FastAPI application entrypoint
│   ├── scripts/
│   │   ├── init_tiger_db.py      # Extension activation, hypertable setup, tables
│   │   └── seed_cms_data.py      # Seed real CMS doctors, payments & embeddings
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Campaign Command Center & Integrated Audit Workspace
│   │   │   ├── audit/[token]/    # Physician Audit & Dispute Portal route
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── CampaignConsole.tsx   # Campaign manager, live stats & HCP roster
│   │   │   ├── DoctorTable.tsx       # HCP directory with NPPES badges & anomaly indicators
│   │   │   ├── NpiSearchBar.tsx      # Real-time CMS NPPES NPI lookup
│   │   │   ├── AuditCard.tsx         # Comprehensive Physician Audit dashboard component
│   │   │   ├── DisputeNoticeModal.tsx# Formal 42 CFR § 403.908 federal notice modal
│   │   │   ├── EnrollmentConfirmation.tsx # Concierge protection confirmation
│   │   │   ├── SendAlertModal.tsx    # Outbound alert dispatch modal
│   │   │   └── TigerDataBadge.tsx    # Live indicator of Timescale & pgvector queries
│   │   └── lib/
│   │       ├── api.ts            # Frontend API client
│   │       └── types.ts
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
├── IMPLEMENTATION_PLAN.md
└── README.md
```

---

## 4. Component Details

### Backend (Python FastAPI)

#### [NEW] `backend/requirements.txt`
- `fastapi`, `uvicorn[standard]`, `asyncpg`, `sqlalchemy[asyncio]`, `pgvector`, `pydantic`, `pydantic-settings`, `httpx`, `python-dotenv`, `numpy`.

#### [NEW] `backend/app/services/nppes_service.py`
- **Live NPPES Enrichment**:
  - Calls `https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi}` asynchronously using `httpx`.
  - Extracts:
    - Provider legal name (`basic.first_name`, `basic.last_name`, `basic.credential`).
    - Primary Healthcare Provider Taxonomy code and human-readable description (`taxonomies[primary=True].desc`).
    - Primary practice address (`addresses[address_purpose='LOCATION']` city, state, zip).
  - Automatically caches results in the `physicians` table in Tiger Data PostgreSQL to minimize external network latency on repeat queries.

#### [NEW] `backend/scripts/init_tiger_db.py`
- Connects to Tiger Data PostgreSQL.
- Executes:
  ```sql
  CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
  CREATE EXTENSION IF NOT EXISTS vector CASCADE;
  ```
- Creates `physicians`, `cms_payments`, and `disputes` tables.
- Converts `cms_payments` into a TimescaleDB hypertable partitioned on `payment_date`.
- Creates pgvector ivfflat or HNSW index on `cms_payments.product_embedding`.

#### [NEW] `backend/scripts/seed_cms_data.py`
- Seeds 15+ realistic HCP profiles across Cardiology, Dermatology, Oncology, Orthopedics, and Neurology.
- Enriches or validates NPIs against NPPES taxonomy schemas.
- Seeds 100+ realistic CMS Open Payments transactions including:
  - Legitimate meals & consulting fees.
  - Unreviewed velocity dumps (TimescaleDB highlight: multiple payments in one week).
  - Out-of-specialty mismatch entries (pgvector highlight: Orthopedic hip replacement logged for a Dermatologist).
- Computes or embeds deterministic 384-dimensional vector embeddings so seed operates instantly without external API keys.

#### [NEW] `backend/app/services/timescale_service.py`
- Uses `time_bucket('1 month', payment_date)` to calculate payment frequency and detect sudden surges.

#### [NEW] `backend/app/services/vector_service.py`
- Queries pgvector using cosine distance `<=>` between doctor specialty embedding (derived from NPPES taxonomy) and payment product embedding. Flags mismatch scores > 0.70.

#### [NEW] `backend/app/services/campaign_service.py`
- Handles campaign tracking, secure audit token generation, and outbound dispatch simulation.
- Generates secure signed links (`/audit/{token}`) for targeted physicians and tracks pipeline conversion states: Dispatched -> Opened -> Disputed -> Protected.

---

### Frontend (Next.js + Tailwind CSS)

#### [NEW] `frontend/src/app/page.tsx`
- **Campaign Command Center & Interactive Audit Workspace**:
  - **Campaign Management View**:
    - Live NPI Search Box: Type any 10-digit NPI to fetch live NPPES credentials in real time.
    - Live Tiger Data metrics badge (TimescaleDB hypertable query latency, pgvector cosine distance calculations).
    - HCP directory table with NPI, NPPES verified taxonomy, total reported $, meal count, and mismatch badge.
    - Outbound alert dispatcher: Select doctor, preview notification summary, and trigger outbound alert link.
    - Live pipeline funnel: Dispatched -> Opened -> Disputed -> Protected.
    - Direct "Inspect Audit & Defense" action to immediately view the physician portal experience.

#### [NEW] `frontend/src/app/audit/[token]/page.tsx`
- Dedicated **Physician Audit & Dispute Portal**:
  - Clean, zero-friction web portal view displaying the doctor's verified NPPES credentials.
  - Complete financial breakdown: Total reported dollars, meal count, top reporting manufacturers, and unreviewed status alert.
  - Visual flags for TimescaleDB velocity spikes and pgvector specialty mismatches.
  - "Dispute Unreviewed Items" direct 1-click action.
  - Generates the **Formal 42 CFR § 403.908 Dispute Notice** addressed to the manufacturer compliance officer.
  - Impiricus permanent alert system enrollment confirmation.

---

## 5. Verification Plan

### Automated Database & API Verification
1. Run `python backend/scripts/init_tiger_db.py` to verify TimescaleDB and pgvector extensions initialize on Tiger Data.
2. Run `python backend/scripts/seed_cms_data.py` to populate seed data and verify hypertables and vector indexes.
3. Test Live NPPES Enrichment:
   - Run a test call to `GET /api/doctors/enrich/{npi}` with a real physician NPI (e.g. `1235149876`) to verify real-time response from `npiregistry.cms.hhs.gov`.
4. Execute backend tests for:
   - `GET /api/doctors` -> returns roster with pgvector anomaly flags and NPPES taxonomy.
   - `GET /api/doctors/{npi}/audit` -> returns audit metrics and TimescaleDB monthly velocity.
   - `POST /api/campaign/dispatch` -> dispatches outreach alert with signed audit token.
   - `POST /api/dispute/generate` -> generates 42 CFR § 403.908 notice.

### Manual Verification
1. Launch backend (`uvicorn app.main:app`) and frontend (`npm run dev`).
2. Open `http://localhost:3000` in a desktop browser.
3. Test the NPI live lookup box: Enter an NPI and observe instant NPPES legal name, credential, and primary taxonomy resolution.
4. Select an anomalous doctor (e.g., Dr. Jane Miller, Dermatologist with an Orthopedic Spine device charge).
5. Click "Dispatch Sunshine Alert" -> verify alert is dispatched and pipeline counter updates.
6. Open the Physician Audit view (or navigate to `/audit/{token}`) -> verify Audit Card renders with total $, meals, velocity spikes, and specialty mismatch warnings.
7. Click "Dispute Unreviewed Items" -> verify generated formal 42 CFR § 403.908 dispute notice displays with all statutory details.
8. Confirm enrollment in Impiricus Concierge Shield and verify pipeline conversion reaches "Protected".
