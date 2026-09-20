"""CRUD helpers for locally persisted CMS Open Payments records.

CMS source fields are immutable after ingestion. The only mutable fields are
local workflow annotations such as review status and mismatch score.
"""

from __future__ import annotations

from datetime import datetime, timezone
from datetime import date
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cms_open_payments_service import fetch_raw_payments_page
from app.services.risk_triage_service import MODEL_VERSION, run_isolation_forest_triage

UNSET = object()

INSERT_INGESTED_PAYMENT_SQL = text("""
    INSERT INTO cms_payments (
        recipient_npi, recipient_profile_id, recipient_type,
        recipient_first_name, recipient_middle_name, recipient_last_name,
        recipient_specialty, recipient_city, recipient_state, recipient_zip_code,
        payment_date, manufacturer_name, manufacturer_id, product_name,
        payment_type, payment_form, payment_count, amount_usd,
        cms_dispute_status, publication_date, delay_in_publication_indicator,
        change_type, cms_program_year, source_url, source_fetched_at,
        raw_cms_record_id, raw_cms_payload, ingestion_run_id
    ) VALUES (
        :recipient_npi, :recipient_profile_id, :recipient_type,
        :recipient_first_name, :recipient_middle_name, :recipient_last_name,
        :recipient_specialty, :recipient_city, :recipient_state, :recipient_zip_code,
        :payment_date, :manufacturer_name, :manufacturer_id, :product_name,
        :payment_type, :payment_form, :payment_count, :amount_usd,
        :cms_dispute_status, :publication_date, :delay_in_publication_indicator,
        :change_type, :cms_program_year, :source_url, :source_fetched_at,
        :raw_cms_record_id, CAST(:raw_cms_payload AS jsonb), :ingestion_run_id
    )
    ON CONFLICT (raw_cms_record_id, payment_date) DO NOTHING
    RETURNING id
""")


PAYMENT_COLUMNS = """
    raw_cms_record_id, payment_date, recipient_npi, recipient_profile_id,
    recipient_type, recipient_first_name, recipient_middle_name,
    recipient_last_name, recipient_specialty, recipient_city, recipient_state,
    recipient_zip_code, manufacturer_name, manufacturer_id, product_name,
    payment_type, payment_form, payment_count, amount_usd,
    cms_dispute_status, publication_date, is_reviewed, mismatch_score,
    cms_program_year, source_url, source_fetched_at, ingestion_run_id
"""


def _cms_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").replace(tzinfo=timezone.utc)


def _payment_params(record: dict[str, Any], source: dict[str, Any], run_id: int) -> dict[str, Any]:
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
        "amount_usd": record.get("total_amount_of_payment_usdollars"),
        "cms_dispute_status": record.get("dispute_status_for_publication") or None,
        "publication_date": _cms_datetime(record.get("payment_publication_date")),
        "delay_in_publication_indicator": record.get("delay_in_publication_indicator") or None,
        "change_type": record.get("change_type") or None,
        "cms_program_year": int(record.get("program_year") or source["program_year"]),
        "source_url": source["url"],
        "source_fetched_at": datetime.now(timezone.utc),
        "raw_cms_record_id": record.get("record_id"),
        "raw_cms_payload": json.dumps(record),
        "ingestion_run_id": run_id,
    }


async def ingest_cms_page(
    db: AsyncSession,
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
    run = await db.execute(text("""
        INSERT INTO cms_ingestion_runs
            (dataset_id, program_year, source_url, filters, start_offset, page_size, pages_requested)
        VALUES (:dataset_id, :program_year, :source_url, CAST(:filters AS jsonb), :start_offset, :page_size, 1)
        RETURNING id
    """), {
        "dataset_id": source["dataset_id"],
        "program_year": source["program_year"],
        "source_url": source["url"],
        "filters": json.dumps(page["filters"]),
        "start_offset": page["pagination"]["offset"],
        "page_size": page["pagination"]["limit"],
    })
    run_id = run.scalar_one()
    # A new source snapshot can change the comparison population and the CMS
    # record itself. Keep prior results for audit, but never present them as
    # current after the next ingestion begins.
    invalidated = await db.execute(text("""
        UPDATE risk_assessments
        SET is_current = FALSE,
            invalidated_by_ingestion_run_id = :run_id,
            invalidated_at = NOW()
        WHERE is_current = TRUE
    """), {"run_id": run_id})
    inserted = 0
    for record in page["records"]:
        result = await db.execute(INSERT_INGESTED_PAYMENT_SQL, _payment_params(record, source, run_id))
        inserted += int(result.scalar_one_or_none() is not None)

    # Train a fresh vanilla Isolation Forest on this new retained snapshot so
    # the re-rendered queue already contains current anomaly results.
    triage = await run_isolation_forest_triage(db)

    seen = len(page["records"])
    await db.execute(text("""
        UPDATE cms_ingestion_runs
        SET records_ingested = :inserted, records_seen = :seen,
            records_inserted = :inserted, records_skipped = :skipped,
            status = 'completed', completed_at = NOW()
        WHERE id = :run_id
    """), {"run_id": run_id, "seen": seen, "inserted": inserted, "skipped": seen - inserted})
    return {
        "run_id": run_id,
        "source": source,
        "filters": page["filters"],
        "pagination": page["pagination"],
        "records_seen": seen,
        "records_inserted": inserted,
        "records_skipped": seen - inserted,
        "risk_assessments_invalidated": invalidated.rowcount,
        "risk_assessments_created": triage["records_scored"],
        "risk_assessments_flagged": triage["records_flagged"],
        "risk_model_version": triage["model_version"],
    }


async def list_payments(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    recipient_state: str | None = None,
) -> dict[str, Any]:
    filters = ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if recipient_state:
        filters = "WHERE recipient_state = :recipient_state"
        params["recipient_state"] = recipient_state.upper()

    total = await db.scalar(text(f"SELECT COUNT(*) FROM cms_payments {filters}"), params)
    result = await db.execute(text(f"""
        SELECT {PAYMENT_COLUMNS}
        FROM cms_payments
        {filters}
        ORDER BY payment_date, raw_cms_record_id
        LIMIT :limit OFFSET :offset
    """), params)
    records = [dict(row) for row in result.mappings().all()]
    return {
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_records": total or 0,
            "returned_records": len(records),
            "next_offset": offset + len(records) if offset + len(records) < (total or 0) else None,
        },
        "records": records,
    }


async def list_review_queue(db: AsyncSession, *, limit: int = 5000) -> dict[str, Any]:
    """Build the frontend queue from retained CMS records, not seed fixtures.

    Payments without an NPI remain available through ``/api/stored-payments``
    but cannot be safely grouped into an HCP review queue.
    """
    result = await db.execute(text("""
        SELECT raw_cms_record_id, payment_date, recipient_npi,
               recipient_first_name, recipient_last_name, recipient_specialty,
               recipient_city, recipient_state, recipient_zip_code,
               manufacturer_name, payment_type, amount_usd, product_name,
               is_reviewed, mismatch_score, assessment.risk_score
        FROM cms_payments
        LEFT JOIN LATERAL (
            SELECT risk_score
            FROM risk_assessments
            WHERE raw_cms_record_id = cms_payments.raw_cms_record_id
              AND payment_date = cms_payments.payment_date
              AND is_current = TRUE
              AND model_version = :risk_model_version
            ORDER BY assessed_at DESC
            LIMIT 1
        ) AS assessment ON TRUE
        WHERE recipient_npi IS NOT NULL AND length(recipient_npi) = 10
        ORDER BY recipient_npi, payment_date DESC, raw_cms_record_id
        LIMIT :limit
    """), {"limit": limit, "risk_model_version": MODEL_VERSION})
    grouped: dict[str, dict[str, Any]] = {}
    payment_count = 0
    for row in result.mappings():
        data = dict(row)
        npi = data["recipient_npi"]
        physician = grouped.setdefault(npi, {
            "npi": npi,
            "nppes": {
                "npi": npi,
                "legal_name": "", "first_name": data["recipient_first_name"] or "Unknown",
                "last_name": data["recipient_last_name"] or "Recipient", "credential": "",
                "taxonomy_code": "", "taxonomy_desc": data["recipient_specialty"] or "Not reported",
                "primary_specialty": data["recipient_specialty"] or "Not reported",
                "address": {
                    "address_1": "", "city": data["recipient_city"] or "",
                    "state": data["recipient_state"] or "", "postal_code": data["recipient_zip_code"] or "",
                },
                "verified": False, "enriched_at": "",
            },
            "payments": [], "total_amount": 0.0, "meal_count": 0,
            "unreviewed_count": 0, "outlier_count": 0, "mismatch_score": 0.0, "risk_score": 0,
        })
        if not physician["nppes"]["legal_name"]:
            physician["nppes"]["legal_name"] = f"{physician['nppes']['first_name']} {physician['nppes']['last_name']}".strip()
        amount = float(data["amount_usd"])
        payment_type = data["payment_type"] or "Not reported"
        physician["payments"].append({
            "id": data["raw_cms_record_id"], "payment_date": data["payment_date"].date().isoformat(),
            "manufacturer": data["manufacturer_name"], "nature_of_payment": payment_type,
            "amount": amount, "product_name": data["product_name"] or "Not reported",
            "product_category": "", "reviewed": bool(data["is_reviewed"]),
            "mismatch_score": float(data["mismatch_score"] or 0),
            "risk_score": int(data["risk_score"] or 0), "velocity_flag": False,
        })
        physician["total_amount"] += amount
        physician["meal_count"] += int("food" in payment_type.lower() or "meal" in payment_type.lower())
        physician["unreviewed_count"] += int(not data["is_reviewed"])
        physician["mismatch_score"] = max(physician["mismatch_score"], float(data["mismatch_score"] or 0))
        physician["risk_score"] = max(physician["risk_score"], int(data["risk_score"] or 0))
        physician["outlier_count"] += int((data["risk_score"] or 0) > 0)
        payment_count += 1

    physicians = list(grouped.values())
    for physician in physicians:
        risk_score = physician["risk_score"]
        mismatch_score = physician["mismatch_score"]
        physician["risk_level"] = "critical" if risk_score >= 60 or mismatch_score >= 0.7 else "high" if risk_score >= 40 or mismatch_score >= 0.5 else "medium" if risk_score >= 25 or mismatch_score >= 0.2 else "low"
    return {
        "physicians": physicians,
        "total": len(physicians),
        "tiger_data_metrics": {
            "timescale_query_ms": 0, "pgvector_calcs": 0, "hypertable_chunks": 0,
            "vector_index_type": "hnsw", "active_physicians": len(physicians),
            "total_payments": payment_count,
        },
    }


async def get_payment(db: AsyncSession, record_id: str, payment_date: date) -> dict[str, Any] | None:
    result = await db.execute(text(f"""
        SELECT {PAYMENT_COLUMNS}
        FROM cms_payments
        WHERE raw_cms_record_id = :record_id AND payment_date::date = :payment_date
    """), {"record_id": record_id, "payment_date": payment_date})
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def update_local_review(
    db: AsyncSession,
    *,
    record_id: str,
    payment_date: date,
    is_reviewed: bool | None,
    mismatch_score: float | None | object = UNSET,
) -> dict[str, Any] | None:
    updates: list[str] = []
    params: dict[str, Any] = {"record_id": record_id, "payment_date": payment_date}
    if is_reviewed is not None:
        updates.append("is_reviewed = :is_reviewed")
        params["is_reviewed"] = is_reviewed
    if mismatch_score is not UNSET:
        updates.append("mismatch_score = :mismatch_score")
        params["mismatch_score"] = mismatch_score
    if not updates:
        raise ValueError("Provide is_reviewed and/or mismatch_score.")

    result = await db.execute(text(f"""
        UPDATE cms_payments
        SET {", ".join(updates)}
        WHERE raw_cms_record_id = :record_id AND payment_date::date = :payment_date
        RETURNING {PAYMENT_COLUMNS}
    """), params)
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def delete_payment(db: AsyncSession, record_id: str, payment_date: date) -> bool:
    result = await db.execute(text("""
        DELETE FROM cms_payments
        WHERE raw_cms_record_id = :record_id AND payment_date::date = :payment_date
    """), {"record_id": record_id, "payment_date": payment_date})
    return result.rowcount == 1
