"""Pydantic schemas for POI search endpoint (GEO-03, GEO-04)."""
from pydantic import BaseModel


class POIResult(BaseModel):
    """A single POI result from Nominatim /search."""

    name: str
    lat: float
    lon: float
    type: str | None = None
    address: str | None = None
    place_id: int | None = None


class POISearchResponse(BaseModel):
    """Response envelope for GET /poi/search."""

    results: list[POIResult]
    count: int
