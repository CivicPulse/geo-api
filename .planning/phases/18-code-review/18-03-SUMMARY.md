---
phase: 18-code-review
plan: "03"
subsystem: database/services
tags: [performance, connection-pool, consensus-scoring, ruff, code-review]
dependency_graph:
  requires: [18-01]
  provides: [REVIEW-03]
  affects: [database.py, cascade.py, config.py, fuzzy.py]
tech_stack:
  added: []
  patterns:
    - Explicit SQLAlchemy async engine pool sizing (pool_size, max_overflow, pool_pre_ping, pool_recycle)
    - Provider weight map keys matching main.py registration names exactly
key_files:
  created:
    - .planning/phases/18-code-review/18-FINDINGS.md
  modified:
    - src/civpulse_geo/config.py
    - src/civpulse_geo/database.py
    - src/civpulse_geo/services/cascade.py
    - src/civpulse_geo/services/fuzzy.py
    - tests/test_cascade.py
decisions:
  - PERF-01 pool config: db_pool_size=5, db_max_overflow=5 gives max 10 connections per worker — within PostgreSQL default 100 max_connections for single-replica K8s deployment
  - PERF-06 weight keys: weight_map now uses "postgis_tiger" and "national_address_database" matching main.py registration; old "tiger"/"nad" aliases removed
  - pool_pre_ping hardcoded True in database.py (not configurable) — always desirable for stale connection detection
  - pool_recycle configurable via db_pool_recycle setting (default 3600s)
  - TDD: wrote failing tests first (RED), confirmed failures, then implemented fixes (GREEN)
  - Updated existing TestGetProviderWeight tests to use corrected provider names (Rule 1 auto-fix — tests were testing the wrong keys)
metrics:
  duration: ~10 minutes
  completed: 2026-03-29
  tasks_completed: 2
  files_modified: 5
  files_created: 1
requirements:
  - REVIEW-03
---

# Phase 18 Plan 03: Performance Audit and Findings Report Summary

**One-liner:** Explicit connection pool config (pool_size=5/max_overflow=5/pool_pre_ping) and Tiger weight key fix from "tiger" to "postgis_tiger" correcting consensus scoring for all Tiger geocode results.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for PERF-06 weight mapping | 94cecbc | tests/test_cascade.py |
| 1 (GREEN) | Fix PERF-01, PERF-06, ruff F841 | ef735f3 | config.py, database.py, cascade.py, fuzzy.py, test_cascade.py |
| 2 | Write 18-FINDINGS.md | 3cedf24 | .planning/phases/18-code-review/18-FINDINGS.md |

## Acceptance Criteria Verification

- [x] config.py contains `db_pool_size: int = 5`
- [x] config.py contains `db_max_overflow: int = 5`
- [x] config.py contains `db_pool_recycle: int = 3600`
- [x] database.py contains `pool_size=settings.db_pool_size`
- [x] database.py contains `max_overflow=settings.db_max_overflow`
- [x] database.py contains `pool_pre_ping=True`
- [x] database.py contains `pool_recycle=settings.db_pool_recycle`
- [x] cascade.py weight_map contains key `"postgis_tiger"` (NOT `"tiger"`)
- [x] cascade.py weight_map contains key `"national_address_database"` (NOT just `"nad"`)
- [x] fuzzy.py does NOT contain `candidate_rows =` assignment
- [x] tests/test_cascade.py contains `class TestProviderWeightMapping`
- [x] tests/test_cascade.py contains `test_postgis_tiger_gets_correct_weight`
- [x] tests/test_cascade.py contains `test_national_address_database_gets_correct_weight`
- [x] `uv run ruff check src/` exits 0 (ALL 5 original lint issues resolved)
- [x] `uv run pytest tests/test_cascade.py -v` exits 0
- [x] `uv run pytest tests/ -q` exits 0 — 541 passed, 2 skipped

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated TestGetProviderWeight to use corrected provider names**
- **Found during:** Task 1 (GREEN phase — running full test suite)
- **Issue:** Pre-existing `test_nad_weight` tested `get_provider_weight("nad")` and `test_tiger_weight` tested `get_provider_weight("tiger")`. After fixing the weight_map keys to `"national_address_database"` and `"postgis_tiger"`, these tests now tested the "unknown provider falls to 0.50" path — they were asserting 0.80/0.40 but getting 0.50.
- **Fix:** Updated `test_nad_weight` to call `get_provider_weight("national_address_database")` and `test_tiger_weight` to call `get_provider_weight("postgis_tiger")`.
- **Files modified:** tests/test_cascade.py
- **Commit:** ef735f3

## Known Stubs

None.

## Self-Check: PASSED

- src/civpulse_geo/config.py: FOUND (db_pool_size, db_max_overflow, db_pool_recycle)
- src/civpulse_geo/database.py: FOUND (pool_size, max_overflow, pool_pre_ping, pool_recycle)
- src/civpulse_geo/services/cascade.py: FOUND (postgis_tiger, national_address_database keys)
- src/civpulse_geo/services/fuzzy.py: CLEAN (no candidate_rows)
- tests/test_cascade.py: FOUND (TestProviderWeightMapping, 4 new tests)
- .planning/phases/18-code-review/18-FINDINGS.md: EXISTS
- Commits ef735f3, 94cecbc, 3cedf24: all present in git log
- Test suite: 541 passed, 2 skipped, 2 warnings (no regressions)
- Ruff: All checks passed
