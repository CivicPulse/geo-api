"""FastAPI contract tests for GET /route endpoint (Plan 27-01 TDD RED phase).

These tests describe the full routing endpoint contract and are written in
the RED phase. They FAIL until Plan 27-02 implements the route handler and schemas.

Contract:
- GET /route?start={lat},{lon}&end={lat},{lon}&mode={pedestrian|auto}
- Proxies to Valhalla sidecar via POST /route with JSON body
- Returns RouteResponse: mode, polyline, duration_seconds, distance_meters, maneuvers, raw_valhalla
- 400: invalid coord format, invalid mode, same start == end
- 404: Valhalla returns no-route response
- 422: missing required query param
- 502: upstream timeout / connect error
- 503: valhalla_enabled is False

Covers requirements: ROUTE-01, ROUTE-02, ROUTE-03

Uses AsyncClient + ASGITransport pattern (same as test_api_tiles.py, test_api_poi_search.py).
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from civpulse_geo.main import app

# ---------------------------------------------------------------------------
# Constants: valid Georgia coordinates
# ---------------------------------------------------------------------------

START = "33.7490,-84.3880"
END = "33.7701,-84.3876"

# Minimal Valhalla trip response with 2 maneuvers
VALHALLA_TRIP_2_MANEUVERS = {
    "trip": {
        "legs": [
            {
                "shape": "encoded_polyline6_string",
                "summary": {"time": 124.5, "length": 0.83},
                "maneuvers": [
                    {
                        "instruction": "Walk east on Peachtree St",
                        "length": 0.12,
                        "time": 18.0,
                        "type": 1,
                    },
                    {
                        "instruction": "Turn right onto 5th St",
                        "length": 0.71,
                        "time": 106.5,
                        "type": 10,
                    },
                ],
            }
        ],
        "summary": {"time": 124.5, "length": 0.83},
    }
}

# Valhalla trip with summary.length=1.5 km (for km->meters conversion test)
VALHALLA_TRIP_1_5KM = {
    "trip": {
        "legs": [
            {
                "shape": "another_polyline_string",
                "summary": {"time": 900.0, "length": 1.5},
                "maneuvers": [
                    {
                        "instruction": "Head north",
                        "length": 1.5,
                        "time": 900.0,
                        "type": 1,
                    }
                ],
            }
        ],
        "summary": {"time": 900.0, "length": 1.5},
    }
}

# Valhalla no-route / error response
VALHALLA_NO_ROUTE = {"error": "No path found between points", "error_code": 442}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _mock_valhalla_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Build a minimal mock httpx.Response for Valhalla route tests."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_valhalla_http():
    """Override app.state.http_client with an AsyncMock and set valhalla_enabled=True."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    original_client = getattr(app.state, "http_client", None)
    original_enabled = getattr(app.state, "valhalla_enabled", None)

    app.state.http_client = mock_client
    app.state.valhalla_enabled = True

    yield mock_client

    # Restore
    if original_client is not None:
        app.state.http_client = original_client
    else:
        try:
            del app.state.http_client
        except AttributeError:
            pass

    if original_enabled is not None:
        app.state.valhalla_enabled = original_enabled
    else:
        try:
            del app.state.valhalla_enabled
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_pedestrian_returns_200_with_route_response(patched_valhalla_http):
    """GET /route?mode=pedestrian → 200 with RouteResponse; verifies POST body to Valhalla.

    Covers ROUTE-01, ROUTE-03.
    """
    patched_valhalla_http.post = AsyncMock(
        return_value=_mock_valhalla_response(VALHALLA_TRIP_2_MANEUVERS)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "pedestrian"
    assert len(body["maneuvers"]) == 2
    assert isinstance(body["polyline"], str) and len(body["polyline"]) > 0
    assert body["duration_seconds"] > 0
    assert body["distance_meters"] > 0

    # Spot-check: verify POST body sent to Valhalla
    assert patched_valhalla_http.post.called
    call_kwargs = patched_valhalla_http.post.call_args[1]
    post_json = call_kwargs.get("json", {})
    assert post_json == {
        "locations": [
            {"lat": 33.7490, "lon": -84.3880},
            {"lat": 33.7701, "lon": -84.3876},
        ],
        "costing": "pedestrian",
        "units": "kilometers",
    }, f"Unexpected POST body to Valhalla: {post_json!r}"


@pytest.mark.asyncio
async def test_route_auto_returns_200_with_route_response(patched_valhalla_http):
    """GET /route?mode=auto → 200 with mode='auto' in response.

    Covers ROUTE-02.
    """
    patched_valhalla_http.post = AsyncMock(
        return_value=_mock_valhalla_response(VALHALLA_TRIP_2_MANEUVERS)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "auto"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "auto"


@pytest.mark.asyncio
async def test_route_response_converts_km_to_meters(patched_valhalla_http):
    """Valhalla summary.length=1.5 km → response distance_meters==1500.0.

    Covers ROUTE-03 (unit conversion).
    """
    patched_valhalla_http.post = AsyncMock(
        return_value=_mock_valhalla_response(VALHALLA_TRIP_1_5KM)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["distance_meters"] == 1500.0


@pytest.mark.asyncio
async def test_route_maneuver_schema_contains_required_fields(patched_valhalla_http):
    """Each maneuver in response has instruction (str), distance_meters (float),
    duration_seconds (float), type (int).

    Covers ROUTE-03 (schema correctness).
    """
    patched_valhalla_http.post = AsyncMock(
        return_value=_mock_valhalla_response(VALHALLA_TRIP_2_MANEUVERS)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 200
    body = response.json()
    for maneuver in body["maneuvers"]:
        assert "instruction" in maneuver
        assert "distance_meters" in maneuver
        assert "duration_seconds" in maneuver
        assert "type" in maneuver
        assert isinstance(maneuver["instruction"], str)
        assert isinstance(maneuver["distance_meters"], float)
        assert isinstance(maneuver["duration_seconds"], float)
        assert isinstance(maneuver["type"], int)


@pytest.mark.asyncio
async def test_route_missing_start_returns_422():
    """GET /route without start param → 422 (required query param missing)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_route_invalid_start_format_returns_400(patched_valhalla_http):
    """GET /route?start=not-a-coord → 400 detail mentions 'start' or 'format'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": "not-a-coord", "end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail", "").lower()
    assert "start" in detail or "format" in detail or "invalid" in detail, (
        f"Expected 'start' or 'format' or 'invalid' in detail, got {detail!r}"
    )


@pytest.mark.asyncio
async def test_route_invalid_mode_returns_400(patched_valhalla_http):
    """GET /route?mode=walking (not in {pedestrian, auto}) → 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "walking"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_route_same_start_and_end_returns_400(patched_valhalla_http):
    """GET /route where start == end → 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": START, "mode": "pedestrian"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_route_valhalla_empty_returns_404(patched_valhalla_http):
    """Valhalla returns error/no-path → 404 detail mentions 'no route' or 'not found'."""
    patched_valhalla_http.post = AsyncMock(
        return_value=_mock_valhalla_response(VALHALLA_NO_ROUTE, status_code=400)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 404
    body = response.json()
    detail = body.get("detail", "").lower()
    assert "no route" in detail or "not found" in detail or "route" in detail, (
        f"Expected 'no route' or 'not found' in detail, got {detail!r}"
    )


@pytest.mark.asyncio
async def test_route_upstream_timeout_returns_502(patched_valhalla_http):
    """httpx.TimeoutException raised by upstream Valhalla → 502 Bad Gateway."""
    patched_valhalla_http.post = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/route",
            params={"start": START, "end": END, "mode": "pedestrian"},
        )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_route_valhalla_disabled_returns_503():
    """When app.state.valhalla_enabled is False → 503 detail mentions 'valhalla' or 'disabled'."""
    original_enabled = getattr(app.state, "valhalla_enabled", None)
    app.state.valhalla_enabled = False

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/route",
                params={"start": START, "end": END, "mode": "pedestrian"},
            )

        assert response.status_code == 503
        body = response.json()
        detail = body.get("detail", "").lower()
        assert "valhalla" in detail or "disabled" in detail or "unavailable" in detail, (
            f"Expected 'valhalla', 'disabled', or 'unavailable' in detail, got {detail!r}"
        )
    finally:
        if original_enabled is not None:
            app.state.valhalla_enabled = original_enabled
        else:
            try:
                del app.state.valhalla_enabled
            except AttributeError:
                pass
