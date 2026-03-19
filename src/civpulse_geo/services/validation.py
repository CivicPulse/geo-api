"""ValidationService: cache-first validation orchestration layer.

Pipeline:
  1. Normalize input address and compute SHA-256 hash
  2. Find or create Address record in database
  3. Cache check -- return cached validation_results if present
  4. Call validation providers on cache miss
  5. Upsert results with PostgreSQL ON CONFLICT DO UPDATE
  6. Commit and return structured response dict
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from civpulse_geo.normalization import canonical_key, parse_address_components
from civpulse_geo.models.address import Address
from civpulse_geo.models.validation import ValidationResult as ValidationResultORM
from civpulse_geo.providers.base import ValidationProvider


class ValidationService:
    """Stateless per-request service -- mirrors GeocodingService pattern.

    Orchestrates the full validation pipeline with cache-first logic.
    Designed to be instantiated per-request. All mutable state lives in the
    database session and provider registry passed at call time.
    """

    async def validate(
        self,
        freeform: str,
        db: AsyncSession,
        providers: dict[str, ValidationProvider],
    ) -> dict:
        """Validate a freeform address using the cache-first pipeline.

        Args:
            freeform: Raw address string from the caller (or constructed from structured fields).
            db: Async database session (from FastAPI dependency).
            providers: Dict of provider name -> instantiated ValidationProvider.

        Returns:
            Dict with keys:
                address_hash (str): SHA-256 hex of the normalized address.
                original_input (str): The freeform address string passed in.
                cache_hit (bool): True if results came from cache.
                candidates (list[ValidationResultORM]): ORM rows (may be empty).

        Raises:
            ProviderError: Propagated from provider when address is unparseable.
        """
        # Step 1: Normalize and hash
        normalized, address_hash = canonical_key(freeform)

        # Step 2: Find or create Address record
        result = await db.execute(
            select(Address).where(Address.address_hash == address_hash)
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

        # Step 3: Cache check -- query validation_results for this address
        cache_result = await db.execute(
            select(ValidationResultORM).where(
                ValidationResultORM.address_id == address.id
            )
        )
        cached = cache_result.scalars().all()

        if cached:
            await db.commit()
            return {
                "address_hash": address_hash,
                "original_input": freeform,
                "candidates": cached,
                "cache_hit": True,
            }

        # Step 4: Call validation providers on cache miss
        new_results: list[ValidationResultORM] = []
        for provider_name, provider in providers.items():
            if not isinstance(provider, ValidationProvider):
                continue

            # Provider raises ProviderError for unparseable -- propagate to caller
            provider_result = await provider.validate(freeform)

            # Step 5: Upsert into validation_results via ON CONFLICT DO UPDATE
            stmt = (
                pg_insert(ValidationResultORM)
                .values(
                    address_id=address.id,
                    provider_name=provider_name,
                    normalized_address=provider_result.normalized_address,
                    address_line_1=provider_result.address_line_1,
                    address_line_2=provider_result.address_line_2,
                    city=provider_result.city,
                    state=provider_result.state,
                    postal_code=provider_result.postal_code,
                    confidence=provider_result.confidence,
                    delivery_point_verified=provider_result.delivery_point_verified,
                    raw_response={
                        "original_input": provider_result.original_input,
                        "provider_name": provider_result.provider_name,
                    },
                )
                .on_conflict_do_update(
                    constraint="uq_validation_address_provider",
                    set_={
                        "normalized_address": provider_result.normalized_address,
                        "address_line_1": provider_result.address_line_1,
                        "address_line_2": provider_result.address_line_2,
                        "city": provider_result.city,
                        "state": provider_result.state,
                        "postal_code": provider_result.postal_code,
                        "confidence": provider_result.confidence,
                        "delivery_point_verified": provider_result.delivery_point_verified,
                        "raw_response": {
                            "original_input": provider_result.original_input,
                            "provider_name": provider_result.provider_name,
                        },
                    },
                )
                .returning(ValidationResultORM.id)
            )
            upsert_result = await db.execute(stmt)
            result_id = upsert_result.scalar_one()

            # Re-query to get full ORM object for response
            orm_result = await db.execute(
                select(ValidationResultORM).where(ValidationResultORM.id == result_id)
            )
            orm_row = orm_result.scalars().first()
            if orm_row:
                new_results.append(orm_row)

        # Step 6: Commit and return
        await db.commit()
        return {
            "address_hash": address_hash,
            "original_input": freeform,
            "candidates": new_results,
            "cache_hit": False,
        }

    async def validate_structured(
        self,
        street: str,
        city: str | None,
        state: str | None,
        zip_code: str | None,
        db: AsyncSession,
        providers: dict[str, ValidationProvider],
    ) -> dict:
        """Concatenate structured fields to freeform and delegate to validate().

        Args:
            street: Street address line (required).
            city: City name (optional).
            state: Two-letter state abbreviation (optional).
            zip_code: ZIP code (optional).
            db: Async database session.
            providers: Dict of provider name -> instantiated ValidationProvider.

        Returns:
            Same dict structure as validate().
        """
        parts = [p for p in [street, city, state, zip_code] if p]
        freeform = ", ".join(parts)
        return await self.validate(freeform, db, providers)
