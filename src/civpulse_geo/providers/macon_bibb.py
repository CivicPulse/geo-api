"""Macon-Bibb County GIS geocoding and validation providers.

Queries the macon_bibb_points staging table populated by the load-macon-bibb CLI command.
Both providers are local (is_local=True) and bypass the DB cache pipeline entirely.

Source data is GeoJSON from Macon-Bibb County GIS (data/Address_Points.geojson).
The ADDType field is mapped to (location_type, confidence) via ADDRESS_TYPE_MAP.

Key design decisions:
- _parse_input_address imported from openaddresses module to avoid code duplication.
- lat/lng extracted via ST_Y(location::geometry) and ST_X(location::geometry) in the
  same SELECT statement to avoid a second round-trip.
- ADDRESS_TYPE_MAP covers PARCEL, STRUCTURE, SITE; unknowns fall to DEFAULT_ADDRESS_TYPE.
- geocode() accepts **kwargs to avoid TypeError when the service layer calls
  provider.geocode(normalized, http_client=http_client).
- Validation fallback uses macon_bibb_row.state and macon_bibb_row.zip_code (NAD pattern).
"""
from __future__ import annotations

from typing import Any

from geoalchemy2.types import Geometry
from scourgify import normalize_address_record
import sqlalchemy
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from civpulse_geo.models.macon_bibb import MaconBibbPoint
from civpulse_geo.providers.base import GeocodingProvider, ValidationProvider
from civpulse_geo.providers.exceptions import ProviderError
from civpulse_geo.providers.schemas import GeocodingResult, ValidationResult
from civpulse_geo.providers.openaddresses import _parse_input_address, FUZZY_MAX_DISTANCE

# ---------------------------------------------------------------------------
# ADDType mapping constants
# ---------------------------------------------------------------------------

ADDRESS_TYPE_MAP: dict[str, tuple[str, float]] = {
    "PARCEL":    ("APPROXIMATE", 0.8),
    "STRUCTURE": ("ROOFTOP", 1.0),
    "SITE":      ("APPROXIMATE", 0.8),
}
DEFAULT_ADDRESS_TYPE: tuple[str, float] = ("APPROXIMATE", 0.1)  # None, empty, or unknown


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

async def _macon_bibb_data_available(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """Check whether the macon_bibb_points table contains any rows.

    Returns True if at least one row exists, False otherwise or on any error.
    Used at startup to conditionally register Macon-Bibb providers.
    """
    try:
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT EXISTS(SELECT 1 FROM macon_bibb_points LIMIT 1)")
            )
            return bool(result.scalar())
    except Exception:
        return False


async def _find_macon_bibb_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postal_code: str,
    street_suffix: str | None = None,
) -> tuple[MaconBibbPoint, float, float] | None:
    """Query macon_bibb_points for a matching row plus lat/lng coordinates.

    Returns a tuple of (MaconBibbPoint row, lat, lng) or None if no match.
    Lat/lng are extracted in the same query via PostGIS ST_Y/ST_X to avoid a
    second round-trip. Matches on street_number, upper-cased street_name, and zip_code.
    When street_suffix is provided, it is included in the WHERE clause (D-07).
    """
    stmt = (
        select(
            MaconBibbPoint,
            func.ST_Y(MaconBibbPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(MaconBibbPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            MaconBibbPoint.street_number == street_number,
            func.upper(MaconBibbPoint.street_name) == street_name.upper(),
            MaconBibbPoint.zip_code == postal_code,
            # D-07: include suffix when available; fall back to name-only if suffix is NULL
            *(
                [func.upper(MaconBibbPoint.street_suffix) == street_suffix.upper()]
                if street_suffix
                else []
            ),
        )
        .order_by(MaconBibbPoint.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()


async def _find_macon_bibb_fuzzy_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postal_code: str,
    street_suffix: str | None = None,
) -> tuple[MaconBibbPoint, float, float] | None:
    """Fuzzy fallback: find the nearest address on the same street and ZIP.

    Drops the exact street_number match and instead orders by numeric distance
    from the target address number. Only returns a match if the nearest row is
    within FUZZY_MAX_DISTANCE address numbers. When street_suffix is provided,
    it is included in the WHERE clause (D-07).

    Returns (MaconBibbPoint, lat, lng) or None.
    """
    try:
        target_num = int(street_number)
    except (ValueError, TypeError):
        return None

    stmt = (
        select(
            MaconBibbPoint,
            func.ST_Y(MaconBibbPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(MaconBibbPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            func.upper(MaconBibbPoint.street_name) == street_name.upper(),
            MaconBibbPoint.zip_code == postal_code,
            MaconBibbPoint.street_number.op("~")(r"^\d+$"),
            # D-07: include suffix when available
            *(
                [func.upper(MaconBibbPoint.street_suffix) == street_suffix.upper()]
                if street_suffix
                else []
            ),
        )
        .order_by(
            func.abs(
                func.cast(MaconBibbPoint.street_number, sqlalchemy.Integer) - target_num
            )
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    row_tuple = result.first()

    if row_tuple is None:
        return None

    mb_row = row_tuple[0]
    try:
        matched_num = int(mb_row.street_number)
    except (ValueError, TypeError):
        return None

    if abs(matched_num - target_num) > FUZZY_MAX_DISTANCE:
        return None

    return row_tuple


async def _find_macon_bibb_zip_prefix_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    zip_prefix: str,
    street_suffix: str | None = None,
) -> tuple[MaconBibbPoint, float, float] | None:
    """ZIP prefix fallback: find a match using a LIKE prefix on zip_code (D-04/D-06).

    Used when the input postal_code is fewer than 5 digits (truncated ZIP). Queries
    with zip_code LIKE '{zip_prefix}%' and orders results lexicographically so that
    adjacent ZIP codes are returned first.

    Returns (MaconBibbPoint, lat, lng) or None.
    """
    stmt = (
        select(
            MaconBibbPoint,
            func.ST_Y(MaconBibbPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(MaconBibbPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            MaconBibbPoint.street_number == street_number,
            func.upper(MaconBibbPoint.street_name) == street_name.upper(),
            MaconBibbPoint.zip_code.like(f"{zip_prefix}%"),
            # D-07: include suffix when available
            *(
                [func.upper(MaconBibbPoint.street_suffix) == street_suffix.upper()]
                if street_suffix
                else []
            ),
        )
        .order_by(MaconBibbPoint.zip_code.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()


# ---------------------------------------------------------------------------
# MaconBibbGeocodingProvider
# ---------------------------------------------------------------------------

class MaconBibbGeocodingProvider(GeocodingProvider):
    """Geocoding provider backed by the Macon-Bibb County GIS address points table.

    Queries the local macon_bibb_points table instead of calling a remote API.
    Returns results directly without writing to geocoding_results (is_local=True).
    ADDType values are mapped to (location_type, confidence) pairs via ADDRESS_TYPE_MAP.

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
        return "macon_bibb"

    async def geocode(self, address: str, **kwargs: Any) -> GeocodingResult:
        """Geocode a single address against the macon_bibb_points table.

        Args:
            address: Freeform address string.
            **kwargs: Accepts http_client= and other kwargs from service layer
                without raising TypeError.

        Returns:
            GeocodingResult with ADDType-mapped location_type and confidence.
            Returns NO_MATCH (confidence=0.0) if no row matches or parse fails.

        Raises:
            ProviderError: On SQLAlchemy database error.
        """
        street_number, street_name, postal_code, street_suffix, street_directional = _parse_input_address(address)

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
                row_tuple = await _find_macon_bibb_match(
                    session, street_number, street_name, postal_code, street_suffix
                )
                fuzzy = False
                if row_tuple is None:
                    row_tuple = await _find_macon_bibb_fuzzy_match(
                        session, street_number, street_name, postal_code, street_suffix
                    )
                    fuzzy = True
                # FIX-02: ZIP prefix fallback for truncated zips
                if row_tuple is None and len(postal_code) < 5:
                    row_tuple = await _find_macon_bibb_zip_prefix_match(
                        session, street_number, street_name,
                        postal_code[:4] if len(postal_code) >= 4 else postal_code,
                        street_suffix,
                    )
                    if row_tuple is None and len(postal_code) >= 3:
                        row_tuple = await _find_macon_bibb_zip_prefix_match(
                            session, street_number, street_name, postal_code[:3], street_suffix
                        )
        except SQLAlchemyError as e:
            raise ProviderError(f"Macon-Bibb query failed: {e}") from e

        if row_tuple is None:
            return GeocodingResult(
                lat=0.0,
                lng=0.0,
                location_type="NO_MATCH",
                confidence=0.0,
                raw_response={},
                provider_name=self.provider_name,
            )

        mb_row, lat, lng = row_tuple
        location_type, confidence = ADDRESS_TYPE_MAP.get(
            mb_row.address_type or "", DEFAULT_ADDRESS_TYPE
        )

        # Halve confidence for fuzzy matches to signal approximate result
        if fuzzy:
            confidence *= 0.5

        raw_response: dict[str, Any] = {
            "source_hash": mb_row.source_hash,
            "street_number": mb_row.street_number,
            "street_name": mb_row.street_name,
            "street_suffix": mb_row.street_suffix,
            "unit": mb_row.unit,
            "city": mb_row.city,
            "state": mb_row.state,
            "zip_code": mb_row.zip_code,
            "address_type": mb_row.address_type,
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
# MaconBibbValidationProvider
# ---------------------------------------------------------------------------

class MaconBibbValidationProvider(ValidationProvider):
    """Validation provider backed by the Macon-Bibb County GIS address points table.

    Looks up the address in macon_bibb_points, then re-normalizes the matched row's
    components through scourgify to produce USPS-standard output. Falls back to
    raw columns (state, zip_code) if scourgify fails on the reconstructed address.

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
        return "macon_bibb"

    async def validate(self, address: str, **kwargs: Any) -> ValidationResult:
        """Validate a single address against the macon_bibb_points table.

        Matching row components are re-normalized through scourgify to produce
        USPS Pub 28 standard output. Falls back to raw columns if scourgify fails.

        Args:
            address: Freeform address string.
            **kwargs: Accepts extra kwargs for future compatibility.

        Returns:
            ValidationResult with confidence=1.0 on match, confidence=0.0 on no match.
            delivery_point_verified is always False.
            Uses mb_row.state and mb_row.zip_code (NAD pattern).

        Raises:
            ProviderError: On SQLAlchemy database error.
        """
        street_number, street_name, postal_code, street_suffix, street_directional = _parse_input_address(address)

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
                row_tuple = await _find_macon_bibb_match(
                    session, street_number, street_name, postal_code, street_suffix
                )
                # FIX-02: ZIP prefix fallback for truncated zips
                if row_tuple is None and len(postal_code) < 5:
                    row_tuple = await _find_macon_bibb_zip_prefix_match(
                        session, street_number, street_name,
                        postal_code[:4] if len(postal_code) >= 4 else postal_code,
                        street_suffix,
                    )
                    if row_tuple is None and len(postal_code) >= 3:
                        row_tuple = await _find_macon_bibb_zip_prefix_match(
                            session, street_number, street_name, postal_code[:3], street_suffix
                        )
        except SQLAlchemyError as e:
            raise ProviderError(f"Macon-Bibb query failed: {e}") from e

        if row_tuple is None:
            return no_match_result

        mb_row, _lat, _lng = row_tuple

        # Build address string from row components for scourgify re-normalization
        suffix = (mb_row.street_suffix or "").strip()
        street_line = f"{mb_row.street_number or ''} {mb_row.street_name or ''} {suffix}".strip()
        city_str = mb_row.city or ""
        state_str = mb_row.state or ""       # .state, not .region
        zip_str = mb_row.zip_code or ""      # .zip_code, not .postcode
        reconstructed = f"{street_line}, {city_str}, {state_str} {zip_str}".strip(", ")

        try:
            scourgify_parsed = normalize_address_record(reconstructed)
            address_line_1 = (scourgify_parsed.get("address_line_1") or "").strip()
            address_line_2_raw = (scourgify_parsed.get("address_line_2") or "").strip() or None
            city_out = (scourgify_parsed.get("city") or "").strip() or None
            state_out = (scourgify_parsed.get("state") or "").strip() or None
            postal_out = (scourgify_parsed.get("postal_code") or "").strip() or None
        except Exception:
            # Fallback: build directly from raw row components
            address_line_1 = street_line
            address_line_2_raw = None
            city_out = mb_row.city or None
            state_out = mb_row.state or None       # .state, not .region
            postal_out = mb_row.zip_code or None   # .zip_code, not .postcode

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
