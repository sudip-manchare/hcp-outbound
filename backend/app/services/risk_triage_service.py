"""Batch anomaly triage using a vanilla scikit-learn Isolation Forest.

The model is fit only on the currently retained CMS payment dataset after an
ingestion. It identifies unusual numerical feature combinations; it never
determines that a payment is fraudulent. Stored observations expose the exact
model inputs so the UI can explain a flag without inventing causal claims.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
import json
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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


async def _load_payment(db: AsyncSession, record_id: str, payment_date: Any) -> dict[str, Any] | None:
    result = await db.execute(text("""
        SELECT raw_cms_record_id, payment_date, recipient_npi, recipient_specialty,
               manufacturer_name, product_name, payment_type, payment_count,
               amount_usd, mismatch_score
        FROM cms_payments
        WHERE raw_cms_record_id = :record_id AND payment_date::date = :payment_date
    """), {"record_id": record_id, "payment_date": payment_date})
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def _load_all_payments(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(text("""
        SELECT raw_cms_record_id, payment_date, recipient_npi, recipient_specialty,
               manufacturer_name, product_name, payment_type, payment_count,
               amount_usd, mismatch_score
        FROM cms_payments
        ORDER BY payment_date, raw_cms_record_id
    """))
    return [dict(row) for row in result.mappings()]


async def _store_assessment(db: AsyncSession, payment: dict[str, Any], assessment: dict[str, Any]) -> None:
    evidence = {"model": assessment["model_metadata"], "observations": assessment["signals"]}
    inserted = await db.execute(text("""
        INSERT INTO risk_assessments (
            raw_cms_record_id, payment_date, risk_score, risk_level, review_recommended,
            model_version, plain_language_explanation, evidence, is_current
        ) VALUES (
            :record_id, :payment_date, :risk_score, :risk_level, :review_recommended,
            :model_version, :plain_language_explanation, CAST(:evidence AS jsonb), TRUE
        ) RETURNING id
    """), {
        "record_id": payment["raw_cms_record_id"], "payment_date": payment["payment_date"],
        "risk_score": assessment["risk_score"], "risk_level": assessment["risk_level"],
        "review_recommended": assessment["review_recommended"], "model_version": MODEL_VERSION,
        "plain_language_explanation": assessment["plain_language_explanation"], "evidence": json.dumps(evidence),
    })
    assessment_id = inserted.scalar_one()
    for observation in assessment["signals"]:
        await db.execute(text("""
            INSERT INTO risk_signals (assessment_id, code, weight, title, plain_explanation, evidence)
            VALUES (:assessment_id, :code, :weight, :title, :plain_explanation, CAST(:evidence AS jsonb))
        """), {**observation, "assessment_id": assessment_id, "evidence": json.dumps(observation["evidence"])})


async def run_isolation_forest_triage(db: AsyncSession) -> dict[str, int | str]:
    """Fit the model to the current dataset and persist its complete batch output."""
    payments = await _load_all_payments(db)
    assessments = score_payments(payments)
    # Support an explicit re-run after a model-version change as well as the
    # normal ingestion lifecycle, which performs this invalidation first.
    await db.execute(text("""
        UPDATE risk_assessments
        SET is_current = FALSE, invalidated_at = NOW()
        WHERE is_current = TRUE
    """))
    for payment, assessment in zip(payments, assessments, strict=True):
        await _store_assessment(db, payment, assessment)
    return {
        "records_scored": len(assessments),
        "records_flagged": sum(item["review_recommended"] for item in assessments),
        "model_version": MODEL_VERSION,
    }


async def assess_payment(db: AsyncSession, record_id: str, payment_date: Any) -> dict[str, Any] | None:
    """Read the current batch result; build the batch if no current result exists."""
    payment = await _load_payment(db, record_id, payment_date)
    if payment is None:
        return None
    current = await get_current_assessment(db, record_id, payment_date)
    if current is None:
        await run_isolation_forest_triage(db)
        current = await get_current_assessment(db, record_id, payment_date)
    return {**current, "payment": payment} if current else None


async def get_current_assessment(db: AsyncSession, record_id: str, payment_date: Any) -> dict[str, Any] | None:
    """Retrieve the current model result; stale history is never returned."""
    result = await db.execute(text("""
        SELECT id, risk_score, risk_level, review_recommended, model_version,
               plain_language_explanation, evidence, assessed_at
        FROM risk_assessments
        WHERE raw_cms_record_id = :record_id
          AND payment_date::date = :payment_date
          AND is_current = TRUE
          AND model_version = :model_version
        ORDER BY assessed_at DESC
        LIMIT 1
    """), {"record_id": record_id, "payment_date": payment_date, "model_version": MODEL_VERSION})
    row = result.mappings().one_or_none()
    if row is None:
        return None
    evidence = row["evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    return {
        "assessment_id": row["id"], "risk_score": row["risk_score"],
        "risk_level": row["risk_level"], "review_recommended": row["review_recommended"],
        "model_version": row["model_version"],
        "plain_language_explanation": row["plain_language_explanation"],
        "signals": evidence.get("observations", []), "model_metadata": evidence.get("model", {}),
        "assessed_at": row["assessed_at"],
    }
