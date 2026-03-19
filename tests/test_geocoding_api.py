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
    raw_response=None,
):
    """Build a mock GeocodingResultORM row for response construction."""
    from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

    row = MagicMock(spec=GeocodingResultORM)
    row.provider_name = provider_name
    row.latitude = latitude
    row.longitude = longitude
    row.location_type = location_type  # None means no enum value
    row.confidence = confidence
    row.raw_response = raw_response  # None or a real dict for Pydantic validation
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


# ---------------------------------------------------------------------------
# Task 1 (02-02): Admin set_official endpoint — API integration tests
# ---------------------------------------------------------------------------

MOCK_HASH = "a" * 64


def _make_mock_official_result(provider_name="census", latitude=38.845, longitude=-76.928,
                                confidence=0.8):
    """Build a mock GeocodingResultORM for official result construction."""
    from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM
    row = MagicMock(spec=GeocodingResultORM)
    row.provider_name = provider_name
    row.latitude = latitude
    row.longitude = longitude
    row.location_type = None
    row.confidence = confidence
    return row


@pytest.mark.asyncio
async def test_put_official_existing_result(patched_app_state):
    """PUT /geocode/{hash}/official with geocoding_result_id returns 200 with updated official."""
    mock_result = _make_mock_official_result()

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.set_official",
        new_callable=AsyncMock,
        return_value={
            "address_hash": MOCK_HASH,
            "official": mock_result,
            "source": "provider_result",
        },
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/geocode/{MOCK_HASH}/official",
                json={"geocoding_result_id": 1},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["address_hash"] == MOCK_HASH
    assert data["source"] == "provider_result"
    assert data["official"]["provider_name"] == "census"


@pytest.mark.asyncio
async def test_put_official_custom_coordinate(patched_app_state):
    """PUT /geocode/{hash}/official with lat/lng returns 200 with admin_override official."""
    mock_result = _make_mock_official_result(
        provider_name="admin_override", latitude=33.123, longitude=-83.456, confidence=1.0
    )

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.set_official",
        new_callable=AsyncMock,
        return_value={
            "address_hash": MOCK_HASH,
            "official": mock_result,
            "source": "admin_override",
        },
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/geocode/{MOCK_HASH}/official",
                json={"latitude": 33.123, "longitude": -83.456},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "admin_override"
    assert data["official"]["provider_name"] == "admin_override"
    assert data["official"]["latitude"] == 33.123


@pytest.mark.asyncio
async def test_put_official_unknown_hash(patched_app_state):
    """PUT /geocode/{nonexistent}/official returns 404 when address not found."""
    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.set_official",
        new_callable=AsyncMock,
        side_effect=ValueError("Address not found"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/geocode/nonexistent/official",
                json={"geocoding_result_id": 1},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_official_invalid_result_id(patched_app_state):
    """PUT /geocode/{hash}/official with invalid geocoding_result_id returns 404."""
    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.set_official",
        new_callable=AsyncMock,
        side_effect=ValueError("Geocoding result not found for this address"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/geocode/{MOCK_HASH}/official",
                json={"geocoding_result_id": 9999},
            )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Task 2 (02-02): Cache refresh and provider-specific query — API tests
# ---------------------------------------------------------------------------

def _make_mock_refresh_result(address_hash=MOCK_HASH):
    """Build a mock GeocodingResultORM for refresh response construction."""
    row = _make_mock_orm_row()
    return row


@pytest.mark.asyncio
async def test_post_refresh_triggers_re_query(patched_app_state):
    """POST /geocode/{hash}/refresh returns 200 with results and refreshed_providers."""
    mock_row = _make_mock_orm_row()

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.refresh",
        new_callable=AsyncMock,
        return_value={
            "address_hash": MOCK_HASH,
            "normalized_address": "4600 SILVER HILL RD WASHINGTON DC 20233",
            "results": [mock_row],
            "refreshed_providers": ["census"],
        },
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/geocode/{MOCK_HASH}/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["address_hash"] == MOCK_HASH
    assert "results" in data
    assert "refreshed_providers" in data
    assert "census" in data["refreshed_providers"]


@pytest.mark.asyncio
async def test_post_refresh_unknown_hash(patched_app_state):
    """POST /geocode/{nonexistent}/refresh returns 404 when address not found."""
    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.refresh",
        new_callable=AsyncMock,
        side_effect=ValueError("Address not found"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/geocode/nonexistent/refresh")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_provider_results(patched_app_state):
    """GET /geocode/{hash}/providers/census returns 200 with the census result."""
    mock_row = _make_mock_orm_row(provider_name="census")

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.get_by_provider",
        new_callable=AsyncMock,
        return_value={
            "address_hash": MOCK_HASH,
            "provider_name": "census",
            "result": mock_row,
        },
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/geocode/{MOCK_HASH}/providers/census")

    assert response.status_code == 200
    data = response.json()
    assert data["provider_name"] == "census"
    assert data["address_hash"] == MOCK_HASH
    assert "latitude" in data
    assert "longitude" in data


@pytest.mark.asyncio
async def test_get_provider_not_found(patched_app_state):
    """GET /geocode/{hash}/providers/nonexistent returns 404."""
    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.get_by_provider",
        new_callable=AsyncMock,
        side_effect=ValueError("No result from provider 'nonexistent' for this address"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/geocode/{MOCK_HASH}/providers/nonexistent")

    assert response.status_code == 404
