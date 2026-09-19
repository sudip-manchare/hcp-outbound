"""
init_tiger_db.py
================
Bootstraps the Tiger Data PostgreSQL database for HCP Outbound:

  1. Enables the TimescaleDB extension
  2. Enables the pgvector extension
  3. Creates all application tables:
       - physicians          (HCP profiles, NPPES-enriched)
       - cms_payments        (CMS Open Payments transactions — Timescale hypertable)
       - disputes            (Formal 42 CFR § 403.908 dispute records)
       - audit_tokens        (Signed, expiring audit portal URL tokens)
  4. Converts cms_payments into a TimescaleDB hypertable on payment_date
  5. Creates a pgvector HNSW index on cms_payments.product_embedding
  6. Creates a pgvector HNSW index on physicians.specialty_embedding

Usage:
    cd backend
    cp .env.example .env          # fill in your Tiger Data DATABASE_URL_SYNC
    pip install -r requirements.txt
    python scripts/init_tiger_db.py
"""

import sys
import os

# Allow imports from backend/app when running as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://localhost/hcp_outbound"
)

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 compatible dimension


def get_conn():
    conn = psycopg2.connect(DATABASE_URL_SYNC)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def enable_extensions(cur):
    print("→ Enabling TimescaleDB extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
    print("→ Enabling pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector CASCADE;")
    print("✓ Extensions enabled.")


def create_tables(cur):
    print("→ Creating physicians table...")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS physicians (
            npi                 VARCHAR(10)  PRIMARY KEY,
            first_name          VARCHAR(100) NOT NULL,
            last_name           VARCHAR(100) NOT NULL,
            credential          VARCHAR(50),
            primary_taxonomy    VARCHAR(300),   -- NPPES taxonomy description
            taxonomy_code       VARCHAR(20),
            city                VARCHAR(100),
            state               VARCHAR(2),
            zip                 VARCHAR(10),
            phone               VARCHAR(20),
            nppes_last_fetched  TIMESTAMPTZ,
            -- pgvector: 384-dim embedding of the NPPES taxonomy description
            specialty_embedding VECTOR({EMBEDDING_DIM}),
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    print("→ Creating cms_payments table (will become a Timescale hypertable)...")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS cms_payments (
            id                  BIGSERIAL,
            physician_npi       VARCHAR(10)  NOT NULL REFERENCES physicians(npi),
            payment_date        TIMESTAMPTZ  NOT NULL,   -- hypertable partition key
            manufacturer_name   VARCHAR(200) NOT NULL,
            product_name        VARCHAR(300),
            payment_type        VARCHAR(100),            -- e.g. 'Food and Beverage', 'Consulting Fee'
            amount_usd          NUMERIC(12, 2) NOT NULL,
            is_reviewed         BOOLEAN      DEFAULT FALSE,
            dispute_id          BIGINT,
            -- pgvector: embedding of product_name + payment_type description
            product_embedding   VECTOR({EMBEDDING_DIM}),
            -- Specialty mismatch score (cosine distance vs physician.specialty_embedding)
            mismatch_score      FLOAT,
            raw_cms_record_id   VARCHAR(100),            -- original CMS Open Payments record ID
            created_at          TIMESTAMPTZ  DEFAULT NOW(),
            PRIMARY KEY (id, payment_date)              -- composite PK required by Timescale
        );
    """)

    print("→ Creating disputes table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS disputes (
            id                  BIGSERIAL    PRIMARY KEY,
            physician_npi       VARCHAR(10)  NOT NULL REFERENCES physicians(npi),
            payment_ids         BIGINT[]     NOT NULL,   -- array of cms_payments.id
            manufacturer_name   VARCHAR(200),
            manufacturer_compliance_email VARCHAR(200),
            dispute_notice_text TEXT,                    -- AI-generated 42 CFR § 403.908 notice
            status              VARCHAR(50)  DEFAULT 'pending',  -- pending | submitted | resolved
            created_at          TIMESTAMPTZ  DEFAULT NOW(),
            updated_at          TIMESTAMPTZ  DEFAULT NOW()
        );
    """)

    print("→ Creating audit_tokens table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_tokens (
            token           VARCHAR(64)  PRIMARY KEY,
            npi             VARCHAR(10)  NOT NULL,
            expires_at      TIMESTAMPTZ  NOT NULL,
            accessed        BOOLEAN      DEFAULT FALSE,
            pipeline_state  VARCHAR(20)  DEFAULT 'dispatched',  -- dispatched|opened|disputed|protected
            created_at      TIMESTAMPTZ  DEFAULT NOW()
        );
    """)

    print("✓ All tables created.")


def create_hypertable(cur):
    print("→ Converting cms_payments to a TimescaleDB hypertable on payment_date...")
    # if_not_exists=true is safe to re-run
    cur.execute("""
        SELECT create_hypertable(
            'cms_payments',
            'payment_date',
            if_not_exists => TRUE,
            migrate_data   => TRUE
        );
    """)
    print("✓ Hypertable created.")


def create_indexes(cur):
    print("→ Creating pgvector HNSW index on cms_payments.product_embedding...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cms_payments_product_emb
        ON cms_payments
        USING hnsw (product_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    print("→ Creating pgvector HNSW index on physicians.specialty_embedding...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_physicians_specialty_emb
        ON physicians
        USING hnsw (specialty_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    print("→ Creating supporting B-tree indexes...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cms_payments_npi
        ON cms_payments (physician_npi);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cms_payments_reviewed
        ON cms_payments (physician_npi, is_reviewed);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cms_payments_manufacturer
        ON cms_payments (manufacturer_name);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_disputes_npi
        ON disputes (physician_npi);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_tokens_npi
        ON audit_tokens (npi, expires_at);
    """)

    print("✓ Indexes created.")


def main():
    print("\n╔══════════════════════════════════════════════╗")
    print("║   Tiger Data DB Init — HCP Outbound Engine   ║")
    print("╚══════════════════════════════════════════════╝\n")

    conn = get_conn()
    cur = conn.cursor()

    try:
        enable_extensions(cur)
        create_tables(cur)
        create_hypertable(cur)
        create_indexes(cur)
    finally:
        cur.close()
        conn.close()

    print("\n🐯 Tiger Data database initialized successfully!\n")


if __name__ == "__main__":
    main()
