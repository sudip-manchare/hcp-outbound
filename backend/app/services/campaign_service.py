"""
campaign_service.py
===================
Handles campaign tracking, secure audit token generation, and outbound
dispatch simulation for the HCP Outbound Audit & Defense engine.

Token generation is decoupled from database persistence so callers can
build a preview URL before the token is committed to storage.

Pipeline states stored on audit_tokens:
    Dispatched → Opened → Disputed → Protected
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

settings = get_settings()

# Token TTL: 7 days
TOKEN_TTL_HOURS = 168


# ---------------------------------------------------------------------------
# Pipeline states
# ---------------------------------------------------------------------------

class PipelineState:
    DISPATCHED = "dispatched"
    OPENED = "opened"
    DISPUTED = "disputed"
    PROTECTED = "protected"


PIPELINE_ORDER = [
    PipelineState.DISPATCHED,
    PipelineState.OPENED,
    PipelineState.DISPUTED,
    PipelineState.PROTECTED,
]


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def generate_audit_token(npi: str) -> str:
    """Generate a cryptographically secure, NPI-bound audit portal token.

    Format: {8-char HMAC prefix}-{64-char random hex}

    IMPORTANT: Store only the SHA-256 hash of this value in the database,
    never the plaintext token. This prevents a DB breach from enabling
    token forgery. Callers (see main.py campaign_dispatch) are responsible
    for hashing before persistence.
    """
    raw = secrets.token_hex(32)
    # FIX: Original file had `hmac.new(...)` which is correct Python stdlib.
    # Kept as-is; the real fix is in main.py where tokens are now hashed
    # before being written to audit_tokens (was stored as plaintext before).
    sig = hmac.new(
        settings.SECRET_KEY.encode(),
        f"{npi}:{raw}".encode(),
        hashlib.sha256,
    ).hexdigest()[:8]
    return f"{sig}-{raw}"


def token_expiry() -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)


# ---------------------------------------------------------------------------
# Audit portal URL builder
# ---------------------------------------------------------------------------

def build_audit_url(token: str, base_url: str | None = None) -> str:
    """Returns the full URL to the Physician Audit & Dispute Portal.

    FIX: Derives the base URL from CORS_ORIGINS config rather than hard-coding
    localhost, so production builds produce the correct absolute URL.
    """
    if base_url is None:
        # Use the first configured frontend origin; fall back to localhost.
        base_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
    return f"{base_url.rstrip('/')}/audit/{token}"


# ---------------------------------------------------------------------------
# Dispatch simulation payload
# ---------------------------------------------------------------------------

def build_dispatch_preview(
    npi: str,
    first_name: str,
    last_name: str,
    total_usd: float,
    unreviewed_count: int,
    manufacturer_count: int,
    audit_url: str,
) -> dict:
    """Builds the outbound alert preview shown in the Campaign Console.

    In production this payload would be handed to an SMS/email provider.
    Currently returned as a simulation; set simulated=False when wired to
    a real delivery channel.
    """
    return {
        "npi": npi,
        "recipient": f"Dr. {last_name}",
        "subject": f"[Action Required] CMS Open Payments — ${total_usd:,.2f} reported under your NPI",
        "body": (
            f"Dr. {last_name}, ${total_usd:,.2f} across {manufacturer_count} industry "
            f"transaction(s) was reported under your NPI ({npi}) in the current CMS Open "
            f"Payments ledger. {unreviewed_count} entr{'y' if unreviewed_count == 1 else 'ies'} "
            f"{'has' if unreviewed_count == 1 else 'have'} not been reviewed.\n\n"
            f"View your public transparency profile and generate a formal dispute before "
            f"the 45-day review window closes:\n\n{audit_url}"
        ),
        "audit_url": audit_url,
        "pipeline_state": PipelineState.DISPATCHED,
        "dispatched_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# NOTE: The raw SQL constants (INSERT_AUDIT_TOKEN_SQL, UPDATE_PIPELINE_SQL,
# GET_TOKEN_SQL, GET_CAMPAIGN_STATS_SQL) that previously used asyncpg $1-style
# placeholders have been removed from this module.
#
# FIX: The original SQL used asyncpg positional placeholders ($1, $2 …) which
# are incompatible with SQLAlchemy's asyncpg driver, which expects :named
# params. All DB operations for campaign/audit-token are now in main.py route
# handlers using SQLAlchemy text() with :named params, consistent with the
# rest of the application.
# ---------------------------------------------------------------------------
