---
phase: 24-osm-data-pipeline-docker-compose-sidecars
plan: 03
subsystem: cli
tags: [typer, httpx, osm, geofabrik, pbf, retry, backoff]

# Dependency graph
requires:
  - phase: 24-osm-data-pipeline-docker-compose-sidecars-01
    provides: test scaffold structure (test_osm_cli.py stubs, data/osm gitignore)
provides:
  - osm-download Typer CLI command with streaming httpx download, idempotency, and retry/backoff
  - tests/test_osm_cli.py with 4 passing tests for PIPE-01 and 8 xfail stubs for plans 04/05
affects:
  - 24-04 (osm-import-nominatim, osm-import-tiles, osm-build-valhalla commands depend on PBF download)
  - 24-05 (osm-pipeline orchestration calls osm-download as first step)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - httpx.stream for streaming binary file downloads with chunked writes
    - Exponential backoff retry loop (2^attempt seconds) with max 3 attempts
    - monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf) for isolating CLI path constants in tests

key-files:
  created:
    - tests/test_osm_cli.py
  modified:
    - src/civpulse_geo/cli/__init__.py

key-decisions:
  - "osm-download uses module-level PBF_PATH constant so tests can monkeypatch it without touching disk"
  - "Parallel agent created full test file (not just 4 tests) since 24-01 file did not exist in worktree"

patterns-established:
  - "Pattern 1: httpx.stream with iter_bytes(chunk_size=8192) for streaming PBF downloads"
  - "Pattern 2: exponential backoff with 2**attempt sleep and max-attempts guard"

requirements-completed: [PIPE-01]

# Metrics
duration: 3min
completed: 2026-04-04
---

# Phase 24 Plan 03: osm-download CLI Command Summary

**Georgia OSM PBF downloader Typer command with streaming httpx, skip-if-exists idempotency, --force flag, and 3-attempt exponential backoff — 4 unit tests passing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-04T15:43:36Z
- **Completed:** 2026-04-04T15:46:30Z
- **Tasks:** 2 (combined into 1 commit since test file was created alongside implementation)
- **Files modified:** 2

## Accomplishments
- Implemented `osm-download` Typer command satisfying PIPE-01
- Streaming httpx download to `data/osm/georgia-latest.osm.pbf` with chunked writes
- Idempotency: skip if file exists (with `--force` override)
- Retry/backoff: 3 attempts, exponential wait (1s, 2s, 4s) on any exception
- Created `tests/test_osm_cli.py` with 4 passing tests + 8 xfail stubs for future plans

## Task Commits

1. **Task 1+2: Implement osm-download command and tests** - `06e40fc` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified
- `src/civpulse_geo/cli/__init__.py` - Added `import httpx`, OSM constants, `osm_download` command
- `tests/test_osm_cli.py` - Created with TestOsmDownload (3 tests), TestOsmDownloadRetry (1 test), and 8 xfail stubs for plans 04/05

## Decisions Made
- Module-level `PBF_PATH` and `OSM_DATA_DIR` constants allow `monkeypatch.setattr` in tests without touching real disk paths
- Parallel agent created the full `tests/test_osm_cli.py` file (plan 24-01 normally creates stubs; since the file was absent from the worktree, both stubs and implementations were created together)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created complete test file instead of removing xfail stubs**
- **Found during:** Task 2 setup (test file inspection)
- **Issue:** `tests/test_osm_cli.py` did not exist in the worktree (parallel plan 24-01 had not yet merged). Plan 24-03 expected to remove xfail markers from existing stubs.
- **Fix:** Created the full test file with the 4 download tests implemented directly (no xfail) plus 8 xfail stubs for plans 04/05 — equivalent end state to plan's intent
- **Files modified:** tests/test_osm_cli.py (created)
- **Verification:** All 4 tests pass; ruff lint clean
- **Committed in:** 06e40fc

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** No scope creep. End state identical to plan intent — 4 tests pass, 8 stubs remain xfail.

## Issues Encountered
- Pre-existing test failures in `tests/test_import_cli.py` (missing data/SAMPLE_Address_Points.geojson fixture) and `tests/test_load_oa_cli.py::test_parse_oa_feature_empty_strings_to_none` — both confirmed pre-existing before our commit, out of scope.

## Known Stubs
None — all 4 TestOsmDownload/TestOsmDownloadRetry tests are fully implemented. Remaining 8 xfail tests in the file are intentional stubs for plans 04/05.

## Next Phase Readiness
- PIPE-01 complete: `osm-download` command available for pipeline orchestration
- Plans 04/05 can implement their commands and remove xfail markers from TestOsmImportNominatim, TestOsmImportTiles, TestOsmBuildValhalla, and TestOsmPipeline
- The `data/osm/` directory and `.gitignore` patterns from plan 24-01 should be applied before running the actual download in production

---
*Phase: 24-osm-data-pipeline-docker-compose-sidecars*
*Completed: 2026-04-04*
