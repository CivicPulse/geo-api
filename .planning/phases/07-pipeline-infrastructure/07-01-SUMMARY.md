---
phase: 07-pipeline-infrastructure
plan: 01
subsystem: api
tags: [python, sqlalchemy, fastapi, providers, geocoding, validation]

# Dependency graph
requires:
  - phase: 06-admin-override
    provides: GeocodingService and ValidationService with cache-first pipeline
provides:
  - is_local property on GeocodingProvider and ValidationProvider ABCs (defaults False)
  - Local provider bypass path in GeocodingService.geocode() (local_results key)
  - Local provider bypass path in ValidationService.validate() (local_candidates key)
  - Cache-hit short-circuit that correctly excludes local providers
affects: [08-openaddresses, 09-tiger, 10-nad]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "is_local concrete property on ABCs — no subclass changes needed for remote providers"
    - "Split provider dict into local/remote before pipeline steps"
    - "Local providers bypass pg_insert but still trigger Address upsert"
    - "Return dicts include local_results/local_candidates keys on all code paths"

key-files:
  created: []
  modified:
    - src/civpulse_geo/providers/base.py
    - src/civpulse_geo/services/geocoding.py
    - src/civpulse_geo/services/validation.py
    - tests/test_providers.py
    - tests/test_geocoding_service.py
    - tests/test_validation_service.py

key-decisions:
  - "is_local is a concrete property (not abstract) so existing providers need zero changes"
  - "OfficialGeocoding auto-set skipped for local-only requests (no ORM row to reference)"
  - "_get_official() only called when remote results exist, avoiding unnecessary db.execute calls"
  - "AsyncMock(spec=GeocodingProvider) returns truthy mock for is_local — test helpers must explicitly set is_local=False"

patterns-established:
  - "Local provider pattern: override is_local property to return True, no other changes required"
  - "Service layer splits providers before pipeline: local_providers/remote_providers dicts"
  - "All return paths (cache-hit and cache-miss) include local_results/local_candidates keys"

requirements-completed: [PIPE-01, PIPE-02]

# Metrics
duration: 25min
completed: 2026-03-22
---

# Phase 7 Plan 01: Pipeline Infrastructure Summary

**is_local property on provider ABCs with geocoding/validation service bypass path — local providers skip geocoding_results/validation_results DB writes while still upserting Address records**

## Performance

- **Duration:** 25 min
- **Started:** 2026-03-22T14:42:38Z
- **Completed:** 2026-03-22T15:07:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added concrete `is_local` property to both `GeocodingProvider` and `ValidationProvider` ABCs, defaulting to `False` — no changes required in census or scourgify providers
- Refactored `GeocodingService.geocode()` to split providers into local/remote, call local providers without DB upsert, and return results under `local_results` key
- Refactored `ValidationService.validate()` identically, with results under `local_candidates` key
- Cache-hit short-circuit now correctly skips when any local provider is requested
- 16 new tests across 3 test files, all passing; 189 total tests passing (10 pre-existing failures in test_import_cli.py unrelated to this plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add is_local property to provider ABCs** - `b33960c` (feat)
2. **Task 2: Refactor service layers for local provider bypass** - `a13f22d` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks — RED then GREEN per task_

## Files Created/Modified
- `src/civpulse_geo/providers/base.py` - Added `is_local` concrete property to both GeocodingProvider and ValidationProvider
- `src/civpulse_geo/services/geocoding.py` - Split provider loop, local bypass path, local_results key on all return paths
- `src/civpulse_geo/services/validation.py` - Same pattern; local_candidates key on all return paths
- `tests/test_providers.py` - Added TestIsLocalProperty class (6 tests)
- `tests/test_geocoding_service.py` - Added TestLocalProviderBypass class (5 tests), fixed _make_provider helper with is_local=False
- `tests/test_validation_service.py` - Added TestLocalProviderBypass class (5 tests), fixed _make_validation_provider helper with is_local=False

## Decisions Made
- `is_local` is concrete (not abstract) so all 0 existing providers need zero code changes — pure backward-compatible addition
- `OfficialGeocoding` auto-set only references remote ORM rows; local results have no `geocoding_result_id` and cannot be linked
- `_get_official()` is only called when `new_results` is non-empty, avoiding an extra db.execute cycle for local-only requests
- `AsyncMock(spec=GeocodingProvider)` returns truthy mock for `is_local` — test helpers must explicitly set `is_local = False` to classify as remote

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Skipped _get_official() call for local-only requests**
- **Found during:** Task 2 (service layer implementation)
- **Issue:** When only local providers were present, `new_results` was empty but `_get_official()` was still called, making an extra db.execute call that hit the mock Address object (which lacks `geocoding_result_id`)
- **Fix:** Guard `_get_official()` call behind `if new_results:` check
- **Files modified:** src/civpulse_geo/services/geocoding.py
- **Verification:** TestLocalProviderBypass tests pass with execute call count verified
- **Committed in:** a13f22d (Task 2 commit)

**2. [Rule 1 - Bug] Updated test helper mocks to set is_local=False explicitly**
- **Found during:** Task 2 (test execution)
- **Issue:** `AsyncMock(spec=GeocodingProvider)` returns a MagicMock for `is_local`, which is truthy — causing existing test remote providers to be classified as local
- **Fix:** Added `provider.is_local = False` to `_make_provider()` and `_make_validation_provider()` helpers
- **Files modified:** tests/test_geocoding_service.py, tests/test_validation_service.py
- **Verification:** All existing cache-hit/cache-miss tests pass unchanged
- **Committed in:** a13f22d (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (Rule 1 bugs discovered during GREEN phase)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
- Pre-existing test failures in `tests/test_import_cli.py` (10 tests) due to missing `data/SAMPLE_Address_Points.geojson` and `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml` files — verified pre-existing via git stash. Out of scope for this plan.

## Next Phase Readiness
- Provider ABCs have `is_local` property — Phase 8 OpenAddresses provider can override to `True` without any service layer changes
- Both service layers have the bypass path wired — Phase 8-10 providers only need to implement provider logic
- Blocker (Phase 9 Tiger): verify all five Tiger extensions present in postgis/postgis:17-3.5 before implementing

---
*Phase: 07-pipeline-infrastructure*
*Completed: 2026-03-22*

## Self-Check: PASSED
- All 7 expected files present
- Commits b33960c and a13f22d verified in git log
