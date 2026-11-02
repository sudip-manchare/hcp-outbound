from pydantic import BaseModel, Field


class LocalPaymentReviewUpdate(BaseModel):
    """Mutable local metadata; never used to overwrite a CMS source record."""

    is_reviewed: bool | None = None
    mismatch_score: float | None = Field(default=None, ge=0, le=1)


class CMSIngestionRequest(BaseModel):
    """One bounded CMS page requested by the frontend's pull-latest action."""

    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    recipient_state: str | None = Field(default=None, min_length=2, max_length=2)
    manufacturer_id: str | None = None
    payment_nature: str | None = None
    recipient_type: str | None = None


# FIX: New models for previously-missing campaign and dispute endpoints.
# Without these, the frontend POST bodies had no validated schema.

class CampaignDispatchRequest(BaseModel):
    """Request body for dispatching an outbound audit alert to a physician."""

    npi: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    channel: str = Field(default="portal_link")


class DisputeGenerateRequest(BaseModel):
    """Request body for generating a 42 CFR § 403.908 dispute notice draft.

    The audit_token field binds the request to a specific physician identity,
    preventing unauthenticated callers from generating dispute notices for
    arbitrary NPIs. The token proves the caller holds the physician's audit link.
    """

    npi: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    audit_token: str = Field(
        ...,
        min_length=10,
        description="Signed audit portal token issued by campaign dispatch.",
    )
