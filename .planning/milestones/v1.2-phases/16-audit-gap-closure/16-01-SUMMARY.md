---
phase: 16-audit-gap-closure
plan: 01
subsystem: api
tags: [bug-fix, fuzzy-matching, startup-wiring, verification, audit-gap-closure]

# Dependency graph
requires:
  - phase: 13-spell-correction-and-fuzzy-phonetic-matching
    provides: FuzzyMatcher service, SpellCorrector service, all Phase 13 requirements
  - phase: 15-llm-sidecar
    provides: complete cascade pipeline up to LLM stage
provides:
  - FuzzyMatcher wired to app.state at startup — cascade stage 3 now reachable at runtime
  - Legacy geocode path 5-tuple unpack fix — no ValueError on all-NO_MATCH local provider runs
  - Phase 13 VERIFICATION.md with 6 requirement confirmations (SPELL-01/02/03, FUZZ-02/03/04)
  - FIX-04 documentation confirmed accurate (scourgify=0.3, Tiger=0.4)
affects:
  - Cascade stage 3 (fuzzy matching) — now reachable at runtime via app.state.fuzzy_matcher

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TDD RED/GREEN: regression test written before bug fix
    - Stateless startup wiring: FuzzyMatcher.__init__ stores session_factory only, no try/except needed

key-files:
  created:
    - .planning/phases/13-spell-correction-and-fuzzy-phonetic-matching/13-VERIFICATION.md
  modified:
    - src/civpulse_geo/main.py (FuzzyMatcher import + app.state.fuzzy_matcher assignment)
    - src/civpulse_geo/services/geocoding.py (3-tuple → 5-tuple unpack at line 214)
    - tests/test_geocoding_service.py (test_legacy_geocode_no_match_does_not_raise_value_error)

key-decisions:
  - "FuzzyMatcher wiring placed after spell_corrector block, before LLM corrector block — matches logical pipeline order (normalize → spell-correct → fuzzy → LLM)"
  - "No try/except around FuzzyMatcher init — constructor only stores session_factory, cannot fail at construction time"
  - "5-tuple unpack discard pattern (_, _) used for suffix and directional — they are not needed in the warning log message"

# Metrics
duration: 15min
completed: 2026-03-29
---

# Phase 16 Plan 01: Audit Gap Closure Summary

**FuzzyMatcher startup wiring, legacy 5-tuple ValueError fix, Phase 13 VERIFICATION.md with 6 requirement confirmations, FIX-04 documentation verified**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-03-29T18:30:00Z
- **Tasks:** 3
- **Files modified:** 4 (1 created)

## Accomplishments

- Fixed `_legacy_geocode` ValueError: changed 3-tuple unpack to 5-tuple in the "all NO_MATCH" warning block at `geocoding.py:214`
- Added regression test `test_legacy_geocode_no_match_does_not_raise_value_error` confirming the fix (TDD RED/GREEN)
- Wired `FuzzyMatcher` to `app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)` in `lifespan()` — cascade stage 3 is now reachable at runtime
- Created `13-VERIFICATION.md` documenting all 6 Phase 13 requirements as verified with evidence and test counts
- Confirmed `REQUIREMENTS.md` FIX-04 already correctly states scourgify=0.3, Tiger=0.4 — no change needed
- Full test suite: 504 passed, 11 pre-existing failures, zero new failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix legacy 5-tuple unpack and add regression test** — `367a208` (fix)
2. **Task 2: Wire FuzzyMatcher to app startup** — `71c59aa` (feat)
3. **Task 3: Create Phase 13 VERIFICATION.md and confirm FIX-04 docs** — `91d5b01` (docs)

## Files Created/Modified

- `src/civpulse_geo/services/geocoding.py` — Line 214: `street_number, street_name, postal_code, _, _ = _parse_input_address(normalized)` (was 3-tuple)
- `tests/test_geocoding_service.py` — Added `test_legacy_geocode_no_match_does_not_raise_value_error` (TDD regression test)
- `src/civpulse_geo/main.py` — Added `from civpulse_geo.services.fuzzy import FuzzyMatcher` + `app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)` + `logger.info("FuzzyMatcher registered")`
- `.planning/phases/13-spell-correction-and-fuzzy-phonetic-matching/13-VERIFICATION.md` — Formal verification report for SPELL-01/02/03 and FUZZ-02/03/04

## Decisions Made

- **FuzzyMatcher after spell_corrector block** — placement follows logical cascade order: normalize → spell-correct → fuzzy → LLM; keeps startup wiring sequential and readable
- **No try/except for FuzzyMatcher** — `FuzzyMatcher.__init__` only stores `session_factory`; it cannot fail; adding try/except would mask real import errors
- **5-tuple discard pattern** — `_, _` used for `street_suffix` and `street_directional` in the warning log; they are not needed for the warning message

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all changes are substantive fixes, not stubs.

## Self-Check: PASSED

All files verified present. All task commits (367a208, 71c59aa, 91d5b01) verified in git log.

---
*Phase: 16-audit-gap-closure*
*Completed: 2026-03-29*
