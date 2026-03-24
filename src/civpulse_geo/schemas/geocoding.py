"""Pydantic request/response models for the geocoding endpoint.

GeocodeRequest       — POST /geocode request body
GeocodeProviderResult — per-provider result embedded in response
GeocodeResponse      — POST /geocode response body
SetOfficialRequest   — PUT /geocode/{hash}/official request body (GEO-06/07)
OfficialResponse     — PUT /geocode/{hash}/official response body
RefreshResponse      — POST /geocode/{hash}/refresh response body (GEO-08)
ProviderResultResponse — GET /geocode/{hash}/providers/{name} response body (GEO-09)
"""
from pydantic import BaseModel


class GeocodeRequest(BaseModel):
    address: str


class GeocodeProviderResult(BaseModel):
    provider_name: str
    latitude: float | None = None
    longitude: float | None = None
    location_type: str | None = None
    confidence: float | None = None


class GeocodeResponse(BaseModel):
    address_hash: str
    normalized_address: str
    cache_hit: bool
    results: list[GeocodeProviderResult]
    local_results: list[GeocodeProviderResult] = []
    official: GeocodeProviderResult | None = None


class SetOfficialRequest(BaseModel):
    """Set official geocode — either point to existing result OR provide custom coordinate.

    Exactly one of geocoding_result_id or (latitude + longitude) must be provided.
    """

    geocoding_result_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
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
