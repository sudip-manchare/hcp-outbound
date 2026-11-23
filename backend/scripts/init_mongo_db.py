"""Create HCP Outbound collections and indexes in MongoDB Atlas.

Run once for a new database, from backend/:
    python -m scripts.init_mongo_db

Creates every application collection, the beanie-declared indexes (including
the unique CMS source identity and the audit-token TTL index), and the Atlas
Vector Search index on ``cms_payments.product_embedding`` (384 dims, cosine).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from app.core.database import close_db, init_db
from app.models.documents import DOCUMENT_MODELS, PAYMENT_VECTOR_INDEX, CmsPayment
from app.services.vector_mismatch_service import VECTOR_INDEX_DEFINITION


async def ensure_collections(db: AsyncIOMotorDatabase) -> list[str]:
    existing = set(await db.list_collection_names())
    names = [model.Settings.name for model in DOCUMENT_MODELS]
    for name in names:
        if name not in existing:
            await db.create_collection(name)
    return names


async def ensure_vector_index(db: AsyncIOMotorDatabase, *, wait_seconds: int = 180) -> str:
    """Create the Atlas Vector Search index if missing and wait until queryable."""
    collection = db[CmsPayment.Settings.name]
    indexes = {index["name"]: index async for index in collection.list_search_indexes()}
    if PAYMENT_VECTOR_INDEX not in indexes:
        await collection.create_search_index(SearchIndexModel(
            definition=VECTOR_INDEX_DEFINITION, name=PAYMENT_VECTOR_INDEX, type="vectorSearch",
        ))
    elif indexes[PAYMENT_VECTOR_INDEX].get("latestDefinition") != VECTOR_INDEX_DEFINITION:
        await collection.update_search_index(PAYMENT_VECTOR_INDEX, VECTOR_INDEX_DEFINITION)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        async for index in collection.list_search_indexes(PAYMENT_VECTOR_INDEX):
            if index.get("queryable") and index.get("status") == "READY":
                return "ready"
        await asyncio.sleep(5)
    return "building"


async def init_mongo(db: AsyncIOMotorDatabase | None = None) -> dict:
    db = db if db is not None else await init_db()
    collections = await ensure_collections(db)
    try:
        vector_index = await ensure_vector_index(db)
    except OperationFailure as exc:
        # Atlas Vector Search is unavailable on self-hosted MongoDB.
        vector_index = f"unavailable: {exc.details.get('errmsg', exc) if exc.details else exc}"
    indexes = {name: sorted(await db[name].index_information()) for name in collections}
    return {
        "database": db.name,
        "collections": collections,
        "indexes": indexes,
        "vector_search_index": {PAYMENT_VECTOR_INDEX: vector_index},
    }


async def main() -> None:
    try:
        print(json.dumps(await init_mongo(), indent=2))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
