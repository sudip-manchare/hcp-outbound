"""Client and normalizer for the official NPPES NPI Registry API."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

import httpx

from app.core.config import get_settings


class NPPESServiceError(RuntimeError):
    """The NPPES service could not provide a usable provider record."""


class NPPESProviderNotFoundError(NPPESServiceError):
    """The official registry contains no record for the requested NPI."""


def validate_npi(npi: str) -> str:
    """Validate the public API's required 10 digit NPI format."""
    if not re.fullmatch(r"\d{10}", npi):
        raise ValueError("NPI must contain exactly 10 digits.")
    return npi


def _first_location(addresses: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (address for address in addresses if address.get("address_purpose") == "LOCATION"),
        addresses[0] if addresses else None,
    )


def _primary_taxonomy(taxonomies: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (taxonomy for taxonomy in taxonomies if taxonomy.get("primary") is True),
        taxonomies[0] if taxonomies else None,
    )


def normalize_provider(record: dict[str, Any], *, retrieved_at: datetime | None = None) -> dict[str, Any]:
    """Return the stable application shape, while retaining all public NPPES facts needed downstream."""
    basic = record.get("basic") or {}
    addresses = record.get("addresses") or []
    taxonomies = record.get("taxonomies") or []
    location = _first_location(addresses) or {}
    primary_taxonomy = _primary_taxonomy(taxonomies) or {}
    entity_type = record.get("enumeration_type")

    return {
        "source": {
            "name": "NPPES NPI Registry",
            "url": "https://npiregistry.cms.hhs.gov/api/",
            "api_version": get_settings().NPPES_API_VERSION,
            "retrieved_at": (retrieved_at or datetime.now(timezone.utc)).isoformat(),
        },
        "npi": record["number"],
        "entity_type": entity_type,
        "status": basic.get("status"),
        "legal_name": {
            "first_name": basic.get("first_name"),
            "middle_name": basic.get("middle_name"),
            "last_name": basic.get("last_name"),
            "name_prefix": basic.get("name_prefix"),
            "name_suffix": basic.get("name_suffix"),
            "credential": basic.get("credential"),
            "organization_name": basic.get("organization_name"),
        },
        "enumeration_date": basic.get("enumeration_date"),
        "last_updated": basic.get("last_updated"),
        "primary_taxonomy": {
            "code": primary_taxonomy.get("code"),
            "description": primary_taxonomy.get("desc"),
            "license": primary_taxonomy.get("license"),
            "license_state": primary_taxonomy.get("state"),
        },
        "practice_location": {
            "address_1": location.get("address_1"),
            "address_2": location.get("address_2"),
            "city": location.get("city"),
            "state": location.get("state"),
            "postal_code": location.get("postal_code"),
            "country_code": location.get("country_code"),
            "telephone_number": location.get("telephone_number"),
        },
        "taxonomies": [
            {
                "code": taxonomy.get("code"),
                "description": taxonomy.get("desc"),
                "primary": bool(taxonomy.get("primary")),
                "license": taxonomy.get("license"),
                "license_state": taxonomy.get("state"),
            }
            for taxonomy in taxonomies
        ],
    }


async def fetch_provider(npi: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Fetch a provider directly from NPPES; this function has no fixture fallback."""
    npi = validate_npi(npi)
    settings = get_settings()
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    try:
        response = await client.get(
            settings.NPPES_API_BASE_URL,
            params={"version": settings.NPPES_API_VERSION, "number": npi},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise NPPESServiceError("NPPES API request failed.") from exc
    finally:
        if owns_client:
            await client.aclose()

    payload = response.json()
    results = payload.get("results") or []
    if not results:
        raise NPPESProviderNotFoundError(f"No NPPES provider found for NPI {npi}.")
    return normalize_provider(results[0])
