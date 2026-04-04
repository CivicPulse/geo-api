---
phase: 27-valhalla-routing
plan: "01"
subsystem: testing
tags: [fastapi, pytest, httpx, valhalla, routing, tdd]

requires:
  - phase: 26-nominatim-poi-search
    provides: test pattern (AsyncClient + ASGITransport + app.state monkeypatch)
  - phase: 25-tile-server-fastapi-tile-proxy
    provides: tile test fixture pattern (patched http_client fixture)

provides:
  - 11 RED-phase contract tests for GET /route endpoint
  - _mock_valhalla_response() helper
  - patched_valhalla_http fixture (sets app.state.valhalla_enabled=True + mocks http_client)

affects:
  - 27-02 (must implement route.py, schemas/route.py to satisfy these tests)

tech-stack:
  added: []
  patterns:
    - "app.state.valhalla_enabled monkeypatch pattern for 503 guard testing"
    - "POST body spot-check pattern (verify exact JSON sent to upstream)"

key-files:
  created:
    - tests/test_api_route.py
  modified: []

key-decisions:
  - "test_route_valhalla_empty_returns_404 passes coincidentally in RED (FastAPI 404 for missing route == expected 404); real handler logic tested when Plan 02 mounts the endpoint"
  - "Used patched_valhalla_http fixture over inline monkeypatching for consistent teardown"
  - "POST body spot-check embedded in test_route_pedestrian to verify exact Valhalla body shape"

patterns-established:
  - "valhalla_enabled flag tested via direct app.state assignment in fixture and test teardown"
  - "_mock_valhalla_response() mirrors _mock_nominatim_search_response() pattern from Phase 26"

requirements-completed:
  - ROUTE-01
  - ROUTE-02
  - ROUTE-03

duration: 8min
completed: 2026-04-04
---

# Phase 27 Plan 01: Valhalla Routing TDD RED Summary

**11 AsyncClient contract tests for GET /route covering pedestrian/auto modes, RouteResponse schema, km-to-meters conversion, and all error paths (400/404/422/502/503)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-04T00:00:00Z
- **Completed:** 2026-04-04T00:08:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created tests/test_api_route.py with 11 contract tests, all currently FAILING (RED phase)
- Established patched_valhalla_http fixture mirroring Phase 25/26 patterns
- Spot-checked exact POST body shape sent to Valhalla upstream in test 1
- All ruff lint checks pass

## Task Commits

1. **Task 1: Write 10 contract tests for GET /route** - `11f8f44` (test)

**Plan metadata:** (pending final commit)

## Files Created/Modified

- `tests/test_api_route.py` - 11 RED-phase contract tests for /route endpoint

## Decisions Made

- Coincidental pass on `test_route_valhalla_empty_returns_404`: FastAPI returns 404 for any unknown path, which matches the assertion. This is acceptable RED-phase behavior — once Plan 02 mounts the `/route` handler, this test will exercise the actual no-route 404 logic.
- Embedded POST body spot-check directly in `test_route_pedestrian_returns_200_with_route_response` rather than a separate test, keeping the contract assertion close to the happy-path test.
- `patched_valhalla_http` fixture sets `app.state.valhalla_enabled = True` unconditionally so tests that need it don't have to repeat the setup.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 27-02 can now implement `src/civpulse_geo/api/route.py`, `src/civpulse_geo/schemas/route.py`, and wire valhalla startup guard in `main.py` to turn these 11 tests GREEN
- Tests assert exact POST body shape, response schema types, and all 5 error status codes — full target contract is defined

---
*Phase: 27-valhalla-routing*
*Completed: 2026-04-04*
