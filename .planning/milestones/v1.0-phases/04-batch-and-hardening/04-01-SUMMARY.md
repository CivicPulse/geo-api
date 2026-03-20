---
phase: 04-batch-and-hardening
plan: 01
subsystem: api
tags: [fastapi, pydantic, asyncio, batch, geocoding]

# Dependency graph
requires:
  - phase: 02-geocoding-pipeline
    provides: GeocodingService.geocode() single-address method with ORM result dict
  - phase: 03-validation-and-import
    provides: ValidateResponse Pydantic schema reused in BatchValidateResultItem

provides:
  - POST /geocode/batch endpoint with per-item error isolation and asyncio.gather concurrency
  - schemas/batch.py with all 7 batch Pydantic models for both geocode and validate endpoints
  - classify_exception() helper mapping ProviderError variants to HTTP status codes
  - Settings.max_batch_size=100 and Settings.batch_concurrency_limit=10

affects:
  - 04-02  # Plan 02 (batch validate) reuses BatchValidateRequest, BatchValidateResponse, BatchValidateResultItem, classify_exception

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-item error isolation: _geocode_one() catches all exceptions, asyncio.gather never sees exceptions"
    - "Semaphore-based concurrency: asyncio.Semaphore(settings.batch_concurrency_limit) caps concurrent provider calls"
    - "All-fail detection: outer HTTP 422 when succeeded==0 and failed>0, via JSONResponse(status_code=422)"
    - "classify_exception() maps ProviderNetworkError/RateLimit/Auth to 500, base ProviderError to 422, unknown to 500"

key-files:
  created:
    - src/civpulse_geo/schemas/batch.py
    - tests/test_batch_geocoding_api.py
  modified:
    - src/civpulse_geo/config.py
    - src/civpulse_geo/api/geocoding.py

key-decisions:
  - "_geocode_one() is a module-level helper in api/geocoding.py, not a GeocodingService method — keeps batch orchestration in the router layer"
  - "asyncio.gather without return_exceptions=True is correct here — _geocode_one() never raises; all errors become BatchGeocodeResultItem with error field"
  - "All-fail detection uses succeeded==0 and failed>0 (not just all-fail) to correctly handle empty batch edge case returning 200"
  - "Batch validate schemas (BatchValidateRequest, BatchValidateResponse, BatchValidateResultItem) defined in Plan 01 as single source of truth for Plan 02"

patterns-established:
  - "Batch route handler: gather + semaphore + per-item isolation + all-fail JSONResponse override"
  - "TDD RED/GREEN flow: write failing tests first, verify 404, then implement, verify all pass"

requirements-completed: [INFRA-03, INFRA-06]

# Metrics
duration: 20min
completed: 2026-03-19
---

# Phase 4 Plan 01: Batch Geocode Endpoint Summary

**POST /geocode/batch with asyncio.gather concurrency, per-item ProviderError isolation, and shared batch Pydantic schemas for both geocode and validate endpoints**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-03-19T15:52:00Z
- **Completed:** 2026-03-19T15:56:09Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created `schemas/batch.py` with 7 Pydantic models covering both batch geocode and batch validate endpoints (Plan 02 ready to use them immediately)
- Implemented `POST /geocode/batch` with `asyncio.Semaphore`-controlled `asyncio.gather`, per-item exception handling, and all-fail HTTP 422 override
- Added `max_batch_size=100` and `batch_concurrency_limit=10` to `Settings`
- 7 new tests pass (all-success, partial-failure, all-fail, empty, exceeds-limit, structure, network-error); 169 total tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Create batch Pydantic schemas and config settings** - `b9fc3d3` (feat)
2. **Task 2 RED: Add failing tests for batch geocode endpoint** - `cd73959` (test)
3. **Task 2 GREEN: Implement batch geocode endpoint** - `74bdba2` (feat)

_Note: TDD task 2 has two commits (test RED then feat GREEN)_

## Files Created/Modified

- `src/civpulse_geo/schemas/batch.py` — All 7 batch Pydantic models plus `classify_exception()` helper
- `src/civpulse_geo/config.py` — Added `max_batch_size=100` and `batch_concurrency_limit=10` to Settings
- `src/civpulse_geo/api/geocoding.py` — Added `_geocode_one()` helper and `POST /geocode/batch` route
- `tests/test_batch_geocoding_api.py` — 7 tests covering all batch geocode scenarios

## Decisions Made

- `_geocode_one()` is a module-level helper in `api/geocoding.py`, not a `GeocodingService` method — keeps batch orchestration in the router layer where it belongs
- `asyncio.gather` without `return_exceptions=True` is correct: `_geocode_one()` never raises, it always returns a `BatchGeocodeResultItem`; all errors become per-item error fields
- All-fail detection uses `succeeded==0 and failed>0` (not `all failed`) to correctly handle the empty batch edge case returning 200
- Batch validate schemas (`BatchValidateRequest`, `BatchValidateResponse`, `BatchValidateResultItem`) defined in Plan 01 as single source of truth for Plan 02 to import

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 02 (`POST /validate/batch`) can import `BatchValidateRequest`, `BatchValidateResponse`, `BatchValidateResultItem`, and `classify_exception` directly from `schemas/batch.py`
- `settings.max_batch_size` and `settings.batch_concurrency_limit` are available for Plan 02's semaphore pattern
- No blockers.

---
*Phase: 04-batch-and-hardening*
*Completed: 2026-03-19*

## Self-Check: PASSED

- FOUND: src/civpulse_geo/schemas/batch.py
- FOUND: src/civpulse_geo/api/geocoding.py
- FOUND: tests/test_batch_geocoding_api.py
- FOUND: .planning/phases/04-batch-and-hardening/04-01-SUMMARY.md
- FOUND: commit b9fc3d3 (feat: schemas and config)
- FOUND: commit cd73959 (test: RED phase)
- FOUND: commit 74bdba2 (feat: GREEN phase implementation)
