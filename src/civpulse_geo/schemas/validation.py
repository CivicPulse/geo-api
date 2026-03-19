"""Pydantic request/response models for the address validation endpoint.

ValidateRequest  — POST /validate request body (freeform or structured)
ValidationCandidate — per-provider candidate in the response
ValidateResponse — POST /validate response body
"""
from pydantic import BaseModel, model_validator


class ValidateRequest(BaseModel):
    """Accept freeform OR structured address input.

    Either 'address' (freeform) or at least 'street' (structured) must be provided.
    Both can be provided, in which case 'address' takes precedence for to_freeform().
    """

    address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None

    @model_validator(mode="after")
    def check_at_least_one_input(self) -> "ValidateRequest":
        if not self.address and not self.street:
            raise ValueError("Provide either 'address' (freeform) or at least 'street' (structured)")
        return self

    def to_freeform(self) -> str:
        """Return a single freeform address string.

        If 'address' is set, return it directly (freeform path).
        Otherwise join structured fields: street, city, state, zip_code (omitting None values).
        """
        if self.address:
            return self.address
        parts = [p for p in [self.street, self.city, self.state, self.zip_code] if p]
        return ", ".join(parts)


class ValidationCandidate(BaseModel):
    """Per-provider normalized address candidate returned in ValidateResponse."""

    normalized_address: str
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    confidence: float
    delivery_point_verified: bool
    provider_name: str


class ValidateResponse(BaseModel):
    """Response body for POST /validate."""

    address_hash: str
    original_input: str
    candidates: list[ValidationCandidate]
    cache_hit: bool
