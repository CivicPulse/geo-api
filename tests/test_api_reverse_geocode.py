"""FastAPI contract tests for GET /geocode/reverse endpoint (Plan 26-02).

These tests describe the full reverse-geocoding endpoint contract and are written
in the RED phase. They FAIL until Plans 03-04 implement the route and schemas.

Contract:
- GET /geocode/reverse?lat={float}&lon={float}
- Returns: {address, lat, lon, place_id, raw_nominatim_response}
- 404 when Nominatim returns {"error": "Unable to geocode"}
- 503 when "nominatim" key is absent from app.state.providers
- 422 when lat is out of [-90, 90] range or required params are missing

Uses AsyncClient + ASGITransport pattern (same as test_api_tiles.py).
app.state.http_client is replaced with AsyncMock(spec=httpx.AsyncClient).
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from civpulse_geo.main import app


def _mock_nominatim_response(json_data: dict | list, status_code: int = 200) -> MagicMock:
    """Build a minimal mock httpx.Response for Nominatim reverse geocode tests."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


REVERSE_MATCH_RESPONSE = {
    "display_name": "123 Peachtree St, Atlanta, GA 30303",
    "lat": "33.749",
    "lon": "-84.388",
    "place_id": 42,
}

REVERSE_NO_MATCH_RESPONSE = {
    "error": "Unable to geocode",
}


@pytest.fixture
def patched_nominatim_client():
    """Override app.state.http_client with AsyncMock for reverse geocode tests.

    Also ensures app.state.providers has a 'nominatim' key (as a sentinel).
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    original_client = getattr(app.state, "http_client", None)
    original_providers = getattr(app.state, "providers", None)

    app.state.http_client = mock_client
    # Ensure nominatim is registered; use a simple sentinel object
    if not hasattr(app.state, "providers") or app.state.providers is None:
        app.state.providers = {}
    app.state.providers["nominatim"] = MagicMock()

    yield mock_client

    # Restore original state
    if original_client is not None:
        app.state.http_client = original_client
    else:
        try:
            del app.state.http_client
        except AttributeError:
            pass

    if original_providers is not None:
        app.state.providers = original_providers
    else:
        try:
            del app.state.providers
        except AttributeError:
            pass


@pytest.mark.asyncio
async def test_reverse_happy_path(patched_nominatim_client):
    """GET /geocode/reverse?lat=33.749&lon=-84.388 → 200 with address, lat, lon, place_id."""
    patched_nominatim_client.get = AsyncMock(
        return_value=_mock_nominatim_response(REVERSE_MATCH_RESPONSE)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/geocode/reverse", params={"lat": 33.749, "lon": -84.388}
        )

    assert response.status_code == 200
    body = response.json()
    assert "address" in body
    assert "123 Peachtree St" in body["address"]
    assert body["lat"] == pytest.approx(33.749, abs=0.001)
    assert body["lon"] == pytest.approx(-84.388, abs=0.001)
    assert body["place_id"] == 42

    # Verify the correct upstream endpoint was called
    assert patched_nominatim_client.get.called
    call_args = patched_nominatim_client.get.call_args
    called_url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
    assert called_url.endswith("/reverse") or "/reverse" in called_url, (
        f"Expected URL containing '/reverse', got {called_url!r}"
    )


@pytest.mark.asyncio
async def test_reverse_no_match_returns_404(patched_nominatim_client):
    """Upstream returns {'error': 'Unable to geocode'} → 404 with detail 'No address found'."""
    patched_nominatim_client.get = AsyncMock(
        return_value=_mock_nominatim_response(REVERSE_NO_MATCH_RESPONSE)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/geocode/reverse", params={"lat": 33.749, "lon": -84.388}
        )

    assert response.status_code == 404
    body = response.json()
    assert "No address found" in body.get("detail", "")


@pytest.mark.asyncio
async def test_reverse_service_unavailable_503():
    """When 'nominatim' key is absent from app.state.providers → 503 with detail about provider."""
    original_providers = getattr(app.state, "providers", None)

    # Ensure nominatim is NOT in providers
    if not hasattr(app.state, "providers") or app.state.providers is None:
        app.state.providers = {}
    # Remove nominatim if present
    app.state.providers.pop("nominatim", None)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/geocode/reverse", params={"lat": 33.749, "lon": -84.388}
            )

        assert response.status_code == 503
        body = response.json()
        assert "Nominatim" in body.get("detail", "") or "nominatim" in body.get("detail", "")
    finally:
        if original_providers is not None:
            app.state.providers = original_providers
        else:
            try:
                del app.state.providers
            except AttributeError:
                pass


@pytest.mark.asyncio
async def test_reverse_invalid_lat_422():
    """GET /geocode/reverse?lat=999&lon=0 → 422 (lat must be in [-90, 90])."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/geocode/reverse", params={"lat": 999, "lon": 0}
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reverse_missing_params_422():
    """GET /geocode/reverse (no lat/lon) → 422 (required query parameters missing)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/geocode/reverse")

    assert response.status_code == 422
