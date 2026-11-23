"""Batch anomaly triage using a vanilla scikit-learn Isolation Forest.

The model is fit only on the currently retained CMS payment dataset after an
ingestion. It identifies unusual numerical feature combinations; it never
determines that a payment is fraudulent. Stored observations expose the exact
model inputs so the UI can explain a flag without inventing causal claims.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
from typing import Any

import numpy as np
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne
from sklearn.ensemble import IsolationForest

from app.core.database import from_bson, payment_day_filter
from app.models.documents import RiskAssessment, RiskSignal


MODEL_VERSION = "isolation-forest-v2"
MIN_TRAINING_RECORDS = 20
CONTAMINATION = 0.05
FEATURE_NAMES = (
    "log_payment_amount", "log_payment_count", "log_recipient_30d_count",
    "log_recipient_30d_total", "manufacturer_90d_share", "mismatch_score",
)


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _feature_rows(records: list[dict[str, Any]]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Derive non-leaking temporal features from retained payment history."""
    derived = [dict(record) for record in records]
    by_recipient: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(derived):
        # Do not infer identity when CMS omits an NPI.
        by_recipient[str(record.get("recipient_npi") or f"missing-{index}")].append(index)

    for indexes in by_recipient.values():
        indexes.sort(key=lambda index: derived[index]["payment_date"])
        window_30: deque[int] = deque()
        window_90: deque[int] = deque()
        total_30 = total_90 = 0.0
        manufacturer_90: dict[str, float] = defaultdict(float)
        for index in indexes:
            record = derived[index]
            date = record["payment_date"]
            amount = max(0.0, _float(record.get("amount_usd")))
            while window_30 and derived[window_30[0]]["payment_date"] < date - timedelta(days=29):
                total_30 -= max(0.0, _float(derived[window_30.popleft()].get("amount_usd")))
            while window_90 and derived[window_90[0]]["payment_date"] < date - timedelta(days=89):
                old = derived[window_90.popleft()]
                old_amount = max(0.0, _float(old.get("amount_usd")))
                total_90 -= old_amount
                manufacturer_90[str(old.get("manufacturer_name") or "Unknown")] -= old_amount
            window_30.append(index)
            total_30 += amount
            window_90.append(index)
            total_90 += amount
            manufacturer = str(record.get("manufacturer_name") or "Unknown")
            manufacturer_90[manufacturer] += amount
            record["recipient_30d_count"] = len(window_30)
            record["recipient_30d_total"] = total_30
            record["manufacturer_90d_share"] = manufacturer_90[manufacturer] / total_90 if total_90 else 0.0

    matrix = np.array([
        [
            np.log1p(max(0.0, _float(record.get("amount_usd")))),
            np.log1p(max(0.0, _float(record.get("payment_count")))),
            np.log1p(record["recipient_30d_count"]),
            np.log1p(max(0.0, record["recipient_30d_total"])),
            record["manufacturer_90d_share"],
            max(0.0, _float(record.get("mismatch_score"))),
        ]
        for record in derived
    ], dtype=float)
    return matrix, derived


def _observations(record: dict[str, Any], medians: dict[str, float]) -> list[dict[str, Any]]:
    """Describe notable inputs; observations are deliberately not rule weights."""
    values = {
        "payment amount": _float(record.get("amount_usd")),
        "30-day recipient payment count": float(record["recipient_30d_count"]),
        "30-day recipient payment total": float(record["recipient_30d_total"]),
        "90-day manufacturer share": float(record["manufacturer_90d_share"]),
        "specialty mismatch score": _float(record.get("mismatch_score")),
    }
    ranked = sorted(
        values,
        key=lambda name: abs(values[name] - medians[name]) / max(abs(medians[name]), 0.01),
        reverse=True,
    )[:2]
    observations = []
    for name in ranked:
        value, median = values[name], medians[name]
        if "share" in name or "score" in name:
            value_text, median_text = f"{value:.0%}", f"{median:.0%}"
        elif "amount" in name or "total" in name:
            value_text, median_text = f"${value:,.2f}", f"${median:,.2f}"
        else:
            value_text, median_text = f"{value:.0f}", f"{median:.0f}"
        observations.append({
            "code": f"model_input_{name.replace('-', '_').replace(' ', '_')}",
            "weight": 0,
            "title": f"Model input: {name}",
            "plain_explanation": f"This record's value is {value_text}; the current-dataset median is {median_text}.",
            "evidence": {"value": value, "dataset_median": median, "feature": name},
        })
    return observations


def score_payments(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fit vanilla Isolation Forest and return one explainable result per row."""
    if not records:
        return []
    matrix, derived = _feature_rows(records)
    medians = {
        "payment amount": float(np.median([_float(row.get("amount_usd")) for row in derived])),
        "30-day recipient payment count": float(np.median([row["recipient_30d_count"] for row in derived])),
        "30-day recipient payment total": float(np.median([row["recipient_30d_total"] for row in derived])),
        "90-day manufacturer share": float(np.median([row["manufacturer_90d_share"] for row in derived])),
        "specialty mismatch score": float(np.median([_float(row.get("mismatch_score")) for row in derived])),
    }
    if len(records) < MIN_TRAINING_RECORDS:
        return [{
            "model_version": MODEL_VERSION, "risk_score": 0, "risk_level": "low",
            "review_recommended": False,
            "plain_language_explanation": f"Isolation Forest needs at least {MIN_TRAINING_RECORDS} retained CMS payment records to make a reliable comparison. This dataset currently has {len(records)}.",
            "signals": [],
            "model_metadata": {"training_records": len(records), "status": "insufficient_training_data", "feature_names": FEATURE_NAMES},
        } for _ in records]

    model = IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=42, n_jobs=-1)
    predictions = model.fit_predict(matrix)
    raw_anomaly = -model.score_samples(matrix)
    percentiles = np.array([np.mean(raw_anomaly <= value) * 100 for value in raw_anomaly])
    assessments: list[dict[str, Any]] = []
    for index, record in enumerate(derived):
        is_outlier = bool(predictions[index] == -1)
        percentile = round(float(percentiles[index]), 1)
        score = round(percentile) if is_outlier else 0
        level = "high_priority_review" if is_outlier and percentile >= 90 else "review" if is_outlier else "low"
        observations = _observations(record, medians) if is_outlier else []
        if is_outlier:
            explanation = (
                f"Isolation Forest marked this payment as unusual among {len(records)} currently retained CMS payments "
                f"(anomaly percentile {percentile:.0f}). The model compared payment amount, included payment count, "
                "30-day recipient activity, 30-day recipient dollars, 90-day manufacturer concentration, and the available specialty-mismatch score. "
                "The observations below describe model inputs; they are not individual causes of the prediction."
            )
        else:
            explanation = f"Isolation Forest did not mark this payment as unusual relative to the {len(records)} currently retained CMS payments."
        assessments.append({
            "model_version": MODEL_VERSION, "risk_score": score, "risk_level": level,
            "review_recommended": is_outlier,
            "plain_language_explanation": f"{explanation} This is a triage result and does not determine fraud or wrongdoing.",
            "signals": observations,
            "model_metadata": {
                "training_records": len(records), "status": "trained", "feature_names": FEATURE_NAMES,
                "contamination": CONTAMINATION,
                "raw_anomaly_score": round(float(raw_anomaly[index]), 6), "anomaly_percentile": percentile,
                "isolation_forest_prediction": "outlier" if is_outlier else "inlier",
            },
        })
    return assessments


PAYMENT_FEATURE_PROJECTION = {
    "_id": 0, "raw_cms_record_id": 1, "payment_date": 1, "recipient_npi": 1,
    "recipient_specialty": 1, "manufacturer_name": 1, "product_name": 1,
    "payment_type": 1, "payment_count": 1, "amount_usd": 1, "mismatch_score": 1,
}


async def _load_payment(db: AsyncIOMotorDatabase, record_id: str, payment_date: Any) -> dict[str, Any] | None:
    row = await db["cms_payments"].find_one(payment_day_filter(record_id, payment_date), PAYMENT_FEATURE_PROJECTION)
    return from_bson(row) if row else None


async def _load_all_payments(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    cursor = db["cms_payments"].find({}, {**PAYMENT_FEATURE_PROJECTION, "_id": 1}).sort([("payment_date", 1), ("raw_cms_record_id", 1)])
    return [from_bson(row) for row in await cursor.to_list(length=None)]


def _assessment_document(payment: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    """One ``risk_assessments`` document with its signals embedded."""
    return RiskAssessment(
        raw_cms_record_id=payment["raw_cms_record_id"],
        payment_date=payment["payment_date"],
        risk_score=assessment["risk_score"],
        risk_level=assessment["risk_level"],
        review_recommended=assessment["review_recommended"],
        model_version=MODEL_VERSION,
        plain_language_explanation=assessment["plain_language_explanation"],
        evidence={"model": assessment["model_metadata"], "observations": assessment["signals"]},
        risk_signals=[RiskSignal(**observation) for observation in assessment["signals"]],
        is_current=True,
    ).model_dump(by_alias=True, exclude={"id", "revision_id"}, exclude_none=False)


async def run_isolation_forest_triage(
    db: AsyncIOMotorDatabase,
    invalidated_by_ingestion_run_id: Any = None,
) -> dict[str, int | str]:
    """Fit the model to the current dataset and persist its complete batch output."""
    import asyncio
    from datetime import datetime, timezone

    payments = await _load_all_payments(db)
    # score_payments trains a scikit-learn IsolationForest — pure CPU work.
    # Offload to a thread pool so other API requests can proceed meanwhile.
    loop = asyncio.get_running_loop()
    assessments = await loop.run_in_executor(None, score_payments, payments)
    # Retire the previous batch (kept for audit) only once the new one is scored.
    collection = db["risk_assessments"]
    invalidation: dict[str, Any] = {"is_current": False, "invalidated_at": datetime.now(timezone.utc)}
    if invalidated_by_ingestion_run_id is not None:
        invalidation["invalidated_by_ingestion_run_id"] = invalidated_by_ingestion_run_id
    invalidated = await collection.update_many({"is_current": True}, {"$set": invalidation})
    documents = [
        _assessment_document(payment, assessment)
        for payment, assessment in zip(payments, assessments, strict=True)
    ]
    if documents:
        await collection.insert_many(documents, ordered=False)
        # Embed the current score on each payment so queue reads need no join.
        await db["cms_payments"].bulk_write([
            UpdateOne(
                {"_id": payment["_id"]},
                {"$set": {"current_risk_score": assessment["risk_score"], "current_risk_model_version": MODEL_VERSION}},
            )
            for payment, assessment in zip(payments, assessments, strict=True)
        ], ordered=False)
    return {
        "records_scored": len(assessments),
        "records_flagged": sum(item["review_recommended"] for item in assessments),
        "records_invalidated": invalidated.modified_count,
        "model_version": MODEL_VERSION,
    }


async def assess_payment(db: AsyncIOMotorDatabase, record_id: str, payment_date: Any) -> dict[str, Any] | None:
    """Read the current batch result; build the batch if no current result exists."""
    payment = await _load_payment(db, record_id, payment_date)
    if payment is None:
        return None
    current = await get_current_assessment(db, record_id, payment_date)
    if current is None:
        await run_isolation_forest_triage(db)
        current = await get_current_assessment(db, record_id, payment_date)
    return {**current, "payment": payment} if current else None


async def get_current_assessment(db: AsyncIOMotorDatabase, record_id: str, payment_date: Any) -> dict[str, Any] | None:
    """Retrieve the current model result; stale history is never returned."""
    row = await db["risk_assessments"].find_one(
        {**payment_day_filter(record_id, payment_date), "is_current": True, "model_version": MODEL_VERSION},
        sort=[("assessed_at", -1)],
    )
    if row is None:
        return None
    evidence = row.get("evidence") or {}
    return {
        "assessment_id": str(row["_id"]), "risk_score": row["risk_score"],
        "risk_level": row["risk_level"], "review_recommended": row["review_recommended"],
        "model_version": row["model_version"],
        "plain_language_explanation": row["plain_language_explanation"],
        "signals": evidence.get("observations", []), "model_metadata": evidence.get("model", {}),
        "assessed_at": row["assessed_at"],
    }
