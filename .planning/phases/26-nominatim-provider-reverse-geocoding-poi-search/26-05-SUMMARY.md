---
phase: 26-nominatim-provider-reverse-geocoding-poi-search
plan: "05"
subsystem: api
tags: [poi, nominatim, geocoding, fastapi, pydantic]
dependency_graph:
  requires: [26-01, 26-03]
  provides: [poi-search-endpoint, poi-schemas]
  affects: [main.py, api/poi.py, schemas/poi.py]
tech_stack:
  added: []
  patterns: [viewbox-radius-approximation, provider-guard-503, bbox-validation-first]
key_files:
  created:
    - src/civpulse_geo/schemas/poi.py
    - src/civpulse_geo/api/poi.py
  modified:
    - src/civpulse_geo/main.py
decisions:
  - Validate bbox format before provider availability check so malformed bbox always returns 400 even without app.state.providers set
  - Use getattr(request.app.state, "providers", {}) to safely handle tests that do not set up full app state
metrics:
  duration: "8 minutes"
  completed: "2026-04-04"
  tasks: 2
  files: 3
---

# Phase 26 Plan 05: POI Search Endpoint Summary

**One-liner:** GET /poi/search via Nominatim viewbox/bounded with lat+radius or explicit bbox, 503 guard on missing provider.

## What Was Built

Added the POI search endpoint (`GET /poi/search`) backed by Nominatim `/search` with viewbox+bounded constraint. Callers supply either a center point (lat/lon + radius in meters) or an explicit bounding box (west,south,east,north) — mutually exclusive; both or neither returns 400.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create POI schemas + poi router + /search endpoint | b00c231 | src/civpulse_geo/schemas/poi.py, src/civpulse_geo/api/poi.py |
| 2 | Mount /poi router in main.py | b00c231 | src/civpulse_geo/main.py |

## Schemas Added

- `POIResult` — name, lat, lon, type, address, place_id
- `POISearchResponse` — results: list[POIResult], count: int

## Endpoint Contract

```
GET /poi/search?q=&lat=&lon=&radius=  (radius default 1000m, range 100–50000)
GET /poi/search?q=&bbox=west,south,east,north
```

- 400: both lat/lon and bbox provided (mutually exclusive)
- 400: neither lat/lon nor bbox provided
- 400: bbox malformed (non-numeric, wrong count of parts, out-of-range coordinates)
- 503: nominatim provider not registered in app.state.providers
- 200 with results=[] when upstream returns empty list

## Radius-to-Viewbox Approximation

For GA (~33°N):
- `delta_lat = radius_m / 111_000`
- `delta_lon = radius_m / 93_000`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Bbox validation moved before provider check**
- **Found during:** Task 1 test run — `test_poi_bbox_malformed_422` failed with AttributeError
- **Issue:** `request.app.state.providers` raised AttributeError when test didn't set up providers; the provider check ran before bbox parsing, so malformed bbox hit the provider check first
- **Fix:** Reordered logic — parse/validate bbox before provider availability check. Used `getattr(request.app.state, "providers", {})` for safe access.
- **Files modified:** src/civpulse_geo/api/poi.py
- **Commit:** b00c231

## Test Results

All 8 `test_api_poi_search.py` tests pass. Full suite (68 tests) green.

```
tests/test_api_poi_search.py    8 passed
tests/test_api_reverse_geocode.py  (passing)
tests/test_nominatim_provider.py   (passing)
tests/test_cascade.py              (passing)
Total: 68 passed
```

## Known Stubs

None.

## Self-Check: PASSED

- src/civpulse_geo/schemas/poi.py: FOUND
- src/civpulse_geo/api/poi.py: FOUND
- src/civpulse_geo/main.py (poi.router): FOUND
- Commit b00c231: FOUND
- /poi/search in app.routes: VERIFIED
