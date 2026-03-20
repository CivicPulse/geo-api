---
phase: 02-geocoding
plan: 01
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, httpx, census-geocoder, postgresql, postgis, cache]

requires:
  - phase: 01-foundation
    provides: Address ORM model, GeocodingResult ORM model, GeocodingProvider ABC, provider registry, normalization utilities, database session, PostGIS geography columns

provides:
  - Census Geocoder provider adapter (CensusGeocodingProvider) implementing GeocodingProvider ABC
  - Pydantic schemas (GeocodeRequest, GeocodeProviderResult, GeocodeResponse)
  - GeocodingService with cache-first pipeline (normalize -> hash -> cache check -> provider call -> upsert -> official auto-set)
  - POST /geocode FastAPI endpoint returning GeocodeResponse with cache_hit flag
  - Shared httpx.AsyncClient in app.state for provider calls
  - OfficialGeocoding auto-set on first successful result via ON CONFLICT DO NOTHING

affects: [02-02-admin-override, 02-refresh-endpoint, 03-validation, phase-03]

tech-stack:
  added: [httpx>=0.28.1 (promoted to runtime dependency)]
  patterns:
    - Cache-first geocoding: normalize -> SHA-256 hash -> DB lookup -> provider call on miss
    - PostgreSQL upsert via pg_insert ON CONFLICT DO UPDATE for geocoding_results
    - EWKT format for PostGIS point insertion: SRID=4326;POINT(lng lat)
    - selectinload() eager loading to prevent MissingGreenlet in async SQLAlchemy
    - Provider receives normalized address string, not raw freeform input
    - Fixed confidence constants: CENSUS_CONFIDENCE=0.8 for match, 0.0 for no-match
    - NO_MATCH results store location_type=None (not in LocationType enum) and location=None

key-files:
  created:
    - src/civpulse_geo/schemas/geocoding.py
    - src/civpulse_geo/schemas/__init__.py
    - src/civpulse_geo/providers/census.py
    - src/civpulse_geo/services/geocoding.py
    - src/civpulse_geo/services/__init__.py
    - src/civpulse_geo/api/geocoding.py
    - tests/test_census_provider.py
    - tests/test_geocoding_service.py
    - tests/test_geocoding_api.py
  modified:
    - pyproject.toml (httpx added to runtime deps)
    - uv.lock
    - src/civpulse_geo/main.py (lifespan, http_client, CensusGeocodingProvider, geocoding router)
    - tests/conftest.py (mock_http_client, mock_providers fixtures)

key-decisions:
  - "Census API y=lat, x=lng coordinate mapping is critical — swapped causes wrong geocoding results; enforced in both implementation and acceptance criteria"
  - "Census confidence fixed at 0.8 for match, 0.0 for no-match — stored as CENSUS_CONFIDENCE constant"
  - "NO_MATCH results store location_type=None (not in enum) and location=None in PostGIS column"
  - "GeocodingService is stateless, instantiated per-request — no singleton or class-level state"
  - "API tests patch app.state before requests rather than running lifespan — avoids real DB/Census API dependency in tests"

patterns-established:
  - "Cache-first pattern: normalize -> hash -> DB lookup -> provider on miss -> upsert -> official auto-set"
  - "EWKT point format: SRID=4326;POINT(lng lat) — longitude before latitude per WKT/PostGIS convention"
  - "selectinload() for all ORM relationships accessed in async context to prevent MissingGreenlet"
  - "Provider ABC signature preserved; extra kwargs (http_client) added as keyword-only args with default None"

requirements-completed: [GEO-01, GEO-02, GEO-03, GEO-04, GEO-05]

duration: 5min
completed: 2026-03-19
---

# Phase 2 Plan 01: Geocoding Pipeline Summary

**Census Geocoder provider adapter + cache-first GeocodingService + POST /geocode FastAPI endpoint with PostgreSQL upsert and OfficialGeocoding auto-set**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-19T05:26:06Z
- **Completed:** 2026-03-19T05:31:16Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

- CensusGeocodingProvider implements GeocodingProvider ABC with correct y=lat, x=lng coordinate mapping, 0.8 confidence on match, ProviderNetworkError on failure
- GeocodingService implements complete cache-first pipeline: normalize address, SHA-256 hash, Address find-or-create, cache check, provider call, pg_insert upsert, OfficialGeocoding auto-set
- POST /geocode endpoint returns GeocodeResponse with address_hash, normalized_address, cache_hit flag, results list, and optional official result
- httpx promoted to runtime dependency; shared AsyncClient in app.state lifespan

## Task Commits

Each task was committed atomically:

1. **Task 1: Pydantic schemas, Census provider adapter, and unit tests** - `25cce1c` (feat)
2. **Task 2: GeocodingService, POST /geocode endpoint, and integration wiring** - `e6d04e4` (feat)

## Files Created/Modified

- `src/civpulse_geo/schemas/geocoding.py` - GeocodeRequest, GeocodeProviderResult, GeocodeResponse Pydantic models
- `src/civpulse_geo/schemas/__init__.py` - Re-exports for schema module
- `src/civpulse_geo/providers/census.py` - CensusGeocodingProvider with Census Geocoder API integration
- `src/civpulse_geo/services/geocoding.py` - GeocodingService cache-first pipeline with PostgreSQL upsert
- `src/civpulse_geo/services/__init__.py` - Re-exports for service module
- `src/civpulse_geo/api/geocoding.py` - FastAPI router with POST /geocode endpoint
- `src/civpulse_geo/main.py` - Updated lifespan: httpx.AsyncClient, CensusGeocodingProvider, geocoding router
- `pyproject.toml` - httpx added to runtime dependencies
- `tests/test_census_provider.py` - 9 unit tests for Census provider
- `tests/test_geocoding_service.py` - 8 unit tests for GeocodingService cache-first logic
- `tests/test_geocoding_api.py` - 3 integration tests for POST /geocode endpoint
- `tests/conftest.py` - Added mock_http_client and mock_providers fixtures

## Decisions Made

- **Census coordinate order:** y=lat, x=lng — Census API uses GeoJSON-like x/y not lat/lng naming. Enforced with CENSUS_CONFIDENCE constant and acceptance criteria check for `lat=coords["y"]`.
- **NO_MATCH handling:** location_type=None (not in LocationType enum), latitude=0.0, longitude=0.0, location=None. Avoids enum mapping error for a non-standard value.
- **API test isolation:** Tests patch `GeocodingService.geocode` and set `app.state` directly rather than running the full lifespan. This avoids requiring a real database or Census API in the test suite.
- **Provider ABC compatibility:** `geocode()` adds `http_client` as keyword-only arg with default None, maintaining ABC contract while enabling injectable clients for testing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] API tests needed app.state mock before lifespan runs**

- **Found during:** Task 2 (test_geocoding_api.py)
- **Issue:** API tests creating AsyncClient without lifespan raised `AttributeError: 'State' object has no attribute 'providers'` since the lifespan that sets app.state wasn't triggered
- **Fix:** Added `patched_app_state` fixture to tests that sets `app.state.http_client` and `app.state.providers` before each test, cleaned up after
- **Files modified:** tests/test_geocoding_api.py
- **Verification:** All 3 API tests pass; `test_post_geocode_returns_200`, `test_post_geocode_response_structure`, `test_post_geocode_missing_address` all exit 0
- **Committed in:** e6d04e4 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix necessary for test isolation. No scope creep.

## Issues Encountered

None beyond the app.state test isolation issue documented above.

## User Setup Required

None - no external service configuration required. The Census Geocoder is free and requires no API key.

## Next Phase Readiness

- POST /geocode endpoint is complete and ready for integration testing against a live database
- Cache-first pattern established: GeocodingService can be extended for force_refresh and admin override endpoints in 02-02
- CensusGeocodingProvider is registered at startup; adding Google or other providers requires only adding to load_providers dict
- OfficialGeocoding auto-set pattern ready for admin override to supersede in next plan

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 02-geocoding*
*Completed: 2026-03-19*
