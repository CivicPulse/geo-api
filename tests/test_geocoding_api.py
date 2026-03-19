"""Integration tests for POST /geocode endpoint.

Tests verify:
- POST /geocode with valid address returns HTTP 200
- Response contains all required fields in GeocodeResponse structure
- POST /geocode with missing address field returns HTTP 422 validation error
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from civpulse_geo.main import app
from civpulse_geo.database import get_db
from civpulse_geo.schemas.geocoding import GeocodeResponse


TEST_ADDRESS = "4600 Silver Hill Rd Washington DC 20233"


def _make_mock_orm_row(
    provider_name="census",
    latitude=38.845,
    longitude=-76.928,
    location_type=None,
    confidence=0.8,
):
    """Build a mock GeocodingResultORM row for response construction."""
    from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

    row = MagicMock(spec=GeocodingResultORM)
    row.provider_name = provider_name
    row.latitude = latitude
    row.longitude = longitude
    row.location_type = location_type  # None means no enum value
    row.confidence = confidence
    return row


@pytest.fixture
def patched_app_state(mock_http_client, mock_providers):
    """Set app.state.http_client and app.state.providers to avoid lifespan dependency."""
    app.state.http_client = mock_http_client
    app.state.providers = mock_providers
    yield
    # Cleanup
    try:
        del app.state.http_client
    except AttributeError:
        pass
    try:
        del app.state.providers
    except AttributeError:
        pass


@pytest.mark.asyncio
async def test_post_geocode_returns_200(patched_app_state):
    """POST /geocode with a valid address body returns HTTP 200."""
    mock_orm_row = _make_mock_orm_row()

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.geocode",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "a" * 64,
            "normalized_address": "4600 SILVER HILL RD WASHINGTON DC 20233",
            "cache_hit": False,
            "results": [mock_orm_row],
            "official": None,
        },
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/geocode", json={"address": TEST_ADDRESS}
            )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_geocode_response_structure(patched_app_state):
    """Response contains all required GeocodeResponse fields with correct types."""
    mock_orm_row = _make_mock_orm_row()

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.geocode",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "b" * 64,
            "normalized_address": "4600 SILVER HILL RD WASHINGTON DC 20233",
            "cache_hit": False,
            "results": [mock_orm_row],
            "official": None,
        },
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/geocode", json={"address": TEST_ADDRESS}
            )

    assert response.status_code == 200
    data = response.json()

    # Required top-level fields
    assert "address_hash" in data
    assert len(data["address_hash"]) == 64  # SHA-256 hex is 64 chars
    assert "normalized_address" in data
    assert isinstance(data["normalized_address"], str)
    assert "cache_hit" in data
    assert isinstance(data["cache_hit"], bool)
    assert "results" in data
    assert isinstance(data["results"], list)

    # Per-provider result structure
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert "provider_name" in result
    assert result["provider_name"] == "census"
    assert "latitude" in result
    assert "longitude" in result
    assert "confidence" in result


@pytest.mark.asyncio
async def test_post_geocode_missing_address(patched_app_state):
    """POST /geocode with empty body returns HTTP 422 Unprocessable Entity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/geocode", json={})

    assert response.status_code == 422
