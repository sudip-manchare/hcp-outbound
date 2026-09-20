"""FastAPI entry point for live NPPES and CMS Open Payments enrichment."""

from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.schema import CMSIngestionRequest, LocalPaymentReviewUpdate
from app.services.cms_open_payments_service import CMSOpenPaymentsServiceError, fetch_payments_page
from app.services.cms_payment_repository import (
    UNSET,
    delete_payment,
    get_payment,
    ingest_cms_page,
    list_review_queue,
    list_payments,
    update_local_review,
)
from app.services.nppes_service import NPPESProviderNotFoundError, NPPESServiceError, fetch_provider, validate_npi
from app.services.risk_triage_service import assess_payment, get_current_assessment
from app.services.gemini_explanation_service import explain_assessment

settings = get_settings()
app = FastAPI(title="HCP Outbound API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


def _bad_npi(npi: str) -> None:
    try:
        validate_npi(npi)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "sources": {
            "nppes": settings.NPPES_API_BASE_URL,
            "cms_open_payments": settings.CMS_OPEN_PAYMENTS_API_BASE_URL,
            "cms_dataset_id": settings.CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID,
        },
    }


@app.get("/api/doctors/enrich/{npi}")
async def enrich_doctor(npi: str) -> dict:
    """Retrieve a provider live from the official NPPES Registry."""
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
) -> dict:
    """Retrieve a generic, paginated CMS General Payment feed.

    Each payment includes a recipient NPI when available. Call the NPPES route
    after selecting the provider you want to inspect.
    """
    try:
        return await fetch_payments_page(
            limit=limit,
            offset=offset,
            recipient_state=recipient_state,
            manufacturer_id=manufacturer_id,
            payment_nature=payment_nature,
            recipient_type=recipient_type,
        )
    except CMSOpenPaymentsServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/ingestions/cms", status_code=status.HTTP_201_CREATED)
async def pull_and_ingest_cms_payments(
    request: CMSIngestionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The frontend's one-call action: pull CMS, then persist only new rows."""
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read a page of local, previously ingested CMS records."""
    return await list_payments(db, limit=limit, offset=offset, recipient_state=recipient_state)


@app.get("/api/doctors")
async def review_queue(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the UI review queue derived from locally ingested CMS records."""
    return await list_review_queue(db)


@app.get("/api/stored-payments/{record_id}")
async def stored_payment(
    record_id: str,
    payment_date: date,
    db: AsyncSession = Depends(get_db),
) -> dict:
    record = await get_payment(db, record_id, payment_date)
    if not record:
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return record


@app.post("/api/stored-payments/{record_id}/risk-triage", status_code=status.HTTP_201_CREATED)
async def triage_stored_payment(
    record_id: str,
    payment_date: date,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the stored model result plus on-demand Gemini interpretation."""
    assessment = await assess_payment(db, record_id, payment_date)
    if not assessment:
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return {**assessment, "ai_explanation": await explain_assessment(assessment)}


@app.get("/api/stored-payments/{record_id}/risk-triage")
async def current_stored_payment_triage(
    record_id: str,
    payment_date: date,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read the current assessment for this ingestion cycle, if it exists."""
    assessment = await get_current_assessment(db, record_id, payment_date)
    if not assessment:
        raise HTTPException(status_code=404, detail="No current risk assessment for this payment.")
    return assessment


@app.patch("/api/stored-payments/{record_id}")
async def update_stored_payment(
    record_id: str,
    payment_date: date,
    update: LocalPaymentReviewUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update local review annotations without changing CMS source fields."""
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
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete only the local copy; the immutable CMS source can be re-ingested later."""
    if not await delete_payment(db, record_id, payment_date):
        raise HTTPException(status_code=404, detail="Stored CMS payment not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
