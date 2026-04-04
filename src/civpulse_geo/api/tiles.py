"""FastAPI router for tile proxy endpoint (TILE-02, TILE-03).

Proxies raster PNG map tiles from the upstream tile-server sidecar.
Streaming implementation wired in Plan 02.
"""
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/tiles", tags=["tiles"])


@router.get("/{z}/{x}/{y}.png")
async def get_tile(z: int, x: int, y: int, request: Request):
    """Proxy a raster PNG tile from the upstream tile-server sidecar.

    Returns:
    - 200 + image/png body with Cache-Control: public, max-age=86400, immutable
    - 404 when upstream tile-server returns 404 (tile outside coverage)
    - 502 when upstream is unreachable / returns 5xx / times out
    """
    # Plan 02: implement streaming proxy via request.app.state.http_client
    raise HTTPException(status_code=501, detail="Not implemented — Plan 02")
