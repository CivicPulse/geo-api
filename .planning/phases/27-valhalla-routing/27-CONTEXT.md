# Phase 27: Valhalla Routing - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning
**Mode:** Smart discuss (batch-accepted recommended defaults)

<domain>
## Phase Boundary

Callers can request walking and driving turn-by-turn routes between two Georgia points via `GET /route`. geo-api proxies to the upstream Valhalla sidecar (see Phase 24) and returns structured route data including maneuvers, encoded polyline, duration, and distance. This phase delivers the FastAPI `/route` endpoint, the Valhalla HTTP client, conditional startup guard, and response schema. It does NOT implement multi-stop routing, bicycle/transit modes, time-of-day costing, alternative routes, or route matrix requests (all deferred).

</domain>

<decisions>
## Implementation Decisions

### Route Contract
- Route path: `GET /route?start={lat},{lon}&end={lat},{lon}&mode={pedestrian|auto}` — matches ROADMAP success criteria
- Router: new `APIRouter(prefix="/route", tags=["routing"])` in `src/civpulse_geo/api/route.py`, but since ROADMAP says `GET /route?...` (no path suffix), use bare route or empty path — define as `@router.get("")` with `prefix="/route"` so full path is `/route`
- Query param parsing: `start` and `end` are `{lat},{lon}` strings, parsed to tuple[float, float]; invalid format → 400
- Mode validation: `mode` must be `pedestrian` or `auto`; invalid → 400

### Upstream Valhalla Call
- Valhalla exposes `POST /route` with JSON body: `{"locations": [{"lat": ..., "lon": ...}, {"lat": ..., "lon": ...}], "costing": "pedestrian|auto", "units": "kilometers"}`
- Translate GET query params → POST JSON body → call `{settings.osm_valhalla_url}/route`
- Uses existing `app.state.http_client` (httpx.AsyncClient); timeout connect=5s, read=15s (routing can be slow)

### Response Schema
New Pydantic models in `src/civpulse_geo/schemas/route.py`:
```python
class Maneuver(BaseModel):
    instruction: str              # "Turn right onto Peachtree St"
    distance_meters: float
    duration_seconds: float
    type: int                     # Valhalla maneuver type code

class RouteResponse(BaseModel):
    mode: str                     # "pedestrian" | "auto"
    polyline: str                 # Valhalla encoded polyline (precision=6)
    duration_seconds: float       # total
    distance_meters: float        # total
    maneuvers: list[Maneuver]
    raw_valhalla: dict            # full upstream response for debugging
```

### Error Handling & Observability
- 400: invalid start/end format, invalid mode, same start == end
- 404: Valhalla returns empty/no-route (e.g., points outside tile coverage)
- 503: Valhalla provider not registered at startup (unreachable at boot)
- 502: Upstream connect/timeout/5xx during request
- Log format: `logger.warning("route proxy failure", extra={"start": start, "end": end, "mode": mode, "upstream_status": status})`

### Conditional Startup Guard
- `_valhalla_reachable()` async probe: `GET {osm_valhalla_url}/status`, 2s timeout at app startup
- Register into `app.state.valhalla_enabled = True/False` flag (not provider dict — valhalla isn't a GeocodingProvider)
- Toggle: `settings.valhalla_enabled: bool = True` — mirrors `nominatim_enabled`
- Route handler checks `app.state.valhalla_enabled`; if False → 503

### Claude's Discretion
- Whether to expose the `raw_valhalla` passthrough field long-term (include for now as debug aid)
- Distance unit handling (Valhalla returns km — we convert to meters in response)
- Exact maneuver type code mapping (pass through int values — consumer-side enum mapping deferred)
- Caching of route responses — not this phase

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app.state.http_client` — httpx.AsyncClient singleton (main.py:77)
- `settings.osm_valhalla_url` — added in Phase 24 (config.py)
- Conditional startup guard pattern — `_nominatim_reachable()` from Phase 26 (providers/nominatim.py)
- `_valhalla_enabled` flag pattern — mirrors `settings.nominatim_enabled`
- APIRouter mount pattern — see `api/tiles.py` (Phase 25) and `api/poi.py` (Phase 26)

### Established Patterns
- New routers in `src/civpulse_geo/api/<domain>.py`
- Pydantic response models in `src/civpulse_geo/schemas/<domain>.py`
- FastAPI TestClient tests in `tests/test_api_<domain>.py` using `unittest.mock.patch` + `AsyncMock`
- Error responses via `HTTPException` with explicit status codes
- Logger: `from loguru import logger` (matches tiles.py, poi.py)

### Integration Points
- New: `src/civpulse_geo/api/route.py` (route router)
- New: `src/civpulse_geo/schemas/route.py` (RouteResponse + Maneuver)
- New: `tests/test_api_route.py` (8-10 contract tests)
- Modify: `src/civpulse_geo/config.py` — add `valhalla_enabled: bool = True`
- Modify: `src/civpulse_geo/main.py` — add `_valhalla_reachable()` probe, set `app.state.valhalla_enabled`, mount `route.router`

</code_context>

<specifics>
## Specific Ideas

- Start/end format: `"33.7490,-84.3880"` (lat,lon with comma separator, no space) — standard Valhalla convention
- Mode values lowercase exactly: `pedestrian`, `auto` — reject `walking`, `driving`, `car` with 400
- Response `polyline` is Valhalla's native polyline6 (precision=6); consumers must decode with polyline6 library
- Georgia coverage assumption: routes between two Georgia points work; routes crossing state lines may return 404 from Valhalla (depends on PBF coverage)

</specifics>

<deferred>
## Deferred Ideas

- Multi-stop routing (3+ locations)
- Bicycle, transit, bus costing models
- Time-of-day costing (traffic-aware routing)
- Alternative routes (multiple path options)
- Route matrix / one-to-many requests
- Isochrones
- Route caching

</deferred>
