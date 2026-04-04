# Phase 26: Nominatim Provider, Reverse Geocoding & POI Search - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning
**Mode:** Smart discuss (batch-accepted recommended defaults)

<domain>
## Phase Boundary

Extend the cascade geocoding pipeline with Nominatim as a 6th provider, and add two new endpoints: reverse geocoding (`/geocode/reverse`) and POI search (`/poi/search`). This phase delivers the HTTP-based NominatimProvider with conditional startup guard, wires it into the cascade, and creates 2 new FastAPI endpoints backed by the same provider. It does NOT implement custom Nominatim query parameters (polygon_geojson, addressdetails toggles), POI type filtering (amenity=cafe, etc.), or cross-provider POI aggregation (Google/OpenStreetMap merged results) — all deferred.

</domain>

<decisions>
## Implementation Decisions

### Nominatim Provider Architecture
- Transport: HTTP via `settings.osm_nominatim_url` (added in Phase 24, defaults to `http://nominatim:8080`) using `app.state.http_client` — matches the existing cascade HTTP client pattern
- Base class: Inherits from `civpulse_geo.providers.base.GeocodingProvider` ABC — returns the same `GeocodingResult` schema as other providers
- Trust weight: `weight_nominatim: float = 0.70` — midway between TIGER unrestricted (0.40) and NAD/Macon-Bibb (0.80) reflecting OSM's variable data quality
- Module location: `src/civpulse_geo/providers/nominatim.py` — matches existing provider layout

### Conditional Startup Guard
- Health probe: `GET {settings.osm_nominatim_url}/status` with 2s timeout during app startup; register NominatimProvider only on HTTP 200
- Failure mode: Warn + skip registration (mirrors pattern from `openaddresses_points table is empty — provider not registered` in `main.py`)
- Re-probe: None — once-at-startup only, consistent with other conditional providers (OpenAddresses, Tiger, NAD, Macon-Bibb)
- Explicit toggle: New `settings.nominatim_enabled: bool = True` allows admins to force-disable even when nominatim is reachable

### New Endpoints
- Reverse geocoding: `GET /geocode/reverse?lat={float}&lon={float}` — mounted on existing `/geocode` router (APIRouter prefix)
- POI search: `GET /poi/search?q={str}` with either `lat={float}&lon={float}&radius={int}` (default radius=1000m) OR `bbox={float,float,float,float}` (west,south,east,north) — mutually exclusive; 400 if both or neither provided
- New Pydantic schemas in `src/civpulse_geo/schemas/`: `ReverseGeocodeResponse` (address, lat, lon, place_id, raw_nominatim_response dict), `POIResult` (name, lat, lon, type, address), `POISearchResponse` (results: list[POIResult])
- Error behavior: 404 when nominatim returns empty results (no address/POI found); 503 when NominatimProvider was not registered at startup (e.g., nominatim service was unreachable)

### Claude's Discretion
- Exact Nominatim HTTP endpoint mapping (`/search?q=`, `/reverse?lat=&lon=`, `/search?q=&viewbox=` etc.) — follow upstream Nominatim API docs
- Whether to introduce a shared `_NominatimClient` helper class or inline HTTP calls per method — keep minimal, extract only if 3+ call sites emerge
- POI search result limit (e.g., max 50) — reasonable default, not operator-configurable this phase
- Caching of reverse/POI results — not this phase (can reuse the cascade cache pattern later)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GeocodingProvider` ABC at `src/civpulse_geo/providers/base.py` — define `async def geocode(self, address: str) -> GeocodingResult`
- `GeocodingResult` schema at `src/civpulse_geo/providers/schemas.py`
- `settings.osm_nominatim_url` (added Phase 24), `app.state.http_client` (existing httpx singleton)
- Weight config pattern: `settings.weight_census`, `weight_openaddresses`, etc. in `config.py`
- Existing `/geocode` router at `src/civpulse_geo/api/geocoding.py` (APIRouter prefix=/geocode)
- `load_providers()` helper + `app.state.providers` dict pattern in `main.py:78-116`

### Established Patterns
- Conditional provider registration with data-availability probes (`_oa_data_available`, `_tiger_extension_available`, etc.)
- `logger.info("{Provider} provider registered")` / `logger.warning("... — {Provider} provider not registered")`
- Cascade registers providers keyed by string name, uses trust weight from settings
- Pydantic response models live in `src/civpulse_geo/schemas/<domain>.py`

### Integration Points
- New: `src/civpulse_geo/providers/nominatim.py` (NominatimGeocodingProvider)
- New: `src/civpulse_geo/api/poi.py` (POI search router)
- New: `src/civpulse_geo/schemas/reverse.py` + `schemas/poi.py`
- Modify: `src/civpulse_geo/config.py` — add `nominatim_enabled`, `weight_nominatim`
- Modify: `src/civpulse_geo/main.py` — add `_nominatim_reachable()` probe + conditional registration; mount new `/poi` router
- Modify: `src/civpulse_geo/api/geocoding.py` — add `GET /reverse` route
- Modify: `src/civpulse_geo/services/cascade.py` — register `weight_nominatim` in the trust weight lookup

</code_context>

<specifics>
## Specific Ideas

- NominatimProvider must be the 6th provider (after census, openaddresses, postgis_tiger, national_address_database, macon_bibb)
- `source=nominatim` must appear in cascade response results when nominatim is running + data loaded (ROADMAP criterion 1)
- Conditional guard MUST use HTTP health probe (post-Phase-24 refactor — osm-postgres is gone, each sidecar runs its own PG)
- POI search bbox format: `west,south,east,north` (standard Nominatim `viewbox` order with bounded=1)

</specifics>

<deferred>
## Deferred Ideas

- Custom Nominatim query parameters (polygon_geojson, addressdetails tuning)
- POI type filtering via `amenity=cafe`, `shop=bakery`, etc.
- Cross-provider POI aggregation (combining nominatim with Overpass, Google Places, etc.)
- Caching of reverse/POI results
- Rate limiting specific to POI search
- Pagination on POI search (larger result sets)

</deferred>
