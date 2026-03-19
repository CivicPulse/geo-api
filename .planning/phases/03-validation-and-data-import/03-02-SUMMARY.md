---
phase: 03-validation-and-data-import
plan: 02
subsystem: database
tags: [fiona, typer, gis, cli, geojson, kml, shp, crs-reprojection, upsert, postgresql]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: addresses table, geocoding_results table, admin_overrides table, OfficialGeocoding model
  - phase: 02-geocoding-service
    provides: uq_geocoding_address_provider constraint, OfficialGeocoding auto-set pattern

provides:
  - CLI tool (geo-import) that loads Bibb County GIS files as provider geocoding records
  - Parsers for GeoJSON (stdlib json), KML (stdlib xml.etree), SHP (fiona + CRS reprojection)
  - Upsert semantics: INSERT ON CONFLICT DO UPDATE for geocoding_results (idempotent re-import)
  - OfficialGeocoding auto-set with admin_override priority preservation

affects: [data-import-scripts, integration-tests, seed-scripts]

# Tech tracking
tech-stack:
  added:
    - fiona>=1.10.0 (SHP reading with CRS-aware reprojection from EPSG:2240 to EPSG:4326)
  patterns:
    - Typer single-command app: invoking runner.invoke(app, [args]) without subcommand prefix
    - SHP CRS reprojection: fiona.transform.transform_geom(src.crs, "EPSG:4326", geom)
    - OfficialGeocoding auto-set pattern: check admin_overrides first, then INSERT ON CONFLICT DO NOTHING
    - Batch commit: conn.commit() every 100 records for memory efficiency

key-files:
  created:
    - src/civpulse_geo/cli/__init__.py
    - src/civpulse_geo/cli/parsers.py
    - tests/test_import_cli.py
  modified:
    - pyproject.toml (added fiona dependency + geo-import entry point)

key-decisions:
  - "Typer single-command app: app has only one command, so runner.invoke does NOT need subcommand prefix in tests or CLI calls"
  - "SHP reprojection: use fiona.transform.transform_geom instead of geopandas (too heavy); fiona alone is sufficient"
  - "OfficialGeocoding auto-set uses INSERT ON CONFLICT (address_id) DO NOTHING to preserve any existing official record whether admin-set or previously imported"
  - "geocoding_results upsert uses ON CONFLICT ON CONSTRAINT uq_geocoding_address_provider DO UPDATE to refresh coordinates on re-import"
  - "ROOFTOP location_type and confidence=1.0 for all county GIS imports (authoritative rooftop-level data)"

patterns-established:
  - "GIS parser uniform schema: each parser returns list[dict] with {'properties': {...}, 'geometry': {'coordinates': [lng, lat]}}"
  - "Bibb County field mapping: FULLADDR + City_1 + ZIP_1 + hardcoded state=GA"
  - "Admin override priority: SELECT admin_overrides before OfficialGeocoding insert — zero override risk"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04]

# Metrics
duration: 25min
completed: 2026-03-19
---

# Phase 3 Plan 02: GIS Data Import CLI Summary

**Typer CLI (geo-import) that loads Bibb County GeoJSON/KML/SHP files as provider "bibb_county_gis" geocoding results with upsert semantics and OfficialGeocoding auto-set respecting admin override priority**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-19T14:30:00Z
- **Completed:** 2026-03-19T14:55:00Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 5

## Accomplishments

- Three file format parsers (GeoJSON via stdlib json, KML via stdlib xml.etree, SHP via fiona) all return uniform feature dict schema
- SHP parser auto-detects CRS and reprojects from EPSG:2240 to EPSG:4326 via fiona.transform.transform_geom
- CLI import command upserts addresses (ON CONFLICT DO NOTHING) and geocoding_results (ON CONFLICT DO UPDATE) for idempotent re-import
- OfficialGeocoding auto-set checks admin_overrides first; INSERT ON CONFLICT DO NOTHING preserves any existing official record
- Summary statistics printed after each run: total, inserted, updated, skipped, errors
- 13 new tests (10 parser + 3 CLI) added; full test suite at 142 passing tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Multi-format parsers for GeoJSON, KML, and SHP** - `62e0a26` (feat)
2. **Task 2: CLI import command with upsert and OfficialGeocoding auto-set** - `059677f` (feat)

_Note: Both tasks used TDD (RED tests written first, then GREEN implementation)_

## Files Created/Modified

- `src/civpulse_geo/cli/__init__.py` - Typer app with import_gis command, upsert loop, OfficialGeocoding auto-set
- `src/civpulse_geo/cli/parsers.py` - load_geojson, load_kml, load_shp with uniform feature dict output
- `tests/test_import_cli.py` - 13 tests covering all three parsers plus CLI import command
- `pyproject.toml` - Added fiona>=1.10.0 dependency and geo-import entry point in [project.scripts]

## Decisions Made

- **Typer single-command app invocation:** When a Typer app has only one command registered via `@app.command("import")`, the app acts as that command directly. Tests must call `runner.invoke(app, [file, ...])` without the "import" prefix — calling with "import" as first arg causes "Got unexpected extra argument" error.
- **fiona over geopandas for SHP:** fiona alone provides CRS-aware reprojection via `transform_geom`; geopandas is unnecessary weight.
- **geocoding_results DO UPDATE vs DO NOTHING:** Plan specified DO UPDATE to refresh coordinates on re-import (upsert semantics). The seed.py script used DO NOTHING — this CLI intentionally uses DO UPDATE to handle coordinate corrections in updated GIS data.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed CLI test invocation pattern**
- **Found during:** Task 2 (CLI command test execution)
- **Issue:** Plan test template used `runner.invoke(app, ["import", str(path), ...])` but single-command Typer apps treat first arg as FILE input, not subcommand name — caused "Got unexpected extra argument" error
- **Fix:** Updated tests to call `runner.invoke(app, [str(path), ...])` without "import" prefix
- **Files modified:** tests/test_import_cli.py
- **Verification:** All 13 CLI tests pass with corrected invocation
- **Committed in:** 059677f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Single fix required for test correctness, no scope changes.

## Issues Encountered

None beyond the Typer invocation pattern corrected above.

## User Setup Required

None - no external service configuration required. The `geo-import` CLI requires a running PostgreSQL database with the existing schema (run `uv run alembic upgrade head` if not already done).

## Next Phase Readiness

- GIS data import CLI is ready: `uv run geo-import data/SAMPLE_Address_Points.geojson`
- Address cache can now be pre-populated with county-authoritative geocoding data
- OfficialGeocoding table will be populated for all imported addresses (where no admin override exists)
- Phase 03 Plan 03 (USPS validation) can proceed — no blockers from this plan

---
*Phase: 03-validation-and-data-import*
*Completed: 2026-03-19*
