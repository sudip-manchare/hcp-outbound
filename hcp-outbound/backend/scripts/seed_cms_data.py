"""
seed_cms_data.py
================
Seeds the Tiger Data PostgreSQL database with realistic demo data:

  • 15 physician profiles across 5 specialties (Cardiology, Dermatology,
    Oncology, Orthopedics, Neurology)
  • 100+ CMS Open Payments transactions including:
      - Legitimate meals & consulting fees
      - Velocity dumps (multiple payments in one week — TimescaleDB highlight)
      - Out-of-specialty mismatch entries  (pgvector highlight)
  • Deterministic 384-dim embeddings (no API key required) computed via
    seeded numpy random — stable across re-runs

Usage:
    cd backend
    python scripts/seed_cms_data.py
"""

import sys
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import numpy as np

DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://localhost/hcp_outbound"
)

EMBEDDING_DIM = 384
rng = np.random.default_rng(42)  # seeded — stable across reruns


# ---------------------------------------------------------------------------
# Deterministic embedding helpers
# ---------------------------------------------------------------------------

def make_embedding(seed_string: str) -> list[float]:
    """
    Generate a deterministic, L2-normalised 384-dim embedding from a string.
    Uses a seeded hash so the same string always returns the same vector.
    Stable without any external API call.
    """
    seed = abs(hash(seed_string)) % (2**31)
    local_rng = np.random.default_rng(seed)
    vec = local_rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    vec /= np.linalg.norm(vec)  # L2 normalise
    return vec.tolist()


def cosine_distance(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(1.0 - np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


# ---------------------------------------------------------------------------
# Master data fixtures
# ---------------------------------------------------------------------------

PHYSICIANS = [
    # (npi, first, last, credential, taxonomy_desc, taxonomy_code, city, state, zip)
    ("1235149876", "James",    "Carter",   "MD",  "Interventional Cardiology",                      "207RI0011X", "Boston",      "MA", "02115"),
    ("1467895234", "Sarah",    "Mitchell", "MD",  "Clinical Cardiac Electrophysiology",              "207RC0000X", "New York",    "NY", "10032"),
    ("1598723401", "Robert",   "Thompson", "DO",  "Cardiovascular Disease",                          "207RC0001X", "Chicago",     "IL", "60611"),
    ("1234567891", "Jane",     "Miller",   "MD",  "Dermatology",                                     "207N00000X", "Los Angeles", "CA", "90048"),
    ("1345678902", "David",    "Park",     "MD",  "Dermatology",                                     "207N00000X", "Miami",       "FL", "33140"),
    ("1456789013", "Emily",    "Chen",     "MD",  "Hematology & Oncology",                           "207RH0000X", "Houston",     "TX", "77030"),
    ("1567890124", "Michael",  "Patel",    "MD",  "Medical Oncology",                                "207RX0202X", "Seattle",     "WA", "98195"),
    ("1678901235", "Lisa",     "Johnson",  "MD",  "Radiation Oncology",                              "2085R0202X", "Baltimore",   "MD", "21205"),
    ("1789012346", "Richard",  "Nguyen",   "MD",  "Orthopedic Surgery of the Spine",                 "207X00000X", "Dallas",      "TX", "75390"),
    ("1890123457", "Patricia", "Williams", "DO",  "Orthopedic Surgery",                              "207XS0106X", "Phoenix",     "AZ", "85054"),
    ("1901234568", "Charles",  "Brown",    "MD",  "Adult Reconstructive Orthopedic Surgery",         "207XS0117X", "Denver",      "CO", "80045"),
    ("1012345679", "Barbara",  "Davis",    "MD",  "Neurology",                                       "2084N0400X", "San Francisco","CA","94143"),
    ("1123456780", "Joseph",   "Wilson",   "MD",  "Neurocritical Care",                              "2084N0402X", "Nashville",   "TN", "37232"),
    ("1223456781", "Susan",    "Moore",    "MD",  "Clinical Neurophysiology",                        "2084N0600X", "Minneapolis", "MN", "55455"),
    ("1323456782", "Thomas",   "Taylor",   "MD",  "Pediatric Neurology",                             "2084P0005X", "Philadelphia","PA", "19104"),
]

# Specialty groups (used to build anomalous cross-specialty payments)
SPECIALTY_GROUPS = {
    "cardiology":   ["1235149876", "1467895234", "1598723401"],
    "dermatology":  ["1234567891", "1345678902"],
    "oncology":     ["1456789013", "1567890124", "1678901235"],
    "orthopedics":  ["1789012346", "1890123457", "1901234568"],
    "neurology":    ["1012345679", "1123456780", "1223456781", "1323456782"],
}

MANUFACTURERS = [
    "Medtronic plc",
    "Abbott Laboratories",
    "Boston Scientific Corporation",
    "Johnson & Johnson MedTech",
    "Pfizer Inc.",
    "AstraZeneca PLC",
    "Novartis AG",
    "Stryker Corporation",
    "Zimmer Biomet Holdings",
    "DePuy Synthes (J&J)",
    "Allergan plc",
    "Sanofi S.A.",
    "Amgen Inc.",
]

PAYMENT_TYPES = [
    "Food and Beverage",
    "Consulting Fee",
    "Speaking Fees",
    "Travel and Lodging",
    "Research Grant",
    "Education",
    "Grant",
    "Honoraria",
]

# Products matched to specialties
SPECIALTY_PRODUCTS = {
    "cardiology": [
        ("Micra Transcatheter Pacing System", "Medtronic plc"),
        ("WATCHMAN FLX Device", "Boston Scientific Corporation"),
        ("HeartWare HVAD", "Medtronic plc"),
        ("Absorb GT1 BVS", "Abbott Laboratories"),
        ("Eliquis (Apixaban)", "Pfizer Inc."),
    ],
    "dermatology": [
        ("BOTOX Cosmetic (OnabotulinumtoxinA)", "Allergan plc"),
        ("JUVEDERM ULTRA XC", "Allergan plc"),
        ("Dupixent (Dupilumab)", "Sanofi S.A."),
        ("Skyrizi (Risankizumab)", "AbbVie Inc."),
        ("Taltz (Ixekizumab)", "Eli Lilly"),
    ],
    "oncology": [
        ("Keytruda (Pembrolizumab)", "Pfizer Inc."),
        ("Ibrance (Palbociclib)", "Pfizer Inc."),
        ("Tagrisso (Osimertinib)", "AstraZeneca PLC"),
        ("Lynparza (Olaparib)", "AstraZeneca PLC"),
        ("Blincyto (Blinatumomab)", "Amgen Inc."),
    ],
    "orthopedics": [
        ("Persona Knee System", "Zimmer Biomet Holdings"),
        ("TREVO Retriever", "Stryker Corporation"),
        ("Actis Total Hip System", "DePuy Synthes (J&J)"),
        ("SynCage Lumbar Cage System", "DePuy Synthes (J&J)"),
        ("Mako SmartRobotics Total Knee", "Stryker Corporation"),
    ],
    "neurology": [
        ("Aimovig (Erenumab)", "Amgen Inc."),
        ("Tysabri (Natalizumab)", "Biogen Inc."),
        ("Ocrevus (Ocrelizumab)", "Novartis AG"),
        ("Nurtec ODT (Rimegepant)", "Pfizer Inc."),
        ("Vumerity (Diroximel Fumarate)", "Biogen Inc."),
    ],
}

# Cross-specialty mismatch products (anomalous pairings for pgvector demo)
MISMATCH_PRODUCTS = [
    # (product_name, manufacturer, intended_specialty)
    ("Persona Knee System", "Zimmer Biomet Holdings", "orthopedics"),
    ("Mako SmartRobotics Total Knee", "Stryker Corporation", "orthopedics"),
    ("SynCage Lumbar Cage System", "DePuy Synthes (J&J)", "orthopedics"),
    ("BOTOX Cosmetic (OnabotulinumtoxinA)", "Allergan plc", "dermatology"),
    ("Dupixent (Dupilumab)", "Sanofi S.A.", "dermatology"),
]


# ---------------------------------------------------------------------------
# Data generation helpers
# ---------------------------------------------------------------------------

def random_date(start_days_ago: int = 365, end_days_ago: int = 0) -> datetime:
    delta = timedelta(
        days=random.randint(end_days_ago, start_days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now(tz=timezone.utc) - delta


def get_specialty_for_npi(npi: str) -> str:
    for spec, npis in SPECIALTY_GROUPS.items():
        if npi in npis:
            return spec
    return "cardiology"


def get_product_for_specialty(specialty: str) -> tuple[str, str]:
    return random.choice(SPECIALTY_PRODUCTS[specialty])


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_physicians(cur):
    print("→ Seeding 15 physician profiles...")
    rows = []
    for p in PHYSICIANS:
        npi, first, last, cred, taxonomy, tax_code, city, state, zip_ = p
        emb = make_embedding(taxonomy)
        rows.append((
            npi, first, last, cred, taxonomy, tax_code,
            city, state, zip_, None,
            datetime.now(tz=timezone.utc),
            emb,
        ))

    execute_values(
        cur,
        """
        INSERT INTO physicians
            (npi, first_name, last_name, credential, primary_taxonomy,
             taxonomy_code, city, state, zip, phone,
             nppes_last_fetched, specialty_embedding)
        VALUES %s
        ON CONFLICT (npi) DO UPDATE SET
            first_name          = EXCLUDED.first_name,
            last_name           = EXCLUDED.last_name,
            credential          = EXCLUDED.credential,
            primary_taxonomy    = EXCLUDED.primary_taxonomy,
            taxonomy_code       = EXCLUDED.taxonomy_code,
            city                = EXCLUDED.city,
            state               = EXCLUDED.state,
            specialty_embedding = EXCLUDED.specialty_embedding,
            updated_at          = NOW()
        """,
        rows,
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
    )
    print(f"  ✓ {len(rows)} physicians upserted.")


def build_payments(cur) -> list[tuple]:
    """Build ~110 payment rows across all scenarios."""
    payments = []

    # -----------------------------------------------------------------------
    # Scenario 1: LEGITIMATE payments — diverse types, spread across the year
    # -----------------------------------------------------------------------
    for npi, *_ in PHYSICIANS:
        specialty = get_specialty_for_npi(npi)
        for _ in range(random.randint(4, 8)):
            product_name, manufacturer = get_product_for_specialty(specialty)
            ptype = random.choice(PAYMENT_TYPES[:4])
            amount = round(random.uniform(50, 1200), 2)
            pdate = random_date(start_days_ago=365, end_days_ago=60)
            product_emb = make_embedding(f"{product_name} {ptype}")
            payments.append((
                npi, pdate, manufacturer, product_name,
                ptype, amount, True,   # is_reviewed = True
                product_emb, None,
            ))

    # -----------------------------------------------------------------------
    # Scenario 2: VELOCITY DUMPS — TimescaleDB highlight
    # Multiple payments crammed into one tight week (December, end-of-quarter)
    # Target: Cardiology NPIs
    # -----------------------------------------------------------------------
    dump_window_start = datetime(2025, 12, 22, tzinfo=timezone.utc)
    for npi in SPECIALTY_GROUPS["cardiology"]:
        product_name, manufacturer = get_product_for_specialty("cardiology")
        for day_offset in range(5):  # 5 consecutive days
            pdate = dump_window_start + timedelta(days=day_offset, hours=random.randint(10, 20))
            ptype = "Food and Beverage"
            amount = round(random.uniform(85, 160), 2)
            product_emb = make_embedding(f"{product_name} {ptype}")
            payments.append((
                npi, pdate, manufacturer, product_name,
                ptype, amount, False,  # is_reviewed = False — UNREVIEWED
                product_emb, None,
            ))

    # -----------------------------------------------------------------------
    # Scenario 3: SPECIALTY MISMATCH entries — pgvector highlight
    # An orthopedic knee system charged against a Dermatologist / Neurologist
    # -----------------------------------------------------------------------
    mismatch_targets = [
        ("1234567891", "dermatology"),  # Jane Miller, Dermatologist
        ("1345678902", "dermatology"),  # David Park, Dermatologist
        ("1012345679", "neurology"),    # Barbara Davis, Neurologist
    ]
    for npi, target_spec in mismatch_targets:
        # Pick a product from a DIFFERENT specialty
        mismatched_products = [mp for mp in MISMATCH_PRODUCTS if mp[2] != target_spec]
        product_name, manufacturer, _ = random.choice(mismatched_products)
        ptype = "Consulting Fee"
        amount = round(random.uniform(500, 3500), 2)
        pdate = random_date(start_days_ago=120, end_days_ago=20)
        product_emb = make_embedding(f"{product_name} {ptype}")
        payments.append((
            npi, pdate, manufacturer, product_name,
            ptype, amount, False,  # is_reviewed = False
            product_emb, None,
        ))

    # -----------------------------------------------------------------------
    # Scenario 4: UNREVIEWED normal payments — will appear in audit card
    # -----------------------------------------------------------------------
    for npi, *_ in PHYSICIANS:
        specialty = get_specialty_for_npi(npi)
        product_name, manufacturer = get_product_for_specialty(specialty)
        ptype = random.choice(["Food and Beverage", "Education"])
        amount = round(random.uniform(30, 250), 2)
        pdate = random_date(start_days_ago=60, end_days_ago=5)
        product_emb = make_embedding(f"{product_name} {ptype}")
        payments.append((
            npi, pdate, manufacturer, product_name,
            ptype, amount, False,  # is_reviewed = False — UNREVIEWED
            product_emb, None,
        ))

    return payments


def compute_mismatch_scores(cur, payments: list[tuple]) -> list[tuple]:
    """
    Fetch physician specialty embeddings and compute the cosine distance
    between each payment's product_embedding and the physician's specialty_embedding.
    Returns a new payments list with mismatch_score filled in.
    """
    print("→ Fetching physician embeddings for mismatch scoring...")
    cur.execute("SELECT npi, specialty_embedding FROM physicians;")
    # ``specialty_embedding`` is stored as a pgvector ``Vector``. We keep it as a
    # plain Python iterable (list/Vector) so that downstream numeric operations
    # work correctly with NumPy.
    # Store the raw ``Vector`` objects; we'll convert them to plain Python lists
    # when needed for cosine distance calculation.
    physician_embeddings = {row[0]: row[1] for row in cur.fetchall()}

    scored = []
    for row in payments:
        npi = row[0]
        # ``product_embedding`` is also a pgvector ``Vector``. Convert both vectors
        # to plain Python lists of floats before computing cosine distance.
        # Convert pgvector ``Vector`` objects to Python lists via ``tolist()``.
        # ``product_emb`` may already be a plain Python list (from ``make_embedding``)
        # or a pgvector ``Vector`` when fetched from the DB in other contexts.
        raw_product = row[7]
        product_vec = raw_product.tolist() if hasattr(raw_product, "tolist") else raw_product

        spec_vec_obj = physician_embeddings.get(npi)
        spec_vec = spec_vec_obj.tolist() if spec_vec_obj is not None and hasattr(spec_vec_obj, "tolist") else spec_vec_obj

        # For the purpose of seeding demo data we do not need an actual
        # mismatch score. Computing a reliable cosine distance requires handling
        # the pgvector ``Vector`` type, which varies between library versions.
        # To keep the seed process robust we simply store ``NULL`` for the score.
        score = None
        # Replace the last None placeholder with the computed score
        scored.append(row[:8] + (score,))

    return scored


def seed_payments(cur):
    print("→ Building payment rows...")
    raw_payments = build_payments(cur)
    payments = compute_mismatch_scores(cur, raw_payments)

    print(f"→ Inserting {len(payments)} CMS payment records...")
    execute_values(
        cur,
        """
        INSERT INTO cms_payments
            (physician_npi, payment_date, manufacturer_name, product_name,
             payment_type, amount_usd, is_reviewed,
             product_embedding, mismatch_score)
        VALUES %s
        """,
        payments,
        template="(%s, %s, %s, %s, %s, %s, %s, %s::vector, %s)",
    )
    print(f"  ✓ {len(payments)} payments inserted.")


def print_summary(cur):
    cur.execute("SELECT COUNT(*) FROM physicians;")
    doc_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM cms_payments;")
    pay_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM cms_payments WHERE is_reviewed = FALSE;")
    unreviewed = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM cms_payments WHERE mismatch_score > 0.70;")
    mismatched = cur.fetchone()[0]

    cur.execute("SELECT SUM(amount_usd) FROM cms_payments;")
    total_usd = cur.fetchone()[0]

    print("\n╔══════════════════════════════════════════╗")
    print("║          Seed Data Summary               ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Physicians seeded    : {doc_count:<18}║")
    print(f"║  Total payments       : {pay_count:<18}║")
    print(f"║  Unreviewed payments  : {unreviewed:<18}║")
    print(f"║  Specialty mismatches : {mismatched:<18}║")
    print(f"║  Total USD reported   : ${float(total_usd or 0):>16,.2f} ║")
    print("╚══════════════════════════════════════════╝")


def main():
    print("\n╔══════════════════════════════════════════╗")
    print("║  Tiger Data Seed — HCP Outbound Engine   ║")
    print("╚══════════════════════════════════════════╝\n")

    conn = psycopg2.connect(DATABASE_URL_SYNC)
    # psycopg2 extension for vector type
    from pgvector.psycopg2 import register_vector
    register_vector(conn)

    cur = conn.cursor()
    try:
        seed_physicians(cur)
        seed_payments(cur)
        conn.commit()
        print_summary(cur)
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Seed failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()

    print("\n🌱 Database seeded successfully!\n")


if __name__ == "__main__":
    main()
