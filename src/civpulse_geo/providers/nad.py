"""NAD geocoding and validation providers.

Queries the nad_points staging table populated by the load-nad CLI command.
Both providers are local (is_local=True) and bypass the DB cache pipeline entirely.

Source data is CSV-delimited (CSVDelimited format per schema.ini) from the NAD r21 release.
Each row's Placement field is mapped to a (location_type, confidence) pair via PLACEMENT_MAP.

Key design decisions:
- _parse_input_address imported from openaddresses module to avoid code duplication.
- lat/lng extracted via ST_Y(location::geometry) and ST_X(location::geometry) in the
  same SELECT statement to avoid a second round-trip.
- PLACEMENT_MAP covers all 7 known NAD Placement values; unknowns fall back to
  DEFAULT_PLACEMENT ("APPROXIMATE", 0.1).
- geocode() accepts **kwargs to avoid TypeError when the service layer calls
  provider.geocode(normalized, http_client=http_client).
- Validation fallback uses nad_row.state (not .region) and nad_row.zip_code (not .postcode).
"""
from __future__ import annotations

from typing import Any

import usaddress
from geoalchemy2.types import Geometry
from scourgify import normalize_address_record
import sqlalchemy
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from civpulse_geo.models.nad import NADPoint
from civpulse_geo.providers.base import GeocodingProvider, ValidationProvider
from civpulse_geo.providers.exceptions import ProviderError
from civpulse_geo.providers.schemas import GeocodingResult, ValidationResult
from civpulse_geo.providers.openaddresses import _parse_input_address, FUZZY_MAX_DISTANCE

# ---------------------------------------------------------------------------
# Placement mapping constants
# ---------------------------------------------------------------------------

PLACEMENT_MAP: dict[str, tuple[str, float]] = {
    "Structure - Rooftop":  ("ROOFTOP", 1.0),
    "Structure - Entrance": ("ROOFTOP", 1.0),
    "Site":                 ("APPROXIMATE", 0.8),
    "Property Access":      ("APPROXIMATE", 0.8),
    "Parcel - Other":       ("APPROXIMATE", 0.6),
    "Linear Geocode":       ("RANGE_INTERPOLATED", 0.5),
    "Parcel - Centroid":    ("GEOMETRIC_CENTER", 0.4),
}
DEFAULT_PLACEMENT: tuple[str, float] = ("APPROXIMATE", 0.1)  # None, empty, or unknown placement


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

async def _find_nad_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postal_code: str,
) -> tuple[NADPoint, float, float] | None:
    """Query nad_points for a matching row plus lat/lng coordinates.

    Returns a tuple of (NADPoint row, lat, lng) or None if no match.
    Lat/lng are extracted in the same query via PostGIS ST_Y/ST_X to avoid a
    second round-trip. Matches on street_number, upper-cased street_name, and zip_code.
    """
    stmt = (
        select(
            NADPoint,
            func.ST_Y(NADPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(NADPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            NADPoint.street_number == street_number,
            func.upper(NADPoint.street_name) == street_name.upper(),
            NADPoint.zip_code == postal_code,
        )
        .order_by(NADPoint.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()  # Returns (NADPoint, lat, lng) or None


async def _find_nad_fuzzy_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postal_code: str,
) -> tuple[NADPoint, float, float] | None:
    """Fuzzy fallback: find the nearest address on the same street and ZIP.

    Drops the exact street_number match and instead orders by numeric distance
    from the target address number. Only returns a match if the nearest row is
    within FUZZY_MAX_DISTANCE address numbers.

    Returns (NADPoint, lat, lng) or None.
    """
    try:
        target_num = int(street_number)
    except (ValueError, TypeError):
        return None

    stmt = (
        select(
            NADPoint,
            func.ST_Y(NADPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(NADPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            func.upper(NADPoint.street_name) == street_name.upper(),
            NADPoint.zip_code == postal_code,
            NADPoint.street_number.op("~")(r"^\d+$"),
        )
        .order_by(
            func.abs(
                func.cast(NADPoint.street_number, sqlalchemy.Integer) - target_num
            )
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    row_tuple = result.first()

    if row_tuple is None:
        return None

    nad_row = row_tuple[0]
    try:
        matched_num = int(nad_row.street_number)
    except (ValueError, TypeError):
        return None

    if abs(matched_num - target_num) > FUZZY_MAX_DISTANCE:
        return None

    return row_tuple


async def _nad_data_available(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """Check whether the nad_points table contains any rows.

    Returns True if at least one row exists, False otherwise or on any error.
    Used at startup to conditionally register NAD providers.
    """
    try:
        async with session_factory() as session:
            result = await session.execute(text("SELECT EXISTS(SELECT 1 FROM nad_points LIMIT 1)"))
            return bool(result.scalar())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# NADGeocodingProvider
# ---------------------------------------------------------------------------

class NADGeocodingProvider(GeocodingProvider):
    """Geocoding provider backed by the National Address Database staging table.

    Queries the local nad_points table instead of calling a remote API.
    Returns results directly without writing to geocoding_results (is_local=True).
    NAD Placement values are mapped to (location_type, confidence) pairs via PLACEMENT_MAP.

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
        return "national_address_database"

    async def geocode(self, address: str, **kwargs: Any) -> GeocodingResult:
        """Geocode a single address against the nad_points table.

        Args:
            address: Freeform address string.
            **kwargs: Accepts http_client= and other kwargs from service layer
                without raising TypeError.

        Returns:
            GeocodingResult with Placement-mapped location_type and confidence.
            Returns NO_MATCH (confidence=0.0) if no row matches or parse fails.

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
                row_tuple = await _find_nad_match(session, street_number, street_name, postal_code)
                fuzzy = False
                if row_tuple is None:
                    row_tuple = await _find_nad_fuzzy_match(session, street_number, street_name, postal_code)
                    fuzzy = True
        except SQLAlchemyError as e:
            raise ProviderError(f"NAD query failed: {e}") from e

        if row_tuple is None:
            return GeocodingResult(
                lat=0.0,
                lng=0.0,
                location_type="NO_MATCH",
                confidence=0.0,
                raw_response={},
                provider_name=self.provider_name,
            )

        nad_row, lat, lng = row_tuple
        location_type, confidence = PLACEMENT_MAP.get(
            nad_row.placement or "", DEFAULT_PLACEMENT
        )

        # Halve confidence for fuzzy matches to signal approximate result
        if fuzzy:
            confidence *= 0.5

        raw_response: dict[str, Any] = {
            "source_hash": nad_row.source_hash,
            "street_number": nad_row.street_number,
            "street_name": nad_row.street_name,
            "street_suffix": nad_row.street_suffix,
            "unit": nad_row.unit,
            "city": nad_row.city,
            "state": nad_row.state,
            "zip_code": nad_row.zip_code,
            "placement": nad_row.placement,
            "lat": lat,
            "lng": lng,
            "fuzzy_match": fuzzy,
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
# NADValidationProvider
# ---------------------------------------------------------------------------

class NADValidationProvider(ValidationProvider):
    """Validation provider backed by the National Address Database staging table.

    Looks up the address in nad_points, then re-normalizes the matched row's
    components through scourgify to produce USPS-standard output. Falls back to
    raw NAD columns (state, zip_code) if scourgify fails on the reconstructed address.

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
        return "national_address_database"

    async def validate(self, address: str, **kwargs: Any) -> ValidationResult:
        """Validate a single address against the nad_points table.

        Matching row components are re-normalized through scourgify to produce
        USPS Pub 28 standard output. Falls back to raw NAD components if scourgify
        fails on the reconstructed address string.

        Args:
            address: Freeform address string.
            **kwargs: Accepts extra kwargs for future compatibility.

        Returns:
            ValidationResult with confidence=1.0 on match, confidence=0.0 on no match.
            delivery_point_verified is always False.
            Uses nad_row.state (not .region) and nad_row.zip_code (not .postcode).

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
                row_tuple = await _find_nad_match(session, street_number, street_name, postal_code)
        except SQLAlchemyError as e:
            raise ProviderError(f"NAD query failed: {e}") from e

        if row_tuple is None:
            return no_match_result

        nad_row, _lat, _lng = row_tuple

        # Build address string from NAD components for scourgify re-normalization
        suffix = (nad_row.street_suffix or "").strip()
        street_line = f"{nad_row.street_number or ''} {nad_row.street_name or ''} {suffix}".strip()
        city_str = nad_row.city or ""
        state_str = nad_row.state or ""       # Note: .state, not .region
        zip_str = nad_row.zip_code or ""      # Note: .zip_code, not .postcode
        reconstructed = f"{street_line}, {city_str}, {state_str} {zip_str}".strip(", ")

        try:
            scourgify_parsed = normalize_address_record(reconstructed)
            address_line_1 = (scourgify_parsed.get("address_line_1") or "").strip()
            address_line_2_raw = (scourgify_parsed.get("address_line_2") or "").strip() or None
            city_out = (scourgify_parsed.get("city") or "").strip() or None
            state_out = (scourgify_parsed.get("state") or "").strip() or None
            postal_out = (scourgify_parsed.get("postal_code") or "").strip() or None
        except Exception:
            # Fallback: build directly from raw NAD components
            address_line_1 = street_line
            address_line_2_raw = None
            city_out = nad_row.city or None
            state_out = nad_row.state or None         # .state, not .region
            postal_out = nad_row.zip_code or None     # .zip_code, not .postcode

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
