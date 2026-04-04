---
phase: 24-osm-data-pipeline-docker-compose-sidecars
plan: 02
subsystem: infra
tags: [docker-compose, osm, nominatim, valhalla, tile-server, postgis, pydantic-settings]

# Dependency graph
requires: []
provides:
  - Four OSM sidecar services under --profile osm (osm-postgres, nominatim, tile-server, valhalla)
  - osm-postgres init script installing PostGIS/hstore/postgis_topology extensions
  - Settings fields for OSM service URLs (osm_nominatim_url, osm_tile_url, osm_valhalla_url)
affects: [24-03, 24-04, 24-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Docker Compose --profile osm gates all OSM services (mirrors existing --profile llm pattern)
    - osm-postgres isolated from civpulse_geo via separate POSTGRES_DB=nominatim and osm_postgres_data volume
    - Nominatim DSN uses libpq format (pgsql:host=...;...) not sqlalchemy URL
    - tile-server uses own internal PostgreSQL (not osm-postgres) via osm_tile_data volume
    - valhalla_tiles named volume persists routing graph across container restarts

key-files:
  created:
    - scripts/30_osm_setup.sh
    - .planning/phases/24-osm-data-pipeline-docker-compose-sidecars/24-02-SUMMARY.md
  modified:
    - docker-compose.yml
    - src/civpulse_geo/config.py

key-decisions:
  - "All 4 OSM services gated under profiles: [osm] so docker compose up without --profile osm starts only api/db"
  - "tile-server uses its own internal PostgreSQL (db: gis, user: renderer) — does NOT connect to osm-postgres"
  - "Nominatim DSN uses libpq format pgsql:host=osm-postgres;... (not postgresql+asyncpg://) per mediagis/nominatim image requirements"
  - "valhalla_tiles named volume persists routing graph so Valhalla builds tiles only once (D-02)"
  - "nominatim start_period: 600s because initial PBF import can take 5-10+ minutes on first startup"

patterns-established:
  - "Pattern: OSM sidecar isolation — osm-postgres hosts nominatim DB, tile-server has own internal PostgreSQL"
  - "Pattern: libpq DSN format for Nominatim service connection string"
  - "Pattern: --profile osm gates all 4 OSM services as a unit"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03]

# Metrics
duration: 15min
completed: 2026-04-04
---

# Phase 24 Plan 02: OSM Docker Compose Sidecars Summary

**Four OSM sidecar services (Nominatim, Valhalla, tile-server, osm-postgres) added under `--profile osm` with isolated PostgreSQL, init script, and config.py URL settings**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-04T15:29:00Z
- **Completed:** 2026-04-04T15:44:32Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Created `scripts/30_osm_setup.sh` init script (mode 755) installing postgis, hstore, postgis_topology on the nominatim database
- Added 4 OSM services to docker-compose.yml under `--profile osm`: osm-postgres, nominatim, tile-server, valhalla with 5 named volumes
- Added 3 OSM URL settings to config.py: osm_nominatim_url, osm_tile_url, osm_valhalla_url

## Task Commits

Each task was committed atomically:

1. **Task 1: Create osm-postgres init script** - `60ff6bc` (feat)
2. **Task 2: Add 4 OSM services to docker-compose.yml** - `f2d5a4f` (feat)
3. **Task 3: Add OSM service URL settings to config.py** - `aa7e6d6` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `scripts/30_osm_setup.sh` - PostGIS/hstore/postgis_topology init script for osm-postgres container
- `docker-compose.yml` - 4 new OSM services + 5 named volumes under profiles: [osm]
- `src/civpulse_geo/config.py` - 3 new OSM service URL settings with docker-compose service name defaults

## Decisions Made
- All 4 OSM services gated under `profiles: [osm]` so default `docker compose up` starts only api/db/ollama
- tile-server intentionally does NOT connect to osm-postgres (uses own internal PostgreSQL via osm_tile_data volume)
- Nominatim DSN uses libpq format `pgsql:host=...` (not SQLAlchemy URL) per mediagis/nominatim image requirements
- valhalla_tiles named volume ensures routing graph persists across container restarts (D-02)
- nominatim `start_period: 600s` accounts for initial PBF import latency (5-10+ minutes on first startup)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing ruff lint errors in `scripts/seed.py` (2 errors: unused import and unused variable) — out of scope for this plan. Only `src/civpulse_geo/config.py` and `scripts/30_osm_setup.sh` are in scope; both pass all checks. 490 existing tests pass; 2 test failures are pre-existing fixture file issues (missing `data/SAMPLE_Address_Points.geojson` and `test_load_oa_cli.py` fixture) unrelated to this plan.

## User Setup Required

None - no external service configuration required for this plan. OSM data (PBF files) loading is handled by Plans 03-05.

## Next Phase Readiness

- Docker Compose infrastructure ready for OSM data loading (Plans 03-05)
- `data/osm/` directory must exist before starting OSM profile services (Plans 03-05 will create it)
- `docker compose --profile osm up -d osm-postgres` will initialize nominatim DB extensions on first start
- Plans 03-05 can now implement CLI commands to download/import PBF data using these service URLs

## Self-Check: PASSED

All files and commits verified:
- scripts/30_osm_setup.sh: FOUND
- docker-compose.yml: FOUND (modified)
- src/civpulse_geo/config.py: FOUND (modified)
- 24-02-SUMMARY.md: FOUND
- Commit 60ff6bc (Task 1): FOUND
- Commit f2d5a4f (Task 2): FOUND
- Commit aa7e6d6 (Task 3): FOUND
- Commit c95501a (docs): FOUND

---
*Phase: 24-osm-data-pipeline-docker-compose-sidecars*
*Completed: 2026-04-04*
