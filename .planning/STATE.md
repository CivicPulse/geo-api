---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: Self-Hosted OSM Stack
status: verifying
stopped_at: Completed 27-valhalla-routing plan 03 (27-03-PLAN.md)
last_updated: "2026-04-04T22:25:40.294Z"
last_activity: 2026-04-04
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 15
  completed_plans: 15
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-04)

**Core value:** Single, reliable source of geocoded and validated address data across CivPulse systems — now expanded to include self-hosted map tiles, POI search, reverse geocoding, and routing
**Current focus:** Phase 27 — Valhalla Routing

## Current Position

Phase: 28
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-04-04

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

| Milestone | Phases | Requirements | Notes |
|-----------|--------|--------------|-------|
| v1.0 | 6 | 26/26 | Shipped 2026-03-19 |
| v1.1 | 5 | 6/6 | Shipped 2026-03-29 |
| v1.2 | 5 | 25/25 | Shipped 2026-03-29 |
| v1.3 | 7 | 30/30 | Shipped 2026-04-03 |
| v1.4 | 5 | 0/21 | In progress |
| Phase 24-osm-data-pipeline-docker-compose-sidecars P01 | 8min | 2 tasks | 3 files |
| Phase 24-osm-data-pipeline-docker-compose-sidecars P02 | 15min | 3 tasks | 3 files |
| Phase 24-osm-data-pipeline-docker-compose-sidecars P03 | 3min | 2 tasks | 2 files |
| Phase 24-osm-data-pipeline-docker-compose-sidecars P04 | 5min | 2 tasks | 2 files |
| Phase 24-osm-data-pipeline-docker-compose-sidecars P05 | 2min | 2 tasks | 2 files |
| Phase 25-tile-server-fastapi-tile-proxy P01 | 2min | 2 tasks | 3 files |
| Phase 25-tile-server-fastapi-tile-proxy P02 | 5 | 2 tasks | 1 files |
| Phase 26-nominatim-provider-reverse-geocoding-poi-search P01 | 12 | 3 tasks | 3 files |
| Phase 26-nominatim-provider-reverse-geocoding-poi-search P02 | 5 | 1 tasks | 1 files |
| Phase 26-nominatim-provider-reverse-geocoding-poi-search P03 | 8 | 2 tasks | 6 files |
| Phase 26-nominatim-provider-reverse-geocoding-poi-search P04 | 1 | 1 tasks | 2 files |
| Phase 26-nominatim-provider-reverse-geocoding-poi-search P05 | 8 | 2 tasks | 3 files |
| Phase 27-valhalla-routing P02 | 5 | 2 tasks | 2 files |
| Phase 27-valhalla-routing P01 | 8 | 1 tasks | 1 files |
| Phase 27-valhalla-routing P03 | 2 | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

Key research decisions for v1.4:

- Nominatim gets dedicated PostgreSQL database on `osm-postgres` instance (never shares civpulse_geo — import is destructive)
- Valhalla uses Job/Deployment split so graph is built once to PVC, not rebuilt on every pod restart
- Tile server and Nominatim can be parallelized after PBF download (separate data stores)
- Raster vs. vector tile decision still open — must be resolved before Phase 25 planning begins
- [Phase 24]: noqa: F401 on stub imports (patch, MagicMock, app) in test_osm_cli.py — intentional scaffolding for Plan 03/04/05 implementation
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: All 4 OSM services gated under profiles: [osm]; tile-server uses isolated internal PostgreSQL; Nominatim DSN uses libpq format; valhalla_tiles volume persists routing graph (D-02)
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: osm-download uses module-level PBF_PATH constant so tests can monkeypatch without touching disk
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: _run_docker_cmd helper centralizes elapsed-time echo and CalledProcessError -> typer.Exit(1) translation
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: osm-import-tiles uses docker compose run --rm (not exec) per Pitfall 3; PBF mounted at /data/region.osm.pbf:ro per Pitfall 4
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: osm-build-valhalla passes all four env flags (serve_tiles=False, force_rebuild=True, build_admins=False, build_elevation=False) per Pitfall 5
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: osm-pipeline delegates to sibling commands via subprocess so each step reuses existing error handling and output formatting
- [Phase 24-osm-data-pipeline-docker-compose-sidecars]: Idempotency check functions use subprocess.run check=False — if docker exec fails (container not running), check silently returns False and step runs normally
- [Phase 25-tile-server-fastapi-tile-proxy]: Used AsyncClient + ASGITransport (not sync TestClient) for tile tests — matches existing project test pattern
- [Phase 25-tile-server-fastapi-tile-proxy]: Tile router skeleton raises HTTPException(501) — route wired, streaming implementation deferred to Plan 02
- [Phase 25-tile-server-fastapi-tile-proxy]: client.get() over client.stream() with StreamingResponse(iter([bytes])) — keeps mock-friendly interface while satisfying streaming contract
- [Phase 25-tile-server-fastapi-tile-proxy]: Upstream 404 checked before generic >=400 catch-all to ensure clean 404 passthrough (not 502)
- [Phase 26-nominatim-provider-reverse-geocoding-poi-search]: POI radius tests assert viewbox param present to enforce radius-to-bbox conversion in implementation
- [Phase 26-nominatim-provider-reverse-geocoding-poi-search]: Malformed bbox test accepts 400 or 422 — both custom validator and FastAPI Pydantic error are acceptable behaviors
- [Phase 26-nominatim-provider-reverse-geocoding-poi-search]: NominatimGeocodingProvider maps Nominatim importance to confidence (clamped 0.0-1.0, default 0.70) and OSM type to location_type via OSM_TYPE_TO_LOCATION_TYPE constant
- [Phase 26-nominatim-provider-reverse-geocoding-poi-search]: _nominatim_reachable placed in nominatim.py for co-location; toggle checked before probe to skip network when disabled
- [Phase 26-nominatim-provider-reverse-geocoding-poi-search]: weight_nominatim=0.70 positions Nominatim below census/OA/NAD but above fallback default
- [Phase 26-04]: GET /geocode/reverse uses direct HTTP pass-through to Nominatim /reverse; 503 guard checks app.state.providers key before any upstream call
- [Phase 26-05]: Validate bbox before provider check in /poi/search so malformed bbox always returns 400
- [Phase 27-valhalla-routing]: Valhalla upstream 400 maps to 404 (no-route semantics, not client error)
- [Phase 27-valhalla-routing]: Router not mounted in main.py for Plan 02 — Plan 03 handles mount atomically with startup probe
- [Phase 27-valhalla-routing]: test_route_valhalla_empty_returns_404 passes coincidentally in RED phase (FastAPI 404 for missing route); real handler logic exercised in Plan 02
- [Phase 27-valhalla-routing]: POST body spot-check for exact Valhalla JSON shape embedded in pedestrian happy-path test
- [Phase 27-valhalla-routing]: Valhalla uses app.state.valhalla_enabled flag (not providers dict) — it is not a GeocodingProvider
- [Phase 27-valhalla-routing]: _valhalla_reachable mirrors _nominatim_reachable exactly: GET /status, 2s timeout, bool return

### Pending Todos

- [Reset ArgoCD targetRevision to main after merge](.planning/todos/pending/2026-04-03-reset-argocd-targetrevision-to-main-after-merge.md) - restore `spec.source.targetRevision: main` in both geo-api ArgoCD Application manifests after the Phase 23 deployment fixes are merged

### Blockers/Concerns

- Raster vs. vector tile decision unresolved — PITFALLS.md recommends Martin + Tilemaker (pre-generated MBTiles) over renderd/mod_tile; FEATURES.md specifies raster PNGs. Must be resolved before Phase 25 planning.

## Session Continuity

Last activity: 2026-04-04 — v1.4 roadmap created
Stopped at: Completed 27-valhalla-routing plan 03 (27-03-PLAN.md)
Resume file: None
Next action: `/gsd:plan-phase 24`
