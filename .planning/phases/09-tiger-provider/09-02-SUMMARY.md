---
phase: 09-tiger-provider
plan: "02"
subsystem: cli
tags: [tiger, postgis, cli, docker, fips, geocoder]
dependency_graph:
  requires: ["09-01"]
  provides: ["setup-tiger CLI command", "Docker Tiger extension init script"]
  affects: ["docker-compose.yml", "src/civpulse_geo/cli/__init__.py"]
tech_stack:
  added: ["subprocess (stdlib)"]
  patterns: ["Typer CLI command", "FIPS-to-abbreviation dict lookup", "Docker entrypoint initdb pattern"]
key_files:
  created:
    - src/civpulse_geo/cli/__init__.py (setup-tiger command, FIPS_TO_ABBREV, _resolve_state, TIGER_EXTENSIONS)
    - tests/test_tiger_cli.py
    - scripts/20_tiger_setup.sh
  modified:
    - docker-compose.yml
decisions:
  - "setup-tiger installs extensions only in Docker init script — data download (~200MB) deferred to manual setup-tiger CLI invocation"
  - "TextClause args inspected via .text attribute in tests (not str(call)) for CREATE EXTENSION counting"
  - "test_import_cli.py failures (10 tests) confirmed pre-existing (missing data fixture); deferred to future plan"
metrics:
  duration_seconds: 210
  completed_date: "2026-03-24"
  tasks_completed: 2
  files_created: 3
  files_modified: 2
---

# Phase 09 Plan 02: setup-tiger CLI and Docker Init Script Summary

**One-liner:** FIPS-aware setup-tiger CLI installs 4 Tiger extensions + generates Loader_Generate_Script() output, with Docker /docker-entrypoint-initdb.d/ auto-install on first container startup.

## What Was Built

### Task 1: setup-tiger CLI command with FIPS conversion (TDD)

Added to `src/civpulse_geo/cli/__init__.py`:

- `FIPS_TO_ABBREV` — 51-entry dict mapping 2-digit FIPS codes to 2-letter state abbreviations (50 states + DC)
- `ABBREV_TO_FIPS` — reverse lookup dict
- `TIGER_EXTENSIONS` — ordered list of 4 required PostGIS extensions
- `_resolve_state(value)` — converts FIPS codes or abbreviations (case-insensitive) to uppercase abbreviation; returns None for unknowns
- `setup_tiger` command — Typer CLI entry point registered as `setup-tiger`; resolves states, installs 4 extensions via `CREATE EXTENSION IF NOT EXISTS`, calls `Loader_Generate_Script(ARRAY[:state], 'sh')` per state, executes result via subprocess

Created `tests/test_tiger_cli.py` with 23 tests across two classes:
- `TestFipsConversion` — spot checks, 51-entry count, FIPS/abbreviation/case/unknown scenarios
- `TestSetupTigerCLI` — unknown FIPS exit 1, 4-extension count, fuzzystrmatch/postgis_tiger_geocoder presence, Loader_Generate_Script called with abbreviation not FIPS, multi-state processing, lowercase abbreviation acceptance

### Task 2: Docker init script and docker-compose.yml update

Created `scripts/20_tiger_setup.sh` (executable):
- Uses `/docker-entrypoint-initdb.d/` pattern (auto-runs on first PostgreSQL initdb)
- Installs all 4 Tiger extensions via psql heredoc
- Uses `$POSTGRES_USER` / `$POSTGRES_DB` env vars from Docker environment
- `set -e` and `ON_ERROR_STOP=1` for safe failure handling
- Extensions only — no data loading (user runs `docker compose exec db geo-import setup-tiger 13` separately)

Updated `docker-compose.yml`:
- Added `./scripts/20_tiger_setup.sh:/docker-entrypoint-initdb.d/20_tiger_setup.sh` volume mount to `db` service
- Retained `postgres_data` volume and healthcheck configuration

## Verification Results

1. `uv run pytest tests/test_tiger_cli.py -x -q` — 23 passed
2. `uv run pytest tests/ -q` — 276 passed, 2 skipped (10 pre-existing failures in test_import_cli.py; unrelated to this plan)
3. `grep -n "setup-tiger" src/civpulse_geo/cli/__init__.py` — command registered at line 74
4. `grep -n "FIPS_TO_ABBREV" src/civpulse_geo/cli/__init__.py` — dict at line 32
5. `grep -n "Loader_Generate_Script" src/civpulse_geo/cli/__init__.py` — wired at line 115
6. `test -x scripts/20_tiger_setup.sh` — executable confirmed
7. `grep "docker-entrypoint-initdb.d" docker-compose.yml` — mount confirmed

## Commits

| Hash | Message |
|------|---------|
| 807fba6 | test(09-02): add failing tests for setup-tiger CLI command |
| ff26721 | feat(09-02): implement setup-tiger CLI command with FIPS conversion |
| fe19d25 | feat(09-02): add Docker init script and mount into docker-compose.yml |

## Deviations from Plan

### Out-of-Scope Pre-existing Test Failures (logged, not fixed)

**Discovered during:** Full test suite runs (Tasks 1 and 2)
**Issue:** `tests/test_import_cli.py` — 10 tests fail due to missing `data/SAMPLE_Address_Points.geojson` fixture
**Action:** Confirmed pre-existing by stashing changes and re-running. Logged to `deferred-items.md`. Not fixed (out of scope per deviation rules).

### Auto-fixed: TextClause mock inspection pattern

**Rule 1 - Bug / Rule applied during testing**
**Found during:** Task 1 GREEN phase
**Issue:** The test counted `CREATE EXTENSION` calls by checking `str(call)` — but SQLAlchemy `text()` objects appear as `<sqlalchemy.sql.elements.TextClause object at 0x...>` in string representation, so the SQL text wasn't visible
**Fix:** Updated tests to inspect `call[0][0].text` attribute on the TextClause object for accurate SQL content matching
**Files modified:** `tests/test_tiger_cli.py`

## Self-Check: PASSED

- `src/civpulse_geo/cli/__init__.py` — exists, contains `FIPS_TO_ABBREV`, `_resolve_state`, `setup-tiger` command
- `tests/test_tiger_cli.py` — exists, 23 tests pass
- `scripts/20_tiger_setup.sh` — exists, executable, contains all 4 CREATE EXTENSION statements
- `docker-compose.yml` — contains `docker-entrypoint-initdb.d/20_tiger_setup.sh`
- Commits 807fba6, ff26721, fe19d25 confirmed in git log
