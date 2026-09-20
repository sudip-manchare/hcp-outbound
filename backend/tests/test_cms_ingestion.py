from datetime import datetime, timezone
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import ingest_cms_open_payments as cli
from scripts import score_cms_payments as scoring_cli

from scripts.ingest_cms_open_payments import INSERT_PAYMENTS_SQL, parse_cms_date, payment_row


def test_payment_row_preserves_generic_recipient_and_raw_record():
    raw_record = {
        "record_id": "1157125489",
        "covered_recipient_npi": "1659344299",
        "covered_recipient_profile_id": "1235813",
        "covered_recipient_type": "Covered Recipient Physician",
        "covered_recipient_first_name": "ROBERT",
        "covered_recipient_last_name": "DURICK",
        "recipient_state": "OH",
        "date_of_payment": "07/24/2025",
        "total_amount_of_payment_usdollars": "47.96",
        "number_of_payments_included_in_total_amount": "1",
        "applicable_manufacturer_or_applicable_gpo_making_payment_name": "Example Co",
        "name_of_drug_or_biological_or_device_or_medical_supply_1": "Example Device",
        "program_year": "2025",
    }
    source = {"url": "https://example.test/api", "program_year": 2025}

    row = payment_row(raw_record, run_id=7, source=source)

    assert row[0] == "1659344299"
    assert row[10] == datetime(2025, 7, 24, tzinfo=timezone.utc)
    assert row[13] == "Example Device"
    assert row[25] == "1157125489"
    assert row[27] == 7


def test_parse_cms_date_handles_an_empty_source_value():
    assert parse_cms_date(None) is None


def test_ingestion_uses_the_cms_source_identity_to_skip_duplicates():
    assert "ON CONFLICT (raw_cms_record_id, payment_date) DO NOTHING" in INSERT_PAYMENTS_SQL


@pytest.mark.parametrize("scoring_fails", [False, True])
def test_cli_scores_retained_data_before_reporting_success(monkeypatch, capsys, scoring_fails):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (7,)
    monkeypatch.setattr(cli.psycopg2, "connect", lambda _: connection)
    monkeypatch.setattr(cli, "prepare_schema", lambda _: None)
    monkeypatch.setattr(cli, "fetch_raw_payments_page", AsyncMock(return_value={
        "source": {"dataset_id": "cms", "program_year": 2025, "url": "https://example.test"},
        "filters": {}, "pagination": {"next_offset": None}, "records": [],
    }))

    async def score(database_url):
        assert database_url == cli.DATABASE_URL_SYNC
        assert connection.commit.called
        assert not any("status = 'completed'" in call.args[0] for call in cursor.execute.call_args_list)
        if scoring_fails:
            raise RuntimeError("scoring failed")
        return {"records_scored": 201, "records_flagged": 10, "model_version": "isolation-forest-v2"}

    scoring = AsyncMock(side_effect=score)
    monkeypatch.setattr(cli, "score_retained_payments", scoring)
    args = SimpleNamespace(reset=False, page_size=100, start_offset=0, recipient_state=None, pages=1)
    if scoring_fails:
        with pytest.raises(RuntimeError, match="scoring failed"):
            asyncio.run(cli.ingest(args))
        assert not any("status = 'completed'" in call.args[0] for call in cursor.execute.call_args_list)
        assert cursor.execute.call_args.args[1] == ("scoring failed", 7)
    else:
        asyncio.run(cli.ingest(args))
        assert '"risk_assessments_flagged": 10' in capsys.readouterr().out
        assert any("status = 'completed'" in call.args[0] for call in cursor.execute.call_args_list)
    scoring.assert_awaited_once()
    connection.close.assert_called_once()


def test_backfill_converts_ssl_options_and_commits_batch_atomically(monkeypatch):
    engine = MagicMock()
    engine.dispose = AsyncMock()
    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr(scoring_cli, "create_async_engine", create_engine)
    session = MagicMock()
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    monkeypatch.setattr(scoring_cli, "AsyncSession", lambda _: session_context)
    scoring = AsyncMock(return_value={"records_scored": 201, "records_flagged": 10})
    monkeypatch.setattr(scoring_cli, "run_isolation_forest_triage", scoring)

    result = asyncio.run(scoring_cli.score_retained_payments(
        "postgresql://localhost/hcp_outbound?sslmode=require",
    ))

    url = create_engine.call_args.args[0]
    assert url.drivername == "postgresql+asyncpg"
    assert url.query == {"ssl": "require"}
    scoring.assert_awaited_once_with(session)
    session.begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)
    engine.dispose.assert_awaited_once()
    assert result["records_flagged"] == 10
