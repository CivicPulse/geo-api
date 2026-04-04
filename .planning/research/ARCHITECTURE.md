# Architecture Research

**Domain:** Self-hosted OSM geospatial stack integrated into existing FastAPI/PostGIS/K8s service
**Researched:** 2026-04-04
**Confidence:** HIGH (existing system) / MEDIUM (new OSM components — verified against official docs and community sources)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│              CONSUMERS (in-cluster K8s services)                     │
│         run-api          vote-api          other CivPulse services   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP (ClusterIP)
┌───────────────────────────────▼──────────────────────────────────────┐
│                        geo-api  (FastAPI)                            │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │                   CascadeOrchestrator                       │     │
│  │  normalize → spell-correct → exact-match → fuzzy →         │     │
│  │  LLM → consensus                                            │     │
│  └───────────────────────────┬─────────────────────────────────┘     │
│                              │ provider dispatch                     │
│  ┌──────────┬────────────────┬┴───────────┬──────────┬────────────┐  │
│  │ census   │ openaddresses  │ tiger(SQL) │   nad    │ osm (NEW)  │  │
│  │ (remote) │   (local)      │  (local)   │ (local)  │  (local)   │  │
│  └──────────┴────────────────┴────────────┴──────────┴────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  NEW ROUTES (v1.4)                                           │    │
│  │  GET  /tiles/{z}/{x}/{y}.png  → proxy → tile-server          │    │
│  │  GET  /search?q=...           → SearchService → Nominatim    │    │
│  │  GET  /reverse?lat=&lon=      → ReverseService → Nominatim   │    │
│  │  POST /route                  → RoutingService → Valhalla    │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────┬───────────────────────────────────────────────────────────┘
           │ internal HTTP (K8s ClusterIP / Docker bridge)
┌──────────┴───────────────────────────────────────────────────────────┐
│              OSM Service Layer  (new pods / containers)              │
│                                                                      │
│  ┌────────────────────┐  ┌───────────────────────┐  ┌────────────┐   │
│  │  tile-server       │  │  nominatim            │  │  valhalla  │   │
│  │  overv/osm-tile-srv│  │  mediagis/nominatim   │  │  ghcr.io/  │   │
│  │  port 8080         │  │  :5.x  port 8080      │  │  valhalla  │   │
│  │  /tile/{z}/{x}/{y} │  │  /search /reverse     │  │  port 8002 │   │
│  │                    │  │  /lookup /details     │  │  /route    │   │
│  └──────────┬─────────┘  └──────────┬────────────┘  └────┬───────┘   │
│             │                       │                     │           │
│  ┌──────────▼───────────────────────▼─────────────┐      │           │
│  │         osm-postgres (PostGIS)                 │      │           │
│  │  DB: osm_tiles   — osm2pgsql rendering schema  │      │           │
│  │  DB: nominatim   — Nominatim geocoding schema  │      │           │
│  └────────────────────────────────────────────────┘      │           │
│                                                           │           │
│  ┌────────────────────────────────────────────────────────▼───────┐   │
│  │  valhalla-data PVC                                             │   │
│  │  /custom_files/georgia-latest.osm.pbf + valhalla_tiles/       │   │
│  └────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
           │ shared PostgreSQL (existing, civpulse-infra namespace)
┌──────────▼───────────────────────────────────────────────┐
│  civpulse_geo DB (existing — unchanged)                  │
│  geocoding_results, addresses, admin_overrides, etc.     │
└──────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| geo-api | Orchestration, cascade pipeline, new route proxies, OSM provider integration | FastAPI (existing, extended) |
| OSMGeocodingProvider | GeocodingProvider ABC impl; wraps Nominatim /search endpoint | New `providers/osm.py` |
| SearchService | POI search, structured location lookup via Nominatim /search + /details | New `services/search.py` |
| ReverseService | Lat/lon to address via Nominatim /reverse endpoint | New `services/reverse.py` |
| RoutingService | Walk/drive directions via Valhalla /route, /matrix | New `services/routing.py` |
| TileProxy | Serves /tiles/{z}/{x}/{y}.png by proxying to tile-server | New route in `api/tiles.py` |
| tile-server | Renders raster PNG tiles from OSM PostGIS data; z/x/y tile cache | overv/openstreetmap-tile-server Docker image |
| nominatim | Geocoding + POI + reverse geocode engine; owns its own PostgreSQL schema | mediagis/nominatim:5.x Docker image |
| valhalla | Turn-by-turn routing engine; builds graph tiles from Georgia PBF | ghcr.io/valhalla/valhalla Docker image |
| osm-postgres | Dedicated PostgreSQL+PostGIS instance for tile-server and Nominatim data | postgis/postgis image, separate from civpulse_geo |
| osm-pipeline | One-shot init / K8s Job; downloads Georgia PBF, imports into both DBs | Shell script wrapped in Docker init or K8s Job |

## Recommended Project Structure

New files added to the existing structure:

```
src/civpulse_geo/
├── providers/
│   ├── base.py              # existing — GeocodingProvider / ValidationProvider ABCs
│   ├── osm.py               # NEW — OSMGeocodingProvider (Nominatim /search wrapper)
│   └── ...                  # existing providers unchanged
├── services/
│   ├── cascade.py           # MODIFIED — add "osm" to weight_map (~0.75)
│   ├── search.py            # NEW — POI search + location details (Nominatim)
│   ├── reverse.py           # NEW — reverse geocoding (Nominatim /reverse)
│   └── routing.py           # NEW — routing client (Valhalla /route, /matrix)
├── api/
│   ├── geocoding.py         # existing — unchanged
│   ├── tiles.py             # NEW — GET /tiles/{z}/{x}/{y}.png proxy
│   ├── search.py            # NEW — GET /search, GET /reverse
│   └── routing.py           # NEW — POST /route, POST /matrix
├── schemas/
│   └── routing.py           # NEW — RouteRequest / RouteResponse Pydantic models
└── config.py                # MODIFIED — add NOMINATIM_URL, VALHALLA_URL, OSM_TILE_URL

docker-compose.yml           # MODIFIED — add osm-db, tile-server, nominatim, valhalla
data/
└── osm/
    └── georgia-latest.osm.pbf  # downloaded by pipeline (gitignored)

k8s/
├── base/
│   ├── deployment.yaml          # existing — unchanged
│   ├── osm-deployments.yaml     # NEW — Nominatim, Valhalla, tile-server, osm-postgres
│   ├── osm-pvc.yaml             # NEW — tile cache, nominatim DB, valhalla data PVCs
│   └── kustomization.yaml       # MODIFIED — add new resources
└── overlays/
    ├── dev/
    └── prod/
```

### Structure Rationale

- **providers/osm.py:** Follows existing plugin pattern — implements GeocodingProvider ABC, registers via registry. Zero changes to cascade pipeline logic.
- **services/search.py and reverse.py:** New capabilities that don't fit the GeocodingProvider interface. Separate service classes avoid forcing POI search and reverse geocoding into the geocoding ABC.
- **services/routing.py:** Entirely new domain (routing). Standalone service client rather than a provider.
- **api/tiles.py:** Thin proxy — geo-api is the single internal entry point for all map services; consumers do not address tile-server directly.
- **Dedicated OSM PostgreSQL instance:** Nominatim and the tile-server osm2pgsql schema are write-heavy and schema-polluting. Keeping them separate from civpulse_geo prevents import load from degrading live geocoding requests.

## Architectural Patterns

### Pattern 1: Provider Plugin (existing pattern, extended)

**What:** New OSMGeocodingProvider implements the GeocodingProvider ABC. It calls Nominatim's `/search` endpoint and maps the JSON response to a GeocodingResult. Conditionally registered in the provider registry (same pattern as existing local providers).

**When to use:** For the address geocoding path only — when a freeform address needs lat/lon coordinates. OSM is a local provider (`is_local = True`), so it bypasses DB result caching.

**Trade-offs:**
- Pro: Zero cascade pipeline changes. Weight tuning uses existing weight_map. Fully integrated into consensus scoring.
- Con: Nominatim /search is optimized for place/POI search, not strict US address geocoding. Should be weighted lower than Tiger/NAD (recommended weight: ~0.75).

```python
# providers/osm.py (pattern sketch)
class OSMGeocodingProvider(GeocodingProvider):
    @property
    def is_local(self) -> bool:
        return True  # bypass DB cache write

    @property
    def provider_name(self) -> str:
        return "osm"

    async def geocode(self, address: str) -> GeocodingResult:
        # GET nominatim/search?q=address&format=jsonv2&countrycodes=us&limit=1
        ...
```

### Pattern 2: Internal Service Client (new services)

**What:** SearchService, ReverseService, and RoutingService are async classes that own an httpx.AsyncClient pointed at the internal Nominatim or Valhalla URL. Instantiated once at app startup (FastAPI lifespan), stored on `app.state`, injected into route handlers via FastAPI dependency injection.

**When to use:** For capabilities that don't fit the GeocodingProvider interface — POI search, reverse geocode, routing. These are not cascade providers; they are purpose-specific service clients.

**Trade-offs:**
- Pro: Clean separation; no impedance mismatch forcing routing into the geocoding ABC.
- Con: Three new service classes add boilerplate. Justified by the distinctly different request/response shapes.

```python
# services/routing.py (pattern sketch)
class RoutingService:
    def __init__(self, valhalla_url: str, client: httpx.AsyncClient):
        self._url = valhalla_url
        self._client = client

    async def route(self, request: RouteRequest) -> RouteResponse:
        payload = _build_valhalla_request(request)
        resp = await self._client.post(f"{self._url}/route", json=payload)
        return _parse_valhalla_response(resp.json())
```

### Pattern 3: Tile Proxy Route

**What:** A thin FastAPI route at `GET /tiles/{z}/{x}/{y}.png` that proxies requests to the internal tile-server. The tile-server is not exposed outside the cluster.

**When to use:** Always. Consumers configure Leaflet TileLayer with the geo-api tile URL. They never talk to the tile-server directly.

**Trade-offs:**
- Pro: Single internal URL for all geo services; tile-server implementation can be swapped without consumer changes.
- Con: Adds ~1ms proxy overhead per tile request. For high tile traffic in production, consider direct ClusterIP access.

### Pattern 4: OSM Data Pipeline as Init / K8s Job

**What:** The one-time (and periodic refresh) OSM data import runs as a shell script executed by an init container (Docker Compose) or a K8s Job. Downloads Georgia PBF from Geofabrik (~333MB), imports into the tile-server PostgreSQL DB, and copies the PBF to the Valhalla data volume. Nominatim handles its own import via `PBF_URL` env var on first startup.

**When to use:** On fresh environment setup and for quarterly or on-demand data refreshes.

**Trade-offs:**
- Pro: Decoupled from application runtime; pipeline failure does not affect geo-api availability.
- Con: Import is non-trivial — estimated 30-90 minutes for Georgia. Must complete before tile-server and Nominatim pass health checks.

## Data Flow

### Address Geocoding (cascade, with new OSM provider)

```
Consumer POST /geocode
    ↓
CascadeOrchestrator
    ↓ normalize + spell-correct
    ↓ exact-match (parallel dispatch to all providers)
        ├── census (remote, cached)    → HTTP → Census API
        ├── openaddresses (local)      → SQL → PostGIS staging
        ├── tiger (local)              → SQL → PostGIS tiger_geocoder
        ├── nad (local)                → SQL → PostGIS NAD staging
        └── osm (local, NEW)           → HTTP → Nominatim /search
    ↓ consensus scoring
       weights: census=0.90, nad=0.85, tiger=0.85, oa=0.80, osm=0.75
    ↓ auto-set OfficialGeocoding
    → GeocodingResponse
```

### POI Search (new)

```
Consumer GET /search?q=coffee+near+macon+ga
    ↓
geo-api SearchService
    ↓ GET nominatim:8080/search?q=...&format=jsonv2&countrycodes=us&limit=10
    → Nominatim → nominatim DB (PostGIS) → JSON array of POI results
    ↓ map to SearchResult schema
    → SearchResponse
```

### Reverse Geocoding (new)

```
Consumer GET /reverse?lat=32.84&lon=-83.63
    ↓
geo-api ReverseService
    ↓ GET nominatim:8080/reverse?lat=32.84&lon=-83.63&format=jsonv2
    → Nominatim → spatial nearest-neighbor query on nominatim DB
    ↓ map to ReverseResult schema
    → ReverseResponse
```

### Tile Serving (new)

```
Leaflet TileLayer GET /tiles/14/4537/6689.png
    ↓
geo-api TileProxy (api/tiles.py)
    ↓ GET tile-server:8080/tile/14/4537/6689.png
    → tile-server
        ↓ check mod_tile disk cache
        ↓ on miss: renderd → Mapnik → PostGIS osm_tiles DB → PNG
        → PNG bytes
    ↓ stream response
    → image/png
```

### Routing (new)

```
Consumer POST /route
  body: {origin: {lat, lon}, destination: {lat, lon}, costing: "pedestrian"}
    ↓
geo-api RoutingService
    ↓ POST valhalla:8002/route
      {locations: [...], costing: "pedestrian"}
    → Valhalla → reads prebuilt graph from /custom_files/valhalla_tiles/
    → turn-by-turn JSON (encoded polyline + maneuvers)
    ↓ map to RouteResponse schema
    → RouteResponse
```

### OSM Data Pipeline (one-time init / periodic refresh)

```
1. Download:   curl https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf
               (~333MB, updated daily by Geofabrik)

2. Tile DB:    osm2pgsql --slim -d osm_tiles georgia-latest.osm.pbf
               (runs inside tile-server init container or K8s Job)
               (~333MB PBF → ~10-15GB PostGIS data for Georgia)

3. Nominatim:  container starts with PBF_URL env var set to local file or remote URL
               mediagis/nominatim entrypoint runs osm2pgsql + indexing automatically
               (first start only; subsequent starts skip if DB populated)

4. Valhalla:   PBF copied to /custom_files/; valhalla Docker entrypoint builds graph tiles
               (detects new PBF on startup; subsequent starts skip if graph exists)
```

## Component Integration Points

### New vs. Modified Components

| Component | Status | Change Description |
|-----------|--------|--------------------|
| `providers/osm.py` | NEW | GeocodingProvider ABC impl wrapping Nominatim /search |
| `services/search.py` | NEW | POI search + location detail service client (Nominatim) |
| `services/reverse.py` | NEW | Reverse geocoding service client (Nominatim) |
| `services/routing.py` | NEW | Valhalla routing + matrix service client |
| `api/tiles.py` | NEW | Tile proxy route handler |
| `api/search.py` | NEW | /search and /reverse route handlers |
| `api/routing.py` | NEW | /route and /matrix route handlers |
| `schemas/routing.py` | NEW | Pydantic RouteRequest / RouteResponse models |
| `config.py` | MODIFIED | Add NOMINATIM_URL, VALHALLA_URL, OSM_TILE_URL settings |
| `services/cascade.py` | MODIFIED | Add "osm" key to weight_map (~0.75) |
| `providers/registry.py` | MODIFIED | Conditional OSMGeocodingProvider registration |
| `main.py` | MODIFIED | Register new routers; add service clients to app.state lifespan |
| `docker-compose.yml` | MODIFIED | Add osm-db, tile-server, nominatim, valhalla services + volumes |
| `k8s/base/` | MODIFIED | Add OSM service deployments, services, and PVCs |

### External Service Integration

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Nominatim (mediagis/nominatim:5.x) | Internal HTTP via httpx.AsyncClient | Port 8080. /search /reverse /lookup /status. Separate PostGIS schema. |
| tile-server (overv/openstreetmap-tile-server) | Internal HTTP proxy via geo-api | Port 8080. /tile/{z}/{x}/{y}.png. Needs its own PostGIS DB. |
| Valhalla (ghcr.io/valhalla/valhalla) | Internal HTTP via httpx.AsyncClient | Port 8002. /route /matrix /status. Reads prebuilt graph from PVC. |
| Geofabrik (geofabrik.de) | One-time / periodic HTTP download in pipeline Job | Georgia PBF ~333MB. No API key. Updated daily by Geofabrik. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| geo-api → Nominatim | HTTP/JSON (async httpx) | Nominatim must be healthy before OSM provider registers |
| geo-api → tile-server | HTTP (async httpx proxy) | Tile-server health not required for core geocoding |
| geo-api → Valhalla | HTTP/JSON (async httpx) | Valhalla needs 2-5 min for graph load; geo-api returns 503 gracefully until ready |
| tile-server → osm-postgres | PostgreSQL (internal) | tile-server owns osm_tiles DB |
| Nominatim → osm-postgres | PostgreSQL (internal) | Nominatim creates and manages its own schema (nominatim DB) |
| osm-pipeline → osm-postgres | PostgreSQL (osm2pgsql write-heavy) | Separate from civpulse_geo; import isolated |
| osm-pipeline → valhalla-data PVC | Volume file copy | PBF placed in /custom_files; Valhalla builds graph on startup |

## Suggested Build Order

The build order is driven by three hard dependencies:
1. OSM data (Georgia PBF) must exist before tile-server, Nominatim, and Valhalla can serve requests.
2. The OSM geocoding provider in geo-api depends on a reachable Nominatim instance.
3. The routing API in geo-api depends on a reachable Valhalla instance.

```
Phase A: OSM Data Pipeline
  Download Georgia PBF, define pipeline as Docker Compose init + K8s Job
  Unblocks all downstream phases

Phase B: Tile Server
  Stand up overv/openstreetmap-tile-server; import PBF into osm_tiles DB
  Validate with: curl http://tile-server:8080/tile/0/0/0.png

Phase C: Tile Proxy Route in geo-api
  Add GET /tiles/{z}/{x}/{y}.png proxy; wire OSM_TILE_URL to config
  Validate Leaflet TileLayer renders Georgia tiles

Phase D: Nominatim + OSM Geocoding Provider
  Stand up Nominatim; implement OSMGeocodingProvider; extend weight_map
  Validate: address in Macon GA returns result from "osm" provider in cascade

Phase E: POI Search + Reverse Geocoding Routes
  Implement SearchService, ReverseService; add /search and /reverse routes
  Validate: GET /search?q=Macon+GA returns POI results; GET /reverse?lat=... returns address

Phase F: Valhalla + Routing Routes
  Stand up Valhalla; implement RoutingService; add /route and /matrix routes
  Validate: POST /route returns turn-by-turn walk/drive directions in Georgia

Phase G: K8s Manifests + Health Probes
  Write Deployments, Services, PVCs for all new OSM services
  Extend kustomization.yaml; validate ArgoCD deploys successfully
```

**Rationale:**
- Phase A first: All three services need the Georgia PBF. Without the pipeline, nothing downstream can be validated end-to-end.
- Tile server (B) before geocoding (D): Tile serving is simpler to validate (request a PNG) and has no inter-service dependencies beyond the OSM DB. Proves Docker Compose OSM setup works before adding Nominatim complexity.
- Nominatim before Valhalla (D before F): OSM geocoding provider integrates into the cascade pipeline and is more critical path. Valhalla routing is lower priority.
- K8s manifests last (G): Validate all services in Docker Compose first, then translate to K8s. Avoids debugging K8s YAML before services are proven working locally.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Dev / single state | Single Docker Compose stack; all OSM services as Docker Compose services; 16GB RAM sufficient for Georgia (~333MB PBF) |
| K8s production (current scope) | Three separate Deployments (tile-server, nominatim, valhalla) + dedicated osm-postgres StatefulSet; PVCs for tile cache (~30GB), nominatim DB (~15GB), valhalla data (~5GB) |
| Multi-state expansion | Replace Georgia PBF with US South or full-US extract from Geofabrik; scale osm-postgres instance vertically; tile cache PVC grows proportionally; Nominatim RAM scales roughly linearly with PBF size |

### Scaling Priorities

1. **First bottleneck:** Tile rendering throughput. renderd is CPU-bound; tile cache misses (cold start, new zoom levels) are slow. Mitigation: pre-render zoom levels z0-z14 for Georgia after import completes.
2. **Second bottleneck:** Nominatim indexing memory during import. Georgia ~333MB PBF requires an estimated 4-6GB RAM for import (full planet needs 128GB+). Ensure osm-postgres has adequate `shared_buffers` and `work_mem`.

## Anti-Patterns

### Anti-Pattern 1: Sharing civpulse_geo PostgreSQL for OSM data

**What people do:** Import OSM data (tile-server schema + Nominatim schema) into the existing civpulse_geo PostgreSQL instance to minimize infrastructure.

**Why it's wrong:** Nominatim and the tile-server osm2pgsql import are write-heavy, long-running processes. Running them on the shared instance risks degrading live geocoding requests. Nominatim creates dozens of tables and custom extensions; schema collision is a real risk. Nominatim officially recommends its own database instance.

**Do this instead:** Run a separate `osm-postgres` container (postgis/postgis image) with its own volume. Both tile-server and Nominatim point to it. The civpulse_geo instance remains dedicated to the application.

### Anti-Pattern 2: Exposing tile-server, Nominatim, or Valhalla directly to consumers

**What people do:** Give consumers (run-api, vote-api) the direct ClusterIP or port of tile-server or Nominatim.

**Why it's wrong:** Bypasses geo-api as the single source of truth. Replacing the tile-server implementation later requires consumer changes instead of just a config change in geo-api.

**Do this instead:** All OSM capabilities are proxied through geo-api endpoints. Consumers only know `http://geo-api.civpulse-infra/tiles/...`, `http://geo-api.civpulse-infra/search`, etc.

### Anti-Pattern 3: Unconditional OSM provider registration

**What people do:** Always register OSMGeocodingProvider in the provider registry, even when Nominatim is not running.

**Why it's wrong:** Breaks existing provider startup validation. geo-api readiness check will fail if it tries to health-check a Nominatim that is not running (dev environments without the OSM profile).

**Do this instead:** Follow the existing conditional registration pattern (same as `_oa_data_available`, `_tiger_extension_available`). Check that `NOMINATIM_URL` is set and returns a healthy `/status` response before registering. If unreachable at startup, skip registration and log a warning.

### Anti-Pattern 4: Routing integrated into CascadeOrchestrator

**What people do:** Treat routing as another provider in the cascade pipeline.

**Why it's wrong:** Routing has a completely different input (origin + destination coordinates, not an address string) and output (polyline + maneuvers, not lat/lon + confidence score). Forcing it into the GeocodingProvider ABC is a category error.

**Do this instead:** Standalone `RoutingService` with its own API routes (`POST /route`, `POST /matrix`) that call Valhalla directly. No cascade involvement.

## Sources

- [Nominatim 5.2.0 Official Documentation](https://nominatim.org/release-docs/latest/) — HIGH confidence
- [mediagis/nominatim-docker GitHub](https://github.com/mediagis/nominatim-docker) — HIGH confidence
- [Valhalla Official Docs](https://valhalla.github.io/valhalla/) — HIGH confidence
- [Valhalla GitHub — routing engine](https://github.com/valhalla/valhalla) — HIGH confidence
- [overv/openstreetmap-tile-server GitHub](https://github.com/Overv/openstreetmap-tile-server) — HIGH confidence
- [Switch2OSM — Using a Docker container](https://switch2osm.org/serving-tiles/using-a-docker-container/) — HIGH confidence
- [Geofabrik Georgia Download Page](https://download.geofabrik.de/north-america/us/georgia.html) — HIGH confidence (333MB PBF, verified 2026-04-04)
- [Nominatim Installation Guide](https://nominatim.org/release-docs/latest/admin/Installation/) — HIGH confidence
- [Nominatim Architecture Overview](https://nominatim.org/release-docs/latest/develop/overview/) — HIGH confidence
- [Deploying Valhalla on Kubernetes via Operator](https://medium.com/@itay.ankri/deploying-valhalla-routing-engine-on-kubernetes-using-valhalla-operator-2426e79ac746) — MEDIUM confidence

---
*Architecture research for: CivPulse Geo API v1.4 Self-Hosted OSM Stack*
*Researched: 2026-04-04*
