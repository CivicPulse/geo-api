"""Unit tests for ValidationService cache-first logic and ValidateRequest/ValidateResponse schemas.

Tests verify:
- ValidateRequest.to_freeform() returns address when freeform input provided
- ValidateRequest.to_freeform() joins structured fields when structured input provided
- ValidateRequest raises ValidationError when neither address nor street is provided
- ValidationService.validate() returns dict with address_hash, original_input, candidates, cache_hit
- cache_hit=False on first call (empty DB mock)
- cache_hit=True when DB returns cached rows
- provider.validate is called when cache is empty
- provider.validate is NOT called when cache has data
- upsert statement is executed via db.execute
- ProviderError propagates when provider raises
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.schemas.validation import ValidateRequest, ValidateResponse, ValidationCandidate
from civpulse_geo.services.validation import ValidationService
from civpulse_geo.models.validation import ValidationResult as ValidationResultORM
from civpulse_geo.providers.schemas import ValidationResult as ValidationResultSchema
from civpulse_geo.providers.exceptions import ProviderError


# ---------------------------------------------------------------------------
# Pydantic schema tests
# ---------------------------------------------------------------------------

def test_validate_request_freeform_to_freeform():
    """ValidateRequest with address='123 Main St' produces to_freeform() returning '123 Main St'."""
    req = ValidateRequest(address="123 Main St")
    assert req.to_freeform() == "123 Main St"


def test_validate_request_structured_to_freeform():
    """ValidateRequest with structured fields produces to_freeform() returning joined string."""
    req = ValidateRequest(street="123 Main St", city="Macon", state="GA", zip_code="31201")
    assert req.to_freeform() == "123 Main St, Macon, GA, 31201"


def test_validate_request_structured_partial_to_freeform():
    """ValidateRequest with just street and state produces to_freeform() with only those parts."""
    req = ValidateRequest(street="123 Main St", state="GA")
    assert req.to_freeform() == "123 Main St, GA"


def test_validate_request_no_input_raises():
    """ValidateRequest with neither address nor street raises ValidationError."""
    with pytest.raises(ValidationError):
        ValidateRequest(city="Macon", state="GA", zip_code="31201")


def test_validate_request_empty_raises():
    """ValidateRequest with empty dict raises ValidationError."""
    with pytest.raises(ValidationError):
        ValidateRequest()


def test_validate_request_address_wins_over_structured():
    """ValidateRequest with both address and street uses address (freeform) for to_freeform()."""
    req = ValidateRequest(address="999 Oak Ave", street="123 Main St", city="Macon", state="GA")
    assert req.to_freeform() == "999 Oak Ave"


# ---------------------------------------------------------------------------
# ValidationService unit tests — helper factories
# ---------------------------------------------------------------------------

def _make_validation_orm_row(
    row_id=1,
    address_id=1,
    provider_name="scourgify",
    normalized_address="123 MAIN ST MACON GA 31201",
    address_line_1="123 MAIN ST",
    address_line_2=None,
    city="MACON",
    state="GA",
    postal_code="31201",
    confidence=1.0,
    delivery_point_verified=False,
):
    """Build a mock ValidationResultORM row simulating a cached result."""
    row = MagicMock(spec=ValidationResultORM)
    row.id = row_id
    row.address_id = address_id
    row.provider_name = provider_name
    row.normalized_address = normalized_address
    row.address_line_1 = address_line_1
    row.address_line_2 = address_line_2
    row.city = city
    row.state = state
    row.postal_code = postal_code
    row.confidence = confidence
    row.delivery_point_verified = delivery_point_verified
    return row


def _make_provider_result(
    normalized_address="123 MAIN ST MACON GA 31201",
    address_line_1="123 MAIN ST",
    city="MACON",
    state="GA",
    postal_code="31201",
    confidence=1.0,
    delivery_point_verified=False,
    provider_name="scourgify",
    original_input="123 Main Street, Macon, GA 31201",
):
    """Build a mock ValidationResult dataclass from providers/schemas.py."""
    return ValidationResultSchema(
        normalized_address=normalized_address,
        address_line_1=address_line_1,
        address_line_2=None,
        city=city,
        state=state,
        postal_code=postal_code,
        confidence=confidence,
        delivery_point_verified=delivery_point_verified,
        provider_name=provider_name,
        original_input=original_input,
    )


def _make_validation_provider(result=None):
    """Build a mock ValidationProvider returning the given result."""
    from civpulse_geo.providers.base import ValidationProvider

    provider = AsyncMock(spec=ValidationProvider)
    provider.provider_name = "scourgify"
    provider.validate = AsyncMock(
        return_value=result or _make_provider_result()
    )
    return provider


def _make_address_orm(address_id=1):
    """Build a mock Address ORM object."""
    from civpulse_geo.models.address import Address

    addr = MagicMock(spec=Address)
    addr.id = address_id
    addr.address_hash = "abc123"
    addr.normalized_address = "123 MAIN ST MACON GA 31201"
    return addr


# ---------------------------------------------------------------------------
# ValidationService.validate() — cache miss tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_cache_miss_calls_provider():
    """On cache miss, service calls provider.validate() and returns cache_hit=False."""
    service = ValidationService()
    provider = _make_validation_provider()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    orm_row = _make_validation_orm_row()

    # Sequence of db.execute calls:
    # 1. Address lookup -> None (not found)
    # 2. Cache check (validation_results query) -> empty list
    # 3. Upsert RETURNING id -> 1
    # 4. Re-query ORM row by id -> orm_row
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    cache_scalars = MagicMock()
    cache_scalars.all.return_value = []
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1

    requery_scalars = MagicMock()
    requery_scalars.first.return_value = orm_row
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result, upsert_result, requery_result])

    result = await service.validate(
        freeform="123 Main Street, Macon, GA 31201",
        db=db,
        providers={"scourgify": provider},
    )

    # Provider should have been called
    assert provider.validate.called
    # Result should indicate cache miss
    assert result["cache_hit"] is False
    assert "address_hash" in result
    assert "original_input" in result
    assert "candidates" in result


@pytest.mark.asyncio
async def test_validate_cache_miss_returns_correct_keys():
    """validate() returns dict with address_hash, original_input, candidates, cache_hit keys."""
    service = ValidationService()
    provider = _make_validation_provider()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    orm_row = _make_validation_orm_row()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    cache_scalars = MagicMock()
    cache_scalars.all.return_value = []
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1

    requery_scalars = MagicMock()
    requery_scalars.first.return_value = orm_row
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result, upsert_result, requery_result])

    result = await service.validate(
        freeform="123 Main Street, Macon, GA 31201",
        db=db,
        providers={"scourgify": provider},
    )

    assert "address_hash" in result
    assert "original_input" in result
    assert "candidates" in result
    assert "cache_hit" in result
    assert result["cache_hit"] is False
    assert result["original_input"] == "123 Main Street, Macon, GA 31201"


# ---------------------------------------------------------------------------
# ValidationService.validate() — cache hit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_cache_hit_returns_true():
    """On cache hit, service returns cache_hit=True and does NOT call provider."""
    service = ValidationService()
    provider = _make_validation_provider()

    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address_orm(address_id=5)
    cached_row = _make_validation_orm_row(row_id=10, address_id=5)

    # Address lookup -> found
    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    # Cache check -> returns rows (cache hit)
    cache_scalars = MagicMock()
    cache_scalars.all.return_value = [cached_row]
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result])

    result = await service.validate(
        freeform="123 Main Street, Macon, GA 31201",
        db=db,
        providers={"scourgify": provider},
    )

    # Provider should NOT have been called
    assert not provider.validate.called
    # Result should indicate cache hit
    assert result["cache_hit"] is True
    assert len(result["candidates"]) == 1


@pytest.mark.asyncio
async def test_validate_provider_not_called_on_cache_hit():
    """Cache hit path skips provider.validate() entirely."""
    service = ValidationService()
    provider = _make_validation_provider()

    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()

    address = _make_address_orm(address_id=3)
    cached_row = _make_validation_orm_row(row_id=7, address_id=3)

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = address
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    cache_scalars = MagicMock()
    cache_scalars.all.return_value = [cached_row]
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result])

    await service.validate(
        freeform="123 Main Street, Macon, GA 31201",
        db=db,
        providers={"scourgify": provider},
    )

    provider.validate.assert_not_called()


# ---------------------------------------------------------------------------
# ValidationService.validate() — upsert behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_upserts_result_via_db_execute():
    """validate() calls db.execute() for the pg_insert upsert statement."""
    service = ValidationService()
    provider = _make_validation_provider()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    orm_row = _make_validation_orm_row()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    cache_scalars = MagicMock()
    cache_scalars.all.return_value = []
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1

    requery_scalars = MagicMock()
    requery_scalars.first.return_value = orm_row
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result, upsert_result, requery_result])

    await service.validate(
        freeform="123 Main Street, Macon, GA 31201",
        db=db,
        providers={"scourgify": provider},
    )

    # db.execute should have been called at least 3 times:
    # 1. address lookup, 2. cache check, 3. upsert, 4. requery
    assert db.execute.call_count >= 3


# ---------------------------------------------------------------------------
# ValidationService.validate() — ProviderError propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_propagates_provider_error():
    """ProviderError from provider.validate() propagates to caller."""
    service = ValidationService()

    provider = AsyncMock()
    provider.provider_name = "scourgify"
    provider.validate = AsyncMock(side_effect=ProviderError("Address unparseable"))

    # Make provider look like a ValidationProvider for isinstance check
    from civpulse_geo.providers.base import ValidationProvider
    provider.__class__ = type("MockValidationProvider", (ValidationProvider,), {
        "provider_name": property(lambda self: "scourgify"),
        "validate": lambda self, addr: None,
        "batch_validate": lambda self, addrs: None,
    })

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.add = MagicMock()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    cache_scalars = MagicMock()
    cache_scalars.all.return_value = []
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result])

    with pytest.raises(ProviderError, match="unparseable"):
        await service.validate(
            freeform="PO Box 123, Macon, GA 31201",
            db=db,
            providers={"scourgify": provider},
        )


@pytest.mark.asyncio
async def test_validate_creates_address_on_miss():
    """When address not in DB, a new Address ORM object is added via db.add()."""
    service = ValidationService()
    provider = _make_validation_provider()

    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    added = []
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))

    orm_row = _make_validation_orm_row()

    addr_scalars = MagicMock()
    addr_scalars.first.return_value = None
    addr_result = MagicMock()
    addr_result.scalars.return_value = addr_scalars

    cache_scalars = MagicMock()
    cache_scalars.all.return_value = []
    cache_result = MagicMock()
    cache_result.scalars.return_value = cache_scalars

    upsert_result = MagicMock()
    upsert_result.scalar_one.return_value = 1

    requery_scalars = MagicMock()
    requery_scalars.first.return_value = orm_row
    requery_result = MagicMock()
    requery_result.scalars.return_value = requery_scalars

    db.execute = AsyncMock(side_effect=[addr_result, cache_result, upsert_result, requery_result])

    await service.validate(
        freeform="123 Main Street, Macon, GA 31201",
        db=db,
        providers={"scourgify": provider},
    )

    # db.add() should have been called with an Address instance
    from civpulse_geo.models.address import Address
    assert len(added) == 1
    assert isinstance(added[0], Address)
