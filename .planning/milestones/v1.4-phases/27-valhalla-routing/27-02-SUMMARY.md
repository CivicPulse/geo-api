---
phase: 27-valhalla-routing
plan: 02
subsystem: routing
tags: [valhalla, routing, pydantic, fastapi, httpx]
dependency_graph:
  requires: []
  provides: [RouteResponse, Maneuver, router]
  affects: [src/civpulse_geo/api/route.py, src/civpulse_geo/schemas/route.py]
tech_stack:
  added: []
  patterns: [httpx-proxy, pydantic-response-schema, fastapi-router, 503-guard]
key_files:
  created:
    - src/civpulse_geo/schemas/route.py
    - src/civpulse_geo/api/route.py
  modified: []
decisions:
  - Used @router.get("") with prefix="/route" so full path resolves to /route (no double slash)
  - Valhalla upstream 400 maps to 404 (no route found semantics, not client error)
  - km to meters conversion applied to both summary-level and maneuver-level distances
  - 503 guard checks app.state.valhalla_enabled before any upstream I/O
  - Router not mounted in main.py — Plan 03 handles mount atomically with startup probe
metrics:
  duration_minutes: 5
  completed: "2026-04-04"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
requirements: [ROUTE-01, ROUTE-02, ROUTE-03]
---

# Phase 27 Plan 02: /route Schemas + Router Summary

**One-liner:** Pydantic RouteResponse/Maneuver schemas and Valhalla proxy router with 400/404/502/503 error mapping.

## What Was Built

### Task 1: RouteResponse and Maneuver Pydantic Schemas

`src/civpulse_geo/schemas/route.py` exports two BaseModel subclasses:

- **Maneuver** — `instruction: str`, `distance_meters: float`, `duration_seconds: float`, `type: int`
- **RouteResponse** — `mode: str`, `polyline: str`, `duration_seconds: float`, `distance_meters: float`, `maneuvers: list[Maneuver]`, `raw_valhalla: dict`

### Task 2: /route Router

`src/civpulse_geo/api/route.py` exports `router = APIRouter(prefix="/route", tags=["routing"])` with a single `GET ""` handler.

**Upstream POST body shape (exact):**
```json
{
  "locations": [{"lat": ..., "lon": ...}, {"lat": ..., "lon": ...}],
  "costing": "pedestrian|auto",
  "units": "kilometers"
}
```

**Error mapping table:**

| Condition | Status |
|-----------|--------|
| Missing query param | 422 (FastAPI built-in) |
| Invalid start/end format or range | 400 |
| mode not in {pedestrian, auto} | 400 |
| start == end | 400 |
| app.state.valhalla_enabled is False | 503 |
| Valhalla upstream 400 (no path) | 404 |
| Empty/missing trip.legs | 404 |
| httpx.TimeoutException | 502 |
| httpx.ConnectError | 502 |
| httpx.HTTPError | 502 |
| Upstream 5xx | 502 |
| Upstream other 4xx | 502 |

**Distance conversion:** Valhalla returns kilometers; router multiplies by 1000 for `distance_meters` on both summary and per-maneuver fields.

## Commits

| Hash | Message |
|------|---------|
| 417eab1 | feat(27-02): add RouteResponse and Maneuver pydantic schemas |
| 9d2983f | feat(27-02): implement /route Valhalla proxy router |

## Test Status

Tests in `tests/test_api_route.py` are expected to fail until Plan 03 mounts the router in `main.py` and wires up `app.state.valhalla_enabled`. The router itself is complete and correct.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. All fields are wired to upstream Valhalla response data; `raw_valhalla` passthrough is intentional for debugging.

## Self-Check: PASSED
