"""FastAPI contract tests for GET /poi/search endpoint (Plan 26-03+).

These tests describe the full POI search endpoint contract and are written in
the RED phase. They FAIL until Plans 03-05 implement the route and schemas.

Contract:
- GET /poi/search?q={str}&lat={float}&lon={float}&radius={int}  (radius default 1000m)
  OR GET /poi/search?q={str}&bbox={west,south,east,north}
- Mutually exclusive: 400 if both lat/lon and bbox provided
- 400 if neither lat/lon nor bbox provided
- Returns: {results: [{name, lat, lon, type, address}, ...]}
- 200 with results=[] when no POIs found
- 503 when "nominatim" key absent from app.state.providers
- 422 when required q param missing

Nominatim upstream behavior:
- /search with q, format=json, limit=50, viewbox=west,south,east,north, bounded=1
- For radius search: lat/lon is converted to a viewbox bbox degree approximation

Uses AsyncClient + ASGITransport pattern (same as test_api_tiles.py).
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from civpulse_geo.main import app


def _mock_nominatim_search_response(
    json_data: list, status_code: int = 200
) -> MagicMock:
    """Build a minimal mock httpx.Response for Nominatim search tests."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


POI_RESULTS_3 = [
    {
        "place_id": 1,
        "display_name": "Starbucks, 100 Peachtree St, Atlanta, GA 30303",
        "lat": "33.750",
        "lon": "-84.390",
        "type": "cafe",
        "class": "amenity",
    },
    {
        "place_id": 2,
        "display_name": "Starbucks, 200 Peachtree St, Atlanta, GA 30308",
        "lat": "33.755",
        "lon": "-84.385",
        "type": "cafe",
        "class": "amenity",
    },
    {
        "place_id": 3,
        "display_name": "Starbucks, 300 West Peachtree St, Atlanta, GA 30313",
        "lat": "33.760",
        "lon": "-84.392",
        "type": "cafe",
        "class": "amenity",
    },
]

POI_RESULTS_EMPTY: list = []


@pytest.fixture
def patched_nominatim_http():
    """Override app.state.http_client and ensure nominatim is in app.state.providers."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    original_client = getattr(app.state, "http_client", None)
    original_providers = getattr(app.state, "providers", None)

    app.state.http_client = mock_client
    if not hasattr(app.state, "providers") or app.state.providers is None:
        app.state.providers = {}
    app.state.providers["nominatim"] = MagicMock()

    yield mock_client

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
async def test_poi_lat_lon_radius(patched_nominatim_http):
    """GET /poi/search?q=coffee&lat=33.749&lon=-84.388&radius=1000 → 200, 3 results."""
    patched_nominatim_http.get = AsyncMock(
        return_value=_mock_nominatim_search_response(POI_RESULTS_3)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/poi/search",
            params={"q": "coffee", "lat": 33.749, "lon": -84.388, "radius": 1000},
        )

    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert len(body["results"]) == 3
    for item in body["results"]:
        assert "name" in item
        assert "lat" in item
        assert "lon" in item
        assert "type" in item
        assert "address" in item

    # Verify upstream was called with /search and viewbox param (radius → bbox conversion)
    assert patched_nominatim_http.get.called
    call_args = patched_nominatim_http.get.call_args
    called_url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
    assert "/search" in called_url, (
        f"Expected '/search' in upstream URL, got {called_url!r}"
    )
    # Radius is converted to viewbox — verify viewbox param is present
    call_kwargs = call_args[1] if call_args[1] else {}
    called_params = call_kwargs.get("params", {})
    assert "viewbox" in called_params, (
        f"Expected 'viewbox' in upstream params for radius search, got {called_params}"
    )


@pytest.mark.asyncio
async def test_poi_bbox(patched_nominatim_http):
    """GET /poi/search?q=park&bbox=-84.5,33.6,-84.3,33.8 → 200, upstream called with viewbox+bounded=1."""
    patched_nominatim_http.get = AsyncMock(
        return_value=_mock_nominatim_search_response(POI_RESULTS_3)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/poi/search",
            params={"q": "park", "bbox": "-84.5,33.6,-84.3,33.8"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "results" in body

    # Verify upstream called with viewbox and bounded=1
    assert patched_nominatim_http.get.called
    call_args = patched_nominatim_http.get.call_args
    call_kwargs = call_args[1] if call_args[1] else {}
    called_params = call_kwargs.get("params", {})
    assert "viewbox" in called_params, (
        f"Expected 'viewbox' in upstream params for bbox search, got {called_params}"
    )
    assert str(called_params.get("bounded", "")) == "1", (
        f"Expected bounded=1 in upstream params, got {called_params}"
    )


@pytest.mark.asyncio
async def test_poi_both_bbox_and_latlon_returns_400():
    """GET /poi/search?q=x&lat=1&lon=2&bbox=1,2,3,4 → 400 detail mentions 'mutually exclusive'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/poi/search",
            params={"q": "x", "lat": 1, "lon": 2, "bbox": "1,2,3,4"},
        )

    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail", "")
    assert "mutually exclusive" in detail.lower() or "exclusive" in detail.lower(), (
        f"Expected 'mutually exclusive' in detail, got {detail!r}"
    )


@pytest.mark.asyncio
async def test_poi_neither_bbox_nor_latlon_returns_400():
    """GET /poi/search?q=x (no lat/lon or bbox) → 400 detail mentions 'lat/lon or bbox required'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/poi/search", params={"q": "x"})

    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail", "")
    assert "lat" in detail.lower() or "bbox" in detail.lower() or "required" in detail.lower(), (
        f"Expected lat/lon or bbox mention in detail, got {detail!r}"
    )


@pytest.mark.asyncio
async def test_poi_no_results_empty_list(patched_nominatim_http):
    """Upstream returns [] → 200 with results=[]."""
    patched_nominatim_http.get = AsyncMock(
        return_value=_mock_nominatim_search_response(POI_RESULTS_EMPTY)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/poi/search",
            params={"q": "unicorn coffee", "lat": 33.749, "lon": -84.388, "radius": 500},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []


@pytest.mark.asyncio
async def test_poi_bbox_malformed_422():
    """GET /poi/search?q=x&bbox=not,a,valid,bbox → 422 or 400 (validation failure)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/poi/search",
            params={"q": "x", "bbox": "not,a,valid,bbox"},
        )

    # Either FastAPI 422 validation or custom 400 is acceptable
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_poi_service_unavailable_503():
    """When 'nominatim' is absent from app.state.providers → 503."""
    original_providers = getattr(app.state, "providers", None)

    if not hasattr(app.state, "providers") or app.state.providers is None:
        app.state.providers = {}
    app.state.providers.pop("nominatim", None)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/poi/search",
                params={"q": "coffee", "lat": 33.749, "lon": -84.388, "radius": 1000},
            )

        assert response.status_code == 503
    finally:
        if original_providers is not None:
            app.state.providers = original_providers
        else:
            try:
                del app.state.providers
            except AttributeError:
                pass


@pytest.mark.asyncio
async def test_poi_missing_q_422():
    """GET /poi/search (no q param) → 422 (required query param missing)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/poi/search",
            params={"lat": 33.749, "lon": -84.388, "radius": 1000},
        )

    assert response.status_code == 422
