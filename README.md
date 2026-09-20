# FalsePay

Outbound Engine to HCPs

## Docker deployment

Deploy the backend first, then build the frontend with its public backend URL.
Run these commands from the repository root. Use `backend/` and `frontend/` as
the respective build contexts in your hosting provider.

```bash
docker build -t falsepay-backend ./backend
docker run --rm --env-file backend/.env --env APP_ENV=production \
  --publish 127.0.0.1:8000:8000 falsepay-backend
```

Prepare `backend/.env` from `backend/.env.example` if you do not already have it.
Supply your database URLs, CMS dataset ID, secret key, and optional Gemini key
through the backend host's runtime environment settings. Set `CORS_ORIGINS` to
`["https://your-frontend.example.com"]` once the frontend domain is known and
restart the backend. Both images exclude `.env` files.

After deploying the backend, use its HTTPS origin when building the frontend:

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=https://your-backend.example.com \
  -t falsepay-frontend ./frontend
docker run --rm --publish 127.0.0.1:3000:3000 falsepay-frontend
```

`NEXT_PUBLIC_API_URL` is a public configuration value, not a secret API key.
Use no trailing slash or `/api` suffix. Next.js embeds this URL during the build,
so rebuild the frontend image when it changes. For both containers, `PORT` can
be set at runtime if your host requires a different listening port (defaults:
backend 8000, frontend 3000). The local commands above bind only to your machine;
configure public HTTPS routing through your deployment provider.

The database is external to these images. See [backend setup](backend/README.md#production-container)
for initializing a new database. For local Docker testing, build the frontend
with `NEXT_PUBLIC_API_URL=http://localhost:8000` and use the default backend
`CORS_ORIGINS=["http://localhost:3000"]`.

## Concept

Goal: build the next HCP engagement tool and invent the way we engage HCPs

Hackathon Concept: The CMS Open Payments "Audit & Defense" Guard
Every pharmaceutical and medical device manufacturer is federally mandated under the Sunshine Act to report every meal, advisory fee, travel expense, and research grant given to physicians. This data is published publicly by CMS (Centers for Medicare & Medicaid Services) on the Open Payments database.

The Physician's Hidden Anxiety: Physicians dread this database. Patients, local journalists, and malpractice attorneys search it. Pharma sales reps frequently log meals or promotional items under a doctor's NPI that the doctor never attended or authorized. Doctors have a limited 45-day review window each spring to dispute fraudulent or inaccurate entries before they become public record.
The Data Engine (100% Public):
Download the open CMS Open Payments dataset.
Match the doctor's NPI to the total dollar value, meal count, and corporate entities that reported payments against them in the latest filing.
The Cold Outbound SMS:

"Dr. [Last Name], $3,840 across 6 industry transactions was reported under your NPI (1234567890) in the new CMS Open Payments ledger. 2 entries have not been reviewed. View your public transparency profile & generate a formal dispute before publication: [1-Click Secure Link]"
The Conversion Mechanism:
The link opens a clean, zero-login audit card displaying their exact reported numbers.
To dispute or lock their report, they tap "Authenticate via Mobile"—which instantly verifies their NPI and creates their active Impiricus profile.
Once opted in, Impiricus acts as their permanent "Open Payments Alert System," creating an ongoing, trusted channel to the physician's personal device.
