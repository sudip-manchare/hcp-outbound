"""Route-contract tests for every public FastAPI endpoint.

External CMS/NPPES calls and the database repository are replaced at the
application boundary.  This exercises routing, request validation, status
codes, and error translation without requiring a live public service or a
developer's MongoDB Atlas cluster.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.services.cms_open_payments_service import CMSOpenPaymentsServiceError
from app.services.nppes_service import NPPESProviderNotFoundError


@pytest.fixture
def client():
    async def test_db():
        yield object()

    main.app.dependency_overrides[main.get_db] = test_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def payment() -> dict:
    return {
        "raw_cms_record_id": "cms-record-1",
        "payment_date": "2025-07-24",
        "recipient_npi": "1234567890",
        "manufacturer_name": "Example Co",
        "amount_usd": "47.96",
        "is_reviewed": False,
        "mismatch_score": None,
    }


def assessment() -> dict:
    return {
        "assessment_id": 7,
        "risk_score": 35,
        "risk_level": "review",
        "review_recommended": True,
        "plain_language_explanation": "A reviewer should compare the source entries.",
        "signals": [],
    }


def test_health_exposes_configured_source_metadata(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["sources"]["nppes"]


def test_enrich_doctor_validates_and_translates_not_found(client, monkeypatch):
    main.fetch_provider = AsyncMock(return_value={"npi": "1234567890", "source": {"name": "NPPES"}})

    assert client.get("/api/doctors/enrich/not-an-npi").status_code == 422
    response = client.get("/api/doctors/enrich/1234567890")
    assert response.status_code == 200
    assert response.json()["npi"] == "1234567890"

    main.fetch_provider = AsyncMock(side_effect=NPPESProviderNotFoundError("missing"))
    assert client.get("/api/doctors/enrich/1234567890").status_code == 404


def test_health_reports_mongodb_backed_cms_and_live_nppes(client):
    sources = client.get("/health").json()["sources"]

    assert sources["cms_open_payments"]["mode"] == "mongodb"
    assert sources["cms_open_payments"]["collection"] == "cms_payments"
    assert sources["nppes"]["mode"] == "live_api"


def test_cms_payments_feed_reads_mongodb_and_never_calls_live_cms(client, monkeypatch):
    live_cms = AsyncMock(side_effect=AssertionError("live CMS API must not be called"))
    monkeypatch.setattr(
        "app.services.cms_open_payments_service.fetch_payments_page", live_cms, raising=True,
    )
    main.query_cms_payments_page = AsyncMock(return_value={"payments": [], "pagination": {"next_offset": None}})

    response = client.get("/api/payments?limit=10&offset=4&recipient_state=oh&payment_nature=Food")
    assert response.status_code == 200
    assert main.query_cms_payments_page.await_args.kwargs == {
        "limit": 10, "offset": 4, "recipient_state": "oh", "manufacturer_id": None,
        "payment_nature": "Food", "recipient_type": None,
    }
    assert not hasattr(main, "fetch_payments_page")
    live_cms.assert_not_awaited()


def test_cms_ingestion_validates_input_and_returns_created_result(client):
    main.ingest_cms_page = AsyncMock(return_value={"run_id": 42, "records_inserted": 3})

    assert client.post("/api/ingestions/cms", json={"limit": 101}).status_code == 422
    response = client.post("/api/ingestions/cms", json={"limit": 20, "offset": 5, "recipient_state": "OH"})

    assert response.status_code == 201
    assert response.json()["run_id"] == 42
    assert main.ingest_cms_page.await_args.kwargs == {
        "limit": 20, "offset": 5, "recipient_state": "OH", "manufacturer_id": None,
        "payment_nature": None, "recipient_type": None,
    }

    main.ingest_cms_page = AsyncMock(side_effect=CMSOpenPaymentsServiceError("down"))
    assert client.post("/api/ingestions/cms", json={"limit": 20}).status_code == 502


def test_stored_payment_collection_and_detail_routes(client):
    main.list_payments = AsyncMock(return_value={"records": [payment()], "pagination": {"total_records": 1}})
    main.get_payment = AsyncMock(return_value=payment())

    listing = client.get("/api/stored-payments?limit=10&offset=2&recipient_state=OH")
    detail = client.get("/api/stored-payments/cms-record-1?payment_date=2025-07-24")

    assert listing.status_code == 200
    assert listing.json()["records"][0]["raw_cms_record_id"] == "cms-record-1"
    assert main.list_payments.await_args.kwargs == {"limit": 10, "offset": 2, "recipient_state": "OH"}
    assert detail.status_code == 200
    assert main.get_payment.await_args.args[1:] == ("cms-record-1", __import__("datetime").date(2025, 7, 24))

    main.get_payment = AsyncMock(return_value=None)
    assert client.get("/api/stored-payments/missing?payment_date=2025-07-24").status_code == 404


def test_risk_triage_create_and_read_routes(client, monkeypatch):
    explanation = {"status": "generated", "analysis": {"summary": "Review the source documentation."}}
    generator = AsyncMock(return_value=explanation)
    monkeypatch.setattr(main, "explain_assessment", generator)
    main.assess_payment = AsyncMock(return_value=assessment())
    main.get_current_assessment = AsyncMock(return_value=assessment())

    created = client.post("/api/stored-payments/cms-1/risk-triage?payment_date=2025-07-24")
    current = client.get("/api/stored-payments/cms-1/risk-triage?payment_date=2025-07-24")

    assert created.status_code == 201
    assert created.json()["assessment_id"] == 7
    assert created.json()["ai_explanation"] == explanation
    generator.assert_awaited_once_with(assessment())
    assert current.status_code == 200
    assert current.json()["risk_level"] == "review"
    assert "ai_explanation" not in current.json()

    main.get_current_assessment = AsyncMock(return_value=None)
    assert client.get("/api/stored-payments/cms-1/risk-triage?payment_date=2025-07-24").status_code == 404


def test_stored_payment_patch_forwards_only_mutable_fields(client):
    main.update_local_review = AsyncMock(return_value={**payment(), "is_reviewed": True, "mismatch_score": 0.4})

    response = client.patch(
        "/api/stored-payments/cms-1?payment_date=2025-07-24",
        json={"is_reviewed": True, "mismatch_score": 0.4},
    )
    assert response.status_code == 200
    assert response.json()["is_reviewed"] is True
    assert main.update_local_review.await_args.kwargs["is_reviewed"] is True
    assert main.update_local_review.await_args.kwargs["mismatch_score"] == 0.4

    main.update_local_review = AsyncMock(side_effect=ValueError("Provide is_reviewed and/or mismatch_score."))
    assert client.patch("/api/stored-payments/cms-1?payment_date=2025-07-24", json={}).status_code == 422


def test_stored_payment_delete_returns_no_content_or_not_found(client):
    main.delete_payment = AsyncMock(return_value=True)
    assert client.delete("/api/stored-payments/cms-1?payment_date=2025-07-24").status_code == 204

    main.delete_payment = AsyncMock(return_value=False)
    assert client.delete("/api/stored-payments/cms-1?payment_date=2025-07-24").status_code == 404


def test_review_queue_returns_repository_response(client):
    main.list_review_queue = AsyncMock(return_value={"physicians": [], "total": 0, "db_metrics": {}})

    response = client.get("/api/doctors")
    assert response.status_code == 200
    assert response.json()["total"] == 0
