"""
campaign_service.py
===================
Handles campaign tracking, secure audit token generation, and outbound
dispatch simulation for the HCP Outbound Audit & Defense engine.

No external SMS provider is required. The service:
  - Generates cryptographically signed, expiring tokens for the /audit/{token} portal.
  - Stores dispatch records and pipeline conversion states in Tiger Data.
  - Tracks physician funnel progression:
      Dispatched → Opened → Disputed → Protected

Pipeline states are stored on audit_tokens and can be queried in real time
by the Campaign Command Console frontend.
"""

import secrets
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import get_settings

settings = get_settings()

# Token TTL: 7 days (plenty for a hackathon demo)
TOKEN_TTL_HOURS = 168

# ---------------------------------------------------------------------------
# Pipeline states
# ---------------------------------------------------------------------------

class PipelineState:
    DISPATCHED = "dispatched"
    OPENED     = "opened"
    DISPUTED   = "disputed"
    PROTECTED  = "protected"

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
    """
    Generate a cryptographically secure, NPI-bound audit portal token.

    The token is a 32-byte random hex string prefixed with a 4-char HMAC
    checksum so the backend can verify it was issued by us without a DB lookup.

    Format: {8-char HMAC prefix}-{64-char random hex}
    """
    raw = secrets.token_hex(32)
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

def build_audit_url(token: str, base_url: str = "http://localhost:3000") -> str:
    """Returns the full URL to the Physician Audit & Dispute Portal."""
    return f"{base_url}/audit/{token}"


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
    """
    Builds the outbound alert preview object shown in the Campaign Console
    before the user clicks 'Dispatch Sunshine Alert'.

    In production this payload would be handed to an email / SMS / push
    provider. In the hackathon demo it is rendered in the UI and a real
    link is generated that opens the Audit Portal.
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
# DB helpers (sync, used by FastAPI endpoints via asyncpg raw queries)
# ---------------------------------------------------------------------------

INSERT_AUDIT_TOKEN_SQL = """
    INSERT INTO audit_tokens (token, npi, expires_at, accessed, pipeline_state)
    VALUES ($1, $2, $3, FALSE, $4)
    ON CONFLICT (token) DO NOTHING;
"""

UPDATE_PIPELINE_SQL = """
    UPDATE audit_tokens
    SET pipeline_state = $1,
        accessed = CASE WHEN $1 != 'dispatched' THEN TRUE ELSE accessed END
    WHERE token = $2;
"""

GET_TOKEN_SQL = """
    SELECT npi, expires_at, accessed, pipeline_state
    FROM audit_tokens
    WHERE token = $1;
"""

GET_CAMPAIGN_STATS_SQL = """
    SELECT
        COUNT(*) FILTER (WHERE pipeline_state = 'dispatched')  AS dispatched,
        COUNT(*) FILTER (WHERE pipeline_state = 'opened')      AS opened,
        COUNT(*) FILTER (WHERE pipeline_state = 'disputed')    AS disputed,
        COUNT(*) FILTER (WHERE pipeline_state = 'protected')   AS protected
    FROM audit_tokens
    WHERE expires_at > NOW();
"""
