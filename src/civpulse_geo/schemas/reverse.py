"""Pydantic schema for the reverse geocoding endpoint (GEO-03)."""
from typing import Any

from pydantic import BaseModel


class ReverseGeocodeResponse(BaseModel):
    """Response schema for GET /geocode/reverse.

    Fields:
        address: Human-readable address string from Nominatim display_name.
        lat: Latitude of the matched location.
        lon: Longitude of the matched location.
        place_id: Nominatim place_id, if present.
        raw: Full raw Nominatim response dict.
    """

    address: str
    lat: float
    lon: float
    place_id: int | None = None
    raw: dict[str, Any]
