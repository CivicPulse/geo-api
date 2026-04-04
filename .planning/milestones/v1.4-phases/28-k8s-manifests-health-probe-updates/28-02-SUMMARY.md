---
phase: 28-k8s-manifests-health-probe-updates
plan: 02
subsystem: api
tags: [fastapi, httpx, asyncio, health-probe, k8s, nominatim, valhalla, tile-server]

# Dependency graph
requires:
  - phase: 28-k8s-manifests-health-probe-updates
    provides: Phase 28-01 OSM sidecar K8s manifests (context for sidecar URLs/naming)
  - phase: 27-valhalla-routing
    provides: _valhalla_reachable probe helper pattern
  - phase: 26-nominatim
    provides: _nominatim_reachable probe helper pattern
provides:
  - _tile_server_reachable async HTTP probe for GET /tile/0/0/0.png
  - /health/ready sidecars block reporting nominatim/tile_server/valhalla readiness
  - Non-blocking sidecar readiness reporting (sidecar failures don't cause 503)
affects: [monitoring, k8s-readiness, operator-dashboards]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - asyncio.gather with return_exceptions=True for concurrent HTTP probes with per-task 1s timeout
    - Non-blocking sidecar readiness block pattern (informational, never fails readiness)
    - disabled | unavailable | ready sidecar status tri-state

key-files:
  created:
    - src/civpulse_geo/providers/tile_server.py
    - tests/test_health_ready_sidecars.py
  modified:
    - src/civpulse_geo/api/health.py

key-decisions:
  - "Tile server always probed (no enable flag) — tile_server has no settings toggle unlike nominatim/valhalla"
  - "Sidecar probe failures return unavailable not disabled — disabled is exclusively for settings flags"
  - "1s timeout per probe with asyncio.gather for concurrent execution (budget: 1s not 3s sequential)"
  - "HTTP probe for tile server uses /tile/0/0/0.png accepting both 200 and 404 as reachable"

patterns-established:
  - "_tile_server_reachable follows exact signature of _nominatim_reachable and _valhalla_reachable"
  - "TDD RED→GREEN: failing tests committed before implementation, then all 6 turned green in one pass"

requirements-completed: [INFRA-05]

# Metrics
duration: 15min
completed: 2026-04-04
---

# Phase 28 Plan 02: Health Probe Sidecar Block Summary

**Non-blocking sidecars block added to /health/ready reporting nominatim/tile_server/valhalla via concurrent asyncio.gather probes with 1s timeout budget each**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-04T22:45:00Z
- **Completed:** 2026-04-04T23:00:38Z
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- Created `_tile_server_reachable` probe helper mirroring Nominatim/Valhalla pattern exactly
- Extended `/health/ready` with `sidecars` block: `{nominatim, tile_server, valhalla}` each reporting `ready | unavailable | disabled`
- Sidecar probes run concurrently via `asyncio.gather` — total budget 1s (not 3s sequential)
- 6 new tests covering all states, disabled short-circuit, mixed states, and non-blocking 200 response

## Task Commits

Each task was committed atomically:

1. **Task 1: Create _tile_server_reachable probe helper** - `8fa40df` (feat)
2. **Task 2: Write test_health_ready_sidecars.py (6 RED tests)** - `d98758f` (test)
3. **Task 3: Extend /health/ready handler with sidecars block** - `f42a4e7` (feat)

## Files Created/Modified
- `src/civpulse_geo/providers/tile_server.py` - Async HTTP probe for GET /tile/0/0/0.png; returns True on 200 or 404
- `src/civpulse_geo/api/health.py` - Extended with `_probe_sidecars()` helper and `sidecars` key in /health/ready response
- `tests/test_health_ready_sidecars.py` - 6 tests: all ready, all unavailable, all disabled, nominatim disabled, valhalla disabled, mixed states

## Decisions Made
- Tile server always probed live — there is no `tile_server_enabled` setting flag (per plan note in interfaces). Only nominatim and valhalla have enable toggles.
- `disabled` is exclusively for settings flags; probe failures yield `unavailable`.
- Probes accept both HTTP 200 and 404 for tile server (404 = server up, tile not yet rendered).
- Used `asyncio.gather(..., return_exceptions=True)` so any single probe exception yields `unavailable` rather than raising.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Minor: unused `get_db` import in initial test file draft — caught by ruff and removed immediately before commit.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- INFRA-05 satisfied: operators can observe sidecar health via geo-api's existing readiness endpoint
- Existing health tests (8) plus new sidecar tests (6) = 14 health tests, all passing
- `/health/ready` response shape is backwards-compatible (sidecars is a new additive key)

## Self-Check: PASSED

- FOUND: src/civpulse_geo/providers/tile_server.py
- FOUND: tests/test_health_ready_sidecars.py
- FOUND: .planning/phases/28-k8s-manifests-health-probe-updates/28-02-SUMMARY.md
- FOUND commit: 8fa40df (feat: _tile_server_reachable)
- FOUND commit: d98758f (test: sidecar RED tests)
- FOUND commit: f42a4e7 (feat: sidecars block in /health/ready)

---
*Phase: 28-k8s-manifests-health-probe-updates*
*Completed: 2026-04-04*
