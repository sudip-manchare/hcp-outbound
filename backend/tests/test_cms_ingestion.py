"""MongoDB persistence tests using an in-memory motor stand-in (mongomock-motor)."""

from datetime import date, datetime, timezone
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core import database
from app.models.documents import AuditToken, CmsPayment
from app.services import cms_payment_repository as repository
from app.services import risk_triage_service as triage
from app.services.embedding_service import embed_text
from app.services.vector_mismatch_service import mismatch_from_neighbours, vector_search_pipeline
from scripts import ingest_cms_open_payments as cli

SOURCE = {"name": "CMS Open Payments", "url": "https://example.test/api", "dataset_id": "cms", "program_year": 2025}


def raw_record(index: int, **overrides) -> dict:
    return {
        "record_id": f"cms-{index}",
        "covered_recipient_npi": f"16593442{index % 100:02d}",
        "covered_recipient_type": "Covered Recipient Physician",
        "covered_recipient_first_name": "ROBERT",
        "covered_recipient_last_name": "DURICK",
        "covered_recipient_specialty_1": "Allopathic & Osteopathic Physicians|Orthopaedic Surgery",
        "recipient_state": "OH",
        "date_of_payment": f"07/{index % 28 + 1:02d}/2025",
        "total_amount_of_payment_usdollars": f"{47.96 + index}",
        "number_of_payments_included_in_total_amount": "1",
        "applicable_manufacturer_or_applicable_gpo_making_payment_name": "Example Co",
        "applicable_manufacturer_or_applicable_gpo_making_payment_id": "100000000001",
        "nature_of_payment_or_transfer_of_value": "Food and Beverage",
        "name_of_drug_or_biological_or_device_or_medical_supply_1": "Example Device",
        "program_year": "2025",
        **overrides,
    }


def page(records: list[dict], offset: int = 0, total: int | None = None) -> dict:
    total = len(records) if total is None else total
    return {
        "source": SOURCE, "filters": {},
        "pagination": {
            "limit": 100, "offset": offset, "total_matching_records": total,
            "returned_records": len(records),
            "next_offset": offset + len(records) if offset + len(records) < total else None,
        },
        "records": records,
    }


@pytest.fixture
def db():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mongo = loop.run_until_complete(database.init_db(AsyncMongoMockClient(tz_aware=True), "hcp_outbound_test"))
    yield SimpleNamespace(db=mongo, run=loop.run_until_complete)
    loop.run_until_complete(database.close_db())
    loop.close()


def test_payment_document_preserves_generic_recipient_raw_record_and_embedding():
    document = repository.payment_document(raw_record(1, date_of_payment="07/24/2025"), SOURCE, "run-7")

    assert document["recipient_npi"] == "1659344201"
    assert document["payment_date"] == datetime(2025, 7, 24, tzinfo=timezone.utc)
    assert document["product_name"] == "Example Device"
    assert document["raw_cms_record_id"] == "cms-1"
    assert document["raw_cms_payload"]["record_id"] == "cms-1"
    assert document["ingestion_run_id"] == "run-7"
    assert len(document["product_embedding"]) == 384


def test_embeddings_are_384_dim_unit_vectors_and_empty_text_has_none():
    vector = embed_text("Example Device Food and Beverage")
    assert len(vector) == 384
    assert sum(value * value for value in vector) == pytest.approx(1.0, abs=1e-4)
    assert embed_text("") is None


def test_unique_source_identity_upsert_skips_duplicates(db):
    collection = db.db[CmsPayment.Settings.name]
    documents = [repository.payment_document(raw_record(index), SOURCE, None) for index in range(3)]

    assert db.run(repository.upsert_payments(collection, documents)) == 3
    changed = {**documents[0], "manufacturer_name": "Changed Co"}
    assert db.run(repository.upsert_payments(collection, [changed])) == 0
    assert db.run(collection.count_documents({})) == 3
    stored = db.run(collection.find_one({"raw_cms_record_id": "cms-0"}))
    assert stored["manufacturer_name"] == "Example Co"  # CMS source fields are immutable


def test_indexes_include_unique_source_identity_and_audit_token_ttl(db):
    payments = db.run(db.db[CmsPayment.Settings.name].index_information())
    tokens = db.run(db.db[AuditToken.Settings.name].index_information())

    assert payments["uq_cms_payments_source_record"]["unique"] is True
    assert list(payments["uq_cms_payments_source_record"]["key"]) == [("raw_cms_record_id", 1), ("payment_date", 1)]
    assert tokens["ttl_audit_tokens_expires_at"]["expireAfterSeconds"] == 0


def test_payments_feed_is_served_from_mongodb_with_filters_and_count(db):
    collection = db.db[CmsPayment.Settings.name]
    records = [raw_record(index) for index in range(5)] + [
        raw_record(10, recipient_state="CA"),
        raw_record(11, nature_of_payment_or_transfer_of_value="Consulting Fee"),
    ]
    db.run(repository.upsert_payments(collection, [repository.payment_document(r, SOURCE, None) for r in records]))

    result = db.run(repository.query_cms_payments_page(
        db.db, limit=2, offset=1, recipient_state="oh", payment_nature="Food and Beverage",
        manufacturer_id="100000000001", recipient_type="Covered Recipient Physician",
    ))

    assert result["source"]["served_from"] == "mongodb"
    assert result["filters"] == {
        "recipient_state": "OH", "manufacturer_id": "100000000001",
        "payment_nature": "Food and Beverage", "recipient_type": "Covered Recipient Physician",
    }
    assert result["pagination"] == {
        "limit": 2, "offset": 1, "total_matching_records": 5, "returned_records": 2, "next_offset": 3,
    }
    assert [payment["record_id"] for payment in result["payments"]] == ["cms-1", "cms-2"]
    assert result["payments"][0]["recipient"]["state"] == "OH"


def test_review_queue_joins_current_risk_assessment_and_reports_db_metrics(db):
    collection = db.db[CmsPayment.Settings.name]
    db.run(repository.upsert_payments(collection, [
        repository.payment_document(raw_record(index), SOURCE, None) for index in range(25)
    ] + [repository.payment_document(raw_record(99, total_amount_of_payment_usdollars="500000"), SOURCE, None)]))

    scored = db.run(triage.run_isolation_forest_triage(db.db))
    queue = db.run(repository.list_review_queue(db.db))
    current = db.run(triage.get_current_assessment(db.db, "cms-99", date(2025, 7, 16)))

    assert scored["records_scored"] == 26
    assert "tiger_data_metrics" not in queue
    assert queue["db_metrics"]["engine"] == "mongodb_atlas"
    assert queue["db_metrics"]["total_payments"] == 26
    assert queue["db_metrics"]["query_ms"] >= 0
    flagged = [p for physician in queue["physicians"] for p in physician["payments"] if p["id"] == "cms-99"]
    assert flagged[0]["risk_score"] == current["risk_score"] > 0
    stored = db.run(db.db["risk_assessments"].find_one({"raw_cms_record_id": "cms-99", "is_current": True}))
    assert stored["risk_signals"] and stored["risk_signals"][0]["code"].startswith("model_input_")

    db.run(triage.run_isolation_forest_triage(db.db))
    assert db.run(db.db["risk_assessments"].count_documents({"is_current": True})) == 26
    assert db.run(db.db["risk_assessments"].count_documents({"is_current": False})) == 26


def test_local_review_update_and_delete_match_calendar_payment_date(db):
    collection = db.db[CmsPayment.Settings.name]
    db.run(repository.upsert_payments(collection, [repository.payment_document(raw_record(3), SOURCE, None)]))

    updated = db.run(repository.update_local_review(
        db.db, record_id="cms-3", payment_date=date(2025, 7, 4), is_reviewed=True, mismatch_score=0.4,
    ))
    assert updated["is_reviewed"] is True and updated["mismatch_score"] == 0.4
    assert db.run(repository.get_payment(db.db, "cms-3", date(2025, 7, 5))) is None
    assert db.run(repository.delete_payment(db.db, "cms-3", date(2025, 7, 4))) is True
    assert db.run(repository.delete_payment(db.db, "cms-3", date(2025, 7, 4))) is False


def test_vector_search_pipeline_and_mismatch_weighting():
    stage = vector_search_pipeline([0.1] * 384)[0]["$vectorSearch"]
    assert stage["index"] == "cms_payments_product_embedding"
    assert stage["path"] == "product_embedding"

    payment = {"_id": 1, "recipient_specialty": "Cardiology"}
    neighbours = [
        {"_id": 1, "recipient_specialty": "Cardiology", "score": 1.0},
        {"_id": 2, "recipient_specialty": "Cardiology", "score": 0.9},
        {"_id": 3, "recipient_specialty": "Orthopaedics", "score": 0.9},
        {"_id": 4, "recipient_specialty": "Dermatology", "score": 0.5},  # not similar enough
    ]
    assert mismatch_from_neighbours(payment, neighbours) == 0.5
    assert mismatch_from_neighbours(payment, neighbours[:1]) is None


@pytest.mark.parametrize("scoring_fails", [False, True])
def test_cli_defaults_to_ten_pages_and_scores_before_reporting_success(db, monkeypatch, capsys, scoring_fails):
    args = cli.parse_args([])
    assert (args.pages, args.page_size) == (10, 100)

    pages = [page([raw_record(offset + index) for index in range(2)], offset=offset, total=20)
             for offset in range(0, 20, 2)]
    fetch = AsyncMock(side_effect=pages)
    monkeypatch.setattr(cli, "fetch_raw_payments_page", fetch)
    monkeypatch.setattr(cli, "init_mongo", AsyncMock())

    async def score(mongo):
        assert await mongo[CmsPayment.Settings.name].count_documents({}) == 20
        if scoring_fails:
            raise RuntimeError("scoring failed")
        return {"records_scored": 20, "records_flagged": 1, "model_version": "isolation-forest-v2",
                "mismatch_scoring": {"status": "scored"}}

    monkeypatch.setattr(cli, "score_retained_payments", AsyncMock(side_effect=score))
    args = SimpleNamespace(reset=True, page_size=2, start_offset=0, recipient_state=None, pages=10)
    runs = db.db["cms_ingestion_runs"]
    if scoring_fails:
        with pytest.raises(RuntimeError, match="scoring failed"):
            db.run(cli.ingest(args, db.db))
        run = db.run(runs.find_one({}))
        assert (run["status"], run["error_message"]) == ("failed", "scoring failed")
    else:
        result = db.run(cli.ingest(args, db.db))
        assert '"risk_assessments_flagged": 1' in capsys.readouterr().out
        assert (result["records_seen"], result["records_inserted"], result["pages"]) == (20, 20, 10)
        assert db.run(runs.find_one({}))["status"] == "completed"
    assert fetch.await_count == 10
