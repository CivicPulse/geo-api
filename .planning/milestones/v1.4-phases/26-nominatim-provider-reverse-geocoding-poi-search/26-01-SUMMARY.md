---
phase: 26-nominatim-provider-reverse-geocoding-poi-search
plan: 01
subsystem: testing
tags: [pytest, nominatim, reverse-geocoding, poi, httpx, asyncmock, tdd]

# Dependency graph
requires:
  - phase: 25-tile-server-fastapi-tile-proxy
    provides: ASGITransport + AsyncMock pattern for httpx-backed endpoint testing
  - phase: prior
    provides: GeocodingProvider ABC, GeocodingResult schema, ProviderNetworkError hierarchy
provides:
  - RED-phase test suite for NominatimGeocodingProvider (6 unit tests)
  - RED-phase contract tests for GET /geocode/reverse (5 tests)
  - RED-phase contract tests for GET /poi/search (8 tests)
  - Full Phase 26 behavioral contract locked in before implementation
affects: [26-02, 26-03, 26-04, 26-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - patched_nominatim_client fixture overrides app.state.http_client with AsyncMock(spec=httpx.AsyncClient)
    - patched_nominatim_client also seeds app.state.providers["nominatim"] sentinel
    - 503 test pops "nominatim" from app.state.providers directly
    - radius search asserts viewbox param is present in upstream call (radius-to-bbox conversion required)
    - bbox search asserts viewbox + bounded=1 in upstream call

key-files:
  created:
    - tests/test_nominatim_provider.py
    - tests/test_api_reverse_geocode.py
    - tests/test_api_poi_search.py
  modified: []

key-decisions:
  - "test_geocode_http_500 kept as explicit alias to match plan spec; both tests verify HTTPStatusError wrapping"
  - "settings import removed from test_api_reverse_geocode.py (unused after review)"
  - "POI radius test asserts viewbox param present to enforce radius-to-bbox conversion in implementation"
  - "bbox malformed test accepts 400 or 422 (either custom validator or FastAPI Pydantic error is acceptable)"

patterns-established:
  - "Nominatim tests use MagicMock(spec=httpx.Response) consistent with tile proxy pattern"
  - "app.state.providers seeded/restored in fixtures to avoid test pollution"

requirements-completed: [GEO-01, GEO-02, GEO-03, GEO-04, GEO-05]

# Metrics
duration: 12min
completed: 2026-04-04
---

# Phase 26 Plan 01: Nominatim TDD Contract Tests Summary

**19 failing RED-phase tests locking the full Nominatim provider, reverse-geocode, and POI-search contract before any implementation exists**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-04T20:03:58Z
- **Completed:** 2026-04-04T20:16:00Z
- **Tasks:** 3
- **Files modified:** 3 (all created)

## Accomplishments
- 6 unit tests for NominatimGeocodingProvider (import fails until Plan 02 creates the module)
- 5 contract tests for GET /geocode/reverse (fail with 404 — route not implemented yet)
- 8 contract tests for GET /poi/search (fail — route not implemented yet)
- All 19 tests fail as required by RED-phase TDD discipline

## Task Commits

1. **Tasks 1-3: Write all three test files (batch commit)** - `4a880d5` (test)

## Files Created/Modified
- `tests/test_nominatim_provider.py` - 6 NominatimGeocodingProvider unit tests using AsyncMock httpx client
- `tests/test_api_reverse_geocode.py` - 5 contract tests for GET /geocode/reverse with fixture managing app.state
- `tests/test_api_poi_search.py` - 8 contract tests for GET /poi/search with radius/bbox/validation coverage

## Decisions Made
- Kept `test_geocode_http_500` as explicit test per plan spec (both tests verify HTTPStatusError → ProviderNetworkError wrapping from different angle)
- Removed unused `settings` import from reverse geocode test after ruff flagged it
- POI radius tests assert `viewbox` param present in upstream call to enforce the radius→bbox conversion in implementation
- Malformed bbox test accepts either 422 (FastAPI validator) or 400 (custom validator) — both are correct behaviors

## Deviations from Plan

None — plan executed exactly as written. All three files created, all 19 tests collectible (6 blocked by ModuleNotFoundError for nominatim provider, 13 collected and failing as expected).

## Issues Encountered
- Ruff flagged unused `settings` import in `test_api_reverse_geocode.py` — removed before commit. No impact on tests.

## Next Phase Readiness
- All 19 RED-phase tests committed and locked
- Plan 02 must create `src/civpulse_geo/providers/nominatim.py` to turn the 6 provider tests GREEN
- Plans 03-05 must implement routes + schemas to turn the 13 endpoint tests GREEN

---
*Phase: 26-nominatim-provider-reverse-geocoding-poi-search*
*Completed: 2026-04-04*
