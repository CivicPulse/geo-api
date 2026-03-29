"""PostGIS Tiger geocoding and validation providers.

Unlike the OpenAddresses provider (which queries a staging table), these providers
call PostGIS SQL functions directly:
- geocode(:address, 1)          -> Tiger/Line address interpolation
- normalize_address(:address)   -> USPS component parsing via Tiger norm_addy type

Both providers are local (is_local=True) and bypass the DB cache pipeline entirely.

Key design decisions:
- SQL constants are module-level text() objects to ensure a single compilation
  and to make the query intent clear to readers.
- Confidence = max(0.0, min(1.0, (100 - rating) / 100)) — Tiger rating 0 is a
  perfect match (1.0 confidence), rating 100 is complete miss (0.0), and ratings
  above 100 are clamped to 0.0 (never negative).
- _tiger_extension_available() is a startup guard that checks pg_extension (installed extensions);
  it returns False on any exception so startup never crashes if Tiger is absent.
- geocode() accepts **kwargs so the service layer can pass http_client= without TypeError.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from civpulse_geo.providers.base import GeocodingProvider, ValidationProvider
from civpulse_geo.providers.exceptions import ProviderError
from civpulse_geo.providers.schemas import GeocodingResult, ValidationResult


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

GEOCODE_SQL = text("""
    SELECT
        rating,
        ST_Y(geomout) AS lat,
        ST_X(geomout) AS lng,
        (addy).address        AS address_number,
        (addy).predirabbrev   AS predir,
        (addy).streetname     AS street_name,
        (addy).streettypeabbrev AS street_type,
        (addy).postdirabbrev  AS postdir,
        (addy).internal       AS internal,
        (addy).location       AS city,
        (addy).stateabbrev    AS state,
        (addy).zip            AS zip,
        (addy).zip4           AS zip4,
        (addy).parsed         AS parsed
    FROM geocode(:address, 1)
    ORDER BY rating ASC
    LIMIT 1
""")

NORMALIZE_SQL = text("""
    SELECT
        (na).address          AS address_number,
        (na).predirabbrev     AS predir,
        (na).streetname       AS street_name,
        (na).streettypeabbrev AS street_type,
        (na).postdirabbrev    AS postdir,
        (na).internal         AS internal,
        (na).location         AS city,
        (na).stateabbrev      AS state,
        (na).zip              AS zip,
        (na).zip4             AS zip4,
        (na).parsed           AS parsed
    FROM normalize_address(:address) AS na
""")

CHECK_EXTENSION_SQL = text("""
    SELECT 1 FROM pg_extension
    WHERE extname = 'postgis_tiger_geocoder'
""")

COUNTY_CONTAINS_SQL = text("""
    SELECT cntyidfp
    FROM tiger.county
    WHERE statefp = :state_fips
      AND ST_Contains(
            the_geom,
            ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 4269)
          )
    LIMIT 1
""")

STATE_FIPS_SQL = text("""
    SELECT statefp FROM tiger.state
    WHERE stusps = :state_abbrev
    LIMIT 1
""")

# Confidence for Tiger validation (normalize_address cross-refs Census data).
# Higher than scourgify (0.3) because Tiger normalizes against actual street data.
TIGER_VALIDATION_CONFIDENCE = 0.4  # D-10


# ---------------------------------------------------------------------------
# Extension availability check
# ---------------------------------------------------------------------------

async def _tiger_extension_available(session_factory: async_sessionmaker) -> bool:
    """Check whether the postgis_tiger_geocoder extension is installed in the current database.

    Queries pg_extension (installed extensions) so it only returns True when the
    extension has been activated with CREATE EXTENSION in the current database.

    Args:
        session_factory: async_sessionmaker used to open a short-lived session.

    Returns:
        True if the extension is installed, False if absent or on any error.
    """
    try:
        async with session_factory() as session:
            result = await session.execute(CHECK_EXTENSION_SQL)
            return result.first() is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# TigerGeocodingProvider
# ---------------------------------------------------------------------------

class TigerGeocodingProvider(GeocodingProvider):
    """Geocoding provider that calls the PostGIS Tiger geocode() SQL function.

    Uses address interpolation via TIGER/Line street range data. Returns results
    directly without writing to geocoding_results (is_local=True).

    Confidence score: max(0.0, min(1.0, (100 - rating) / 100))
    - rating 0   -> confidence 1.0 (exact match)
    - rating 100 -> confidence 0.0 (no match)
    - rating >100 -> clamped to 0.0

    Args:
        session_factory: async_sessionmaker[AsyncSession] for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def is_local(self) -> bool:
        """Always True — this provider calls local PostGIS SQL functions."""
        return True

    @property
    def provider_name(self) -> str:
        return "postgis_tiger"

    async def geocode(self, address: str, **kwargs: Any) -> GeocodingResult:
        """Geocode a single address via the PostGIS Tiger geocode() function.

        Args:
            address: Freeform address string.
            **kwargs: Accepts http_client=, county_fips= and other kwargs from
                service layer without raising TypeError. When county_fips is
                provided (5-digit FIPS string e.g. "13021"), the geocoded point
                must fall inside that specific county or NO_MATCH is returned.

        Returns:
            GeocodingResult with RANGE_INTERPOLATED location_type and rating-based
            confidence. Returns NO_MATCH (confidence=0.0) if no row is returned
            or if the geocoded point falls outside the expected county.

        Raises:
            ProviderError: On SQLAlchemy database error.
        """
        try:
            async with self._session_factory() as session:
                result = await session.execute(GEOCODE_SQL, {"address": address})
                row = result.first()

                if row is None:
                    return GeocodingResult(
                        lat=0.0,
                        lng=0.0,
                        location_type="NO_MATCH",
                        confidence=0.0,
                        raw_response={},
                        provider_name=self.provider_name,
                    )

                # FIX-01: County spatial post-filter (D-01, D-02, D-03)
                if row.state:
                    state_result = await session.execute(
                        STATE_FIPS_SQL, {"state_abbrev": row.state}
                    )
                    state_row = state_result.first()
                    if state_row:
                        county_result = await session.execute(
                            COUNTY_CONTAINS_SQL,
                            {
                                "state_fips": state_row.statefp,
                                "lng": row.lng,
                                "lat": row.lat,
                            },
                        )
                        county_row = county_result.first()
                        if county_row is None:
                            # D-03: geocoded point outside all counties in expected state
                            return GeocodingResult(
                                lat=0.0,
                                lng=0.0,
                                location_type="NO_MATCH",
                                confidence=0.0,
                                raw_response={},
                                provider_name=self.provider_name,
                            )
                        # D-02: if caller specified county_fips, verify match
                        expected_county = kwargs.get("county_fips")
                        if expected_county and county_row.cntyidfp != expected_county:
                            return GeocodingResult(
                                lat=0.0,
                                lng=0.0,
                                location_type="NO_MATCH",
                                confidence=0.0,
                                raw_response={},
                                provider_name=self.provider_name,
                            )

        except SQLAlchemyError as e:
            raise ProviderError(f"Tiger geocode query failed: {e}") from e

        confidence = max(0.0, min(1.0, (100 - row.rating) / 100))

        raw_response: dict[str, Any] = {
            "rating": row.rating,
            "address_number": row.address_number,
            "predir": row.predir,
            "street_name": row.street_name,
            "street_type": row.street_type,
            "postdir": row.postdir,
            "internal": row.internal,
            "city": row.city,
            "state": row.state,
            "zip": row.zip,
            "zip4": row.zip4,
            "parsed": row.parsed,
        }

        return GeocodingResult(
            lat=row.lat,
            lng=row.lng,
            location_type="RANGE_INTERPOLATED",
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
# TigerValidationProvider
# ---------------------------------------------------------------------------

class TigerValidationProvider(ValidationProvider):
    """Validation provider that calls the PostGIS normalize_address() SQL function.

    Parses address components via Tiger norm_addy type. Returns results directly
    without writing to validation_results (is_local=True).

    Returns confidence=TIGER_VALIDATION_CONFIDENCE (0.4) when normalize_address()
    sets parsed=True, and confidence=0.0 (NO_MATCH) when parsed=False or no row
    is returned.

    Args:
        session_factory: async_sessionmaker[AsyncSession] for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def is_local(self) -> bool:
        """Always True — this provider calls local PostGIS SQL functions."""
        return True

    @property
    def provider_name(self) -> str:
        return "postgis_tiger"

    async def validate(self, address: str, **kwargs: Any) -> ValidationResult:
        """Validate a single address via the PostGIS normalize_address() function.

        Args:
            address: Freeform address string.
            **kwargs: Accepts extra kwargs for future compatibility.

        Returns:
            ValidationResult with confidence=TIGER_VALIDATION_CONFIDENCE (0.4) when
            parsed=True. Returns NO_MATCH (confidence=0.0) when parsed=False or no
            row returned. delivery_point_verified is always False.

        Raises:
            ProviderError: On SQLAlchemy database error.
        """
        try:
            async with self._session_factory() as session:
                result = await session.execute(NORMALIZE_SQL, {"address": address})
                row = result.first()
        except SQLAlchemyError as e:
            raise ProviderError(f"Tiger normalize_address query failed: {e}") from e

        if row is None or not row.parsed:
            return ValidationResult(
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

        # Build address_line_1 from non-None norm_addy components
        address_line_1 = " ".join(
            filter(
                None,
                [
                    str(row.address_number) if row.address_number else None,
                    row.predir,
                    row.street_name,
                    row.street_type,
                    row.postdir,
                ],
            )
        )
        address_line_2 = row.internal or None

        # Build normalized_address from non-None parts
        parts = [p for p in [address_line_1, row.city, row.state, row.zip] if p]
        normalized_address = " ".join(parts) if parts else address_line_1

        return ValidationResult(
            normalized_address=normalized_address,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=row.city,
            state=row.state,
            postal_code=row.zip,
            confidence=TIGER_VALIDATION_CONFIDENCE,
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
