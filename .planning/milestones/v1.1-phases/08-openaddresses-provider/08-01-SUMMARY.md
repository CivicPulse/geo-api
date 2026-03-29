---
phase: 08-openaddresses-provider
plan: 01
subsystem: api
tags: [sqlalchemy, geoalchemy2, postgis, usaddress, scourgify, openaddresses, async]

# Dependency graph
requires:
  - phase: 07-pipeline-infrastructure
    provides: openaddresses_points staging table ORM model, is_local bypass on GeocodingProvider/ValidationProvider ABCs
provides:
  - OAGeocodingProvider: queries openaddresses_points, returns GeocodingResult with accuracy-mapped location_type/confidence
  - OAValidationProvider: queries openaddresses_points, re-normalizes via scourgify, returns ValidationResult
  - Both providers registered in FastAPI lifespan as app.state.providers["openaddresses"] and app.state.validation_providers["openaddresses"]
affects: [09-tiger-provider, 10-nad-provider, geocoding-service, validation-service]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ST_Y/ST_X extracted in same SELECT via func.ST_Y(column.cast(Geometry)) to avoid second DB round-trip
    - geocode(**kwargs) pattern for accepting http_client= from service layer without TypeError
    - scourgify + usaddress two-step parse for street_number/street_name extraction from freeform input
    - scourgify re-normalization of matched OA row with fallback to raw OA components

key-files:
  created:
    - src/civpulse_geo/providers/openaddresses.py
    - tests/test_oa_provider.py
  modified:
    - src/civpulse_geo/main.py

key-decisions:
  - "geocode() accepts **kwargs to avoid TypeError when service layer calls provider.geocode(normalized, http_client=http_client)"
  - "lat/lng extracted via ST_Y/ST_X in same SELECT as row fetch — no second query"
  - "OA providers instantiated directly in lifespan (not via load_providers) because they require async_sessionmaker argument"
  - "scourgify re-normalization on matched row with exception-safe fallback to raw OA columns for USPS-normalized output"
  - "ACCURACY_MAP default ('APPROXIMATE', 0.1) covers empty string and None accuracy values via .get(accuracy or '', DEFAULT_ACCURACY)"

patterns-established:
  - "Local provider pattern: is_local=True, accepts **kwargs, wraps SQLAlchemyError in ProviderError"
  - "Async session factory pattern: async with self._session_factory() as session"
  - "Two-step address parse: scourgify normalize -> usaddress.tag() for token extraction"

requirements-completed: [OA-01, OA-02, OA-03, OA-04]

# Metrics
duration: 4min
completed: 2026-03-22
---

# Phase 8 Plan 01: OpenAddresses Provider Summary

**OAGeocodingProvider and OAValidationProvider querying openaddresses_points via ST_Y/ST_X, registered in FastAPI lifespan, with accuracy-mapped confidence scores and scourgify USPS re-normalization**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-22T19:59:25Z
- **Completed:** 2026-03-22T20:02:56Z
- **Tasks:** 2 (TDD: 3 commits for Task 1 + 1 commit for Task 2)
- **Files modified:** 3

## Accomplishments

- OAGeocodingProvider queries openaddresses_points with ST_Y/ST_X lat/lng extraction in a single SELECT, maps OA accuracy field to location_type/confidence, returns NO_MATCH on parse failure or DB miss
- OAValidationProvider matches the same DB row, re-normalizes through scourgify with fallback to raw OA components, returns ValidationResult with confidence=1.0 on match
- Both providers registered unconditionally in FastAPI lifespan; 28 new tests all green, 226 total passing

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests for OA providers** - `2735508` (test)
2. **TDD GREEN: OAGeocodingProvider and OAValidationProvider** - `e492d7e` (feat)
3. **Task 2: Register OA providers in FastAPI lifespan** - `0286047` (feat)

_Note: TDD tasks have two commits (test -> feat). No REFACTOR commit needed._

## Files Created/Modified

- `src/civpulse_geo/providers/openaddresses.py` - OAGeocodingProvider and OAValidationProvider with ACCURACY_MAP, _parse_input_address, _find_oa_match helpers
- `tests/test_oa_provider.py` - 28 tests covering all accuracy mappings, no-match paths, **kwargs, ProviderError wrapping, batch loops, scourgify fallback
- `src/civpulse_geo/main.py` - Added AsyncSessionLocal and OA provider imports, registered both providers in lifespan after load_providers() calls

## Decisions Made

- geocode() accepts `**kwargs` to be compatible with the service layer calling `provider.geocode(normalized, http_client=http_client)` — this was flagged in the plan interfaces section as CRITICAL
- lat/lng extracted in the same SELECT via `func.ST_Y(OpenAddressesPoint.location.cast(Geometry))` to avoid a second DB round-trip per geocode call
- OA providers instantiated directly in lifespan rather than via `load_providers()` because they require `async_sessionmaker` as a constructor argument, not an HTTP client
- scourgify re-normalization on matched OA row fields uses an exception-safe fallback to raw OA columns when scourgify cannot parse the reconstructed address string

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pre-existing test failure in `tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features` references a missing file `/data/SAMPLE_Address_Points.geojson`. This failure predates Phase 8 work and is unrelated to OA providers. All 226 other tests pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- OA provider foundation established; Tiger provider (Phase 9) can follow the same local provider pattern (is_local=True, **kwargs, ProviderError wrapping, async session factory)
- The `_parse_input_address` + `_find_oa_match` helper pattern is reusable across local providers
- Both OA providers are in `app.state.providers` and `app.state.validation_providers` and will be exercised by the geocoding/validation service layer immediately

---
*Phase: 08-openaddresses-provider*
*Completed: 2026-03-22*
