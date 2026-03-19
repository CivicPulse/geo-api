"""GeocodingService: cache-first geocoding orchestration layer.

Implements the core geocoding pipeline:
  1. Normalize input address and compute SHA-256 hash
  2. Find or create Address record in database
  3. Cache check — return cached results if present
  4. Call providers on cache miss
  5. Upsert results with PostgreSQL ON CONFLICT DO UPDATE
  6. Auto-set OfficialGeocoding on first successful result
  7. Commit and return structured response dict

The cache-first pattern ensures each unique normalized address is geocoded
at most once per provider, minimizing external API calls.
"""
from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from civpulse_geo.normalization import canonical_key, parse_address_components
from civpulse_geo.models.address import Address
from civpulse_geo.models.geocoding import (
    GeocodingResult as GeocodingResultORM,
    OfficialGeocoding,
)
from civpulse_geo.providers.base import GeocodingProvider


class GeocodingService:
    """Orchestrates the full geocoding pipeline with cache-first logic.

    Designed to be instantiated per-request (stateless). All mutable state
    lives in the database session and provider registry passed at call time.
    """

    async def geocode(
        self,
        freeform: str,
        db: AsyncSession,
        providers: dict[str, GeocodingProvider],
        http_client: httpx.AsyncClient,
        force_refresh: bool = False,
    ) -> dict:
        """Geocode a freeform address using the cache-first pipeline.

        Args:
            freeform: Raw address string from the caller.
            db: Async database session (from FastAPI dependency).
            providers: Dict of provider name -> instantiated GeocodingProvider.
            http_client: Shared httpx.AsyncClient from app.state.
            force_refresh: If True, skip cache and call providers even if cached.

        Returns:
            Dict with keys:
                address_hash (str): SHA-256 hex of the normalized address.
                normalized_address (str): USPS-normalized address string.
                cache_hit (bool): True if results came from cache.
                results (list[GeocodingResultORM]): ORM rows (may be empty).
                official (GeocodingResultORM | None): The official result ORM row.
        """
        # Step 1: Normalize and hash
        normalized, address_hash = canonical_key(freeform)

        # Step 2: Find or create Address record
        result = await db.execute(
            select(Address)
            .options(selectinload(Address.geocoding_results))
            .where(Address.address_hash == address_hash)
        )
        address = result.scalars().first()

        if address is None:
            components = parse_address_components(freeform)
            address = Address(
                original_input=freeform,
                normalized_address=normalized,
                address_hash=address_hash,
                street_number=components.get("street_number"),
                street_name=components.get("street_name"),
                street_suffix=components.get("street_suffix"),
                street_predirection=components.get("street_predirection"),
                street_postdirection=components.get("street_postdirection"),
                unit_type=components.get("unit_type"),
                unit_number=components.get("unit_number"),
                city=components.get("city"),
                state=components.get("state"),
                zip_code=components.get("zip_code"),
            )
            db.add(address)
            await db.flush()  # get address.id

        # Step 3: Cache check (skip if force_refresh)
        if not force_refresh and address.geocoding_results:
            cached = address.geocoding_results

            # Load official result for this address
            official_result = await self._get_official(db, address.id)

            await db.commit()
            return {
                "address_hash": address_hash,
                "normalized_address": normalized,
                "results": cached,
                "cache_hit": True,
                "official": official_result,
            }

        # Step 4: Call providers on cache miss
        new_results: list[GeocodingResultORM] = []
        for provider_name, provider in providers.items():
            if not isinstance(provider, GeocodingProvider):
                continue

            provider_result = await provider.geocode(
                normalized, http_client=http_client
            )

            # Step 5: Upsert into geocoding_results
            # For NO_MATCH results, store null location_type and null geometry
            is_match = provider_result.confidence > 0.0

            location_type_value = None
            if is_match:
                # "RANGE_INTERPOLATED" matches LocationType enum value
                location_type_value = provider_result.location_type

            ewkt_point = None
            latitude = None
            longitude = None
            if is_match:
                # WKT convention: POINT(lng lat) — longitude first
                ewkt_point = (
                    f"SRID=4326;POINT({provider_result.lng} {provider_result.lat})"
                )
                latitude = provider_result.lat
                longitude = provider_result.lng

            stmt = (
                pg_insert(GeocodingResultORM)
                .values(
                    address_id=address.id,
                    provider_name=provider_name,
                    location=ewkt_point,
                    latitude=latitude,
                    longitude=longitude,
                    location_type=location_type_value,
                    confidence=provider_result.confidence,
                    raw_response=provider_result.raw_response,
                )
                .on_conflict_do_update(
                    constraint="uq_geocoding_address_provider",
                    set_={
                        "location": ewkt_point,
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_type": location_type_value,
                        "confidence": provider_result.confidence,
                        "raw_response": provider_result.raw_response,
                    },
                )
                .returning(GeocodingResultORM.id)
            )
            upsert_result = await db.execute(stmt)
            result_id = upsert_result.scalar_one()

            # Re-query to get full ORM object for response
            orm_row_result = await db.execute(
                select(GeocodingResultORM).where(
                    GeocodingResultORM.id == result_id
                )
            )
            orm_row = orm_row_result.scalars().first()
            if orm_row:
                new_results.append(orm_row)

        # Step 6: Auto-set OfficialGeocoding on first successful match
        successful = [r for r in new_results if r.confidence and r.confidence > 0.0]
        if successful:
            await db.execute(
                pg_insert(OfficialGeocoding)
                .values(
                    address_id=address.id,
                    geocoding_result_id=successful[0].id,
                )
                .on_conflict_do_nothing(index_elements=["address_id"])
            )

        # Step 7: Commit and return
        await db.commit()

        # Re-load official after commit
        official_result = await self._get_official(db, address.id)

        return {
            "address_hash": address_hash,
            "normalized_address": normalized,
            "results": new_results,
            "cache_hit": False,
            "official": official_result,
        }

    async def _get_official(
        self,
        db: AsyncSession,
        address_id: int,
    ) -> GeocodingResultORM | None:
        """Load the OfficialGeocoding result for an address, if one exists."""
        result = await db.execute(
            select(OfficialGeocoding).where(
                OfficialGeocoding.address_id == address_id
            )
        )
        official = result.scalars().first()
        if official is None:
            return None

        # Load the associated GeocodingResult
        gr_result = await db.execute(
            select(GeocodingResultORM).where(
                GeocodingResultORM.id == official.geocoding_result_id
            )
        )
        return gr_result.scalars().first()
