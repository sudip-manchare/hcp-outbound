"""Migrate the CMS table and ingest generic, paginated Open Payments data.

Usage examples:
    # Replace existing records and load the first 100 live CMS records.
    python scripts/ingest_cms_open_payments.py --reset --pages 1

    # Resume from a later CMS page, retaining existing data.
    python scripts/ingest_cms_open_payments.py --start-offset 100 --pages 5

    # Ingest a focused cohort instead of the whole program-year feed.
    python scripts/ingest_cms_open_payments.py --recipient-state OH --pages 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

from app.services.cms_open_payments_service import fetch_raw_payments_page
from scripts.score_cms_payments import score_retained_payments


load_dotenv(Path(__file__).parent.parent / ".env")
DATABASE_URL_SYNC = os.environ.get("DATABASE_URL_SYNC", "postgresql://localhost/hcp_outbound")


MIGRATION_SQL = """
ALTER TABLE cms_payments DROP CONSTRAINT IF EXISTS cms_payments_physician_npi_fkey;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cms_payments' AND column_name = 'physician_npi'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cms_payments' AND column_name = 'recipient_npi'
    ) THEN
        ALTER TABLE cms_payments RENAME COLUMN physician_npi TO recipient_npi;
    END IF;
END $$;

ALTER TABLE cms_payments ALTER COLUMN recipient_npi DROP NOT NULL;
ALTER TABLE cms_payments ALTER COLUMN payment_type TYPE VARCHAR(300);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_profile_id VARCHAR(50);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_type VARCHAR(100);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_first_name VARCHAR(100);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_middle_name VARCHAR(100);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_last_name VARCHAR(100);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_specialty VARCHAR(500);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_city VARCHAR(100);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_state VARCHAR(50);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS recipient_zip_code VARCHAR(20);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS manufacturer_id VARCHAR(50);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS payment_form VARCHAR(150);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS payment_count INTEGER;
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS cms_dispute_status VARCHAR(100);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS publication_date DATE;
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS delay_in_publication_indicator VARCHAR(10);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS change_type VARCHAR(50);
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS cms_program_year SMALLINT;
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS source_fetched_at TIMESTAMPTZ;
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS raw_cms_payload JSONB;
ALTER TABLE cms_payments ADD COLUMN IF NOT EXISTS ingestion_run_id BIGINT;

CREATE TABLE IF NOT EXISTS cms_ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    dataset_id VARCHAR(100) NOT NULL,
    program_year SMALLINT NOT NULL,
    source_url TEXT NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    start_offset INTEGER NOT NULL,
    page_size INTEGER NOT NULL,
    pages_requested INTEGER NOT NULL,
    records_ingested INTEGER NOT NULL DEFAULT 0,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_skipped INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE cms_ingestion_runs ADD COLUMN IF NOT EXISTS records_seen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cms_ingestion_runs ADD COLUMN IF NOT EXISTS records_inserted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cms_ingestion_runs ADD COLUMN IF NOT EXISTS records_skipped INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_payments_source_record
ON cms_payments (raw_cms_record_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_cms_payments_recipient_npi
ON cms_payments (recipient_npi);
CREATE INDEX IF NOT EXISTS idx_cms_payments_ingestion_run
ON cms_payments (ingestion_run_id);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id BIGSERIAL PRIMARY KEY,
    raw_cms_record_id VARCHAR(100) NOT NULL,
    payment_date TIMESTAMPTZ NOT NULL,
    risk_score SMALLINT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_level VARCHAR(30) NOT NULL CHECK (risk_level IN ('low', 'review', 'high_priority_review')),
    review_recommended BOOLEAN NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    plain_language_explanation TEXT NOT NULL,
    evidence JSONB NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    invalidated_by_ingestion_run_id BIGINT,
    invalidated_at TIMESTAMPTZ,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_signals (
    id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL REFERENCES risk_assessments(id) ON DELETE CASCADE,
    code VARCHAR(100) NOT NULL,
    weight SMALLINT NOT NULL CHECK (weight >= 0),
    title VARCHAR(200) NOT NULL,
    plain_explanation TEXT NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_assessments_source
ON risk_assessments (raw_cms_record_id, payment_date, assessed_at DESC);
ALTER TABLE risk_assessments ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE risk_assessments ADD COLUMN IF NOT EXISTS invalidated_by_ingestion_run_id BIGINT;
ALTER TABLE risk_assessments ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_risk_assessments_current
ON risk_assessments (raw_cms_record_id, payment_date, model_version, assessed_at DESC)
WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_risk_signals_assessment
ON risk_signals (assessment_id);

UPDATE cms_ingestion_runs
SET records_seen = records_ingested,
    records_inserted = records_ingested
WHERE records_seen = 0 AND records_inserted = 0 AND records_ingested > 0;
"""


def parse_cms_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").replace(tzinfo=timezone.utc)


def prepare_schema(cur) -> None:
    cur.execute(MIGRATION_SQL)


def clear_application_data(cur) -> None:
    """Remove only HCP Outbound application data; extensions and DB settings remain."""
    cur.execute("TRUNCATE TABLE risk_signals, risk_assessments, audit_tokens, disputes, cms_payments, physicians RESTART IDENTITY CASCADE;")
    cur.execute("TRUNCATE TABLE cms_ingestion_runs RESTART IDENTITY;")


def payment_row(record: dict, run_id: int, source: dict) -> tuple:
    products = [
        record.get(f"name_of_drug_or_biological_or_device_or_medical_supply_{index}")
        for index in range(1, 6)
    ]
    product_name = next((product for product in products if product), None)
    return (
        record.get("covered_recipient_npi") or None,
        record.get("covered_recipient_profile_id") or None,
        record.get("covered_recipient_type") or None,
        record.get("covered_recipient_first_name") or None,
        record.get("covered_recipient_middle_name") or None,
        record.get("covered_recipient_last_name") or None,
        record.get("covered_recipient_specialty_1") or None,
        record.get("recipient_city") or None,
        record.get("recipient_state") or None,
        record.get("recipient_zip_code") or None,
        parse_cms_date(record.get("date_of_payment")),
        record.get("applicable_manufacturer_or_applicable_gpo_making_payment_name") or "Unknown reporting entity",
        record.get("applicable_manufacturer_or_applicable_gpo_making_payment_id") or None,
        product_name,
        record.get("nature_of_payment_or_transfer_of_value") or None,
        record.get("form_of_payment_or_transfer_of_value") or None,
        int(record.get("number_of_payments_included_in_total_amount") or 1),
        record.get("total_amount_of_payment_usdollars"),
        record.get("dispute_status_for_publication") or None,
        parse_cms_date(record.get("payment_publication_date")),
        record.get("delay_in_publication_indicator") or None,
        record.get("change_type") or None,
        int(record.get("program_year") or source["program_year"]),
        source["url"],
        datetime.now(timezone.utc),
        record.get("record_id"),
        Json(record),
        run_id,
    )


INSERT_PAYMENTS_SQL = """
INSERT INTO cms_payments (
    recipient_npi, recipient_profile_id, recipient_type,
    recipient_first_name, recipient_middle_name, recipient_last_name,
    recipient_specialty, recipient_city, recipient_state, recipient_zip_code,
    payment_date, manufacturer_name, manufacturer_id, product_name,
    payment_type, payment_form, payment_count, amount_usd,
    cms_dispute_status, publication_date, delay_in_publication_indicator,
    change_type, cms_program_year, source_url, source_fetched_at,
    raw_cms_record_id, raw_cms_payload, ingestion_run_id
) VALUES %s
ON CONFLICT (raw_cms_record_id, payment_date) DO NOTHING
RETURNING id;
"""


async def ingest(args) -> None:
    conn = psycopg2.connect(DATABASE_URL_SYNC)
    run_id = None
    try:
        with conn.cursor() as cur:
            prepare_schema(cur)
            if args.reset:
                clear_application_data(cur)
            conn.commit()

            first_page = await fetch_raw_payments_page(
                limit=args.page_size,
                offset=args.start_offset,
                recipient_state=args.recipient_state,
            )
            source = first_page["source"]
            cur.execute(
                """
                INSERT INTO cms_ingestion_runs
                    (dataset_id, program_year, source_url, filters, start_offset, page_size, pages_requested)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    source["dataset_id"], source["program_year"], source["url"],
                    Json(first_page["filters"]), args.start_offset, args.page_size, args.pages,
                ),
            )
            run_id = cur.fetchone()[0]
            conn.commit()

            pages = [first_page]
            for page_number in range(1, args.pages):
                next_offset = args.start_offset + page_number * args.page_size
                pages.append(await fetch_raw_payments_page(
                    limit=args.page_size,
                    offset=next_offset,
                    recipient_state=args.recipient_state,
                ))

            seen = 0
            inserted = 0
            for page in pages:
                rows = [payment_row(record, run_id, source) for record in page["records"]]
                seen += len(rows)
                if rows:
                    inserted_rows = execute_values(cur, INSERT_PAYMENTS_SQL, rows, page_size=100, fetch=True)
                    inserted += len(inserted_rows)
                conn.commit()

            # Persist current model results before declaring ingestion complete.
            # This also scores previously retained rows and duplicate-only pulls.
            triage = await score_retained_payments(DATABASE_URL_SYNC)

            cur.execute(
                """UPDATE cms_ingestion_runs
                   SET records_ingested = %s, records_seen = %s, records_inserted = %s,
                       records_skipped = %s, status = 'completed', completed_at = NOW()
                   WHERE id = %s""",
                (inserted, seen, inserted, seen - inserted, run_id),
            )
            conn.commit()
            print(json.dumps({
                "run_id": run_id,
                "records_seen": seen,
                "records_inserted": inserted,
                "records_skipped": seen - inserted,
                "risk_assessments_created": triage["records_scored"],
                "risk_assessments_flagged": triage["records_flagged"],
                "risk_model_version": triage["model_version"],
                "pages": len(pages),
                "pagination": pages[-1]["pagination"],
                "filters": first_page["filters"],
            }, indent=2, default=str))
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cms_ingestion_runs SET status = 'failed', error_message = %s, completed_at = NOW() "
                "WHERE id = %s AND status = 'running'",
                (str(exc), run_id),
            )
            conn.commit()
        raise
    finally:
        conn.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest paginated CMS Open Payments data into Tiger Data.")
    parser.add_argument("--reset", action="store_true", help="Delete existing HCP Outbound application data before ingesting.")
    parser.add_argument("--pages", type=int, default=1, help="Number of CMS pages to ingest (default: 1).")
    parser.add_argument("--page-size", type=int, default=100, help="Records per CMS page (maximum configured by the app).")
    parser.add_argument("--start-offset", type=int, default=0, help="CMS offset at which ingestion starts.")
    parser.add_argument("--recipient-state", type=str, default=None, help="Optional two-letter recipient state filter.")
    args = parser.parse_args()
    if args.pages < 1 or args.page_size < 1 or args.start_offset < 0:
        parser.error("pages and page-size must be positive, and start-offset cannot be negative.")
    return args


if __name__ == "__main__":
    asyncio.run(ingest(parse_args()))
