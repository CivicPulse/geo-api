---
phase: quick
plan: 260325-0th
subsystem: database
tags: [geojson, geocoding, macon-bibb, gis, staging-table, sha256, sqlalchemy, alembic]

# Dependency graph
requires:
  - phase: quick/260325-0pw
    provides: OpenAddressesParcel migration (d4a71c3f8b92) that this migration chains from
provides:
  - MaconBibbPoint ORM model (macon_bibb_points staging table)
  - Alembic migration e5b2a1d3f4c6 chaining from d4a71c3f8b92
  - load-macon-bibb CLI command for .geojson FeatureCollection import
  - MaconBibbGeocodingProvider with ADDRESS_TYPE_MAP confidence mapping
  - MaconBibbValidationProvider with USPS-normalized output via scourgify
  - Lifespan registration in main.py (conditional on macon_bibb_points data)
affects: [providers, lifespan, cli, tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - SHA-256 source_hash from OBJECTID+FULLADDR+coordinates for GIS deduplication
    - ADDRESS_TYPE_MAP replaces PLACEMENT_MAP for Macon-Bibb ADDType values
    - state/zip_code column names (NAD pattern) for Macon-Bibb model

key-files:
  created:
    - src/civpulse_geo/models/macon_bibb.py
    - alembic/versions/e5b2a1d3f4c6_add_macon_bibb_address_points_table.py
    - src/civpulse_geo/providers/macon_bibb.py
    - tests/test_macon_bibb_provider.py
    - tests/test_load_macon_bibb_cli.py
  modified:
    - src/civpulse_geo/models/__init__.py
    - src/civpulse_geo/cli/__init__.py
    - src/civpulse_geo/main.py

key-decisions:
  - "Macon-Bibb source_hash is SHA-256 of OBJECTID:FULLADDR:lon:lat — not a raw field value like NAD UUID or OA hash field"
  - "ADDRESS_TYPE_MAP maps PARCEL/SITE to APPROXIMATE 0.8 and STRUCTURE to ROOFTOP 1.0 — mirrors NAD PLACEMENT_MAP pattern"
  - "load-macon-bibb accepts uncompressed .geojson (json.load into memory) not .geojson.gz — source file is 67k features, fits in RAM"
  - "state hardcoded to GA for all records — this is a county-level dataset for Macon-Bibb County, Georgia only"
  - "Provider registered under key 'macon_bibb' in main.py lifespan — consistent with provider_name property"

patterns-established:
  - "4th local provider following NAD pattern exactly: state/zip_code columns, _parse_input_address reuse, bare-except data_available check"

requirements-completed: []

# Metrics
duration: 20min
completed: 2026-03-25
---

# Quick Task 260325-0th: Add 4th Local Geocoder Using Macon-Bibb County GIS

**MaconBibbPoint staging table, load-macon-bibb CLI with SHA-256 deduplication, and local geocoding/validation providers backed by 67k Macon-Bibb County GIS address points**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-03-25T00:24:00Z
- **Completed:** 2026-03-25T00:44:41Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- MaconBibbPoint ORM model with all GeoJSON property fields mapped (ADDR_HN, ADDR_SN, ADDR_ST, UNIT, City_1, ZIP_1, ADDType, hardcoded state=GA)
- Alembic migration e5b2a1d3f4c6 chains from d4a71c3f8b92 (OA parcels), creates macon_bibb_points with spatial GiST and composite (street_name, zip_code) indexes
- load-macon-bibb CLI command loads uncompressed .geojson FeatureCollection with ON CONFLICT upsert deduplication via SHA-256 source_hash
- MaconBibbGeocodingProvider returns geocoding results with ADDRESS_TYPE_MAP confidence (PARCEL/SITE=0.8, STRUCTURE=1.0); fuzzy fallback halves confidence
- MaconBibbValidationProvider returns USPS-normalized output via scourgify with raw column fallback
- Both providers auto-register in lifespan when macon_bibb_points table has data
- 41 tests pass (provider + CLI unit tests via TDD RED/GREEN)

## Task Commits

1. **Task 1: Create ORM model, Alembic migration, and CLI load command** - `f26c2ea` (feat)
2. **Task 2 RED: Add failing tests** - `f9beff8` (test)
3. **Task 2 GREEN: Implement providers and register in lifespan** - `a99a45d` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/civpulse_geo/models/macon_bibb.py` - MaconBibbPoint ORM model (macon_bibb_points staging table)
- `alembic/versions/e5b2a1d3f4c6_add_macon_bibb_address_points_table.py` - Alembic migration, chains from d4a71c3f8b92
- `src/civpulse_geo/providers/macon_bibb.py` - MaconBibbGeocodingProvider, MaconBibbValidationProvider, _macon_bibb_data_available
- `src/civpulse_geo/models/__init__.py` - Added MaconBibbPoint import and __all__ entry
- `src/civpulse_geo/cli/__init__.py` - Added hashlib import, _parse_macon_bibb_feature, _upsert_macon_bibb_batch, load-macon-bibb command
- `src/civpulse_geo/main.py` - Macon-Bibb provider registration block in lifespan
- `tests/test_macon_bibb_provider.py` - 27 provider tests
- `tests/test_load_macon_bibb_cli.py` - 14 CLI tests

## Decisions Made

- SHA-256 source_hash computed from `"{OBJECTID}:{FULLADDR}:{lon}:{lat}"` — GeoJSON has no pre-existing hash field like OA, and OBJECTID alone is not globally stable across exports
- load-macon-bibb accepts `.geojson` only (not `.geojson.gz`) — source file is uncompressed; single-pass json.load fits 67k features in memory cleanly
- ADDRESS_TYPE_MAP: PARCEL/SITE -> APPROXIMATE 0.8, STRUCTURE -> ROOFTOP 1.0; unknown/empty -> DEFAULT_ADDRESS_TYPE 0.1 — mirrors NAD PLACEMENT_MAP design
- Registered under key "macon_bibb" in providers/validation_providers dicts — short and consistent with provider_name

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Data must be loaded via `geo-import load-macon-bibb data/Address_Points.geojson` before the provider registers at startup.

## Next Phase Readiness

- Macon-Bibb County GIS is now a 4th local geocoding source alongside OA, Tiger, and NAD
- Provider auto-registers at startup when macon_bibb_points table is populated
- To activate: run `geo-import load-macon-bibb data/Address_Points.geojson` inside the api container

---
*Quick Task: 260325-0th*
*Completed: 2026-03-25*
