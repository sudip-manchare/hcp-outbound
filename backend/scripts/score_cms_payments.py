"""Backfill or refresh stored mismatch and Isolation Forest results without fetching CMS.

Run from backend/: python -m scripts.score_cms_payments
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.core.database import close_db, init_db
from app.models.documents import CmsPayment
from app.services.embedding_service import embed_text, payment_embedding_text
from app.services.risk_triage_service import run_isolation_forest_triage
from app.services.vector_mismatch_service import score_specialty_mismatch


async def embed_missing_payments(db: AsyncIOMotorDatabase) -> int:
    """Store 384-dim product embeddings for payments that do not have one yet."""
    collection = db[CmsPayment.Settings.name]
    rows = await collection.find(
        {"product_embedding": None}, {"_id": 1, "product_name": 1, "payment_type": 1},
    ).to_list(length=None)
    updates = [
        UpdateOne({"_id": row["_id"]}, {"$set": {"product_embedding": vector}})
        for row in rows
        if (vector := embed_text(payment_embedding_text(row.get("product_name"), row.get("payment_type"))))
    ]
    if updates:
        await collection.bulk_write(updates, ordered=False)
    return len(updates)


async def score_retained_payments(db: AsyncIOMotorDatabase) -> dict:
    embedded = await embed_missing_payments(db)
    mismatch = await score_specialty_mismatch(db)
    triage = await run_isolation_forest_triage(db)
    return {**triage, "payments_embedded": embedded, "mismatch_scoring": mismatch}


async def main() -> dict:
    try:
        return await score_retained_payments(await init_db())
    finally:
        await close_db()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main()), indent=2, default=str))
