---
phase: 14-cascade-orchestrator-and-consensus-scoring
plan: "01"
subsystem: api
tags: [pydantic, sqlalchemy, alembic, config, cascade, consensus-scoring]

# Dependency graph
requires:
  - phase: 13-spell-correction-and-fuzzy-phonetic-matching
    provides: FuzzyMatcher, SpellCorrector services, GIN indexes, g7d4e0f3a6b2 Alembic head

provides:
  - "cascade_enabled flag and 12 new Settings fields (timeouts + provider weights)"
  - "Alembic migration h8e5f1g4a7b3 adding set_by_stage TEXT nullable on official_geocoding"
  - "OfficialGeocoding.set_by_stage ORM field"
  - "GeocodeProviderResult.is_outlier field"
  - "CascadeTraceStage Pydantic model"
  - "GeocodeResponse.cascade_trace and would_set_official fields"

affects:
  - 14-02-cascade-orchestrator
  - 14-03-api-integration

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic Settings: env-var-readable config fields with sensible defaults, no instantiation change"
    - "Alembic: nullable column addition chains from prior head revision"
    - "Schema extension: new fields default to None/False for backward compatibility"

key-files:
  created:
    - alembic/versions/h8e5f1g4a7b3_add_set_by_stage_to_official_geocoding.py
  modified:
    - src/civpulse_geo/config.py
    - src/civpulse_geo/models/geocoding.py
    - src/civpulse_geo/schemas/geocoding.py

key-decisions:
  - "cascade_enabled defaults True — opt-out via CASCADE_ENABLED=false env var"
  - "set_by_stage is nullable so existing rows (pre-cascade) remain valid with NULL"
  - "is_outlier/cascade_trace/would_set_official all default to False/None — zero backward-compat risk"
  - "CascadeTraceStage placed before GeocodeResponse so forward reference is not needed"

patterns-established:
  - "Plan 01 establishes contracts only — no behavioral change; all new fields are wired in Plan 02"

requirements-completed: [CASC-02, CASC-04, CONS-02, CONS-03, CONS-05, CONS-06]

# Metrics
duration: 2min
completed: "2026-03-29"
---

# Phase 14 Plan 01: Cascade Infrastructure — Config, Migration, and Schema Contracts

**Cascade config (12 fields), Alembic migration for set_by_stage, and backward-compatible Pydantic schema extensions for cascade trace and outlier detection**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-29T15:29:41Z
- **Completed:** 2026-03-29T15:31:35Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Extended Settings with cascade_enabled, 4 timeout budget fields, and 6 provider weight fields — all env-var readable via Pydantic BaseSettings
- Created h8e5f1g4a7b3 Alembic migration adding nullable set_by_stage column, chaining from g7d4e0f3a6b2 head
- Extended GeocodeProviderResult with is_outlier, GeocodeResponse with cascade_trace and would_set_official, and added CascadeTraceStage model
- All 430 tests pass (2 pre-existing fixture-missing failures unrelated to this plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend config.py with cascade settings** - `1dc6f95` (feat)
2. **Task 2: Alembic migration and ORM for set_by_stage** - `4eb1fe8` (feat)
3. **Task 3: Extend Pydantic schemas with cascade response fields** - `9957830` (feat)

## Files Created/Modified

- `src/civpulse_geo/config.py` - Added 12 new Settings fields: cascade_enabled, timeout budgets, provider weights
- `alembic/versions/h8e5f1g4a7b3_add_set_by_stage_to_official_geocoding.py` - Migration adding set_by_stage TEXT nullable
- `src/civpulse_geo/models/geocoding.py` - OfficialGeocoding.set_by_stage mapped column added
- `src/civpulse_geo/schemas/geocoding.py` - is_outlier, CascadeTraceStage, cascade_trace, would_set_official added

## Decisions Made

- cascade_enabled defaults True — callers opt-out via CASCADE_ENABLED=false (consistent with feature-flag pattern)
- set_by_stage is nullable so all existing official_geocoding rows remain valid; values like "exact_match_consensus", "fuzzy_consensus", "single_provider" populated in Plan 02
- CascadeTraceStage placed before GeocodeResponse to avoid forward reference issues
- Worktree was behind main by Phases 12 and 13 commits — merged main before executing to ensure correct Alembic head (g7d4e0f3a6b2)

## Deviations from Plan

None — plan executed exactly as written. One deviation note: worktree branch was missing Phase 12-13 commits; merged main to resolve (Rule 3 — blocking issue, missing dependency context).

## Issues Encountered

- Worktree branch was created before Phase 12/13 commits landed on main. Merged `main` into worktree branch before starting to ensure alembic head migration g7d4e0f3a6b2 was available.
- 2 pre-existing test failures exist unrelated to this plan:
  - `tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features` — missing data/SAMPLE_Address_Points.geojson fixture
  - `tests/test_load_oa_cli.py::TestLoadOaImport::test_parse_oa_feature_empty_strings_to_none` — pre-existing assertion failure from Phase 8

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 02 (CascadeOrchestrator) can now import `settings.cascade_enabled`, `settings.exact_match_timeout_ms`, etc.
- Plan 02 can set `official_geocoding.set_by_stage` when auto-setting the official result
- Plan 03 (API integration) can serialize `cascade_trace` and `would_set_official` from GeocodeResponse
- All contracts established; Plans 02 and 03 have no infrastructure dependency on this plan remaining open

---
*Phase: 14-cascade-orchestrator-and-consensus-scoring*
*Completed: 2026-03-29*

## Self-Check: PASSED

All files present and all task commits verified:
- FOUND: src/civpulse_geo/config.py
- FOUND: alembic/versions/h8e5f1g4a7b3_add_set_by_stage_to_official_geocoding.py
- FOUND: src/civpulse_geo/models/geocoding.py
- FOUND: src/civpulse_geo/schemas/geocoding.py
- FOUND: commit 1dc6f95 (Task 1)
- FOUND: commit 4eb1fe8 (Task 2)
- FOUND: commit 9957830 (Task 3)
