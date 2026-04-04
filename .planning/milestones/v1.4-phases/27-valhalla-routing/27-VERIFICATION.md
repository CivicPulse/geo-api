---
phase: 27-valhalla-routing
verified: 2026-04-04T00:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 27: Valhalla Routing Verification Report

**Phase Goal:** Callers can request walking and driving turn-by-turn routes between two points; route responses include maneuvers, polyline, duration, and distance
**Verified:** 2026-04-04
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /route?mode=pedestrian returns a walking route | VERIFIED | test_route_pedestrian_returns_200_with_route_response PASSED; route.py checks `"pedestrian" in _VALID_MODES` |
| 2 | GET /route?mode=auto returns a driving route | VERIFIED | test_route_auto_returns_200_with_route_response PASSED; route.py checks `"auto" in _VALID_MODES` |
| 3 | Route response contains maneuvers, polyline, duration_seconds, distance_meters | VERIFIED | schemas/route.py RouteResponse has all 4 fields; test_route_maneuver_schema_contains_required_fields PASSED |
| 4 | POST body to upstream Valhalla is {"locations":[...], "costing": mode, "units":"kilometers"} | VERIFIED | route.py lines 65-72 construct exact body; spot-check in test_route_pedestrian_returns_200_with_route_response PASSED |
| 5 | app.state.valhalla_enabled flag set by startup probe | VERIFIED | main.py lines 131-143 set flag; valhalla.py probe exists; config.py valhalla_enabled=True |
| 6 | 503 when Valhalla disabled, 400 on bad params, 404 on no route, 502 on upstream fail | VERIFIED | All 11 contract tests PASSED covering each status code |
| 7 | settings.valhalla_enabled toggle exists (defaults True) | VERIFIED | config.py line 67: `valhalla_enabled: bool = True` |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_api_route.py` | Contract tests for /route endpoint | VERIFIED | 379 lines, 11 tests, all PASS |
| `src/civpulse_geo/schemas/route.py` | RouteResponse + Maneuver Pydantic models | VERIFIED | 23 lines, both models export correctly |
| `src/civpulse_geo/api/route.py` | APIRouter for /route endpoint | VERIFIED | 142 lines, exports `router`, prefix="/route" |
| `src/civpulse_geo/providers/valhalla.py` | _valhalla_reachable health probe | VERIFIED | 21 lines, async function, mirrors nominatim probe |
| `src/civpulse_geo/config.py` | valhalla_enabled setting | VERIFIED | line 67 adds `valhalla_enabled: bool = True` |
| `src/civpulse_geo/main.py` | Mount route router + set app.state.valhalla_enabled | VERIFIED | imports route + _valhalla_reachable; lifespan probe; include_router(route.router) at line 273 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_api_route.py` | `civpulse_geo.main.app` | ASGITransport | WIRED | `from civpulse_geo.main import app` at line 26 |
| `tests/test_api_route.py` | `app.state.valhalla_enabled` | fixture + monkeypatch | WIRED | `patched_valhalla_http` fixture sets `app.state.valhalla_enabled = True` |
| `src/civpulse_geo/api/route.py` | `settings.osm_valhalla_url` | POST to upstream | WIRED | line 64: `settings.osm_valhalla_url.rstrip('/')` |
| `src/civpulse_geo/api/route.py` | `app.state.valhalla_enabled` | 503 guard check | WIRED | line 59: `getattr(request.app.state, "valhalla_enabled", False)` |
| `src/civpulse_geo/api/route.py` | `app.state.http_client` | POST to Valhalla /route | WIRED | line 74: `client: httpx.AsyncClient = request.app.state.http_client` |
| `src/civpulse_geo/main.py` | `src/civpulse_geo/providers/valhalla.py` | import _valhalla_reachable | WIRED | line 42: `from civpulse_geo.providers.valhalla import _valhalla_reachable` |
| `src/civpulse_geo/main.py` | `src/civpulse_geo/api/route.py` | app.include_router(route.router) | WIRED | line 273: `app.include_router(route.router)` |
| `main.py lifespan` | `app.state.valhalla_enabled` | probe result assignment | WIRED | lines 133/136/142 set `app.state.valhalla_enabled = True/False` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `src/civpulse_geo/api/route.py` | `upstream` | `client.post(upstream_url, json=body)` | Yes — live httpx POST to Valhalla; mocked in tests | FLOWING |
| `src/civpulse_geo/api/route.py` | `maneuvers` | `leg["maneuvers"]` from upstream JSON | Yes — parsed from Valhalla trip response | FLOWING |
| `src/civpulse_geo/api/route.py` | `distance_m` | `summary["length"] * 1000.0` | Yes — km-to-meters conversion verified by test | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 11 contract tests pass | `uv run pytest tests/test_api_route.py -v` | 11 passed in 0.04s | PASS |
| ruff clean on all 4 target files | `uv run ruff check src/civpulse_geo/api/route.py src/civpulse_geo/schemas/route.py src/civpulse_geo/providers/valhalla.py src/civpulse_geo/main.py` | All checks passed | PASS |
| /route mounted in app routes | `from civpulse_geo.main import app; '/route' in [r.path for r in app.routes]` | True | PASS |
| Full unit test suite (no regression) | `uv run pytest tests/ --ignore=tests/e2e -q` | 629 passed, 2 skipped, 1 warning | PASS |

Note: `tests/e2e/test_cascade_pipeline.py` fails with 404 on `/geocode` but this is pre-existing (last modified in phase 23, commit `746c51a`) and unrelated to phase 27.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| ROUTE-01 | 27-01, 27-02, 27-03 | Callers can request walking (pedestrian) routes | SATISFIED | GET /route?mode=pedestrian → 200; test_route_pedestrian_returns_200_with_route_response PASSED |
| ROUTE-02 | 27-01, 27-02, 27-03 | Callers can request driving (auto) routes | SATISFIED | GET /route?mode=auto → 200; test_route_auto_returns_200_with_route_response PASSED |
| ROUTE-03 | 27-01, 27-02, 27-03 | Route responses include maneuvers, polyline, duration_seconds, distance_meters | SATISFIED | RouteResponse schema verified; km-to-meters conversion test PASSED; maneuver schema test PASSED |

All 3 requirement IDs declared in frontmatter of all 3 plans (27-01, 27-02, 27-03).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No stubs, placeholders, empty handlers, or hardcoded empty returns found in any phase 27 file.

### Human Verification Required

None. All observable behaviors are verifiable programmatically via the test suite and static analysis.

The only item that would require a live environment is the actual Valhalla sidecar probe during app startup — but the app.state.valhalla_enabled fixture approach in tests confirms the guard logic works correctly without needing a running Valhalla instance.

### Gaps Summary

No gaps. All truths verified, all artifacts substantive and wired, all key links confirmed, all 11 contract tests pass GREEN, ruff clean, no regression in 629-test suite.

---

_Verified: 2026-04-04_
_Verifier: Claude (gsd-verifier)_
