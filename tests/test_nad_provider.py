"""Tests for NADGeocodingProvider and NADValidationProvider.

Tests verify:
- GeocodingResult returned with correct lat/lng, location_type, confidence
- PLACEMENT_MAP covers all 7 known Placement values with exact (location_type, confidence) tuples
- DEFAULT_PLACEMENT used for None, empty string, unknown, and garbage placement values
- NO_MATCH behavior when no row found or parse fails
- is_local=True on both providers
- provider_name="national_address_database" on both providers
- geocode() accepts **kwargs (no TypeError when http_client= passed)
- ValidationResult returned with USPS-normalized fields using NAD columns (state, zip_code)
- scourgify fallback uses raw NAD columns (state not region, zip_code not postcode)
- ProviderError raised on SQLAlchemy exception
- batch_geocode and batch_validate serial loops
- _nad_data_available returns True/False based on table presence
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError

from civpulse_geo.providers.nad import (
    NADGeocodingProvider,
    NADValidationProvider,
    PLACEMENT_MAP,
    DEFAULT_PLACEMENT,
    _nad_data_available,
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


def _make_nad_row(
    street_number="123",
    street_name="MAIN ST",
    street_suffix="",
    city="MACON",
    state="GA",
    zip_code="31201",
    placement="Structure - Rooftop",
    source_hash="abc123",
    unit=None,
):
    """Return a mock NADPoint row with NAD-specific column names."""
    row = MagicMock()
    row.street_number = street_number
    row.street_name = street_name
    row.street_suffix = street_suffix
    row.city = city
    row.state = state          # Note: state, not region
    row.zip_code = zip_code    # Note: zip_code, not postcode
    row.placement = placement
    row.source_hash = source_hash
    row.unit = unit
    return row


def _make_query_tuple(row, lat=32.84, lng=-83.63):
    """Return (NAD row, lat, lng) tuple as returned by select with ST_Y/ST_X."""
    return (row, lat, lng)


# ---------------------------------------------------------------------------
# Placement mapping tests
# ---------------------------------------------------------------------------

class TestPlacementMapping:

    def test_placement_map_has_all_seven_keys(self):
        expected_keys = {
            "Structure - Rooftop",
            "Structure - Entrance",
            "Site",
            "Property Access",
            "Parcel - Other",
            "Linear Geocode",
            "Parcel - Centroid",
        }
        assert set(PLACEMENT_MAP.keys()) == expected_keys

    def test_structure_rooftop_mapping(self):
        assert PLACEMENT_MAP["Structure - Rooftop"] == ("ROOFTOP", 1.0)

    def test_structure_entrance_mapping(self):
        assert PLACEMENT_MAP["Structure - Entrance"] == ("ROOFTOP", 1.0)

    def test_site_mapping(self):
        assert PLACEMENT_MAP["Site"] == ("APPROXIMATE", 0.8)

    def test_property_access_mapping(self):
        assert PLACEMENT_MAP["Property Access"] == ("APPROXIMATE", 0.8)

    def test_parcel_other_mapping(self):
        assert PLACEMENT_MAP["Parcel - Other"] == ("APPROXIMATE", 0.6)

    def test_linear_geocode_mapping(self):
        assert PLACEMENT_MAP["Linear Geocode"] == ("RANGE_INTERPOLATED", 0.5)

    def test_parcel_centroid_mapping(self):
        assert PLACEMENT_MAP["Parcel - Centroid"] == ("GEOMETRIC_CENTER", 0.4)

    def test_default_placement(self):
        assert DEFAULT_PLACEMENT == ("APPROXIMATE", 0.1)


# ---------------------------------------------------------------------------
# NADGeocodingProvider tests
# ---------------------------------------------------------------------------

class TestNADGeocodingProvider:

    def test_provider_name(self):
        provider = NADGeocodingProvider(MagicMock())
        assert provider.provider_name == "national_address_database"

    def test_is_local_true(self):
        provider = NADGeocodingProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_geocode_match_returns_correct_lat_lng_and_placement(self):
        row = _make_nad_row(placement="Structure - Rooftop")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row, 32.84, -83.63))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert isinstance(result, GeocodingResult)
        assert result.lat == pytest.approx(32.84)
        assert result.lng == pytest.approx(-83.63)
        assert result.location_type == "ROOFTOP"
        assert result.confidence == pytest.approx(1.0)
        assert result.provider_name == "national_address_database"

    @pytest.mark.asyncio
    async def test_geocode_no_match_returns_no_match(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("999", "NONEXISTENT ST", "00000", None, None)):
            result = await provider.geocode("999 Nonexistent St, Nowhere, XX 00000")

        assert result.lat == 0.0
        assert result.lng == 0.0
        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0
        assert result.provider_name == "national_address_database"

    @pytest.mark.asyncio
    async def test_geocode_parse_failure_returns_no_match_without_db_query(self):
        """When _parse_input_address returns None components, return NO_MATCH without DB query."""
        mock_factory = MagicMock()
        provider = NADGeocodingProvider(mock_factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=(None, None, None, None, None)):
            result = await provider.geocode("gibberish address")

        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0
        # No DB call should have been made
        mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_geocode_accepts_http_client_kwarg(self):
        """geocode() must not raise TypeError when called with http_client= kwarg."""
        row = _make_nad_row(placement="Structure - Rooftop")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            # Must NOT raise TypeError
            result = await provider.geocode(
                "123 Main St, Macon, GA 31201",
                http_client=None,
            )

        assert result.provider_name == "national_address_database"

    @pytest.mark.asyncio
    async def test_geocode_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            with pytest.raises(ProviderError, match="NAD query failed"):
                await provider.geocode("123 Main St, Macon, GA 31201")

    @pytest.mark.asyncio
    async def test_geocode_raw_response_contains_nad_fields(self):
        row = _make_nad_row(
            placement="Structure - Rooftop",
            source_hash="deadbeef",
            street_number="123",
            street_name="MAIN ST",
            city="MACON",
            state="GA",
            zip_code="31201",
        )
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row, 32.84, -83.63))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.raw_response["source_hash"] == "deadbeef"
        assert result.raw_response["lat"] == pytest.approx(32.84)
        assert result.raw_response["lng"] == pytest.approx(-83.63)
        assert "placement" in result.raw_response

    @pytest.mark.asyncio
    async def test_batch_geocode_returns_list_in_input_order(self):
        """batch_geocode returns results in input order."""
        row = _make_nad_row(placement="Structure - Rooftop")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = NADGeocodingProvider(factory)

        addresses = [
            "123 Main St, Macon, GA 31201",
            "456 Oak Ave, Macon, GA 31210",
        ]

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            results = await provider.batch_geocode(addresses)

        assert len(results) == 2
        assert all(isinstance(r, GeocodingResult) for r in results)

    @pytest.mark.asyncio
    async def test_geocode_placement_none_uses_default(self):
        """placement=None maps to DEFAULT_PLACEMENT."""
        row = _make_nad_row(placement=None)
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        location_type, confidence = DEFAULT_PLACEMENT
        assert result.location_type == location_type
        assert result.confidence == pytest.approx(confidence)

    @pytest.mark.asyncio
    async def test_geocode_placement_empty_string_uses_default(self):
        """placement="" maps to DEFAULT_PLACEMENT."""
        row = _make_nad_row(placement="")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        location_type, confidence = DEFAULT_PLACEMENT
        assert result.location_type == location_type
        assert result.confidence == pytest.approx(confidence)

    @pytest.mark.asyncio
    async def test_geocode_placement_unknown_string_uses_default(self):
        """placement="Unknown" maps to DEFAULT_PLACEMENT."""
        row = _make_nad_row(placement="Unknown")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        location_type, confidence = DEFAULT_PLACEMENT
        assert result.location_type == location_type
        assert result.confidence == pytest.approx(confidence)

    @pytest.mark.asyncio
    async def test_geocode_placement_garbage_value_uses_default(self):
        """placement="0" (garbage) maps to DEFAULT_PLACEMENT."""
        row = _make_nad_row(placement="0")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        location_type, confidence = DEFAULT_PLACEMENT
        assert result.location_type == location_type
        assert result.confidence == pytest.approx(confidence)


# ---------------------------------------------------------------------------
# NADValidationProvider tests
# ---------------------------------------------------------------------------

class TestNADValidationProvider:

    def test_provider_name(self):
        provider = NADValidationProvider(MagicMock())
        assert provider.provider_name == "national_address_database"

    def test_is_local_true(self):
        provider = NADValidationProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_validate_match_returns_confidence_1_delivery_point_false(self):
        row = _make_nad_row(
            street_number="123",
            street_name="MAIN",
            street_suffix="ST",
            city="MACON",
            state="GA",
            zip_code="31201",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.84, -83.63))
        provider = NADValidationProvider(factory)

        scourgify_return = {
            "address_line_1": "123 MAIN ST",
            "address_line_2": None,
            "city": "MACON",
            "state": "GA",
            "postal_code": "31201",
        }

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN", "31201", None, None)):
            with patch(
                "civpulse_geo.providers.nad.normalize_address_record",
                return_value=scourgify_return,
            ):
                result = await provider.validate("123 Main St, Macon, GA 31201")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.delivery_point_verified is False

    @pytest.mark.asyncio
    async def test_validate_match_populates_nad_fields(self):
        """validate with match populates address_line_1, city, state (from nad_row.state), postal_code (from nad_row.zip_code)."""
        row = _make_nad_row(
            street_number="123",
            street_name="MAIN",
            street_suffix="ST",
            city="MACON",
            state="GA",
            zip_code="31201",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.84, -83.63))
        provider = NADValidationProvider(factory)

        scourgify_return = {
            "address_line_1": "123 MAIN ST",
            "address_line_2": None,
            "city": "MACON",
            "state": "GA",
            "postal_code": "31201",
        }

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN", "31201", None, None)):
            with patch(
                "civpulse_geo.providers.nad.normalize_address_record",
                return_value=scourgify_return,
            ):
                result = await provider.validate("123 Main St, Macon, GA 31201")

        assert result.address_line_1 == "123 MAIN ST"
        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31201"
        assert result.provider_name == "national_address_database"
        assert result.original_input == "123 Main St, Macon, GA 31201"

    @pytest.mark.asyncio
    async def test_validate_no_match_returns_confidence_0(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = NADValidationProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("999", "NONEXISTENT ST", "00000", None, None)):
            result = await provider.validate("999 Nonexistent St, Nowhere, XX 00000")

        assert isinstance(result, ValidationResult)
        assert result.confidence == 0.0
        assert result.provider_name == "national_address_database"
        assert result.delivery_point_verified is False

    @pytest.mark.asyncio
    async def test_validate_parse_failure_returns_confidence_0(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = NADValidationProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=(None, None, None, None, None)):
            result = await provider.validate("gibberish")

        assert result.normalized_address == ""
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_validate_scourgify_fallback_uses_nad_columns(self):
        """When scourgify raises on re-normalization, fallback uses nad_row.state (not .region) and nad_row.zip_code (not .postcode)."""
        row = _make_nad_row(
            street_number="123",
            street_name="MAIN",
            street_suffix="ST",
            city="MACON",
            state="GA",
            zip_code="31201",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.84, -83.63))
        provider = NADValidationProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN", "31201", None, None)):
            with patch(
                "civpulse_geo.providers.nad.normalize_address_record",
                side_effect=Exception("scourgify failed"),
            ):
                result = await provider.validate("123 Main St, Macon, GA 31201")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.city == "MACON"
        # Fallback must use .state (not .region) and .zip_code (not .postcode)
        assert result.state == "GA"
        assert result.postal_code == "31201"

    @pytest.mark.asyncio
    async def test_validate_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = NADValidationProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            with pytest.raises(ProviderError, match="NAD query failed"):
                await provider.validate("123 Main St, Macon, GA 31201")

    @pytest.mark.asyncio
    async def test_batch_validate_returns_list_in_input_order(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = NADValidationProvider(factory)

        addresses = ["addr1", "addr2"]
        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=(None, None, None, None, None)):
            results = await provider.batch_validate(addresses)

        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)


# ---------------------------------------------------------------------------
# NAD zip prefix fallback tests
# ---------------------------------------------------------------------------

class TestNADZipPrefixFallback:

    @pytest.mark.asyncio
    async def test_nad_geocode_zip_prefix_fallback(self):
        """A 4-digit truncated ZIP triggers prefix fallback in NADGeocodingProvider."""
        row = _make_nad_row(placement="Structure - Rooftop", zip_code="31201")
        # Calls: exact match → None, fuzzy match → None, 4-digit prefix → match
        mock_session = AsyncMock()
        mock_result_none = MagicMock()
        mock_result_none.first.return_value = None
        mock_result_match = MagicMock()
        mock_result_match.first.return_value = _make_query_tuple(row, 32.84, -83.63)
        mock_session.execute = AsyncMock(
            side_effect=[mock_result_none, mock_result_none, mock_result_match]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=mock_ctx)

        provider = NADGeocodingProvider(factory)

        with patch("civpulse_geo.providers.nad._parse_input_address",
                   return_value=("123", "MAIN ST", "3120", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 3120")

        assert result.location_type != "NO_MATCH"
        assert result.lat == pytest.approx(32.84)
        assert result.provider_name == "national_address_database"


# ---------------------------------------------------------------------------
# _nad_data_available tests
# ---------------------------------------------------------------------------

class TestNadDataAvailable:

    @pytest.mark.asyncio
    async def test_returns_true_when_table_has_data(self):
        """Returns True when session scalar returns a truthy value."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        result = await _nad_data_available(mock_factory)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_table_is_empty(self):
        """Returns False when session scalar returns False."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        result = await _nad_data_available(mock_factory)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """Returns False on any exception."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        result = await _nad_data_available(mock_factory)
        assert result is False
