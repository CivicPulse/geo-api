# Phase 24: OSM Data Pipeline & Docker Compose Sidecars - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 24-OSM Data Pipeline & Docker Compose Sidecars
**Areas discussed:** Docker Compose service topology, CLI command design, Tile server stack choice, Data pipeline error handling

---

## Docker Compose Service Topology

### OSM Service Profile

| Option | Description | Selected |
|--------|-------------|----------|
| Profile-based | `--profile osm` opt-in, consistent with Ollama pattern | ✓ |
| Always-on | All OSM services start with plain `docker compose up` | |
| Split profiles | Separate `--profile tiles`, `--profile nominatim`, `--profile routing` | |

**User's choice:** Profile-based (Recommended)
**Notes:** Keeps default startup fast for devs not working on OSM features.

### Database Topology

| Option | Description | Selected |
|--------|-------------|----------|
| Shared osm-postgres | One container, two databases (nominatim, osm_tiles) | ✓ |
| Separate containers | Independent nominatim-db and tiles-db containers | |

**User's choice:** Shared osm-postgres (Recommended)
**Notes:** Lower resource usage, databases are isolated at DB level not just schema.

### Valhalla Profile

| Option | Description | Selected |
|--------|-------------|----------|
| Same --profile osm | All three OSM services under one profile | ✓ |
| Separate --profile routing | Valhalla gets its own profile | |

**User's choice:** Same --profile osm (Recommended)
**Notes:** One flag for the full OSM stack.

### Database Initialization

| Option | Description | Selected |
|--------|-------------|----------|
| Init script in entrypoint | Shell script in /docker-entrypoint-initdb.d/ | ✓ |
| Nominatim manages its own DB | Let mediagis/nominatim handle its own PostgreSQL | |

**User's choice:** Init script in entrypoint (Recommended)
**Notes:** Same pattern as existing 20_tiger_setup.sh.

---

## CLI Command Design

### Command Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Flat commands | osm-pipeline, osm-download, osm-import-nominatim, etc. | ✓ |
| Typer subgroup | `geo-import osm pipeline` nested commands | |
| Single unified command only | One `osm-setup` command for everything | |

**User's choice:** Flat commands (Recommended)
**Notes:** Consistent with existing CLI surface (import, load-oa, load-nad).

### Progress Reporting

| Option | Description | Selected |
|--------|-------------|----------|
| Rich stage progress | Rich console with current stage + elapsed time | ✓ |
| Minimal logging | Loguru log lines only | |
| You decide | Claude picks | |

**User's choice:** Rich stage progress (Recommended)
**Notes:** Consistent with existing Rich progress bars.

### Import Implementation

| Option | Description | Selected |
|--------|-------------|----------|
| Shell out to docker | subprocess calls to docker compose exec | ✓ |
| API-based where possible | Mix of shell-out and API calls | |
| You decide | Claude picks | |

**User's choice:** Shell out to docker (Recommended)
**Notes:** Imports are container-native operations.

### PBF Storage

| Option | Description | Selected |
|--------|-------------|----------|
| Host-mounted ./data/osm/ | PBF on host filesystem, mounted into containers | ✓ |
| Docker named volume | PBF in a Docker managed volume | |

**User's choice:** Host-mounted ./data/osm/ (Recommended)
**Notes:** Visible to operators, consistent with existing ./data/ pattern.

---

## Tile Server Stack Choice

| Option | Description | Selected |
|--------|-------------|----------|
| overv/openstreetmap-tile-server | Classic renderd/mod_tile/Mapnik, raster PNG output | ✓ |
| Tilemaker + Martin | Pre-generated MBTiles, vector tiles, lighter infrastructure | |
| You decide | Claude picks | |

**User's choice:** overv/openstreetmap-tile-server
**Notes:** Directly satisfies raster PNG requirement. User requested a future backlog item for Tilemaker + Martin vector tile approach (requires Leaflet → MapLibre GL JS frontend migration).

---

## Data Pipeline Error Handling

### Error Mode

| Option | Description | Selected |
|--------|-------------|----------|
| Continue + report | Continue after failure, report all results at end | ✓ |
| Stop on first error | Abort entire pipeline on first failure | |
| You decide | Claude picks | |

**User's choice:** Continue + report (Recommended)
**Notes:** Tile import and Valhalla don't depend on Nominatim. Summary includes re-run commands for failed steps.

### PBF Download Retry

| Option | Description | Selected |
|--------|-------------|----------|
| Retry with backoff | Up to 3 retries with exponential backoff | ✓ |
| Fail immediately | Single attempt | |
| You decide | Claude picks | |

**User's choice:** Retry with backoff (Recommended)

### Idempotency

| Option | Description | Selected |
|--------|-------------|----------|
| Skip if data exists | Check for existing data, skip completed steps, --force to override | ✓ |
| Always re-import | Re-run every step regardless | |
| You decide | Claude picks | |

**User's choice:** Skip if data exists (Recommended)
**Notes:** --force flag forces re-import of all steps.

---

## Claude's Discretion

- Container image tags and version pinning
- osm-postgres resource limits
- Healthcheck commands and intervals for OSM services
- osm2pgsql import flags
- Nominatim import-phase PostgreSQL tuning parameters

## Deferred Ideas

- Vector tile serving via Tilemaker + Martin — future backlog item (requires frontend migration to MapLibre GL JS)
