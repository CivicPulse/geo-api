---
phase: 08-openaddresses-provider
plan: 02
subsystem: database
tags: [openaddresses, gzip, ndjson, usaddress, upsert, postgis, rich, cli]

# Dependency graph
requires:
  - phase: 07-pipeline-infrastructure
    provides: openaddresses_points staging table with uq_oa_source_hash constraint and load-oa CLI stub

provides:
  - load-oa CLI command with full NDJSON import logic replacing the Phase 7 stub
  - _parse_street_components helper for usaddress-based suffix extraction
  - _parse_oa_feature helper for coordinate validation and empty-to-None conversion
  - _upsert_oa_batch helper with ON CONFLICT ON CONSTRAINT uq_oa_source_hash DO UPDATE

affects:
  - 08-openaddresses-provider (plan 03+: provider queries openaddresses_points table populated by this command)
  - 09-tiger-provider
  - 10-nad-provider

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Two-pass .geojson.gz import: count lines first for Rich progress bar total, then stream and process
    - Batch upsert using raw SQL with ON CONFLICT + RETURNING (xmax = 0) AS was_inserted for insert vs update accounting
    - usaddress.parse() for StreetNamePostType suffix extraction with fallback to full street when no StreetName tokens found
    - Empty-string-to-None normalization via `val or None` pattern on all OA string properties

key-files:
  created: []
  modified:
    - src/civpulse_geo/cli/__init__.py
    - tests/test_load_oa_cli.py

key-decisions:
  - "OA hash property used directly as source_hash (not recomputed) — avoids SHA-256 overhead, trusts OA source deduplication"
  - "engine.connect() used instead of engine.begin() so _upsert_oa_batch can call conn.commit() per batch for incremental durability"
  - "Two-pass approach (count then import) accepted for clean progress bar despite reading compressed file twice"

patterns-established:
  - "_parse_X_feature / _upsert_X_batch helpers pattern: makes each concern unit-testable without CLI invocation"
  - "Malformed JSON lines and features without coordinates are skipped and counted, never raise exceptions"

requirements-completed: [OA-01]

# Metrics
duration: 8min
completed: 2026-03-22
---

# Phase 8 Plan 02: load-oa NDJSON Import Summary

**Functional load-oa CLI command with gzip NDJSON streaming, usaddress suffix parsing, empty-to-NULL normalization, and ON CONFLICT upsert into openaddresses_points**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-22T19:53:00Z
- **Completed:** 2026-03-22T20:01:45Z
- **Tasks:** 1 (TDD: RED test commit + GREEN feat commit)
- **Files modified:** 2

## Accomplishments
- Replaced load-oa stub with full gzip NDJSON streaming import processing 1000-row batches
- Added `_parse_street_components` using usaddress.parse() to extract StreetNamePostType tokens as street_suffix
- Added `_parse_oa_feature` with coordinate validation, empty-string-to-None normalization, and missing hash guard
- Added `_upsert_oa_batch` with `ON CONFLICT ON CONSTRAINT uq_oa_source_hash DO UPDATE` and `RETURNING (xmax = 0) AS was_inserted` for insert/update accounting
- Two-pass file reading enables Rich progress bar with `MofNCompleteColumn` and `TimeElapsedColumn`
- Summary prints processed/inserted/updated/skipped counts and elapsed time
- 9 new tests in `TestLoadOaImport` class; all 13 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement load-oa NDJSON import with batch upsert** - `d921395` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD RED phase confirmed import failure before GREEN implementation._

## Files Created/Modified
- `src/civpulse_geo/cli/__init__.py` - Added gzip/usaddress imports, OA_BATCH_SIZE constant, _parse_street_components, _parse_oa_feature, _upsert_oa_batch helpers, and full load_openaddresses function body replacing stub
- `tests/test_load_oa_cli.py` - Added TestLoadOaImport with 9 tests covering street parsing, feature parsing, batch upsert, and end-to-end CLI invocation with mock DB

## Decisions Made
- Used `engine.connect()` rather than `engine.begin()` so `_upsert_oa_batch` can call `conn.commit()` per batch — incremental durability for large imports
- OA hash used directly as `source_hash` (not recomputed) — trusts OA's own deduplication scheme and avoids SHA-256 overhead on 60k+ rows
- Two-pass approach (count lines first for progress bar) accepted over single-pass with indeterminate bar — better UX outweighs reading compressed file twice

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failures in `tests/test_import_cli.py` (missing `data/SAMPLE_Address_Points.geojson`) and `tests/test_oa_provider.py` (missing `civpulse_geo.providers.openaddresses` module) confirmed as out-of-scope pre-existing failures, not caused by this plan's changes.

## User Setup Required

None - no external service configuration required. The load-oa command requires a running PostgreSQL instance with the openaddresses_points table (created by Phase 7 migrations).

## Next Phase Readiness
- `load-oa` is functional and can populate `openaddresses_points` from .geojson.gz files
- Phase 8 Plan 01's `OAGeocodingProvider` and `OAValidationProvider` can now query the populated table
- Ready for Phase 8 Plan 03+ (OA provider query implementation against populated staging table)

## Self-Check: PASSED

- FOUND: src/civpulse_geo/cli/__init__.py
- FOUND: tests/test_load_oa_cli.py
- FOUND: .planning/phases/08-openaddresses-provider/08-02-SUMMARY.md
- FOUND commit d921395: feat(08-02): implement load-oa NDJSON import with batch upsert

---
*Phase: 08-openaddresses-provider*
*Completed: 2026-03-22*
