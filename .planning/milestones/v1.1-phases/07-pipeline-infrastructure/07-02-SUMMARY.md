---
phase: 07-pipeline-infrastructure
plan: 02
subsystem: database
tags: [sqlalchemy, geoalchemy2, alembic, typer, rich, openaddresses, nad, postgis]

# Dependency graph
requires:
  - phase: 07-01
    provides: is_local property on GeocodingProvider ABC (establishes local provider bypass pattern)
  - phase: 06-validation
    provides: Alembic migration chain (a3d62fae3d64 validation results migration)
provides:
  - openaddresses_points staging table ORM model with GiST spatial index and composite B-tree lookup index
  - nad_points staging table ORM model with GiST spatial index and composite B-tree lookup index
  - Alembic migration c1f84b2e9a07 creating both staging tables
  - load-oa CLI command stub (Phase 8 will implement data loading)
  - load-nad CLI command stub (Phase 10 will implement data loading)
  - rich installed as project dependency
affects:
  - phase 08 (OpenAddresses provider — uses openaddresses_points table and load-oa command)
  - phase 10 (NAD provider — uses nad_points table and load-nad command)

# Tech tracking
tech-stack:
  added:
    - rich>=14.3.3 (progress bars for CLI commands)
  patterns:
    - Geography column pattern with spatial_index=False + create_geospatial_index deferred creation
    - source_hash UniqueConstraint for upsert support on staging tables
    - CLI command stubs with placeholder echo for phases that implement data loading later

key-files:
  created:
    - src/civpulse_geo/models/openaddresses.py
    - src/civpulse_geo/models/nad.py
    - alembic/versions/c1f84b2e9a07_add_local_provider_staging_tables.py
    - tests/test_load_oa_cli.py
    - tests/test_load_nad_cli.py
  modified:
    - src/civpulse_geo/models/__init__.py
    - src/civpulse_geo/cli/__init__.py
    - pyproject.toml
    - uv.lock
    - tests/test_import_cli.py (fix subcommand routing after multi-command Typer app)
    - tests/test_geocoding_service.py (fix TestLocalProviderBypass mock setup)

key-decisions:
  - "Staging table source_hash is String(64) to hold SHA-256 hex digests for upsert deduplication"
  - "Geography columns use spatial_index=False + deferred create_geospatial_index per project pattern"
  - "CLI stubs use typer.Exit(0) not return to ensure clean exit code from Typer runner"
  - "load-oa validates .geojson.gz extension; load-nad validates file existence only (Phase 10 validates TXT format)"

patterns-established:
  - "Staging table pattern: source_hash UniqueConstraint + GiST spatial index + composite B-tree lookup index"
  - "CLI stub pattern: validate file existence, echo placeholder message, raise typer.Exit(0)"

requirements-completed: [PIPE-03, PIPE-04, PIPE-05, PIPE-06]

# Metrics
duration: 25min
completed: 2026-03-22
---

# Phase 07 Plan 02: Staging Tables and CLI Stubs Summary

**openaddresses_points and nad_points staging tables with GiST spatial indexes, ORM models, and load-oa/load-nad Typer command stubs with rich installed**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-22T00:00:00Z
- **Completed:** 2026-03-22T00:25:00Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Created OpenAddressesPoint and NADPoint SQLAlchemy ORM models with Geography columns and UniqueConstraint on source_hash for upsert deduplication
- Created Alembic migration c1f84b2e9a07 chaining from a3d62fae3d64, creating both staging tables with GiST spatial indexes and composite B-tree lookup indexes
- Added load-oa and load-nad CLI command stubs to the Typer app with rich installed; both validate file existence and display placeholder messages for phases 8 and 10
- Fixed pre-existing bugs in tests (TestLocalProviderBypass mock setup and TestImportGISCommand subcommand routing after multi-command Typer app)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ORM models and Alembic migration** - `52a934e` (feat)
2. **Task 2: Install rich and create CLI command stubs with tests** - `4812259` (feat)

**Plan metadata:** (created after SUMMARY.md)

## Files Created/Modified
- `src/civpulse_geo/models/openaddresses.py` - OpenAddressesPoint ORM model with Geography, source_hash UniqueConstraint, region/postcode/street_name columns for composite index
- `src/civpulse_geo/models/nad.py` - NADPoint ORM model with Geography, source_hash UniqueConstraint, state/zip_code/street_name columns for composite index
- `src/civpulse_geo/models/__init__.py` - Added OpenAddressesPoint and NADPoint to exports
- `alembic/versions/c1f84b2e9a07_add_local_provider_staging_tables.py` - Migration creating both tables with GiST spatial indexes, composite B-tree lookup indexes, and unique source_hash constraints
- `src/civpulse_geo/cli/__init__.py` - Added rich import, load-oa and load-nad command stubs
- `pyproject.toml` - rich>=14.3.3 dependency added
- `tests/test_load_oa_cli.py` - PIPE-05 CLI registration tests
- `tests/test_load_nad_cli.py` - PIPE-06 CLI registration tests
- `tests/test_import_cli.py` - Fixed TestImportGISCommand to include "import" subcommand name (required after app gained multiple commands)
- `tests/test_geocoding_service.py` - Fixed TestLocalProviderBypass: added is_local=False to _make_provider, fixed _make_db_for_local_provider to return None from OfficialGeocoding query

## Decisions Made
- Used `String(64)` for source_hash columns (SHA-256 produces 64 hex chars)
- Geography columns use `spatial_index=False` + deferred `create_geospatial_index` per the project's established pattern from initial_schema migration
- load-oa validates `.geojson.gz` extension explicitly; load-nad only validates file existence (format validation deferred to Phase 10)
- CLI stubs use `raise typer.Exit(0)` pattern to ensure clean exit with Typer's CliRunner

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TestLocalProviderBypass mock returning wrong object for OfficialGeocoding query**
- **Found during:** Task 2 (full test suite verification)
- **Issue:** `_make_db_for_local_provider` mock returned same `addr_result` (spec'd as Address) for all execute calls. When `_get_official` queried OfficialGeocoding, the mock's `first()` returned an Address mock, causing `AttributeError: Mock object has no attribute 'geocoding_result_id'`
- **Fix:** Changed `db.execute = AsyncMock(return_value=addr_result)` to `AsyncMock(side_effect=[addr_result, none_result])` where `none_result` returns `None` from `first()` (no official geocoding set)
- **Files modified:** tests/test_geocoding_service.py
- **Verification:** All 5 TestLocalProviderBypass tests pass
- **Committed in:** 4812259 (Task 2 commit)

**2. [Rule 1 - Bug] Fixed TestImportGISCommand to include "import" subcommand after multi-command Typer app**
- **Found during:** Task 2 (full test suite verification)
- **Issue:** Tests invoked CLI with `[str(GEOJSON_PATH), "--database-url", ...]` but Typer now treats the file path as a subcommand name since the app has multiple commands (import, load-oa, load-nad). Tests failed with "No such command '/path/to/file.geojson'"
- **Fix:** Added "import" as first argument in `runner.invoke()` calls for TestImportGISCommand tests
- **Files modified:** tests/test_import_cli.py
- **Verification:** TestImportGISCommand::test_import_unsupported_format passes; data-dependent tests still fail due to pre-existing missing sample data files
- **Committed in:** 4812259 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 pre-existing bugs triggered by our changes)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
- `tests/test_import_cli.py` has 10 tests that require sample data files (`data/SAMPLE_Address_Points.geojson`, `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml`) that are gitignored and absent from this environment. These are pre-existing failures that predate this plan. Logged to `deferred-items.md`.
- 191 tests pass excluding the data-dependent tests in test_import_cli.py.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 8 (OpenAddresses provider): `openaddresses_points` table schema defined, `load-oa` CLI stub registered — Phase 8 only needs to implement data loading logic
- Phase 10 (NAD provider): `nad_points` table schema defined, `load-nad` CLI stub registered — Phase 10 only needs to implement data loading logic
- Both staging tables require `alembic upgrade head` on the target database before any data can be loaded

---
*Phase: 07-pipeline-infrastructure*
*Completed: 2026-03-22*

## Self-Check: PASSED

- FOUND: src/civpulse_geo/models/openaddresses.py
- FOUND: src/civpulse_geo/models/nad.py
- FOUND: alembic/versions/c1f84b2e9a07_add_local_provider_staging_tables.py
- FOUND: tests/test_load_oa_cli.py
- FOUND: tests/test_load_nad_cli.py
- FOUND: commit 52a934e (Task 1)
- FOUND: commit 4812259 (Task 2)
