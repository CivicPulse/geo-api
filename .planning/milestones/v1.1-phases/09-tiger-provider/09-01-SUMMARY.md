---
phase: 09-tiger-provider
plan: 01
subsystem: api
tags: [postgis, tiger, geocoding, validation, sqlalchemy, fastapi]

# Dependency graph
requires:
  - phase: 08-oa-provider
    provides: OAGeocodingProvider/OAValidationProvider pattern with is_local=True, async_sessionmaker injection, **kwargs pattern

provides:
  - TigerGeocodingProvider calling PostGIS geocode() SQL function with rating-to-confidence mapping
  - TigerValidationProvider calling PostGIS normalize_address() SQL function with parsed-flag checking
  - _tiger_extension_available() startup guard checking pg_available_extensions
  - Conditional Tiger provider registration in FastAPI lifespan

affects: [10-nad-provider, future-phases-using-providers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - SQL function provider pattern (vs staging table query) using sqlalchemy text() with named bind params
    - Rating-to-confidence formula: max(0.0, min(1.0, (100 - rating) / 100))
    - Extension availability guard pattern with bare except -> return False

key-files:
  created:
    - src/civpulse_geo/providers/tiger.py
    - tests/test_tiger_provider.py
  modified:
    - src/civpulse_geo/main.py
    - pyproject.toml

key-decisions:
  - "Tiger calls PostGIS SQL functions (geocode/normalize_address) directly rather than staging table — no data import step needed"
  - "Confidence = max(0.0, min(1.0, (100 - rating) / 100)) — clamped to never be negative for ratings > 100"
  - "_tiger_extension_available uses bare except to ensure startup never crashes when Tiger is absent"
  - "Provider count log lines moved after Tiger registration block to report final inclusive count"

patterns-established:
  - "SQL function provider: module-level text() constants, named bind params :address, result.first() pattern"
  - "Extension guard: async check at startup, conditional registration, warning log on absence"

requirements-completed: [TIGR-01, TIGR-02, TIGR-03, TIGR-04]

# Metrics
duration: 4min
completed: 2026-03-24
---

# Phase 9 Plan 1: Tiger Provider Summary

**TigerGeocodingProvider and TigerValidationProvider using PostGIS geocode()/normalize_address() SQL functions, with rating-to-confidence mapping (0->1.0, clamped) and conditional startup registration via pg_available_extensions check**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-24T07:00:06Z
- **Completed:** 2026-03-24T07:03:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- TigerGeocodingProvider with GEOCODE_SQL calling PostGIS geocode() function, confidence clamped via max(0.0, min(1.0, (100 - rating) / 100))
- TigerValidationProvider with NORMALIZE_SQL calling PostGIS normalize_address() function, NO_MATCH when parsed=False or no row
- _tiger_extension_available() startup guard using CHECK_EXTENSION_SQL against pg_available_extensions
- 25 unit tests passing all behaviors: NO_MATCH, confidence boundaries (0/50/100/108), kwargs, ProviderError wrapping, batch serial loops
- Conditional Tiger registration in FastAPI lifespan with warning when extension absent

## Task Commits

Each task was committed atomically:

1. **Task 1: TigerGeocodingProvider, TigerValidationProvider, and unit tests** - `38a4ed1` (feat + TDD)
2. **Task 2: Register Tiger providers conditionally in FastAPI lifespan** - `39875d8` (feat)

**Plan metadata:** (docs commit — see below)

_Note: Task 1 used TDD — tests written first (RED), then implementation (GREEN), committed together_

## Files Created/Modified

- `src/civpulse_geo/providers/tiger.py` — TigerGeocodingProvider, TigerValidationProvider, _tiger_extension_available, SQL constants
- `tests/test_tiger_provider.py` — 25 unit tests covering all specified behaviors
- `src/civpulse_geo/main.py` — Tiger import + conditional registration block in lifespan
- `pyproject.toml` — Added `tiger:` pytest marker

## Decisions Made

- Tiger calls PostGIS SQL functions directly (not staging table) — no data import step; function availability is checked at startup via pg_available_extensions
- Confidence clamping via `max(0.0, min(1.0, ...))` ensures rating > 100 never produces negative confidence
- Bare `except` in `_tiger_extension_available` ensures startup never crashes if Tiger is absent — returns False silently
- Provider count log lines moved after Tiger registration block so counts reflect final state including conditionally-registered Tiger providers

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Pre-existing test failures in `tests/test_import_cli.py` (missing fixture file `data/SAMPLE_Address_Points.geojson`) were confirmed pre-existing before our changes and are out of scope.

## User Setup Required

None - no external service configuration required. Tiger provider activation is conditional on PostGIS Tiger extension availability in the connected PostgreSQL instance.

## Self-Check: PASSED

All files exist and both task commits (38a4ed1, 39875d8) are present in git history.

## Next Phase Readiness

- Tiger provider complete; Phase 10 (NAD provider) can now begin
- NAD provider will follow table-query pattern (different from this plan's SQL function pattern) — isolation goal achieved
- Pre-existing `test_import_cli.py` failures (missing fixture file) should be tracked as deferred items for cleanup

---
*Phase: 09-tiger-provider*
*Completed: 2026-03-24*
