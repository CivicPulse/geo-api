---
phase: quick
plan: 260324-lqg
subsystem: tiger-provider
tags: [bug-fix, tiger, postgis, sql, extension-check]
dependency_graph:
  requires: []
  provides: [correct-tiger-extension-guard]
  affects: [tiger-provider-registration]
tech_stack:
  added: []
  patterns: [pg_extension catalog query]
key_files:
  modified:
    - src/civpulse_geo/providers/tiger.py
    - tests/test_tiger_provider.py
  created: []
decisions:
  - "Use pg_extension WHERE extname (not pg_available_extensions WHERE name) to check for installed extensions — prevents false-positive registration when extension exists on server but is not activated in the current database"
metrics:
  duration_minutes: 5
  completed_date: "2026-03-24T15:42:29Z"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 2
  files_created: 0
---

# Quick Task 260324-lqg: Fix Tiger Extension Check Predicate

**One-liner:** Corrected `CHECK_EXTENSION_SQL` to query `pg_extension WHERE extname` (installed) instead of `pg_available_extensions WHERE name` (available-but-not-installed), closing TIGR-04 false-positive registration edge case.

## What Was Done

Replaced the Tiger provider startup guard SQL from querying `pg_available_extensions` (which lists extensions available for installation on the server) to querying `pg_extension` (which lists extensions actually installed via `CREATE EXTENSION` in the current database).

The old predicate caused `_tiger_extension_available()` to return `True` when `postgis_tiger_geocoder` was present in the server's extension catalog but had not been activated in the current database — leading Tiger providers to register at startup and then fail at runtime with SQL function-not-found errors.

## Tasks

| # | Name | Type | Commit | Status |
|---|------|------|--------|--------|
| 1 | Fix CHECK_EXTENSION_SQL and update docstrings/tests | auto/tdd | 6bbf483 | Done |

## Changes Made

### `src/civpulse_geo/providers/tiger.py`

- `CHECK_EXTENSION_SQL`: changed `SELECT 1 FROM pg_available_extensions WHERE name = 'postgis_tiger_geocoder'` to `SELECT 1 FROM pg_extension WHERE extname = 'postgis_tiger_geocoder'`
- Module docstring: updated reference from `pg_available_extensions` to `pg_extension (installed extensions)`
- `_tiger_extension_available` docstring: updated to describe installed-extension semantics

### `tests/test_tiger_provider.py`

- `test_returns_true_when_extension_present`: updated docstring to reference `pg_extension`
- `test_returns_false_when_query_returns_none`: updated docstring to reference `pg_extension`
- No logic changes — mock-based tests are independent of the actual SQL string

## Verification

```
grep -n "pg_extension" src/civpulse_geo/providers/tiger.py
# -> lines 16, 75, 87 (module docstring, SQL, function docstring)

grep -n "pg_available_extensions" src/civpulse_geo/providers/tiger.py
# -> no matches

uv run pytest tests/test_tiger_provider.py -x -q
# -> 25 passed
```

## Deviations from Plan

None — plan executed exactly as written.

## Pre-existing Issue (Out of Scope)

`tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features` fails with `FileNotFoundError: data/SAMPLE_Address_Points.geojson`. This failure pre-dates this quick task and is unrelated to the Tiger extension check fix. Not fixed here.

## Self-Check: PASSED

- [x] `src/civpulse_geo/providers/tiger.py` exists and contains `pg_extension`
- [x] `src/civpulse_geo/providers/tiger.py` contains zero references to `pg_available_extensions`
- [x] Commit `6bbf483` exists
- [x] 25 Tiger provider tests pass
