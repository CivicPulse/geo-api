---
phase: 10-nad-provider
plan: 01
subsystem: api
tags: [nad, geocoding, validation, sqlalchemy, scourgify, usaddress, postgis, geoalchemy2]

# Dependency graph
requires:
  - phase: 08-oa-provider
    provides: OAGeocodingProvider/OAValidationProvider pattern and _parse_input_address function reused by NAD
  - phase: 09-tiger-provider
    provides: conditional provider registration pattern (_tiger_extension_available) cloned for _nad_data_available
provides:
  - NADGeocodingProvider querying nad_points with PLACEMENT_MAP confidence/location_type mapping
  - NADValidationProvider querying nad_points with scourgify re-normalization and raw NAD fallback
  - _nad_data_available for startup conditional registration check
  - _find_nad_match returning (NADPoint, lat, lng) tuple in single SQL query
  - Conditional NAD provider registration in main.py lifespan after Tiger block
  - models/nad.py docstring corrected to CSV-delimited
affects: [11-nad-loading, phase-10-integration-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - PLACEMENT_MAP dict[str, tuple[str, float]] for NAD Placement -> (location_type, confidence) translation
    - _parse_input_address imported from openaddresses module (no duplication of address parsing logic)
    - Validation scourgify fallback uses provider-native column names (state, zip_code not region/postcode)
    - _nad_data_available uses SQL EXISTS to avoid full count scan at startup

key-files:
  created:
    - src/civpulse_geo/providers/nad.py
    - tests/test_nad_provider.py
  modified:
    - src/civpulse_geo/main.py
    - src/civpulse_geo/models/nad.py

key-decisions:
  - "_parse_input_address reused from openaddresses module — no address parsing duplication across OA and NAD providers"
  - "PLACEMENT_MAP has exactly 7 keys covering all known NAD Placement values; DEFAULT_PLACEMENT ('APPROXIMATE', 0.1) handles None/empty/unknown/garbage"
  - "NAD providers use nad_row.state (not .region) and nad_row.zip_code (not .postcode) — column names differ from OA"
  - "_nad_data_available uses bare except to ensure startup never crashes even if nad_points table doesn't exist yet"

patterns-established:
  - "Conditional provider registration pattern: check data/extension availability, register if present, warn if not, log final count after all blocks"
  - "NAD-specific column names (state/zip_code) differ from OA (region/postcode) — validation fallback must use the correct column names for each provider"

requirements-completed: [NAD-01, NAD-02, NAD-04]

# Metrics
duration: 4min
completed: 2026-03-24
---

# Phase 10 Plan 01: NAD Provider Summary

**NAD geocoding and validation providers with 7-value PLACEMENT_MAP, conditional startup registration via _nad_data_available, and 34-test TDD suite**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-24T09:23:55Z
- **Completed:** 2026-03-24T09:27:50Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- NADGeocodingProvider and NADValidationProvider backed by nad_points staging table, both with is_local=True
- PLACEMENT_MAP covering all 7 NAD Placement values with exact (location_type, confidence) tuples; DEFAULT_PLACEMENT for None/empty/unknown/garbage
- _nad_data_available function for conditional startup registration; wired into main.py lifespan after Tiger block
- models/nad.py docstring corrected from "pipe-delimited TXT" to "CSV-delimited (CSVDelimited format per schema.ini)"

## Task Commits

Each task was committed atomically:

1. **Task 1: Create NAD providers with PLACEMENT_MAP and test suite** - `332224f` (feat)
2. **Task 2: Wire NAD conditional registration in lifespan and fix NAD model docstring** - `2894610` (feat)

**Plan metadata:** (docs commit follows)

_Note: Task 1 followed TDD: RED (test file with ImportError) then GREEN (implementation, 34/34 passing)_

## Files Created/Modified

- `src/civpulse_geo/providers/nad.py` - NADGeocodingProvider, NADValidationProvider, PLACEMENT_MAP, DEFAULT_PLACEMENT, _find_nad_match, _nad_data_available
- `tests/test_nad_provider.py` - 34 tests across TestPlacementMapping, TestNADGeocodingProvider, TestNADValidationProvider, TestNadDataAvailable (535 lines)
- `src/civpulse_geo/main.py` - Added NAD import and conditional registration block after Tiger block
- `src/civpulse_geo/models/nad.py` - Corrected class docstring to CSV-delimited

## Decisions Made

- `_parse_input_address` reused from `openaddresses` module — address parsing logic is identical and duplication would create drift risk
- NAD Placement strings are long-form ("Structure - Rooftop") unlike OA accuracy strings ("rooftop") — PLACEMENT_MAP dict lookup is the cleanest approach
- Validation fallback block explicitly uses `nad_row.state` and `nad_row.zip_code` with inline comments to prevent future contributors from accidentally using OA-style column names

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

The `test_import_cli.py` suite has 10 pre-existing failures (missing `data/SAMPLE_Address_Points.geojson` fixture file) that are unrelated to this plan. Confirmed pre-existing by stash check. All 312 other tests pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- NAD geocoding and validation providers are fully implemented and tested
- Conditional registration in main.py is ready for when nad_points data is loaded
- Phase 10 Plan 02 (load-nad CLI) can now populate the table and trigger registration

---
*Phase: 10-nad-provider*
*Completed: 2026-03-24*
