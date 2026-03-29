"""Tests for MaconBibbGeocodingProvider and MaconBibbValidationProvider.

Tests verify:
- GeocodingResult returned with correct lat/lng, location_type, confidence
- ADDRESS_TYPE_MAP covers PARCEL, STRUCTURE, SITE with correct (location_type, confidence) tuples
- DEFAULT_ADDRESS_TYPE used for None, empty string, and unknown address type values
- NO_MATCH behavior when no row found or parse fails
- is_local=True on both providers
- provider_name="macon_bibb" on both providers
- geocode() accepts **kwargs (no TypeError when http_client= passed)
- Fuzzy match returns halved confidence and fuzzy_match=True in raw_response
- ValidationResult returned with USPS-normalized fields using state/zip_code columns
- ProviderError raised on SQLAlchemy exception
- batch_geocode and batch_validate serial loops
- _macon_bibb_data_available returns True/False based on table presence
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError

from civpulse_geo.providers.macon_bibb import (
    MaconBibbGeocodingProvider,
    MaconBibbValidationProvider,
    ADDRESS_TYPE_MAP,
    DEFAULT_ADDRESS_TYPE,
    _macon_bibb_data_available,
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

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory


def _make_macon_bibb_row(
    street_number="489",
    street_name="NORTHMINSTER",
    street_suffix="DR",
    city="MACON",
    state="GA",
    zip_code="31204",
    address_type="PARCEL",
    source_hash="abc123",
    unit=None,
):
    """Return a mock MaconBibbPoint row."""
    row = MagicMock()
    row.street_number = street_number
    row.street_name = street_name
    row.street_suffix = street_suffix
    row.city = city
    row.state = state
    row.zip_code = zip_code
    row.address_type = address_type
    row.source_hash = source_hash
    row.unit = unit
    return row


def _make_query_tuple(row, lat=32.872, lng=-83.687):
    """Return (MaconBibbPoint row, lat, lng) tuple as returned by select with ST_Y/ST_X."""
    return (row, lat, lng)


# ---------------------------------------------------------------------------
# ADDRESS_TYPE_MAP tests
# ---------------------------------------------------------------------------

class TestAddressTypeMapping:

    def test_address_type_map_has_expected_keys(self):
        expected_keys = {"PARCEL", "STRUCTURE", "SITE"}
        assert set(ADDRESS_TYPE_MAP.keys()) == expected_keys

    def test_parcel_mapping(self):
        assert ADDRESS_TYPE_MAP["PARCEL"] == ("APPROXIMATE", 0.8)

    def test_structure_mapping(self):
        assert ADDRESS_TYPE_MAP["STRUCTURE"] == ("ROOFTOP", 1.0)

    def test_site_mapping(self):
        assert ADDRESS_TYPE_MAP["SITE"] == ("APPROXIMATE", 0.8)

    def test_default_address_type(self):
        assert DEFAULT_ADDRESS_TYPE == ("APPROXIMATE", 0.1)


# ---------------------------------------------------------------------------
# MaconBibbGeocodingProvider tests
# ---------------------------------------------------------------------------

class TestMaconBibbGeocodingProvider:

    def test_provider_name(self):
        provider = MaconBibbGeocodingProvider(MagicMock())
        assert provider.provider_name == "macon_bibb"

    def test_is_local_true(self):
        provider = MaconBibbGeocodingProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_geocode_exact_match_returns_correct_lat_lng_and_confidence(self):
        row = _make_macon_bibb_row(address_type="STRUCTURE")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row, 32.872, -83.687))
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            result = await provider.geocode("489 Northminster Dr, Macon, GA 31204")

        assert isinstance(result, GeocodingResult)
        assert result.lat == pytest.approx(32.872)
        assert result.lng == pytest.approx(-83.687)
        assert result.location_type == "ROOFTOP"
        assert result.confidence == pytest.approx(1.0)
        assert result.provider_name == "macon_bibb"

    @pytest.mark.asyncio
    async def test_geocode_parcel_type_returns_approximate(self):
        row = _make_macon_bibb_row(address_type="PARCEL")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            result = await provider.geocode("489 Northminster Dr, Macon, GA 31204")

        assert result.location_type == "APPROXIMATE"
        assert result.confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_geocode_no_match_returns_no_match(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("999", "NONEXISTENT", "00000", None, None)):
            result = await provider.geocode("999 Nonexistent St, Nowhere, XX 00000")

        assert result.lat == 0.0
        assert result.lng == 0.0
        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0
        assert result.provider_name == "macon_bibb"

    @pytest.mark.asyncio
    async def test_geocode_parse_failure_returns_no_match_without_db_query(self):
        """When _parse_input_address returns None, return NO_MATCH without DB query."""
        mock_factory = MagicMock()
        provider = MaconBibbGeocodingProvider(mock_factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=(None, None, None, None, None)):
            result = await provider.geocode("gibberish address")

        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0
        mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_geocode_accepts_http_client_kwarg(self):
        """geocode() must not raise TypeError when called with http_client= kwarg."""
        row = _make_macon_bibb_row(address_type="PARCEL")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            result = await provider.geocode(
                "489 Northminster Dr, Macon, GA 31204",
                http_client=None,
            )

        assert result.provider_name == "macon_bibb"

    @pytest.mark.asyncio
    async def test_geocode_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            with pytest.raises(ProviderError, match="Macon-Bibb query failed"):
                await provider.geocode("489 Northminster Dr, Macon, GA 31204")

    @pytest.mark.asyncio
    async def test_geocode_fuzzy_match_halves_confidence(self):
        """Fuzzy match returns result with halved confidence and fuzzy_match=True."""
        row = _make_macon_bibb_row(address_type="PARCEL")
        # First call (exact) returns None, second call (fuzzy) returns row
        mock_session = AsyncMock()
        mock_result_none = MagicMock()
        mock_result_none.first.return_value = None
        mock_result_match = MagicMock()
        mock_result_match.first.return_value = _make_query_tuple(row)
        mock_session.execute = AsyncMock(side_effect=[mock_result_none, mock_result_match])

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=mock_ctx)

        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("490", "NORTHMINSTER", "31204", None, None)):
            result = await provider.geocode("490 Northminster Dr, Macon, GA 31204")

        assert result.confidence == pytest.approx(0.4)  # 0.8 / 2
        assert result.raw_response.get("fuzzy_match") is True

    @pytest.mark.asyncio
    async def test_geocode_address_type_none_uses_default(self):
        """address_type=None maps to DEFAULT_ADDRESS_TYPE."""
        row = _make_macon_bibb_row(address_type=None)
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            result = await provider.geocode("489 Northminster Dr, Macon, GA 31204")

        location_type, confidence = DEFAULT_ADDRESS_TYPE
        assert result.location_type == location_type
        assert result.confidence == pytest.approx(confidence)

    @pytest.mark.asyncio
    async def test_geocode_address_type_unknown_uses_default(self):
        """Unknown address_type maps to DEFAULT_ADDRESS_TYPE."""
        row = _make_macon_bibb_row(address_type="UNKNOWN_TYPE")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            result = await provider.geocode("489 Northminster Dr, Macon, GA 31204")

        location_type, confidence = DEFAULT_ADDRESS_TYPE
        assert result.location_type == location_type
        assert result.confidence == pytest.approx(confidence)

    @pytest.mark.asyncio
    async def test_batch_geocode_returns_list_in_input_order(self):
        row = _make_macon_bibb_row(address_type="PARCEL")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = MaconBibbGeocodingProvider(factory)

        addresses = [
            "489 Northminster Dr, Macon, GA 31204",
            "100 Cherry St, Macon, GA 31201",
        ]

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            results = await provider.batch_geocode(addresses)

        assert len(results) == 2
        assert all(isinstance(r, GeocodingResult) for r in results)


# ---------------------------------------------------------------------------
# MaconBibbValidationProvider tests
# ---------------------------------------------------------------------------

class TestMaconBibbValidationProvider:

    def test_provider_name(self):
        provider = MaconBibbValidationProvider(MagicMock())
        assert provider.provider_name == "macon_bibb"

    def test_is_local_true(self):
        provider = MaconBibbValidationProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_validate_match_returns_confidence_1_delivery_point_false(self):
        row = _make_macon_bibb_row(
            street_number="489",
            street_name="NORTHMINSTER",
            street_suffix="DR",
            city="MACON",
            state="GA",
            zip_code="31204",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.872, -83.687))
        provider = MaconBibbValidationProvider(factory)

        scourgify_return = {
            "address_line_1": "489 NORTHMINSTER DR",
            "address_line_2": None,
            "city": "MACON",
            "state": "GA",
            "postal_code": "31204",
        }

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            with patch(
                "civpulse_geo.providers.macon_bibb.normalize_address_record",
                return_value=scourgify_return,
            ):
                result = await provider.validate("489 Northminster Dr, Macon, GA 31204")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.delivery_point_verified is False

    @pytest.mark.asyncio
    async def test_validate_match_populates_usps_fields(self):
        row = _make_macon_bibb_row(
            street_number="489",
            street_name="NORTHMINSTER",
            street_suffix="DR",
            city="MACON",
            state="GA",
            zip_code="31204",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.872, -83.687))
        provider = MaconBibbValidationProvider(factory)

        scourgify_return = {
            "address_line_1": "489 NORTHMINSTER DR",
            "address_line_2": None,
            "city": "MACON",
            "state": "GA",
            "postal_code": "31204",
        }

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            with patch(
                "civpulse_geo.providers.macon_bibb.normalize_address_record",
                return_value=scourgify_return,
            ):
                result = await provider.validate("489 Northminster Dr, Macon, GA 31204")

        assert result.address_line_1 == "489 NORTHMINSTER DR"
        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31204"
        assert result.provider_name == "macon_bibb"
        assert result.original_input == "489 Northminster Dr, Macon, GA 31204"

    @pytest.mark.asyncio
    async def test_validate_no_match_returns_confidence_0(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = MaconBibbValidationProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("999", "NONEXISTENT", "00000", None, None)):
            result = await provider.validate("999 Nonexistent St, Nowhere, XX 00000")

        assert isinstance(result, ValidationResult)
        assert result.confidence == 0.0
        assert result.provider_name == "macon_bibb"
        assert result.delivery_point_verified is False

    @pytest.mark.asyncio
    async def test_validate_parse_failure_returns_confidence_0(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = MaconBibbValidationProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=(None, None, None, None, None)):
            result = await provider.validate("gibberish")

        assert result.normalized_address == ""
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_validate_scourgify_fallback_uses_state_and_zip_code_columns(self):
        """When scourgify raises, fallback uses row.state and row.zip_code."""
        row = _make_macon_bibb_row(
            street_number="489",
            street_name="NORTHMINSTER",
            street_suffix="DR",
            city="MACON",
            state="GA",
            zip_code="31204",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.872, -83.687))
        provider = MaconBibbValidationProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            with patch(
                "civpulse_geo.providers.macon_bibb.normalize_address_record",
                side_effect=Exception("scourgify failed"),
            ):
                result = await provider.validate("489 Northminster Dr, Macon, GA 31204")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31204"

    @pytest.mark.asyncio
    async def test_validate_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = MaconBibbValidationProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "31204", None, None)):
            with pytest.raises(ProviderError, match="Macon-Bibb query failed"):
                await provider.validate("489 Northminster Dr, Macon, GA 31204")

    @pytest.mark.asyncio
    async def test_batch_validate_returns_list_in_input_order(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = MaconBibbValidationProvider(factory)

        addresses = ["addr1", "addr2"]
        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=(None, None, None, None, None)):
            results = await provider.batch_validate(addresses)

        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)


# ---------------------------------------------------------------------------
# Macon-Bibb zip prefix fallback tests
# ---------------------------------------------------------------------------

class TestMaconBibbZipPrefixFallback:

    @pytest.mark.asyncio
    async def test_macon_bibb_geocode_zip_prefix_fallback(self):
        """A 4-digit truncated ZIP triggers prefix fallback in MaconBibbGeocodingProvider."""
        row = _make_macon_bibb_row(address_type="STRUCTURE", zip_code="31204")
        # Calls: exact match → None, fuzzy match → None, 4-digit prefix → match
        mock_session = AsyncMock()
        mock_result_none = MagicMock()
        mock_result_none.first.return_value = None
        mock_result_match = MagicMock()
        mock_result_match.first.return_value = _make_query_tuple(row, 32.872, -83.687)
        mock_session.execute = AsyncMock(
            side_effect=[mock_result_none, mock_result_none, mock_result_match]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=mock_ctx)

        provider = MaconBibbGeocodingProvider(factory)

        with patch("civpulse_geo.providers.macon_bibb._parse_input_address",
                   return_value=("489", "NORTHMINSTER", "3120", None, None)):
            result = await provider.geocode("489 Northminster Dr, Macon, GA 3120")

        assert result.location_type != "NO_MATCH"
        assert result.lat == pytest.approx(32.872)
        assert result.provider_name == "macon_bibb"


# ---------------------------------------------------------------------------
# _macon_bibb_data_available tests
# ---------------------------------------------------------------------------

class TestMaconBibbDataAvailable:

    @pytest.mark.asyncio
    async def test_returns_true_when_table_has_data(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        result = await _macon_bibb_data_available(mock_factory)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_table_is_empty(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        result = await _macon_bibb_data_available(mock_factory)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        result = await _macon_bibb_data_available(mock_factory)
        assert result is False
