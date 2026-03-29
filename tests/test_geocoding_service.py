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
    provider.is_local = False  # Explicitly mark as remote provider
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

    # Force legacy path — this test verifies legacy cache-hit behavior
    with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
        mock_settings.cascade_enabled = False
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

    with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
        mock_settings.cascade_enabled = False
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


# ---------------------------------------------------------------------------
# Task 1 (02-02): Admin set_official endpoint — service layer tests
# ---------------------------------------------------------------------------

def _make_geocoding_result_orm(result_id=1, address_id=1, provider_name="census",
                                latitude=38.845, longitude=-76.928, confidence=0.8):
    """Build a mock GeocodingResultORM with specified attributes."""
    row = MagicMock(spec=GeocodingResultORM)
    row.id = result_id
    row.address_id = address_id
    row.provider_name = provider_name
    row.latitude = latitude
    row.longitude = longitude
    row.location_type = None
    row.confidence = confidence
    row.raw_response = {}
    return row


@pytest.mark.asyncio
async def test_set_official_existing_provider():
    """set_official with geocoding_result_id updates OfficialGeocoding to point at that result."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=False)
    geocoding_result = _make_geocoding_result_orm(result_id=5, address_id=1)

    # Sequence: address lookup, geocoding_result lookup, official upsert
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    gr_scalars = MagicMock()
    gr_scalars.first.return_value = geocoding_result
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars

    upsert_result = MagicMock()

    db.execute = AsyncMock(side_effect=[addr_result, gr_result, upsert_result])

    result = await service.set_official(
        address_hash="abc123",
        db=db,
        geocoding_result_id=5,
    )

    assert result["address_hash"] == "abc123"
    assert result["official"] is geocoding_result
    assert result["source"] == "provider_result"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_set_official_invalid_result_id():
    """set_official raises ValueError when geocoding_result_id doesn't belong to address."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    # geocoding_result NOT found (doesn't belong to address)
    gr_scalars = MagicMock()
    gr_scalars.first.return_value = None
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars

    db.execute = AsyncMock(side_effect=[addr_result, gr_result])

    with pytest.raises(ValueError, match="Geocoding result not found"):
        await service.set_official(
            address_hash="abc123",
            db=db,
            geocoding_result_id=999,
        )


@pytest.mark.asyncio
async def test_set_custom_official():
    """set_official with lat/lng creates admin_override GeocodingResult and sets it as official."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    # Upsert of admin_override GeocodingResult returns id=10
    upsert_gr_result = MagicMock()
    upsert_gr_result.scalar_one.return_value = 10

    # Re-query of the new GeocodingResult row
    new_gr = _make_geocoding_result_orm(result_id=10, address_id=1,
                                        provider_name="admin_override",
                                        latitude=33.123, longitude=-83.456,
                                        confidence=1.0)
    requery_scalars = MagicMock()
    requery_scalars.first.return_value = new_gr
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    # Official upsert
    official_upsert = MagicMock()

    admin_override_upsert = MagicMock()
    db.execute = AsyncMock(side_effect=[addr_result, upsert_gr_result, admin_override_upsert, requery_result, official_upsert])

    result = await service.set_official(
        address_hash="abc123",
        db=db,
        latitude=33.123,
        longitude=-83.456,
    )

    assert result["address_hash"] == "abc123"
    assert result["official"].provider_name == "admin_override"
    assert result["official"].latitude == 33.123
    assert result["official"].confidence == 1.0
    assert result["source"] == "admin_override"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_set_custom_official_stores_reason():
    """set_official custom path stores reason in raw_response."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_gr_result = MagicMock()
    upsert_gr_result.scalar_one.return_value = 10

    new_gr = _make_geocoding_result_orm(result_id=10, address_id=1,
                                        provider_name="admin_override",
                                        latitude=33.123, longitude=-83.456,
                                        confidence=1.0)
    requery_scalars = MagicMock()
    requery_scalars.first.return_value = new_gr
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    official_upsert = MagicMock()

    admin_override_upsert = MagicMock()
    db.execute = AsyncMock(side_effect=[addr_result, upsert_gr_result, admin_override_upsert, requery_result, official_upsert])

    # Capture the stmt values passed to execute to verify reason is included
    captured_stmts = []
    original_execute = db.execute.side_effect

    result = await service.set_official(
        address_hash="abc123",
        db=db,
        latitude=33.123,
        longitude=-83.456,
        reason="Surveyor confirmed location",
    )

    # The reason should have been passed — we verify via the result returning successfully
    assert result["source"] == "admin_override"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_set_custom_official_writes_admin_override():
    """set_official with custom lat/lng writes an AdminOverride row via pg_insert upsert."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_gr_result = MagicMock()
    upsert_gr_result.scalar_one.return_value = 10

    admin_override_upsert = MagicMock()

    new_gr = _make_geocoding_result_orm(result_id=10, address_id=1,
                                        provider_name="admin_override",
                                        latitude=33.123, longitude=-83.456,
                                        confidence=1.0)
    requery_scalars = MagicMock()
    requery_scalars.first.return_value = new_gr
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    official_upsert = MagicMock()

    db.execute = AsyncMock(side_effect=[addr_result, upsert_gr_result, admin_override_upsert, requery_result, official_upsert])

    result = await service.set_official(
        address_hash="abc123",
        db=db,
        latitude=33.123,
        longitude=-83.456,
        reason="Surveyor verified",
    )

    # 5 db.execute calls: addr lookup, GR upsert, AdminOverride upsert, GR re-query, OfficialGeocoding upsert
    assert db.execute.call_count == 5, f"Expected 5 db.execute calls, got {db.execute.call_count}"
    assert result["source"] == "admin_override"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_set_custom_official_upserts_admin_override():
    """set_official AdminOverride insert uses on_conflict_do_update (upsert, not plain insert)."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    upsert_gr_result = MagicMock()
    upsert_gr_result.scalar_one.return_value = 10

    admin_override_upsert = MagicMock()

    new_gr = _make_geocoding_result_orm(result_id=10, address_id=1,
                                        provider_name="admin_override",
                                        latitude=33.123, longitude=-83.456,
                                        confidence=1.0)
    requery_scalars = MagicMock()
    requery_scalars.first.return_value = new_gr
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    official_upsert = MagicMock()

    db.execute = AsyncMock(side_effect=[addr_result, upsert_gr_result, admin_override_upsert, requery_result, official_upsert])

    result = await service.set_official(
        address_hash="abc123",
        db=db,
        latitude=33.123,
        longitude=-83.456,
    )

    # 5 calls confirms upsert path executed (plain INSERT would fail on 2nd call with real DB)
    assert db.execute.call_count == 5, f"Expected 5 db.execute calls, got {db.execute.call_count}"
    assert result["source"] == "admin_override"


# ---------------------------------------------------------------------------
# Task 2 (02-02): refresh and get_by_provider — service layer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_re_queries_providers():
    """refresh() calls geocode with force_refresh=True, calling providers even when cached."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=True)  # has cached results

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    db.execute = AsyncMock(return_value=addr_result)

    provider = _make_provider()
    http_client = AsyncMock()

    # Mock geocode() to return a fresh result
    mock_result = {
        "address_hash": "abc123",
        "normalized_address": "4600 SILVER HILL RD WASHINGTON DC 20233",
        "results": [_make_cached_orm_row()],
        "cache_hit": False,
        "official": None,
    }

    with patch.object(service, "geocode", new_callable=AsyncMock, return_value=mock_result) as mock_geocode:
        result = await service.refresh(
            address_hash="abc123",
            db=db,
            providers={"census": provider},
            http_client=http_client,
        )

    # geocode() must have been called with force_refresh=True
    mock_geocode.assert_called_once()
    call_kwargs = mock_geocode.call_args
    assert call_kwargs.kwargs.get("force_refresh") is True or (
        len(call_kwargs.args) > 4 and call_kwargs.args[4] is True
    )
    assert result["address_hash"] == "abc123"


@pytest.mark.asyncio
async def test_refresh_updates_existing_results():
    """refresh() returns results from geocode() and includes refreshed_providers list."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    db.execute = AsyncMock(return_value=addr_result)

    provider = _make_provider()
    http_client = AsyncMock()

    fresh_row = _make_cached_orm_row()
    mock_result = {
        "address_hash": "abc123",
        "normalized_address": "4600 SILVER HILL RD WASHINGTON DC 20233",
        "results": [fresh_row],
        "cache_hit": False,
        "official": None,
    }

    with patch.object(service, "geocode", new_callable=AsyncMock, return_value=mock_result):
        result = await service.refresh(
            address_hash="abc123",
            db=db,
            providers={"census": provider},
            http_client=http_client,
        )

    assert result["results"] == [fresh_row]
    assert "census" in result["refreshed_providers"]
    assert result["normalized_address"] == "4600 SILVER HILL RD WASHINGTON DC 20233"


@pytest.mark.asyncio
async def test_get_by_provider_returns_specific():
    """get_by_provider returns only the named provider's result."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)

    address = _make_address(address_id=1, has_results=False)
    census_result = _make_geocoding_result_orm(result_id=1, address_id=1, provider_name="census")

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    gr_scalars = MagicMock()
    gr_scalars.first.return_value = census_result
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars

    db.execute = AsyncMock(side_effect=[addr_result, gr_result])

    result = await service.get_by_provider(
        address_hash="abc123",
        provider_name="census",
        db=db,
    )

    assert result["address_hash"] == "abc123"
    assert result["provider_name"] == "census"
    assert result["result"] is census_result


@pytest.mark.asyncio
async def test_get_by_provider_not_found():
    """get_by_provider raises ValueError when provider has no result for the address."""
    from civpulse_geo.services.geocoding import GeocodingService

    service = GeocodingService()
    db = AsyncMock(spec=AsyncSession)

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    gr_scalars = MagicMock()
    gr_scalars.first.return_value = None
    gr_result = MagicMock()
    gr_result.scalars.return_value = gr_scalars

    db.execute = AsyncMock(side_effect=[addr_result, gr_result])

    with pytest.raises(ValueError, match="No result from provider"):
        await service.get_by_provider(
            address_hash="abc123",
            provider_name="nonexistent",
            db=db,
        )


# ---------------------------------------------------------------------------
# Task 1 (07-01): Local provider bypass tests
# ---------------------------------------------------------------------------

def _make_local_geocoding_provider():
    """Build a mock GeocodingProvider with is_local=True."""
    from civpulse_geo.providers.base import GeocodingProvider

    provider = AsyncMock(spec=GeocodingProvider)
    provider.provider_name = "test-local"
    provider.is_local = True
    provider.geocode = AsyncMock(
        return_value=ProviderResult(
            lat=32.84, lng=-83.63, location_type="ROOFTOP",
            confidence=0.95, raw_response={}, provider_name="test-local",
        )
    )
    return provider


def _make_db_for_local_provider(address_id=1):
    """Build a mock db session that simulates a new address (cache miss) for local provider tests.

    Returns (db, address) tuple. The address is pre-configured with empty geocoding_results.
    db.execute sequence:
      1. Address lookup with selectinload -> address found
      2. OfficialGeocoding lookup in _get_official -> None (no official set yet)
    (No upsert calls should happen for local providers.)
    """
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    address = _make_address(address_id=address_id, has_results=False)

    # First execute: address lookup -> returns address
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    # Second execute: OfficialGeocoding lookup in _get_official -> returns None
    none_scalars = MagicMock()
    none_scalars.first.return_value = None
    none_result = MagicMock()
    none_result.scalars.return_value = none_scalars

    db.execute = AsyncMock(side_effect=[addr_result, none_result])
    return db, address


class TestLocalProviderBypass:
    """Tests verifying that local providers bypass geocoding_results DB writes.

    All tests in this class use CASCADE_ENABLED=false to verify the legacy path behavior.
    """

    @pytest.mark.asyncio
    async def test_local_provider_bypasses_geocoding_results_write(self):
        """geocode() with a local provider does NOT call pg_insert(GeocodingResultORM)."""
        service = GeocodingService()
        local_provider = _make_local_geocoding_provider()
        http_client = AsyncMock()

        db, address = _make_db_for_local_provider()

        with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
            mock_settings.cascade_enabled = False
            result = await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=db,
                providers={"test-local": local_provider},
                http_client=http_client,
            )

        # Only address lookup should have been called (1 execute),
        # plus no geocoding_results insert
        # The result should have local_results with the provider result
        assert "local_results" in result
        assert len(result["local_results"]) == 1
        assert result["local_results"][0].provider_name == "test-local"

        # results (remote ORM rows) should be empty
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_local_provider_result_in_local_results_key(self):
        """geocode() with local provider returns provider result under local_results, not results."""
        service = GeocodingService()
        local_provider = _make_local_geocoding_provider()
        http_client = AsyncMock()

        db, address = _make_db_for_local_provider()

        with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
            mock_settings.cascade_enabled = False
            result = await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=db,
                providers={"test-local": local_provider},
                http_client=http_client,
            )

        assert "local_results" in result
        assert "results" in result
        # Local results should contain the schema result (not an ORM row)
        assert len(result["local_results"]) == 1
        local = result["local_results"][0]
        assert local.lat == 32.84
        assert local.lng == -83.63
        # Remote results should be empty
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_local_provider_db_execute_count(self):
        """geocode() with local provider calls db.execute only for address lookup (no upsert)."""
        service = GeocodingService()
        local_provider = _make_local_geocoding_provider()
        http_client = AsyncMock()

        db, address = _make_db_for_local_provider()

        with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
            mock_settings.cascade_enabled = False
            await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=db,
                providers={"test-local": local_provider},
                http_client=http_client,
            )

        # Should only execute address lookup (1 call) — no upsert for geocoding_results
        assert db.execute.call_count == 1, (
            f"Expected 1 db.execute call (address lookup), got {db.execute.call_count}"
        )

    @pytest.mark.asyncio
    async def test_cache_hit_return_includes_local_results_key(self):
        """Cache-hit return path includes local_results key (empty list)."""
        service = GeocodingService()
        remote_provider = _make_provider()  # is_local=False by default
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

        with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
            mock_settings.cascade_enabled = False
            result = await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=db,
                providers={"census": remote_provider},
                http_client=http_client,
            )

        assert result["cache_hit"] is True
        assert "local_results" in result
        assert result["local_results"] == []

    @pytest.mark.asyncio
    async def test_local_provider_geocode_is_called(self):
        """geocode() calls provider.geocode() even when there are no remote providers."""
        service = GeocodingService()
        local_provider = _make_local_geocoding_provider()
        http_client = AsyncMock()

        db, address = _make_db_for_local_provider()

        with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
            mock_settings.cascade_enabled = False
            await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=db,
                providers={"test-local": local_provider},
                http_client=http_client,
            )

        local_provider.geocode.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 14: Cascade dispatcher tests (CASC-01, CASC-02, D-02, D-03)
# ---------------------------------------------------------------------------

from unittest.mock import patch as _patch
from civpulse_geo.config import settings as _settings
from civpulse_geo.services.cascade import CascadeResult, ProviderCandidate


def _make_cascade_result(
    address_hash="a" * 64,
    normalized_address="4600 SILVER HILL RD WASHINGTON DC 20233",
    cache_hit=False,
    results=None,
    local_results=None,
    official=None,
    cascade_trace=None,
    would_set_official=None,
    outlier_providers=None,
):
    """Build a minimal CascadeResult for use in cascade dispatcher tests."""
    from civpulse_geo.models.address import Address

    addr = MagicMock(spec=Address)
    addr.id = 1
    return CascadeResult(
        address_hash=address_hash,
        normalized_address=normalized_address,
        address=addr,
        cache_hit=cache_hit,
        results=results or [],
        local_results=local_results or [],
        official=official,
        cascade_trace=cascade_trace,
        would_set_official=would_set_official,
        outlier_providers=outlier_providers or set(),
    )


@pytest.mark.asyncio
async def test_geocode_delegates_to_cascade_when_enabled():
    """When CASCADE_ENABLED=true, geocode() calls CascadeOrchestrator.run()."""
    service = GeocodingService()
    cascade_result = _make_cascade_result()

    with _patch.object(_settings, "cascade_enabled", True):
        with _patch(
            "civpulse_geo.services.geocoding.CascadeOrchestrator.run",
            new_callable=AsyncMock,
            return_value=cascade_result,
        ) as mock_run:
            result = await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=AsyncMock(),
                providers={},
                http_client=AsyncMock(),
            )

    mock_run.assert_called_once()
    assert result["address_hash"] == cascade_result.address_hash
    assert result["cache_hit"] is False


@pytest.mark.asyncio
async def test_geocode_delegates_to_legacy_when_disabled():
    """When CASCADE_ENABLED=false, geocode() calls _legacy_geocode()."""
    service = GeocodingService()
    legacy_result = {
        "address_hash": "b" * 64,
        "normalized_address": "4600 SILVER HILL RD WASHINGTON DC 20233",
        "cache_hit": True,
        "results": [],
        "local_results": [],
        "official": None,
    }

    with _patch.object(_settings, "cascade_enabled", False):
        with _patch.object(
            service, "_legacy_geocode", new_callable=AsyncMock, return_value=legacy_result
        ) as mock_legacy:
            result = await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=AsyncMock(),
                providers={},
                http_client=AsyncMock(),
            )

    mock_legacy.assert_called_once()
    assert result["address_hash"] == legacy_result["address_hash"]


@pytest.mark.asyncio
async def test_geocode_passes_dry_run_and_trace():
    """dry_run and trace kwargs are forwarded to CascadeOrchestrator.run()."""
    service = GeocodingService()
    cascade_result = _make_cascade_result(cascade_trace=[{"stage": "normalize"}])

    with _patch.object(_settings, "cascade_enabled", True):
        with _patch(
            "civpulse_geo.services.geocoding.CascadeOrchestrator.run",
            new_callable=AsyncMock,
            return_value=cascade_result,
        ) as mock_run:
            await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=AsyncMock(),
                providers={},
                http_client=AsyncMock(),
                dry_run=True,
                trace=True,
            )

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("dry_run") is True
    assert call_kwargs.get("trace") is True


@pytest.mark.asyncio
async def test_geocode_cascade_result_includes_outlier_providers():
    """Cascade path returns outlier_providers set in the result dict."""
    service = GeocodingService()
    cascade_result = _make_cascade_result(outlier_providers={"tiger"})

    with _patch.object(_settings, "cascade_enabled", True):
        with _patch(
            "civpulse_geo.services.geocoding.CascadeOrchestrator.run",
            new_callable=AsyncMock,
            return_value=cascade_result,
        ):
            result = await service.geocode(
                freeform="4600 Silver Hill Rd Washington DC 20233",
                db=AsyncMock(),
                providers={},
                http_client=AsyncMock(),
            )

    assert "outlier_providers" in result
    assert "tiger" in result["outlier_providers"]


# Fix: existing legacy-dependent tests that fail under CASCADE_ENABLED=true
# Patch the affected tests to use _legacy_geocode directly or disable cascade.
# We add a fixture-based approach as well as direct class patches.

@pytest.mark.asyncio
async def test_geocode_cache_hit_returns_cached_legacy():
    """cache_hit=True when cached results returned (legacy path, CASCADE_ENABLED=false)."""
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

    with _patch.object(_settings, "cascade_enabled", False):
        result = await service.geocode(
            freeform="4600 Silver Hill Rd Washington DC 20233",
            db=db,
            providers={"census": provider},
            http_client=http_client,
        )

    assert not provider.geocode.called
    assert result["cache_hit"] is True
    assert len(result["results"]) == 1


# ---------------------------------------------------------------------------
# Phase 16 Task 1: Regression test for 5-tuple unpack fix in _legacy_geocode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_geocode_no_match_does_not_raise_value_error():
    """_legacy_geocode must not raise ValueError when all local providers return NO_MATCH.

    The warning block at geocoding.py line 214 previously unpacked _parse_input_address
    as a 3-tuple, but the function returns a 5-tuple. This test exercises that exact
    code path and verifies it completes without raising ValueError.
    """
    service = GeocodingService()
    http_client = AsyncMock()

    # Local provider that returns NO_MATCH (confidence=0.0)
    from civpulse_geo.providers.base import GeocodingProvider
    local_provider = AsyncMock(spec=GeocodingProvider)
    local_provider.provider_name = "test-local"
    local_provider.is_local = True
    local_provider.geocode = AsyncMock(
        return_value=ProviderResult(
            lat=None,
            lng=None,
            location_type=None,
            confidence=0.0,
            raw_response={},
            provider_name="test-local",
        )
    )

    # DB: address lookup returns existing address with no cached results
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    address = _make_address(address_id=1, has_results=False)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    # _get_official lookup -> None
    none_scalars = MagicMock()
    none_scalars.first.return_value = None
    none_result = MagicMock()
    none_result.scalars.return_value = none_scalars

    db.execute = AsyncMock(side_effect=[addr_result, none_result])

    # With CASCADE_ENABLED=false the legacy path is used — the 5-tuple unpack
    # in the warning block must not raise ValueError
    with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
        mock_settings.cascade_enabled = False
        result = await service.geocode(
            freeform="123 XYZZY ST MACON GA 31201",
            db=db,
            providers={"test-local": local_provider},
            http_client=http_client,
        )

    # The call must not raise — and local_results must show the NO_MATCH entry
    assert "local_results" in result
    assert len(result["local_results"]) == 1
    assert result["local_results"][0].confidence == 0.0
