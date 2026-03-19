"""Structured result schemas for geocoding providers.

Defines GeocodingResult, the canonical output type for all GeocodingProvider
implementations. Using a dataclass enforces consistent field names and types
across providers, enabling fair comparison and admin override logic.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class GeocodingResult:
    """Canonical geocoding result returned by all GeocodingProvider implementations.

    Fields:
        lat: Latitude in decimal degrees (WGS84).
        lng: Longitude in decimal degrees (WGS84).
        location_type: Precision descriptor — matches LocationType enum values:
            ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE.
        confidence: Confidence score from 0.0 to 1.0. Provider-specific meaning;
            higher = more precise.
        raw_response: Unmodified response dict from the upstream provider API.
            Preserved for audit and debugging.
        provider_name: Identifies which provider produced this result.
            Matches the key used in the provider registry.
    """
    lat: float
    lng: float
    location_type: str      # matches LocationType enum values
    confidence: float       # 0.0 to 1.0
    raw_response: dict[str, Any]
    provider_name: str
