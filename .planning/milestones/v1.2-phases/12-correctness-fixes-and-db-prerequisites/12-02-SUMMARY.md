---
phase: 12-correctness-fixes-and-db-prerequisites
plan: 02
subsystem: providers, database
tags: [tiger, scourgify, spatial-filter, confidence, alembic, pg_trgm, gin-index]
depends_on: []
provides: [county-spatial-post-filter, corrected-confidence-constants, trgm-gin-indexes]
affects: [geocoding-pipeline, consensus-scoring, fuzzy-matching]
tech_stack:
  added: []
  patterns:
    - ST_Contains county spatial post-filter on Tiger geocode results
    - Multi-call session mock pattern (_make_geocode_session_factory)
    - TIGER_VALIDATION_CONFIDENCE and SCOURGIFY_CONFIDENCE constants replacing hardcoded 1.0
key_files:
  created:
    - alembic/versions/f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py
  modified:
    - src/civpulse_geo/providers/tiger.py
    - src/civpulse_geo/providers/scourgify.py
    - tests/test_tiger_provider.py
    - tests/test_scourgify_provider.py
decisions:
  - "COUNTY_CONTAINS_SQL uses ST_Transform(ST_SetSRID(..., 4326), 4269) to convert geocode result (WGS84) to match tiger.county SRID 4269 (NAD83)"
  - "geocode() try/except block wraps entire multi-execute session block to preserve ProviderError semantics"
  - "SCOURGIFY_CONFIDENCE = 0.3: parse-only, not address-verified (D-09)"
  - "TIGER_VALIDATION_CONFIDENCE = 0.4: normalize_address cross-refs Census data, higher than scourgify"
  - "_make_geocode_session_factory added as separate helper to support ordered multi-execute mock returns without breaking existing tests"
metrics:
  duration: "~15 minutes"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_changed: 5
requirements: [FIX-01, FIX-04, FUZZ-01]
---

# Phase 12 Plan 02: Tiger County Post-filter, Confidence Fixes, GIN Index Migration Summary

**One-liner:** Tiger geocode with ST_Contains county spatial post-filter, corrected confidence constants (0.3/0.4), and Alembic migration for pg_trgm + GIN trigram indexes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Tiger county post-filter, confidence constants, GIN migration | 56a7fa8 | tiger.py, scourgify.py, f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py |
| 2 | Tests for county filter, updated confidence assertions | 3b65195 | test_tiger_provider.py, test_scourgify_provider.py |

## What Was Built

### FIX-01: Tiger County Spatial Post-filter

Added `COUNTY_CONTAINS_SQL` and `STATE_FIPS_SQL` constants to `tiger.py`. Modified `TigerGeocodingProvider.geocode()` to:
1. Look up state FIPS from Tiger's `tiger.state` table using the geocoded `row.state` abbreviation.
2. Run `ST_Contains` on `tiger.county` to verify the geocoded point falls within any county in the expected state.
3. Return NO_MATCH if the point falls outside all counties (prevents neighboring-state leakage).
4. Accept optional `county_fips` kwarg — if provided, verify the geocoded point is in that specific county, return NO_MATCH on mismatch.

Key SRID handling: geocode results are SRID 4326 (WGS84); `tiger.county.the_geom` is SRID 4269 (NAD83). The SQL uses `ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 4269)` to convert before the containment check.

State lookup failure (no row from STATE_FIPS_SQL) gracefully skips the county filter rather than blocking the result. Same for `row.state=None`.

### FIX-04: Corrected Confidence Constants

- `SCOURGIFY_CONFIDENCE` changed from `1.0` to `0.3` — scourgify parses address structure offline but cannot verify the address exists at that location.
- `TIGER_VALIDATION_CONFIDENCE = 0.4` added as module-level constant — Tiger's `normalize_address()` cross-references Census TIGER/Line data so slightly higher confidence than pure offline parsing.
- `TigerValidationProvider.validate()` now returns `confidence=TIGER_VALIDATION_CONFIDENCE` instead of hardcoded `1.0`.

### FUZZ-01: GIN Trigram Index Migration

Created `alembic/versions/f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py`:
- Enables `pg_trgm` extension (`CREATE EXTENSION IF NOT EXISTS pg_trgm`)
- Creates `idx_oa_points_street_trgm` GIN index on `openaddresses_points.street_name`
- Creates `idx_nad_points_street_name_trgm` GIN index on `nad_points.street_name`
- `down_revision = "e5b2a1d3f4c6"` (chains from macon_bibb_points migration)

Migration verified: both indexes present in database, `pg_trgm` extension active.

### Tests

Added 5 new tests in `TestTigerGeocodingProvider`:
1. `test_tiger_geocode_wrong_county_returns_no_match` — COUNTY_CONTAINS returns None → NO_MATCH
2. `test_tiger_geocode_correct_county_returns_match` — county found → RANGE_INTERPOLATED
3. `test_tiger_geocode_county_fips_kwarg_mismatch` — county 13021 vs expected 13189 → NO_MATCH
4. `test_tiger_geocode_county_fips_kwarg_match` — county 13021 vs expected 13021 → match
5. `test_tiger_geocode_no_state_skips_county_filter` — state=None → filter skipped, match returned

Added `_make_geocode_session_factory` helper that returns ordered mock results across 3 sequential `execute()` calls (GEOCODE_SQL, STATE_FIPS_SQL, COUNTY_CONTAINS_SQL).

Updated confidence assertions: `1.0` → `0.4` in Tiger validation test, `1.0` → `0.3` in two scourgify tests.

## Verification Results

```
46 passed in tests/test_tiger_provider.py + tests/test_scourgify_provider.py
370 passed, 11 pre-existing failures, 2 skipped across full suite (no new failures)
idx_oa_points_street_trgm: present
idx_nad_points_street_name_trgm: present
pg_trgm extension: active
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- [x] `src/civpulse_geo/providers/tiger.py` — exists, contains COUNTY_CONTAINS_SQL, TIGER_VALIDATION_CONFIDENCE
- [x] `src/civpulse_geo/providers/scourgify.py` — exists, SCOURGIFY_CONFIDENCE = 0.3
- [x] `alembic/versions/f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py` — exists, contains gin_trgm_ops
- [x] `tests/test_tiger_provider.py` — contains test_tiger_geocode_wrong_county_returns_no_match
- [x] `tests/test_scourgify_provider.py` — contains `confidence == 0.3`
- [x] Commits 56a7fa8 and 3b65195 exist in git log
