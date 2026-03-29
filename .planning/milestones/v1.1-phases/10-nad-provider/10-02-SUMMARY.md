---
phase: 10-nad-provider
plan: 02
subsystem: database
tags: [nad, postgresql, copy, csv, zipfile, bulk-import, cli, typer, psycopg2]

# Dependency graph
requires:
  - phase: 10-nad-provider/10-01
    provides: NAD provider query logic, nad_points table, uq_nad_source_hash constraint
  - phase: 07-pipeline-infrastructure/07-02
    provides: load-oa CLI COPY pattern, _resolve_state helper, CLI stub wiring
provides:
  - Full load-nad CLI command replacing stub — ZIP streaming, state filtering, COPY pipeline
  - _resolve_city() helper with Post_City -> Inc_Muni -> County fallback chain
  - _parse_nad_row() helper for UUID brace stripping, WKT point building, column mapping
  - _flush_nad_batch() helper using copy_expert -> nad_temp -> ON CONFLICT upsert
  - NAD_COPY_SQL, NAD_UPSERT_SQL, CREATE_NAD_TEMP_TABLE constants
  - 17 tests covering state validation, city fallback, row parsing, COPY pipeline structure
affects: [nad-provider-users, data-loading-docs]

# Tech tracking
tech-stack:
  added: [csv (stdlib), io (stdlib), zipfile (stdlib)]
  patterns:
    - COPY-to-temp-table upsert pattern (identical to load-oa batch pattern but CSV-based)
    - ZIP streaming without disk extraction using io.TextIOWrapper over zf.open()
    - Two-pass counting (count pass then import pass) for Rich progress bar
    - State filtering during stream — only matching rows enter the COPY pipeline

key-files:
  created: []
  modified:
    - src/civpulse_geo/cli/__init__.py
    - tests/test_load_nad_cli.py

key-decisions:
  - "load-nad uses two-pass approach (count filtered rows then import) for accurate Rich progress bar — consistent with load-oa two-pass pattern"
  - "COPY targets nad_temp (TEXT columns) then upserts via ST_GeogFromText — avoids geography type handling in psycopg2 COPY"
  - "utf-8-sig encoding on TextIOWrapper handles UTF-8 BOM present in NAD ZIP files"
  - "UUID brace stripping via .strip().strip('{}') — produces 36-char source_hash matching uq_nad_source_hash constraint"
  - "City fallback is case-insensitive 'not stated' check — handles both 'Not stated' and 'Not Stated' variants in the source data"

patterns-established:
  - "COPY CSV pipeline: StringIO batch buffer -> csv.writer -> copy_expert -> temp table -> INSERT ON CONFLICT"
  - "ZIP streaming: zipfile.ZipFile -> zf.open(txt_name) -> io.TextIOWrapper(encoding='utf-8-sig') -> csv.DictReader"
  - "Batch flushing pattern: accumulate NAD_BATCH_SIZE rows, flush via _flush_nad_batch, reset buffer"

requirements-completed: [NAD-03]

# Metrics
duration: 4min
completed: 2026-03-24
---

# Phase 10 Plan 02: NAD Load CLI Summary

**Full COPY-based load-nad CLI replacing stub — streams CSV from ZIP, filters by state, upserts into nad_points via psycopg2 copy_expert through a temp table**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-24T09:30:39Z
- **Completed:** 2026-03-24T09:33:35Z
- **Tasks:** 1 (TDD: RED + GREEN + REFACTOR)
- **Files modified:** 2

## Accomplishments
- Replaced load-nad stub with full production implementation handling ZIP streaming, state filtering, city fallback, UUID brace stripping, and COPY-to-temp-table upsert
- Added `--state` as a required option reusing `_resolve_state` for FIPS/abbreviation resolution
- Implemented city fallback chain (`_resolve_city`) covering all three NAD city columns with case-insensitive "Not stated" skipping
- Added 17 unit tests covering state validation, city fallback logic, row parsing, column mapping, and coordinate handling

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement load-nad CLI with COPY-based import and tests** - `0ee849f` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD task — RED phase wrote failing tests, GREEN implemented the command, REFACTOR verified help text had no pipe-delimited references_

## Files Created/Modified
- `src/civpulse_geo/cli/__init__.py` - Added csv/io/zipfile imports, NAD constants (NAD_BATCH_SIZE, NAD_COPY_SQL, NAD_UPSERT_SQL, CREATE_NAD_TEMP_TABLE, TRUNCATE_NAD_TEMP), _resolve_city, _parse_nad_row, _flush_nad_batch helpers, and full load_nad command replacing stub
- `tests/test_load_nad_cli.py` - Extended with TestResolveCityFallback (5 tests), TestParseNadRow (6 tests), and 2 new TestLoadNadCli tests for --state required and invalid state handling

## Decisions Made
- Two-pass approach (count filtered rows, then import) is consistent with load-oa and provides accurate progress bar total
- COPY targets nad_temp (all TEXT columns) then ST_GeogFromText in the upsert SQL — this avoids geography type complications in psycopg2 COPY streams
- utf-8-sig encoding on TextIOWrapper handles BOM bytes present in real NAD ZIP files
- City fallback case-insensitivity covers both "Not stated" and "Not Stated" variants observed in NAD source data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing failures in `tests/test_import_cli.py` (10 tests) referencing `data/SAMPLE_Address_Points.geojson` — confirmed pre-existing by stash verification, out of scope.

## Next Phase Readiness
- Phase 10 is complete: NAD provider query logic (10-01) and NAD bulk COPY loader (10-02) are both implemented and tested
- NAD_r21_TXT.zip can now be loaded via `geo-import load-nad NAD_r21_TXT.zip --state GA` for any state
- nad_points table will be populated and the NAD provider registered at startup when _nad_data_available() returns True

## Self-Check: PASSED

All files verified present. Task commit 0ee849f confirmed in git log.

---
*Phase: 10-nad-provider*
*Completed: 2026-03-24*
