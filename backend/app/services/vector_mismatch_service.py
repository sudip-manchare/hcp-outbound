"""Specialty-mismatch scores from Atlas Vector Search over product embeddings.

For each payment, ``$vectorSearch`` finds payments for similar products. The
mismatch score is the similarity-weighted share of those neighbours received
by a different recipient specialty: 0 means this specialty typically receives
payments for the product, 1 means it never does in the retained dataset.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne
from pymongo.errors import OperationFailure

from app.models.documents import EMBEDDING_DIM, PAYMENT_VECTOR_INDEX, CmsPayment

logger = logging.getLogger(__name__)

NEIGHBOURS = 10
NUM_CANDIDATES = 100
# Atlas cosine vectorSearchScore is (1 + cosine) / 2; 0.75 means cosine >= 0.5.
MIN_SIMILARITY_SCORE = 0.75
CONCURRENCY = 8

VECTOR_INDEX_DEFINITION = {
    "fields": [{
        "type": "vector",
        "path": "product_embedding",
        "numDimensions": EMBEDDING_DIM,
        "similarity": "cosine",
    }],
}


def vector_search_pipeline(query_vector: list[float]) -> list[dict[str, Any]]:
    return [
        {"$vectorSearch": {
            "index": PAYMENT_VECTOR_INDEX,
            "path": "product_embedding",
            "queryVector": query_vector,
            "numCandidates": NUM_CANDIDATES,
            "limit": NEIGHBOURS + 1,  # the payment itself is usually the top hit
        }},
        {"$project": {"_id": 1, "recipient_specialty": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]


def mismatch_from_neighbours(payment: dict[str, Any], neighbours: list[dict[str, Any]]) -> float | None:
    similar = [
        item for item in neighbours
        if item["_id"] != payment["_id"] and item.get("recipient_specialty")
        and item.get("score", 0) >= MIN_SIMILARITY_SCORE
    ]
    total = sum(item["score"] for item in similar)
    if not total:
        return None
    different = sum(item["score"] for item in similar if item["recipient_specialty"] != payment["recipient_specialty"])
    return round(different / total, 4)


async def score_specialty_mismatch(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """Recompute ``mismatch_score`` for every embedded payment with a specialty.

    Returns ``status="vector_index_unavailable"`` without changing data when
    the Atlas Vector Search index is missing (e.g. local MongoDB).
    """
    collection = db[CmsPayment.Settings.name]
    payments = await collection.find(
        {"product_embedding": {"$ne": None}, "recipient_specialty": {"$ne": None}},
        {"_id": 1, "recipient_specialty": 1, "product_embedding": 1},
    ).to_list(length=None)
    if not payments:
        return {"status": "no_embedded_payments", "payments_scored": 0}

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def score(payment: dict[str, Any]) -> UpdateOne:
        async with semaphore:
            neighbours = await collection.aggregate(vector_search_pipeline(payment["product_embedding"])).to_list(length=None)
        return UpdateOne({"_id": payment["_id"]}, {"$set": {"mismatch_score": mismatch_from_neighbours(payment, neighbours)}})

    try:
        updates = await asyncio.gather(*(score(payment) for payment in payments))
    except (OperationFailure, NotImplementedError) as exc:
        logger.warning("Atlas Vector Search unavailable; mismatch scores unchanged: %s", exc)
        return {"status": "vector_index_unavailable", "payments_scored": 0}
    await collection.bulk_write(updates, ordered=False)
    return {"status": "scored", "payments_scored": len(updates)}
