# Phase 25: Tile Server & FastAPI Tile Proxy - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning
**Mode:** Smart discuss (batch-accepted recommended defaults)

<domain>
## Phase Boundary

Leaflet frontends can request raster PNG map tiles through geo-api's tile proxy endpoint. geo-api exposes `GET /tiles/{z}/{x}/{y}.png` which proxies to the upstream `tile-server` sidecar (see Phase 24). This phase delivers the FastAPI route, streaming response wiring, cache headers, and upstream failure handling. It does NOT implement vector tiles, tile pre-warming, CDN edge caching, or rate limiting (all deferred).

</domain>

<decisions>
## Implementation Decisions

### API Contract
- Route: `GET /tiles/{z}/{x}/{y}.png` — matches ROADMAP success criteria verbatim
- Router mount: `APIRouter(prefix="/tiles", tags=["tiles"])` — mirrors existing `/geocode`, `/health` pattern from `src/civpulse_geo/api/geocoding.py` and `health.py`
- Response type: `fastapi.responses.StreamingResponse` streaming the upstream PNG bytes with `media_type="image/png"` (avoids full in-memory buffering for 50-200KB tiles)
- Upstream URL: derived from `settings.osm_tile_url` (Phase 24 config, defaults to `http://tile-server:8080`) + `/tile/{z}/{x}/{y}.png`

### Caching & Headers
- `Cache-Control: public, max-age=86400, immutable` — tiles are immutable for a given z/x/y coordinate once generated
- Forward upstream `ETag` header when present (tile-server emits ETags)
- No `Vary` header (tiles don't vary by auth, cookie, or language)
- `Access-Control-Allow-Origin: *` — tiles are public static assets consumable by any frontend

### Error Handling & Observability
- httpx client timeout: 5s connect, 10s read
- Upstream 404 → response 404 (client requested a tile outside generated coverage)
- Upstream ConnectError / TimeoutError / 5xx → response 502 Bad Gateway + structured log
- Log format: `logger.warning("tile proxy failure", extra={"z": z, "x": x, "y": y, "upstream_status": status})` — non-crashing, uses existing observability stack (Phase 22 structlog)
- Metrics: if `api/metrics.py` exposes a counter/histogram pattern, add `tile_requests_total{status=2xx|4xx|5xx}`; otherwise defer

### Claude's Discretion
- Exact httpx client lifecycle (module-level singleton vs per-request vs FastAPI dependency) — use whatever matches the existing cascade service pattern
- Exact Prometheus metric names and label cardinality — follow existing patterns in `api/metrics.py` or `services/metrics.py`
- Unit test mocking strategy for httpx calls — use `respx` if already in deps, else `unittest.mock.patch`

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `APIRouter` + `app.include_router()` pattern (see `main.py:239-242`)
- `structlog` / observability from Phase 22 (available via existing logger imports)
- `settings.osm_tile_url` config value (added in Phase 24, `src/civpulse_geo/config.py`)
- `httpx` already in deps (used by cascade providers and `osm-download` CLI)

### Established Patterns
- Routers live at `src/civpulse_geo/api/<module>.py` with a module-level `router` object
- Mount new routers in `src/civpulse_geo/main.py` with `app.include_router(module.router)`
- Tests live at `tests/test_api_<module>.py` using FastAPI `TestClient`
- Error responses use `HTTPException` for deterministic status codes

### Integration Points
- New: `src/civpulse_geo/api/tiles.py` (new router module)
- New: `tests/test_api_tiles.py` (FastAPI TestClient tests)
- Modify: `src/civpulse_geo/main.py` — add `app.include_router(tiles.router)`

</code_context>

<specifics>
## Specific Ideas

- Route path MUST be exactly `GET /tiles/{z}/{x}/{y}.png` (not `/map/tiles/...` or `/tiles/{z}/{x}/{y}` without `.png`) — this is stated verbatim in the ROADMAP success criteria
- `Cache-Control` headers MUST be present on success responses (ROADMAP success criterion 2)
- Upstream misses MUST return 404, not 500 (ROADMAP success criterion 3)
- geo-api MUST NOT crash on upstream failure — logged + proxied as structured error

</specifics>

<deferred>
## Deferred Ideas

- Vector tiles (MVT/Protobuf format) — separate phase
- Tile pre-warming / cache warming script — operational concern, future phase
- CDN edge caching integration (Cloudflare, etc.) — infrastructure layer, out of scope
- Per-IP or per-client rate limiting on tile requests — security phase
- Tile usage analytics beyond basic counters — dedicated observability phase

</deferred>
