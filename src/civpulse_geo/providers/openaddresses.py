"""OpenAddresses geocoding and validation providers.

Queries the openaddresses_points staging table populated by the load-oa CLI command.
Both providers are local (is_local=True) and bypass the DB cache pipeline entirely.

Key design decisions:
- lat/lng extracted via ST_Y(location::geometry) and ST_X(location::geometry) in the
  same SELECT statement to avoid a second round-trip.
- _parse_input_address uses scourgify for normalization and usaddress for token parsing
  to extract street_number and street_name from address_line_1.
- On scourgify parse failure during input parsing, (None, None, None) is returned and
  the caller returns a NO_MATCH result.
- geocode() accepts **kwargs to avoid TypeError when the service layer calls
  provider.geocode(normalized, http_client=http_client).
"""
from __future__ import annotations

from typing import Any

import usaddress
from geoalchemy2.types import Geometry
from scourgify import normalize_address_record
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from civpulse_geo.models.openaddresses import OpenAddressesPoint
from civpulse_geo.providers.base import GeocodingProvider, ValidationProvider
from civpulse_geo.providers.exceptions import ProviderError
from civpulse_geo.providers.schemas import GeocodingResult, ValidationResult

# ---------------------------------------------------------------------------
# Accuracy mapping constants
# ---------------------------------------------------------------------------

ACCURACY_MAP: dict[str, tuple[str, float]] = {
    "rooftop": ("ROOFTOP", 1.0),
    "parcel": ("APPROXIMATE", 0.8),
    "interpolation": ("RANGE_INTERPOLATED", 0.5),
    "centroid": ("GEOMETRIC_CENTER", 0.4),
}
DEFAULT_ACCURACY: tuple[str, float] = ("APPROXIMATE", 0.1)  # empty string or unknown


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _parse_input_address(address: str) -> tuple[str | None, str | None, str | None]:
    """Parse a freeform address string into (street_number, street_name, postal_code).

    Uses scourgify for USPS normalization and usaddress for token-level parsing of the
    street line. Returns (None, None, None) on any parse failure.
    """
    try:
        parsed = normalize_address_record(address)
    except Exception:
        return (None, None, None)

    postal_code = (parsed.get("postal_code") or "").strip() or None
    address_line_1 = (parsed.get("address_line_1") or "").strip()

    if not address_line_1:
        return (None, None, None)

    try:
        tokens, _ = usaddress.tag(address_line_1)
    except usaddress.RepeatedLabelError:
        return (None, None, None)

    street_number = tokens.get("AddressNumber")
    # Collect all StreetName tokens (may be multiple for compound names like "MARTIN LUTHER KING")
    street_name_parts = [
        v for k, v in tokens.items()
        if k == "StreetName"
    ]
    street_name = " ".join(street_name_parts).strip() or None

    return (street_number, street_name, postal_code)


async def _find_oa_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postcode: str,
) -> tuple[OpenAddressesPoint, float, float] | None:
    """Query openaddresses_points for a matching row plus lat/lng coordinates.

    Returns a tuple of (OpenAddressesPoint row, lat, lng) or None if no match.
    Lat/lng are extracted in the same query via PostGIS ST_Y/ST_X to avoid a
    second round-trip.
    """
    stmt = (
        select(
            OpenAddressesPoint,
            func.ST_Y(OpenAddressesPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(OpenAddressesPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            OpenAddressesPoint.street_number == street_number,
            func.upper(OpenAddressesPoint.street_name) == street_name.upper(),
            OpenAddressesPoint.postcode == postcode,
        )
        .order_by(OpenAddressesPoint.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()  # Returns (OpenAddressesPoint, lat, lng) or None


# ---------------------------------------------------------------------------
# OAGeocodingProvider
# ---------------------------------------------------------------------------

class OAGeocodingProvider(GeocodingProvider):
    """Geocoding provider backed by the OpenAddresses staging table.

    Queries the local openaddresses_points table instead of calling a remote API.
    Returns results directly without writing to geocoding_results (is_local=True).

    Args:
        session_factory: async_sessionmaker[AsyncSession] for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def is_local(self) -> bool:
        """Always True — this provider queries a local staging table."""
        return True

    @property
    def provider_name(self) -> str:
        return "openaddresses"

    async def geocode(self, address: str, **kwargs: Any) -> GeocodingResult:
        """Geocode a single address against the openaddresses_points table.

        Args:
            address: Freeform address string.
            **kwargs: Accepts http_client= and other kwargs from service layer
                without raising TypeError.

        Returns:
            GeocodingResult with accuracy-mapped location_type and confidence.
            Returns NO_MATCH (confidence=0.0) if no row matches.

        Raises:
            ProviderError: On SQLAlchemy database error.
        """
        street_number, street_name, postal_code = _parse_input_address(address)

        # If parsing failed, return NO_MATCH immediately (no DB query needed)
        if street_number is None or street_name is None or postal_code is None:
            return GeocodingResult(
                lat=0.0,
                lng=0.0,
                location_type="NO_MATCH",
                confidence=0.0,
                raw_response={},
                provider_name=self.provider_name,
            )

        try:
            async with self._session_factory() as session:
                row_tuple = await _find_oa_match(session, street_number, street_name, postal_code)
        except SQLAlchemyError as e:
            raise ProviderError(f"OpenAddresses query failed: {e}") from e

        if row_tuple is None:
            return GeocodingResult(
                lat=0.0,
                lng=0.0,
                location_type="NO_MATCH",
                confidence=0.0,
                raw_response={},
                provider_name=self.provider_name,
            )

        oa_row, lat, lng = row_tuple
        location_type, confidence = ACCURACY_MAP.get(
            oa_row.accuracy or "", DEFAULT_ACCURACY
        )

        raw_response: dict[str, Any] = {
            "source_hash": oa_row.source_hash,
            "street_number": oa_row.street_number,
            "street_name": oa_row.street_name,
            "street_suffix": oa_row.street_suffix,
            "city": oa_row.city,
            "region": oa_row.region,
            "postcode": oa_row.postcode,
            "accuracy": oa_row.accuracy,
            "lat": lat,
            "lng": lng,
        }

        return GeocodingResult(
            lat=lat,
            lng=lng,
            location_type=location_type,
            confidence=confidence,
            raw_response=raw_response,
            provider_name=self.provider_name,
        )

    async def batch_geocode(
        self, addresses: list[str], **kwargs: Any
    ) -> list[GeocodingResult]:
        """Geocode a list of addresses serially.

        Args:
            addresses: List of freeform address strings.
            **kwargs: Forwarded to geocode().

        Returns:
            List of GeocodingResult in the same order as input.
        """
        results = []
        for addr in addresses:
            result = await self.geocode(addr, **kwargs)
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# OAValidationProvider
# ---------------------------------------------------------------------------

class OAValidationProvider(ValidationProvider):
    """Validation provider backed by the OpenAddresses staging table.

    Looks up the address in openaddresses_points, then re-normalizes the matched
    row's components through scourgify to produce USPS-standard output.

    Args:
        session_factory: async_sessionmaker[AsyncSession] for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def is_local(self) -> bool:
        """Always True — this provider queries a local staging table."""
        return True

    @property
    def provider_name(self) -> str:
        return "openaddresses"

    async def validate(self, address: str, **kwargs: Any) -> ValidationResult:
        """Validate a single address against the openaddresses_points table.

        Matching row components are re-normalized through scourgify to produce
        USPS Pub 28 standard output. Falls back to raw OA components if scourgify
        fails on the reconstructed address string.

        Args:
            address: Freeform address string.
            **kwargs: Accepts extra kwargs for future compatibility.

        Returns:
            ValidationResult with confidence=1.0 on match, confidence=0.0 on no match.
            delivery_point_verified is always False.

        Raises:
            ProviderError: On SQLAlchemy database error.
        """
        street_number, street_name, postal_code = _parse_input_address(address)

        no_match_result = ValidationResult(
            normalized_address="",
            address_line_1="",
            address_line_2=None,
            city=None,
            state=None,
            postal_code=None,
            confidence=0.0,
            delivery_point_verified=False,
            provider_name=self.provider_name,
            original_input=address,
        )

        if street_number is None or street_name is None or postal_code is None:
            return no_match_result

        try:
            async with self._session_factory() as session:
                row_tuple = await _find_oa_match(session, street_number, street_name, postal_code)
        except SQLAlchemyError as e:
            raise ProviderError(f"OpenAddresses query failed: {e}") from e

        if row_tuple is None:
            return no_match_result

        oa_row, _lat, _lng = row_tuple

        # Build address string from OA components for scourgify re-normalization
        suffix = (oa_row.street_suffix or "").strip()
        street_line = f"{oa_row.street_number or ''} {oa_row.street_name or ''} {suffix}".strip()
        city_str = oa_row.city or ""
        region_str = oa_row.region or ""
        postcode_str = oa_row.postcode or ""
        reconstructed = f"{street_line}, {city_str}, {region_str} {postcode_str}".strip(", ")

        try:
            scourgify_parsed = normalize_address_record(reconstructed)
            address_line_1 = (scourgify_parsed.get("address_line_1") or "").strip()
            address_line_2_raw = (scourgify_parsed.get("address_line_2") or "").strip() or None
            city_out = (scourgify_parsed.get("city") or "").strip() or None
            state_out = (scourgify_parsed.get("state") or "").strip() or None
            postal_out = (scourgify_parsed.get("postal_code") or "").strip() or None
        except Exception:
            # Fallback: build directly from raw OA components
            address_line_1 = street_line
            address_line_2_raw = None
            city_out = oa_row.city or None
            state_out = oa_row.region or None
            postal_out = oa_row.postcode or None

        # Build normalized_address from non-None parts
        parts = [
            p for p in [address_line_1, address_line_2_raw, city_out, state_out, postal_out]
            if p
        ]
        normalized_address = " ".join(parts) if parts else address_line_1

        return ValidationResult(
            normalized_address=normalized_address,
            address_line_1=address_line_1,
            address_line_2=address_line_2_raw,
            city=city_out,
            state=state_out,
            postal_code=postal_out,
            confidence=1.0,
            delivery_point_verified=False,
            provider_name=self.provider_name,
            original_input=address,
        )

    async def batch_validate(
        self, addresses: list[str], **kwargs: Any
    ) -> list[ValidationResult]:
        """Validate a list of addresses serially.

        Args:
            addresses: List of freeform address strings.
            **kwargs: Forwarded to validate().

        Returns:
            List of ValidationResult in the same order as input.
        """
        results = []
        for addr in addresses:
            result = await self.validate(addr, **kwargs)
            results.append(result)
        return results
