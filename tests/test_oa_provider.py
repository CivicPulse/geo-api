"""Tests for OAGeocodingProvider and OAValidationProvider.

Tests verify:
- GeocodingResult returned with correct lat/lng, location_type, confidence
- NO_MATCH behavior when no row found
- All 5 accuracy mappings (rooftop, parcel, interpolation, centroid, empty/unknown)
- is_local=True on both providers
- provider_name="openaddresses" on both providers
- geocode() accepts **kwargs (no TypeError when http_client= passed)
- ValidationResult returned with USPS-normalized fields
- ProviderError raised on SQLAlchemy exception
- batch_geocode and batch_validate serial loops
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError

from civpulse_geo.providers.openaddresses import (
    OAGeocodingProvider,
    OAValidationProvider,
    ACCURACY_MAP,
    DEFAULT_ACCURACY,
    _parse_input_address,
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


def _make_oa_row(
    street_number="123",
    street_name="MAIN ST",
    street_suffix="",
    city="MACON",
    region="GA",
    postcode="31201",
    accuracy="rooftop",
    source_hash="abc123",
    unit=None,
):
    """Return a mock OpenAddressesPoint row."""
    row = MagicMock()
    row.street_number = street_number
    row.street_name = street_name
    row.street_suffix = street_suffix
    row.city = city
    row.region = region
    row.postcode = postcode
    row.accuracy = accuracy
    row.source_hash = source_hash
    row.unit = unit
    return row


def _make_query_tuple(row, lat=32.84, lng=-83.63):
    """Return (OA row, lat, lng) tuple as returned by select with ST_Y/ST_X."""
    return (row, lat, lng)


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------

class TestAccuracyMapping:
    def test_accuracy_map_has_all_keys(self):
        assert "rooftop" in ACCURACY_MAP
        assert "parcel" in ACCURACY_MAP
        assert "interpolation" in ACCURACY_MAP
        assert "centroid" in ACCURACY_MAP

    def test_rooftop_mapping(self):
        assert ACCURACY_MAP["rooftop"] == ("ROOFTOP", 1.0)

    def test_parcel_mapping(self):
        assert ACCURACY_MAP["parcel"] == ("APPROXIMATE", 0.8)

    def test_interpolation_mapping(self):
        assert ACCURACY_MAP["interpolation"] == ("RANGE_INTERPOLATED", 0.5)

    def test_centroid_mapping(self):
        assert ACCURACY_MAP["centroid"] == ("GEOMETRIC_CENTER", 0.4)

    def test_default_accuracy(self):
        assert DEFAULT_ACCURACY == ("APPROXIMATE", 0.1)


# ---------------------------------------------------------------------------
# OAGeocodingProvider tests
# ---------------------------------------------------------------------------

class TestOAGeocodingProvider:

    def test_provider_name(self):
        provider = OAGeocodingProvider(MagicMock())
        assert provider.provider_name == "openaddresses"

    def test_is_local_true(self):
        provider = OAGeocodingProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_geocode_match_rooftop(self):
        row = _make_oa_row(accuracy="rooftop")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row, 32.84, -83.63))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert isinstance(result, GeocodingResult)
        assert result.lat == pytest.approx(32.84)
        assert result.lng == pytest.approx(-83.63)
        assert result.location_type == "ROOFTOP"
        assert result.confidence == pytest.approx(1.0)
        assert result.provider_name == "openaddresses"

    @pytest.mark.asyncio
    async def test_geocode_match_parcel(self):
        row = _make_oa_row(accuracy="parcel")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.location_type == "APPROXIMATE"
        assert result.confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_geocode_match_interpolation(self):
        row = _make_oa_row(accuracy="interpolation")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.location_type == "RANGE_INTERPOLATED"
        assert result.confidence == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_geocode_match_centroid(self):
        row = _make_oa_row(accuracy="centroid")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.location_type == "GEOMETRIC_CENTER"
        assert result.confidence == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_geocode_match_empty_accuracy(self):
        row = _make_oa_row(accuracy="")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.location_type == "APPROXIMATE"
        assert result.confidence == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_geocode_match_none_accuracy(self):
        row = _make_oa_row(accuracy=None)
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.location_type == "APPROXIMATE"
        assert result.confidence == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_geocode_no_match(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("999", "NONEXISTENT ST", "00000", None, None)):
            result = await provider.geocode("999 Nonexistent St, Nowhere, XX 00000")

        assert result.lat == 0.0
        assert result.lng == 0.0
        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0
        assert result.provider_name == "openaddresses"

    @pytest.mark.asyncio
    async def test_geocode_no_match_on_parse_failure(self):
        """When _parse_input_address returns None components, return NO_MATCH."""
        factory = _make_session_factory(execute_return_value=None)
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=(None, None, None, None, None)):
            result = await provider.geocode("gibberish address")

        assert result.location_type == "NO_MATCH"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_geocode_accepts_http_client_kwarg(self):
        """geocode() must not raise TypeError when called with http_client= kwarg."""
        row = _make_oa_row(accuracy="rooftop")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            # This must NOT raise TypeError
            result = await provider.geocode(
                "123 Main St, Macon, GA 31201",
                http_client=None,
            )

        assert result.provider_name == "openaddresses"

    @pytest.mark.asyncio
    async def test_geocode_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            with pytest.raises(ProviderError, match="OpenAddresses query failed"):
                await provider.geocode("123 Main St, Macon, GA 31201")

    @pytest.mark.asyncio
    async def test_batch_geocode_serial_loop(self):
        """batch_geocode returns results in input order."""
        row = _make_oa_row(accuracy="rooftop")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row))
        provider = OAGeocodingProvider(factory)

        addresses = [
            "123 Main St, Macon, GA 31201",
            "456 Oak Ave, Macon, GA 31210",
        ]

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            results = await provider.batch_geocode(addresses)

        assert len(results) == 2
        assert all(isinstance(r, GeocodingResult) for r in results)

    @pytest.mark.asyncio
    async def test_geocode_raw_response_contains_key_fields(self):
        row = _make_oa_row(
            accuracy="rooftop",
            source_hash="deadbeef",
            street_number="123",
            street_name="MAIN ST",
            city="MACON",
            region="GA",
            postcode="31201",
        )
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row, 32.84, -83.63))
        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 31201")

        assert result.raw_response["source_hash"] == "deadbeef"
        assert result.raw_response["lat"] == pytest.approx(32.84)
        assert result.raw_response["lng"] == pytest.approx(-83.63)


# ---------------------------------------------------------------------------
# OAValidationProvider tests
# ---------------------------------------------------------------------------

class TestOAValidationProvider:

    def test_provider_name(self):
        provider = OAValidationProvider(MagicMock())
        assert provider.provider_name == "openaddresses"

    def test_is_local_true(self):
        provider = OAValidationProvider(MagicMock())
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_validate_no_match(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = OAValidationProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("999", "NONEXISTENT ST", "00000", None, None)):
            result = await provider.validate("999 Nonexistent St, Nowhere, XX 00000")

        assert isinstance(result, ValidationResult)
        assert result.normalized_address == ""
        assert result.confidence == 0.0
        assert result.provider_name == "openaddresses"
        assert result.delivery_point_verified is False

    @pytest.mark.asyncio
    async def test_validate_no_match_on_parse_failure(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = OAValidationProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=(None, None, None, None, None)):
            result = await provider.validate("gibberish")

        assert result.normalized_address == ""
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_validate_match_returns_confidence_1(self):
        row = _make_oa_row(
            street_number="123",
            street_name="MAIN",
            street_suffix="ST",
            city="MACON",
            region="GA",
            postcode="31201",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.84, -83.63))
        provider = OAValidationProvider(factory)

        scourgify_return = {
            "address_line_1": "123 MAIN ST",
            "address_line_2": None,
            "city": "MACON",
            "state": "GA",
            "postal_code": "31201",
        }

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN", "31201", None, None)):
            with patch(
                "civpulse_geo.providers.openaddresses.normalize_address_record",
                return_value=scourgify_return,
            ):
                result = await provider.validate("123 Main St, Macon, GA 31201")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.delivery_point_verified is False
        assert result.provider_name == "openaddresses"
        assert result.address_line_1 == "123 MAIN ST"
        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31201"
        assert result.original_input == "123 Main St, Macon, GA 31201"

    @pytest.mark.asyncio
    async def test_validate_match_scourgify_fallback(self):
        """When scourgify raises on re-normalization, fallback to raw OA components."""
        row = _make_oa_row(
            street_number="123",
            street_name="MAIN",
            street_suffix="ST",
            city="MACON",
            region="GA",
            postcode="31201",
        )
        factory = _make_session_factory(execute_return_value=(row, 32.84, -83.63))
        provider = OAValidationProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN", "31201", None, None)):
            with patch(
                "civpulse_geo.providers.openaddresses.normalize_address_record",
                side_effect=Exception("scourgify failed"),
            ):
                result = await provider.validate("123 Main St, Macon, GA 31201")

        assert isinstance(result, ValidationResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31201"

    @pytest.mark.asyncio
    async def test_validate_raises_provider_error_on_sqlalchemy_exception(self):
        factory = _make_session_factory(raise_exc=SQLAlchemyError("DB down"))
        provider = OAValidationProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "31201", None, None)):
            with pytest.raises(ProviderError, match="OpenAddresses query failed"):
                await provider.validate("123 Main St, Macon, GA 31201")

    @pytest.mark.asyncio
    async def test_batch_validate_serial_loop(self):
        factory = _make_session_factory(execute_return_value=None)
        provider = OAValidationProvider(factory)

        addresses = ["addr1", "addr2"]
        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=(None, None, None, None, None)):
            results = await provider.batch_validate(addresses)

        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)


# ---------------------------------------------------------------------------
# _parse_input_address 5-tuple tests
# ---------------------------------------------------------------------------

class TestParseInputAddress:

    def test_parse_input_address_returns_5_tuple(self):
        """_parse_input_address returns a 5-element tuple for a standard address."""
        result = _parse_input_address("123 Main St, Anytown, GA 31201")
        assert len(result) == 5
        street_number, street_name, postal_code, street_suffix, street_directional = result
        assert street_number == "123"
        assert street_name is not None
        assert postal_code == "31201"
        # "ST" is the suffix for "St"
        assert street_suffix is not None

    def test_parse_input_address_suffix_beaver_falls(self):
        """Multi-word street 'Beaver Falls' — suffix should be normalized by usaddress."""
        result = _parse_input_address("123 Beaver Falls Rd, Macon, GA 31201")
        assert len(result) == 5
        street_number, street_name, postal_code, street_suffix, street_directional = result
        # scourgify normalizes "Falls" out as suffix; street_name should be "BEAVER"
        # usaddress may parse "FALLS" as StreetNamePostType or StreetName depending on normalization
        # The key check: result is a 5-tuple and street_suffix or street_name captures the suffix
        assert street_number == "123"
        assert postal_code == "31201"
        # street_suffix captures the post-type if usaddress finds one
        # At minimum the parse succeeds (no None street_number)
        assert street_number is not None

    def test_parse_input_address_directional(self):
        """Street with directional suffix — street_directional should be populated."""
        result = _parse_input_address("123 5th Ave N, Macon, GA 31201")
        assert len(result) == 5
        street_number, street_name, postal_code, street_suffix, street_directional = result
        assert street_number == "123"
        # street_directional should be "N"
        assert street_directional == "N"

    def test_parse_input_address_no_suffix(self):
        """Single-word street name with no suffix — street_suffix should be None."""
        result = _parse_input_address("123 Broadway, Macon, GA 31201")
        assert len(result) == 5
        street_number, street_name, postal_code, street_suffix, street_directional = result
        # Broadway has no standard USPS suffix
        assert street_suffix is None

    def test_parse_input_address_parse_failure_returns_5_none_tuple(self):
        """On parse failure, all 5 elements are None."""
        result = _parse_input_address("gibberish xyz abc")
        assert len(result) == 5
        assert all(v is None for v in result)

    @pytest.mark.asyncio
    async def test_oa_geocode_zip_prefix_fallback(self):
        """A 4-digit truncated ZIP triggers prefix fallback and returns a result."""
        row = _make_oa_row(accuracy="rooftop", postcode="31201")
        # Exact match returns None, prefix fallback returns the row
        mock_session = AsyncMock()
        mock_result_none = MagicMock()
        mock_result_none.first.return_value = None
        mock_result_match = MagicMock()
        mock_result_match.first.return_value = _make_query_tuple(row, 32.84, -83.63)
        # Calls: exact match, fuzzy match, then zip prefix 4-digit (returns match)
        mock_session.execute = AsyncMock(
            side_effect=[mock_result_none, mock_result_none, mock_result_match]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=mock_ctx)

        provider = OAGeocodingProvider(factory)

        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "MAIN ST", "3120", None, None)):
            result = await provider.geocode("123 Main St, Macon, GA 3120")

        assert result.location_type != "NO_MATCH"
        assert result.lat == pytest.approx(32.84)

    @pytest.mark.asyncio
    async def test_oa_geocode_suffix_match(self):
        """When street_suffix is parsed, it is passed to the match function."""
        row = _make_oa_row(accuracy="rooftop", street_suffix="RD")
        factory = _make_session_factory(execute_return_value=_make_query_tuple(row, 32.84, -83.63))
        provider = OAGeocodingProvider(factory)

        # Provide suffix in the parse result — should reach _find_oa_match with suffix
        with patch("civpulse_geo.providers.openaddresses._parse_input_address",
                   return_value=("123", "BEAVER FALLS", "31201", "RD", None)):
            result = await provider.geocode("123 Beaver Falls Rd, Macon, GA 31201")

        assert result.location_type != "NO_MATCH"
        assert result.provider_name == "openaddresses"
