# Project Research Summary

**Project:** CivPulse Geo API — v1.4 Self-Hosted OSM Stack
**Domain:** Self-hosted OpenStreetMap geospatial services (tile serving, geocoding, routing) integrated into an existing FastAPI/PostGIS/K8s service
**Researched:** 2026-04-04
**Confidence:** HIGH

## Executive Summary

CivPulse geo-api v1.4 replaces dependency on third-party map services (public OSM APIs, Google Maps, Mapbox) with a fully self-hosted OSM stack. The milestone adds four capabilities to the existing FastAPI service: raster tile serving (replacing tile.openstreetmap.org), Nominatim-powered geocoding and POI search (replacing rate-limited public Nominatim), reverse geocoding, and turn-by-turn routing via Valhalla. All new capabilities are proxied through geo-api — consumers (voter-web, run-api) never address the OSM services directly. The Georgia state OSM extract (~333MB PBF from Geofabrik) is the only required data source; planet-wide or US-wide imports are explicitly out of scope.

The recommended approach builds on the existing provider plugin architecture. Nominatim registers as a 6th provider in the existing `CascadeOrchestrator` using the established `GeocodingProvider` ABC — zero cascade pipeline changes are required. POI search, reverse geocoding, and routing are implemented as standalone service clients (not cascade providers) because their input/output shapes are categorically different from address geocoding. The tile server, Nominatim, and Valhalla run as Docker Compose / K8s sidecar services backed by a dedicated `osm-postgres` PostGIS instance that is isolated from the existing `civpulse_geo` databases.

The primary risk is operational complexity around the OSM data import pipeline. Nominatim's import is destructive and non-resumable below rank 26; it requires its own isolated PostgreSQL database to avoid corrupting the existing geo-api data. Valhalla must use a Job/Deployment split to avoid rebuilding routing graph tiles (10–30 minutes) on every pod restart. The tile serving stack complexity is a real decision point: the classic renderd/mod_tile/Mapnik stack is fragile; a pre-generated MBTiles approach (Tilemaker + Martin tile server) is strongly preferred. These are addressable risks with known mitigations — the project should proceed.

---

## Key Findings

### Recommended Stack

The stack additions for v1.4 are entirely infrastructure — no new Python runtime packages are required beyond `httpx` (already a dependency). Three Docker sidecar services are added: `overv/openstreetmap-tile-server` (or Martin tile server for the simpler pre-generated approach), `mediagis/nominatim:5.x`, and `ghcr.io/valhalla/valhalla`. A dedicated `osm-postgres` container (postgis/postgis image) serves both the tile-server and Nominatim — it is explicitly isolated from the existing shared PostgreSQL instance.

The observability stack from v1.3 (OpenTelemetry SDK, Grafana Alloy, Loki, Tempo, VictoriaMetrics) is already in place and requires no changes. The existing CI/CD pipeline (GitHub Actions → GHCR → ArgoCD 3.3.x) deploys unchanged. No new Python packages are required for the v1.4 OSM features.

**Core technologies:**
- `mediagis/nominatim:5.x`: Geocoding + POI + reverse geocode engine — official Docker image, own PostgreSQL schema, PBF-based import
- `overv/openstreetmap-tile-server` (or Martin + Tilemaker): Raster tile serving — widely-used Docker image; Martin is the lower-complexity alternative
- `ghcr.io/valhalla/valhalla`: Walking and driving routing — official image, POST-based JSON API, builds graph from PBF
- `postgis/postgis`: Dedicated OSM PostgreSQL instance — isolates write-heavy import load from civpulse_geo databases
- Geofabrik Georgia PBF (~333MB): Single OSM data source — updated daily, no API key, re-import via CLI on operator schedule

### Expected Features

**Must have (table stakes):**
- Georgia OSM data pipeline CLI command — root dependency; nothing else works without it
- Tile server sidecar + FastAPI tile proxy (`GET /tiles/{z}/{x}/{y}.png`) — Leaflet frontends require z/x/y PNG contract
- `NominatimProvider` in cascade pipeline — forward geocoding integrated into existing consensus scoring
- Reverse geocoding endpoint (`GET /geocode/reverse`) — coordinate → address for polling-place lookups
- POI search endpoint (`GET /poi/search`) — "polling places near X" for voter and canvassing apps
- Walking route (`GET /route?mode=pedestrian`) — core run-api canvassing use case
- Driving route (`GET /route?mode=auto`) — voter polling-place directions

**Should have (competitive/differentiating):**
- Nominatim as cascade provider (not standalone) — results flow through existing consensus scoring, not an orphaned data path
- Valhalla as optional Docker Compose sidecar (`--profile routing`) — same operational model as existing Ollama sidecar
- Bounding-box constrained POI search (`bbox` param) — useful for polling-place map overlays (add after core validated)
- Single CLI command for full data pipeline — consistent with existing `gis-import` CLI pattern

**Defer (v2+):**
- Isochrone / reachability analysis — Valhalla endpoint exists when needed; not in v1.4 scope
- Real-time OSM diff updates — significant operational complexity; Georgia street data changes rarely
- Vector tiles — requires Leaflet → MapLibre GL JS migration; separate large frontend project
- Transit / multimodal routing — requires GTFS data pipeline; no authoritative Georgia GTFS available

### Architecture Approach

The v1.4 architecture extends the existing FastAPI service with new route families (`/tiles`, `/search`, `/reverse`, `/route`) while adding three OSM service containers behind geo-api's proxy layer. The existing `CascadeOrchestrator` is extended by adding `OSMGeocodingProvider` to the weight map (weight ~0.75, lower than Tiger/NAD due to Nominatim's address-geocoding limitations). All new OSM capabilities follow two patterns: the Provider Plugin pattern (for cascade-integrated geocoding) and the Internal Service Client pattern (for POI search, reverse geocoding, and routing — standalone `httpx.AsyncClient` services instantiated at app startup and injected via FastAPI dependency injection). The key structural decision is a dedicated `osm-postgres` PostgreSQL instance: Nominatim's import is destructive to any shared schema and its required tuning parameters are incompatible with live application traffic.

**Major components:**
1. `OSMGeocodingProvider` (`providers/osm.py`) — GeocodingProvider ABC impl; wraps Nominatim `/search`; `is_local=True`; conditional registration
2. `SearchService` / `ReverseService` (`services/search.py`, `services/reverse.py`) — POI search and reverse geocode via Nominatim; standalone service clients
3. `RoutingService` (`services/routing.py`) — Valhalla `/route` client; standalone; not a cascade provider
4. `TileProxy` (`api/tiles.py`) — thin FastAPI proxy to tile-server; single internal entry point for all tile requests
5. `osm-postgres` — dedicated PostGIS instance; tile-server uses `osm_tiles` DB; Nominatim uses `nominatim` DB; both isolated from `civpulse_geo`
6. OSM data pipeline (K8s Job / Docker Compose init) — one-shot Georgia PBF download + import; re-runnable for data refresh

### Critical Pitfalls

1. **Nominatim shares existing PostGIS database and corrupts it** — Nominatim's import drops and recreates `public` schema tables and requires aggressive server-level PostgreSQL tuning incompatible with live traffic. Prevention: dedicated `nominatim` database on the `osm-postgres` instance; never point `NOMINATIM_DATABASE_DSN` at `civpulse_geo_dev` or `civpulse_geo_prod`; import tuning applied session-level only.

2. **Nominatim import cannot resume below rank 26 — full restart required** — Interrupted import leaves a non-recoverable inconsistent state. Prevention: K8s Job with `activeDeadlineSeconds >= 4 hours`; dedicated PVC for Nominatim data; completion marker file; `nominatim admin --check-database` as final Job step.

3. **Valhalla rebuilds routing tiles on every pod restart** — 10–30 minute rebuild on each rolling update or eviction makes routing permanently unreliable. Prevention: `valhalla-tiles-builder` K8s Job writes tiles to PVC once; Valhalla Deployment mounts PVC read-only and starts in seconds.

4. **PostgreSQL import tuning starves geo-api connections** — Nominatim's recommended `maintenance_work_mem=10GB`, `max_wal_size=1GB` are server-global settings that degrade all databases on the shared instance. Prevention: schedule import in maintenance window; use `ALTER DATABASE nominatim SET maintenance_work_mem = '2GB'` instead of server-level config; verify geo-api `/health/ready` throughout import.

5. **Raster tile rendering stack complexity is disproportionate** — renderd/mod_tile/Mapnik/osm-carto is fragile to stylesheet and font version mismatches and unsuitable for K8s live rendering. Prevention: explicit raster vs. vector decision before implementation; if raster required, use pre-generated MBTiles (Tilemaker + Martin) served statically — no live rendering in K8s.

---

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: OSM Data Pipeline
**Rationale:** The Georgia PBF is the root dependency for all downstream phases. Tile server, Nominatim, and Valhalla are all inert without it. Database isolation must also be established here before any import attempt — this is the critical Pitfall 1 prevention phase.
**Delivers:** Georgia PBF downloaded; `osm-postgres` container with isolated `nominatim` and `osm_tiles` databases; K8s Job spec with `activeDeadlineSeconds`, completion marker, and `nominatim admin --check-database` validation; CLI command wiring
**Addresses:** Georgia OSM data pipeline (P1 feature)
**Avoids:** Nominatim DB corruption (Pitfall 1), PostgreSQL import tuning starvation (Pitfall 4), non-resumable import failure (Pitfall 2)

### Phase 2: Tile Server + FastAPI Proxy
**Rationale:** Tile serving validates the OSM Docker Compose setup (osm2pgsql import → tile rendering) before adding Nominatim complexity. Simpler to validate (request a PNG) and establishes the internal proxy pattern that all subsequent OSM routes will follow. Raster vs. vector decision must be made explicit here.
**Delivers:** Tile server sidecar running; `GET /tiles/{z}/{x}/{y}.png` FastAPI proxy; `OSM_TILE_URL` config; Georgia tiles rendering in a Leaflet TileLayer
**Addresses:** Tile server sidecar + FastAPI proxy (P1 feature)
**Avoids:** Raster tile rendering stack complexity (Pitfall 5); tile CORS blocking frontend (integration gotcha)

### Phase 3: Nominatim Provider + Search/Reverse Routes
**Rationale:** With Nominatim's database import already completed (Phase 1), this phase wires the application layer. OSM geocoding provider integrates into the cascade pipeline — more critical path than routing. Structured search query format (not free-form) must be used for US address geocoding quality.
**Delivers:** `OSMGeocodingProvider` registered in cascade with weight ~0.75; `GET /geocode/reverse`; `GET /poi/search`; `source=nominatim` visible in geocoding response candidates
**Addresses:** NominatimProvider in cascade, reverse geocoding endpoint, POI search endpoint (all P1)
**Avoids:** Unconditional provider registration (Architecture Anti-Pattern 3); Nominatim free-form query mismatch (integration gotcha); Nominatim importance score misuse as confidence (integration gotcha)

### Phase 4: Valhalla + Routing Routes
**Rationale:** Valhalla routing is lower priority than Nominatim (it is an optional sidecar, not integrated into the cascade). The Job/Deployment split must be designed before writing any K8s manifests — this is the critical Pitfall 3 prevention phase.
**Delivers:** `valhalla-tiles-builder` K8s Job; Valhalla Deployment (PVC mount, no rebuild on restart); `POST /route` with `mode=pedestrian` and `mode=auto`; normalized GeoJSON-compatible route response
**Addresses:** Walking route, driving route (both P1)
**Avoids:** Valhalla tile rebuild on every restart (Pitfall 3); Valhalla OOM during tile build (performance trap); OSRM API confusion (integration gotcha)

### Phase 5: K8s Manifests + Health Probes
**Rationale:** Validate all services in Docker Compose first (Phases 1–4), then translate to K8s. Avoids debugging K8s YAML before services are proven working locally. All new Pods need explicit resource limits to avoid node eviction.
**Delivers:** K8s Deployments, Services, PVCs for tile-server, Nominatim, Valhalla, osm-postgres; kustomization.yaml updated; ArgoCD deploys successfully; NetworkPolicy restricting Nominatim to geo-api namespace; all Pods have resource limits
**Addresses:** K8s production hardening
**Avoids:** All Pods missing resource limits (eviction risk); Nominatim exposed on public ingress (security mistake); Valhalla tiles PVC not persisted (Pitfall 3 recurrence)

### Phase Ordering Rationale

- Pipeline before services: Tile server, Nominatim, and Valhalla all need the Georgia PBF. Phase 1 must complete and the databases must be healthy before any service import can be validated end-to-end.
- Tile server before geocoding: Simpler validation (PNG response), fewer moving parts. Establishes the OSM Docker Compose setup before adding Nominatim multi-rank indexing complexity.
- Nominatim before Valhalla: OSM geocoding is more critical to the cascade pipeline (it affects all geocoding calls). Routing is lower priority and deployed as an optional profile.
- Docker Compose validation before K8s: Eliminates infrastructure variables (YAML, PVC, NetworkPolicy) when validating service behavior.
- Database isolation is a prerequisite, not a phase: Must be established within Phase 1 before any import begins. Not a separate phase — it is part of the pipeline design.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (OSM Data Pipeline):** Nominatim import Job design has multiple failure modes (rank-based resumption, PBF freshness, shared PostgreSQL tuning). The Job spec design warrants explicit research-phase attention before implementation begins.
- **Phase 2 (Tile Server):** Raster vs. vector tile decision is unresolved. PITFALLS.md recommends Martin + Tilemaker (pre-generated MBTiles) over renderd/mod_tile. FEATURES.md specifies raster PNG. Needs explicit ADR or consumer team confirmation before implementation begins.
- **Phase 5 (K8s Manifests):** Valhalla StatefulSet/Job split on Kubernetes has limited official documentation; the community blog source is MEDIUM confidence. The Valhalla Kubernetes operator should be evaluated as an alternative during this phase.

Phases with standard patterns (skip research-phase):
- **Phase 3 (Nominatim Provider):** Provider Plugin pattern is well-established in this codebase; Nominatim API is HIGH confidence official docs; integration follows existing conditional registration pattern exactly.
- **Phase 4 (Valhalla Routing):** Valhalla HTTP API is HIGH confidence official docs; RoutingService as standalone client is a clean new domain with no cascade entanglement.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Nominatim 5.x, Valhalla, overv/openstreetmap-tile-server verified against official docs and GitHub repos. Martin + Tilemaker alternative also HIGH confidence. No new Python packages required. |
| Features | HIGH | Nominatim and Valhalla API docs are official sources. OSM tile usage policy confirmed. Feature dependency graph verified. Anti-features rationale verified against PMTiles/Leaflet docs. |
| Architecture | HIGH (existing) / MEDIUM (new OSM components) | Existing provider plugin and cascade patterns are known quantities. New OSM service communication patterns verified against official docs. K8s stateful Valhalla deployment is MEDIUM (community blog source). |
| Pitfalls | HIGH (DB isolation, import behavior, Valhalla K8s) / MEDIUM (tile stack) | Nominatim DB isolation and import pitfalls verified against official docs and GitHub issue tracker. Valhalla K8s OOM verified against GitHub discussions. Tile stack complexity is MEDIUM (forum/blog). |

**Overall confidence:** HIGH

### Gaps to Address

- **Raster vs. vector tile decision:** PITFALLS.md recommends abandoning renderd/mod_tile in favor of Martin + pre-generated MBTiles; FEATURES.md specifies raster PNGs. This contradiction must be resolved with voter-web / run-api consumer teams before Phase 2 planning. The decision has significant architectural consequences.
- **Nominatim address hit rate for Georgia:** PITFALLS.md flags that Nominatim's hit rate for US street addresses should be profiled (>70% expected) before assigning meaningful cascade weight. Should be validated during Phase 3 integration testing, not assumed.
- **Valhalla K8s operator vs. manual manifests:** The Valhalla Kubernetes operator (community blog, MEDIUM confidence) should be evaluated during Phase 5 planning. Manual Job + Deployment + PVC is more auditable and likely preferred for this project scale.
- **OSM data import scheduling:** Import takes 30–90 minutes and stresses the shared PostgreSQL instance. A maintenance window policy for production re-imports has not been defined. Should be documented in the operational runbook established during Phase 1.

---

## Sources

### Primary (HIGH confidence)
- [Nominatim Official Docs](https://nominatim.org/release-docs/latest/) — installation requirements, import guide, search/reverse API, FAQ, troubleshooting
- [mediagis/nominatim-docker GitHub](https://github.com/mediagis/nominatim-docker) — Docker image behavior, PBF_URL import pattern, K8s discussions
- [Valhalla Official Docs](https://valhalla.github.io/valhalla/) and [GitHub](https://github.com/valhalla/valhalla) — routing API, tile build config, memory tuning discussions
- [overv/openstreetmap-tile-server GitHub](https://github.com/Overv/openstreetmap-tile-server) — tile server Docker image
- [Switch2OSM](https://switch2osm.org/serving-tiles/) — canonical self-hosted tile serving guide
- [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) — confirms public API production use is prohibited
- [Geofabrik Georgia Download](https://download.geofabrik.de/north-america/us/georgia.html) — 333MB PBF verified 2026-04-04
- [PMTiles + Leaflet docs](https://docs.protomaps.com/pmtiles/leaflet) — vector tile Leaflet limitations confirmed
- [Martin Tile Server Official Docs](https://maplibre.org/martin/) — CORS config, MBTiles serving

### Secondary (MEDIUM confidence)
- [OSRM vs Valhalla comparison](https://github.com/Telenav/open-source-spec/blob/master/osrm/doc/osrm-vs-valhalla.md) — routing engine tradeoffs
- [Photon vs Nominatim comparison](https://www.geoapify.com/nominatim-vs-photon-geocoder/) — geocoding engine selection rationale
- [Deploying Valhalla on Kubernetes](https://medium.com/@itay.ankri/deploying-valhalla-routing-engine-on-kubernetes-using-valhalla-operator-2426e79ac746) — Valhalla K8s stateful workload pattern
- [State of Vector Tiles for Self-Hosting 2024](https://community.openstreetmap.org/t/state-of-vector-tiles-for-self-hosting-in-2024/117723) — raster vs. vector tile tradeoffs
- [Valhalla GitHub discussions](https://github.com/valhalla/valhalla/discussions/4816) — memory consumption, OOM behavior during tile build
- [Nominatim GitHub discussions](https://github.com/osm-search/Nominatim/discussions/3244) — import resumption behavior and rank thresholds

---
*Research completed: 2026-04-04*
*Ready for roadmap: yes*
