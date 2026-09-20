"""Backfill or refresh stored Isolation Forest assessments without fetching CMS.

Run from backend/: python -m scripts.score_cms_payments
"""

import asyncio
import json

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.services.risk_triage_service import run_isolation_forest_triage


async def score_retained_payments(database_url: str | None = None) -> dict:
    # CLI ingestion uses the synchronous URL. Score that same database even
    # when the API's separately configured URL points elsewhere.
    url = make_url(database_url or get_settings().DATABASE_URL_SYNC)
    # libpq/psycopg2 calls this option sslmode; asyncpg calls it ssl.
    if "sslmode" in url.query:
        ssl_mode = url.query["sslmode"]
        url = url.difference_update_query(["sslmode"]).update_query_dict({"ssl": ssl_mode})
    engine = create_async_engine(url.set(drivername="postgresql+asyncpg"))
    try:
        async with AsyncSession(engine) as db:
            async with db.begin():
                return await run_isolation_forest_triage(db)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(score_retained_payments()), indent=2))
