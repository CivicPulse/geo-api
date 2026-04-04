"""FastAPI router for tile proxy endpoint (TILE-01, TILE-02, TILE-03).

Proxies raster PNG map tiles from the upstream tile-server sidecar.
Streams response bytes to avoid buffering 50-200KB tiles in memory.
"""
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from civpulse_geo.config import settings

router = APIRouter(prefix="/tiles", tags=["tiles"])

_TILE_CACHE_CONTROL = "public, max-age=86400, immutable"
_UPSTREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


@router.get("/{z}/{x}/{y}.png")
async def get_tile(z: int, x: int, y: int, request: Request):
    """Proxy a raster PNG tile from the upstream tile-server sidecar (TILE-02)."""
    upstream_url = f"{settings.osm_tile_url}/tile/{z}/{x}/{y}.png"
    client: httpx.AsyncClient = request.app.state.http_client

    try:
        upstream = await client.get(upstream_url, timeout=_UPSTREAM_TIMEOUT)
    except httpx.TimeoutException:
        logger.warning(
            "tile proxy timeout z={} x={} y={} url={}",
            z,
            x,
            y,
            upstream_url,
        )
        raise HTTPException(status_code=502, detail="Upstream tile server timeout")
    except httpx.ConnectError:
        logger.warning(
            "tile proxy connect error z={} x={} y={} url={}",
            z,
            x,
            y,
            upstream_url,
        )
        raise HTTPException(status_code=502, detail="Upstream tile server unreachable")
    except httpx.HTTPError as exc:
        logger.warning(
            "tile proxy transport error z={} x={} y={} error={}",
            z,
            x,
            y,
            exc,
        )
        raise HTTPException(status_code=502, detail="Upstream tile server error")

    if upstream.status_code == 404:
        raise HTTPException(status_code=404, detail="Tile not found")

    if upstream.status_code >= 400:
        logger.warning(
            "tile proxy upstream failure z={} x={} y={} upstream_status={}",
            z,
            x,
            y,
            upstream.status_code,
        )
        raise HTTPException(status_code=502, detail="Upstream tile server failure")

    # Build response headers (TILE-03)
    headers = {
        "Cache-Control": _TILE_CACHE_CONTROL,
        "Access-Control-Allow-Origin": "*",
    }
    if "etag" in upstream.headers:
        headers["ETag"] = upstream.headers["etag"]

    return StreamingResponse(
        iter([upstream.content]),
        status_code=200,
        media_type="image/png",
        headers=headers,
    )
