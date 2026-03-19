---
phase: 02-geocoding
plan: 02
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, admin-override, cache-refresh, provider-query, postgresql]

requires:
  - phase: 02-geocoding
    plan: 01
    provides: GeocodingService.geocode(), POST /geocode, OfficialGeocoding auto-set, cache-first pipeline

provides:
  - GeocodingService.set_official() — GEO-06 (point at existing result) and GEO-07 (custom lat/lng) paths
  - GeocodingService.refresh() — GEO-08 force re-query all providers via force_refresh=True
  - GeocodingService.get_by_provider() — GEO-09 fetch a specific provider's result
  - PUT /geocode/{address_hash}/official endpoint — admin override (GEO-06/07)
  - POST /geocode/{address_hash}/refresh endpoint — cache invalidation (GEO-08)
  - GET /geocode/{address_hash}/providers/{provider_name} endpoint — provider comparison (GEO-09)
  - SetOfficialRequest, OfficialResponse, RefreshResponse, ProviderResultResponse Pydantic schemas

affects: [03-validation, phase-03]

tech-stack:
  added: []
  patterns:
    - Admin override uses provider_name="admin_override" with confidence=1.0 — authoritative synthetic result
    - OfficialGeocoding upsert with ON CONFLICT DO UPDATE on address_id — idempotent set_official
    - refresh() delegates to geocode(force_refresh=True) — reuses cache-first pipeline, avoids duplication
    - GEO-07 custom coordinate stored as GeocodingResult row (not AdminOverride table) — uniform official pointer
    - ValueError raised from service, caught in API layer and raised as HTTPException(404)

key-files:
  created: []
  modified:
    - src/civpulse_geo/schemas/geocoding.py (SetOfficialRequest, OfficialResponse, RefreshResponse, ProviderResultResponse added)
    - src/civpulse_geo/services/geocoding.py (set_official, refresh, get_by_provider added)
    - src/civpulse_geo/api/geocoding.py (three new endpoints: PUT /official, POST /refresh, GET /providers/{name})
    - tests/test_geocoding_service.py (8 new tests for set_official, refresh, get_by_provider)
    - tests/test_geocoding_api.py (8 new tests for three new endpoints)

key-decisions:
  - "GEO-07 custom coordinate stored as GeocodingResult row with provider_name=admin_override rather than AdminOverride table — keeps OfficialGeocoding pointer uniform (always geocoding_result_id)"
  - "refresh() delegates to existing geocode(force_refresh=True) rather than duplicating provider loop — single source of truth for cache bypass"
  - "confidence=1.0 for admin_override results — admin coordinate is treated as authoritative"
  - "reason stored in raw_response JSON field of GeocodingResult — avoids separate AdminOverride table join for common read path"
  - "_make_mock_orm_row test fixture requires explicit raw_response=None to satisfy Pydantic ProviderResultResponse validation"

metrics:
  duration: 4min
  completed: 2026-03-19
  tasks: 2
  files_modified: 5
---

# Phase 2 Plan 02: Admin Override, Cache Refresh, Provider Query Summary

**Admin set-official (GEO-06/07) + cache refresh (GEO-08) + provider-specific query (GEO-09) endpoints completing Phase 2 geocoding surface with 17 new tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-19T05:33:43Z
- **Completed:** 2026-03-19T05:37:43Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- PUT /geocode/{address_hash}/official accepts either geocoding_result_id (GEO-06, existing provider result) or latitude+longitude (GEO-07, custom admin coordinate); both paths upsert OfficialGeocoding via ON CONFLICT DO UPDATE
- GEO-07 creates a synthetic GeocodingResult row with provider_name="admin_override", confidence=1.0, reason in raw_response — keeps OfficialGeocoding pointer uniform
- POST /geocode/{address_hash}/refresh (GEO-08) delegates to geocode(force_refresh=True), re-queries all providers and upserts results; returns refreshed_providers list
- GET /geocode/{address_hash}/providers/{provider_name} (GEO-09) fetches a single provider's result by address_id + provider_name; raises 404 on miss
- All endpoints return 404 for unknown address_hash via service ValueError -> HTTPException pattern
- Full test suite: 90 tests pass (Phase 1 + Phase 2 Plan 01 + Plan 02)

## Task Commits

Each task was committed atomically:

1. **Task 1: Admin set-official and custom-coordinate endpoints** - `f3bd6f6` (feat)
2. **Task 2: Cache refresh and provider-specific query endpoints** - `fbdc11d` (feat)

## Files Created/Modified

- `src/civpulse_geo/schemas/geocoding.py` — Added SetOfficialRequest, OfficialResponse, RefreshResponse, ProviderResultResponse
- `src/civpulse_geo/services/geocoding.py` — Added set_official(), refresh(), get_by_provider() methods
- `src/civpulse_geo/api/geocoding.py` — Added PUT /official, POST /refresh, GET /providers/{name} endpoints
- `tests/test_geocoding_service.py` — 8 new service-level tests for all three new methods
- `tests/test_geocoding_api.py` — 8 new API integration tests for all three new endpoints + fixture fix

## Decisions Made

- **GEO-07 uses GeocodingResult not AdminOverride:** Custom coordinates stored as GeocodingResult rows with provider_name="admin_override". This keeps OfficialGeocoding always pointing at a geocoding_result_id, avoiding conditional logic in the read path. The AdminOverride table exists in the schema but is not used by this plan.
- **refresh() delegates to geocode():** Rather than duplicating the provider loop and upsert logic, refresh() calls self.geocode(force_refresh=True). This reuses the full cache-bypass pipeline and avoids divergence.
- **confidence=1.0 for admin_override:** Admin coordinate is treated as authoritative — highest possible confidence.
- **reason in raw_response:** Avoids needing to join AdminOverride table on common read paths. Raw JSON is flexible for future metadata.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test fixture _make_mock_orm_row missing explicit raw_response**

- **Found during:** Task 2 GREEN phase (test_get_provider_results)
- **Issue:** `_make_mock_orm_row` used `MagicMock(spec=GeocodingResultORM)` without setting `raw_response` explicitly. Pydantic's `ProviderResultResponse` rejected the MagicMock object for the `raw_response: dict | None` field with `ValidationError: Input should be a valid dictionary`.
- **Fix:** Added `raw_response=None` parameter to `_make_mock_orm_row` and set `row.raw_response = raw_response` explicitly.
- **Files modified:** tests/test_geocoding_api.py
- **Verification:** All 12 Task 2 tests passed after fix; full suite 90/90.
- **Committed in:** fbdc11d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test fixture)
**Impact on plan:** Minor — one-line fixture fix. No scope creep.

## Issues Encountered

None beyond the test fixture issue documented above.

## User Setup Required

None — all new endpoints use the same database session and app.state dependencies established in Plan 01.

## Next Phase Readiness

- All GEO-01 through GEO-09 requirements completed
- Phase 2 geocoding surface is complete: geocode, set-official, refresh, provider-specific query
- Phase 3 (validation) can add POST /validate using the same dependency injection pattern
- OfficialGeocoding upsert pattern established for admin override; Phase 3 can reference the same table

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 02-geocoding*
*Completed: 2026-03-19*
