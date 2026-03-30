"""Pydantic request/response models for the geocoding endpoint.

GeocodeRequest       — POST /geocode request body
GeocodeProviderResult — per-provider result embedded in response
GeocodeResponse      — POST /geocode response body
SetOfficialRequest   — PUT /geocode/{hash}/official request body (GEO-06/07)
OfficialResponse     — PUT /geocode/{hash}/official response body
RefreshResponse      — POST /geocode/{hash}/refresh response body (GEO-08)
ProviderResultResponse — GET /geocode/{hash}/providers/{name} response body (GEO-09)
"""
from pydantic import BaseModel, Field


class GeocodeRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=500)


class GeocodeProviderResult(BaseModel):
    provider_name: str
    latitude: float | None = None
    longitude: float | None = None
    location_type: str | None = None
    confidence: float | None = None
    is_outlier: bool = False  # True when > 1km from winning cluster centroid (CONS-03)


class CascadeTraceStage(BaseModel):
    """Single stage entry in cascade_trace array (D-19)."""

    stage: str  # "normalize", "spell_correct", "exact_match", "fuzzy", "consensus", "auto_set"
    ms: float  # stage duration in milliseconds
    results_count: int = 0
    early_exit: bool = False
    detail: dict | None = None  # stage-specific fields


class GeocodeResponse(BaseModel):
    address_hash: str
    normalized_address: str
    cache_hit: bool
    results: list[GeocodeProviderResult]
    local_results: list[GeocodeProviderResult] = []
    official: GeocodeProviderResult | None = None
    cascade_trace: list[dict] | None = None  # Per-stage trace when trace=True or dry_run=True (D-19)
    would_set_official: GeocodeProviderResult | None = None  # dry_run only: what would have been set (D-17)


class SetOfficialRequest(BaseModel):
    """Set official geocode — either point to existing result OR provide custom coordinate.

    Exactly one of geocoding_result_id or (latitude + longitude) must be provided.
    """

    geocoding_result_id: int | None = None
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    reason: str | None = None


class OfficialResponse(BaseModel):
    address_hash: str
    official: GeocodeProviderResult
    source: str  # "provider_result" or "admin_override"


class RefreshResponse(BaseModel):
    address_hash: str
    normalized_address: str
    results: list[GeocodeProviderResult]
    refreshed_providers: list[str]


class ProviderResultResponse(BaseModel):
    address_hash: str
    provider_name: str
    latitude: float | None = None
    longitude: float | None = None
    location_type: str | None = None
    confidence: float | None = None
    raw_response: dict | None = None
