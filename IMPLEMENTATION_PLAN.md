# Implementation Plan - HCP Outbound: CMS Open Payments "Audit & Defense" Guard

Build the next-generation HCP outbound engagement engine that transforms CMS Open Payments anxiety into high-conversion physician relationships, powered by Tiger Data (PostgreSQL + TimescaleDB + pgvector) and an AI Sunshine Dispute Advocate.

---

## 1. Product Vision & Novel Functionality

### The Physician Hook
Under the federal Sunshine Act, pharmaceutical and medical device companies must report all transfers of value to physicians on the public CMS Open Payments database. Rogue sales reps frequently log phantom meals or speaking fees under physician NPIs without their consent. Doctors face a strict 45-day review window each spring to dispute entries before they become public record for patients, journalists, and malpractice lawyers to scrutinize.

### The Innovation Beyond Impiricus
While Impiricus currently facilitates clinical requests (samples, dosing info) to already-engaged physicians, cold outbound to doctors has historically suffered from sub-2% conversion rates.
**Our Invention: The AI Sunshine Dispute Advocate & Reverse Engagement Loop:**
1. **High-Urgency Outbound**: An automated SMS alerts the doctor of unreviewed transactions and specialty-mismatched entries under their NPI with a 1-click secure link.
2. **Zero-Login Mobile Audit Card**: A mobile web card showing total dollars, meal count, reporting manufacturers, and unreviewed entries flagged by pgvector & TimescaleDB.
3. **AI Sunshine Dispute Advocate (42 CFR § 403.908)**: Tapping "Dispute Unreviewed Items" triggers a 4-digit SMS OTP. Upon verification, the engine auto-generates a formal federal dispute notice directed to the manufacturer's compliance contact.
4. **The Reverse Engagement Flip**: Impiricus acts as the permanent concierge shield. The pharma manufacturer corrects the entry and opens a compliant, trusted digital channel with a previously unreachable doctor.

---

## 2. Technical Architecture & Tiger Data Showcase

```
+-----------------------------------------------------------------------------+
|                      Presenter Split-Screen Web App (Next.js)               |
|                                                                             |
|  [Left: Campaign Console & HCP Roster]      [Right: Live Mobile Phone View] |
|   - Doctor Directory with NPI search         - Simulated / Real SMS Alert   |
|   - Anomaly / Mismatch Risk Indicators       - Zero-Login Audit Card        |
|   - "Send Alert SMS" Demo Trigger            - 1-Tap Dispute & OTP Auth     |
|   - Live Pipeline Analytics                  - AI 42 CFR § 403.908 Notice   |
+------------------------------------+----------------------------------------+
                                     | API calls (REST / SSE)
                                     v
+-----------------------------------------------------------------------------+
|                        Python FastAPI Backend                               |
|   - CMS Data Seed & Ingestion Engine                                        |
|   - TimescaleDB Time-Series Velocity Analytics (`time_bucket`)              |
|   - pgvector Semantic Mismatch Scorer (`cosine_distance`)                   |
|   - Twilio Outbound SMS & OTP Verification Service                          |
|   - AI Sunshine Dispute Notice Generator (42 CFR § 403.908)                |
+------------------------------------+----------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|               Tiger Data Managed PostgreSQL (Postgres 16+)                  |
|                                                                             |
|   [TimescaleDB Extension]                    [pgvector Extension]           |
|   - Hypertables: `cms_payments`              - Doctor specialty embeddings  |
|     (partitioned by `payment_date`)          - Manufacturer product         |
|   - Velocity queries: time-bucket rollups      embeddings                   |
|     detecting end-of-quarter meal dumps      - Cosine distance mismatch     |
+-----------------------------------------------------------------------------+
```

### Winning "Best Use of Tiger Data"
- **TimescaleDB**:
  - `cms_payments` is registered as a TimescaleDB hypertable (`create_hypertable('cms_payments', 'payment_date')`).
  - Time-series analytics via `time_bucket('1 month', payment_date)` detect sudden velocity spikes (e.g., sales reps logging 4 consecutive meals in December before reporting deadlines).
- **pgvector**:
  - Physician specialties and pharma product/study descriptions are vectorized.
  - Anomaly scoring via `<=>` (cosine distance): e.g., an Orthopedic Spine system payment logged against an Interventional Cardiologist triggers a high Specialty Mismatch Score (>0.85), proving algorithmic fraud detection.

---

## 3. Proposed Changes & Implementation Steps

### Directory Structure
```
hcp-outbound/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── campaign.py       # SMS trigger & batch management
│   │   │   ├── doctors.py        # HCP directory, audit card, anomaly queries
│   │   │   ├── auth.py           # OTP send & verify
│   │   │   └── dispute.py        # AI Sunshine Dispute Notice generator
│   │   ├── core/
│   │   │   ├── config.py         # Settings & env vars
│   │   │   └── database.py       # Tiger Data asyncpg / SQLAlchemy connection
│   │   ├── models/
│   │   │   └── schema.py         # Physician, Payment (Timescale), Dispute schemas
│   │   ├── services/
│   │   │   ├── timescale_service.py # Time-bucket velocity queries
│   │   │   ├── vector_service.py    # pgvector embeddings & cosine scoring
│   │   │   └── twilio_service.py    # Twilio SMS & OTP handling (with demo simulator)
│   │   └── main.py               # FastAPI application entrypoint
│   ├── scripts/
│   │   ├── init_tiger_db.py      # Extension activation, hypertable setup, tables
│   │   └── seed_cms_data.py      # Seed real CMS doctors, payments & embeddings
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Split-screen presentation view
│   │   │   ├── audit/[token]/    # Standalone mobile route for actual phone clicks
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── CampaignConsole.tsx   # Left-side campaign manager & HCP roster
│   │   │   ├── PhoneEmulator.tsx     # Right-side interactive iPhone frame
│   │   │   ├── AuditCard.tsx         # Mobile Audit Card component
│   │   │   ├── OtpModal.tsx          # Mobile OTP verification modal
│   │   │   ├── DisputeNoticeModal.tsx# Formal 42 CFR § 403.908 notice preview
│   │   │   └── TigerDataBadge.tsx    # Live indicator of Timescale & pgvector queries
│   │   └── lib/
│   │       ├── api.ts            # Frontend API client
│   │       └── types.ts
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
└── README.md
```

---

## 4. Component Details

### Backend (Python FastAPI)

#### [NEW] `backend/requirements.txt`
- `fastapi`, `uvicorn[standard]`, `asyncpg`, `sqlalchemy[asyncio]`, `pgvector`, `pydantic`, `pydantic-settings`, `twilio`, `python-dotenv`, `numpy`.

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
- Seeds 100+ realistic CMS Open Payments transactions including:
  - Legitimate meals & consulting fees.
  - Unreviewed velocity dumps (TimescaleDB highlight: multiple payments in one week).
  - Out-of-specialty mismatch entries (pgvector highlight: Orthopedic hip replacement logged for a Dermatologist).
- Computes or embeds deterministic 384-dimensional vector embeddings so seed operates instantly without external API keys.

#### [NEW] `backend/app/services/timescale_service.py`
- Uses `time_bucket('1 month', payment_date)` to calculate payment frequency and detect sudden surges.

#### [NEW] `backend/app/services/vector_service.py`
- Queries pgvector using cosine distance `<=>` between doctor specialty embedding and payment product embedding. Flags mismatch scores > 0.70.

#### [NEW] `backend/app/services/twilio_service.py`
- Handles SMS dispatch and OTP generation/verification.
- Dual-mode: if `TWILIO_ACCOUNT_SID` is set, dispatches real SMS to judge/presenter phone; also broadcasts events to local frontend emulator.

---

### Frontend (Next.js + Tailwind CSS)

#### [NEW] `frontend/src/app/page.tsx`
- Split-screen presentation view:
  - **Left 60%**: Impiricus Outbound Campaign Command Center.
    - Live Tiger Data metrics badge (TimescaleDB hypertable query latency, pgvector cosine distance calculations).
    - HCP directory table with NPI, specialty, total reported $, meal count, and mismatch badge.
    - Outbound trigger modal: Select doctor, enter mobile number, click "Launch Sunshine Alert SMS".
    - Live pipeline funnel: Dispatched -> Opened -> Disputed -> Claimed.
  - **Right 40%**: Realistic Mobile Phone Frame (iPhone view).
    - Renders an interactive mobile screen.
    - Incoming iOS lock-screen push notification / SMS bubble.
    - Tapping SMS opens the zero-login **Audit Card** view.
    - Shows financial summary, meal count, top manufacturers, unreviewed status alert.
    - "Dispute Unreviewed Items" CTA button.
    - 4-digit OTP entry screen with instant validation.
    - Reveals the **Formal 42 CFR § 403.908 Dispute Notice** addressed to the manufacturer compliance officer.
    - Impiricus permanent alert system enrollment confirmation.

#### [NEW] `frontend/src/app/audit/[token]/page.tsx`
- Standalone mobile-optimized route so if the presenter or judges receive the SMS on their actual physical phone, tapping the link loads the exact same sleek audit card on their handheld device!

---

## 5. Verification Plan

### Automated Database & API Verification
1. Run `python backend/scripts/init_tiger_db.py` to verify TimescaleDB and pgvector extensions initialize on Tiger Data.
2. Run `python backend/scripts/seed_cms_data.py` to populate seed data and verify hypertables and vector indexes.
3. Execute backend tests for:
   - `GET /api/doctors` -> returns roster with pgvector anomaly flags.
   - `GET /api/doctors/{npi}/audit` -> returns audit metrics and TimescaleDB monthly velocity.
   - `POST /api/campaign/send-sms` -> triggers Twilio or mock event with signed audit token.
   - `POST /api/auth/verify-otp` -> validates 4-digit OTP.
   - `POST /api/dispute/generate` -> generates 42 CFR § 403.908 notice.

### Manual Split-Screen Verification
1. Launch backend (`uvicorn app.main:app`) and frontend (`npm run dev`).
2. Open `http://localhost:3000` in a desktop browser.
3. Select an anomalous doctor (e.g., Dr. Jane Miller, Dermatologist with an Orthopedic Spine device charge).
4. Click "Launch Sunshine Alert SMS".
5. Observe the simulated SMS appear on the right-side phone emulator (and real phone if Twilio configured).
6. Click the SMS link in the phone emulator -> verify Audit Card renders with total $, meals, and unreviewed warnings.
7. Click "Dispute Unreviewed Items" -> verify OTP prompt appears -> enter 4-digit code.
8. Verify success screen displays generated formal 42 CFR § 403.908 dispute notice and enrollment confirmation.
9. Verify left-side Campaign Console pipeline counter updates in real time.
