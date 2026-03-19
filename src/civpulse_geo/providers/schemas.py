"""Structured result schemas for geocoding and validation providers.

Defines GeocodingResult and ValidationResult, the canonical output types for all
GeocodingProvider and ValidationProvider implementations respectively. Using
dataclasses enforces consistent field names and types across providers, enabling
fair comparison and admin override logic.
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


@dataclass
class ValidationResult:
    """Canonical validation result returned by all ValidationProvider implementations.

    Fields:
        normalized_address: Full USPS-normalized address string, e.g. "123 MAIN ST MACON GA 31201".
        address_line_1: Normalized street line, e.g. "123 MAIN ST".
        address_line_2: Secondary designator, e.g. "APT 4B", or None.
        city: City name in uppercase, e.g. "MACON", or None if unparseable.
        state: Two-letter USPS state abbreviation, e.g. "GA", or None.
        postal_code: ZIP code (ZIP5 or ZIP+4), e.g. "31201" or "31201-5678", or None.
        confidence: Confidence score from 0.0 to 1.0. For scourgify, always 1.0 on success.
        delivery_point_verified: True only if the provider confirms mail-deliverable address.
            Always False for scourgify (offline normalization only).
        provider_name: Identifies which provider produced this result.
        original_input: Echo of the raw input string for "did you mean?" UI flows.
    """
    normalized_address: str          # Full USPS normalized: "123 MAIN ST MACON GA 31201"
    address_line_1: str              # "123 MAIN ST"
    address_line_2: str | None       # "APT 4B" or None
    city: str | None                 # "MACON"
    state: str | None                # "GA"
    postal_code: str | None          # "31201" or "31201-5678" (scourgify preserves ZIP+4)
    confidence: float                # 1.0 for scourgify success
    delivery_point_verified: bool    # Always False for scourgify-only
    provider_name: str               # "scourgify"
    original_input: str              # Echo back input for "did you mean?" UI
