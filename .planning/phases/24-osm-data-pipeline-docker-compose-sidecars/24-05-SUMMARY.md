---
phase: 24-osm-data-pipeline-docker-compose-sidecars
plan: 05
subsystem: cli
tags: [typer, docker, subprocess, osm, pipeline, idempotency, testing]

# Dependency graph
requires:
  - phase: 24-osm-data-pipeline-docker-compose-sidecars-03
    provides: osm-download command, PBF_PATH constant
  - phase: 24-osm-data-pipeline-docker-compose-sidecars-04
    provides: osm-import-nominatim, osm-import-tiles, osm-build-valhalla, _run_docker_cmd helper
provides:
  - osm-pipeline unified Typer CLI command (PIPE-05)
  - _check_pbf_exists idempotency helper
  - _check_nominatim_populated idempotency helper
  - _check_tiles_populated idempotency helper
  - _check_valhalla_built idempotency helper
  - 5 passing unit tests in TestOsmPipeline (all xfail markers removed)
affects:
  - Manual Docker Compose stack verification (T3 checkpoint — awaiting operator sign-off)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Continue-on-failure orchestration with per-step OK/FAIL/SKIP result dict (D-12)
    - Idempotency via check_fn lambdas before each pipeline step (D-14)
    - --force flag bypasses all idempotency checks for full re-run
    - subprocess.run check=False for idempotency probes (non-destructive reads)
    - subprocess.run check=True via _invoke for actual step execution

key-files:
  created: []
  modified:
    - src/civpulse_geo/cli/__init__.py
    - tests/test_osm_cli.py

key-decisions:
  - "osm-pipeline delegates to sibling commands via subprocess (['uv', 'run', 'geo-import', cmd_name]) so each step benefits from existing command error handling and output"
  - "Idempotency checks use subprocess.run check=False (never raise) for safety — check_fn failures silently default to already_done=False"
  - "_check_tiles_populated uses COUNT(*) SQL query via docker compose exec so it works without psql installed on host"

requirements-completed: [PIPE-05, INFRA-01, INFRA-02, INFRA-03]

# Metrics
duration: 2min
completed: 2026-04-04
---

# Phase 24 Plan 05: osm-pipeline Unified Orchestrator Summary

**Unified `osm-pipeline` CLI command with 4-step continue-on-failure orchestration, idempotency checks, and --force bypass — PIPE-05 complete; Docker stack verification pending operator sign-off**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-04T15:53:26Z
- **Completed:** 2026-04-04T15:55:20Z
- **Tasks:** 2 (T3 is checkpoint:human-verify — awaiting operator)
- **Files modified:** 2

## Accomplishments

- Implemented `osm-pipeline` command orchestrating all 4 steps in order: download -> import-nominatim -> import-tiles -> build-valhalla (PIPE-05)
- Added 4 idempotency check helpers: `_check_pbf_exists`, `_check_nominatim_populated`, `_check_tiles_populated`, `_check_valhalla_built` (D-14)
- Continue-on-failure: FAIL a step, print re-run hint, continue to next step, report final summary (D-12)
- --force flag bypasses all idempotency check functions
- Replaced all 5 `xfail` stubs in `TestOsmPipeline` with real test implementations; 12/12 test_osm_cli.py tests pass

## Task Commits

1. **Task 1: Add osm-pipeline unified command with idempotency checks** - `d5597af` (feat)
2. **Task 2: Implement TestOsmPipeline tests (remove 5 xfail markers)** - `889440e` (test)

T3 (docker compose manual verification) is a checkpoint:human-verify gate — not executed by automation.

## Files Created/Modified

- `src/civpulse_geo/cli/__init__.py` — Added 4 `_check_*` idempotency helpers and `osm_pipeline` command (122 lines added)
- `tests/test_osm_cli.py` — Replaced 5 xfail stubs with real TestOsmPipeline implementations; added `import subprocess` (70 insertions, 11 deletions)

## Decisions Made

- `osm-pipeline` delegates to sibling commands via subprocess so each step reuses existing command error handling and output formatting
- Idempotency check functions use `check=False` (non-raising) subprocess.run calls — if the docker exec fails (container not running), the check silently returns False and the step runs normally
- `_check_tiles_populated` uses a COUNT(*) SQL query via `docker compose exec` so idempotency works without psql on the host machine

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Pre-existing ruff lint warnings in unrelated test files (test_cascade.py, test_tiger_cli.py, etc.) — confirmed pre-existing, out of scope per deviation rules scope boundary.
- Pre-existing e2e test failures in `tests/e2e/` (require live API server) — confirmed pre-existing before our changes per 24-04-SUMMARY.md.

## Known Stubs

None — T3 is intentionally a manual checkpoint gate (docker compose bring-up cannot be automated). All 5 pipeline unit tests are fully implemented.

## Checkpoint Reached: T3

Task 3 is `type="checkpoint:human-verify"` — awaiting operator to run 8 docker compose verification steps and report "approved" or failing step details.

## Next Phase Readiness

- All 5 osm-* CLI commands implemented and tested (PIPE-01 through PIPE-05)
- Phase 24 plan 05 T1/T2 complete; T3 awaiting manual Docker stack verification
- After operator approval, phase 24 is complete and phase 25 planning can begin

---
*Phase: 24-osm-data-pipeline-docker-compose-sidecars*
*Completed: 2026-04-04*
