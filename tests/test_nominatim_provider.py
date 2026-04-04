"""Unit tests for NominatimGeocodingProvider.

These tests describe the full provider contract and are written in the RED phase.
They will FAIL until Plan 02 creates src/civpulse_geo/providers/nominatim.py.

Tests verify:
- provider_name returns "nominatim"
- Successful geocode: correct coordinate mapping, confidence from importance, location_type from OSM type
- No match: empty list → NO_MATCH result (lat=0.0, lng=0.0, confidence=0.0)
- Network error raises ProviderNetworkError
- HTTP 500 raises ProviderNetworkError
- batch_geocode calls geocode serially for each address, returning results in order
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.providers.nominatim import NominatimGeocodingProvider
from civpulse_geo.providers.exceptions import ProviderNetworkError
from civpulse_geo.providers.schemas import GeocodingResult

NOMINATIM_MATCH_RESPONSE = [
    {
        "place_id": 1,
        "lat": "33.749",
        "lon": "-84.388",
        "display_name": "Atlanta, Fulton County, Georgia, United States",
        "type": "city",
        "class": "place",
        "importance": 0.75,
    }
]

NOMINATIM_NO_MATCH_RESPONSE: list = []

TEST_ADDRESS = "Atlanta, GA"


def _make_mock_client(json_data: list | dict, status_code: int = 200) -> AsyncMock:
    """Build an AsyncMock httpx.AsyncClient returning the given JSON."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = MagicMock()  # no-op on success
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_provider_name():
    """provider_name property returns the string 'nominatim'."""
    provider = NominatimGeocodingProvider()
    assert provider.provider_name == "nominatim"


@pytest.mark.asyncio
async def test_geocode_success():
    """/search returns one result → GeocodingResult with correct lat/lng, confidence, location_type."""
    mock_client = _make_mock_client(NOMINATIM_MATCH_RESPONSE)
    provider = NominatimGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert isinstance(result, GeocodingResult)
    assert result.lat == pytest.approx(33.749)
    assert result.lng == pytest.approx(-84.388)
    assert result.provider_name == "nominatim"
    assert result.confidence >= 0.7
    assert result.location_type != "NO_MATCH"


@pytest.mark.asyncio
async def test_geocode_no_match():
    """/search returns [] → NO_MATCH result with zero coords and confidence=0.0."""
    mock_client = _make_mock_client(NOMINATIM_NO_MATCH_RESPONSE)
    provider = NominatimGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert result.lat == 0.0
    assert result.lng == 0.0
    assert result.location_type == "NO_MATCH"
    assert result.confidence == 0.0
    assert result.provider_name == "nominatim"


@pytest.mark.asyncio
async def test_geocode_http_error():
    """HTTP 500 from upstream is wrapped and raised as ProviderNetworkError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Internal Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    mock_client.get = AsyncMock(return_value=mock_response)
    provider = NominatimGeocodingProvider(http_client=mock_client)

    with pytest.raises(ProviderNetworkError):
        await provider.geocode(TEST_ADDRESS)


@pytest.mark.asyncio
async def test_geocode_http_500():
    """Alias for HTTP 500 — raises ProviderNetworkError (same as test_geocode_http_error)."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    mock_client.get = AsyncMock(return_value=mock_response)
    provider = NominatimGeocodingProvider(http_client=mock_client)

    with pytest.raises(ProviderNetworkError):
        await provider.geocode(TEST_ADDRESS)


@pytest.mark.asyncio
async def test_geocode_network_error():
    """httpx.RequestError is wrapped and raised as ProviderNetworkError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(
        side_effect=httpx.RequestError("Connection refused")
    )
    provider = NominatimGeocodingProvider(http_client=mock_client)

    with pytest.raises(ProviderNetworkError):
        await provider.geocode(TEST_ADDRESS)


@pytest.mark.asyncio
async def test_batch_geocode_serial():
    """batch_geocode(["a","b"]) calls geocode twice and returns list of 2 GeocodingResults in order."""
    mock_client = _make_mock_client(NOMINATIM_MATCH_RESPONSE)
    provider = NominatimGeocodingProvider(http_client=mock_client)
    addresses = ["Atlanta, GA", "Macon, GA"]

    results = await provider.batch_geocode(addresses)

    assert len(results) == 2
    assert mock_client.get.call_count == 2
    for result in results:
        assert isinstance(result, GeocodingResult)
        assert result.provider_name == "nominatim"
