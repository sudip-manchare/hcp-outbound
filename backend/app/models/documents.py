"""Beanie document models for the MongoDB Atlas collections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from beanie import Document, PydanticObjectId
from beanie.odm.custom_types.decimal import DecimalAnnotation
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 compatible dimension
PAYMENT_VECTOR_INDEX = "cms_payments_product_embedding"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Physician(Document):
    npi: str
    first_name: str
    last_name: str
    credential: str | None = None
    primary_taxonomy: str | None = None
    taxonomy_code: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    nppes_last_fetched: datetime | None = None
    specialty_embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "physicians"
        indexes = [IndexModel([("npi", ASCENDING)], name="uq_physicians_npi", unique=True)]


class CmsPayment(Document):
    # CMS publishes payments for providers, practitioners, and teaching
    # hospitals; an NPI is therefore not required for every source row.
    recipient_npi: str | None = None
    recipient_profile_id: str | None = None
    recipient_type: str | None = None
    recipient_first_name: str | None = None
    recipient_middle_name: str | None = None
    recipient_last_name: str | None = None
    recipient_specialty: str | None = None
    recipient_city: str | None = None
    recipient_state: str | None = None
    recipient_zip_code: str | None = None
    payment_date: datetime
    manufacturer_name: str
    manufacturer_id: str | None = None
    product_name: str | None = None
    payment_type: str | None = None  # CMS nature of payment / transfer of value
    payment_form: str | None = None
    payment_count: int | None = None
    amount_usd: DecimalAnnotation
    is_reviewed: bool = False
    dispute_id: PydanticObjectId | None = None
    product_embedding: list[float] | None = None
    # Share of similar-product payments (Atlas $vectorSearch) received by other specialties.
    mismatch_score: float | None = None
    # Set when a reviewer PATCHes mismatch_score; vector scoring then skips the payment.
    mismatch_score_manual: bool = False
    # Embedded copy of the current risk_assessments score (replaces a per-row join).
    current_risk_score: int | None = None
    current_risk_model_version: str | None = None
    raw_cms_record_id: str | None = None
    cms_dispute_status: str | None = None
    publication_date: datetime | None = None
    delay_in_publication_indicator: str | None = None
    change_type: str | None = None
    cms_program_year: int | None = None
    source_url: str | None = None
    source_dataset_id: str | None = None
    source_fetched_at: datetime | None = None
    raw_cms_payload: dict[str, Any] | None = None
    ingestion_run_id: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "cms_payments"
        indexes = [
            IndexModel(
                [("raw_cms_record_id", ASCENDING), ("payment_date", ASCENDING)],
                name="uq_cms_payments_source_record", unique=True,
            ),
            IndexModel([("recipient_npi", ASCENDING), ("payment_date", DESCENDING)], name="idx_cms_payments_npi_date"),
            IndexModel([("recipient_npi", ASCENDING), ("is_reviewed", ASCENDING)], name="idx_cms_payments_reviewed"),
            IndexModel([("manufacturer_name", ASCENDING)], name="idx_cms_payments_manufacturer"),
            IndexModel([("manufacturer_id", ASCENDING)], name="idx_cms_payments_manufacturer_id"),
            IndexModel([("recipient_state", ASCENDING)], name="idx_cms_payments_recipient_state"),
            IndexModel([("payment_date", ASCENDING)], name="idx_cms_payments_payment_date"),
            IndexModel([("ingestion_run_id", ASCENDING)], name="idx_cms_payments_ingestion_run"),
        ]


class Dispute(Document):
    physician_npi: str
    payment_ids: list[PydanticObjectId]  # cms_payments._id values
    manufacturer_name: str | None = None
    manufacturer_compliance_email: str | None = None
    dispute_notice_text: str | None = None  # 42 CFR § 403.908 notice
    status: Literal["pending", "submitted", "resolved"] = "pending"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "disputes"
        indexes = [IndexModel([("physician_npi", ASCENDING)], name="idx_disputes_npi")]


class AuditToken(Document):
    token: str  # SHA-256 hex digest of the signed token, never the plaintext
    npi: str
    expires_at: datetime
    accessed: bool = False
    pipeline_state: Literal["dispatched", "opened", "disputed", "protected"] = "dispatched"
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "audit_tokens"
        indexes = [
            IndexModel([("token", ASCENDING)], name="uq_audit_tokens_token", unique=True),
            IndexModel([("npi", ASCENDING), ("expires_at", ASCENDING)], name="idx_audit_tokens_npi"),
            # MongoDB removes a token document once expires_at has passed.
            IndexModel([("expires_at", ASCENDING)], name="ttl_audit_tokens_expires_at", expireAfterSeconds=0),
        ]


class CmsIngestionRun(Document):
    dataset_id: str
    program_year: int
    source_url: str
    filters: dict[str, Any] = Field(default_factory=dict)
    start_offset: int
    page_size: int
    pages_requested: int
    records_ingested: int = 0
    records_seen: int = 0
    records_inserted: int = 0
    records_skipped: int = 0
    status: Literal["running", "completed", "failed"] = "running"
    error_message: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    class Settings:
        name = "cms_ingestion_runs"


class RiskSignal(BaseModel):
    code: str
    weight: int = Field(ge=0)
    title: str
    plain_explanation: str
    evidence: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)


class RiskAssessment(Document):
    raw_cms_record_id: str
    payment_date: datetime
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "review", "high_priority_review"]
    review_recommended: bool
    model_version: str
    plain_language_explanation: str
    evidence: dict[str, Any]  # model metadata
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    is_current: bool = True
    invalidated_by_ingestion_run_id: PydanticObjectId | None = None
    invalidated_at: datetime | None = None
    assessed_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "risk_assessments"
        indexes = [
            IndexModel(
                [("raw_cms_record_id", ASCENDING), ("payment_date", ASCENDING), ("assessed_at", DESCENDING)],
                name="idx_risk_assessments_source",
            ),
            IndexModel([("risk_level", ASCENDING), ("assessed_at", DESCENDING)], name="idx_risk_assessments_priority"),
            IndexModel(
                [
                    ("raw_cms_record_id", ASCENDING), ("payment_date", ASCENDING),
                    ("model_version", ASCENDING), ("assessed_at", DESCENDING),
                ],
                name="idx_risk_assessments_current",
                partialFilterExpression={"is_current": True},
            ),
        ]


DOCUMENT_MODELS = [Physician, CmsPayment, Dispute, AuditToken, CmsIngestionRun, RiskAssessment]
