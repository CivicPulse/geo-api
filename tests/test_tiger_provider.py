"""Tests for TigerGeocodingProvider, TigerValidationProvider, and _tiger_extension_available.

Tests verify:
- GeocodingResult returned with correct lat/lng, RANGE_INTERPOLATED location_type, confidence
- Confidence mapping: rating 0 -> 1.0, rating 50 -> 0.5, rating 100 -> 0.0, rating 108 clamped to 0.0
- NO_MATCH behavior when no row found or parsed=False
- is_local=True on both providers
- provider_name="postgis_tiger" on both providers
- geocode() accepts **kwargs (no TypeError when http_client= passed)
- ValidationResult returned with address components built from norm_addy fields
- ProviderError raised on SQLAlchemy exception
- batch_geocode and batch_validate serial loops
- _tiger_extension_available returns True/False/False on match/no-match/exception
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import SQLAlchemyError

from civpulse_geo.providers.tiger import (
    TigerGeocodingProvider,
    TigerValidationProvider,
    _tiger_extension_available,
)
from civpulse_geo.providers.schemas import GeocodingResult, ValidationResult
from civpulse_geo.providers.exceptions import ProviderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_factory(execute_return_value=None, raise_exc=None):
    """Build a mock async_sessionmaker that works with 'async with factory() as session'."""
    mock_session = AsyncMock()

    if raise_exc is not None:
        mock_session.execute.side_effect = raise_exc
    else:
        mock_result = MagicMock()
        mock_result.first.return_value = execute_return_value
        mock_session.execute = AsyncMock(return_value=mock_result)

    # Support 'async with session_factory() as session'
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory


def _make_geocode_row(
    rating=10,
    lat=32.84,
    lng=-83.63,
    address_number="123",
    predir=None,
    street_name="MAIN",
    street_type="ST",
    postdir=None,
    internal=None,
    city="MACON",
    state="GA",
    zip="31201",
    zip4=None,
    parsed=True,
):
    """Return a mock row with all geocode() column aliases."""
    row = MagicMock()
    row.rating = rating
    row.lat = lat
    row.lng = lng
    row.address_number = address_number
    row.predir = predir
    row.street_name = street_name
    row.street_type = street_type
    row.postdir = postdir
    row.internal = internal
    row.city = city
    row.state = state
    row.zip = zip
    row.zip4 = zip4
    row.parsed = parsed
    return row


def _make_normalize_row(
    address_number="123",
    predir=None,
    street_name="MAIN",
    street_type="ST",
    postdir=None,
    internal=None,
    city="MACON",
    state="GA",
    zip="31201",
    zip4=None,
    parsed=True,
):
    """Return a mock row with all normalize_address() column aliases."""
    row = MagicMock()
    row.address_number = address_number
    row.predir = predir
    row.street_name = street_name
    row.street_type = street_type
    row.postdir = postdir
    row.internal = internal
    row.city = city
    row.state = state
    row.zip = zip
    row.zip4 = zip4
    row.parsed = parsed
    return row


# ---------------------------------------------------------------------------
# TigerGeocodingProvider tests
# ---------------------------------------------------------------------------

class TestTigerGeocodingProvider:

    def test_provider_name(self):
        provider = TigerGeocodingProvider(MagicMock())
        assert provider.provider_name == "postgis_tiger"

    def test_is_local_true(self):
        provider = TigerGeocodingProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_geocode_match_returns_range_interpolated(self):
        row = _make_geocode_row(rating=10, lat=32.84, lng=-83.63)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert isinstance(result, GeocodingResult)
        assert result.lat == pytest.approx(32.84)
        assert result.lng == pytest.approx(-83.63)
        assert result.location_type == "RANGE_INTERPOLATED"
        assert result.confidence == pytest.approx(0.9)  # (100 - 10) / 100
        assert result.provider_name == "postgis_tiger"

    @pytest.mark.asyncio
    async def test_geocode_rating_0_confidence_1(self):
        row = _make_geocode_row(rating=0)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("123 Main St")

        assert result.confidence == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_geocode_rating_100_confidence_0(self):
        row = _make_geocode_row(rating=100)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("123 Main St")

        assert result.confidence == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_geocode_rating_108_clamped_to_0(self):
        """Rating exceeding 100 should be clamped to 0.0, not negative."""
        row = _make_geocode_row(rating=108)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("123 Main St")

        assert result.confidence == pytest.approx(0.0)
        assert result.confidence >= 0.0  # never negative

    @pytest.mark.asyncio
    async def test_geocode_rating_50_confidence_half(self):
        row = _make_geocode_row(rating=50)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("123 Main St")

        assert result.confidence == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_geocode_no_match_when_result_none(self):
        """When result.first() returns None, geocode() returns NO_MATCH result."""
        factory = _make_session_factory(execute_return_value=None)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("999 Nonexistent St")

        assert result.lat == 0.0
        assert result.lng == 0.0
        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0
        assert result.provider_name == "postgis_tiger"

    @pytest.mark.asyncio
    async def test_geocode_accepts_http_client_kwarg(self):
        """geocode() must not raise TypeError when called with http_client= kwarg."""
        row = _make_geocode_row(rating=10)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        # This must NOT raise TypeError
        result = await provider.geocode("123 Main St", http_client=None)

        assert result.provider_name == "postgis_tiger"

    @pytest.mark.asyncio
    async def test_geocode_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = TigerGeocodingProvider(factory)

        with pytest.raises(ProviderError, match="Tiger geocode query failed"):
            await provider.geocode("123 Main St")

    @pytest.mark.asyncio
    async def test_geocode_raw_response_contains_all_fields(self):
        """raw_response dict must contain all norm_addy field keys."""
        row = _make_geocode_row(
            rating=10,
            address_number="123",
            predir=None,
            street_name="MAIN",
            street_type="ST",
            postdir=None,
            internal=None,
            city="MACON",
            state="GA",
            zip="31201",
            zip4=None,
            parsed=True,
        )
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        result = await provider.geocode("123 Main St")

        expected_keys = {
            "rating", "address_number", "predir", "street_name", "street_type",
            "postdir", "internal", "city", "state", "zip", "zip4", "parsed",
        }
        assert expected_keys.issubset(set(result.raw_response.keys()))

    @pytest.mark.asyncio
    async def test_batch_geocode_serial_loop(self):
        """batch_geocode returns results in input order."""
        row = _make_geocode_row(rating=10)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerGeocodingProvider(factory)

        addresses = ["123 Main St, Macon, GA 31201", "456 Oak Ave, Macon, GA 31210"]
        results = await provider.batch_geocode(addresses)

        assert len(results) == 2
        assert all(isinstance(r, GeocodingResult) for r in results)


# ---------------------------------------------------------------------------
# TigerValidationProvider tests
# ---------------------------------------------------------------------------

class TestTigerValidationProvider:

    def test_provider_name(self):
        provider = TigerValidationProvider(MagicMock())
        assert provider.provider_name == "postgis_tiger"

    def test_is_local_true(self):
        provider = TigerValidationProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_validate_match_parsed_true_returns_confidence_1(self):
        row = _make_normalize_row(parsed=True)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerValidationProvider(factory)

        result = await provider.validate("123 Main St, Macon, GA 31201")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.provider_name == "postgis_tiger"
        assert result.delivery_point_verified is False
        assert result.original_input == "123 Main St, Macon, GA 31201"

    @pytest.mark.asyncio
    async def test_validate_match_address_line_1_built_from_components(self):
        """address_line_1 is built from address_number, predir, street_name, street_type, postdir."""
        row = _make_normalize_row(
            address_number="123",
            predir=None,
            street_name="MAIN",
            street_type="ST",
            postdir=None,
            parsed=True,
        )
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerValidationProvider(factory)

        result = await provider.validate("123 Main St")

        # address_line_1 should be "123 MAIN ST" (None components filtered out)
        assert result.address_line_1 == "123 MAIN ST"

    @pytest.mark.asyncio
    async def test_validate_match_state_city_zip_populated(self):
        row = _make_normalize_row(city="MACON", state="GA", zip="31201", parsed=True)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerValidationProvider(factory)

        result = await provider.validate("123 Main St")

        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31201"

    @pytest.mark.asyncio
    async def test_validate_parsed_false_returns_no_match(self):
        """When parsed=False, validate() returns NO_MATCH ValidationResult."""
        row = _make_normalize_row(parsed=False)
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerValidationProvider(factory)

        result = await provider.validate("something unparseable")

        assert result.confidence == 0.0
        assert result.normalized_address == ""
        assert result.address_line_1 == ""
        assert result.city is None
        assert result.state is None
        assert result.postal_code is None
        assert result.provider_name == "postgis_tiger"

    @pytest.mark.asyncio
    async def test_validate_none_row_returns_no_match(self):
        """When result.first() returns None, validate() returns NO_MATCH."""
        factory = _make_session_factory(execute_return_value=None)
        provider = TigerValidationProvider(factory)

        result = await provider.validate("999 Nonexistent St")

        assert result.confidence == 0.0
        assert result.normalized_address == ""
        assert result.address_line_1 == ""
        assert result.provider_name == "postgis_tiger"

    @pytest.mark.asyncio
    async def test_validate_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = TigerValidationProvider(factory)

        with pytest.raises(ProviderError, match="Tiger normalize_address query failed"):
            await provider.validate("123 Main St")

    @pytest.mark.asyncio
    async def test_validate_result_contains_state_city_zip_fields(self):
        """validate() result exposes state, city, and zip components."""
        row = _make_normalize_row(
            city="MACON",
            state="GA",
            zip="31201",
            street_name="MAIN",
            street_type="ST",
            parsed=True,
        )
        factory = _make_session_factory(execute_return_value=row)
        provider = TigerValidationProvider(factory)

        result = await provider.validate("123 Main St")

        assert result.state == "GA"
        assert result.city == "MACON"
        assert result.postal_code == "31201"

    @pytest.mark.asyncio
    async def test_batch_validate_serial_loop(self):
        """batch_validate returns results in input order."""
        factory = _make_session_factory(execute_return_value=None)
        provider = TigerValidationProvider(factory)

        addresses = ["addr1", "addr2"]
        results = await provider.batch_validate(addresses)

        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)


# ---------------------------------------------------------------------------
# _tiger_extension_available tests
# ---------------------------------------------------------------------------

class TestTigerExtensionCheck:

    @pytest.mark.asyncio
    async def test_returns_true_when_extension_present(self):
        """Returns True when pg_available_extensions query finds the row."""
        factory = _make_session_factory(execute_return_value=MagicMock())
        result = await _tiger_extension_available(factory)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_query_returns_none(self):
        """Returns False when pg_available_extensions query returns no row."""
        factory = _make_session_factory(execute_return_value=None)
        result = await _tiger_extension_available(factory)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """Returns False when any exception is raised during the check."""
        factory = _make_session_factory(raise_exc=Exception("DB error"))
        result = await _tiger_extension_available(factory)
        assert result is False
