"""FastAPI router for POI search endpoint (GEO-03, GEO-04, GEO-05).

Provides GET /poi/search backed by Nominatim /search with viewbox/bounded bbox
constraint. Accepts either a center-point + radius (meters) or an explicit bbox
(west,south,east,north) — mutually exclusive.
"""
from fastapi import APIRouter, HTTPException, Query, Request

from civpulse_geo.config import settings
from civpulse_geo.schemas.poi import POIResult, POISearchResponse

router = APIRouter(prefix="/poi", tags=["poi"])

# Degree-to-meter approximation constants for GA (~33°N latitude)
_METERS_PER_DEG_LAT = 111_000.0
_METERS_PER_DEG_LON_GA = 93_000.0

MAX_POI_LIMIT = 50


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse 'west,south,east,north' string into four floats.

    Raises:
        HTTPException(400): If the string doesn't have exactly 4 comma-separated
            numeric values or if coordinates are out of valid WGS-84 range.
    """
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=400, detail="bbox must be 'west,south,east,north'"
        )
    try:
        w, s, e, n = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be floats")
    if not (
        -180.0 <= w <= 180.0
        and -180.0 <= e <= 180.0
        and -90.0 <= s <= 90.0
        and -90.0 <= n <= 90.0
    ):
        raise HTTPException(
            status_code=400, detail="bbox coordinates out of range"
        )
    return w, s, e, n


def _viewbox_from_point(
    lat: float, lon: float, radius_m: int
) -> tuple[float, float, float, float]:
    """Convert a center point + radius (meters) to a viewbox tuple.

    Returns:
        (west, south, east, north) as floats.
    """
    dlat = radius_m / _METERS_PER_DEG_LAT
    dlon = radius_m / _METERS_PER_DEG_LON_GA
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


@router.get("/search", response_model=POISearchResponse)
async def poi_search(
    request: Request,
    q: str = Query(..., min_length=1, description="POI search term"),
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="Center latitude"),
    lon: float | None = Query(
        None, ge=-180.0, le=180.0, description="Center longitude"
    ),
    radius: int = Query(
        1000, ge=100, le=50000, description="Search radius in meters (default 1000)"
    ),
    bbox: str | None = Query(
        None, description="Bounding box as 'west,south,east,north'"
    ),
) -> POISearchResponse:
    """POI search via Nominatim (GEO-03, GEO-04).

    Exactly one of (lat+lon) or bbox must be supplied; both or neither → 400.
    Returns up to 50 results ordered by Nominatim relevance.
    """
    has_point = lat is not None and lon is not None
    has_partial_point = (lat is None) != (lon is None)
    has_bbox = bbox is not None

    if has_point and has_bbox:
        raise HTTPException(
            status_code=400,
            detail="lat/lon and bbox are mutually exclusive",
        )
    if not has_point and not has_bbox:
        if has_partial_point:
            raise HTTPException(
                status_code=400,
                detail="lat and lon must be provided together",
            )
        raise HTTPException(
            status_code=400,
            detail="lat/lon or bbox required",
        )
    if has_partial_point:
        raise HTTPException(
            status_code=400,
            detail="lat and lon must be provided together",
        )

    # Parse/validate bbox before provider check so malformed bbox returns 400 promptly.
    if has_bbox:
        w, s, e, n = _parse_bbox(bbox)  # type: ignore[arg-type]
    else:
        w, s, e, n = _viewbox_from_point(lat, lon, radius)  # type: ignore[arg-type]

    providers = getattr(request.app.state, "providers", {})
    if "nominatim" not in providers:
        raise HTTPException(
            status_code=503,
            detail="Nominatim provider not registered",
        )

    url = f"{settings.osm_nominatim_url.rstrip('/')}/search"
    params = {
        "q": q,
        "format": "json",
        "limit": MAX_POI_LIMIT,
        "viewbox": f"{w},{s},{e},{n}",
        "bounded": 1,
    }
    response = await request.app.state.http_client.get(url, params=params)
    upstream = response.json()
    if not isinstance(upstream, list):
        upstream = []

    results = [
        POIResult(
            name=(item.get("display_name") or "").split(",", 1)[0].strip() or "unknown",
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            type=item.get("type"),
            address=item.get("display_name"),
            place_id=item.get("place_id"),
        )
        for item in upstream
    ]
    return POISearchResponse(results=results, count=len(results))
