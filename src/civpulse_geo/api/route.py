"""FastAPI router for route endpoint (ROUTE-01, ROUTE-02, ROUTE-03)."""
import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger

from civpulse_geo.config import settings
from civpulse_geo.schemas.route import Maneuver, RouteResponse

router = APIRouter(prefix="/route", tags=["routing"])

_VALID_MODES = {"pedestrian", "auto"}
_UPSTREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
_KM_TO_M = 1000.0


def _parse_coord(value: str, field_name: str) -> tuple[float, float]:
    """Parse 'lat,lon' string into (lat, lon) floats; raise HTTPException 400 on failure."""
    parts = value.split(",")
    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail=f"invalid {field_name} format: expected 'lat,lon'",
        )
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"invalid {field_name} format: non-numeric",
        )
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise HTTPException(
            status_code=400,
            detail=f"invalid {field_name}: coordinates out of range",
        )
    return lat, lon


@router.get("", response_model=RouteResponse)
async def get_route(
    request: Request,
    start: str = Query(..., description="Start coordinate as 'lat,lon'"),
    end: str = Query(..., description="End coordinate as 'lat,lon'"),
    mode: str = Query(..., description="Routing mode: 'pedestrian' or 'auto'"),
) -> RouteResponse:
    """Proxy routing request to Valhalla and return structured route response."""
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of {sorted(_VALID_MODES)}",
        )

    start_lat, start_lon = _parse_coord(start, "start")
    end_lat, end_lon = _parse_coord(end, "end")

    if (start_lat, start_lon) == (end_lat, end_lon):
        raise HTTPException(status_code=400, detail="start and end must differ")

    if not getattr(request.app.state, "valhalla_enabled", False):
        raise HTTPException(
            status_code=503, detail="Valhalla routing service disabled or unreachable"
        )

    upstream_url = f"{settings.osm_valhalla_url.rstrip('/')}/route"
    body = {
        "locations": [
            {"lat": start_lat, "lon": start_lon},
            {"lat": end_lat, "lon": end_lon},
        ],
        "costing": mode,
        "units": "kilometers",
    }

    client: httpx.AsyncClient = request.app.state.http_client
    try:
        upstream = await client.post(upstream_url, json=body, timeout=_UPSTREAM_TIMEOUT)
    except httpx.TimeoutException:
        logger.warning("route proxy timeout start={} end={} mode={}", start, end, mode)
        raise HTTPException(status_code=502, detail="Upstream Valhalla timeout")
    except httpx.ConnectError:
        logger.warning(
            "route proxy connect error start={} end={} mode={}", start, end, mode
        )
        raise HTTPException(status_code=502, detail="Upstream Valhalla unreachable")
    except httpx.HTTPError as exc:
        logger.warning(
            "route proxy transport error start={} end={} error={}", start, end, exc
        )
        raise HTTPException(status_code=502, detail="Upstream Valhalla error")

    # Valhalla returns 400 with {"error": ...} when no path can be found
    if upstream.status_code == 400:
        raise HTTPException(status_code=404, detail="no route found between points")
    if upstream.status_code >= 500:
        logger.warning(
            "route proxy upstream 5xx start={} end={} status={}",
            start,
            end,
            upstream.status_code,
        )
        raise HTTPException(status_code=502, detail="Upstream Valhalla failure")
    if upstream.status_code >= 400:
        logger.warning(
            "route proxy upstream 4xx start={} end={} status={}",
            start,
            end,
            upstream.status_code,
        )
        raise HTTPException(status_code=502, detail="Upstream Valhalla failure")

    data = upstream.json()
    trip = data.get("trip") or {}
    legs = trip.get("legs") or []
    if not legs:
        raise HTTPException(status_code=404, detail="no route found between points")

    leg = legs[0]
    polyline = leg.get("shape", "")
    summary = trip.get("summary") or leg.get("summary") or {}
    duration_s = float(summary.get("time", 0.0))
    distance_m = float(summary.get("length", 0.0)) * _KM_TO_M

    maneuvers_raw = leg.get("maneuvers") or []
    maneuvers = [
        Maneuver(
            instruction=str(m.get("instruction", "")),
            distance_meters=float(m.get("length", 0.0)) * _KM_TO_M,
            duration_seconds=float(m.get("time", 0.0)),
            type=int(m.get("type", 0)),
        )
        for m in maneuvers_raw
    ]

    return RouteResponse(
        mode=mode,
        polyline=polyline,
        duration_seconds=duration_s,
        distance_meters=distance_m,
        maneuvers=maneuvers,
        raw_valhalla=data,
    )
