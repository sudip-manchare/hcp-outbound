import asyncio
import json
from decimal import Decimal
from pathlib import Path

import httpx

from app.services.cms_open_payments_service import fetch_payments_page
from app.services.nppes_service import fetch_provider


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://test")


def test_nppes_response_is_normalized_from_the_official_shape():
    payload = {
        "result_count": 1,
        "results": [{
            "number": "1972093250", "enumeration_type": "NPI-1",
            "basic": {"first_name": "WILLIAM", "last_name": "ZUKE", "credential": "MD", "status": "A"},
            "addresses": [{"address_purpose": "LOCATION", "city": "KALAMAZOO", "state": "MI"}],
            "taxonomies": [{"code": "207XS0114X", "desc": "Orthopaedic Surgery", "primary": True}],
        }],
    }

    async def run():
        async with _client(lambda request: httpx.Response(200, json=payload)) as client:
            return await fetch_provider("1972093250", client)

    provider = asyncio.run(run())
    assert provider["npi"] == "1972093250"
    assert provider["primary_taxonomy"]["code"] == "207XS0114X"
    assert provider["practice_location"]["city"] == "KALAMAZOO"


def test_cms_request_paginates_without_an_npi_filter_and_normalizes_payment():
    payload = {"count": 1, "results": [{
        "record_id": "1", "covered_recipient_npi": "1659344299", "program_year": "2025",
        "total_amount_of_payment_usdollars": "47.96", "date_of_payment": "07/24/2025",
        "number_of_payments_included_in_total_amount": "1",
        "applicable_manufacturer_or_applicable_gpo_making_payment_name": "Example Co",
        "name_of_drug_or_biological_or_device_or_medical_supply_1": "Example Device",
    }]}
    seen_url = []

    def handler(request):
        seen_url.append(str(request.url))
        return httpx.Response(200, json=payload)

    async def run():
        async with _client(handler) as client:
            return await fetch_payments_page(limit=2, offset=4, recipient_state="oh", client=client)

    result = asyncio.run(run())
    assert "covered_recipient_npi" not in seen_url[0]
    assert "offset=4" in seen_url[0]
    assert "recipient_state" in seen_url[0]
    assert result["payments"][0]["amount_usd"] == Decimal("47.96")
    assert result["payments"][0]["products"] == ["Example Device"]
    assert result["payments"][0]["recipient"]["npi"] == "1659344299"
    assert result["pagination"]["next_offset"] is None


def test_nppes_sample_is_valid_json_and_matches_the_normalized_contract():
    sample = json.loads((Path(__file__).parents[1] / "samples" / "nppes_normalized_provider.sample.json").read_text())
    assert sample["npi"] == "1972093250"
    assert sample["primary_taxonomy"]["code"]
    assert sample["source"]["name"] == "NPPES NPI Registry"
