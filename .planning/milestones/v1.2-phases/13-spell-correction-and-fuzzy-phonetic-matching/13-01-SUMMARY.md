---
phase: 13-spell-correction-and-fuzzy-phonetic-matching
plan: 01
subsystem: api
tags: [symspellpy, spell-correction, postgresql, sqlalchemy, fastapi, alembic, geocoding]

# Dependency graph
requires:
  - phase: 12-correctness-fixes-and-db-prerequisites
    provides: pg_trgm GIN indexes on OA and NAD street_name columns; correct normalization pipeline
provides:
  - SpellCorrector class with correct_street_name() using symspellpy Verbosity.TOP
  - spell_dictionary PostgreSQL table populated from OA/NAD/Macon-Bibb staging tables
  - rebuild_dictionary() function for TRUNCATE+INSERT tokenization across all three staging tables
  - load_spell_corrector() function for startup in-memory SymSpell load
  - Alembic migration g7d4e0f3a6b2: spell_dictionary table + Macon-Bibb GIN trigram index
  - CLI hooks in load-oa, load-nad, gis import, load-macon-bibb for auto-rebuild (SPELL-03)
  - Standalone rebuild-dictionary CLI command
  - GeocodingService.geocode() spell_corrector parameter with _apply_spell_correction helper
  - API startup loads SpellCorrector into app.state.spell_corrector (D-09)
  - Single and batch geocoding endpoints pass spell_corrector to service (SPELL-01)
affects:
  - 13-02 (FuzzyMatcher — uses Macon-Bibb GIN index created here; both are Phase 13 components)
  - 14 (orchestrator depends on spell correction pre-processing existing addresses before cascade)

# Tech tracking
tech-stack:
  added:
    - symspellpy==6.9.0 (offline spell correction using symmetric delete algorithm)
    - editdistpy==0.2.0 (transitive dependency of symspellpy)
  patterns:
    - TDD RED/GREEN: tests written first, then implementation until tests pass
    - Per-word tokenization: split street names on spaces, correct each token independently, rejoin
    - Graceful degradation: SpellCorrector not loaded at startup logs warning but API continues
    - Sync engine at startup: sync SQLAlchemy create_engine used for SymSpell loading (synchronous operation)
    - CLI hook pattern: rebuild_dictionary(conn) called after final commit in each data-load command

key-files:
  created:
    - alembic/versions/g7d4e0f3a6b2_add_spell_dictionary_macon_bibb_trgm.py
    - src/civpulse_geo/models/spell_dictionary.py
    - src/civpulse_geo/spell/__init__.py
    - src/civpulse_geo/spell/corrector.py
    - tests/test_spell_corrector.py
  modified:
    - pyproject.toml (symspellpy dependency added)
    - src/civpulse_geo/models/__init__.py (SpellDictionary exported)
    - src/civpulse_geo/cli/__init__.py (rebuild hooks + rebuild-dictionary command)
    - src/civpulse_geo/main.py (startup SpellCorrector loading)
    - src/civpulse_geo/services/geocoding.py (spell_corrector param + _apply_spell_correction)
    - src/civpulse_geo/api/geocoding.py (spell_corrector passed to service, single + batch)

key-decisions:
  - "symspellpy 6.9.0 uses Verbosity.TOP to return only the top candidate per token (D-03)"
  - "Tokens < 4 characters are never spell-corrected to avoid over-correcting short names like Oak/Elm (D-04)"
  - "rebuild_dictionary uses TRUNCATE + unnest(string_to_array) for per-word tokenization across all three staging tables (D-08, D-10)"
  - "Tiger featnames included in rebuild with bare except guard — silently skipped if table absent (SPELL-02)"
  - "SpellCorrector uses sync engine at API startup — SymSpell create_dictionary_entry is synchronous (D-09)"
  - "_apply_spell_correction uppercases freeform before regex replacement since _parse_input_address returns uppercase tokens"

patterns-established:
  - "Spell module pattern: spell/__init__.py re-exports SpellCorrector, rebuild_dictionary, load_spell_corrector"
  - "Graceful degradation: all app.state accesses use getattr(request.app.state, 'spell_corrector', None)"
  - "CLI auto-rebuild: data-load commands call rebuild_dictionary(conn) after final commit inside with engine.connect() block"

requirements-completed:
  - SPELL-01
  - SPELL-02
  - SPELL-03

# Metrics
duration: 7min
completed: 2026-03-29
---

# Phase 13 Plan 01: Spell Corrector Summary

**symspellpy-backed offline street name correction with PostgreSQL spell_dictionary, auto-rebuild CLI hooks, and geocoding pipeline wiring before scourgify normalization**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-29T13:51:06Z
- **Completed:** 2026-03-29T13:58:17Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- SpellCorrector class corrects per-word street name typos (max_edit_distance=2, Verbosity.TOP) with short-token bypass (< 4 chars)
- spell_dictionary table + migration (g7d4e0f3a6b2) with Macon-Bibb GIN trigram index added in same migration
- rebuild_dictionary() uses TRUNCATE + unnest(string_to_array) to tokenize street names from OA, NAD, and Macon-Bibb staging tables; Tiger featnames included with silent except guard
- API workers load spell dictionary into memory at startup (one query, in-memory for all requests)
- Geocoding pipeline: spell correction applied before canonical_key/scourgify normalization via _apply_spell_correction helper
- Both single and batch geocoding endpoints pass spell_corrector to GeocodingService.geocode()
- 15 new unit tests, all passing; 392 total tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Add symspellpy dependency, Alembic migration, and SpellDictionary model** - `e315317` (feat)
2. **Task 2: Implement SpellCorrector class, rebuild_dictionary, and unit tests** - `30befe8` (feat)
3. **Task 3: Wire CLI rebuild hooks, startup loading, and geocoding pipeline** - `2cf019a` (feat)

## Files Created/Modified

- `alembic/versions/g7d4e0f3a6b2_add_spell_dictionary_macon_bibb_trgm.py` - Alembic migration: spell_dictionary table + Macon-Bibb GIN trgm index
- `src/civpulse_geo/models/spell_dictionary.py` - SpellDictionary ORM model (word, frequency, updated_at)
- `src/civpulse_geo/spell/__init__.py` - Public API exports for spell module
- `src/civpulse_geo/spell/corrector.py` - SpellCorrector, rebuild_dictionary(), load_spell_corrector()
- `tests/test_spell_corrector.py` - 15 unit tests (TDD RED/GREEN)
- `pyproject.toml` - symspellpy>=6.9.0 dependency
- `src/civpulse_geo/models/__init__.py` - SpellDictionary added to exports
- `src/civpulse_geo/cli/__init__.py` - rebuild hooks in 4 CLI commands + standalone rebuild-dictionary
- `src/civpulse_geo/main.py` - startup SpellCorrector loading into app.state
- `src/civpulse_geo/services/geocoding.py` - spell_corrector param, _apply_spell_correction static method
- `src/civpulse_geo/api/geocoding.py` - spell_corrector passed to service (single + batch endpoints)

## Decisions Made

- **symspellpy 6.9.0 Verbosity.TOP** — returns only the top suggestion per token, consistent with D-03
- **Tokens < 4 chars bypass correction** — short street names (Oak, Elm) have too many edit-distance neighbors, pass through uncorrected (D-04)
- **unnest(string_to_array)** — multi-word street names like "MARTIN LUTHER KING DR" tokenized into individual words for dictionary; single-word lookup works correctly
- **Tiger featnames with bare except** — SPELL-02 requires supplementing with Tiger data where available; bare except ensures startup never crashes when Tiger is absent
- **Sync engine at startup** — SymSpell.create_dictionary_entry is synchronous; using create_engine + sync connection avoids async/sync mismatch at startup

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Two pre-existing test failures unrelated to this plan:
- `tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features` — missing `data/SAMPLE_Address_Points.geojson` file
- `tests/test_load_oa_cli.py::TestLoadOaImport::test_parse_oa_feature_empty_strings_to_none` — pre-existing assertion on OA accuracy field

Both verified as pre-existing by git stash check. Logged to deferred-items scope.

## User Setup Required

None - no external service configuration required. API workers will pick up the spell dictionary automatically once staging tables are populated and the spell_dictionary migration is applied.

## Self-Check: PASSED

All created files verified present. All task commits (e315317, 30befe8, 2cf019a) verified in git log.

## Next Phase Readiness

- SpellCorrector subsystem complete and wired into geocoding pipeline
- Macon-Bibb GIN trigram index created (required by Plan 02 FuzzyMatcher)
- Plan 02 (FuzzyMatcher service) can proceed immediately — both pg_trgm and fuzzystrmatch extensions confirmed present from Phase 12

---
*Phase: 13-spell-correction-and-fuzzy-phonetic-matching*
*Completed: 2026-03-29*
