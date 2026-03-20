---
phase: 04-batch-and-hardening
plan: 02
subsystem: api
tags: [fastapi, asyncio, batch, validation, pydantic, pytest]

# Dependency graph
requires:
  - phase: 04-01
    provides: "BatchValidateRequest, BatchValidateResponse, BatchValidateResultItem, BatchItemError, classify_exception schemas in schemas/batch.py; batch geocode pattern to mirror"
  - phase: 03-validation
    provides: "ValidationService.validate(), ValidationResultORM, api/validation.py router"
provides:
  - "POST /validate/batch endpoint in api/validation.py"
  - "_validate_one() module-level helper with semaphore + per-item exception isolation"
  - "7 batch validate tests in tests/test_batch_validation_api.py"
  - "INFRA-04 and INFRA-06 requirements fully covered"
affects: [05-deployment, future-api-consumers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_validate_one() helper: asyncio.Semaphore-guarded, catches all exceptions per item, always returns BatchValidateResultItem"
    - "All-fail detection: succeeded==0 and failed>0 pattern (not simply len(failures)) -- correctly handles empty batch returning 200"
    - "Outer 422 via JSONResponse(status_code=422, content=response_body.model_dump()) -- FastAPI model serialization bypassed for error response"
    - "TDD RED/GREEN: create failing tests then implement until all pass"

key-files:
  created:
    - tests/test_batch_validation_api.py
  modified:
    - src/civpulse_geo/api/validation.py

key-decisions:
  - "_validate_one() does NOT take http_client parameter -- ValidationService.validate() uses scourgify which is offline (no HTTP needed)"
  - "Uses request.app.state.validation_providers (NOT request.app.state.providers) -- validation providers registered separately from geocoding providers"
  - "asyncio.gather without return_exceptions=True is correct -- _validate_one() catches all exceptions and always returns BatchValidateResultItem"
  - "patched_app_state fixture sets both validation_providers and http_client -- app expects http_client even for validation tests due to shared lifespan"

patterns-established:
  - "Batch route pattern: empty-early-return -> semaphore -> gather -> count -> all-fail check -> return"
  - "Per-item helper pattern: try/except with classify_exception maps all provider exceptions to typed item results"

requirements-completed: [INFRA-04, INFRA-06]

# Metrics
duration: 2min
completed: 2026-03-19
---

# Phase 04 Plan 02: Batch Validation API Summary

**POST /validate/batch with asyncio.gather, per-item error isolation, and 7 comprehensive tests -- completing INFRA-04 and INFRA-06**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-19T15:59:14Z
- **Completed:** 2026-03-19T16:01:30Z
- **Tasks:** 2 (Task 1 TDD: RED + GREEN commits; Task 2 regression verification)
- **Files modified:** 2

## Accomplishments
- POST /validate/batch endpoint delivering per-item results with individual status codes
- Per-item exception isolation: ProviderError -> 422 item, ProviderNetworkError -> 500 item; other items unaffected
- All-fail batch returns outer HTTP 422; mixed or all-success returns 200 with full result array
- Empty batch (0 addresses) returns 200 with zero counts without touching the service
- Batch size > 100 returns 422 via Pydantic model_validator before handler executes
- 176/176 tests pass (all phases) with zero regressions
- Both /geocode/batch and /validate/batch confirmed in OpenAPI spec

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests** - `36c2ebc` (test)
2. **Task 1 GREEN: Batch validate endpoint** - `924852d` (feat)
3. **Task 2: Full regression + OpenAPI** - verified; no new files staged (verification only)

_Note: TDD tasks have separate RED and GREEN commits._

## Files Created/Modified
- `tests/test_batch_validation_api.py` - 7 batch validation tests covering all scenarios
- `src/civpulse_geo/api/validation.py` - Added _validate_one() helper + @router.post("/batch") handler

## Decisions Made
- `_validate_one()` does not accept `http_client` -- ValidationService uses scourgify (offline library), no HTTP client needed. Differs from geocode batch.
- `patched_app_state` fixture sets both `app.state.validation_providers` and `app.state.http_client` -- tests need http_client set even for validation because the shared app lifespan may reference it.
- Plan followed exactly; no architectural deviations.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both batch endpoints (geocode + validate) are fully implemented and tested
- INFRA-03, INFRA-04, and INFRA-06 requirements complete
- Phase 4 batch-and-hardening is now fully complete
- All 176 tests passing; codebase is clean

## Self-Check: PASSED

- tests/test_batch_validation_api.py: FOUND
- src/civpulse_geo/api/validation.py: FOUND
- 04-02-SUMMARY.md: FOUND
- Commit 36c2ebc (TDD RED): FOUND
- Commit 924852d (TDD GREEN): FOUND

---
*Phase: 04-batch-and-hardening*
*Completed: 2026-03-19*
