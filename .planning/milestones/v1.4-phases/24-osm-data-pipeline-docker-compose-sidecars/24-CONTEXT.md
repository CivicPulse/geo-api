# Phase 24: OSM Data Pipeline & Docker Compose Sidecars - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Operator can download the Georgia OSM PBF extract and import it into all three OSM services (Nominatim, tile server, Valhalla) via CLI commands. All three sidecar services plus a dedicated osm-postgres instance run locally via Docker Compose under a single `--profile osm` flag. This phase establishes the data foundation and local dev environment for all subsequent v1.4 phases.

**Does NOT include:** FastAPI proxy endpoints (Phase 25), cascade provider integration (Phase 26), routing endpoints (Phase 27), or K8s manifests (Phase 28).

</domain>

<decisions>
## Implementation Decisions

### Docker Compose Service Topology
- **D-01:** All three OSM sidecar services (Nominatim, tile server, Valhalla) and osm-postgres are opt-in via `--profile osm` — consistent with the existing `--profile llm` pattern for Ollama.
- **D-02:** A single shared `osm-postgres` container (postgis/postgis image) hosts two isolated databases: `nominatim` and `osm_tiles`. Databases are separate DBs on the same instance, not just separate schemas.
- **D-03:** Valhalla is under the same `--profile osm` as Nominatim and the tile server — no separate `--profile routing`.
- **D-04:** The `osm-postgres` container uses an init script mounted to `/docker-entrypoint-initdb.d/` to create both databases and PostGIS extensions — same pattern as the existing `20_tiger_setup.sh`.

### CLI Command Design
- **D-05:** New commands are flat Typer commands alongside existing ones: `osm-pipeline` (unified), `osm-download`, `osm-import-nominatim`, `osm-import-tiles`, `osm-build-valhalla`. No Typer subgroups — consistent with existing CLI surface.
- **D-06:** Individual import commands shell out to `docker compose exec` / `docker exec` for container-native operations. The imports are Docker operations, not Python library calls.
- **D-07:** PBF download destination is host-mounted `./data/osm/georgia-latest.osm.pbf` — visible to operators, mountable into containers. Consistent with existing `./data/` directory pattern.
- **D-08:** Progress reporting uses Rich stage progress with elapsed time per stage — consistent with existing Rich progress bars in `load-oa` and `load-nad` commands.

### Tile Server Stack
- **D-09:** Use `overv/openstreetmap-tile-server` for raster tile serving. Renders PNG tiles on-demand from PostGIS via Mapnik/renderd. Directly satisfies TILE-01/02/03 raster PNG requirement without frontend changes.
- **D-10:** osm2pgsql imports PBF into the `osm_tiles` database on the shared `osm-postgres` instance.
- **D-11:** Tilemaker + Martin (vector tiles) is deferred to a future backlog item for vector map support (requires Leaflet → MapLibre GL JS frontend migration).

### Data Pipeline Error Handling
- **D-12:** Unified pipeline command continues after a step failure and reports results at the end. Tile import and Valhalla graph build don't depend on Nominatim — no reason to block them. Exit code reflects overall status (non-zero if any step failed). Summary includes re-run command for failed steps.
- **D-13:** PBF download retries up to 3 times with exponential backoff for transient network failures.
- **D-14:** Unified command is idempotent — checks for existing PBF, populated Nominatim DB, osm_tiles tables, and Valhalla graph before each step. Skips completed steps with a note. `--force` flag forces re-import of all steps.

### Claude's Discretion
- Container image tags and version pinning for Nominatim, tile server, Valhalla
- osm-postgres resource limits (mem_limit) for Docker Compose
- Specific healthcheck commands and intervals for each OSM service
- osm2pgsql import flags (slim mode, cache size, etc.)
- Nominatim import-phase PostgreSQL tuning (session-level `ALTER DATABASE SET` parameters)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research
- `.planning/research/SUMMARY.md` — Overall v1.4 architecture, recommended stack, phase ordering rationale
- `.planning/research/PITFALLS.md` — Critical pitfalls: Nominatim DB isolation (Pitfall 1), non-resumable import (Pitfall 2), Valhalla graph rebuild (Pitfall 3), import tuning starvation (Pitfall 4), tile stack complexity (Pitfall 5)
- `.planning/research/ARCHITECTURE.md` — Component architecture and service communication patterns
- `.planning/research/FEATURES.md` — Feature specifications and acceptance criteria
- `.planning/research/STACK.md` — Technology stack details and version requirements

### Requirements
- `.planning/REQUIREMENTS.md` — PIPE-01 through PIPE-05 (data pipeline), INFRA-01 through INFRA-03 (sidecar services)

### Existing Infrastructure
- `docker-compose.yml` — Current service topology (db, ollama, api) — extend with osm-postgres + 3 sidecars under `--profile osm`
- `scripts/20_tiger_setup.sh` — Reference pattern for osm-postgres init script
- `src/civpulse_geo/cli/__init__.py` — Existing CLI commands and Typer app structure

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Typer CLI app** (`src/civpulse_geo/cli/__init__.py`): Flat command structure with Rich progress bars. New `osm-*` commands plug in directly.
- **Rich progress** (`rich.progress`): Already imported and used in `load-oa`, `load-nad` commands for long-running imports.
- **Docker Compose** (`docker-compose.yml`): Profile pattern established with `ollama` service using `profiles: [llm]`. OSM services follow same pattern.
- **Init script pattern** (`scripts/20_tiger_setup.sh`): Existing `/docker-entrypoint-initdb.d/` script for Tiger PostGIS setup. Reference for `30_osm_setup.sh`.
- **config/settings**: Application settings via Pydantic — may need new env vars for OSM service URLs.

### Established Patterns
- **Docker Compose profiles**: Optional heavy services use `profiles:` key — devs opt in with `--profile <name>`
- **CLI subprocess calls**: `subprocess.run` used in existing CLI for shell operations
- **Host-mounted data**: `./data/` directory used for GIS data files, mounted into containers
- **Healthchecks**: Every service in docker-compose.yml has a healthcheck definition

### Integration Points
- `docker-compose.yml` — Add `osm-postgres`, `nominatim`, `tile-server`, `valhalla` services
- `scripts/` — Add osm-postgres init script
- `src/civpulse_geo/cli/__init__.py` — Add `osm-pipeline`, `osm-download`, `osm-import-nominatim`, `osm-import-tiles`, `osm-build-valhalla` commands
- `src/civpulse_geo/config.py` — Add OSM-related settings (service URLs, PBF path)
- `.gitignore` — Ensure `data/osm/` PBF files are gitignored

</code_context>

<specifics>
## Specific Ideas

- Unified pipeline output should show checkmark/cross per step with re-run command for failures (see D-12 preview mockup from discussion)
- PBF stored at `./data/osm/georgia-latest.osm.pbf` specifically — not a generic path

</specifics>

<deferred>
## Deferred Ideas

- **Vector tile serving (Tilemaker + Martin)** — Future backlog item. Requires Leaflet → MapLibre GL JS frontend migration in voter-web/run-api. Lighter infrastructure, better K8s fit, but changes the frontend contract. Add as FUTURE-04 enhancement when ready.

</deferred>

---

*Phase: 24-osm-data-pipeline-docker-compose-sidecars*
*Context gathered: 2026-04-04*
