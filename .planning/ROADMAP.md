# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- ✅ **v1.1 Local Data Sources** — Phases 7-11 (shipped 2026-03-29)
- ✅ **v1.2 Cascading Address Resolution** — Phases 12-16 (shipped 2026-03-29)
- ✅ **v1.3 Production Readiness & Deployment** — Phases 17-23 (shipped 2026-04-03)
- 🚧 **v1.4 Self-Hosted OSM Stack** — Phases 24-28 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-6) — SHIPPED 2026-03-19</summary>

- [x] **Phase 1: Foundation** — PostGIS schema, canonical key strategy, plugin contract, and project scaffolding (3/3 plans)
- [x] **Phase 2: Geocoding** — Multi-provider geocoding with cache, official record, and admin override (2/2 plans)
- [x] **Phase 3: Validation and Data Import** — USPS address validation and Bibb County GIS CLI import (3/3 plans)
- [x] **Phase 4: Batch and Hardening** — Batch endpoints, per-item error handling, and HTTP layer completion (2/2 plans)
- [x] **Phase 5: Fix Admin Override & Import Order** — Admin override table write fix and import-order documentation (1/1 plan)
- [x] **Phase 6: Documentation & Traceability Cleanup** — SUMMARY frontmatter and ROADMAP checkbox fixes (1/1 plan)

Full details archived in `milestones/v1.0-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.1 Local Data Sources (Phases 7-11) — SHIPPED 2026-03-29</summary>

- [x] **Phase 7: Pipeline Infrastructure** — Direct-return pipeline bypass, provider ABC extension, and staging table migrations (2/2 plans) — completed 2026-03-22
- [x] **Phase 8: OpenAddresses Provider** — OA geocoding and validation from .geojson.gz files via PostGIS staging table (2/2 plans) — completed 2026-03-22
- [x] **Phase 9: Tiger Provider** — Tiger geocoding and validation via PostGIS geocode() and normalize_address() SQL functions (2/2 plans) — completed 2026-03-24
- [x] **Phase 10: NAD Provider** — NAD geocoding and validation from 80M-row staging table with bulk COPY import (2/2 plans) — completed 2026-03-24
- [x] **Phase 11: Fix Batch Endpoint Local Provider Serialization** — Batch endpoints include local provider results in every response item (1/1 plan) — completed 2026-03-24

Full details archived in `milestones/v1.1-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.2 Cascading Address Resolution (Phases 12-16) — SHIPPED 2026-03-29</summary>

- [x] **Phase 12: Correctness Fixes and DB Prerequisites** — Fix 4 known provider defects and add GIN trigram indexes (2/2 plans) — completed 2026-03-29
- [x] **Phase 13: Spell Correction and Fuzzy/Phonetic Matching** — Offline spell correction and pg_trgm + Double Metaphone fallback (2/2 plans) — completed 2026-03-29
- [x] **Phase 14: Cascade Orchestrator and Consensus Scoring** — 6-stage cascade pipeline with cross-provider consensus and auto-set official (3/3 plans) — completed 2026-03-29
- [x] **Phase 15: LLM Sidecar** — Local Ollama qwen2.5:3b for address correction when deterministic stages fail (3/3 plans) — completed 2026-03-29
- [x] **Phase 16: Audit Gap Closure** — FuzzyMatcher startup wiring, legacy 5-tuple fix, Phase 13 verification (1/1 plan) — completed 2026-03-29

Full details archived in `milestones/v1.2-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.3 Production Readiness & Deployment (Phases 17-23) — SHIPPED 2026-04-03</summary>

- [x] **Phase 17: Tech Debt Resolution** — Resolve all 4 known runtime defects (2/2 plans) — completed 2026-03-29
- [x] **Phase 18: Code Review** — Parallel security, stability, performance audit (3/3 plans) — completed 2026-03-30
- [x] **Phase 19: Dockerfile and Database Provisioning** — Multi-stage Docker image + DB provisioning (2/2 plans) — completed 2026-03-30
- [x] **Phase 20: Health, Resilience, and K8s Manifests** — Health probes, graceful shutdown, K8s manifests (3/3 plans) — completed 2026-03-30
- [x] **Phase 21: CI/CD Pipeline** — GitHub Actions CI/CD with Trivy scan (2/2 plans) — completed 2026-03-30
- [x] **Phase 22: Observability** — Structured logging, Prometheus metrics, OTel traces (3/3 plans) — completed 2026-03-30
- [x] **Phase 23: E2E Testing, Load Baselines, and Final Validation** — Full E2E + load + observability + validation (9/9 plans) — completed 2026-04-03

Full details archived in `milestones/v1.3-ROADMAP.md`.

</details>

### 🚧 v1.4 Self-Hosted OSM Stack (In Progress)

**Milestone Goal:** Add a fully self-hosted OpenStreetMap-based geospatial stack — tile serving, geocoding, POI search, reverse geocoding, and routing — eliminating all third-party map service dependencies.

- [x] **Phase 24: OSM Data Pipeline & Docker Compose Sidecars** — Georgia PBF download, dedicated osm-postgres instance, Nominatim/tile-server/Valhalla Docker Compose services, and unified CLI pipeline command (completed 2026-04-04)
- [x] **Phase 25: Tile Server & FastAPI Tile Proxy** — Tile sidecar serving raster z/x/y PNGs and FastAPI proxy endpoint with caching headers (completed 2026-04-04)
- [x] **Phase 26: Nominatim Provider, Reverse Geocoding & POI Search** — NominatimProvider in cascade pipeline, reverse geocode endpoint, and POI search endpoint (completed 2026-04-04)
- [ ] **Phase 27: Valhalla Routing** — Walking and driving route endpoints backed by Valhalla sidecar with pre-built graph
- [ ] **Phase 28: K8s Manifests & Health Probe Updates** — Kustomize manifests for all new sidecars and updated health probes for Nominatim, tile server, and Valhalla

## Phase Details

### Phase 24: OSM Data Pipeline & Docker Compose Sidecars
**Goal**: Operator can download the Georgia OSM PBF and import it into all three OSM services via CLI; all three sidecar services (Nominatim, tile server, Valhalla) run locally via Docker Compose
**Depends on**: Phase 23
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05, INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. Operator runs a single CLI command and the Georgia PBF downloads, Nominatim database is populated, tile database is populated, and Valhalla graph is built
  2. `docker compose up` starts all three OSM sidecar services alongside the existing geo-api stack without errors
  3. Nominatim, the tile server, and Valhalla each connect to the dedicated `osm-postgres` instance (not civpulse_geo)
  4. The unified pipeline CLI command succeeds end-to-end from scratch on a clean environment
**Plans**: 5 plans
Plans:
- [x] 24-01-PLAN.md — Wave 0 test scaffolding + PBF gitignore + data/osm directory
- [x] 24-02-PLAN.md — Docker Compose OSM profile (osm-postgres, nominatim, tile-server, valhalla) + init script + config settings
- [x] 24-03-PLAN.md — osm-download CLI command with retry/backoff and idempotency (PIPE-01)
- [x] 24-04-PLAN.md — osm-import-nominatim, osm-import-tiles, osm-build-valhalla CLI commands (PIPE-02, PIPE-03, PIPE-04)
- [x] 24-05-PLAN.md — osm-pipeline unified command + manual Docker Compose stack verification (PIPE-05)
**UI hint**: no

### Phase 25: Tile Server & FastAPI Tile Proxy
**Goal**: Leaflet frontends can request raster PNG map tiles through geo-api's tile proxy endpoint
**Depends on**: Phase 24
**Requirements**: TILE-01, TILE-02, TILE-03
**Success Criteria** (what must be TRUE):
  1. `GET /tiles/{z}/{x}/{y}.png` returns a valid PNG image for Georgia coordinates
  2. Tile response includes `Cache-Control` headers appropriate for downstream caching
  3. Tile requests that miss the tile server return a 404 (not a 500), and geo-api logs the failure without crashing
**Plans**: 2 plans
Plans:
- [x] 25-01-PLAN.md — TDD test scaffolding (8 tests) + tiles router skeleton mounted in main.py (TILE-02)
- [x] 25-02-PLAN.md — Streaming httpx proxy with Cache-Control, ETag forward, 404 passthrough, 502 on upstream failure (TILE-01, TILE-03)
**UI hint**: no

### Phase 26: Nominatim Provider, Reverse Geocoding & POI Search
**Goal**: The cascade geocoding pipeline includes Nominatim as a 6th provider, and callers can reverse geocode coordinates and search for nearby POIs
**Depends on**: Phase 24
**Requirements**: GEO-01, GEO-02, GEO-03, GEO-04, GEO-05
**Success Criteria** (what must be TRUE):
  1. `GET /geocode?address=...` response includes a result with `source=nominatim` when Nominatim is running and data is loaded
  2. `GET /geocode/reverse?lat=...&lon=...` returns a valid address string for Georgia coordinates
  3. `GET /poi/search?q=...&lat=...&lon=...` returns a list of POI results near the given location
  4. `GET /poi/search?q=...&bbox=...` constrains results to the given bounding box
  5. NominatimProvider is not registered at startup when the `nominatim` HTTP service is unreachable (conditional startup guard; post-Phase-24 refactor: osm-postgres was removed, so the guard probes nominatim's HTTP endpoint directly instead of a shared PG)
**Plans**: 5 plans
Plans:
- [x] 26-01-PLAN.md — TDD test scaffolding (19 tests): nominatim provider, /geocode/reverse, /poi/search contracts (GEO-01..05)
- [x] 26-02-PLAN.md — NominatimGeocodingProvider HTTP class against /search endpoint (GEO-01, GEO-02)
- [x] 26-03-PLAN.md — Conditional startup guard + cascade weight_nominatim + config toggle + KNOWN_PROVIDERS (GEO-01, GEO-05)
- [x] 26-04-PLAN.md — GET /geocode/reverse endpoint + ReverseGeocodeResponse schema (GEO-03)
- [x] 26-05-PLAN.md — GET /poi/search endpoint + POI schemas + bbox/radius handling + router mount (GEO-03, GEO-04, GEO-05)
**UI hint**: no

### Phase 27: Valhalla Routing
**Goal**: Callers can request walking and driving turn-by-turn routes between two points; route responses include maneuvers, polyline, duration, and distance
**Depends on**: Phase 24
**Requirements**: ROUTE-01, ROUTE-02, ROUTE-03
**Success Criteria** (what must be TRUE):
  1. `GET /route?start=...&end=...&mode=pedestrian` returns a valid walking route for two Georgia points
  2. `GET /route?start=...&end=...&mode=auto` returns a valid driving route for two Georgia points
  3. Route response includes turn-by-turn maneuvers, an encoded polyline, total duration in seconds, and total distance in meters
**Plans**: 3 plans
Plans:
- [x] 27-01-PLAN.md — TDD test scaffolding (11 contract tests) for GET /route (ROUTE-01, ROUTE-02, ROUTE-03)
- [x] 27-02-PLAN.md — route.py router implementation + RouteResponse/Maneuver schemas (ROUTE-01, ROUTE-02, ROUTE-03)
- [ ] 27-03-PLAN.md — valhalla_enabled setting + _valhalla_reachable probe + main.py wiring + router mount
**UI hint**: no

### Phase 28: K8s Manifests & Health Probe Updates
**Goal**: All new OSM sidecar services are deployable via Kustomize to dev and prod, and geo-api's health endpoints reflect the readiness of Nominatim, tile server, and Valhalla
**Depends on**: Phase 27
**Requirements**: INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. `GET /health/ready` reports the readiness status of Nominatim, tile server, and Valhalla alongside existing providers
  2. Kustomize `kustomization.yaml` includes manifests for osm-postgres, Nominatim, tile server, and Valhalla with resource limits defined
  3. ArgoCD syncs the new manifests to dev without errors
**Plans**: TBD
**UI hint**: no

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-6 | v1.0 | — | Complete | 2026-03-19 |
| 7-11 | v1.1 | — | Complete | 2026-03-29 |
| 12-16 | v1.2 | — | Complete | 2026-03-29 |
| 17-23 | v1.3 | — | Complete | 2026-04-03 |
| 24. OSM Data Pipeline & Docker Compose Sidecars | v1.4 | 5/5 | Complete    | 2026-04-04 |
| 25. Tile Server & FastAPI Tile Proxy | v1.4 | 2/2 | Complete    | 2026-04-04 |
| 26. Nominatim Provider, Reverse Geocoding & POI Search | v1.4 | 5/5 | Complete    | 2026-04-04 |
| 27. Valhalla Routing | v1.4 | 2/3 | In Progress|  |
| 28. K8s Manifests & Health Probe Updates | v1.4 | 0/TBD | Not started | - |
