---
phase: 24-osm-data-pipeline-docker-compose-sidecars
plan: 04
subsystem: cli
tags: [typer, docker, subprocess, nominatim, tile-server, valhalla, osm, testing]

# Dependency graph
requires:
  - phase: 24-osm-data-pipeline-docker-compose-sidecars-03
    provides: osm-download command, PBF_PATH constant, test file scaffold with xfail stubs
provides:
  - osm-import-nominatim Typer CLI command (PIPE-02)
  - osm-import-tiles Typer CLI command (PIPE-03)
  - osm-build-valhalla Typer CLI command (PIPE-04)
  - _run_docker_cmd shared helper with elapsed-time progress (D-08)
  - 3 passing unit tests with mocked subprocess.run
affects:
  - 24-05 (osm-pipeline orchestration calls all three import commands)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - subprocess.run with check=True inside _run_docker_cmd helper for uniform error handling
    - monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf) for isolating path resolution in tile import test
    - TDD RED/GREEN: tests written first against not-yet-implemented commands, then implementation added

key-files:
  created: []
  modified:
    - src/civpulse_geo/cli/__init__.py
    - tests/test_osm_cli.py

key-decisions:
  - "_run_docker_cmd helper centralizes elapsed-time echo and CalledProcessError -> typer.Exit(1) translation"
  - "osm-import-tiles uses docker compose run --rm (not exec) per Pitfall 3; PBF mounted at /data/region.osm.pbf:ro per Pitfall 4"
  - "osm-build-valhalla passes all four env flags (serve_tiles=False, force_rebuild=True, build_admins=False, build_elevation=False) per Pitfall 5"

requirements-completed: [PIPE-02, PIPE-03, PIPE-04]

# Metrics
duration: 5min
completed: 2026-04-04
---

# Phase 24 Plan 04: OSM Import CLI Commands Summary

**Three Docker shell-out commands for Nominatim, tile-server, and Valhalla imports via subprocess.run with TDD-driven subprocess mock tests — PIPE-02/03/04 complete**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-04T15:46:50Z
- **Completed:** 2026-04-04T15:51:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Implemented `osm-import-nominatim` command satisfying PIPE-02 — shells out to `docker compose exec nominatim nominatim import --osm-file /nominatim/pbf/georgia-latest.osm.pbf --threads N`
- Implemented `osm-import-tiles` command satisfying PIPE-03 — shells out to `docker compose run --rm -v {abs_pbf}:/data/region.osm.pbf:ro tile-server import`
- Implemented `osm-build-valhalla` command satisfying PIPE-04 — shells out to `docker compose run --rm` with four env flags
- Added `_run_docker_cmd` shared helper providing consistent elapsed-time progress output (D-08) and unified error handling
- Removed xfail markers from 3 test stubs (TestOsmImportNominatim, TestOsmImportTiles, TestOsmBuildValhalla)
- All 3 tests pass; 5 xfail stubs remain for Plan 05 (TestOsmPipeline)

## Task Commits

1. **Task 1: Add three import CLI commands** - `4b084ae` (feat)
2. **Task 2: Implement import command tests** - `eed17da` (test)

## Files Created/Modified

- `src/civpulse_geo/cli/__init__.py` — Added `_run_docker_cmd` helper + `osm_import_nominatim`, `osm_import_tiles`, `osm_build_valhalla` commands (86 lines added)
- `tests/test_osm_cli.py` — Replaced 3 xfail stubs with real test implementations (46 insertions, 10 deletions)

## Decisions Made

- `_run_docker_cmd` centralizes all docker subprocess invocations — exits 1 on CalledProcessError, echoes elapsed time (D-08)
- Tile import uses `docker compose run --rm` (not `exec`) per Pitfall 3; PBF mounted at `/data/region.osm.pbf:ro` per Pitfall 4
- Valhalla build passes all four env flags (serve_tiles, force_rebuild, build_admins, build_elevation) per Pitfall 5
- TDD flow: tests written first (RED — 3 failures) then implementation added (GREEN — 3 passing)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Pre-existing failures in `tests/e2e/test_cascade_pipeline.py` and `tests/test_import_cli.py` — confirmed pre-existing before our changes, out of scope.

## Known Stubs

None — all 3 TestOsmImport*/TestOsmBuildValhalla tests are fully implemented. 5 xfail stubs in TestOsmPipeline are intentional for Plan 05.

## Self-Check: PASSED

- `src/civpulse_geo/cli/__init__.py` — FOUND (modified)
- `tests/test_osm_cli.py` — FOUND (modified)
- Commit `4b084ae` — FOUND
- Commit `eed17da` — FOUND
- `uv run pytest tests/test_osm_cli.py::TestOsmImportNominatim tests/test_osm_cli.py::TestOsmImportTiles tests/test_osm_cli.py::TestOsmBuildValhalla -v` — 3 PASSED

---
*Phase: 24-osm-data-pipeline-docker-compose-sidecars*
*Completed: 2026-04-04*
