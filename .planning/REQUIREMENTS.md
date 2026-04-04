# Requirements: CivPulse Geo API

**Defined:** 2026-04-04
**Core Value:** Single, reliable source of geocoded and validated address data across CivPulse systems — now expanded to include self-hosted map tiles, POI search, reverse geocoding, and routing.

## v1.4 Requirements

Requirements for Self-Hosted OSM Stack milestone. Each maps to roadmap phases.

### OSM Data Pipeline

- [x] **PIPE-01**: Operator can download the Georgia state OSM PBF extract via CLI command
- [x] **PIPE-02**: Operator can import PBF into Nominatim's dedicated PostgreSQL database via CLI command
- [x] **PIPE-03**: Operator can import PBF into the tile server's PostGIS database via CLI command
- [x] **PIPE-04**: Operator can build Valhalla routing graph from PBF via CLI command
- [x] **PIPE-05**: Operator can run a single unified CLI command that executes all imports (PIPE-01 through PIPE-04)

### Tile Serving

- [x] **TILE-01**: Tile server sidecar serves raster z/x/y PNG tiles for Georgia from Docker Compose
- [x] **TILE-02**: User can request tiles via FastAPI proxy endpoint `GET /tiles/{z}/{x}/{y}.png`
- [x] **TILE-03**: Tile proxy returns appropriate Cache-Control headers for downstream caching

### Geocoding & Search

- [x] **GEO-01**: NominatimProvider registered as 6th cascade provider with conditional startup guard
- [x] **GEO-02**: NominatimProvider participates in cross-provider consensus scoring (no cascade changes needed)
- [x] **GEO-03**: User can reverse geocode coordinates to an address via `GET /geocode/reverse`
- [x] **GEO-04**: User can search for POIs by category and location via `GET /poi/search`
- [x] **GEO-05**: User can constrain POI search to a bounding box via `bbox` query parameter

### Routing

- [ ] **ROUTE-01**: User can get walking directions between two points via `GET /route` with `mode=pedestrian`
- [ ] **ROUTE-02**: User can get driving directions between two points via `GET /route` with `mode=auto`
- [ ] **ROUTE-03**: Route response includes turn-by-turn maneuvers, encoded polyline, duration, and distance

### Infrastructure

- [x] **INFRA-01**: Nominatim runs as Docker Compose sidecar service with dedicated PostgreSQL
- [x] **INFRA-02**: Valhalla runs as Docker Compose sidecar service with pre-built graph on persistent volume
- [x] **INFRA-03**: Tile server runs as Docker Compose sidecar service
- [ ] **INFRA-04**: K8s manifests for all new sidecar services (Kustomize base + overlays)
- [ ] **INFRA-05**: Health probes updated to include Nominatim, tile server, and Valhalla readiness

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Routing Enhancements

- **FUTURE-01**: Route matrix (multiple origins → multiple destinations)
- **FUTURE-02**: Isochrone / reachability analysis

### Data Pipeline Enhancements

- **FUTURE-03**: Real-time OSM diff updates (minutely/hourly)

### Tile Serving Enhancements

- **FUTURE-04**: Vector tile serving (MapLibre GL JS frontend migration)

### Routing Modes

- **FUTURE-05**: Transit/multimodal routing (requires GTFS data)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Vector tiles (MVT/PMTiles) | Leaflet doesn't support natively; requires frontend migration to MapLibre GL JS |
| Planet/US-wide import | Georgia extract sufficient; 300GB+ disk and days of import for US |
| Real-time OSM diff updates | Georgia street data changes rarely; manual re-import sufficient |
| Transit/multimodal routing | Requires GTFS feed; no authoritative Georgia GTFS in OSM |
| Autocomplete/typeahead geocoding | geo-api is batch/point-lookup API; already in project Out of Scope |
| Photon geocoder | Elasticsearch overkill for GA-only; Nominatim uses existing PostGIS pattern |
| Google Maps / Mapbox | Paid per-request pricing; ToS prohibits caching; against project's self-sufficiency goal |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 24 | Complete |
| PIPE-02 | Phase 24 | Complete |
| PIPE-03 | Phase 24 | Complete |
| PIPE-04 | Phase 24 | Complete |
| PIPE-05 | Phase 24 | Complete |
| TILE-01 | Phase 25 | Complete |
| TILE-02 | Phase 25 | Complete |
| TILE-03 | Phase 25 | Complete |
| GEO-01 | Phase 26 | Complete |
| GEO-02 | Phase 26 | Complete |
| GEO-03 | Phase 26 | Complete |
| GEO-04 | Phase 26 | Complete |
| GEO-05 | Phase 26 | Complete |
| ROUTE-01 | Phase 27 | Pending |
| ROUTE-02 | Phase 27 | Pending |
| ROUTE-03 | Phase 27 | Pending |
| INFRA-01 | Phase 24 | Complete |
| INFRA-02 | Phase 24 | Complete |
| INFRA-03 | Phase 24 | Complete |
| INFRA-04 | Phase 28 | Pending |
| INFRA-05 | Phase 28 | Pending |

**Coverage:**
- v1.4 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-04*
*Last updated: 2026-04-04 after roadmap creation*
