---
phase: 03-validation-and-data-import
plan: 03
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, scourgify, postgresql, validation, cache]

# Dependency graph
requires:
  - phase: 03-01
    provides: ScourgifyValidationProvider, ValidationResultORM model, ValidationResult dataclass
  - phase: 02-01
    provides: GeocodingService pattern, canonical_key normalization, Address model, pg_insert upsert pattern

provides:
  - POST /validate endpoint accepting freeform and structured address input
  - ValidationService with cache-first pipeline (normalize, find/create address, cache check, upsert)
  - ValidateRequest/ValidateResponse/ValidationCandidate Pydantic schemas
  - ScourgifyValidationProvider registered in app.state.validation_providers
  - 20 tests covering unit (schemas + service) and integration (API) layers

affects:
  - phase-04-downstream-consumers
  - any consumer of the /validate endpoint

# Tech tracking
tech-stack:
  added: []
  patterns:
    - cache-first validation pipeline (mirrors GeocodingService)
    - stateless per-request service instantiation
    - pg_insert ON CONFLICT DO UPDATE for upsert semantics
    - ProviderError -> HTTP 422 mapping in router layer
    - app.state.validation_providers registry separate from app.state.providers

key-files:
  created:
    - src/civpulse_geo/schemas/validation.py
    - src/civpulse_geo/services/validation.py
    - src/civpulse_geo/api/validation.py
    - tests/test_validation_service.py
    - tests/test_validation_api.py
  modified:
    - src/civpulse_geo/main.py
    - tests/conftest.py

key-decisions:
  - "ValidationService is stateless (instantiated per-request) — mirrors GeocodingService pattern"
  - "validation_providers registered separately from geocoding providers in app.state — avoids isinstance confusion between GeocodingProvider and ValidationProvider in mixed loops"
  - "ProviderError from scourgify maps to HTTP 422 (not 500) — unparseable addresses are client-side input errors"
  - "Cache check queries validation_results by address_id; cache hit if any rows exist for that address"
  - "Integration tests patch ValidationService.validate at the service layer (not provider layer) — simpler mock setup, consistent with geocoding API test pattern"

patterns-established:
  - "Cache-first pipeline: normalize -> find/create Address -> cache check -> provider call on miss -> pg_insert upsert -> commit"
  - "Router reads providers from request.app.state.validation_providers (not http_client needed for offline scourgify)"
  - "to_freeform() on ValidateRequest handles both input modes before service call"

requirements-completed:
  - VAL-01
  - VAL-02
  - VAL-03
  - VAL-04
  - VAL-05
  - VAL-06

# Metrics
duration: 6min
completed: 2026-03-19
---

# Phase 03 Plan 03: Validation Service and API Summary

**POST /validate endpoint with cache-first ValidationService: normalizes addresses via scourgify, stores in validation_results with pg_insert upsert, returns USPS candidates with cache_hit flag**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-19T14:26:35Z
- **Completed:** 2026-03-19T14:32:35Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Validation vertical slice complete: POST /validate accepts freeform or structured input and returns USPS-normalized candidates with confidence scores
- Cache-first ValidationService mirrors GeocodingService: normalize -> find/create Address -> cache check -> pg_insert upsert on miss -> commit
- ProviderError from scourgify (PO boxes, gibberish) correctly maps to HTTP 422 with descriptive detail
- 20 tests added (13 unit + 7 integration), full suite passes at 162 tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Pydantic schemas, ValidationService, and unit tests** - `b606edc` (feat)
2. **Task 2: Validation router, app wiring, and integration tests** - `7e2c7b2` (feat)

_Note: Task 1 followed TDD pattern (RED: write failing tests -> GREEN: implement until pass)_

## Files Created/Modified

- `src/civpulse_geo/schemas/validation.py` - ValidateRequest (freeform+structured), ValidationCandidate, ValidateResponse Pydantic models
- `src/civpulse_geo/services/validation.py` - ValidationService with cache-first pipeline
- `src/civpulse_geo/api/validation.py` - POST /validate FastAPI router with ProviderError -> 422 mapping
- `src/civpulse_geo/main.py` - Added ScourgifyValidationProvider registration and validation router
- `tests/test_validation_service.py` - 13 unit tests: schema validation, cache hit/miss, ProviderError propagation
- `tests/test_validation_api.py` - 7 integration tests: HTTP 200/422 scenarios, response structure
- `tests/conftest.py` - Added mock_validation_providers fixture

## Decisions Made

- **Separate validation_providers registry**: `app.state.validation_providers` is a distinct dict from `app.state.providers` (geocoding). The ValidationService loop does `isinstance(provider, ValidationProvider)` to skip non-validation providers, but keeping them separate avoids accidentally routing geocoding providers into the validation pipeline.
- **HTTP 422 for ProviderError**: Scourgify raises ProviderError for PO boxes and unparseable addresses. These are client-side input errors (invalid address), so 422 Unprocessable Entity is the correct status code — not 500.
- **Integration tests patch at service layer**: Tests patch `ValidationService.validate` directly rather than the provider, consistent with geocoding API test pattern. This gives simpler mock setup and tests the router transformation logic independently.
- **Cache check by address_id**: After finding/creating the Address record, ValidationService queries `validation_results WHERE address_id = ?`. Any rows present = cache hit. No expiration logic (consistent with geocoding service design decision from Phase 02).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tests passed on first run after implementation.

## User Setup Required

None - no external service configuration required. ScourgifyValidationProvider is offline (pure Python, no API key).

## Next Phase Readiness

- POST /validate endpoint is live and fully tested
- Validation vertical slice complete: provider -> service -> API -> tests
- Phase 03 all 3 plans complete — validation-and-data-import phase finished
- Ready for phase 04 (downstream consumers or production deployment)

---
*Phase: 03-validation-and-data-import*
*Completed: 2026-03-19*
