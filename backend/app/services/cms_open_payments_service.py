"""Live client for CMS Open Payments' public datastore API."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import get_settings
class CMSOpenPaymentsServiceError(RuntimeError):
    """The CMS Open Payments API could not provide a usable response."""


def _as_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _product_names(record: dict[str, Any]) -> list[str]:
    return [
        value
        for key, value in record.items()
        if key.startswith("name_of_drug_or_biological_or_device_or_medical_supply_") and value
    ]


def normalize_payment(record: dict[str, Any], *, retrieved_at: datetime | None = None) -> dict[str, Any]:
    """Map the CMS datastore fields to a stable, product-facing payment contract."""
    return {
        "source": {
            "name": "CMS Open Payments",
            "url": "https://openpaymentsdata.cms.gov/api/1",
            "dataset_id": get_settings().CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID,
            "program_year": int(record.get("program_year") or get_settings().CMS_OPEN_PAYMENTS_PROGRAM_YEAR),
            "retrieved_at": (retrieved_at or datetime.now(timezone.utc)).isoformat(),
        },
        "record_id": record.get("record_id"),
        "recipient": {
            "npi": record.get("covered_recipient_npi") or None,
            "profile_id": record.get("covered_recipient_profile_id") or None,
            "type": record.get("covered_recipient_type"),
            "first_name": record.get("covered_recipient_first_name") or None,
            "middle_name": record.get("covered_recipient_middle_name") or None,
            "last_name": record.get("covered_recipient_last_name") or None,
            "primary_specialty": record.get("covered_recipient_specialty_1") or None,
            "city": record.get("recipient_city") or None,
            "state": record.get("recipient_state") or None,
            "zip_code": record.get("recipient_zip_code") or None,
        },
        "payment_date": record.get("date_of_payment"),
        "amount_usd": _as_decimal(record.get("total_amount_of_payment_usdollars")),
        "payment_count": int(record.get("number_of_payments_included_in_total_amount") or 1),
        "payment_form": record.get("form_of_payment_or_transfer_of_value"),
        "payment_nature": record.get("nature_of_payment_or_transfer_of_value"),
        "manufacturer": {
            "name": record.get("applicable_manufacturer_or_applicable_gpo_making_payment_name"),
            "id": record.get("applicable_manufacturer_or_applicable_gpo_making_payment_id"),
            "state": record.get("applicable_manufacturer_or_applicable_gpo_making_payment_state"),
            "country": record.get("applicable_manufacturer_or_applicable_gpo_making_payment_country"),
        },
        "products": _product_names(record),
        "publication": {
            "dispute_status_for_publication": record.get("dispute_status_for_publication"),
            "publication_date": record.get("payment_publication_date"),
            "delay_in_publication": record.get("delay_in_publication_indicator"),
            "change_type": record.get("change_type"),
        },
    }


async def fetch_payments_page(
    *,
    limit: int = 100,
    offset: int = 0,
    recipient_state: str | None = None,
    manufacturer_id: str | None = None,
    payment_nature: str | None = None,
    recipient_type: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Read a generic CMS General Payment page, without requiring an NPI.

    Every returned record includes a recipient NPI when CMS published one. The
    caller can then enrich only selected recipients with the NPPES API.
    """
    page = await fetch_raw_payments_page(
        limit=limit,
        offset=offset,
        recipient_state=recipient_state,
        manufacturer_id=manufacturer_id,
        payment_nature=payment_nature,
        recipient_type=recipient_type,
        client=client,
    )
    return {
        "source": page["source"],
        "filters": page["filters"],
        "pagination": page["pagination"],
        "payments": [normalize_payment(row) for row in page["records"]],
    }


async def fetch_raw_payments_page(
    *,
    limit: int = 100,
    offset: int = 0,
    recipient_state: str | None = None,
    manufacturer_id: str | None = None,
    payment_nature: str | None = None,
    recipient_type: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch one unmodified API page for the ingestion job.

    Keeping this function separate lets the API response stay normalized for
    the frontend while the database records retain the full source payload.
    """
    settings = get_settings()
    limit = max(1, min(limit, settings.CMS_OPEN_PAYMENTS_MAX_PAGE_SIZE))
    offset = max(0, offset)
    url = (
        f"{settings.CMS_OPEN_PAYMENTS_API_BASE_URL.rstrip('/')}/datastore/query/"
        f"{settings.CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID}/0"
    )
    params: list[tuple[str, str]] = [("limit", str(limit)), ("offset", str(offset))]
    filters = {
        "recipient_state": ("recipient_state", recipient_state.upper() if recipient_state else None),
        "manufacturer_id": ("applicable_manufacturer_or_applicable_gpo_making_payment_id", manufacturer_id),
        "payment_nature": ("nature_of_payment_or_transfer_of_value", payment_nature),
        "recipient_type": ("covered_recipient_type", recipient_type),
    }
    applied_filters: dict[str, str] = {}
    condition_index = 0
    for name, (property_name, value) in filters.items():
        if value is None:
            continue
        params.extend([
            (f"conditions[{condition_index}][property]", property_name),
            (f"conditions[{condition_index}][operator]", "="),
            (f"conditions[{condition_index}][value]", value),
        ])
        applied_filters[name] = value
        condition_index += 1

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CMSOpenPaymentsServiceError("CMS Open Payments API request failed.") from exc
    finally:
        if owns_client:
            await client.aclose()

    rows = payload.get("results") or []
    total = payload.get("count", len(rows))
    return {
        "source": {
            "name": "CMS Open Payments",
            "url": settings.CMS_OPEN_PAYMENTS_API_BASE_URL,
            "dataset_id": settings.CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID,
            "program_year": settings.CMS_OPEN_PAYMENTS_PROGRAM_YEAR,
        },
        "filters": applied_filters,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_matching_records": total,
            "returned_records": len(rows),
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
        },
        "records": rows,
    }
