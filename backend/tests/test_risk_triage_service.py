from datetime import datetime, timedelta, timezone

from app.services.risk_triage_service import CONTAMINATION, MIN_TRAINING_RECORDS, MODEL_VERSION, score_payments


def _record(index: int, amount: float = 20.0) -> dict:
    return {
        "raw_cms_record_id": f"cms-{index}",
        "payment_date": datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        "recipient_npi": f"1234567{index % 10:03d}", "manufacturer_name": "Acme Pharma",
        "amount_usd": amount, "payment_count": 1, "mismatch_score": 0.02,
    }


def test_isolation_forest_flags_an_extreme_payment_and_keeps_explanation_grounded():
    records = [_record(index) for index in range(MIN_TRAINING_RECORDS + 5)]
    records[-1] = _record(999, amount=500_000.0)

    results = score_payments(records)
    extreme = results[-1]

    assert extreme["model_version"] == MODEL_VERSION
    assert extreme["review_recommended"] is True
    assert extreme["risk_score"] > 0
    assert extreme["model_metadata"]["isolation_forest_prediction"] == "outlier"
    assert extreme["signals"]
    assert "does not determine fraud" in extreme["plain_language_explanation"]


def test_isolation_forest_waits_for_a_usable_dataset_instead_of_fabricating_flags():
    results = score_payments([_record(index) for index in range(MIN_TRAINING_RECORDS - 1)])

    assert len(results) == MIN_TRAINING_RECORDS - 1
    assert all(result["review_recommended"] is False for result in results)
    assert all(result["model_metadata"]["status"] == "insufficient_training_data" for result in results)


def test_isolation_forest_uses_a_bounded_review_queue_rate():
    records = [_record(index, amount=float(index + 1)) for index in range(100)]
    results = score_payments(records)

    assert CONTAMINATION == 0.05
    assert sum(result["review_recommended"] for result in results) == 5
