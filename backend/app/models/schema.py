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
