# Phase 24: OSM Data Pipeline & Docker Compose Sidecars - Research

**Researched:** 2026-04-04
**Domain:** OSM data pipeline CLI, Docker Compose sidecar services (Nominatim, tile server, Valhalla), dedicated PostgreSQL for OSM data
**Confidence:** HIGH (core findings verified against official docs and GitHub repos)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** All three OSM sidecar services (Nominatim, tile server, Valhalla) and osm-postgres are opt-in via `--profile osm` — consistent with the existing `--profile llm` pattern for Ollama.
- **D-02:** A single shared `osm-postgres` container (postgis/postgis image) hosts two isolated databases: `nominatim` and `osm_tiles`. Databases are separate DBs on the same instance, not just separate schemas.
- **D-03:** Valhalla is under the same `--profile osm` as Nominatim and the tile server — no separate `--profile routing`.
- **D-04:** The `osm-postgres` container uses an init script mounted to `/docker-entrypoint-initdb.d/` to create both databases and PostGIS extensions — same pattern as the existing `20_tiger_setup.sh`.
- **D-05:** New commands are flat Typer commands alongside existing ones: `osm-pipeline` (unified), `osm-download`, `osm-import-nominatim`, `osm-import-tiles`, `osm-build-valhalla`. No Typer subgroups.
- **D-06:** Individual import commands shell out to `docker compose exec` / `docker exec` for container-native operations. The imports are Docker operations, not Python library calls.
- **D-07:** PBF download destination is host-mounted `./data/osm/georgia-latest.osm.pbf`.
- **D-08:** Progress reporting uses Rich stage progress with elapsed time per stage.
- **D-09:** Use `overv/openstreetmap-tile-server` for raster tile serving.
- **D-10:** osm2pgsql imports PBF into the `osm_tiles` database on the shared `osm-postgres` instance.
- **D-11:** Tilemaker + Martin (vector tiles) is deferred.
- **D-12:** Unified pipeline command continues after a step failure and reports results at end. Exit code reflects overall status (non-zero if any step failed). Summary includes re-run command for failed steps.
- **D-13:** PBF download retries up to 3 times with exponential backoff.
- **D-14:** Unified command is idempotent — checks for existing PBF, populated Nominatim DB, osm_tiles tables, and Valhalla graph before each step. `--force` flag forces re-import of all steps.

### Claude's Discretion

- Container image tags and version pinning for Nominatim, tile server, Valhalla
- osm-postgres resource limits (mem_limit) for Docker Compose
- Specific healthcheck commands and intervals for each OSM service
- osm2pgsql import flags (slim mode, cache size, etc.)
- Nominatim import-phase PostgreSQL tuning (session-level `ALTER DATABASE SET` parameters)

### Deferred Ideas (OUT OF SCOPE)

- Vector tile serving (Tilemaker + Martin) — future backlog item (FUTURE-04)
- FastAPI proxy endpoints — Phase 25
- Cascade provider integration — Phase 26
- Routing endpoints — Phase 27
- K8s manifests — Phase 28
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-01 | Operator can download the Georgia state OSM PBF extract via CLI command | `osm-download` Typer command using `httpx` with retry/backoff; PBF to `./data/osm/georgia-latest.osm.pbf` |
| PIPE-02 | Operator can import PBF into Nominatim's dedicated PostgreSQL database via CLI command | `osm-import-nominatim` shells out to nominatim container; mediagis/nominatim:5.2 with `PBF_PATH` env |
| PIPE-03 | Operator can import PBF into the tile server's PostGIS database via CLI command | `osm-import-tiles` uses `docker compose run --rm tile-server import`; overv/openstreetmap-tile-server import command pattern |
| PIPE-04 | Operator can build Valhalla routing graph from PBF via CLI command | `osm-build-valhalla` shells out to Valhalla container; `custom_files/` volume mount pattern |
| PIPE-05 | Operator can run a single unified CLI command that executes all imports | `osm-pipeline` orchestrates PIPE-01 through PIPE-04; continues-on-failure; idempotency checks |
| INFRA-01 | Nominatim runs as Docker Compose sidecar service with dedicated PostgreSQL | `mediagis/nominatim:5.2` service under `profiles: [osm]`; `osm-postgres` dependency |
| INFRA-02 | Valhalla runs as Docker Compose sidecar service with pre-built graph on persistent volume | `ghcr.io/valhalla/valhalla:latest` service under `profiles: [osm]`; `valhalla_tiles` named volume |
| INFRA-03 | Tile server runs as Docker Compose sidecar service | `overv/openstreetmap-tile-server:2.3.0` service under `profiles: [osm]` |
</phase_requirements>

---

## Summary

Phase 24 establishes the data foundation and local dev environment for all subsequent v1.4 phases. It has three sub-deliverables: (1) four Docker Compose services (`osm-postgres`, `nominatim`, `tile-server`, `valhalla`) added under `--profile osm`, (2) an init script `scripts/30_osm_setup.sh` that provisions PostGIS extensions on `osm-postgres`, and (3) five CLI commands that download the Georgia PBF and drive each service's import.

The primary technical tension is between decision D-02 (shared `osm-postgres` for both Nominatim and tiles) and the architecture of `overv/openstreetmap-tile-server`: this image bundles its own internal PostgreSQL and does not natively support connecting to an external PostgreSQL via simple environment variables. The correct resolution is that the tile-server container uses its own internal PostgreSQL (mounted via `osm_tile_data` named volume) while Nominatim uses the shared `osm-postgres`. Both remain isolated from `civpulse_geo`. The `osm-postgres` container hosts the `nominatim` database only in this phase. This is documented in the critical finding section and Pitfall 1 below.

The Valhalla ecosystem note: `nilsnolde/docker-valhalla` (the community wrapper) was **archived March 3, 2026** and its code moved upstream to `ghcr.io/valhalla/valhalla`. Use the official upstream image exclusively.

**Primary recommendation:** Use `ghcr.io/valhalla/valhalla:latest`, `mediagis/nominatim:5.2`, and `overv/openstreetmap-tile-server:2.3.0` under `--profile osm`. The tile server carries its own PostgreSQL via named volume; Nominatim uses a separate `osm-postgres` container. Both are isolated from `civpulse_geo`. The CLI commands shell out via `subprocess.run(["docker", "compose", ...])`.

---

## Project Constraints (from global CLAUDE.md)

These global directives apply to all implementation work in this phase:

- Use `uv run` for all Python commands — never bare `python` or `python3`
- Use `uv add` / `uv remove` to manage packages — never pip
- Use `ruff` to lint Python code before every commit
- Use `docker compose` (not `docker-compose`) — Docker Compose v2 syntax
- Use Conventional Commits for all commit messages
- Commit after completing each task/story — no large uncommitted changesets
- Do NOT push to GitHub unless explicitly requested
- No system Python

---

## Standard Stack

### Core

| Image / Library | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| `mediagis/nominatim` | `5.2` | Nominatim geocoding engine container | Official Docker image for Nominatim; 5.2 is current stable as of 2026-04-04 |
| `overv/openstreetmap-tile-server` | `2.3.0` | Raster tile server (renderd/mod_tile/Mapnik) | D-09 locked; most widely-deployed OSM raster tile Docker image |
| `ghcr.io/valhalla/valhalla` | `latest` | Valhalla routing engine | Official upstream image; nilsnolde wrapper archived 2026-03-03 |
| `postgis/postgis` | `17-3.5` | Dedicated PostgreSQL for `nominatim` DB | Matches existing `db` service version; PostGIS 3.5 |
| `httpx` | already pinned | PBF download in `osm-download` CLI command | Already a project dependency; supports streaming downloads and retry |
| `subprocess` (stdlib) | — | Shell out to `docker compose exec` from CLI commands | D-06 locked; standard pattern already used in existing CLI |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich.progress` | already pinned | Stage progress bars in CLI commands | D-08 locked; already imported in CLI |
| `typer` | already pinned | CLI command registration | D-05 locked; existing app |
| `pydantic-settings` | already pinned | New OSM URL settings | Add `osm_nominatim_url`, `osm_tile_url`, `osm_valhalla_url` to `Settings` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `overv/openstreetmap-tile-server` (bundled PG) | `smartappli/openstreetmap-tile-server` (supports external PG) | The smartappli fork supports `PGHOST` etc. but is a third-party fork with less community validation. Decision D-09 locks the overv image. |
| `ghcr.io/valhalla/valhalla:latest` | Pinned semver tag | `latest` tracks upstream; for stability consider pinning to a specific tag after verifying at implementation time. |

**Installation:** No new Python packages needed. Stack additions are Docker images only.

---

## Architecture Patterns

### Recommended Docker Compose Additions

The key topology decision: `osm-postgres` hosts only the `nominatim` database. The `tile-server` uses its own internal PostgreSQL via the `osm_tile_data` named volume. Both are fully isolated from `civpulse_geo`.

```yaml
# services to add to docker-compose.yml

  osm-postgres:
    image: postgis/postgis:17-3.5
    environment:
      POSTGRES_DB: nominatim
      POSTGRES_USER: nominatim
      POSTGRES_PASSWORD: nominatim
    volumes:
      - osm_postgres_data:/var/lib/postgresql/data
      - ./scripts/30_osm_setup.sh:/docker-entrypoint-initdb.d/30_osm_setup.sh
    mem_limit: 4g
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nominatim -d nominatim"]
      interval: 10s
      timeout: 5s
      retries: 5
    profiles:
      - osm

  nominatim:
    image: mediagis/nominatim:5.2
    environment:
      NOMINATIM_DATABASE_DSN: "pgsql:host=osm-postgres;port=5432;dbname=nominatim;user=nominatim;password=nominatim"
      PBF_PATH: /nominatim/pbf/georgia-latest.osm.pbf
      REPLICATION_URL: ""
    volumes:
      - nominatim_data:/nominatim/data
      - ./data/osm:/nominatim/pbf:ro
    ports:
      - "8093:8080"
    depends_on:
      osm-postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/status || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 600s
    profiles:
      - osm

  tile-server:
    image: overv/openstreetmap-tile-server:2.3.0
    # NOTE: This container uses its own internal PostgreSQL (db: gis, user: renderer).
    # It does NOT connect to osm-postgres. Isolation from civpulse_geo is via separate volume.
    volumes:
      - osm_tile_data:/data/database/
      - osm_tile_cache:/data/tiles/
    ports:
      - "8094:8080"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/tile/0/0/0.png || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 300s
    profiles:
      - osm

  valhalla:
    image: ghcr.io/valhalla/valhalla:latest
    environment:
      serve_tiles: "True"
      use_tiles_ignore_pbf: "True"
      build_admins: "False"
      build_elevation: "False"
    volumes:
      - valhalla_tiles:/custom_files
      - ./data/osm:/custom_files/pbf:ro
    ports:
      - "8002:8002"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8002/status || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    profiles:
      - osm

volumes:
  # existing volumes: postgres_data, ollama_data
  osm_postgres_data:
  nominatim_data:
  osm_tile_data:      # tile-server's internal PostgreSQL
  osm_tile_cache:     # rendered tile cache
  valhalla_tiles:     # pre-built routing graph tiles
```

### Pattern 1: osm-postgres Init Script (mirrors 20_tiger_setup.sh)

**What:** A bash script at `scripts/30_osm_setup.sh` runs via `/docker-entrypoint-initdb.d/` on first `osm-postgres` container startup to add PostGIS and hstore extensions to the `nominatim` database.

```bash
#!/bin/bash
# scripts/30_osm_setup.sh
# Install PostGIS and hstore extensions required by Nominatim.
# Mirrors the pattern from scripts/20_tiger_setup.sh.
# Runs via /docker-entrypoint-initdb.d/ on first startup only.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS hstore;
    CREATE EXTENSION IF NOT EXISTS postgis_topology;
EOSQL

echo "OSM PostgreSQL extensions installed."
```

### Pattern 2: CLI Command Shell-Out (D-06)

**What:** Each `osm-*` command calls `subprocess.run` to drive container operations. This mirrors existing subprocess usage in `cli/__init__.py`.

```python
import subprocess

def _run_docker_compose(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run a docker compose subcommand. Passes stdout/stderr through."""
    return subprocess.run(["docker", "compose"] + args, check=check)
```

### Pattern 3: Nominatim Import

**What:** Nominatim 5.2 imports from `PBF_PATH` at container start (if not already imported), OR via `nominatim import` command inside the container.

For `osm-import-nominatim` CLI command (D-06), shell out to the running container:

```bash
docker compose exec nominatim nominatim import --osm-file /nominatim/pbf/georgia-latest.osm.pbf --threads 4
```

### Pattern 4: Tile Server Import vs. Run Mode

**What:** The `overv/openstreetmap-tile-server` image uses the container command argument to determine mode. Import is a separate one-time invocation, not an exec into the running serve container.

```bash
# Import (one-time, creates internal PostgreSQL schema):
docker compose run --rm \
  -v ./data/osm/georgia-latest.osm.pbf:/data/region.osm.pbf:ro \
  tile-server import

# Run mode (started normally by docker compose up):
docker compose --profile osm up -d tile-server
```

The `osm-import-tiles` CLI command must use `docker compose run --rm` for the import step.

### Pattern 5: Valhalla Tile Build

**What:** With `use_tiles_ignore_pbf=True`, Valhalla detects PBF in `custom_files/` and builds tiles on first start via file-hash comparison. Subsequent restarts skip rebuild (tiles already present).

For `osm-build-valhalla` CLI command: restart Valhalla with `force_rebuild=True` to trigger build, then set back to `False` for normal operation. Or use a one-shot container invocation:

```bash
# Trigger tile build without starting the serve process:
docker compose run --rm \
  -e serve_tiles=False \
  -e force_rebuild=True \
  -e build_admins=False \
  -e build_elevation=False \
  valhalla
```

### Pattern 6: Pipeline Idempotency Checks (D-14)

| Step | Check Command | Idempotent Signal |
|------|--------------|-------------------|
| `osm-download` | `Path("./data/osm/georgia-latest.osm.pbf").exists()` | File exists |
| `osm-import-nominatim` | `docker compose exec nominatim nominatim admin --check-database` | Exit 0 |
| `osm-import-tiles` | `docker compose exec tile-server psql -U renderer -d gis -c "\dt" 2>/dev/null` | `planet_osm_*` tables listed |
| `osm-build-valhalla` | `docker compose exec valhalla ls /custom_files/valhalla_tiles 2>/dev/null` | Non-empty output |

### Recommended Project Structure Changes

```
docker-compose.yml          # ADD: osm-postgres, nominatim, tile-server, valhalla + volumes
scripts/
  30_osm_setup.sh           # NEW: osm-postgres init script
data/
  osm/                      # NEW: PBF download dir (gitignored)
    georgia-latest.osm.pbf  # Downloaded by osm-download command
src/civpulse_geo/
  cli/
    __init__.py             # ADD: osm-pipeline, osm-download, osm-import-nominatim,
                            #      osm-import-tiles, osm-build-valhalla commands
  config.py                 # ADD: osm_nominatim_url, osm_tile_url, osm_valhalla_url
.gitignore                  # ADD: data/osm/ and *.osm.pbf patterns
```

### Anti-Patterns to Avoid

- **Pointing Nominatim at civpulse_geo:** `NOMINATIM_DATABASE_DSN` must NEVER reference `civpulse_geo_dev` or `civpulse_geo_prod`. Nominatim's import drops and recreates public schema tables — it will destroy application data without warning.
- **Using `PBF_URL` in Nominatim container:** The PBF is already downloaded by `osm-download`. Use `PBF_PATH` to mount the local file rather than re-downloading inside the container.
- **Using `docker compose exec` for tile-server import:** Import mode requires `docker compose run --rm tile-server import` (a new container invocation), not exec into the running serve container.
- **Using nilsnolde/docker-valhalla:** Archived March 2026. Use `ghcr.io/valhalla/valhalla`.
- **Setting `build_admins=True` and `build_elevation=True` in Valhalla:** These add significant build time and are not required for basic walking/driving routing. Set both to `False`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OSM data import into PostgreSQL | Custom osm2pgsql wrapper | `overv/openstreetmap-tile-server import` command | Image handles schema, indexes, osm2pgsql flags internally |
| Nominatim geocoding schema | Any SQL DDL | `mediagis/nominatim` image + `nominatim import` command | 50+ tables, triggers, functions; Docker image manages all |
| Valhalla graph building | Any Python tile building | `ghcr.io/valhalla/valhalla` entrypoint with PBF in `custom_files/` | Graph compilation is C++; container handles all build tooling |
| PostgreSQL extensions for PostGIS/hstore | Manual statements | `scripts/30_osm_setup.sh` init script | Already established project pattern |
| HTTP retry logic for PBF download | Custom loop | Manual retry in `osm-download` using `time.sleep` + loop | httpx is already present; simple 3-attempt loop with exponential backoff per D-13 |

**Key insight:** All OSM data pipeline operations are container-native. The Python CLI orchestrates and reports progress — the heavy lifting (osm2pgsql, Nominatim import, Valhalla tile build) happens inside Docker containers via shell-outs.

---

## Critical Architectural Finding: Tile Server PostgreSQL Isolation

**Decision D-02 states:** "A single shared `osm-postgres` container hosts two isolated databases: `nominatim` and `osm_tiles`."

**Research finding:** `overv/openstreetmap-tile-server` bundles its own internal PostgreSQL instance. It does NOT support connecting to an external PostgreSQL via simple environment variables. The container creates a `gis` database owned by user `renderer` entirely within its own process. Multiple GitHub issues confirm external PostgreSQL requires hacking the container startup scripts (modifying `project.mml` and Mapnik XML generation) — not a supported pattern.

**Correct implementation of D-02's intent:**
- `osm-postgres` container: hosts the `nominatim` database
- `tile-server` container: hosts its own internal `gis` database via `osm_tile_data` named volume

Both are isolated from `civpulse_geo` (on different PostgreSQL instances entirely). The planner should implement it this way. D-02's "osm_tiles database" label describes the tile server's internal database, which is not externally accessible. The named volume `osm_tile_data` makes the isolation and persistence explicit.

**Confidence:** HIGH — verified against official source code and GitHub issues #21 and #396.

---

## Common Pitfalls

### Pitfall 1: Nominatim Corrupts Shared PostgreSQL

**What goes wrong:** `NOMINATIM_DATABASE_DSN` pointing to `civpulse_geo` causes Nominatim's import to drop and recreate `public` schema tables, destroying application data.
**How to avoid:** `NOMINATIM_DATABASE_DSN` must point to `osm-postgres` with DSN format: `pgsql:host=osm-postgres;port=5432;dbname=nominatim;user=nominatim;password=nominatim`
**Warning signs:** DSN contains `civpulse_geo` in the dbname.

### Pitfall 2: Nominatim Import Cannot Resume Below Rank 26

**What goes wrong:** Interrupted import leaves an unrecoverable inconsistent state. Re-running produces cryptic errors (`Tokenizer was not set up properly`).
**How to avoid:** Allow adequate time (90+ minutes for Georgia). Build a completion check into `osm-import-nominatim`: run `nominatim admin --check-database` after import. If import fails, the recovery is: delete `nominatim_data` volume, drop and recreate `nominatim` database on `osm-postgres`, re-run.
**Resume check:** `docker compose exec nominatim psql nominatim -c "SELECT max(rank_search) FROM placex WHERE indexed_status = 0;"` — if rank is >= 26, can continue with `nominatim import --continue indexing`.

### Pitfall 3: Tile Server Import vs. Run Mode Confusion

**What goes wrong:** Using `docker compose exec tile-server` to trigger import when import requires `docker compose run --rm tile-server import`.
**How to avoid:** `osm-import-tiles` CLI command must use `docker compose run --rm -v ./data/osm/georgia-latest.osm.pbf:/data/region.osm.pbf:ro tile-server import`.
**Warning signs:** Import appears to complete with no osm2pgsql log output; `/tile/0/0/0.png` returns 404.

### Pitfall 4: PBF Not Mounted at /data/region.osm.pbf

**What goes wrong:** Tile server import container looks for PBF at exactly `/data/region.osm.pbf`. Wrong path = silent failure or internet download.
**How to avoid:** Mount with explicit path: `-v ./data/osm/georgia-latest.osm.pbf:/data/region.osm.pbf:ro`.

### Pitfall 5: Valhalla Rebuilds Tiles on Every Restart

**What goes wrong:** With empty `valhalla_tiles` volume, Valhalla rebuilds graph on every container start (10-30 minutes).
**How to avoid:** Set `use_tiles_ignore_pbf=True` in the compose service definition. The `osm-build-valhalla` command does a one-shot build with `force_rebuild=True`; the running service uses `use_tiles_ignore_pbf=True`.

### Pitfall 6: data/osm/ PBF Not Gitignored

**What goes wrong:** 333MB PBF accidentally committed to git.
**How to avoid:** Add `data/osm/` and `*.osm.pbf` to `.gitignore` before creating the directory. The current `.gitignore` does not cover PBF files.

### Pitfall 7: Nominatim Healthcheck start_period Too Short

**What goes wrong:** Nominatim's HTTP port is not bound during import (up to 90 minutes). Healthcheck fails continuously, causing Docker to consider the container unhealthy prematurely.
**How to avoid:** Set `start_period: 600s` minimum on Nominatim healthcheck. In Phase 24, no other services depend on Nominatim health status — the healthcheck is informational only during this phase.

---

## Code Examples

### PBF Download Command Skeleton

```python
# src/civpulse_geo/cli/__init__.py — new command following existing flat Typer pattern

GEORGIA_PBF_URL = "https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf"
OSM_DATA_DIR = Path("data/osm")
PBF_PATH = OSM_DATA_DIR / "georgia-latest.osm.pbf"

@app.command("osm-download")
def osm_download(
    force: bool = typer.Option(False, "--force", help="Re-download even if PBF already exists."),
) -> None:
    """Download the Georgia OSM PBF extract from Geofabrik."""
    OSM_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PBF_PATH.exists() and not force:
        typer.echo(f"PBF already exists at {PBF_PATH}. Use --force to re-download.")
        return
    for attempt in range(3):
        try:
            with httpx.stream("GET", GEORGIA_PBF_URL, follow_redirects=True) as r:
                r.raise_for_status()
                with open(PBF_PATH, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=8192):
                        f.write(chunk)
            typer.echo(f"Downloaded to {PBF_PATH}")
            return
        except Exception as e:
            if attempt == 2:
                typer.echo(f"Download failed after 3 attempts: {e}", err=True)
                raise typer.Exit(1)
            wait = 2 ** attempt
            typer.echo(f"Attempt {attempt+1}/3 failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
```

### Unified Pipeline Command Skeleton (D-12, D-14)

```python
@app.command("osm-pipeline")
def osm_pipeline(
    force: bool = typer.Option(False, "--force", help="Re-run all steps even if already complete."),
) -> None:
    """Download Georgia PBF and import into all OSM services (Nominatim, tiles, Valhalla)."""
    steps = [
        ("download",         _run_osm_download,         _check_pbf_exists),
        ("import-nominatim", _run_import_nominatim,     _check_nominatim_populated),
        ("import-tiles",     _run_import_tiles,         _check_tiles_populated),
        ("build-valhalla",   _run_build_valhalla,       _check_valhalla_built),
    ]
    results: dict[str, bool] = {}
    for name, run_fn, check_fn in steps:
        if not force and check_fn():
            typer.echo(f"  SKIP  {name} (already complete)")
            results[name] = True
            continue
        try:
            run_fn()
            results[name] = True
            typer.echo(f"  OK    {name}")
        except Exception as e:
            results[name] = False
            typer.echo(f"  FAIL  {name}: {e}")
            typer.echo(f"        To retry: geo-import osm-{name}")
    failed = [k for k, v in results.items() if not v]
    if failed:
        typer.echo(f"\nCompleted with {len(failed)} failure(s). See above.")
        raise typer.Exit(1)
    typer.echo("\nAll steps complete.")
```

### Nominatim DSN Format (verified against mediagis/nominatim-docker docs)

```
NOMINATIM_DATABASE_DSN=pgsql:host=osm-postgres;port=5432;dbname=nominatim;user=nominatim;password=nominatim
```

This uses PostgreSQL's libpq keyword=value format with semicolons, NOT a `postgresql://` URL. The `pgsql:` prefix is required by Nominatim's configuration parser.

### Settings Additions

```python
# src/civpulse_geo/config.py — add to Settings class
osm_nominatim_url: str = "http://nominatim:8080"
osm_tile_url: str = "http://tile-server:8080"
osm_valhalla_url: str = "http://valhalla:8002"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `nilsnolde/docker-valhalla` community wrapper | `ghcr.io/valhalla/valhalla` official upstream image | March 2026 (nilsnolde archived) | Must use official image; `build_admins`/`do_timezones` now default True in upstream |
| `nominatim import` with bundled PostgreSQL | `mediagis/nominatim` + external PostgreSQL via `NOMINATIM_DATABASE_DSN` | Nominatim 4.x+ | Enables database isolation and connection to dedicated `osm-postgres` |
| `docker-compose` (v1) | `docker compose` (v2 plugin) | Compose v2 GA | Must use v2 syntax; Docker Compose v5.1.1 is installed on this machine |

**Deprecated/outdated:**
- `nilsnolde/docker-valhalla` (`ghcr.io/nilsnolde/docker-valhalla/valhalla`): Archived 2026-03-03. Do not use.
- `docker-compose` (hyphenated, v1 CLI): Not installed on this machine. Use `docker compose`.

---

## Open Questions

1. **Exact Valhalla image tag to pin**
   - What we know: `ghcr.io/valhalla/valhalla:latest` is official upstream, updated weekly
   - What's unclear: No specific stable semver tag identified during research
   - Recommendation: Check `https://github.com/valhalla/valhalla/pkgs/container/valhalla` at implementation time; start with `latest` and pin a specific tag if stability is needed.

2. **Tile server import: does `docker compose run` inherit compose service volumes?**
   - What we know: `docker compose run --rm tile-server import` creates a new container from the service definition but may not auto-mount service volumes
   - What's unclear: Whether the `osm_tile_data` volume is automatically mounted during `run` (it should be, per Docker Compose spec)
   - Recommendation: Explicitly test `docker compose run --rm tile-server import` with the PBF volume binding at implementation time. Fall back to `docker run` with explicit `--volume` flags if `run` doesn't inherit service volumes correctly.

3. **Nominatim import: PBF_PATH at startup vs. post-start exec**
   - What we know: Both `PBF_PATH` (on first startup) and `nominatim import --osm-file` (post-start exec) are supported by mediagis/nominatim 5.2
   - What's unclear: Which approach is more idempotent and controllable for CLI-driven import
   - Recommendation: Use `docker compose exec nominatim nominatim import --osm-file /nominatim/pbf/georgia-latest.osm.pbf` for the `osm-import-nominatim` command. This gives the operator explicit control via CLI and avoids the container auto-triggering import on every restart when `PBF_PATH` is set.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container services | Yes | 29.3.1 | — |
| Docker Compose v2 plugin | `docker compose` commands | Yes | v5.1.1 | — |
| uv | Python package management | Yes | 0.8.14 | — |
| Internet access | Geofabrik PBF download | Assumed | — | Pre-stage PBF manually in `data/osm/` |
| `data/osm/` directory | PBF storage | Not yet created | — | Created by `osm-download` or `mkdir -p data/osm` |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:**
- `data/osm/` directory: Does not exist yet; created by `osm-download` command.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_osm_cli.py -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | `osm-download` exits 0, creates PBF at correct path | unit (mock httpx) | `uv run pytest tests/test_osm_cli.py::TestOsmDownload -x` | No — Wave 0 |
| PIPE-01 | `osm-download` retries 3x on network failure | unit | `uv run pytest tests/test_osm_cli.py::TestOsmDownloadRetry -x` | No — Wave 0 |
| PIPE-01 | `osm-download` skips if PBF exists without `--force` | unit | `uv run pytest tests/test_osm_cli.py::TestOsmDownloadIdempotency -x` | No — Wave 0 |
| PIPE-02 | `osm-import-nominatim` calls correct docker compose exec command | unit (mock subprocess) | `uv run pytest tests/test_osm_cli.py::TestOsmImportNominatim -x` | No — Wave 0 |
| PIPE-03 | `osm-import-tiles` calls correct docker compose run command with correct volume | unit (mock subprocess) | `uv run pytest tests/test_osm_cli.py::TestOsmImportTiles -x` | No — Wave 0 |
| PIPE-04 | `osm-build-valhalla` calls correct docker command | unit (mock subprocess) | `uv run pytest tests/test_osm_cli.py::TestOsmBuildValhalla -x` | No — Wave 0 |
| PIPE-05 | `osm-pipeline` runs all steps in order | unit (mock steps) | `uv run pytest tests/test_osm_cli.py::TestOsmPipeline -x` | No — Wave 0 |
| PIPE-05 | `osm-pipeline` continues after one step fails | unit | `uv run pytest tests/test_osm_cli.py::TestOsmPipelineContinueOnFailure -x` | No — Wave 0 |
| PIPE-05 | `osm-pipeline` skips completed steps (idempotency) | unit | `uv run pytest tests/test_osm_cli.py::TestOsmPipelineIdempotency -x` | No — Wave 0 |
| PIPE-05 | `osm-pipeline --force` re-runs all steps | unit | `uv run pytest tests/test_osm_cli.py::TestOsmPipelineForce -x` | No — Wave 0 |
| INFRA-01 | Nominatim starts, `osm-postgres` healthcheck passes | manual | manual-only — requires running containers | — |
| INFRA-02 | Valhalla starts and healthcheck passes | manual | manual-only — requires running containers | — |
| INFRA-03 | Tile server starts and serves tile at `/tile/0/0/0.png` | manual | manual-only — requires running containers | — |

Note: INFRA tests require running Docker containers with imported data (60-90 minutes). These are validated manually via `docker compose --profile osm up` + curl spot-checks, not automated unit tests.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_osm_cli.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full test suite green + manual `docker compose --profile osm up` verification before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_osm_cli.py` — covers PIPE-01 through PIPE-05; mirrors `tests/test_tiger_cli.py` pattern using `typer.testing.CliRunner` and `unittest.mock.patch`

*(No new conftest.py fixtures needed — existing `CliRunner` pattern from test_tiger_cli.py is sufficient)*

---

## Sources

### Primary (HIGH confidence)

- [mediagis/nominatim-docker GitHub](https://github.com/mediagis/nominatim-docker) — image tags (5.2 current), `NOMINATIM_DATABASE_DSN` libpq format, `PBF_PATH` env var behavior
- [Valhalla official Docker README](https://github.com/valhalla/valhalla/blob/master/docker/README.md) — `force_rebuild`, `use_tiles_ignore_pbf`, `serve_tiles`, `custom_files/` volume pattern; code moved from nilsnolde
- [overv/openstreetmap-tile-server GitHub](https://github.com/Overv/openstreetmap-tile-server) — import vs run command, volume patterns, version 2.3.0 confirmed on Docker Hub
- [overv/openstreetmap-tile-server Issue #21](https://github.com/Overv/openstreetmap-tile-server/issues/21) — external PostgreSQL not officially supported
- [overv/openstreetmap-tile-server Issue #396](https://github.com/Overv/openstreetmap-tile-server/issues/396) — external PostgreSQL requires project.mml/Mapnik XML manual modification
- [nilsnolde/docker-valhalla README](https://github.com/nilsnolde/docker-valhalla/blob/master/README.md) — confirms archived March 2026, code moved upstream
- [Geofabrik Georgia PBF URL](https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf) — `https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf`, ~333MB, updated daily
- `.planning/research/PITFALLS.md` — Nominatim DB isolation, import resumption, PostgreSQL tuning pitfalls
- `.planning/research/SUMMARY.md` — stack decisions, architectural overview
- `docker-compose.yml` — existing service topology (profile pattern, healthcheck definitions)
- `scripts/20_tiger_setup.sh` — reference pattern for init script structure
- `src/civpulse_geo/cli/__init__.py` — existing flat Typer commands, subprocess pattern, Rich progress usage

### Secondary (MEDIUM confidence)

- [Docker Hub mediagis/nominatim](https://hub.docker.com/r/mediagis/nominatim) — 5.2 tag confirmed in image layers
- [Docker Hub overv/openstreetmap-tile-server](https://hub.docker.com/r/overv/openstreetmap-tile-server/) — 2.3.0 tag confirmed in image layers
- [Switch2OSM Using a Docker Container](https://switch2osm.org/serving-tiles/using-a-docker-container/) — canonical tile server import pattern

---

## Metadata

**Confidence breakdown:**
- Standard stack (image versions): HIGH — Docker Hub tags verified
- Docker Compose topology: HIGH — verified against official image documentation
- Tile server PostgreSQL isolation finding: HIGH — verified against official source and GitHub issues
- CLI patterns: HIGH — directly mirrors existing project patterns
- Valhalla tile build behavior: HIGH — verified against official upstream README
- Pitfalls: HIGH — based on prior v1.4 research plus tile-server external PostgreSQL finding

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (30 days; stable infrastructure images)
