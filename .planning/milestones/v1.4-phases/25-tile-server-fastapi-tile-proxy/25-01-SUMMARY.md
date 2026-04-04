---
phase: 25-tile-server-fastapi-tile-proxy
plan: 01
subsystem: api
tags: [fastapi, httpx, tiles, png, tdd, tile-proxy]

# Dependency graph
requires:
  - phase: 24-osm-data-pipeline-docker-compose-sidecars
    provides: tile-server sidecar Docker Compose service, settings.osm_tile_url config
provides:
  - GET /tiles/{z}/{x}/{y}.png route skeleton registered on FastAPI app (returns 501)
  - 8 failing TDD tests covering full tile proxy contract
  - tiles APIRouter with prefix=/tiles, tags=[tiles]
affects:
  - 25-02 (Plan 02 implements streaming proxy to make these tests green)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tiles router follows same APIRouter(prefix=..., tags=[...]) pattern as geocoding.py"
    - "TDD test file uses AsyncClient + ASGITransport per project test pattern (not sync TestClient)"
    - "app.state.http_client overridden directly on app.state for tile test isolation (no dependency injection needed)"

key-files:
  created:
    - src/civpulse_geo/api/tiles.py
    - tests/test_api_tiles.py
  modified:
    - src/civpulse_geo/main.py

key-decisions:
  - "Used AsyncClient + ASGITransport (not sync TestClient) — matches existing project test pattern in conftest.py"
  - "Tile tests override app.state.http_client directly (not via fixture injection) — consistent with geocoding test pattern"
  - "Router skeleton raises HTTPException(501) — route is wired and reachable, implementation deferred to Plan 02"

patterns-established:
  - "TDD RED-only plan: tests created first, skeleton returns 501, Plan 02 turns them green"
  - "Tile router prefix convention: /tiles with /{z}/{x}/{y}.png path segment"

requirements-completed:
  - TILE-02

# Metrics
duration: 2min
completed: 2026-04-04
---

# Phase 25 Plan 01: Tile Proxy TDD Scaffold Summary

**FastAPI /tiles/{z}/{x}/{y}.png route skeleton registered with 8 failing TDD tests covering full tile proxy contract (streaming PNG, Cache-Control, ETag, CORS, 404/502 error handling, upstream URL correctness)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-04T18:35:19Z
- **Completed:** 2026-04-04T18:37:17Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created `tests/test_api_tiles.py` with 8 TDD tests covering all CONTEXT.md success criteria
- Created `src/civpulse_geo/api/tiles.py` with APIRouter skeleton (prefix=/tiles, returns 501)
- Mounted tiles router in main.py — `/tiles/{z}/{x}/{y}.png` is now registered and introspectable
- All 8 tests confirm RED phase: fail with 501 (route wired, not 404) ready for Plan 02

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing TDD tests for tile proxy endpoint** - `e8c9262` (test)
2. **Task 2: Create tiles router skeleton and mount in main.py** - `365b5ce` (feat)

## Files Created/Modified

- `tests/test_api_tiles.py` - 8 async TDD tests for full tile proxy contract
- `src/civpulse_geo/api/tiles.py` - Tiles APIRouter skeleton with /{z}/{x}/{y}.png route (raises 501)
- `src/civpulse_geo/main.py` - Added tiles import and app.include_router(tiles.router)

## Decisions Made

- **AsyncClient vs TestClient:** Used `AsyncClient + ASGITransport` per existing project pattern (conftest.py, test_health.py) rather than the sync `TestClient` mentioned in the plan. No functional difference for test behavior — purely conformity with project conventions.
- **app.state.http_client override:** Tile tests override `app.state.http_client` directly via a fixture (not dependency injection). This matches the geocoding test pattern and avoids lifespan startup for unit tests.
- **501 skeleton:** Router raises `HTTPException(status_code=501)` so the route is reachable and returns a structured error — tests get 501 instead of 404, confirming wiring is correct.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused imports flagged by ruff**
- **Found during:** Task 1 (test file creation)
- **Issue:** `import asyncio` and `from unittest.mock import patch` were unused after final test implementation
- **Fix:** Removed both unused imports
- **Files modified:** tests/test_api_tiles.py
- **Verification:** `uv run ruff check tests/test_api_tiles.py` passes
- **Committed in:** e8c9262 (Task 1 commit)

**2. [Rule 1 - Pattern Adaptation] Used AsyncClient instead of sync TestClient**
- **Found during:** Task 1 (test authoring)
- **Issue:** Plan specified `TestClient` (sync) but project uses `AsyncClient + ASGITransport` throughout all test files
- **Fix:** Used existing async pattern for consistency
- **Files modified:** tests/test_api_tiles.py
- **Verification:** All 8 tests collect and run; behavioral contract is identical
- **Committed in:** e8c9262 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 lint fix, 1 pattern adaptation)
**Impact on plan:** Both adjustments maintain correctness and project consistency. No scope creep.

## Issues Encountered

None — plan executed smoothly.

## Known Stubs

- `src/civpulse_geo/api/tiles.py` — `get_tile()` raises `HTTPException(501)` intentionally. This is the design: Plan 01 establishes skeleton, Plan 02 implements streaming proxy. All 8 tests will remain failing until Plan 02 wires `request.app.state.http_client`.

## Next Phase Readiness

- Plan 02 (`25-02`) has a concrete test target: all 8 tests in `tests/test_api_tiles.py` must pass green
- `request.app.state.http_client` is available (set in lifespan) — Plan 02 reads it via `request.app.state`
- `settings.osm_tile_url` config value is available (Phase 24) — upstream URL = `{osm_tile_url}/tile/{z}/{x}/{y}.png`
- No blockers for Plan 02

## Self-Check: PASSED

- FOUND: src/civpulse_geo/api/tiles.py
- FOUND: tests/test_api_tiles.py
- FOUND: .planning/phases/25-tile-server-fastapi-tile-proxy/25-01-SUMMARY.md
- FOUND: e8c9262 (test commit)
- FOUND: 365b5ce (feat commit)

---
*Phase: 25-tile-server-fastapi-tile-proxy*
*Completed: 2026-04-04*
