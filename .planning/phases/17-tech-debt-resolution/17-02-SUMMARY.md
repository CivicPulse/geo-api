---
phase: 17-tech-debt-resolution
plan: "02"
subsystem: api
tags: [startup, spell-correction, symspellpy, sqlalchemy, python]

# Dependency graph
requires:
  - phase: 16-audit-gap-closure
    provides: FuzzyMatcher startup wiring and spell corrector loading at startup
  - phase: 13-spell-correction-and-fuzzy-phonetic-matching
    provides: rebuild_dictionary() and load_spell_corrector() in spell/corrector.py
provides:
  - Spell dictionary auto-rebuild in lifespan when table is empty and staging data exists
  - Startup skips rebuild when spell_dictionary already populated (D-08)
  - Startup skips rebuild with warning when staging tables also empty (D-07)
  - Rebuild logs timing (word count + elapsed ms)
affects: [phase-20-k8s-init-container, any phase testing startup behavior]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Belt-and-suspenders: app auto-rebuilds spell_dictionary at startup; K8s init container (Phase 20) pre-warms it"
    - "Startup auto-fix pattern: check empty table → check prerequisite data → fix → continue"

key-files:
  created:
    - tests/test_spell_startup.py
  modified:
    - src/civpulse_geo/main.py

key-decisions:
  - "DEBT-03: Only auto-rebuild when spell_dictionary is empty (dict_count == 0) — never TRUNCATE on every restart"
  - "DEBT-03: Only rebuild when staging tables have data (staging_count > 0) — silent skip with warning when no data available"
  - "rebuild_dictionary(conn) manages its own conn.commit() — no additional commit needed in lifespan"
  - "Use _text local alias inside try block to avoid conflict with any module-level text import"

patterns-established:
  - "Startup self-healing: detect empty prerequisite table, check if source data exists, rebuild if both conditions met"

requirements-completed: [DEBT-03]

# Metrics
duration: 4min
completed: 2026-03-29
---

# Phase 17 Plan 02: Tech Debt Resolution - Spell Dictionary Auto-Rebuild Summary

**Startup auto-rebuilds spell_dictionary when empty and staging tables have data, eliminating manual CLI step after data loads**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T22:57:01Z
- **Completed:** 2026-03-29T23:00:37Z
- **Tasks:** 1 (TDD: test + feat commits)
- **Files modified:** 2

## Accomplishments

- Spell dictionary auto-rebuild logic added to lifespan function in main.py — checks spell_dictionary row count before loading
- When dict is empty and any staging table (OA, NAD, Macon-Bibb) has data, rebuild_dictionary() is called automatically
- When dict already has rows, loads directly (no TRUNCATE on every restart, per D-08)
- When both dict and staging are empty, logs a warning and continues (per D-07, graceful degradation)
- Rebuild duration logged with word count and elapsed milliseconds
- 3 new tests added covering all 3 decision paths

## Task Commits

1. **Task 1 (RED): DEBT-03 failing tests** - `9a592da` (test)
2. **Task 1 (GREEN): DEBT-03 implementation + lint fix** - `8900739` (feat)

## Files Created/Modified

- `src/civpulse_geo/main.py` — Added auto-rebuild check block with staging table count query, timing, and logging
- `tests/test_spell_startup.py` — New test file: 3 tests covering empty+data, populated, and empty+no-data paths

## Decisions Made

- Used `_text` local alias inside the try block to avoid conflict with module-level `text` imports elsewhere
- `rebuild_dictionary(conn)` already calls `conn.commit()` internally — no additional commit added in lifespan
- Only checking `openaddresses_points + nad_points + macon_bibb_points` for staging count (not Tiger, which uses PostGIS functions not a staging table)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test failures in `tests/test_import_cli.py` (missing `data/SAMPLE_Address_Points.geojson` in this worktree — fixture was committed on a different branch) and `tests/test_load_oa_cli.py` (DEBT-04 accuracy parser bug, not in scope for this plan). These are out-of-scope pre-existing failures documented in PROJECT.md ("11 pre-existing failures in CLI fixture tests"). Our changes did not introduce or change these failures.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DEBT-03 complete: application startup is now self-healing for spell dictionary
- Phase 17-03 (DEBT-01: Tiger timeout) can proceed independently
- Phase 17-04 (DEBT-04: CLI accuracy parser) can proceed independently
- Phase 20 (K8s init container for spell dictionary pre-warm) should reference D-09 decision in context

---
*Phase: 17-tech-debt-resolution*
*Completed: 2026-03-29*
