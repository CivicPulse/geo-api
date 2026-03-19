"""Pydantic request/response models for batch geocoding and validation endpoints.

BatchItemError            — shared per-item error wrapper
BatchGeocodeRequest       — POST /geocode/batch request body
BatchGeocodeResultItem    — per-item result in batch geocode response
BatchGeocodeResponse      — POST /geocode/batch response body
BatchValidateRequest      — POST /validate/batch request body
BatchValidateResultItem   — per-item result in batch validate response
BatchValidateResponse     — POST /validate/batch response body
classify_exception        — map exception to (status_code, status, message)
"""
from pydantic import BaseModel, model_validator

from civpulse_geo.schemas.geocoding import GeocodeResponse
from civpulse_geo.schemas.validation import ValidateResponse


class BatchItemError(BaseModel):
    """Shared error wrapper for a single failed item in a batch."""

    message: str


class BatchGeocodeRequest(BaseModel):
    """POST /geocode/batch request body."""

    addresses: list[str]

    @model_validator(mode="after")
    def check_batch_size(self) -> "BatchGeocodeRequest":
        from civpulse_geo.config import settings

        if len(self.addresses) > settings.max_batch_size:
            raise ValueError(
                f"Batch size {len(self.addresses)} exceeds maximum of "
                f"{settings.max_batch_size} addresses"
            )
        return self


class BatchGeocodeResultItem(BaseModel):
    """Per-item result in the batch geocode response."""

    index: int
    original_input: str
    status_code: int  # HTTP-style: 200, 422, or 500
    status: str       # "success", "invalid_input", or "provider_error"
    data: GeocodeResponse | None = None
    error: BatchItemError | None = None


class BatchGeocodeResponse(BaseModel):
    """POST /geocode/batch response body."""

    total: int
    succeeded: int
    failed: int
    results: list[BatchGeocodeResultItem]


class BatchValidateRequest(BaseModel):
    """POST /validate/batch request body."""

    addresses: list[str]

    @model_validator(mode="after")
    def check_batch_size(self) -> "BatchValidateRequest":
        from civpulse_geo.config import settings

        if len(self.addresses) > settings.max_batch_size:
            raise ValueError(
                f"Batch size {len(self.addresses)} exceeds maximum of "
                f"{settings.max_batch_size} addresses"
            )
        return self


class BatchValidateResultItem(BaseModel):
    """Per-item result in the batch validate response."""

    index: int
    original_input: str
    status_code: int
    status: str
    data: ValidateResponse | None = None
    error: BatchItemError | None = None


class BatchValidateResponse(BaseModel):
    """POST /validate/batch response body."""

    total: int
    succeeded: int
    failed: int
    results: list[BatchValidateResultItem]


def classify_exception(exc: Exception) -> tuple[int, str, str]:
    """Map exception type to (status_code, status, message) for batch per-item results."""
    from civpulse_geo.providers.exceptions import (
        ProviderError,
        ProviderNetworkError,
        ProviderRateLimitError,
        ProviderAuthError,
    )

    if isinstance(exc, (ProviderNetworkError, ProviderRateLimitError, ProviderAuthError)):
        return 500, "provider_error", str(exc)
    if isinstance(exc, ProviderError):
        return 422, "invalid_input", str(exc)
    return 500, "provider_error", f"Unexpected error: {type(exc).__name__}"
