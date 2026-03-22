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
    AdminOverride,
)
from civpulse_geo.providers.base import GeocodingProvider
from civpulse_geo.providers.schemas import GeocodingResult as GeocodingResultSchema


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

        # Determine which providers are local vs remote
        local_providers = {k: v for k, v in providers.items()
                           if isinstance(v, GeocodingProvider) and v.is_local}
        remote_providers = {k: v for k, v in providers.items()
                            if isinstance(v, GeocodingProvider) and not v.is_local}

        # Step 3: Cache check (skip if force_refresh or any local providers requested)
        if not force_refresh and address.geocoding_results and not local_providers:
            cached = address.geocoding_results

            # Load official result for this address
            official_result = await self._get_official(db, address.id)

            await db.commit()
            return {
                "address_hash": address_hash,
                "normalized_address": normalized,
                "results": cached,
                "local_results": [],
                "cache_hit": True,
                "official": official_result,
            }

        # Step 4a: Call local providers on any request (bypass DB write)
        local_results: list[GeocodingResultSchema] = []
        for provider_name, provider in local_providers.items():
            provider_result = await provider.geocode(
                normalized, http_client=http_client
            )
            local_results.append(provider_result)

        # Step 4b: Call remote providers on cache miss
        new_results: list[GeocodingResultORM] = []
        for provider_name, provider in remote_providers.items():
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

        # Step 6: Auto-set OfficialGeocoding on first successful remote match
        # Local results have no ORM row and cannot be referenced by geocoding_result_id
        official_result = None
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

        # Re-load official after commit (only when remote results exist)
        if new_results:
            official_result = await self._get_official(db, address.id)

        return {
            "address_hash": address_hash,
            "normalized_address": normalized,
            "results": new_results,
            "local_results": local_results,
            "cache_hit": False,
            "official": official_result,
        }

    async def set_official(
        self,
        address_hash: str,
        db: AsyncSession,
        geocoding_result_id: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        reason: str | None = None,
    ) -> dict:
        """Set the official geocoding result for an address.

        Two mutually exclusive paths:
        - GEO-06: geocoding_result_id provided → point OfficialGeocoding at existing result
        - GEO-07: latitude + longitude provided → create admin_override result, set as official

        Args:
            address_hash: SHA-256 hex identifying the address.
            db: Async database session.
            geocoding_result_id: ID of an existing GeocodingResult row for this address.
            latitude: Custom latitude for admin_override path.
            longitude: Custom longitude for admin_override path.
            reason: Optional reason string stored in raw_response.

        Returns:
            Dict with keys:
                address_hash (str): The address hash.
                official (GeocodingResultORM): The new official result row.
                source (str): "provider_result" or "admin_override".

        Raises:
            ValueError: If address not found, result not found, or invalid argument combo.
        """
        # Validate exactly one path is taken
        has_result_id = geocoding_result_id is not None
        has_coords = latitude is not None and longitude is not None
        if has_result_id and has_coords:
            raise ValueError(
                "Provide either geocoding_result_id OR latitude+longitude, not both."
            )
        if not has_result_id and not has_coords:
            raise ValueError(
                "Provide either geocoding_result_id or latitude+longitude."
            )

        # Step 1: Look up Address by address_hash
        addr_result = await db.execute(
            select(Address).where(Address.address_hash == address_hash)
        )
        address = addr_result.scalars().first()
        if address is None:
            raise ValueError("Address not found")

        if has_result_id:
            # GEO-06: verify result belongs to this address
            gr_result = await db.execute(
                select(GeocodingResultORM).where(
                    GeocodingResultORM.id == geocoding_result_id,
                    GeocodingResultORM.address_id == address.id,
                )
            )
            geocoding_result = gr_result.scalars().first()
            if geocoding_result is None:
                raise ValueError("Geocoding result not found for this address")

            # Upsert OfficialGeocoding
            await db.execute(
                pg_insert(OfficialGeocoding)
                .values(
                    address_id=address.id,
                    geocoding_result_id=geocoding_result_id,
                )
                .on_conflict_do_update(
                    index_elements=["address_id"],
                    set_={"geocoding_result_id": geocoding_result_id},
                )
            )
            await db.commit()
            return {
                "address_hash": address_hash,
                "official": geocoding_result,
                "source": "provider_result",
            }
        else:
            # GEO-07: create synthetic admin_override GeocodingResult
            ewkt_point = f"SRID=4326;POINT({longitude} {latitude})"
            raw = {"reason": reason, "source": "admin_override"}

            stmt = (
                pg_insert(GeocodingResultORM)
                .values(
                    address_id=address.id,
                    provider_name="admin_override",
                    location=ewkt_point,
                    latitude=latitude,
                    longitude=longitude,
                    location_type=None,
                    confidence=1.0,
                    raw_response=raw,
                )
                .on_conflict_do_update(
                    constraint="uq_geocoding_address_provider",
                    set_={
                        "location": ewkt_point,
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_type": None,
                        "confidence": 1.0,
                        "raw_response": raw,
                    },
                )
                .returning(GeocodingResultORM.id)
            )
            upsert_result = await db.execute(stmt)
            result_id = upsert_result.scalar_one()

            # Write admin_override row (GEO-07)
            await db.execute(
                pg_insert(AdminOverride)
                .values(
                    address_id=address.id,
                    location=ewkt_point,
                    latitude=latitude,
                    longitude=longitude,
                    reason=reason,
                )
                .on_conflict_do_update(
                    index_elements=["address_id"],
                    set_={
                        "location": ewkt_point,
                        "latitude": latitude,
                        "longitude": longitude,
                        "reason": reason,
                    },
                )
            )

            # Re-query the new/updated ORM row
            requery_result = await db.execute(
                select(GeocodingResultORM).where(GeocodingResultORM.id == result_id)
            )
            new_result = requery_result.scalars().first()

            # Upsert OfficialGeocoding to point at the new result
            await db.execute(
                pg_insert(OfficialGeocoding)
                .values(
                    address_id=address.id,
                    geocoding_result_id=result_id,
                )
                .on_conflict_do_update(
                    index_elements=["address_id"],
                    set_={"geocoding_result_id": result_id},
                )
            )
            await db.commit()
            return {
                "address_hash": address_hash,
                "official": new_result,
                "source": "admin_override",
            }

    async def refresh(
        self,
        address_hash: str,
        db: AsyncSession,
        providers: dict[str, GeocodingProvider],
        http_client: httpx.AsyncClient,
    ) -> dict:
        """Force re-query of all providers for an address (GEO-08).

        Bypasses the cache by calling geocode() with force_refresh=True. The
        existing cache-first logic in geocode() handles the upsert of new results.

        Args:
            address_hash: SHA-256 hex identifying the address.
            db: Async database session.
            providers: Dict of provider name -> instantiated GeocodingProvider.
            http_client: Shared httpx.AsyncClient from app.state.

        Returns:
            Dict with keys:
                address_hash (str): The address hash.
                normalized_address (str): The normalized address string.
                results (list[GeocodingResultORM]): Fresh provider results.
                refreshed_providers (list[str]): Names of providers re-queried.

        Raises:
            ValueError: If the address_hash is not found in the database.
        """
        # Look up Address to get the normalized_address for geocode() call
        addr_result = await db.execute(
            select(Address).where(Address.address_hash == address_hash)
        )
        address = addr_result.scalars().first()
        if address is None:
            raise ValueError("Address not found")

        # Reuse geocode() with force_refresh=True to bypass cache
        result = await self.geocode(
            freeform=address.normalized_address,
            db=db,
            providers=providers,
            http_client=http_client,
            force_refresh=True,
        )

        return {
            "address_hash": address_hash,
            "normalized_address": address.normalized_address,
            "results": result["results"],
            "refreshed_providers": list(providers.keys()),
        }

    async def get_by_provider(
        self,
        address_hash: str,
        provider_name: str,
        db: AsyncSession,
    ) -> dict:
        """Fetch a specific provider's geocoding result for an address (GEO-09).

        Args:
            address_hash: SHA-256 hex identifying the address.
            provider_name: Name of the provider (e.g. "census", "admin_override").
            db: Async database session.

        Returns:
            Dict with keys:
                address_hash (str): The address hash.
                provider_name (str): The provider name queried.
                result (GeocodingResultORM): The provider's result row.

        Raises:
            ValueError: If address_hash not found or provider has no result for this address.
        """
        # Step 1: Look up Address
        addr_result = await db.execute(
            select(Address).where(Address.address_hash == address_hash)
        )
        address = addr_result.scalars().first()
        if address is None:
            raise ValueError("Address not found")

        # Step 2: Query for the specific provider's result
        gr_result = await db.execute(
            select(GeocodingResultORM).where(
                GeocodingResultORM.address_id == address.id,
                GeocodingResultORM.provider_name == provider_name,
            )
        )
        geocoding_result = gr_result.scalars().first()
        if geocoding_result is None:
            raise ValueError(
                f"No result from provider '{provider_name}' for this address"
            )

        return {
            "address_hash": address_hash,
            "provider_name": provider_name,
            "result": geocoding_result,
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
