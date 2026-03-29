---
phase: 14-cascade-orchestrator-and-consensus-scoring
plan: "02"
subsystem: services
tags: [cascade, consensus-scoring, haversine, clustering, async, sqlalchemy, pydantic]

# Dependency graph
requires:
  - phase: 14-01
    provides: "cascade_enabled settings, set_by_stage ORM field, CascadeTraceStage schema"
  - phase: 13-spell-correction-and-fuzzy-phonetic-matching
    provides: "FuzzyMatcher, SpellCorrector services"

provides:
  - "CascadeOrchestrator.run() — 6-stage async pipeline"
  - "CascadeResult dataclass"
  - "ProviderCandidate + Cluster — consensus scoring primitives"
  - "haversine_m() — in-Python great-circle distance"
  - "run_consensus() — greedy 100m clustering with outlier flagging"
  - "get_provider_weight() — provider trust weight lookup"

affects:
  - 14-03-api-integration

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.gather: parallel provider dispatch with per-task exception isolation"
    - "asyncio.wait_for: per-stage timeout budgets with graceful degradation"
    - "Greedy single-pass clustering: sort by weight desc, 100m join threshold"
    - "Weighted centroid: sum(w*coord) / sum(w) recomputed on each add()"
    - "official_loaded flag: avoids double _get_official() call when admin override detected"

key-files:
  created:
    - src/civpulse_geo/services/cascade.py
    - tests/test_cascade.py
  modified: []

key-decisions:
  - "official_loaded flag added to prevent double _get_official() DB call when admin override blocks auto-set"
  - "best_candidate selected as cluster member closest to weighted centroid (not simply first/highest-weight)"
  - "skip_single_low_conf initialized before winning_cluster block to allow reference in reload guard"
  - "Test mock side_effect sequences match exact DB call count per code path"

patterns-established:
  - "CascadeOrchestrator is stateless (like GeocodingService) — instantiate per request"
  - "Fuzzy weight scaling: effective_weight = provider_weight * (fuzzy_confidence / 0.80)"

requirements-completed: [CASC-01, CASC-03, CASC-04, CONS-01, CONS-02, CONS-04, CONS-05]

# Metrics
duration: 6min
completed: "2026-03-29"
---

# Phase 14 Plan 02: CascadeOrchestrator Service with Consensus Scoring

**CascadeOrchestrator with 6-stage pipeline: normalize, exact match (parallel), fuzzy, consensus clustering, auto-set official, commit — plus haversine distance, greedy 100m clustering, weighted centroids, and 1km outlier flagging**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-29T15:34:56Z
- **Completed:** 2026-03-29T15:40:49Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files created:** 2

## Accomplishments

- Implemented `haversine_m()` using stdlib math (R=6,371,000m) — no external dependency
- Implemented `get_provider_weight()` mapping provider names to settings.weight_* with 0.50 fallback for unknown providers
- Implemented `Cluster` with weighted centroid recomputed on each `add()` call (D-07)
- Implemented `run_consensus()`: sort by weight DESC, greedy 100m clustering, winning cluster by total_weight (D-10), 1km outlier flagging (CONS-03)
- Implemented `CascadeOrchestrator.run()` with all 6 stages and all D-* design decisions respected
- Parallel provider dispatch via `asyncio.gather` + per-provider `asyncio.wait_for` timeout
- Early-exit (D-12): skips fuzzy stage when any provider returns >= 0.80 confidence
- Consensus always runs (D-13): even on early-exit, consistent outlier flagging and set_by_stage
- Fuzzy weight scaling (D-09): effective_weight = provider_weight * (fuzzy_confidence / 0.80)
- Single-result handling (D-11): auto-set only when confidence >= 0.80
- Admin override protection (D-22): checks OfficialGeocoding (join check) + AdminOverride table before any write
- `on_conflict_do_update` for OfficialGeocoding with `set_by_stage` (not `on_conflict_do_nothing`)
- dry_run and trace modes fully implemented
- All 30 unit tests pass; 460 total tests pass (2 pre-existing fixture failures unrelated to this plan)

## Task Commits

Each TDD phase committed atomically:

1. **TDD RED: Failing tests** - `47ab2f9` (test)
2. **TDD GREEN + fix: Implementation + admin override fix** - `599d896` (feat)

## Files Created/Modified

- `src/civpulse_geo/services/cascade.py` — CascadeOrchestrator, CascadeResult, ProviderCandidate, Cluster, haversine_m, run_consensus, get_provider_weight (748 lines)
- `tests/test_cascade.py` — 30 unit tests covering all behaviors (732 lines)

## Decisions Made

- `official_loaded` flag added to avoid double `_get_official()` call when admin override detected — the admin check path calls `_get_official` inline, so the Stage 6 reload guard must be skipped
- `best_candidate` selected as cluster member with minimum haversine distance to weighted centroid (not first/highest-weight member) — this ensures the representative result is the one geographically closest to the consensus position
- `skip_single_low_conf` initialized to `False` before the `if winning_cluster:` block so it's safely in scope for the Stage 6 reload guard condition

## Deviations from Plan

None — plan executed exactly as written. One inline bug discovered during RED→GREEN:

**[Rule 1 - Bug] Double _get_official() call when admin override blocks auto-set**
- **Found during:** GREEN phase test run
- **Issue:** When admin override was detected, `_get_official` was called inside the admin override guard AND again in the Stage 6 reload block, causing the mock side_effect to run out
- **Fix:** Added `official_loaded: bool = False` flag; set to True after inline `_get_official()` call; Stage 6 reload guard checks `not official_loaded`
- **Files modified:** `src/civpulse_geo/services/cascade.py`
- **Commit:** `599d896`

## Known Stubs

None — all behaviors fully wired. Plan 03 (API integration) will wire `CascadeOrchestrator.run()` into `GeocodingService.geocode()` when `settings.cascade_enabled` is True.

## Self-Check: PASSED

- FOUND: src/civpulse_geo/services/cascade.py
- FOUND: tests/test_cascade.py
- FOUND: commit 47ab2f9 (TDD RED)
- FOUND: commit 599d896 (TDD GREEN)
- FOUND: class CascadeOrchestrator in cascade.py
- FOUND: class CascadeResult in cascade.py
- FOUND: class ProviderCandidate in cascade.py
- FOUND: class Cluster in cascade.py
- FOUND: def haversine_m in cascade.py
- FOUND: def run_consensus in cascade.py
- FOUND: def get_provider_weight in cascade.py
- FOUND: asyncio.gather in cascade.py
- FOUND: asyncio.wait_for in cascade.py
- FOUND: on_conflict_do_update (not do_nothing) in cascade.py
- FOUND: admin_override check in cascade.py
- FOUND: set_by_stage in cascade.py
- FOUND: 30 passing tests in tests/test_cascade.py
