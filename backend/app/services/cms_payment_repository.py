"""CRUD helpers for locally persisted CMS Open Payments records (MongoDB).

CMS source fields are immutable after ingestion. The only mutable fields are
local workflow annotations such as review status and mismatch score.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument, UpdateOne

from app.core.config import get_settings
from app.core.database import from_bson, payment_day_filter, to_decimal128
from app.models.documents import CmsIngestionRun, CmsPayment, utcnow
from app.services.embedding_service import embed_text, payment_embedding_text
from app.services.cms_open_payments_service import fetch_raw_payments_page, normalize_payment
from app.services.vector_mismatch_service import score_specialty_mismatch
from app.services.risk_triage_service import MODEL_VERSION, run_isolation_forest_triage

UNSET = object()

PAYMENT_FIELDS = (
    "raw_cms_record_id", "payment_date", "recipient_npi", "recipient_profile_id",
    "recipient_type", "recipient_first_name", "recipient_middle_name",
    "recipient_last_name", "recipient_specialty", "recipient_city", "recipient_state",
    "recipient_zip_code", "manufacturer_name", "manufacturer_id", "product_name",
    "payment_type", "payment_form", "payment_count", "amount_usd",
    "cms_dispute_status", "publication_date", "is_reviewed", "mismatch_score",
    "cms_program_year", "source_url", "source_fetched_at", "ingestion_run_id",
)
PAYMENT_PROJECTION = {"_id": 0, **{field: 1 for field in PAYMENT_FIELDS}}


def _payments(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[CmsPayment.Settings.name]


def _cms_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").replace(tzinfo=timezone.utc)


def _payment_output(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    record = from_bson({field: document.get(field) for field in PAYMENT_FIELDS})
    if record["publication_date"]:
        record["publication_date"] = record["publication_date"].date()
    if record["ingestion_run_id"] is not None:
        record["ingestion_run_id"] = str(record["ingestion_run_id"])
    return record


def payment_document(record: dict[str, Any], source: dict[str, Any], run_id: Any) -> dict[str, Any]:
    """Map one raw CMS datastore record to a ``cms_payments`` document."""
    products = [
        record.get(f"name_of_drug_or_biological_or_device_or_medical_supply_{index}")
        for index in range(1, 6)
    ]
    return {
        "recipient_npi": record.get("covered_recipient_npi") or None,
        "recipient_profile_id": record.get("covered_recipient_profile_id") or None,
        "recipient_type": record.get("covered_recipient_type") or None,
        "recipient_first_name": record.get("covered_recipient_first_name") or None,
        "recipient_middle_name": record.get("covered_recipient_middle_name") or None,
        "recipient_last_name": record.get("covered_recipient_last_name") or None,
        "recipient_specialty": record.get("covered_recipient_specialty_1") or None,
        "recipient_city": record.get("recipient_city") or None,
        "recipient_state": record.get("recipient_state") or None,
        "recipient_zip_code": record.get("recipient_zip_code") or None,
        "payment_date": _cms_datetime(record.get("date_of_payment")),
        "manufacturer_name": record.get("applicable_manufacturer_or_applicable_gpo_making_payment_name") or "Unknown reporting entity",
        "manufacturer_id": record.get("applicable_manufacturer_or_applicable_gpo_making_payment_id") or None,
        "product_name": next((product for product in products if product), None),
        "payment_type": record.get("nature_of_payment_or_transfer_of_value") or None,
        "payment_form": record.get("form_of_payment_or_transfer_of_value") or None,
        "payment_count": int(record.get("number_of_payments_included_in_total_amount") or 1),
        "amount_usd": to_decimal128(record.get("total_amount_of_payment_usdollars")),
        "is_reviewed": False,
        "dispute_id": None,
        "product_embedding": embed_text(payment_embedding_text(
            next((product for product in products if product), None),
            record.get("nature_of_payment_or_transfer_of_value"),
        )),
        "mismatch_score": None,
        "current_risk_score": None,
        "current_risk_model_version": None,
        "raw_cms_record_id": record.get("record_id"),
        "cms_dispute_status": record.get("dispute_status_for_publication") or None,
        "publication_date": _cms_datetime(record.get("payment_publication_date")),
        "delay_in_publication_indicator": record.get("delay_in_publication_indicator") or None,
        "change_type": record.get("change_type") or None,
        "cms_program_year": int(record.get("program_year") or source["program_year"]),
        "source_url": source["url"],
        "source_fetched_at": utcnow(),
        "raw_cms_payload": record,
        "ingestion_run_id": run_id,
        "created_at": utcnow(),
    }


async def upsert_payments(collection: AsyncIOMotorCollection, documents: list[dict[str, Any]]) -> int:
    """Insert only source records not already stored; return the inserted count.

    ``$setOnInsert`` on the unique ``(raw_cms_record_id, payment_date)`` index
    never overwrites an existing local copy.
    """
    if not documents:
        return 0
    result = await collection.bulk_write([
        UpdateOne(
            {"raw_cms_record_id": document["raw_cms_record_id"], "payment_date": document["payment_date"]},
            {"$setOnInsert": document},
            upsert=True,
        )
        for document in documents
    ], ordered=False)
    return result.upserted_count


async def ingest_cms_page(
    db: AsyncIOMotorDatabase,
    *,
    limit: int,
    offset: int,
    recipient_state: str | None = None,
    manufacturer_id: str | None = None,
    payment_nature: str | None = None,
    recipient_type: str | None = None,
) -> dict[str, Any]:
    """Fetch one official CMS page and insert only records not already stored."""
    page = await fetch_raw_payments_page(
        limit=limit,
        offset=offset,
        recipient_state=recipient_state,
        manufacturer_id=manufacturer_id,
        payment_nature=payment_nature,
        recipient_type=recipient_type,
    )
    source = page["source"]
    run = await CmsIngestionRun(
        dataset_id=source["dataset_id"],
        program_year=source["program_year"],
        source_url=source["url"],
        filters=page["filters"],
        start_offset=page["pagination"]["offset"],
        page_size=page["pagination"]["limit"],
        pages_requested=1,
    ).insert()
    inserted = await upsert_payments(
        _payments(db), [payment_document(record, source, run.id) for record in page["records"]],
    )

    # Specialty mismatch is an Isolation Forest input, so refresh it first.
    await score_specialty_mismatch(db)
    # Train a fresh vanilla Isolation Forest on this new retained snapshot so
    # the re-rendered queue already contains current anomaly results.
    # Prior results stay current until the new batch is ready, so a failed
    # import never leaves the queue without scores.
    triage = await run_isolation_forest_triage(db, invalidated_by_ingestion_run_id=run.id)

    seen = len(page["records"])
    run.records_ingested = run.records_inserted = inserted
    run.records_seen = seen
    run.records_skipped = seen - inserted
    run.status = "completed"
    run.completed_at = utcnow()
    await run.save()
    return {
        "run_id": str(run.id),
        "source": source,
        "filters": page["filters"],
        "pagination": page["pagination"],
        "records_seen": seen,
        "records_inserted": inserted,
        "records_skipped": seen - inserted,
        "risk_assessments_invalidated": triage["records_invalidated"],
        "risk_assessments_created": triage["records_scored"],
        "risk_assessments_flagged": triage["records_flagged"],
        "risk_model_version": triage["model_version"],
    }


async def query_cms_payments_page(
    db: AsyncIOMotorDatabase,
    *,
    limit: int,
    offset: int,
    recipient_state: str | None = None,
    manufacturer_id: str | None = None,
    payment_nature: str | None = None,
    recipient_type: str | None = None,
) -> dict[str, Any]:
    """Serve the normalized CMS General Payment feed from ``cms_payments``.

    Mirrors ``fetch_payments_page`` so ``GET /api/payments`` keeps its shape
    without calling the CMS API at request time.
    """
    settings = get_settings()
    limit = max(1, min(limit, settings.CMS_OPEN_PAYMENTS_MAX_PAGE_SIZE))
    offset = max(0, offset)
    filters = {
        "recipient_state": ("recipient_state", recipient_state.upper() if recipient_state else None),
        "manufacturer_id": ("manufacturer_id", manufacturer_id),
        "payment_nature": ("payment_type", payment_nature),
        "recipient_type": ("recipient_type", recipient_type),
    }
    query: dict[str, Any] = {}
    applied_filters: dict[str, str] = {}
    for name, (field, value) in filters.items():
        if value is not None:
            query[field] = value
            applied_filters[name] = value

    collection = _payments(db)
    total = await collection.count_documents(query)
    cursor = collection.find(query, {"raw_cms_payload": 1, "source_fetched_at": 1}).sort("_id", 1).skip(offset).limit(limit)
    rows = await cursor.to_list(length=limit)
    return {
        "source": {
            "name": "CMS Open Payments",
            "url": settings.CMS_OPEN_PAYMENTS_API_BASE_URL,
            "dataset_id": settings.CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID,
            "program_year": settings.CMS_OPEN_PAYMENTS_PROGRAM_YEAR,
            "served_from": "mongodb",
            "collection": CmsPayment.Settings.name,
        },
        "filters": applied_filters,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_matching_records": total,
            "returned_records": len(rows),
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
        },
        "payments": [
            normalize_payment(row.get("raw_cms_payload") or {}, retrieved_at=row.get("source_fetched_at"))
            for row in rows
        ],
    }


async def list_payments(
    db: AsyncIOMotorDatabase,
    *,
    limit: int,
    offset: int,
    recipient_state: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if recipient_state:
        query["recipient_state"] = recipient_state.upper()

    collection = _payments(db)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query, PAYMENT_PROJECTION)
        .sort([("payment_date", 1), ("raw_cms_record_id", 1)])
        .skip(offset)
        .limit(limit)
    )
    records = [_payment_output(row) for row in await cursor.to_list(length=limit)]
    return {
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_records": total,
            "returned_records": len(records),
            "next_offset": offset + len(records) if offset + len(records) < total else None,
        },
        "records": records,
    }


QUEUE_PROJECTION = {
    "_id": 0, "raw_cms_record_id": 1, "payment_date": 1, "recipient_npi": 1,
    "recipient_first_name": 1, "recipient_last_name": 1, "recipient_specialty": 1,
    "recipient_city": 1, "recipient_state": 1, "recipient_zip_code": 1,
    "manufacturer_name": 1, "payment_type": 1, "amount_usd": 1, "product_name": 1,
    "is_reviewed": 1, "mismatch_score": 1, "current_risk_score": 1, "current_risk_model_version": 1,
}


async def _queue_rows(db: AsyncIOMotorDatabase, query: dict[str, Any], sort: list, limit: int | None) -> list[dict[str, Any]]:
    """Payments with their current risk score, read from the embedded copy.

    Triage writes ``current_risk_score`` onto each payment alongside the
    ``risk_assessments`` history, so the queue needs no per-row join.
    """
    cursor = _payments(db).find(query, QUEUE_PROJECTION).sort(sort)
    if limit is not None:
        cursor = cursor.limit(limit)
    rows = []
    for row in await cursor.to_list(length=limit):
        row = from_bson(row)
        is_current = row.pop("current_risk_model_version", None) == MODEL_VERSION
        score = row.pop("current_risk_score", None)
        rows.append({**row, "risk_score": score if is_current else None})
    return rows


async def list_review_queue(db: AsyncIOMotorDatabase, *, limit: int = 5000) -> dict[str, Any]:
    """Build the frontend queue from retained CMS records, not seed fixtures.

    Payments without an NPI remain available through ``/api/stored-payments``
    but cannot be safely grouped into an HCP review queue.
    """
    _query_start = time.perf_counter()
    rows = await _queue_rows(
        db,
        {"recipient_npi": {"$regex": r"^\d{10}$"}},
        [("recipient_npi", 1), ("payment_date", -1), ("raw_cms_record_id", 1)],
        limit,
    )
    query_ms = round((time.perf_counter() - _query_start) * 1000, 1)
    grouped: dict[str, dict[str, Any]] = {}
    payment_count = 0
    vector_scored = 0
    for data in rows:
        npi = data["recipient_npi"]
        physician = grouped.setdefault(npi, {
            "npi": npi,
            "nppes": {
                "npi": npi,
                "legal_name": "", "first_name": data.get("recipient_first_name") or "Unknown",
                "last_name": data.get("recipient_last_name") or "Recipient", "credential": "",
                "taxonomy_code": "", "taxonomy_desc": data.get("recipient_specialty") or "Not reported",
                "primary_specialty": data.get("recipient_specialty") or "Not reported",
                "address": {
                    "address_1": "", "city": data.get("recipient_city") or "",
                    "state": data.get("recipient_state") or "", "postal_code": data.get("recipient_zip_code") or "",
                },
                "verified": False, "enriched_at": "",
            },
            "payments": [], "total_amount": 0.0, "meal_count": 0,
            "unreviewed_count": 0, "outlier_count": 0, "mismatch_score": 0.0, "risk_score": 0,
        })
        if not physician["nppes"]["legal_name"]:
            physician["nppes"]["legal_name"] = f"{physician['nppes']['first_name']} {physician['nppes']['last_name']}".strip()
        amount = float(data["amount_usd"])
        payment_type = data.get("payment_type") or "Not reported"
        risk_score = int(data.get("risk_score") or 0)
        mismatch_score = float(data.get("mismatch_score") or 0)
        physician["payments"].append({
            "id": data["raw_cms_record_id"], "payment_date": data["payment_date"].date().isoformat(),
            "manufacturer": data["manufacturer_name"], "nature_of_payment": payment_type,
            "amount": amount, "product_name": data.get("product_name") or "Not reported",
            "product_category": "", "reviewed": bool(data.get("is_reviewed")),
            "mismatch_score": mismatch_score,
            "risk_score": risk_score, "velocity_flag": False,
        })
        physician["total_amount"] += amount
        physician["meal_count"] += int("food" in payment_type.lower() or "meal" in payment_type.lower())
        physician["unreviewed_count"] += int(not data.get("is_reviewed"))
        physician["mismatch_score"] = max(physician["mismatch_score"], mismatch_score)
        physician["risk_score"] = max(physician["risk_score"], risk_score)
        physician["outlier_count"] += int(risk_score > 0)
        payment_count += 1
        vector_scored += int(data.get("mismatch_score") is not None)

    physicians = list(grouped.values())
    for physician in physicians:
        risk_score = physician["risk_score"]
        mismatch_score = physician["mismatch_score"]
        physician["risk_level"] = "critical" if risk_score >= 60 or mismatch_score >= 0.7 else "high" if risk_score >= 40 or mismatch_score >= 0.5 else "medium" if risk_score >= 25 or mismatch_score >= 0.2 else "low"
    return {
        "physicians": physicians,
        "total": len(physicians),
        "db_metrics": {
            "engine": "mongodb_atlas",
            "query_ms": query_ms,
            "vector_scored_payments": vector_scored,
            "vector_index_type": "atlas_vector_search",
            "active_physicians": len(physicians),
            "total_payments": payment_count,
        },
    }


async def list_review_queue_for_npi(db: AsyncIOMotorDatabase, npi: str) -> list[dict[str, Any]]:
    """Fetch all payments for a single NPI, used by the audit token route."""
    return await _queue_rows(db, {"recipient_npi": npi}, [("payment_date", -1), ("raw_cms_record_id", 1)], None)


async def get_payment(db: AsyncIOMotorDatabase, record_id: str, payment_date: date) -> dict[str, Any] | None:
    return _payment_output(await _payments(db).find_one(payment_day_filter(record_id, payment_date), PAYMENT_PROJECTION))


async def update_local_review(
    db: AsyncIOMotorDatabase,
    *,
    record_id: str,
    payment_date: date,
    is_reviewed: bool | None,
    mismatch_score: float | None | object = UNSET,
) -> dict[str, Any] | None:
    updates: dict[str, Any] = {}
    if is_reviewed is not None:
        updates["is_reviewed"] = is_reviewed
    if mismatch_score is not UNSET:
        updates["mismatch_score"] = mismatch_score
    if not updates:
        raise ValueError("Provide is_reviewed and/or mismatch_score.")

    document = await _payments(db).find_one_and_update(
        payment_day_filter(record_id, payment_date),
        {"$set": updates},
        projection=PAYMENT_PROJECTION,
        return_document=ReturnDocument.AFTER,
    )
    return _payment_output(document)


async def delete_payment(db: AsyncIOMotorDatabase, record_id: str, payment_date: date) -> bool:
    result = await _payments(db).delete_one(payment_day_filter(record_id, payment_date))
    return result.deleted_count == 1
