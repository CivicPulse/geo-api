---
phase: 26-nominatim-provider-reverse-geocoding-poi-search
plan: 03
subsystem: api
tags: [nominatim, geocoding, cascade, settings, startup-probe, lifespan]

# Dependency graph
requires:
  - phase: 26-02
    provides: NominatimGeocodingProvider class at src/civpulse_geo/providers/nominatim.py
  - phase: prior
    provides: lifespan conditional registration pattern (macon_bibb), settings, cascade weight_map
provides:
  - nominatim_enabled + weight_nominatim settings fields
  - _nominatim_reachable() HTTP probe in providers/nominatim.py
  - Conditional NominatimGeocodingProvider registration in main.py lifespan
  - "nominatim" entry in cascade get_provider_weight weight_map
  - "nominatim" in KNOWN_PROVIDERS frozenset (api/geocoding.py)
  - GEO-01: Nominatim fully wired into cascade
  - GEO-05: Conditional startup guard via HTTP probe + toggle
affects: [26-04, 26-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HTTP probe pattern: GET {base_url}/status with 2s timeout in async helper, returns bool"
    - "Toggle + probe guard: settings.nominatim_enabled checked before probe to allow disabling without network"
    - "Nominatim provider registered using app.state.http_client (shared client) matching macon_bibb pattern"

key-files:
  created: []
  modified:
    - src/civpulse_geo/config.py
    - src/civpulse_geo/providers/nominatim.py
    - src/civpulse_geo/services/cascade.py
    - src/civpulse_geo/api/geocoding.py
    - src/civpulse_geo/main.py
    - tests/test_cascade.py

key-decisions:
  - "_nominatim_reachable placed in nominatim.py (not main.py) for co-location with provider; imported by main.py"
  - "Toggle checked first (nominatim_enabled), probe runs only when toggle is True — avoids network calls when disabled"
  - "Probe uses shared app.state.http_client (not a new client) for consistent connection pool usage"
  - "weight_nominatim=0.70 default: lower than census (0.90) and OA (0.80), higher than tiger (0.40)"

requirements-completed: [GEO-01, GEO-05]

# Metrics
duration: 8min
completed: 2026-04-04
---

# Phase 26 Plan 03: Nominatim Cascade Wiring Summary

**Wires NominatimGeocodingProvider into the cascade by adding weight_nominatim=0.70 + nominatim_enabled=True settings, _nominatim_reachable() HTTP probe, conditional lifespan registration, and cascade weight_map entry**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-04T21:00:00Z
- **Completed:** 2026-04-04T21:08:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- `weight_nominatim: float = 0.70` and `nominatim_enabled: bool = True` added to `Settings` in config.py
- `_nominatim_reachable()` async probe appended to nominatim.py: GET `{base_url}/status`, 2s timeout, returns bool
- `"nominatim": settings.weight_nominatim` added to cascade `get_provider_weight()` weight_map
- `"nominatim"` added to `KNOWN_PROVIDERS` frozenset in api/geocoding.py
- Conditional lifespan block added to main.py: toggle guard → HTTP probe → register or warn
- `test_get_provider_weight_nominatim` added to `TestGetProviderWeight` in test_cascade.py
- All 55 cascade + nominatim provider tests pass; ruff clean on all 5 source files

## Task Commits

1. **Task 1: settings + probe + cascade weight + KNOWN_PROVIDERS** - `9de3843` (feat)
2. **Task 2: main.py lifespan registration + cascade test** - `3d20db2` (feat)

## Files Created/Modified

- `src/civpulse_geo/config.py` — added `weight_nominatim` and `nominatim_enabled` fields after `weight_nad`
- `src/civpulse_geo/providers/nominatim.py` — appended `_nominatim_reachable()` module-level async function
- `src/civpulse_geo/services/cascade.py` — added `"nominatim": settings.weight_nominatim` to weight_map
- `src/civpulse_geo/api/geocoding.py` — added `"nominatim"` to KNOWN_PROVIDERS frozenset
- `src/civpulse_geo/main.py` — imported NominatimGeocodingProvider + _nominatim_reachable; added conditional registration block after Macon-Bibb
- `tests/test_cascade.py` — added `test_get_provider_weight_nominatim` asserting weight == 0.70

## Decisions Made

- `_nominatim_reachable` lives in `nominatim.py` (co-located with provider), imported by `main.py` — same pattern as `_macon_bibb_data_available`, `_oa_data_available`, etc.
- Toggle is checked before the HTTP probe to allow disabling nominatim without any network round-trip
- Shared `app.state.http_client` passed to both the probe and the provider constructor for consistent connection pooling
- weight_nominatim=0.70 positions Nominatim below census (0.90) and OA/NAD/Macon-Bibb (0.80) but above the default fallback (0.50)

## Deviations from Plan

None — plan executed exactly as written. Both tasks completed in sequence, all assertions and tests pass.

## Known Stubs

None — all wiring is real. Provider will be registered when Nominatim service is reachable at startup.

## Issues Encountered

Pre-existing F841 ruff warnings in tests/test_cascade.py (unused `result` variables in 6 tests, lines 397/510/554/619/938/1011). Not caused by this plan; out of scope per scope boundary rules. Logged to deferred items.
