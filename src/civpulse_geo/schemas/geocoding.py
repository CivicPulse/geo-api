"""Pydantic request/response models for the geocoding endpoint.

GeocodeRequest   — POST /geocode request body
GeocodeProviderResult — per-provider result embedded in response
GeocodeResponse  — POST /geocode response body
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
    official: GeocodeProviderResult | None = None
