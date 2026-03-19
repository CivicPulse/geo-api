---
phase: 05-fix-admin-override-and-import-order
plan: "01"
subsystem: database
tags: [postgres, postgis, sqlalchemy, geocoding, admin-override, cli]

# Dependency graph
requires:
  - phase: 03-cli-import
    provides: CLI import command with admin_overrides guard
  - phase: 02-geocoding-service
    provides: set_official() with custom coordinate (GEO-07) path
provides:
  - AdminOverride upsert in set_official else-branch (GEO-07)
  - DATA-03 import-order constraint documented in CLI docstring and inline comment
  - Tests for AdminOverride write and upsert behavior
  - Test for CLI admin-override guard preventing official_geocoding INSERT
affects: [phase-06, any future geocoding service changes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pg_insert(AdminOverride).on_conflict_do_update with index_elements=[address_id] for upsert"
    - "5-call AsyncMock sequence for set_official else-branch: addr_lookup, GR_upsert, AdminOverride_upsert, GR_requery, OfficialGeocoding_upsert"

key-files:
  created: []
  modified:
    - src/civpulse_geo/services/geocoding.py
    - src/civpulse_geo/cli/__init__.py
    - tests/test_geocoding_service.py
    - tests/test_import_cli.py

key-decisions:
  - "AdminOverride upsert is inserted between GeocodingResult upsert and GeocodingResult re-query in set_official else-branch -- this preserves result_id availability for the OfficialGeocoding upsert"
  - "AdminOverride upsert uses index_elements=[address_id] matching the unique=True constraint on the model"
  - "DATA-03 documented in both docstring (operational overview) and inline comment (near ON CONFLICT DO NOTHING) to ensure the constraint is visible at two reading points"

patterns-established:
  - "AdminOverride upsert belongs ONLY in the else: branch of set_official -- the if has_result_id: branch (GEO-06 path) must not write to admin_overrides"

requirements-completed: [DATA-03, GEO-07]

# Metrics
duration: 15min
completed: 2026-03-19
---

# Phase 05 Plan 01: Fix Admin Override and Import Order Summary

**AdminOverride table now receives an upsert on every set_official() custom-coordinate call, closing the silent data-loss bug where admin overrides were never persisted to admin_overrides; DATA-03 import-order constraint documented in CLI**

## Performance

- **Duration:** 15 min
- **Started:** 2026-03-19T17:00:00Z
- **Completed:** 2026-03-19T17:15:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Fixed silent bug: set_official() else-branch now writes pg_insert(AdminOverride).on_conflict_do_update after GeocodingResult upsert (GEO-07)
- Updated 2 existing tests (test_set_custom_official, test_set_custom_official_stores_reason) to use 5-call mock sequence
- Added 2 new tests proving AdminOverride write and upsert behavior
- Documented DATA-03 import-order constraint in import_gis docstring and inline comment near ON CONFLICT DO NOTHING guard
- Added test_import_skips_official_when_admin_override_exists proving CLI guard prevents official_geocoding INSERT when override row exists
- Full suite: 179 tests passing, no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add AdminOverride upsert to set_official and update existing tests** - `44775c4` (feat)
2. **Task 2: Document DATA-03 import-order constraint and add CLI guard test** - `8ed3fee` (feat)

**Plan metadata:** *(see final docs commit)*

## Files Created/Modified
- `src/civpulse_geo/services/geocoding.py` - Added AdminOverride to import block; inserted pg_insert(AdminOverride).on_conflict_do_update in set_official else-branch between GeocodingResult upsert and re-query
- `src/civpulse_geo/cli/__init__.py` - Updated import_gis docstring with DATA-03 operational constraint; updated inline comment near override_row guard with DATA-03 explanation
- `tests/test_geocoding_service.py` - Updated existing tests to 5-call mock sequence; added test_set_custom_official_writes_admin_override and test_set_custom_official_upserts_admin_override
- `tests/test_import_cli.py` - Added test_import_skips_official_when_admin_override_exists

## Decisions Made
- AdminOverride upsert is inserted between GeocodingResult upsert and GeocodingResult re-query in set_official else-branch -- this preserves result_id availability for the OfficialGeocoding upsert
- AdminOverride upsert uses index_elements=["address_id"] matching the unique=True constraint on the AdminOverride model
- DATA-03 documented in both docstring (operational overview) and inline comment (near ON CONFLICT DO NOTHING) to ensure the constraint is visible at two reading points

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GEO-07 is fully implemented: set_official custom-coordinate path writes AdminOverride row
- DATA-03 constraint is documented and tested
- Ready for Phase 06 if planned

## Self-Check: PASSED

- SUMMARY.md: FOUND
- src/civpulse_geo/services/geocoding.py: FOUND
- Commit 44775c4 (Task 1): FOUND
- Commit 8ed3fee (Task 2): FOUND

---
*Phase: 05-fix-admin-override-and-import-order*
*Completed: 2026-03-19*
