"""FastAPI entry point: CMS Open Payments served from MongoDB, NPPES enrichment live."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.database import close_db, from_bson, get_db
from app.models.documents import AuditToken, CmsPayment
from app.models.schema import (
    CMSIngestionRequest,
    CampaignDispatchRequest,
    DisputeGenerateRequest,
    LocalPaymentReviewUpdate,
)
from app.services.campaign_service import (
    build_audit_url,
    build_dispatch_preview,
    generate_audit_token,
    token_expiry,
)
from app.services.cms_open_payments_service import CMSOpenPaymentsServiceError
from app.services.cms_payment_repository import (
    UNSET,
    delete_payment,
    get_payment,
    ingest_cms_page,
    list_payments,
    list_review_queue,
    query_cms_payments_page,
    update_local_review,
)
from app.services.gemini_explanation_service import explain_assessment
from app.services.nppes_service import (
    NPPESProviderNotFoundError,
    NPPESServiceError,
    fetch_provider,
    validate_npi,
)
from app.services.risk_triage_service import assess_payment, get_current_assessment

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_db()


app = FastAPI(title="HCP Outbound API", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Security headers middleware
# FIX: Add HTTP security response headers to every reply. These prevent
# clickjacking (X-Frame-Options), MIME-type sniffing (X-Content-Type-Options),
# and limit resource loading (CSP). Applied at middleware level so all routes
# benefit without per-handler boilerplate.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Adjust CSP directives when a CDN or external font provider is added.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:;"
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    # FIX: Restrict allowed headers instead of the previous allow_headers=["*"].
    # Allowing every header widens the cross-origin attack surface unnecessarily.
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "Accept"],
)


# ---------------------------------------------------------------------------
# Admin authentication dependency
# FIX: All state-mutating and data-reading admin routes previously had no
# authentication, letting anyone call ingestion, deletion, or triage endpoints.
# This dependency checks the X-API-Key header against configured API_KEYS.
# Physician-portal routes (/api/audit/*, /api/dispute/*) use token auth instead.
# ---------------------------------------------------------------------------

def _require_admin(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Reject requests that lack a valid admin API key."""
    if not settings.API_KEYS:
        # No keys configured: allow in development, block in production.
        # The config validator already ensures SECRET_KEY is set in production;
        # add a similar env-level guard for API_KEYS when ready to enforce it.
        if settings.APP_ENV == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin authentication is not configured on this server.",
            )
        return  # development: open for local iteration
    if not x_api_key or x_api_key not in settings.API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )


# Convenience type alias used as a parameter annotation on admin routes.
AdminAuth = Annotated[None, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bad_npi(npi: str) -> None:
    try:
        validate_npi(npi)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _resolve_token_hash(token: str) -> str:
    """Return the SHA-256 hex digest used as the DB lookup key for a token.

    FIX: Tokens are stored as their SHA-256 hash, not as plaintext. This
    means a database breach cannot be used to forge audit links.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def _load_token_record(db: AsyncIOMotorDatabase, token: str) -> dict:
    """Look up a token record and enforce expiry, raising HTTP exceptions on failure."""
    token_hash = _resolve_token_hash(token)
    record = await db[AuditToken.Settings.name].find_one(
        {"token": token_hash},
        {"_id": 0, "npi": 1, "expires_at": 1, "accessed": 1, "pipeline_state": 1},
    )
    if record is None:
        raise HTTPException(status_code=404, detail="This audit link is invalid or has not been issued.")
    expires_at = record["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=410, detail="This audit link has expired.")
    return dict(record) | {"token_hash": token_hash}


# ---------------------------------------------------------------------------
# Public routes (no auth)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "sources": {
            "nppes": {"mode": "live_api", "url": settings.NPPES_API_BASE_URL},
            "cms_open_payments": {
                "mode": "mongodb",
                "database": settings.MONGODB_DB_NAME,
                "collection": CmsPayment.Settings.name,
                "ingested_from": settings.CMS_OPEN_PAYMENTS_API_BASE_URL,
            },
            "cms_dataset_id": settings.CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID,
        },
    }


@app.get("/api/doctors/enrich/{npi}")
async def enrich_doctor(npi: str) -> dict:
    """Retrieve a provider live from the official NPPES Registry (public data)."""
    _bad_npi(npi)
    try:
        return await fetch_provider(npi)
    except NPPESProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NPPESServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/payments")
async def cms_payments(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    recipient_state: str | None = Query(default=None, min_length=2, max_length=2),
    manufacturer_id: str | None = Query(default=None),
    payment_nature: str | None = Query(default=None),
    recipient_type: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Paginated CMS General Payment feed served from MongoDB (no live CMS call)."""
    return await query_cms_payments_page(
        db,
        limit=limit,
        offset=offset,
        recipient_state=recipient_state,
        manufacturer_id=manufacturer_id,
        payment_nature=payment_nature,
        recipient_type=recipient_type,
    )


# ---------------------------------------------------------------------------
# Admin routes (X-API-Key required)
# ---------------------------------------------------------------------------

@app.post("/api/ingestions/cms", status_code=status.HTTP_201_CREATED)
async def pull_and_ingest_cms_payments(
    request: CMSIngestionRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Pull one CMS page and persist only new rows. Requires admin auth."""
    try:
        return await ingest_cms_page(
            db,
            limit=request.limit,
            offset=request.offset,
            recipient_state=request.recipient_state,
            manufacturer_id=request.manufacturer_id,
            payment_nature=request.payment_nature,
            recipient_type=request.recipient_type,
        )
    except CMSOpenPaymentsServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/stored-payments")
async def stored_payments(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    recipient_state: str | None = Query(default=None, min_length=2, max_length=2),
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Read a page of locally ingested CMS records. Requires admin auth."""
    return await list_payments(db, limit=limit, offset=offset, recipient_state=recipient_state)


@app.get("/api/doctors")
async def review_queue(
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Return the UI review queue from locally ingested CMS records. Requires admin auth."""
    return await list_review_queue(db)


@app.get("/api/stored-payments/{record_id}")
async def stored_payment(
    record_id: str,
    payment_date: date,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    record = await get_payment(db, record_id, payment_date)
    if not record:
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return record


@app.post("/api/stored-payments/{record_id}/risk-triage", status_code=status.HTTP_201_CREATED)
async def triage_stored_payment(
    record_id: str,
    payment_date: date,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Return stored model result plus on-demand Gemini interpretation. Requires admin auth."""
    assessment = await assess_payment(db, record_id, payment_date)
    if not assessment:
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return {**assessment, "ai_explanation": await explain_assessment(assessment)}


@app.get("/api/stored-payments/{record_id}/risk-triage")
async def current_stored_payment_triage(
    record_id: str,
    payment_date: date,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Read the current assessment for this ingestion cycle. Requires admin auth."""
    assessment = await get_current_assessment(db, record_id, payment_date)
    if not assessment:
        raise HTTPException(status_code=404, detail="No current risk assessment for this payment.")
    return assessment


@app.patch("/api/stored-payments/{record_id}")
async def update_stored_payment(
    record_id: str,
    payment_date: date,
    update: LocalPaymentReviewUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Update local review annotations without changing CMS source fields. Requires admin auth."""
    try:
        record = await update_local_review(
            db,
            record_id=record_id,
            payment_date=payment_date,
            is_reviewed=update.is_reviewed,
            mismatch_score=update.mismatch_score if "mismatch_score" in update.model_fields_set else UNSET,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not record:
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return record


@app.delete("/api/stored-payments/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stored_payment(
    record_id: str,
    payment_date: date,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> Response:
    """Delete only the local copy; CMS source can be re-ingested later. Requires admin auth."""
    if not await delete_payment(db, record_id, payment_date):
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Campaign routes (admin auth)
# All MongoDB operations for campaigns live here; campaign_service.py stays
# free of database access.
# ---------------------------------------------------------------------------

@app.post("/api/campaign/dispatch", status_code=status.HTTP_201_CREATED)
async def campaign_dispatch(
    request: CampaignDispatchRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Generate a signed audit token and return the outbound alert preview.

    In production, pass the preview body to an SMS/email provider.
    Requires admin auth.
    """
    _bad_npi(request.npi)

    # Fetch a display name from retained CMS data for the preview message.
    payments = db[CmsPayment.Settings.name]
    name_doc = await payments.find_one(
        {"recipient_npi": request.npi, "recipient_last_name": {"$ne": None}},
        {"_id": 0, "recipient_first_name": 1, "recipient_last_name": 1},
    )
    name_row = (
        f"{name_doc.get('recipient_first_name') or ''} {name_doc['recipient_last_name']}" if name_doc else None
    )
    name_parts = (name_row or "Unknown Recipient").split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    # Aggregate payment summary for the preview body.
    agg_rows = await payments.aggregate([
        {"$match": {"recipient_npi": request.npi}},
        {"$group": {
            "_id": None,
            "total_usd": {"$sum": "$amount_usd"},
            "manufacturer_ids": {"$addToSet": "$manufacturer_id"},
            "unreviewed_count": {"$sum": {"$cond": ["$is_reviewed", 0, 1]}},
        }},
        {"$project": {
            "_id": 0, "total_usd": 1, "unreviewed_count": 1,
            # COUNT(DISTINCT) semantics: missing manufacturer IDs are not counted.
            "manufacturer_count": {"$size": {"$setDifference": ["$manufacturer_ids", [None]]}},
        }},
    ]).to_list(length=1)
    agg = from_bson(agg_rows[0]) if agg_rows else {}
    total_usd = float(agg.get("total_usd") or 0)
    manufacturer_count = int(agg.get("manufacturer_count") or 0)
    unreviewed_count = int(agg.get("unreviewed_count") or 0)

    token = generate_audit_token(request.npi)
    expires_at = token_expiry()
    audit_url = build_audit_url(token)

    # FIX: Store the SHA-256 hash of the token, not the plaintext value.
    # A DB breach cannot reconstruct the plaintext token from its hash, so
    # stolen hashes cannot be used to forge audit portal links.
    token_hash = _resolve_token_hash(token)
    try:
        await AuditToken(token=token_hash, npi=request.npi, expires_at=expires_at).insert()
    except DuplicateKeyError:
        pass

    preview = build_dispatch_preview(
        npi=request.npi,
        first_name=first_name,
        last_name=last_name,
        total_usd=total_usd,
        unreviewed_count=unreviewed_count,
        manufacturer_count=manufacturer_count,
        audit_url=audit_url,
    )
    return {**preview, "audit_token": token, "simulated": True}


@app.get("/api/campaign/stats")
async def campaign_stats(
    db: AsyncIOMotorDatabase = Depends(get_db),
    _auth: AdminAuth = None,
) -> dict:
    """Return live pipeline funnel counts from non-expired audit tokens. Requires admin auth."""
    counts = {"dispatched": 0, "opened": 0, "disputed": 0, "protected": 0}
    rows = await db[AuditToken.Settings.name].aggregate([
        {"$match": {"expires_at": {"$gt": datetime.now(timezone.utc)}}},
        {"$group": {"_id": "$pipeline_state", "count": {"$sum": 1}}},
    ]).to_list(length=None)
    for row in rows:
        if row["_id"] in counts:
            counts[row["_id"]] = row["count"]
    return counts


# ---------------------------------------------------------------------------
# Physician audit portal route (token-based auth, no admin key)
# FIX: This route was entirely missing. AuditPageClient.tsx called
# GET /api/audit/{token} which returned a network error because the route
# did not exist, making the entire physician-facing portal non-functional.
# ---------------------------------------------------------------------------

@app.get("/api/audit/{token}")
async def get_audit_card(
    token: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Resolve a physician audit portal token and return their payment summary.

    Called by the zero-login physician portal page. No admin key required;
    the signed token is the physician's credential.
    """
    token_record = await _load_token_record(db, token)
    npi = token_record["npi"]
    token_hash = token_record["token_hash"]

    # Record 'opened' pipeline state transition on first access.
    if token_record["pipeline_state"] == "dispatched":
        await db[AuditToken.Settings.name].update_one(
            {"token": token_hash},
            {"$set": {"pipeline_state": "opened", "accessed": True}},
        )

    # Build physician payment summary from retained CMS records.
    cursor = db[CmsPayment.Settings.name].find(
        {"recipient_npi": npi},
        {
            "_id": 0, "raw_cms_record_id": 1, "payment_date": 1, "manufacturer_name": 1,
            "payment_type": 1, "amount_usd": 1, "product_name": 1, "is_reviewed": 1,
            "mismatch_score": 1, "recipient_first_name": 1, "recipient_last_name": 1,
            "recipient_specialty": 1, "recipient_city": 1, "recipient_state": 1,
            "recipient_zip_code": 1,
        },
    ).sort("payment_date", -1).limit(200)
    rows = [from_bson(r) for r in await cursor.to_list(length=200)]

    if not rows:
        raise HTTPException(status_code=404, detail="No payment records found for this audit link.")

    first = rows[0]
    payments = [
        {
            "id": r["raw_cms_record_id"],
            "payment_date": r["payment_date"].date().isoformat(),
            "manufacturer": r["manufacturer_name"],
            "nature_of_payment": r["payment_type"] or "Not reported",
            "amount": float(r["amount_usd"]),
            "product_name": r["product_name"] or "Not reported",
            "product_category": "",
            "reviewed": bool(r["is_reviewed"]),
            "mismatch_score": float(r["mismatch_score"] or 0),
            "risk_score": 0,
            "velocity_flag": False,
        }
        for r in rows
    ]
    physician = {
        "npi": npi,
        "nppes": {
            "npi": npi,
            "legal_name": f"{first.get('recipient_first_name', '')} {first.get('recipient_last_name', '')}".strip(),
            "first_name": first.get("recipient_first_name") or "",
            "last_name": first.get("recipient_last_name") or "",
            "credential": "", "taxonomy_code": "", "taxonomy_desc": "",
            "primary_specialty": first.get("recipient_specialty") or "Not reported",
            "address": {
                "address_1": "",
                "city": first.get("recipient_city") or "",
                "state": first.get("recipient_state") or "",
                "postal_code": first.get("recipient_zip_code") or "",
            },
            "verified": False, "enriched_at": "",
        },
        "payments": payments,
        "total_amount": sum(float(r["amount_usd"]) for r in rows),
        "meal_count": sum(
            1 for r in rows
            if "food" in (r.get("payment_type") or "").lower()
            or "meal" in (r.get("payment_type") or "").lower()
        ),
        "unreviewed_count": sum(1 for r in rows if not r["is_reviewed"]),
        "mismatch_score": max((float(r.get("mismatch_score") or 0) for r in rows), default=0.0),
        "risk_score": 0, "risk_level": "low", "outlier_count": 0,
    }
    return {
        "physician": physician,
        "audit_token": token,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "velocity_summary": [],
        "top_manufacturers": [],
    }


# ---------------------------------------------------------------------------
# Dispute generation route (token-based auth, no admin key)
# FIX: This route was entirely missing. The frontend called POST /api/dispute/generate
# which resulted in a network error. Now it validates the audit token, verifies
# the NPI binding, selects unreviewed payments, and returns a DisputeNotice.
# ---------------------------------------------------------------------------

@app.post("/api/dispute/generate", status_code=status.HTTP_201_CREATED)
async def generate_dispute(
    request: DisputeGenerateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Generate a 42 CFR § 403.908 dispute notice draft for unreviewed payments.

    The audit token verifies the physician's identity — this prevents an
    unauthenticated caller from generating dispute notices for arbitrary NPIs.
    """
    token_record = await _load_token_record(db, request.audit_token)
    token_hash = token_record["token_hash"]

    # FIX: Validate that the token is bound to the requested NPI.
    # Without this check, any valid token could generate a notice for any NPI.
    if token_record["npi"] != request.npi:
        raise HTTPException(
            status_code=403,
            detail="The audit token is not issued for the requested NPI.",
        )

    # Fetch unreviewed payments eligible for dispute.
    cursor = db[CmsPayment.Settings.name].find(
        {"recipient_npi": request.npi, "is_reviewed": {"$ne": True}},
        {
            "_id": 0, "raw_cms_record_id": 1, "payment_date": 1, "manufacturer_name": 1,
            "manufacturer_id": 1, "payment_type": 1, "amount_usd": 1, "product_name": 1,
            "recipient_first_name": 1, "recipient_last_name": 1, "recipient_specialty": 1,
            "recipient_city": 1, "recipient_state": 1,
        },
    ).sort("payment_date", -1).limit(50)
    payments = [from_bson(r) for r in await cursor.to_list(length=50)]

    if not payments:
        raise HTTPException(
            status_code=422,
            detail="No unreviewed payments found. All entries have already been reviewed.",
        )

    first = payments[0]
    physician_name = (
        f"{first.get('recipient_first_name', '')} {first.get('recipient_last_name', '')}".strip()
        or "Unknown Physician"
    )
    physician_address = ", ".join(
        p for p in [first.get("recipient_city") or "", first.get("recipient_state") or ""] if p
    )

    disputed_payments = [
        {
            "id": p["raw_cms_record_id"],
            "payment_date": p["payment_date"].date().isoformat(),
            "manufacturer": p["manufacturer_name"],
            "nature_of_payment": p["payment_type"] or "Not reported",
            "amount": float(p["amount_usd"]),
            "product_name": p["product_name"] or "Not reported",
            "product_category": "", "reviewed": False,
            "mismatch_score": 0.0, "risk_score": 0, "velocity_flag": False,
        }
        for p in payments
    ]

    # Advance pipeline state to 'disputed'.
    await db[AuditToken.Settings.name].update_one(
        {"token": token_hash, "pipeline_state": {"$in": ["dispatched", "opened"]}},
        {"$set": {"pipeline_state": "disputed"}},
    )

    return {
        "physician_name": physician_name,
        "physician_npi": request.npi,
        "physician_credential": "",
        "physician_specialty": first.get("recipient_specialty") or "Not reported",
        "physician_address": physician_address,
        "manufacturer_name": payments[0]["manufacturer_name"] or "Unknown Reporting Entity",
        "manufacturer_contact": "Compliance Officer",
        "disputed_payments": disputed_payments,
        "total_disputed_amount": sum(float(p["amount_usd"]) for p in payments),
        # FIX: Label clearly as a DRAFT template. The notice is not formally
        # submitted by this API call; the physician must review and submit it.
        # Presenting it as a "formal" notice without that caveat is a regulatory risk.
        "legal_citation": "42 CFR \u00a7 403.908 \u2014 DRAFT template, review before submission",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notice_id": str(uuid.uuid4()),
    }
