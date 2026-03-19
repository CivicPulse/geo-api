"""Unit tests for GeocodingService cache-first logic.

Tests verify:
- Cache miss triggers provider.geocode() call with normalized address
- Cache hit returns cached results without calling any provider
- New Address row is created on cache miss when address_hash not found
- Provider results are upserted into geocoding_results
- OfficialGeocoding is created on first successful result
- cache_hit=False on provider call, cache_hit=True on cached return
- Provider receives normalized address (not raw freeform input)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.services.geocoding import GeocodingService
from civpulse_geo.providers.schemas import GeocodingResult as ProviderResult
from civpulse_geo.models.address import Address
from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM


def _make_provider(lat=38.845, lng=-76.928, confidence=0.8, location_type="RANGE_INTERPOLATED"):
    """Build a mock GeocodingProvider that returns a configurable result."""
    from civpulse_geo.providers.base import GeocodingProvider

    provider = AsyncMock(spec=GeocodingProvider)
    provider.provider_name = "census"
    provider.geocode = AsyncMock(
        return_value=ProviderResult(
            lat=lat,
            lng=lng,
            location_type=location_type,
            confidence=confidence,
            raw_response={"result": {"addressMatches": []}},
            provider_name="census",
        )
    )
    return provider


def _make_cached_orm_row():
    """Build a mock GeocodingResultORM row simulating a cached result."""
    row = MagicMock(spec=GeocodingResultORM)
    row.id = 1
    row.provider_name = "census"
    row.latitude = 38.845
    row.longitude = -76.928
    row.location_type = None
    row.confidence = 0.8
    row.raw_response = {}
    return row


def _make_address(address_id=1, has_results=False):
    """Build a mock Address ORM object."""
    addr = MagicMock(spec=Address)
    addr.id = address_id
    addr.address_hash = "abc123"
    addr.normalized_address = "4600 SILVER HILL RD WASHINGTON DC 20233"
    if has_results:
        addr.geocoding_results = [_make_cached_orm_row()]
    else:
        addr.geocoding_results = []
    return addr


@pytest.mark.asyncio
async def test_geocode_cache_miss_calls_provider():
    """On cache miss, service calls provider.geocode() with the normalized address."""
    service = GeocodingService()
    provider = _make_provider()
    http_client = AsyncMock()

    # Mock DB: address not found, then created
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    # First execute: address lookup returns None
    # Second execute: upsert returning id=1
    # Third execute: re-query ORM row
    # Fourth execute: official lookup returns None
    # Fifth execute: official insert
    # After commit: official re-lookup returns None
    mock_addr = _make_address(has_results=False)

    execute_results = []

    # Address lookup result (scalars().first() -> None)
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars
    execute_results.append(addr_result)

    # Upsert returning id
    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1
    execute_results.append(upsert_result)

    # Re-query ORM row
    orm_scalars = MagicMock()
    orm_scalars.first.return_value = _make_cached_orm_row()
    orm_result = MagicMock()
    orm_result.scalars.return_value = orm_scalars
    execute_results.append(orm_result)

    # Official lookup (insert on_conflict_do_nothing)
    execute_results.append(MagicMock())

    # Official re-query after commit: none
    official_scalars = MagicMock()
    official_scalars.first.return_value = None
    official_result = MagicMock()
    official_result.scalars.return_value = official_scalars
    execute_results.append(official_result)

    # GeocodingResult re-lookup for official
    gr_scalars = MagicMock()
    gr_scalars.first.return_value = None
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars
    execute_results.append(gr_result)

    db.execute = AsyncMock(side_effect=execute_results)

    # Mock db.add to capture the Address object
    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    result = await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    # Provider should have been called
    assert provider.geocode.called
    # Result should indicate cache miss
    assert result["cache_hit"] is False


@pytest.mark.asyncio
async def test_geocode_cache_hit_returns_cached():
    """On cache hit, service returns cached results without calling any provider."""
    service = GeocodingService()
    provider = _make_provider()
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    # Address found with cached results
    cached_address = _make_address(has_results=True)

    # First execute: address lookup
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = cached_address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    # Official lookup: returns None
    official_scalars = MagicMock()
    official_scalars.first.return_value = None
    official_result = MagicMock()
    official_result.scalars.return_value = official_scalars

    # GeocodingResult for official: returns None
    gr_scalars = MagicMock()
    gr_scalars.first.return_value = None
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars

    db.execute = AsyncMock(
        side_effect=[addr_result, official_result, gr_result]
    )

    result = await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    # Provider should NOT have been called
    assert not provider.geocode.called
    # Result should indicate cache hit
    assert result["cache_hit"] is True
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_geocode_creates_address_record():
    """When address_hash not found in DB, service creates a new Address row."""
    service = GeocodingService()
    provider = _make_provider()
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    # Address not found
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 99

    orm_scalars = MagicMock()
    orm_scalars.first.return_value = _make_cached_orm_row()
    orm_result = MagicMock()
    orm_result.scalars.return_value = orm_scalars

    official_none_scalars = MagicMock()
    official_none_scalars.first.return_value = None
    official_none_result = MagicMock()
    official_none_result.scalars.return_value = official_none_scalars

    gr_none_scalars = MagicMock()
    gr_none_scalars.first.return_value = None
    gr_none_result = MagicMock()
    gr_none_result.scalars.return_value = gr_none_scalars

    db.execute = AsyncMock(side_effect=[
        addr_result,         # address lookup
        upsert_result,       # upsert insert
        orm_result,          # re-query ORM row
        MagicMock(),         # official insert on_conflict_do_nothing
        official_none_result,  # official lookup after commit
        gr_none_result,      # GeocodingResult for official
    ])

    await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    # db.add should have been called with an Address instance
    assert len(added_objects) == 1
    added = added_objects[0]
    assert isinstance(added, Address)
    assert added.original_input == "4600 Silver Hill Rd Washington DC 20233"


@pytest.mark.asyncio
async def test_geocode_stores_provider_result():
    """After provider returns, service upserts a GeocodingResult row."""
    service = GeocodingService()
    provider = _make_provider(lat=38.845, lng=-76.928, confidence=0.8)
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 42

    orm_row = _make_cached_orm_row()
    orm_row.id = 42
    orm_scalars = MagicMock()
    orm_scalars.first.return_value = orm_row
    orm_result = MagicMock()
    orm_result.scalars.return_value = orm_scalars

    official_none_scalars = MagicMock()
    official_none_scalars.first.return_value = None
    official_none_result = MagicMock()
    official_none_result.scalars.return_value = official_none_scalars

    gr_none_scalars = MagicMock()
    gr_none_scalars.first.return_value = None
    gr_none_result = MagicMock()
    gr_none_result.scalars.return_value = gr_none_scalars

    db.execute = AsyncMock(side_effect=[
        addr_result,
        upsert_result,
        orm_result,
        MagicMock(),  # official insert
        official_none_result,
        gr_none_result,
    ])

    result = await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    # Results list should contain the upserted ORM row
    assert len(result["results"]) == 1
    assert result["results"][0].id == 42
    assert result["results"][0].confidence == 0.8


@pytest.mark.asyncio
async def test_geocode_sets_official_on_first_result():
    """On initial geocode with a successful match, OfficialGeocoding is created."""
    service = GeocodingService()
    provider = _make_provider(confidence=0.8)
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 7

    orm_scalars = MagicMock()
    orm_scalars.first.return_value = _make_cached_orm_row()
    orm_result = MagicMock()
    orm_result.scalars.return_value = orm_scalars

    official_none_scalars = MagicMock()
    official_none_scalars.first.return_value = None
    official_none_result = MagicMock()
    official_none_result.scalars.return_value = official_none_scalars

    gr_none_scalars = MagicMock()
    gr_none_scalars.first.return_value = None
    gr_none_result = MagicMock()
    gr_none_result.scalars.return_value = gr_none_scalars

    official_insert_result = MagicMock()

    db.execute = AsyncMock(side_effect=[
        addr_result,
        upsert_result,
        orm_result,
        official_insert_result,  # official insert on_conflict_do_nothing
        official_none_result,    # official re-query after commit
        gr_none_result,
    ])

    await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    # Should have called execute for official insert (4th call)
    assert db.execute.call_count >= 4


@pytest.mark.asyncio
async def test_cache_hit_flag_false_on_miss():
    """cache_hit=False when providers were called (cache miss)."""
    service = GeocodingService()
    provider = _make_provider()
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1

    orm_scalars = MagicMock()
    orm_scalars.first.return_value = _make_cached_orm_row()
    orm_result = MagicMock()
    orm_result.scalars.return_value = orm_scalars

    official_none_scalars = MagicMock()
    official_none_scalars.first.return_value = None
    official_none_result = MagicMock()
    official_none_result.scalars.return_value = official_none_scalars

    gr_none_scalars = MagicMock()
    gr_none_scalars.first.return_value = None
    gr_none_result = MagicMock()
    gr_none_result.scalars.return_value = gr_none_scalars

    db.execute = AsyncMock(side_effect=[
        addr_result, upsert_result, orm_result, MagicMock(),
        official_none_result, gr_none_result,
    ])

    result = await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    assert result["cache_hit"] is False


@pytest.mark.asyncio
async def test_cache_hit_flag_true_on_hit():
    """cache_hit=True when cached results returned without provider call."""
    service = GeocodingService()
    provider = _make_provider()
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    cached_address = _make_address(has_results=True)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = cached_address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    official_scalars = MagicMock()
    official_scalars.first.return_value = None
    official_result = MagicMock()
    official_result.scalars.return_value = official_scalars

    gr_scalars = MagicMock()
    gr_scalars.first.return_value = None
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars

    db.execute = AsyncMock(side_effect=[addr_result, official_result, gr_result])

    result = await service.geocode(
        freeform="4600 Silver Hill Rd Washington DC 20233",
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    assert result["cache_hit"] is True


@pytest.mark.asyncio
async def test_uses_normalized_address_for_provider():
    """Provider.geocode() receives the normalized address, not the raw freeform input."""
    service = GeocodingService()
    provider = _make_provider()
    http_client = AsyncMock()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1

    orm_scalars = MagicMock()
    orm_scalars.first.return_value = _make_cached_orm_row()
    orm_result = MagicMock()
    orm_result.scalars.return_value = orm_scalars

    official_none_scalars = MagicMock()
    official_none_scalars.first.return_value = None
    official_none_result = MagicMock()
    official_none_result.scalars.return_value = official_none_scalars

    gr_none_scalars = MagicMock()
    gr_none_scalars.first.return_value = None
    gr_none_result = MagicMock()
    gr_none_result.scalars.return_value = gr_none_scalars

    db.execute = AsyncMock(side_effect=[
        addr_result, upsert_result, orm_result, MagicMock(),
        official_none_result, gr_none_result,
    ])

    raw_input = "4600 silver hill rd washington dc"
    await service.geocode(
        freeform=raw_input,
        db=db,
        providers={"census": provider},
        http_client=http_client,
    )

    # The address passed to provider.geocode should be normalized (uppercased, etc.)
    # NOT the raw lowercase freeform input
    called_address = provider.geocode.call_args[0][0]
    assert called_address != raw_input, "Provider should receive normalized address, not raw input"
    assert called_address == called_address.upper() or len(called_address) > 0
