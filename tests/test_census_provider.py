"""Unit tests for CensusGeocodingProvider.

Tests verify:
- provider_name returns "census"
- Successful geocode: correct coordinate mapping (y=lat, x=lng), confidence=0.8
- No match: returns zero coordinates, confidence=0.0
- Network error raises ProviderNetworkError
- HTTP error raises ProviderNetworkError
- batch_geocode calls geocode serially for each address
- Raw Census JSON response is preserved in raw_response
- Confidence values are correct for match and no-match cases
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.providers.census import CensusGeocodingProvider
from civpulse_geo.providers.exceptions import ProviderNetworkError
from civpulse_geo.providers.schemas import GeocodingResult

# Verified Census API response format (from RESEARCH.md)
CENSUS_MATCH_RESPONSE = {
    "result": {
        "addressMatches": [
            {
                "coordinates": {
                    "x": -76.928365658124,
                    "y": 38.845053106269,
                },
                "matchedAddress": "4600 SILVER HILL RD, WASHINGTON, DC, 20233",
                "tigerLine": {"tigerLineId": "76355984", "side": "L"},
                "addressComponents": {
                    "fromAddress": "4498",
                    "toAddress": "4600",
                    "preQualifier": "",
                    "preDirection": "",
                    "preType": "",
                    "streetName": "SILVER HILL",
                    "suffixType": "RD",
                    "suffixDirection": "",
                    "suffixQualifier": "",
                    "city": "WASHINGTON",
                    "state": "DC",
                    "zip": "20233",
                },
            }
        ]
    }
}

CENSUS_NO_MATCH_RESPONSE = {
    "result": {
        "addressMatches": [],
    }
}

TEST_ADDRESS = "4600 Silver Hill Rd Washington DC 20233"


def _make_mock_client(json_data: dict, status_code: int = 200) -> AsyncMock:
    """Build an AsyncMock httpx.AsyncClient returning the given JSON."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = MagicMock()  # no-op on success
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_provider_name_is_census():
    """provider_name property returns the string 'census'."""
    provider = CensusGeocodingProvider()
    assert provider.provider_name == "census"


@pytest.mark.asyncio
async def test_geocode_successful_match():
    """Successful match returns correct lat/lng with RANGE_INTERPOLATED type."""
    mock_client = _make_mock_client(CENSUS_MATCH_RESPONSE)
    provider = CensusGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert isinstance(result, GeocodingResult)
    # CRITICAL: y=lat, x=lng
    assert result.lat == pytest.approx(38.845053106269)
    assert result.lng == pytest.approx(-76.928365658124)
    assert result.location_type == "RANGE_INTERPOLATED"
    assert result.confidence == 0.8
    assert result.provider_name == "census"


@pytest.mark.asyncio
async def test_geocode_no_match():
    """Empty addressMatches returns zero coordinates, NO_MATCH type, 0.0 confidence."""
    mock_client = _make_mock_client(CENSUS_NO_MATCH_RESPONSE)
    provider = CensusGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert result.lat == 0.0
    assert result.lng == 0.0
    assert result.location_type == "NO_MATCH"
    assert result.confidence == 0.0
    assert result.provider_name == "census"


@pytest.mark.asyncio
async def test_geocode_network_error():
    """httpx.RequestError is wrapped and raised as ProviderNetworkError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(
        side_effect=httpx.RequestError("Connection refused")
    )
    provider = CensusGeocodingProvider(http_client=mock_client)

    with pytest.raises(ProviderNetworkError):
        await provider.geocode(TEST_ADDRESS)


@pytest.mark.asyncio
async def test_geocode_http_error():
    """HTTP 500 response is wrapped and raised as ProviderNetworkError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    mock_client.get = AsyncMock(return_value=mock_response)
    provider = CensusGeocodingProvider(http_client=mock_client)

    with pytest.raises(ProviderNetworkError):
        await provider.geocode(TEST_ADDRESS)


@pytest.mark.asyncio
async def test_batch_geocode_calls_geocode_serially():
    """batch_geocode calls geocode once per address and returns results in order."""
    mock_client = _make_mock_client(CENSUS_MATCH_RESPONSE)
    provider = CensusGeocodingProvider(http_client=mock_client)
    addresses = [
        "100 Main St Springfield IL 62701",
        "200 Oak Ave Chicago IL 60601",
        "300 Pine Rd Boston MA 02101",
    ]

    results = await provider.batch_geocode(addresses, http_client=mock_client)

    assert len(results) == 3
    assert mock_client.get.call_count == 3
    for result in results:
        assert isinstance(result, GeocodingResult)
        assert result.provider_name == "census"


@pytest.mark.asyncio
async def test_raw_response_preserved():
    """The full Census JSON response is stored in raw_response field."""
    mock_client = _make_mock_client(CENSUS_MATCH_RESPONSE)
    provider = CensusGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert result.raw_response == CENSUS_MATCH_RESPONSE
    # Verify nested structure is intact
    assert result.raw_response["result"]["addressMatches"][0]["matchedAddress"] == (
        "4600 SILVER HILL RD, WASHINGTON, DC, 20233"
    )


@pytest.mark.asyncio
async def test_confidence_on_match():
    """Successful match always returns confidence=0.8 (Census fixed value)."""
    mock_client = _make_mock_client(CENSUS_MATCH_RESPONSE)
    provider = CensusGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert result.confidence == 0.8


@pytest.mark.asyncio
async def test_confidence_on_no_match():
    """No match returns confidence=0.0."""
    mock_client = _make_mock_client(CENSUS_NO_MATCH_RESPONSE)
    provider = CensusGeocodingProvider(http_client=mock_client)

    result = await provider.geocode(TEST_ADDRESS)

    assert result.confidence == 0.0
