---
phase: 17-tech-debt-resolution
plan: 01
subsystem: api
tags: [fastapi, sqlalchemy, asyncio, pytest, geocoding, cascade-pipeline, timeout, caching]

requires:
  - phase: 16-audit-gap-closure
    provides: "Cascade pipeline wiring (FuzzyMatcher, LLM corrector, consensus scoring)"

provides:
  - "OA accuracy parser returns None for empty string (not 'parcel' default)"
  - "Per-provider timeout configuration (tiger_timeout_ms=3000, census_timeout_ms=2000)"
  - "Tiger GEOCODE_SQL uses restrict_region GA boundary subselect"
  - "_call_provider dispatches per-provider timeout using _timeout_map"
  - "CascadeOrchestrator cache-hit early exit with selectinload eager loading"
  - "Cache-hit path re-runs consensus on cached ORM rows"
  - "Cache-hit would_set_official wired from consensus winning cluster best candidate"
  - "Local providers still called fresh on cache hit"

affects:
  - "17-02 (remaining tech debt plans)"
  - "18-code-review (cascade pipeline stability)"
  - "23-e2e-validation (cache behavior and timeout behavior)"

tech-stack:
  added: []
  patterns:
    - "Per-provider timeout map: _timeout_map dict with provider_name key lookup, fallback to exact_match_timeout_ms"
    - "selectinload on Address.geocoding_results for cache detection in Stage 1 query"
    - "Cache-hit early exit pattern: check address.geocoding_results before Stage 2"
    - "Consensus re-run on cached ORM rows with would_set_official wired retroactively"

key-files:
  modified:
    - src/civpulse_geo/cli/__init__.py
    - src/civpulse_geo/config.py
    - src/civpulse_geo/services/cascade.py
    - src/civpulse_geo/providers/tiger.py
    - tests/test_cascade.py

key-decisions:
  - "DEBT-04: accuracy parser uses None default (not 'parcel') — empty string from OA features must not become a fake 'parcel' accuracy"
  - "DEBT-01: tiger_timeout_ms=3000 separate from exact_match_timeout_ms=2000 — PostGIS geocode() needs more time than HTTP providers"
  - "DEBT-01: _timeout_map dict inside _call_provider — reads current settings values at call time for test patchability"
  - "DEBT-01: Tiger GEOCODE_SQL restrict_region uses GA state boundary subselect — narrows Tiger's spatial search dramatically"
  - "DEBT-02: selectinload(Address.geocoding_results) in Stage 1 query — required for cache detection without N+1 lazy load"
  - "DEBT-02: cache-hit early exit placed after Stage 1 normalize block — normalized address needed before cache lookup"
  - "DEBT-02: would_set_official wired from consensus winning cluster best candidate on cache hit — D-05 retroactive provider weight changes"

patterns-established:
  - "Timeout map pattern: Build _timeout_map dict before wait_for, use .get(provider_name, default) — extensible to new providers"
  - "Cache-hit consensus: Re-run run_consensus on cached ORM rows, capture winning_cluster, derive best_candidate — mirrors Stage 6 logic"

requirements-completed: [DEBT-04, DEBT-01, DEBT-02]

duration: 6min
completed: 2026-03-29
---

# Phase 17 Plan 01: Tech Debt Resolution (DEBT-01, 02, 04) Summary

**OA accuracy parser fixed (None not 'parcel'), Tiger gets dedicated 3s timeout via per-provider map, and cascade cache-hit early exit wired with consensus re-run populating would_set_official retroactively**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-29T22:56:43Z
- **Completed:** 2026-03-29T23:02:24Z
- **Tasks:** 2 (TDD with RED/GREEN phases)
- **Files modified:** 5

## Accomplishments

- Fixed DEBT-04: OA accuracy="" now returns None instead of "parcel" — previously failing test_parse_oa_feature_empty_strings_to_none now passes
- Fixed DEBT-01: Tiger gets 3000ms timeout, other providers use 2000ms via per-provider `_timeout_map` dict; Tiger SQL uses restrict_region GA boundary subselect to narrow search space
- Fixed DEBT-02: CascadeOrchestrator now returns cache_hit=True on second lookup; local providers still called fresh; consensus re-runs on cached ORM rows with would_set_official wired from winner
- Added 8 new tests across 5 test classes covering per-provider timeout, fail-open timeout, cache-hit early exit, local providers on cache hit, and consensus winner wiring

## Task Commits

Each task was committed atomically:

1. **TDD RED - Failing tests for per-provider timeout and cache-hit early exit** - `9e52a72` (test)
2. **Task 1: Fix OA accuracy parser, add per-provider timeouts, optimize Tiger SQL** - `8d1c1ff` (feat)
3. **Task 2: Cache-hit early exit in CascadeOrchestrator** - `dacc45d` (feat)

## Files Created/Modified

- `src/civpulse_geo/cli/__init__.py` - Changed accuracy default from "parcel" to None for empty string input
- `src/civpulse_geo/config.py` - Added `tiger_timeout_ms: int = 3000` and `census_timeout_ms: int = 2000` fields
- `src/civpulse_geo/services/cascade.py` - Added `selectinload` import; updated Stage 1 query; added `_call_provider` per-provider timeout map; inserted cache-hit early exit block with local provider re-run and consensus re-run
- `src/civpulse_geo/providers/tiger.py` - Updated `GEOCODE_SQL` to pass GA state boundary array as restrict_region to `geocode()` function
- `tests/test_cascade.py` - Added `TestPerProviderTimeout`, `TestProviderTimeoutFailOpen`, `TestCacheHitEarlyExit`, `TestCacheHitLocalProvidersStillCalled`, `TestCacheHitConsensusReRun` test classes

## Decisions Made

- `_timeout_map` dict built inside `_call_provider` body (not at module level) so settings values are read at call time and can be patched in tests
- `selectinload(Address.geocoding_results)` added to Stage 1 query rather than a separate query — avoids N+1 lazy load issue
- Cache-hit early exit placed immediately after Stage 1 normalize trace append — normalized address must exist before cache lookup
- Cache-hit path uses same `haversine_m` min-distance logic as Stage 6 for `best_candidate` selection — consistency between normal and cache paths

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed pre-existing unused `local_providers`/`remote_providers` variables**
- **Found during:** Task 1 (ruff lint check)
- **Issue:** Two dict comprehensions assigned but never used — ruff F841 violations blocking clean lint
- **Fix:** Removed the two unused assignments (they were artifacts from an earlier refactor of the cascade pipeline)
- **Files modified:** `src/civpulse_geo/services/cascade.py`
- **Verification:** `uv run ruff check src/civpulse_geo/services/cascade.py` exits 0
- **Committed in:** `8d1c1ff` (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - pre-existing unused variable removal)
**Impact on plan:** Minor cleanup, no scope creep. Removes ruff noise that would have blocked acceptance criteria lint check.

## Issues Encountered

- Pre-existing test_import_cli.py fixture failures (10 failures) remain from missing `data/SAMPLE_Address_Points.geojson` file — pre-existing before this plan, out of scope for DEBT-01/02/04

## Known Stubs

None — all changes wire real behavior with no placeholder data.

## Next Phase Readiness

- DEBT-01, DEBT-02, DEBT-04 resolved — cascade pipeline is more robust under Tiger load with correct timeout semantics
- Cache-hit path is now correctness-verified with consensus re-run
- DEBT-03 (spell dictionary empty at startup) not addressed in this plan — covered by 17-02-PLAN.md
- Full test suite: 512 pass, 10 pre-existing failures in fixture tests (test_import_cli.py)

---
*Phase: 17-tech-debt-resolution*
*Completed: 2026-03-29*
