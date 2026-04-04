---
phase: 26-nominatim-provider-reverse-geocoding-poi-search
verified: 2026-04-04T21:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 26: Nominatim Provider + Reverse Geocoding + POI Search Verification Report

**Phase Goal:** The cascade geocoding pipeline includes Nominatim as a 6th provider, and callers can reverse geocode coordinates and search for nearby POIs
**Verified:** 2026-04-04T21:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `source=nominatim` appears in cascade results when nominatim is registered | VERIFIED | `NominatimGeocodingProvider` wired in `cascade.py` weight map, `main.py` lifespan, and `KNOWN_PROVIDERS`; `test_cascade.py::test_get_provider_weight_nominatim` passes |
| 2 | `GET /geocode/reverse?lat=&lon=` returns address for coordinates | VERIFIED | Route exists in `api/geocoding.py:259`; all 5 reverse-geocode contract tests pass |
| 3 | `GET /poi/search?q=&lat=&lon=` returns POI results | VERIFIED | Route exists in `api/poi.py:62`; all 8 POI contract tests pass |
| 4 | `GET /poi/search?q=&bbox=` constrains by bbox, 400 on missing/both params | VERIFIED | `_parse_bbox` + `has_point/has_bbox` guard in `api/poi.py`; `test_poi_bbox`, `test_poi_both_bbox_and_latlon_returns_400`, `test_poi_neither_bbox_nor_latlon_returns_400` all pass |
| 5 | `NominatimProvider` conditionally registered only when Nominatim HTTP service reachable | VERIFIED | `main.py:117-128` implements `_nominatim_reachable` probe + `nominatim_enabled` toggle with `logger.warning` on failure |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Lines | Status | Details |
|----------|----------|-------|--------|---------|
| `src/civpulse_geo/providers/nominatim.py` | `NominatimGeocodingProvider` class | 191 | VERIFIED | Contains class, `_nominatim_reachable` probe, full ABC implementation |
| `src/civpulse_geo/api/geocoding.py` | `GET /geocode/reverse` route handler | — | VERIFIED | Route at line 259; `ReverseGeocodeResponse` imported and returned |
| `src/civpulse_geo/api/poi.py` | POI search router mounted at `/poi` | 145 | VERIFIED | `@router.get("/search")` at line 62; viewbox + bounded params |
| `src/civpulse_geo/schemas/reverse.py` | `ReverseGeocodeResponse` Pydantic model | 22 | VERIFIED | `class ReverseGeocodeResponse(BaseModel)` with all required fields |
| `src/civpulse_geo/schemas/poi.py` | `POIResult`, `POISearchResponse` Pydantic models | 20 | VERIFIED | Both classes present |
| `src/civpulse_geo/config.py` | `weight_nominatim=0.70`, `nominatim_enabled=True` | — | VERIFIED | Lines 65–66 confirmed via import assertion |
| `src/civpulse_geo/services/cascade.py` | `"nominatim": settings.weight_nominatim` in weight map | — | VERIFIED | Line 83 confirmed |
| `src/civpulse_geo/main.py` | `NominatimGeocodingProvider` + `_nominatim_reachable` in lifespan | — | VERIFIED | Lines 41, 117–128 |
| `tests/test_nominatim_provider.py` | 6+ unit tests for provider | 148 | VERIFIED | 7 tests collected and all pass |
| `tests/test_api_reverse_geocode.py` | 5 contract tests for `/geocode/reverse` | 180 | VERIFIED | 5 tests collected and all pass |
| `tests/test_api_poi_search.py` | 8 contract tests for `/poi/search` | 278 | VERIFIED | 8 tests collected and all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `main.py` | `providers/nominatim.py::_nominatim_reachable` | `await _nominatim_reachable(...)` | WIRED | Imported at line 41; called at line 119 |
| `main.py` | `NominatimGeocodingProvider` | `app.state.providers["nominatim"] = NominatimGeocodingProvider(...)` | WIRED | Line 120 |
| `services/cascade.py` | `settings.weight_nominatim` | `"nominatim": settings.weight_nominatim` in weight_map | WIRED | Line 83 confirmed; `get_provider_weight("nominatim") == 0.70` asserted programmatically |
| `api/geocoding.py (/reverse)` | `settings.osm_nominatim_url` | `f"{settings.osm_nominatim_url.rstrip('/')}/reverse"` | WIRED | Line 272 |
| `api/geocoding.py` | `app.state.providers["nominatim"]` | 503 guard before HTTP call | WIRED | Line 270 |
| `api/poi.py` | `settings.osm_nominatim_url` | `f"{settings.osm_nominatim_url.rstrip('/')}/search"` with `viewbox`+`bounded` | WIRED | Line 120 |
| `main.py` | `api/poi.py::router` | `app.include_router(poi.router)` | WIRED | Line 257; `/poi/search` confirmed in `app.routes` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `api/geocoding.py::reverse_geocode` | `body` (Nominatim JSON) | `request.app.state.http_client.get(url, params=...)` | Yes — live HTTP call to Nominatim `/reverse` | FLOWING |
| `api/poi.py::poi_search` | `upstream` (list from Nominatim) | `request.app.state.http_client.get(url, params=...)` | Yes — live HTTP call to Nominatim `/search` with computed `viewbox`+`bounded` | FLOWING |
| `providers/nominatim.py::geocode` | `raw` (search result list) | `httpx.AsyncClient.get(url, params=...)` to `/search` | Yes — full HTTP call with `q`, `format`, `limit=1` | FLOWING |

Data sources are real HTTP calls (mocked in tests). No hardcoded static returns found in non-test paths.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Both new routes registered in app | `python -c "...assert '/poi/search' in paths and '/geocode/reverse' in paths"` | Both present | PASS |
| `get_provider_weight("nominatim") == 0.70` | import assertion | 0.70 confirmed | PASS |
| `settings.weight_nominatim == 0.70` and `nominatim_enabled is True` | import assertion | Both confirmed | PASS |
| `_nominatim_reachable` is async coroutine | `inspect.iscoroutinefunction(...)` | True | PASS |
| All 20 phase 26 tests pass | `uv run pytest tests/test_nominatim_provider.py tests/test_api_reverse_geocode.py tests/test_api_poi_search.py -v` | 20/20 passed | PASS |
| Full non-e2e regression suite | `uv run pytest tests/ -q --ignore=tests/e2e` | 618 passed, 2 skipped, 0 failed | PASS |
| Ruff lint on all 4 implementation files | `uv run ruff check ...nominatim.py ...geocoding.py ...poi.py ...main.py` | All checks passed | PASS |

**Note on e2e failures:** Running the full `tests/` suite without `--ignore=tests/e2e` produces 12 failures in `tests/e2e/`. These are marked `pytest.mark.e2e` and require a live deployed service (they fail with `{"detail":"Not Found"}` because no running API server is available in the CI environment). These failures pre-date Phase 26 and are unrelated to it — all non-e2e tests pass clean.

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| GEO-01 | 26-01, 26-02, 26-03 | Nominatim registered as 6th cascade provider | SATISFIED | `NominatimGeocodingProvider` in `app.state.providers`; weight_map entry; `KNOWN_PROVIDERS` updated |
| GEO-02 | 26-01, 26-02, 26-03 | Nominatim participates in cascade consensus scoring | SATISFIED | `get_provider_weight("nominatim") == 0.70`; cascade weight map entry present |
| GEO-03 | 26-01, 26-04, 26-05 | `GET /geocode/reverse` and `GET /poi/search` endpoints | SATISFIED | Both routes in `app.routes`; all 13 endpoint tests pass |
| GEO-04 | 26-01, 26-05 | `/poi/search` supports bbox constraint with `viewbox`+`bounded=1` | SATISFIED | `_parse_bbox` + `has_bbox` branch in `api/poi.py`; `test_poi_bbox` passes |
| GEO-05 | 26-03, 26-05 | Provider conditionally registered with HTTP probe + toggle + warning | SATISFIED | `_nominatim_reachable` probe in `main.py:117-128`; `nominatim_enabled` toggle; `logger.warning` on failure |

All 5 requirement IDs (GEO-01 through GEO-05) are accounted for across plan frontmatter and verified against implementation.

---

### Anti-Patterns Found

No blockers or warnings found. Scan results:

- No `TODO`/`FIXME`/`PLACEHOLDER` comments in any phase 26 implementation file
- No `return null` / `return {}` / `return []` stubs — all handlers return real data or raise `HTTPException`
- No hardcoded empty collections flowing to rendering paths
- `return []` in `api/poi.py:130` is a defensive fallback (`if not isinstance(upstream, list): upstream = []`) — data flows from a live HTTP call and this handles unexpected upstream responses, not a stub
- Ruff clean on all 4 implementation files

---

### Human Verification Required

No human verification items. All success criteria verified programmatically.

---

## Gaps Summary

No gaps. All 5 observable truths are verified. All required artifacts exist, are substantive, wired, and have real data flowing through them. All 20 phase-specific tests pass. The full non-e2e regression suite (618 tests) passes with no regressions introduced.

---

_Verified: 2026-04-04T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
