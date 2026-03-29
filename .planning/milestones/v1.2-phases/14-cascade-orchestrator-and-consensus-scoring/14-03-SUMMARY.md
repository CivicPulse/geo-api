---
phase: 14
plan: 03
subsystem: geocoding-service-api
tags: [cascade, geocoding, api, dry-run, trace, is-outlier]
dependency_graph:
  requires: ["14-01", "14-02"]
  provides: ["cascade-integration", "geocoding-service-dispatcher", "api-cascade-params"]
  affects: ["geocoding-pipeline", "batch-geocoding", "api-routes"]
tech_stack:
  added: []
  patterns:
    - "Two-branch dispatcher pattern in GeocodingService.geocode() (cascade vs legacy)"
    - "FastAPI Query() params for dry_run and trace on POST /geocode"
    - "patch('civpulse_geo.services.geocoding.settings') pattern for cascade test isolation"
key_files:
  created: []
  modified:
    - src/civpulse_geo/services/geocoding.py
    - src/civpulse_geo/api/geocoding.py
    - tests/test_geocoding_service.py
    - tests/test_geocoding_api.py
decisions:
  - "patch settings via civpulse_geo.services.geocoding.settings (not the module directly) for test isolation"
  - "outlier_providers defaults to empty set() in legacy path result dict to avoid KeyError in API"
  - "Batch endpoint receives fuzzy_matcher from app.state (no dry_run/trace — debugging features only)"
  - "Existing legacy tests wrapped with cascade_enabled=False rather than rewriting with cascade mocks"
metrics:
  duration_minutes: 7
  completed_date: "2026-03-29"
  tasks_completed: 3
  files_modified: 4
  tests_added: 15
---

# Phase 14 Plan 03: Cascade Orchestrator Integration Summary

Wire CascadeOrchestrator into GeocodingService and API routes with two-branch dispatcher, dry_run/trace params, is_outlier response fields, and parameterized cascade/legacy tests.

## What Was Built

### Task 1: GeocodingService cascade dispatcher (39676cf)

Refactored `GeocodingService.geocode()` in `src/civpulse_geo/services/geocoding.py` to:

- Import `CascadeOrchestrator`, `CascadeResult`, and `FuzzyMatcher`
- Import `settings` for the `CASCADE_ENABLED` feature flag
- Dispatch to `CascadeOrchestrator().run()` when `settings.cascade_enabled=True`
- Fall back to `_legacy_geocode()` when `settings.cascade_enabled=False`
- Accept new params: `dry_run`, `trace`, `fuzzy_matcher`
- Move the entire v1.1 pipeline body (Steps 0-7) to `_legacy_geocode()` verbatim

The legacy path is byte-for-byte identical to the previous `geocode()` body. `set_official`, `refresh`, `get_by_provider`, `_get_official`, and `_apply_spell_correction` are unchanged.

### Task 2: API route cascade params (103afa3)

Updated `src/civpulse_geo/api/geocoding.py` to:

- Add `Query` import from fastapi
- Add `dry_run: bool = Query(False, ...)` and `trace: bool = Query(False, ...)` to `geocode()` route
- Pass `fuzzy_matcher=getattr(request.app.state, "fuzzy_matcher", None)`, `dry_run`, `trace` through to `service.geocode()`
- Build `outlier_providers = result.get("outlier_providers", set())` and include `is_outlier=r.provider_name in outlier_providers` in every `GeocodeProviderResult`
- Include `cascade_trace=result.get("cascade_trace")` and `would_set_official=would_set` in `GeocodeResponse`
- Convert `would_set_official` from `ProviderCandidate` (`.lat/.lng`) to `GeocodeProviderResult` (`.latitude/.longitude`)
- Update `_geocode_one()` batch helper with `fuzzy_matcher` param, `is_outlier` support, explicit `cascade_trace=None` / `would_set_official=None`
- Pass `fuzzy_matcher` from `app.state` to `batch_geocode()` helper calls

### Task 3: Tests (2c676ba)

Added to `tests/test_geocoding_service.py`:
- `test_geocode_delegates_to_cascade_when_enabled` — verifies `CascadeOrchestrator.run()` is called when `cascade_enabled=True`
- `test_geocode_delegates_to_legacy_when_disabled` — verifies `_legacy_geocode()` is called when `cascade_enabled=False`
- `test_geocode_passes_dry_run_and_trace` — verifies `dry_run=True` and `trace=True` forwarded to `CascadeOrchestrator.run()`
- `test_geocode_cascade_result_includes_outlier_providers` — verifies `outlier_providers` set in result dict
- `test_geocode_cache_hit_returns_cached_legacy` — legacy cache-hit test with explicit `cascade_enabled=False`
- Wrapped 7 existing legacy-path tests with `patch("civpulse_geo.services.geocoding.settings")` to force `cascade_enabled=False`

Added to `tests/test_geocoding_api.py`:
- `test_geocode_dry_run_param` — `?dry_run=true` returns `would_set_official` and `cascade_trace` fields
- `test_geocode_trace_param` — `?trace=true` returns `cascade_trace` list in response
- `test_geocode_normal_no_trace` — normal POST returns `cascade_trace=None`
- `test_geocode_response_has_is_outlier` — each result has `is_outlier` field
- `test_geocode_outlier_flagged_in_response` — `outlier_providers={"tiger"}` causes `is_outlier=True`
- `test_geocode_passes_dry_run_to_service` — verifies `dry_run=True` flows to service
- `test_geocode_passes_trace_to_service` — verifies `trace=True` flows to service

## Test Results

```
76 passed in 0.76s
```

Full test suite: 450+ passed, 11 pre-existing failures in test_import_cli.py and test_load_oa_cli.py (unrelated to this plan, from phase 12 changes).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Merged main branch prerequisites before execution**
- **Found during:** Plan start (pre-execution check)
- **Issue:** Worktree branch had not received plans 14-01 (config, schema) and 14-02 (cascade.py) artifacts
- **Fix:** `git merge main` fast-forwarded the branch to include all prerequisites
- **Files modified:** All files from plans 14-01 and 14-02
- **Commit:** N/A (merge commit)

**2. [Rule 1 - Bug] Existing legacy tests failing under CASCADE_ENABLED=true**
- **Found during:** Task 3 test baseline run
- **Issue:** 7 existing tests in TestLocalProviderBypass and two cache-hit tests assumed the legacy DB mock call sequence, but the default `cascade_enabled=True` routes them to CascadeOrchestrator (which makes different DB calls)
- **Fix:** Wrapped each affected test with `patch("civpulse_geo.services.geocoding.settings")` to set `cascade_enabled=False`, preserving their value as legacy-path regression tests
- **Files modified:** tests/test_geocoding_service.py
- **Commit:** 2c676ba (included in Task 3 commit)

## Known Stubs

None — all cascade paths wired end-to-end.

## Self-Check

Files exist:
- `src/civpulse_geo/services/geocoding.py` — FOUND (modified)
- `src/civpulse_geo/api/geocoding.py` — FOUND (modified)
- `tests/test_geocoding_service.py` — FOUND (modified)
- `tests/test_geocoding_api.py` — FOUND (modified)
