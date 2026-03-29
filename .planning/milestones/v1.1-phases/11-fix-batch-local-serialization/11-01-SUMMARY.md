---
phase: 11-fix-batch-local-serialization
plan: 01
subsystem: api
tags: [batch, serialization, gap-closure, local-providers]

# Dependency graph
requires:
  - phase: 07-pipeline-infrastructure/07-01
    provides: Local provider pipeline bypass, local_results/local_candidates keys in service response dict
  - phase: 10-nad-provider/10-02
    provides: Full v1.1 provider suite complete — all local providers registered and tested
provides:
  - Verified GAP-INT-01 fix from commit f6f904d
  - 16/16 batch endpoint tests passing including 2 regression tests (test_batch_geocode_local_results_included, test_batch_validate_local_candidates_included)
  - Phase 11 documentation close-out confirming GAP-INT-01 closure
affects: [batch-api-consumers]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created:
    - .planning/phases/11-fix-batch-local-serialization/11-01-SUMMARY.md
  modified:
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "GAP-INT-01 was fixed in commit f6f904d before planning began; Phase 11 is verification-only — no new implementation"
  - "Pre-existing test_import_cli.py failures (10 tests, missing data/SAMPLE_Address_Points.geojson) confirmed out of scope — predates v1.1"

patterns-established: []
requirements-completed: []
gaps-closed: [GAP-INT-01]

# Metrics
duration: 5min
completed: 2026-03-24
---

# Phase 11 Plan 01: Fix Batch Local Serialization Summary

**Verified GAP-INT-01 closure: batch endpoints now include local_results/local_candidates via fix applied in commit f6f904d before planning began — 16/16 batch tests pass including 2 regression tests**

## Performance

- **Duration:** 5 min
- **Completed:** 2026-03-24
- **Tasks:** 2 (Task 1: test verification; Task 2: documentation close-out)
- **Files modified:** 2 (.planning/ROADMAP.md, .planning/STATE.md)
- **Files created:** 1 (this SUMMARY.md)

## What GAP-INT-01 Was

`POST /geocode/batch` and `POST /validate/batch` silently dropped local provider results. The Phase 7
pipeline bypass correctly populated `local_results` and `local_candidates` keys in the service layer
response dict. The defect was in the batch API handler serialization helpers `_geocode_one()` (in
`src/civpulse_geo/api/geocoding.py`) and `_validate_one()` (in `src/civpulse_geo/api/validation.py`),
which constructed their `GeocodeResponse` / `ValidateResponse` objects without passing the
`local_results=` and `local_candidates=` keyword arguments. Since both schema fields default to `[]`,
the omission was silent — no error, just always-empty local result lists in batch responses.

## What Commit f6f904d Fixed

The fix added local result wiring to both batch helpers:

**`_geocode_one()` in `src/civpulse_geo/api/geocoding.py`:** Builds `local_provider_results` list by
iterating `result.get("local_results", [])` and constructing `GeocodeProviderResult` objects using
`.lat`/`.lng` (the `GeocodingResult` dataclass field names — distinct from ORM row `.latitude`/`.longitude`).
This list is then passed as `local_results=local_provider_results` to `GeocodeResponse(...)`.

**`_validate_one()` in `src/civpulse_geo/api/validation.py`:** Builds `local_candidates` list by
iterating `result.get("local_candidates", [])` and constructing `ValidationCandidate` objects from
`ValidationResult` dataclass fields. Passed as `local_candidates=local_candidates` to `ValidateResponse(...)`.

## Test Evidence

Regression tests added in the same commit (f6f904d):

| Test | File | Result |
|------|------|--------|
| `test_batch_geocode_local_results_included` | `tests/test_batch_geocoding_api.py` | PASSED |
| `test_batch_validate_local_candidates_included` | `tests/test_batch_validation_api.py` | PASSED |

Full batch suite:
- `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v` — **16 passed**
- Full project: 325 passed, 10 pre-existing failures (test_import_cli.py missing fixture), 2 skipped

## Files Modified by the Fix (commit f6f904d)

- `src/civpulse_geo/api/geocoding.py` — `_geocode_one()` wires `local_results=`
- `src/civpulse_geo/api/validation.py` — `_validate_one()` wires `local_candidates=`
- `tests/test_batch_geocoding_api.py` — Added regression test + `_make_geocode_success_return_with_local()` helper
- `tests/test_batch_validation_api.py` — Added regression test + `_make_validate_success_return_with_local()` helper

## Task Commits

Task 1 (verify tests): No source files changed — test run only; verification logged here.

Task 2 (documentation close-out): Captured in docs commit (this SUMMARY.md + ROADMAP.md + STATE.md).

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `.planning/phases/11-fix-batch-local-serialization/11-01-SUMMARY.md` — FOUND (this file)
- `.planning/ROADMAP.md` contains `[x] **Phase 11` — verified via grep
- `.planning/STATE.md` contains `status: complete` — verified
- `GAP-INT-01` referenced in SUMMARY.md — present
- `f6f904d` referenced in SUMMARY.md — present
- `gaps-closed` in SUMMARY.md frontmatter — present

---
*Phase: 11-fix-batch-local-serialization*
*Completed: 2026-03-24*
