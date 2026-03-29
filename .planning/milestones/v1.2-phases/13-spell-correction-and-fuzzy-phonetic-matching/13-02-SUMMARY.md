---
phase: 13-spell-correction-and-fuzzy-phonetic-matching
plan: 02
subsystem: api
tags: [fuzzy-matching, pg_trgm, word_similarity, dmetaphone, fuzzystrmatch, postgresql, sqlalchemy, pytest]

# Dependency graph
requires:
  - phase: 13-01
    provides: Macon-Bibb GIN trigram index (g7d4e0f3a6b2 migration); pg_trgm and fuzzystrmatch extensions confirmed
  - phase: 12-correctness-fixes-and-db-prerequisites
    provides: GIN indexes on OA and NAD street_name columns; correct normalization pipeline
provides:
  - FuzzyMatcher service class at services/fuzzy.py
  - FuzzyMatchResult dataclass
  - similarity_to_confidence() function mapping 0.65-1.0 → 0.50-0.75
  - 30-address calibration corpus (test_fuzzy_calibration.py) with FUZZ-04 regression protection
  - Unit tests for FuzzyMatcher (14 tests in test_fuzzy_matcher.py)
affects:
  - 14 (orchestrator will call FuzzyMatcher.find_fuzzy_match() after exact providers return NO_MATCH)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TDD RED/GREEN: failing tests committed first, then implementation until tests pass
    - UNION ALL query pattern: three sub-queries per staging table joined with UNION ALL, ORDER BY score DESC, LIMIT 5
    - dmetaphone() SQL tiebreaker: separate SQL query using VALUES clause with dmetaphone() comparison
    - Calibration corpus: parameterized pytest with 30 entries, fixture-seeded mock DB session

key-files:
  created:
    - src/civpulse_geo/services/fuzzy.py
    - tests/test_fuzzy_matcher.py
    - tests/test_fuzzy_calibration.py

key-decisions:
  - "UNION ALL across OA/NAD/Macon-Bibb staging tables in single query (D-06) — avoids three round-trips"
  - "dmetaphone tiebreaker as second SQL query when candidates within 0.05 gap (D-12) — uses fuzzystrmatch extension already present"
  - "Calibration corpus uses mock session returning realistic rows — avoids real DB in CI while still testing confidence/threshold logic (D-15)"
  - "word_similarity(input, stored_name) argument order locked — input (needle) first per Research Pitfall 1"
  - "zip_code filtering uses LIKE prefix match for zip flexibility from Phase 12 fix"

# Metrics
duration: 8min
completed: 2026-03-29
---

# Phase 13 Plan 02: FuzzyMatcher Summary

**FuzzyMatcher service: pg_trgm word_similarity() across OA/NAD/Macon-Bibb with dmetaphone() tiebreaker, 30-address calibration corpus with CI regression protection**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-29T14:02:04Z
- **Completed:** 2026-03-29T14:10:04Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- FuzzyMatcher class queries all three local staging tables (openaddresses_points, nad_points, macon_bibb_points) via UNION ALL with word_similarity() >= 0.65 threshold
- dmetaphone() tiebreaker via SQL when top candidates score within 0.05 of each other (D-12)
- similarity_to_confidence() maps word_similarity 0.65-1.0 linearly to confidence 0.50-0.75 (D-07)
- Returns single best FuzzyMatchResult (D-14) or None when no candidate qualifies
- 30-address calibration corpus: 4 Issue #1 addresses + 26 generated (single/double typos, phonetic, transpositions, negatives, short names)
- 50 total tests pass (14 unit + 36 calibration = 50 new; 430 total pass excluding pre-existing failures)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for FuzzyMatcher** - `35071fb` (test)
2. **Task 1 GREEN + Task 2: FuzzyMatcher implementation + calibration corpus** - `95d2457` (feat), `5756e62` (feat)

## Files Created/Modified

- `src/civpulse_geo/services/fuzzy.py` — FuzzyMatcher service class, FuzzyMatchResult dataclass, similarity_to_confidence(), constants (FUZZY_SIMILARITY_THRESHOLD, FUZZY_TIEBREAK_GAP, FUZZY_CONFIDENCE_MIN, FUZZY_CONFIDENCE_MAX)
- `tests/test_fuzzy_matcher.py` — 14 unit tests for FuzzyMatcher (TDD RED/GREEN)
- `tests/test_fuzzy_calibration.py` — 30-address calibration corpus, 6 metadata tests, 30 parameterized tests

## Decisions Made

- **UNION ALL in single query** — Three sub-queries for OA, NAD, Macon-Bibb joined via UNION ALL with ORDER BY score DESC, LIMIT 5. Single DB round-trip for candidate retrieval
- **dmetaphone() as second SQL query** — When tiebreak needed, issue a second SQL query using VALUES clause + dmetaphone() comparison from fuzzystrmatch extension (already installed). Avoids Python phonetics dependency
- **Mock session for calibration** — Calibration corpus uses fixture-seeded mock sessions returning pre-defined rows at score 0.80. This validates the FuzzyMatcher confidence mapping and threshold logic without requiring a real DB in CI (D-15)
- **word_similarity(input, stored)** — Argument order locked per Research Pitfall 1: input (needle) first, stored value (haystack) second
- **ZIP prefix LIKE match** — zip_code filtering uses `LIKE '{prefix}%'` for flexibility with truncated zips from Phase 12 fix

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written.

**Note:** The dmetaphone tiebreaker was implemented as a second SQL query rather than a Python in-memory computation using the `doublemetaphone` package, which is not installed. The SQL-side approach (using fuzzystrmatch's dmetaphone() function) was the preferred approach per the plan's action description and keeps the phonetic computation in the DB where the fuzzystrmatch extension already exists.

## Issues Encountered

Two pre-existing test failures unrelated to this plan:
- `tests/test_import_cli.py` (8 failures) — missing `data/SAMPLE_Address_Points.geojson` and related data files
- `tests/test_load_oa_cli.py::TestLoadOaImport::test_parse_oa_feature_empty_strings_to_none` — pre-existing assertion

Both verified as pre-existing from plan 01 SUMMARY. 430 tests pass excluding these.

## Self-Check: PASSED

All created files verified present. All task commits (35071fb, 95d2457, 5756e62) verified in git log.
