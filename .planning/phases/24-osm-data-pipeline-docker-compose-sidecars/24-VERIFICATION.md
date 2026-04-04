---
phase: 24-osm-data-pipeline-docker-compose-sidecars
verified: 2026-04-04T17:00:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Run full end-to-end osm-pipeline on a clean environment (empty volumes)"
    expected: "PBF downloads, nominatim imports in 60-120 min, tiles import, valhalla graph builds, all 3 sidecars serve requests"
    why_human: "Requires 3GB+ network download, 60-120 min real wall-clock for Nominatim import, and Docker daemon with full internet access. Cannot be automated in CI."
---

# Phase 24: OSM Data Pipeline & Docker Compose Sidecars — Verification Report

**Phase Goal:** Operator can download the Georgia OSM PBF and import it into all three OSM services via CLI; all three sidecar services (Nominatim, tile server, Valhalla) run locally via Docker Compose
**Verified:** 2026-04-04T17:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Architectural Context

During T3 checkpoint, manual Docker verification revealed that both `mediagis/nominatim:5.2` and `overv/openstreetmap-tile-server:2.3.0` bundle their own internal PostgreSQL. The originally planned `osm-postgres` shared service (D-02) was superseded and dropped in commit `f5060fd`. Each OSM sidecar now uses its own bundled PG with isolation from `civpulse_geo` preserved via separate named volumes. This is the correct final state and all verification below reflects it.

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                         | Status     | Evidence                                                                                        |
|----|-----------------------------------------------------------------------------------------------|------------|-------------------------------------------------------------------------------------------------|
| 1  | `osm-download` CLI command is registered and downloads Georgia PBF with retry/idempotency    | VERIFIED   | `uv run geo-import osm-download --help` shows command; 4 unit tests pass                       |
| 2  | `osm-import-nominatim` CLI command is registered and triggers nominatim container bring-up   | VERIFIED   | `uv run geo-import osm-import-nominatim --help` shows command; test verifies docker compose up |
| 3  | `osm-import-tiles` CLI command is registered and invokes tile-server import with PBF mount   | VERIFIED   | `uv run geo-import osm-import-tiles --help` shows command; test verifies docker compose run     |
| 4  | `osm-build-valhalla` CLI command is registered and invokes valhalla graph build              | VERIFIED   | `uv run geo-import osm-build-valhalla --help` shows command; test verifies docker compose run   |
| 5  | `osm-pipeline` CLI command orchestrates all 4 steps with idempotency and continue-on-failure | VERIFIED   | `uv run geo-import osm-pipeline --help` shows command; 5 unit tests pass                       |
| 6  | All 3 OSM sidecars (nominatim, tile-server, valhalla) declared under `--profile osm`         | VERIFIED   | `docker compose --profile osm config --services` lists: api, db, nominatim, tile-server, valhalla |
| 7  | `docker compose config -q` exits 0 (compose file is valid)                                   | VERIFIED   | Command confirmed exits 0                                                                       |
| 8  | `osm-postgres` service is absent (architectural refactor — each sidecar uses bundled PG)     | VERIFIED   | Service not present in docker-compose.yml; only referenced in explanatory comments             |

**Score:** 8/8 truths verified

---

### Required Artifacts

| Artifact                                   | Expected                                      | Status     | Details                                                                                   |
|--------------------------------------------|-----------------------------------------------|------------|-------------------------------------------------------------------------------------------|
| `src/civpulse_geo/cli/__init__.py`         | 5 osm-* Typer commands + pipeline helpers     | VERIFIED   | Lines 1215-1465; all 5 `@app.command("osm-*")` decorators present; `_run_docker_cmd`, `_check_*` helpers present |
| `tests/test_osm_cli.py`                    | 12 passing unit tests, 0 xfail stubs          | VERIFIED   | 12/12 PASSED; `grep -c "pytest.mark.xfail"` returns 0; all stubs replaced                |
| `docker-compose.yml`                       | 3 OSM sidecar services under profiles: [osm]  | VERIFIED   | nominatim (line 76), tile-server (line 100), valhalla (line 124) — all `profiles: [osm]`  |
| `src/civpulse_geo/config.py`               | 3 OSM URL settings                            | VERIFIED   | `osm_nominatim_url`, `osm_tile_url`, `osm_valhalla_url` at lines 54-56                   |
| `data/osm/.gitkeep`                        | Tracked directory marker                      | VERIFIED   | File exists; `git check-ignore data/osm/.gitkeep` exits 1 (not ignored)                  |
| `.gitignore`                               | PBF ignore patterns                           | VERIFIED   | `git check-ignore data/osm/georgia-latest.osm.pbf` exits 0 and echoes path               |

---

### Key Link Verification

| From                                      | To                                                  | Via                              | Status   | Details                                                                              |
|-------------------------------------------|-----------------------------------------------------|----------------------------------|----------|--------------------------------------------------------------------------------------|
| `osm_download` in cli/__init__.py         | `https://download.geofabrik.de/...georgia-latest.osm.pbf` | `httpx.stream` GET              | VERIFIED | Line 1235; `GEORGIA_PBF_URL` constant at line 36                                    |
| `osm_import_nominatim` in cli/__init__.py | `docker compose --profile osm up -d nominatim`      | `subprocess.run` via `_run_docker_cmd` | VERIFIED | Lines 1294-1299; test asserts exact args list                                       |
| `osm_import_tiles` in cli/__init__.py     | `docker compose run --rm tile-server import`        | `subprocess.run` via `_run_docker_cmd` | VERIFIED | Lines 1315-1322; PBF volume mount `:data/region.osm.pbf:ro` present                |
| `osm_build_valhalla` in cli/__init__.py   | `docker compose run --rm valhalla`                  | `subprocess.run` via `_run_docker_cmd` | VERIFIED | Lines 1333-1343; all 4 env flags (`force_rebuild=True`, etc.) present               |
| `osm_pipeline` in cli/__init__.py         | 4 sibling commands via `_invoke`                    | `subprocess.run ["uv","run","geo-import", cmd_name]` | VERIFIED | Lines 1417-1430; step list wires all 4 commands with idempotency check functions   |
| `docker-compose.yml nominatim`            | `./data/osm` bind mount                             | `volumes: - ./data/osm:/nominatim/pbf` | VERIFIED | Line 87; NOT `:ro` (correctly removed per T3 fix — nominatim chowns on startup)    |
| `docker-compose.yml tile-server`          | `./data/osm` bind mount                             | `volumes: - ./data/osm:/data/osm:ro` | VERIFIED | Line 110                                                                            |
| `docker-compose.yml valhalla`             | `./data/osm` bind mount                             | `volumes: - ./data/osm:/custom_files/pbf:ro` | VERIFIED | Line 138                                                                           |

---

### Data-Flow Trace (Level 4)

Not applicable — phase produces CLI tools and Docker Compose configuration, not components that render dynamic data from a database.

---

### Behavioral Spot-Checks

| Behavior                                             | Command                                                            | Result                                                           | Status  |
|------------------------------------------------------|--------------------------------------------------------------------|------------------------------------------------------------------|---------|
| All 5 osm-* commands listed in CLI help              | `uv run geo-import --help \| grep osm`                            | 5 commands shown with descriptions                               | PASS    |
| `docker compose config -q` validates compose file    | `docker compose config -q`                                         | Exit 0                                                           | PASS    |
| OSM services listed under --profile osm              | `docker compose --profile osm config --services`                  | api, db, nominatim, tile-server, valhalla                        | PASS    |
| Default profile excludes OSM services                | `docker compose config --services`                                 | Only: api, db                                                    | PASS    |
| All 12 unit tests pass                               | `uv run pytest tests/test_osm_cli.py -v`                          | 12 passed in 0.08s                                               | PASS    |
| Ruff lint clean on phase 24 files                    | `uv run ruff check src/civpulse_geo/cli/__init__.py src/civpulse_geo/config.py tests/test_osm_cli.py` | All checks passed | PASS    |
| PBF path gitignored                                  | `git check-ignore data/osm/georgia-latest.osm.pbf`               | Path echoed, exit 0                                              | PASS    |
| .gitkeep tracked (not gitignored)                    | `git check-ignore data/osm/.gitkeep`                              | Exit 1 (not ignored)                                             | PASS    |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                  | Status     | Evidence                                                                 |
|-------------|------------|------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------|
| PIPE-01     | Plan 03    | Operator can download Georgia OSM PBF via CLI                                | SATISFIED  | `osm-download` command at line 1215; httpx streaming + retry; 4 tests pass |
| PIPE-02     | Plan 04    | Operator can import PBF into Nominatim database via CLI                      | SATISFIED  | `osm-import-nominatim` at line 1279; `docker compose --profile osm up -d nominatim`; 1 test passes |
| PIPE-03     | Plan 04    | Operator can import PBF into tile server's PostGIS via CLI                   | SATISFIED  | `osm-import-tiles` at line 1302; `docker compose run --rm tile-server import` with PBF volume mount; 1 test passes |
| PIPE-04     | Plan 04    | Operator can build Valhalla routing graph from PBF via CLI                   | SATISFIED  | `osm-build-valhalla` at line 1325; `docker compose run --rm valhalla` with force_rebuild env; 1 test passes |
| PIPE-05     | Plan 05    | Operator can run single unified CLI command for all imports                  | SATISFIED  | `osm-pipeline` at line 1397; 4-step orchestration with idempotency + continue-on-failure; 5 tests pass |
| INFRA-01    | Plan 02    | Nominatim runs as Docker Compose sidecar with dedicated PostgreSQL           | SATISFIED  | nominatim service at line 76; bundled internal PG via nominatim_data volume; profiles: [osm] |
| INFRA-02    | Plan 02    | Valhalla runs as Docker Compose sidecar with pre-built graph on persistent volume | SATISFIED | valhalla service at line 124; valhalla_tiles volume; profiles: [osm]   |
| INFRA-03    | Plan 02    | Tile server runs as Docker Compose sidecar                                   | SATISFIED  | tile-server service at line 100; osm_tile_data + osm_tile_cache volumes; profiles: [osm] |

All 8 requirements satisfied. No orphaned requirements.

---

### Anti-Patterns Found

No blockers or warnings found.

| File                                        | Pattern Checked                        | Finding                      | Severity |
|---------------------------------------------|----------------------------------------|------------------------------|----------|
| `src/civpulse_geo/cli/__init__.py`          | TODO/FIXME/placeholder                 | None found                   | —        |
| `src/civpulse_geo/cli/__init__.py`          | Empty return stubs                     | None found                   | —        |
| `tests/test_osm_cli.py`                     | xfail markers remaining                | 0 remaining (all removed)    | —        |
| `docker-compose.yml`                        | osm-postgres service present           | Absent (correctly removed)   | —        |
| `docker-compose.yml`                        | nominatim `:ro` bind mount (T3 bug)    | Absent (correctly fixed)     | —        |

---

### Human Verification Required

#### 1. End-to-End Pipeline on Clean Environment

**Test:** On a machine with Docker + internet access and empty OSM volumes, run: `uv run geo-import osm-pipeline`

**Expected:** Command downloads georgia-latest.osm.pbf (~1.5GB), nominatim auto-imports during `docker compose up nominatim` (60-120 min), `osm-import-tiles` invokes `docker compose run --rm tile-server import`, `osm-build-valhalla` builds routing tiles. Final summary shows 4x OK.

**Why human:** Requires 3GB+ network download, 60-120 min real wall-clock for Nominatim PBF import, and Docker daemon with internet egress. Automated CI cannot run this without significant infrastructure. Deferred to a future phase per operator decision documented in 24-05-SUMMARY.md T3 Checkpoint Resolved section.

---

### Gaps Summary

No gaps. All 8 requirements are satisfied. All 5 CLI commands exist, are substantive, and are wired to correct Docker invocations. All 12 unit tests pass. Docker Compose configuration is valid with all 3 sidecars under `--profile osm` and `osm-postgres` correctly absent post-refactor.

The single open item — full end-to-end pipeline on a clean environment — is intentionally deferred per operator decision. It cannot be automated without 60-120 minutes of real wall-clock time and a 3GB+ PBF download.

---

_Verified: 2026-04-04T17:00:00Z_
_Verifier: Claude (gsd-verifier)_
