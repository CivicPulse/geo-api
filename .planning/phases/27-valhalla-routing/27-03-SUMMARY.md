---
phase: 27-valhalla-routing
plan: "03"
subsystem: api
tags: [valhalla, routing, fastapi, httpx, config, lifespan]

# Dependency graph
requires:
  - phase: 27-02
    provides: route.router (APIRouter with GET /route endpoint + RouteResponse schema)
  - phase: 26-nominatim-geocoding
    provides: _nominatim_reachable pattern used as reference for _valhalla_reachable
provides:
  - settings.valhalla_enabled toggle (config.py)
  - providers/valhalla.py with _valhalla_reachable async HTTP probe
  - main.py lifespan sets app.state.valhalla_enabled via probe result
  - GET /route mounted in app (app.include_router(route.router))
affects: [future routing phases, observability, e2e tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_valhalla_reachable: mirrors _nominatim_reachable pattern exactly (GET /status, 2s timeout, bool return)"
    - "app.state.valhalla_enabled: non-provider flag pattern (valhalla is not a GeocodingProvider)"

key-files:
  created:
    - src/civpulse_geo/providers/valhalla.py
  modified:
    - src/civpulse_geo/config.py
    - src/civpulse_geo/main.py

key-decisions:
  - "Valhalla is not a GeocodingProvider — uses app.state.valhalla_enabled flag not providers dict"
  - "Pre-existing e2e test_cascade_pipeline.py failure confirmed out of scope (requires live DB)"

patterns-established:
  - "Routing sidecar probe: providers/valhalla.py::_valhalla_reachable mirrors nominatim pattern"
  - "Conditional startup guard: if settings.X_enabled: probe then set app.state.X_enabled"

requirements-completed: [ROUTE-01, ROUTE-02, ROUTE-03]

# Metrics
duration: 2min
completed: 2026-04-04
---

# Phase 27 Plan 03: Valhalla Routing Wiring Summary

**valhalla_enabled config toggle + async /status probe + lifespan guard wired into main.py, GET /route mounted, all 11 contract tests green**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-04T22:21:30Z
- **Completed:** 2026-04-04T22:22:46Z
- **Tasks:** 2
- **Files modified:** 3 (config.py, main.py, created providers/valhalla.py)

## Accomplishments

- Added `valhalla_enabled: bool = True` to Settings in config.py
- Created `providers/valhalla.py` with `_valhalla_reachable()` async HTTP probe (mirrors `_nominatim_reachable` exactly)
- Wired lifespan startup block: probe `{osm_valhalla_url}/status` → set `app.state.valhalla_enabled`; logs enabled/disabled/unreachable branches
- Mounted `route.router` in main.py — `GET /route` is now a registered path
- All 11 tests in `tests/test_api_route.py` pass GREEN
- Full unit/integration suite (629 tests) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add valhalla_enabled setting + _valhalla_reachable probe** - `9fe5c3d` (feat)
2. **Task 2: Wire valhalla probe + mount route router in main.py** - `24dbc0c` (feat)

## Files Created/Modified

- `src/civpulse_geo/config.py` - Added `valhalla_enabled: bool = True` after `nominatim_enabled`
- `src/civpulse_geo/providers/valhalla.py` - New file: `_valhalla_reachable()` async HTTP probe
- `src/civpulse_geo/main.py` - Added import, lifespan block, and `app.include_router(route.router)`

## Decisions Made

- Valhalla is not a GeocodingProvider — stored as `app.state.valhalla_enabled` flag (bool), not in `app.state.providers` dict. This matches the CONTEXT.md design decision.
- Pre-existing `tests/e2e/test_cascade_pipeline.py` failure confirmed out of scope — fails identically before and after these changes (requires live database connection).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All three edits applied cleanly. 11/11 route tests green on first run.

## Startup Log Branches (observable behavior)

Three branches exist in the lifespan block:

- **Valhalla reachable:** `"Valhalla routing enabled at {url}"`
- **Valhalla unreachable (toggle on, probe fails):** `"valhalla unreachable at {url} — routing disabled"`
- **Toggle off:** `"Valhalla routing disabled via settings.valhalla_enabled=False"`

## User Setup Required

None - no external service configuration required. `settings.valhalla_enabled` defaults to True; `osm_valhalla_url` defaults to `http://valhalla:8002` (set in Phase 24).

## Next Phase Readiness

- Phase 27 (Valhalla routing) fully complete: schema (27-01), router (27-02), wiring (27-03)
- GET /route is live and tested end-to-end with mocked Valhalla
- Ready for Phase 28 or any phase that consumes routing

---
*Phase: 27-valhalla-routing*
*Completed: 2026-04-04*
