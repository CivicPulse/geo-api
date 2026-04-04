# Feature Research

**Domain:** Self-hosted OSM geospatial stack — tile serving, geocoding/POI search, routing
**Researched:** 2026-04-04
**Confidence:** HIGH (tile serving, Nominatim API, Valhalla API verified against official docs; architecture patterns verified against Switch2OSM and Valhalla docs)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the CivPulse ecosystem consumers (voter-web, run-api canvassing) will assume exist. Missing these = the milestone fails its stated goal.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Raster tile endpoint (`/tiles/{z}/{x}/{y}.png`) | Leaflet frontends speak z/x/y — this is the universal tile contract | MEDIUM | overv/openstreetmap-tile-server Docker image bundles osm2pgsql + renderd + mod_tile + mapnik; single compose service |
| Georgia OSM data pipeline | All downstream features are inert without data loaded | MEDIUM | Geofabrik provides `us/georgia-latest.osm.pbf`; osm2pgsql imports to PostGIS for tiles; Nominatim imports separately |
| Forward geocoding via OSM/Nominatim provider | Cascade pipeline slot — plugs into existing 5-provider architecture as a 6th provider | MEDIUM | Nominatim HTTP API (free-form + structured); httpx async call; fits existing `GeocodingProvider` ABC |
| Reverse geocoding (`/geocode/reverse?lat=&lon=`) | Polling-place lookups and voter address validation need coordinate → address; stated in v1.4 scope | MEDIUM | Nominatim `/reverse` endpoint returns closest OSM object's address; thin FastAPI proxy endpoint |
| POI search by category and location | Voter apps need "polling places near X"; canvassing apps need "government offices near Y" | MEDIUM | Nominatim structured query with `amenity=` tag or bounded `[amenity]`-style special phrase |
| Walking route (`/route?mode=pedestrian`) | Canvassing: door-to-door walking directions are the core run-api use case | MEDIUM | Valhalla pedestrian costing; returns turn-by-turn maneuvers + encoded polyline + duration/distance |
| Driving route (`/route?mode=auto`) | Polling-place directions: voters drive, not walk | LOW | Valhalla auto costing; same endpoint shape as walking, different `costing` parameter |

### Differentiators (Competitive Advantage)

Features that make geo-api more useful than a pass-through to public OSM APIs, specific to CivPulse's needs.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Nominatim as cascade provider (not standalone) | Nominatim results flow through existing consensus scoring, admin-override, and caching infrastructure — no orphaned data path | MEDIUM | Implement `NominatimProvider` following existing `GeocodingProvider` ABC; `is_local=True` since it is internal; bypasses DB cache like other local providers |
| Tile proxy via FastAPI middleware | Centralizes tile auth, rate limiting, and future caching in one place; Leaflet frontend never knows the internal tile server address | LOW | Simple `httpx` reverse proxy route in geo-api; passes z/x/y through to renderd |
| Valhalla as optional Docker Compose sidecar | Routing stays fully air-gapped; same operational model as Ollama LLM sidecar already in the project (`--profile routing`) | LOW | Add `valhalla` service to docker-compose.yml; geo-api proxies `/route` to it |
| Single OSM data pipeline CLI command | Operators run one command to download Georgia PBF, import to Nominatim, import to tile PostGIS, and build Valhalla graph | MEDIUM | Extend existing Typer CLI; mirrors the existing `gis-import` CLI pattern |
| Bounding-box constrained POI search | Return only POIs within a map viewport — useful for polling-place overlays | LOW | Nominatim `viewbox=` + `bounded=1` parameters; expose as query params on FastAPI endpoint |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Vector tiles (MVT/PMTiles) instead of raster | Smaller payloads, style flexibility, modern standard | Leaflet does not support vector tiles natively; requires MapLibre bridge plugin or full MapLibre GL JS migration — a separate large frontend project | Raster PNG tiles via mod_tile/renderd — zero frontend change, proven stack, works today |
| Planet-wide or US-wide import | "While we're at it" scope creep | Georgia PBF is ~500MB; Nominatim for US requires 300GB+ disk and days of import time; tile DB for the US south is ~50GB; not justified for a voter-district app | Georgia state extract only; re-import is a CLI command if scope expands |
| Real-time OSM diff updates (minutely/hourly) | Data freshness | Adds continuous osm2pgsql update pipeline, Nominatim update daemon, and significant operational complexity. Georgia street data changes rarely. | Manual re-import via CLI on a monthly or election-cycle cadence |
| Routing for transit/multimodal | "What if voters take the bus?" | Requires GTFS feed import into Valhalla and a separate transit data maintenance pipeline; no authoritative GTFS for Georgia is bundled with OSM | Walking + driving covers the stated use cases (canvassing + polling place directions) |
| Autocomplete/typeahead geocoding | UX improvement for address entry | geo-api is a batch/point-lookup API consumed by internal services. Autocomplete adds latency-sensitive interactive endpoints that do not fit the model. Already in project's Out of Scope. | Consumer apps implement typeahead using Photon or Mapbox; geo-api provides authoritative lookup after selection |
| Photon geocoder instead of Nominatim | Photon is faster for search-as-you-type | Photon is built on Elasticsearch (~90-200GB index for full planet); overkill for Georgia-only; Nominatim uses PostgreSQL + PostGIS which the project already runs; Photon's advantage is autocomplete, which is an anti-feature above | Nominatim structured search excels at the known-address lookup pattern geo-api already uses |
| Isochrone / reachability analysis | "Show all voters within 10-min walk" | Not in v1.4 scope; separate feature with its own data model and API shape | Defer to v2; Valhalla `/isochrone` endpoint exists when needed |

---

## Feature Dependencies

```
[Georgia OSM data pipeline]
    └──required-by──> [Tile server renders tiles]
    └──required-by──> [Nominatim geocoding/POI/reverse]
    └──required-by──> [Valhalla routing]

[Nominatim sidecar service running]
    └──required-by──> [NominatimProvider in cascade]
    └──required-by──> [POI search endpoint]
    └──required-by──> [Reverse geocoding endpoint]

[Valhalla sidecar service running]
    └──required-by──> [Walking route endpoint]
    └──required-by──> [Driving route endpoint]

[Tile server sidecar (renderd/mod_tile) running]
    └──required-by──> [Tile proxy endpoint in FastAPI]

[Existing GeocodingProvider ABC]
    └──extended-by──> [NominatimProvider]

[Existing cascade pipeline]
    └──enhanced-by──> [NominatimProvider as 6th provider]
```

### Dependency Notes

- **Georgia OSM data pipeline is the root dependency.** Nothing else works without the PBF imported. This must be Phase 1 of the milestone.
- **Tile server and Nominatim use separate data stores.** osm2pgsql imports to a PostGIS database for rendering; Nominatim has its own internal PostgreSQL database. They share the same PBF source file but require separate imports.
- **NominatimProvider extends existing provider ABC with zero cascade changes.** New provider registers conditionally (same `_nominatim_available` startup check pattern already used for Tiger, NAD, OA providers).
- **Valhalla routing is independent of Nominatim.** Routing needs the OSM PBF converted to Valhalla tiles (`valhalla_build_tiles`), not Nominatim's database. The two imports are separate.
- **Tile proxy in FastAPI depends on tile server sidecar.** FastAPI does not render tiles; it proxies to renderd. If the tile server sidecar is not running, the proxy returns 503.
- **Reverse geocoding is a new endpoint shape.** Existing cascade is address-in → coordinates-out. Reverse is coordinates-in → address-out. This is a new route (`/geocode/reverse`), not a cascade extension.

---

## MVP Definition

### Launch With (v1.4)

Minimum viable product — what is needed to eliminate third-party map service dependencies.

- [ ] Georgia OSM data pipeline CLI command (downloads PBF, imports to Nominatim DB, imports to tile PostGIS, builds Valhalla graph)
- [ ] Tile server sidecar (Docker Compose service) serving z/x/y PNGs for Georgia
- [ ] Tile proxy endpoint in FastAPI (`GET /tiles/{z}/{x}/{y}.png`)
- [ ] `NominatimProvider` registered in cascade pipeline (forward geocoding, 6th provider)
- [ ] Reverse geocoding endpoint (`GET /geocode/reverse`)
- [ ] POI search endpoint (`GET /poi/search`)
- [ ] Walking route endpoint (`GET /route` with `mode=pedestrian`)
- [ ] Driving route endpoint (`GET /route` with `mode=auto`)

### Add After Validation (v1.4.x)

- [ ] Bounding-box constrained POI search — add `bbox` query param once polling-place overlay map is being actively built
- [ ] Route matrix (multiple origins → multiple destinations) — useful for batch canvass route optimization when run-api integrates

### Future Consideration (v2+)

- [ ] Isochrone / reachability analysis — when "voters within N minutes" is a stated product requirement
- [ ] Real-time OSM diff updates — when data freshness becomes a complaint from operators
- [ ] Vector tile serving — when frontend migrates from Leaflet to MapLibre GL JS
- [ ] Transit routing — when GTFS data is available and multimodal is a requirement

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Georgia OSM data pipeline | HIGH | MEDIUM | P1 |
| Tile server sidecar + FastAPI proxy | HIGH | MEDIUM | P1 |
| NominatimProvider in cascade | HIGH | LOW | P1 |
| Reverse geocoding endpoint | HIGH | LOW | P1 |
| POI search endpoint | HIGH | LOW | P1 |
| Walking route (Valhalla pedestrian) | HIGH | MEDIUM | P1 |
| Driving route (Valhalla auto) | HIGH | LOW | P1 |
| Bounding-box POI search | MEDIUM | LOW | P2 |
| Route matrix | MEDIUM | MEDIUM | P2 |
| Isochrone analysis | LOW | MEDIUM | P3 |
| Real-time OSM diff updates | LOW | HIGH | P3 |
| Vector tiles | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.4 launch (milestone goal)
- P2: Should have, add after core is validated
- P3: Nice to have, future milestone

---

## Competitor Feature Analysis

The "competitors" here are the third-party services geo-api is replacing, plus the public OSM APIs that cannot be used at production scale.

| Feature | OSM Public APIs (tile.openstreetmap.org + nominatim.org) | Google Maps / Mapbox | Our Approach |
|---------|-----------------------------------------------------------|----------------------|--------------|
| Tile serving | Free but ToS-restricted; cannot be used for production apps | Paid, per-request pricing | Self-hosted renderd/mod_tile; no usage limits, no cost per tile |
| Forward geocoding | Nominatim public (1 req/s rate limit, no caching allowed) | Paid; ToS prohibits result caching | Self-hosted Nominatim; no rate limit; results cacheable; integrates with existing cascade |
| Reverse geocoding | Nominatim public (rate-limited) | Paid | Self-hosted Nominatim; no rate limit |
| POI search | Nominatim public (rate-limited) | Paid Places API | Self-hosted Nominatim bounded `amenity=` search |
| Routing | OSRM public demo (not for production) | Paid Directions API | Self-hosted Valhalla; walking + driving; no cost |
| Data privacy | Queries logged by OSM Foundation / Google | Queries logged by provider | Fully air-gapped; no query data leaves the cluster |
| Data freshness | Weekly planet updates (OSM); continuous (Google) | Continuous | Georgia PBF from Geofabrik; manual re-import on operator schedule |

---

## Integration Notes for Existing Architecture

Specific to integrating v1.4 features into geo-api without disrupting v1.0–v1.3 functionality.

**NominatimProvider:**
- Implement `NominatimProvider(GeocodingProvider)` with `is_local = True`
- Startup guard: `_nominatim_available` checks `NOMINATIM_URL` env var and HTTP health check
- Conditional registration follows identical pattern to `_oa_data_available`, `_nad_data_available`, `_tiger_extension_available`
- No DB caching (local provider convention already established in v1.1)
- Participates in cross-provider consensus scoring automatically (no orchestrator changes needed)

**Tile proxy:**
- Single FastAPI route `GET /tiles/{z}/{x}/{y}.png` proxies to internal renderd HTTP port
- No auth (internal service network model)
- Add `Cache-Control: public, max-age=86400` response headers to allow Nginx/K8s ingress to cache tiles

**Routing:**
- New endpoint family `GET /route` with `origin`, `destination`, `mode` params
- Thin proxy to Valhalla HTTP API (port 8002 internal)
- Normalize Valhalla response to a GeoJSON-compatible shape for frontend consumption

---

## Sources

- [Nominatim Search API docs](https://nominatim.org/release-docs/latest/api/Search/) — HIGH confidence, official
- [Nominatim Reverse API docs](https://nominatim.org/release-docs/latest/api/Reverse/) — HIGH confidence, official
- [Valhalla API Reference](https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/) — HIGH confidence, official
- [Switch2OSM Tile Serving Guide](https://switch2osm.org/serving-tiles/) — HIGH confidence, official OSM community guide
- [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) — HIGH confidence, confirms public API cannot be used for production apps
- [Overv openstreetmap-tile-server Docker image](https://github.com/Overv/openstreetmap-tile-server) — MEDIUM confidence, widely used community Docker image
- [Valhalla GitHub](https://github.com/valhalla/valhalla) — HIGH confidence, official source
- [Photon vs Nominatim comparison](https://www.geoapify.com/nominatim-vs-photon-geocoder/) — MEDIUM confidence, third-party analysis
- [OSRM vs Valhalla technical comparison](https://github.com/Telenav/open-source-spec/blob/master/osrm/doc/osrm-vs-valhalla.md) — MEDIUM confidence, detailed engineering analysis
- [PMTiles and Leaflet](https://docs.protomaps.com/pmtiles/leaflet) — HIGH confidence, official Protomaps docs confirming vector tile limitations with Leaflet

---

*Feature research for: CivPulse geo-api v1.4 Self-Hosted OSM Stack*
*Researched: 2026-04-04*
