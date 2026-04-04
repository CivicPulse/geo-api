"""FastAPI TestClient tests for tile proxy endpoint (TILE-02, TILE-03).

Tests describe the full contract:
- Streaming PNG response with Cache-Control header
- ETag forward from upstream
- CORS header on all responses
- 404 passthrough for upstream 404
- 502 on upstream 5xx / ConnectError / TimeoutException
- Upstream URL correctness (targets {osm_tile_url}/tile/{z}/{x}/{y}.png)

These tests FAIL until Plan 02 implements the streaming proxy.
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from civpulse_geo.main import app
from civpulse_geo.config import settings

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal fake PNG


def _mock_response(status_code=200, content=PNG_BYTES, headers=None):
    """Build a minimal mock httpx.Response for tile proxy tests."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {}
    return resp


@pytest.fixture
def patched_tile_http_client():
    """Override app.state.http_client with an AsyncMock for tile tests."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    original = getattr(app.state, "http_client", None)
    app.state.http_client = mock_client
    yield mock_client
    if original is not None:
        app.state.http_client = original
    else:
        try:
            del app.state.http_client
        except AttributeError:
            pass


@pytest.mark.asyncio
async def test_tile_proxy_success(patched_tile_http_client):
    """GET /tiles/10/277/408.png returns 200 with PNG bytes, correct Content-Type, Cache-Control."""
    patched_tile_http_client.get = AsyncMock(
        return_value=_mock_response(
            status_code=200,
            content=PNG_BYTES,
            headers={"content-type": "image/png"},
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers.get("content-type", "").startswith("image/png")
    cache_control = response.headers.get("cache-control", "")
    assert "public" in cache_control
    assert "max-age=86400" in cache_control
    assert "immutable" in cache_control


@pytest.mark.asyncio
async def test_tile_proxy_forwards_etag(patched_tile_http_client):
    """When upstream returns ETag header, response includes ETag."""
    patched_tile_http_client.get = AsyncMock(
        return_value=_mock_response(
            status_code=200,
            content=PNG_BYTES,
            headers={"content-type": "image/png", "etag": "abc123"},
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 200
    assert response.headers.get("etag") == "abc123"


@pytest.mark.asyncio
async def test_tile_proxy_cors_header(patched_tile_http_client):
    """Response includes Access-Control-Allow-Origin: * on all tile responses."""
    patched_tile_http_client.get = AsyncMock(
        return_value=_mock_response(
            status_code=200,
            content=PNG_BYTES,
            headers={"content-type": "image/png"},
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


@pytest.mark.asyncio
async def test_tile_proxy_upstream_404(patched_tile_http_client):
    """Upstream returns 404 → response status 404 (tile outside coverage)."""
    patched_tile_http_client.get = AsyncMock(
        return_value=_mock_response(status_code=404, content=b"not found")
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tile_proxy_upstream_500(patched_tile_http_client):
    """Upstream returns 500 → response status 502 Bad Gateway."""
    patched_tile_http_client.get = AsyncMock(
        return_value=_mock_response(status_code=500, content=b"internal server error")
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_tile_proxy_upstream_connect_error(patched_tile_http_client):
    """httpx.ConnectError raised by upstream → response status 502 Bad Gateway."""
    patched_tile_http_client.get = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_tile_proxy_upstream_timeout(patched_tile_http_client):
    """httpx.TimeoutException raised by upstream → response status 502 Bad Gateway."""
    patched_tile_http_client.get = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tiles/10/277/408.png")

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_tile_proxy_calls_correct_upstream_url(patched_tile_http_client):
    """Verify tile proxy targets {osm_tile_url}/tile/{z}/{x}/{y}.png."""
    patched_tile_http_client.get = AsyncMock(
        return_value=_mock_response(
            status_code=200,
            content=PNG_BYTES,
            headers={"content-type": "image/png"},
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/tiles/10/277/408.png")

    assert patched_tile_http_client.get.called
    call_args = patched_tile_http_client.get.call_args
    # First positional arg is the URL
    called_url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
    assert called_url.startswith(settings.osm_tile_url), (
        f"Expected URL to start with {settings.osm_tile_url!r}, got {called_url!r}"
    )
    assert "/tile/10/277/408.png" in called_url, (
        f"Expected '/tile/10/277/408.png' in URL, got {called_url!r}"
    )
