# Pitfalls Research

**Domain:** Self-Hosted OSM Stack — Tile Serving, Nominatim Geocoding, Routing (Valhalla/OSRM) added to existing FastAPI/PostGIS/K8s system
**Project:** CivPulse Geo API — v1.4 Self-Hosted OSM Stack
**Researched:** 2026-04-04
**Confidence:** HIGH for Nominatim DB isolation and import behavior (official docs + GitHub issue tracker); HIGH for Valhalla K8s stateful workload pattern (community blog + GitHub discussions); MEDIUM for tile stack raster/vector tradeoffs (community forum + blog posts); MEDIUM for OSM replication pipeline (OSM wiki + community posts); LOW for Nominatim cascade integration scoring (training data + general geocoding literature)

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or permanent operational problems.

---

### Pitfall 1: Nominatim Shares the Existing PostGIS Database and Corrupts It

**What goes wrong:**
Nominatim requires aggressive PostgreSQL tuning for its import phase: `shared_buffers=2GB`, `maintenance_work_mem=10GB`, `synchronous_commit=off`, `wal_level=minimal`. If these settings are applied to the shared PostgreSQL 17 instance that already serves the geo-api app (FastAPI + asyncpg), the geo-api app's runtime query performance degrades severely and `synchronous_commit=off` introduces crash-recovery data loss risk for geocoding cache data that is not safe to lose. More critically, Nominatim's import drops and recreates tables named `place`, `location_property_osmline`, and others in the `public` schema. If Nominatim is pointed at the same database and schema as geo-api's tables, it will destroy existing data without warning.

**Why it happens:**
The Nominatim official docs say "Nominatim requires its own database" but the `mediagis/nominatim` Docker image defaults to creating its internal PostgreSQL instance, so developers assume using an existing external PostgreSQL host simply means passing `NOMINATIM_DATABASE_DSN` — they don't realize that Nominatim still drops and recreates the `public` schema tables.

**How to avoid:**
- Give Nominatim its own dedicated PostgreSQL database on the same shared server instance (not just a schema): `CREATE DATABASE nominatim OWNER nominatim;`. Keep geo-api in the `civpulse_geo_dev` / `civpulse_geo_prod` databases.
- Do NOT apply Nominatim's import-phase tuning to the server's `postgresql.conf`. Use `ALTER DATABASE nominatim SET maintenance_work_mem = '10GB';` session-level overrides, or run the import in a dedicated init container/job that connects only with a Nominatim-specific user that has no access to other databases.
- The `synchronous_commit=off` setting must NEVER be applied globally to the shared instance — only session-level inside the Nominatim import process.
- After import completes, revert any altered server-level tuning immediately. Build this into the import job's cleanup step.

**Warning signs:**
- `NOMINATIM_DATABASE_DSN` points to `civpulse_geo_dev` or `civpulse_geo_prod` (wrong).
- Import job connecting as the `geo_dev` or `geo_prod` app user (wrong — Nominatim needs a separate DB user with SUPERUSER for import).
- geo-api returning 500 errors during Nominatim import due to exhausted connections or changed query plans.

**Phase to address:** OSM data pipeline phase (first phase). Establish database isolation before any import attempt.

---

### Pitfall 2: Nominatim Import Cannot Be Resumed After Interruption — Full Restart Required

**What goes wrong:**
If the Nominatim import (via `nominatim import --osm-file georgia.osm.pbf`) is interrupted at any stage before rank 26 indexing, the database is left in a partially initialized state. The standard advice is "start the full setup from the beginning." Re-running the import against the partially initialized database produces cryptic errors: `Tokenizer was not set up properly`, `Database property missing`, or silent hangs at the post-process tables step that appear to complete but do not produce a usable index.

**Why it happens:**
Nominatim's import is a two-phase process: ingestion (osm2pgsql) followed by multi-rank indexing (places ranked 0–30). The tokenizer state file is created on disk during the first run; if the database is partially populated but the tokenizer never finalized, the state is inconsistent. There is no rollback mechanism.

**How to avoid:**
- Run the import as a Kubernetes Job with adequate resource limits. Do not run as a sidecar or init container that has a shared timeout with the main pod.
- Set the Job `activeDeadlineSeconds` to at least 4 hours for a Georgia extract. The Georgia PBF is ~500MB compressed; import typically takes 30–90 minutes depending on hardware.
- Use a dedicated PersistentVolumeClaim for the Nominatim data directory. If the Job fails, inspect the database rank before deciding to wipe and restart.
- To check if resumption is possible: `SELECT count(*) FROM placex WHERE indexed_status > 0;` — if this is 0, import completed indexing. If non-zero and the rank is ≥ 26, run `nominatim import --continue indexing`.
- If rank is < 26 and the Job cannot be resumed: delete the Nominatim PVC, drop and recreate the `nominatim` database, and re-run the Job.
- Build a `completed` marker file write into the Job's final step. Init containers on the Nominatim serving Deployment should check for this marker before attempting to serve.

**Warning signs:**
- Nominatim Job exits non-zero within the first 10 minutes (probably a database connection or PBF download failure, not an import failure — fix and retry immediately).
- Job runs to completion but `/search?q=Atlanta,GA` returns empty results (indexing did not complete — check rank).
- `nominatim admin --check-database` reports errors.

**Phase to address:** OSM data pipeline phase. Design the Job spec and resumption check logic before executing the import.

---

### Pitfall 3: Valhalla Graph Tiles Rebuilt from Scratch on Every Pod Restart

**What goes wrong:**
The standard `ghcr.io/gis-ops/docker-valhalla` container rebuilds routing graph tiles from the PBF file on every startup if the tile directory is empty or missing. For a Georgia extract, tile building takes 10–30 minutes and exhausts significant CPU and I/O. In Kubernetes, if Valhalla is deployed as a Deployment (not a StatefulSet) without a pre-built PersistentVolumeClaim, every pod restart — including rolling updates, OOM kills, and node evictions — triggers a full rebuild, making the routing service unavailable for the build duration.

**Why it happens:**
The Docker image entrypoint checks for the existence of `valhalla_tiles.tar` and runs `valhalla_build_tiles` if absent. Deployments without sticky PVC storage produce empty volumes on pod restart, forcing a rebuild. Engineers familiar with stateless apps deploy Valhalla as a Deployment and do not account for the stateful build artifact.

**How to avoid:**
- Use a Kubernetes Job to build tiles once and write them to a PVC. The Valhalla Deployment mounts the same PVC read-only and starts in seconds (tiles already present).
- Pattern: `valhalla-tiles-builder` Job (runs once per OSM data update) → `valhalla` Deployment (mounts PVC, starts immediately).
- Set `valhalla_build_admins=False` and `valhalla_build_elevation=False` in `valhalla.json` for initial deployment — these add significant build time and are optional for basic walking/driving routing.
- Size the PVC: Georgia routing tiles are approximately 2–5GB. Allocate 10GB PVC to allow for elevation data addition later.
- Reduce per-thread cache to avoid OOM: set `mjolnir.tile_cache_size` to 256MB (default 1GB per thread × 8 threads = 8GB). For a Georgia-only extract, 256MB per thread is sufficient.

**Warning signs:**
- Valhalla pod shows `Terminating` → `Pending` → `ContainerCreating` → `Running` cycle on every deploy (missing PVC persistence).
- `valhalla_build_tiles` process visible in `kubectl top pod` during normal operations (should only run in the builder Job).
- Routing requests return 503 for 10–30 minutes after any rolling update.

**Phase to address:** Routing engine deployment phase. Design the Job/Deployment split before writing any K8s manifests.

---

### Pitfall 4: PostgreSQL Tuning for Nominatim Import Starves geo-api App Connections

**What goes wrong:**
Nominatim's official import tuning specifies `max_wal_size=1GB`, `checkpoint_timeout=60min`, and `maintenance_work_mem=10GB` at the server level. If these are applied to the shared PostgreSQL instance and the Nominatim import runs concurrently with geo-api production traffic, PostgreSQL's maintenance operations (VACUUM, CREATE INDEX during import) consume all available `maintenance_work_mem`, increase checkpoint intervals (causing write latency spikes across all databases), and potentially cause the geo-api connection pool to starve as PostgreSQL becomes I/O-saturated.

**Why it happens:**
Nominatim's recommended tuning is designed for a dedicated PostgreSQL host. The documentation does not warn about shared-instance consequences. These settings are server-global, not database-scoped.

**How to avoid:**
- Schedule the Nominatim import Job during a maintenance window (low-traffic period).
- Apply import tuning as session-level `SET` commands inside the import process where possible, not globally.
- Set `maintenance_work_mem` via `ALTER DATABASE nominatim SET maintenance_work_mem = '2GB';` (reduced from 10GB) as a compromise that won't starve other databases.
- Do not set `wal_level=minimal` globally — this disables WAL archiving for ALL databases. Use only if the PostgreSQL instance is dedicated to Nominatim during import.
- After import, verify geo-api P95 latency has not regressed using the `/metrics` endpoint.

**Warning signs:**
- geo-api `/health/ready` starts returning 503 during or immediately after Nominatim import.
- PostgreSQL `pg_stat_activity` shows many `idle in transaction` connections from geo-api during import.
- Nominatim import logs show `checkpoint request` messages every few seconds (WAL pressure spilling into other databases).

**Phase to address:** OSM data pipeline phase. The import Job spec must include a pre-flight check ensuring geo-api health before beginning, and a post-import health check confirming geo-api is unaffected.

---

### Pitfall 5: Raster Tile Rendering Stack Has Unacceptable Startup and Storage Complexity

**What goes wrong:**
The "classic" self-hosted raster tile stack (renderd + mod_tile + Mapnik + osm-carto stylesheet) requires importing OSM data into a second PostGIS database (separate from Nominatim) using `osm2pgsql` with the carto schema, compiling or installing Mapnik, managing font packages, and running Apache/nginx as the tile server. For a Georgia extract, the pre-rendered tile cache at z0–z14 is ~200MB but the operational overhead is disproportionate: the system is fragile to stylesheet version mismatches, font installation failures, and Mapnik/osm-carto version incompatibilities. On-demand rendering at high zoom also causes rendering queue backlogs under any concurrent load.

**Why it happens:**
Most self-hosted OSM tile tutorials default to the classic renderd/mod_tile stack because it produces familiar-looking Mapnik-rendered raster tiles. Engineers assume raster tiles are simpler than vector tiles because browsers render them natively, but the server-side rendering complexity is far higher.

**How to avoid:**
- Use the vector tile approach instead: generate a PMTiles file with Tilemaker from the Georgia PBF, serve it with Martin tile server (Rust, single binary, PostGIS-aware). Martin serves vector tiles with near-zero operational overhead.
- Alternatively, pre-generate raster tiles only up to z14 using `tilemaker` + `tileshrink` and serve the static MBTiles file via Martin — no live rendering needed for a state extract.
- The Leaflet frontend can consume vector tiles with `maplibre-gl` or use raster tiles from a static MBTiles source. The requirement says "raster tile server (z/x/y PNGs)" — verify with the consumer (voter-web, run-api) whether vector tiles are acceptable before committing to raster rendering infrastructure.
- If raster tiles are truly required: use a pre-rendering pipeline (Job) to generate an MBTiles file, then serve it statically. Do not run live rendering in K8s.

**Warning signs:**
- Tile server Deployment requires more than 3 containers (renderd + mod_tile + apache + database = over-complex).
- Tile rendering Pod has no CPU limits set (live rendering will consume all available CPU on a shared node).
- Tile server K8s Deployment spec references osm-carto stylesheets mounted as ConfigMaps (unmaintainable).

**Phase to address:** Tile serving design phase. Make the raster vs. vector decision explicit before any implementation work begins.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Use `mediagis/nominatim` all-in-one container (includes its own PostgreSQL) | Simple deployment, one container | Nominatim's bundled PG ignores the shared PG instance; cannot leverage existing PostGIS indexes; duplicate data storage; disk usage doubles | Never for this project — shared PG is already provisioned |
| Skip Nominatim update replication setup (import once, no diffs) | Faster initial deployment | OSM data becomes stale; addresses in newly-built areas not found; no recovery path other than full re-import | Acceptable for initial milestone delivery; defer OSM diff replication to v1.5 |
| Build Valhalla tiles inside the serving container on startup | Simpler manifest (one container) | Pod restarts trigger 10–30 min rebuild; routing unavailable during rolling updates | Never — use the Job/Deployment split |
| Use `osrm-backend` instead of Valhalla | Faster routing responses (OSRM precomputes entire graph) | OSRM requires loading the full precomputed graph into RAM (~2–4GB for Georgia); no graceful degradation when graph file is being replaced; Valhalla handles multi-modal (walk+drive) natively | Only if sub-100ms routing latency is a hard requirement and RAM is available |
| Generate tiles at z0–z18 | Full zoom coverage | z15–z18 tile count grows exponentially; Georgia at z18 = hundreds of GB; query time multiplies | Generate z0–z14 only; clients can overzoom |
| Nominatim provider bypasses existing cascade pipeline (direct HTTP call) | Simpler integration | Loss of consensus scoring, outlier detection, confidence normalization against other providers | Acceptable only if Nominatim is the only provider; not acceptable here — must participate in the existing `CascadeOrchestrator` |

---

## Integration Gotchas

Common mistakes when connecting the new OSM services to the existing geo-api system.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Nominatim as geocoding provider | Making synchronous HTTP calls inside the existing asyncpg transaction context | Use `httpx.AsyncClient` (already a dependency) outside any DB transaction; apply the same timeout and retry pattern as the Census Geocoder provider |
| Nominatim address format | Passing the full free-form address string to Nominatim's `/search` endpoint and expecting US address parsing to work | Use Nominatim's structured search endpoint: `?street=...&city=...&state=GA&country=US&format=jsonv2` — this dramatically improves match rates for US street addresses |
| Nominatim confidence scores | Directly using Nominatim's `importance` field as a confidence score comparable to other providers | Nominatim's `importance` (0.0–1.0) is popularity-based (OSM edit density), not geocoding confidence. Normalize it: treat any result with `rank_address >= 26` (street/house level) as HIGH confidence, `rank_address >= 16` as MEDIUM |
| Valhalla routing API | Assuming Valhalla's HTTP API matches OSRM's format | They differ entirely. Valhalla uses `POST /route` with a JSON body containing `locations` and `costing` keys; OSRM uses GET with path parameters. Do not copy OSRM client code |
| Tile server CORS | Deploying tile server without CORS headers; Leaflet frontend on voter-web cannot load tiles | Martin tile server requires `--allow-origin '*'` flag or `MARTIN_ALLOW_ORIGIN=*` env var. Do not enable CORS at the K8s ingress layer if Martin handles it — duplicate headers break tile loading |
| PBF source freshness | Downloading the Georgia PBF from Geofabrik at import time inside the K8s Job | The Job becomes non-deterministic (network dependency). Pre-download the PBF to a PVC in a separate fetch step; the import Job consumes from PVC, not from network |
| Nominatim service discovery | Hard-coding Nominatim's cluster IP in geo-api config | Use a Kubernetes Service DNS name: `http://nominatim.geo-api.svc.cluster.local:8080`. Add to the same `geo-api` K8s namespace or note cross-namespace DNS if deployed separately |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Nominatim serving from the same container that ran the import | Query latency is 500ms–2s instead of <100ms | After import, run `nominatim admin --warm` to pre-warm the PostgreSQL cache. Run a VACUUM ANALYZE on the nominatim database post-import. | Immediately after cold-start if cache not warmed |
| Valhalla using default tile cache size (1GB × 8 threads) | OOM kill during Georgia tile build; pod eviction | Set `mjolnir.tile_cache_size: 268435456` (256MB) in `valhalla.json` for build; this is sufficient for a state extract | During first build Job run without config tuning |
| Tile server serving all zoom levels on demand | CPU spike to 100% on first map load; tile request queue backup | Pre-render or pre-generate tiles up to z14 and store in MBTiles; serve from file, not on-demand rendering | First production load test |
| Nominatim returning low-quality results for common query patterns | Geocoding cascade falls through to external providers unnecessarily; hit rate for Nominatim is <50% | Profile query patterns against Nominatim staging instance before integrating into cascade; verify Georgia address hit rate > 70% before assigning meaningful provider weight | On first integration test |
| All three OSM services (Nominatim + Valhalla + tile server) sharing one K8s node | Node CPU/RAM saturation; all three services degrade simultaneously | Set `podAntiAffinity` rules to spread these Pods across nodes, or isolate on a dedicated node pool | Any non-trivial load: Nominatim import is especially CPU/RAM hungry |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Nominatim database user granted access to geo-api databases | Compromised Nominatim container allows access to cached geocoding results and admin overrides | Create a dedicated PostgreSQL user `nominatim` with access only to the `nominatim` database; geo-api users (`geo_dev`, `geo_prod`) have no access to `nominatim` database |
| Valhalla and tile server exposed on public-facing ingress | Tile server and routing are internal services; public exposure increases attack surface unnecessarily | Confirm no public Ingress/IngressRoute for these services; they are consumed by in-cluster voter-web and run-api only, same as geo-api |
| PBF download from arbitrary URL in Job spec | Malicious or corrupted PBF file can crash Nominatim import or corrupt the nominatim database | Pin to a verified Geofabrik URL with SHA-256 checksum verification in the download step |
| Nominatim serving without rate limiting | Nominatim is expensive per query; unrestricted access from a misconfigured consumer could saturate the service | Apply K8s NetworkPolicy to restrict Nominatim access to geo-api namespace pods only; add `rate_limit` in the geo-api Nominatim provider client |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Nominatim import:** Import Job exits 0 — verify with `nominatim admin --check-database` and a live `/search?q=123+Main+St,+Atlanta,+GA` query before marking complete
- [ ] **Valhalla tile build:** Build Job exits 0 — verify with a `POST /route` request for a known Georgia origin/destination pair (e.g., Atlanta to Savannah) before marking complete
- [ ] **Tile server:** Martin starts and returns HTTP 200 — verify that Leaflet/MapLibre can actually render a tile by loading `/tiles/{z}/{x}/{y}` at a Georgia-specific coordinate, not just the root endpoint
- [ ] **Nominatim cascade provider:** Provider is registered and returns results — verify that the `CascadeOrchestrator` actually calls Nominatim and that its result participates in consensus scoring (check that `source=nominatim` appears in geocoding response `candidates`)
- [ ] **Database isolation:** Nominatim import completed — verify that `\dt` in `civpulse_geo_dev` shows no Nominatim tables (`place`, `location_property_osmline`, etc.)
- [ ] **PostgreSQL tuning revert:** Import Job completed — verify that `SHOW maintenance_work_mem;` on the shared server has returned to the pre-import value
- [ ] **Routing engine:** Valhalla responds to route requests — verify that both walking and driving `costing` modes return valid route geometries, not just that the health endpoint returns 200
- [ ] **K8s resource limits:** All new Pods have explicit `resources.requests` and `resources.limits` — missing limits causes eviction during node pressure

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Nominatim import corrupted geo-api database | HIGH | 1. Restore from latest PostgreSQL backup. 2. Recreate `nominatim` as a separate database. 3. Drop Nominatim user access to geo-api databases. 4. Re-run import Job with corrected config. |
| Nominatim import interrupted at rank < 26 | MEDIUM | 1. Check `SELECT max(rank_search) FROM placex WHERE indexed_status = 0;` to confirm rank. 2. If rank >= 26, run `nominatim import --continue indexing`. 3. If rank < 26, delete PVC, drop and recreate nominatim DB, restart Job. |
| Valhalla tiles PVC lost (node failure, PVC deleted) | LOW | 1. Re-run the `valhalla-tiles-builder` Job against the PBF PVC. 2. Georgia tiles rebuild in 10–30 minutes. Routing service unavailable during rebuild. |
| PostgreSQL performance degraded after Nominatim import | LOW-MEDIUM | 1. `SHOW maintenance_work_mem;` — if elevated, `ALTER SYSTEM RESET maintenance_work_mem; SELECT pg_reload_conf();`. 2. `VACUUM ANALYZE` on geo-api tables if query plans degraded. 3. Check `pg_stat_bgwriter` for excessive checkpoints. |
| Tile server returning wrong tiles (misaligned with Georgia data) | MEDIUM | 1. Verify PBF source is the correct Georgia extract. 2. Regenerate MBTiles/PMTiles from PBF. 3. Restart Martin. The issue is almost always the wrong PBF region or a corrupted MBTiles file. |
| Nominatim provider reducing overall geocoding accuracy | MEDIUM | 1. Disable Nominatim from the cascade by setting its weight to 0 or removing from provider registry. 2. Profile which address types Nominatim is mismatching. 3. Adjust structured search query format or rank thresholds. |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Nominatim shares existing PostGIS database | Phase: OSM data pipeline (database provisioning step) | `\l` in psql shows `nominatim` as a separate database; `\dt` in `civpulse_geo_dev` shows no Nominatim tables |
| Nominatim import cannot resume | Phase: OSM data pipeline (import Job design) | Job spec has `activeDeadlineSeconds`, marker file step, and `nominatim admin --check-database` as final step |
| Valhalla rebuilds tiles on every pod restart | Phase: Routing engine deployment | `kubectl rollout restart deployment/valhalla` completes in <60 seconds (no rebuild triggered) |
| PostgreSQL import tuning starves geo-api | Phase: OSM data pipeline (import Job) | geo-api `/health/ready` returns 200 throughout import Job execution |
| Raster tile stack complexity | Phase: Tile serving design (pre-phase decision) | ADR or phase spec explicitly documents raster vs. vector decision with rationale |
| Nominatim bypasses CascadeOrchestrator | Phase: Nominatim provider integration | `source=nominatim` visible in geocoding API response `candidates` for a Georgia address |
| Valhalla OOM during tile build | Phase: Routing engine deployment | Tile build Job completes without OOM kill; `kubectl describe job valhalla-tiles-builder` shows Succeeded |
| Tile CORS blocking frontend | Phase: Tile server integration testing | voter-web or a Playwright test loads a map tile from the cluster-internal tile server URL without CORS errors |
| OSM data becomes stale (no replication) | Deferred to v1.5 — accept as known limitation | Document in operational runbook: "OSM data was imported [date]; re-run import Job to refresh" |

---

## Sources

- [Nominatim Installation Requirements — Official Docs](https://nominatim.org/release-docs/latest/admin/Installation/)
- [Nominatim Import Guide — Official Docs](https://nominatim.org/release-docs/latest/admin/Import/)
- [Nominatim Troubleshooting / FAQ — Official Docs](https://nominatim.org/release-docs/latest/admin/Faq/)
- [Nominatim on Kubernetes — mediagis/nominatim-docker Discussion #463](https://github.com/mediagis/nominatim-docker/discussions/463)
- [Nominatim: separate database vs shared — Official discussion](https://nominatim.org/tutorials/running-nomintim-and-rendering-together.html)
- [What to do when import data interrupted — osm-search/Nominatim Discussion #3244](https://github.com/osm-search/Nominatim/discussions/3244)
- [Valhalla: Understanding memory consumption — valhalla/valhalla Discussion #4816](https://github.com/valhalla/valhalla/discussions/4816)
- [Valhalla: OOM-Killer when building tiles — valhalla/valhalla Discussion #3138](https://github.com/valhalla/valhalla/discussions/3138)
- [Valhalla: Scaling the Routing Service startup — valhalla/valhalla Issue #3953](https://github.com/valhalla/valhalla/issues/3953)
- [Deploying Valhalla on Kubernetes using Valhalla Operator — Medium/Itay Ankri](https://medium.com/@itay.ankri/deploying-valhalla-routing-engine-on-kubernetes-using-valhalla-operator-2426e79ac746)
- [Self-Hosting a Google Maps Alternative with OpenStreetMap — wcedmisten.fyi](https://wcedmisten.fyi/post/self-hosting-osm/)
- [State of Vector Tiles for Self-Hosting in 2024 — OSM Community Forum](https://community.openstreetmap.org/t/state-of-vector-tiles-for-self-hosting-in-2024/117723)
- [osm2pgsql schema conflict: replication failed with different schema — Issue #2259](https://github.com/osm2pgsql-dev/osm2pgsql/issues/2259)
- [Martin Tile Server — Official Documentation](https://maplibre.org/martin/)
- [Valhalla Docs — Official](https://valhalla.github.io/valhalla/)

---
*Pitfalls research for: Self-Hosted OSM Stack (tile serving + Nominatim geocoding + routing) added to existing FastAPI/PostGIS/K8s system*
*Researched: 2026-04-04*
