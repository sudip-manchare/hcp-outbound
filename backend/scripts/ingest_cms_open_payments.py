"""One-time load of generic, paginated CMS Open Payments data into MongoDB Atlas.

Request handlers serve CMS data from MongoDB only; this script is the only
place the CMS API is read in bulk. NPPES is not pre-fetched.

Usage examples (from backend/):
    # Replace existing records and load 10 pages x 100 = 1,000 live CMS records.
    python -m scripts.ingest_cms_open_payments --reset

    # Resume from a later CMS page, retaining existing data.
    python -m scripts.ingest_cms_open_payments --start-offset 1000 --pages 5

    # Ingest a focused cohort instead of the whole program-year feed.
    python -m scripts.ingest_cms_open_payments --recipient-state OH --pages 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import close_db, init_db
from app.models.documents import DOCUMENT_MODELS, CmsIngestionRun, CmsPayment, utcnow
from app.services.cms_open_payments_service import fetch_raw_payments_page
from app.services.cms_payment_repository import payment_document, upsert_payments
from scripts.init_mongo_db import init_mongo
from scripts.score_cms_payments import score_retained_payments

DEFAULT_PAGES = 10


async def clear_application_data(db: AsyncIOMotorDatabase) -> None:
    """Remove only HCP Outbound documents; collections and indexes remain."""
    for model in DOCUMENT_MODELS:
        await db[model.Settings.name].delete_many({})


async def ingest(args, db: AsyncIOMotorDatabase | None = None) -> dict:
    owns_db = db is None
    db = db if db is not None else await init_db()
    run: CmsIngestionRun | None = None
    try:
        await init_mongo(db)
        if args.reset:
            await clear_application_data(db)

        first_page = await fetch_raw_payments_page(
            limit=args.page_size,
            offset=args.start_offset,
            recipient_state=args.recipient_state,
        )
        source = first_page["source"]
        run = await CmsIngestionRun(
            dataset_id=source["dataset_id"],
            program_year=source["program_year"],
            source_url=source["url"],
            filters=first_page["filters"],
            start_offset=args.start_offset,
            page_size=args.page_size,
            pages_requested=args.pages,
        ).insert()

        pages = [first_page]
        for page_number in range(1, args.pages):
            if pages[-1]["pagination"].get("next_offset") is None:
                break
            pages.append(await fetch_raw_payments_page(
                limit=args.page_size,
                offset=args.start_offset + page_number * args.page_size,
                recipient_state=args.recipient_state,
            ))

        collection = db[CmsPayment.Settings.name]
        seen = inserted = 0
        for page in pages:
            documents = [payment_document(record, source, run.id) for record in page["records"]]
            seen += len(documents)
            inserted += await upsert_payments(collection, documents)

        # Persist current model results before declaring ingestion complete.
        # This also scores previously retained rows and duplicate-only pulls.
        triage = await score_retained_payments(db)

        run.records_ingested = run.records_inserted = inserted
        run.records_seen = seen
        run.records_skipped = seen - inserted
        run.status = "completed"
        run.completed_at = utcnow()
        await run.save()
        result = {
            "run_id": str(run.id),
            "records_seen": seen,
            "records_inserted": inserted,
            "records_skipped": seen - inserted,
            "risk_assessments_created": triage["records_scored"],
            "risk_assessments_flagged": triage["records_flagged"],
            "risk_model_version": triage["model_version"],
            "mismatch_scoring": triage["mismatch_scoring"],
            "pages": len(pages),
            "pagination": pages[-1]["pagination"],
            "filters": first_page["filters"],
        }
        print(json.dumps(result, indent=2, default=str))
        return result
    except Exception as exc:
        if run is not None and run.status == "running":
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = utcnow()
            await run.save()
        raise
    finally:
        if owns_db:
            await close_db()


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Ingest paginated CMS Open Payments data into MongoDB Atlas.")
    parser.add_argument("--reset", action="store_true", help="Delete existing HCP Outbound application data before ingesting.")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help=f"Number of CMS pages to ingest (default: {DEFAULT_PAGES}).")
    parser.add_argument("--page-size", type=int, default=100, help="Records per CMS page (maximum configured by the app).")
    parser.add_argument("--start-offset", type=int, default=0, help="CMS offset at which ingestion starts.")
    parser.add_argument("--recipient-state", type=str, default=None, help="Optional two-letter recipient state filter.")
    args = parser.parse_args(argv)
    if args.pages < 1 or args.page_size < 1 or args.start_offset < 0:
        parser.error("pages and page-size must be positive, and start-offset cannot be negative.")
    return args


if __name__ == "__main__":
    asyncio.run(ingest(parse_args()))
