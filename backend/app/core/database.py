"""MongoDB (motor + beanie) connection management."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from beanie import init_beanie
from bson import Decimal128
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings
from app.models.documents import DOCUMENT_MODELS

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None
_init_lock = asyncio.Lock()


def create_client(uri: str | None = None) -> AsyncIOMotorClient:
    # tz_aware keeps every datetime read back from MongoDB in UTC.
    return AsyncIOMotorClient(uri or get_settings().MONGODB_URI, tz_aware=True)


async def init_db(
    client: AsyncIOMotorClient | None = None,
    db_name: str | None = None,
) -> AsyncIOMotorDatabase:
    """Connect once per process and register beanie models (creates indexes)."""
    global _client, _database
    async with _init_lock:
        if _database is None or client is not None:
            _client = client or create_client()
            _database = _client[db_name or get_settings().MONGODB_DB_NAME]
            await init_beanie(database=_database, document_models=DOCUMENT_MODELS)
    return _database


async def close_db() -> None:
    global _client, _database
    if _client is not None:
        _client.close()
    _client = _database = None


async def get_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    """FastAPI dependency yielding the initialized MongoDB database."""
    yield await init_db() if _database is None else _database


def from_bson(value: Any) -> Any:
    """Convert BSON-only scalars (Decimal128) returned by raw motor queries."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, dict):
        return {key: from_bson(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_bson(item) for item in value]
    return value


def to_decimal128(value: Any) -> Decimal128 | None:
    if value in (None, ""):
        return None
    return Decimal128(Decimal(str(value)))


def payment_day_filter(record_id: str, payment_date: date) -> dict[str, Any]:
    """Match a CMS source record on its calendar payment date (UTC)."""
    start = datetime.combine(payment_date, time.min, tzinfo=timezone.utc)
    return {"raw_cms_record_id": record_id, "payment_date": {"$gte": start, "$lt": start + timedelta(days=1)}}
