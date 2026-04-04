# Phase 18: Code Review — Findings Report

**Date:** 2026-03-29
**Scope:** Full codebase audit — 45 source files, 29 test files (527 tests)
**Teams:** Security, Stability, Performance

## Blocker Summary (Resolved In-Phase)

All blockers were resolved in plans 18-01, 18-02, 18-03. Listed here for completeness.

| ID | Team | Finding | Fix | Plan |
|----|------|---------|-----|------|
| SEC-01 | Security | Hardcoded DB credentials in config.py defaults | Replaced with CHANGEME placeholders | 18-01 |
| SEC-02 | Security | No max_length on address input fields | Added Field(max_length=500) to all schemas | 18-01 |
| SEC-03 | Security | No lat/lng range validation on SetOfficialRequest | Added Field(ge/le) bounds | 18-01 |
| SEC-04 | Security | provider_name reflected in error messages | Added allowlist + sanitized error | 18-01 |
| STAB-01 | Stability | POST /geocode has no exception catch | Global exception handler in main.py | 18-02 |
| STAB-02 | Stability | POST /validate catches only ProviderError | Global exception handler in main.py | 18-02 |
| STAB-04 | Stability | Legacy provider loop has no per-provider catch | Added try/except per provider in loop | 18-02 |
| PERF-01 | Performance | Connection pool uses SQLAlchemy defaults | Explicit pool_size/max_overflow/pool_pre_ping | 18-03 |
| PERF-06 | Performance | Tiger weight_map key "tiger" mismatches "postgis_tiger" | Fixed key + added national_address_database | 18-03 |

## Security Non-Blockers

### SEC-05: CLI SQL constants are compile-time only (P3)

**File:** `src/civpulse_geo/cli/__init__.py` — NAD_COPY_SQL, NAD_UPSERT_SQL
**Finding:** Raw SQL string constants for NAD bulk COPY/upsert. All values are module-level constants — no user input enters any SQL string. Verified: no CLI command accepts user-supplied SQL-interpolated values.
**Priority:** P3 (nice-to-have — could convert to parameterized queries for defense-in-depth, but no current risk)
**Action:** No action needed. Document for awareness.

## Stability Non-Blockers

### STAB-03: SpellCorrector graceful degradation (P3)

**File:** `src/civpulse_geo/main.py` lines 86-129
**Finding:** Lifespan wraps spell corrector init in try/except, falls back to `app.state.spell_corrector = None`. Cascade and legacy paths check for None and skip spell correction. This is correct graceful degradation — no 500 risk.
**Priority:** P3 (no action needed — pattern is correct)
**Action:** No action needed.

### STAB-05: Re-query after upsert pattern (P2)

**File:** `src/civpulse_geo/services/cascade.py` ~546, `services/geocoding.py` ~304
**Finding:** After each remote provider upsert (`.returning(GeocodingResultORM.id)`), code re-queries the same row by ID to get the full ORM object. Adds 1 extra SELECT per remote provider per geocode miss. With 1 remote provider (Census), this is 1 extra roundtrip.
**Priority:** P2 (fix when convenient — can be eliminated by using `.returning(*)` or constructing ORM from RETURNING data)
**Action:** Consider refactoring to use `.returning(GeocodingResultORM)` to avoid the extra query. Low urgency — bounded overhead.

### STAB-06: test_spell_startup.py correctness (P3)

**File:** `tests/test_spell_startup.py`
**Finding:** Per D-05, reviewed for correctness. Tests correctly assert the three Phase 17 decision paths: (1) empty dict + data triggers rebuild, (2) empty dict + no data skips with warning, (3) populated dict skips rebuild. Mock setup correctly simulates each condition. No false passes or incorrect assertions found.
**Priority:** P3 (no action needed — tests are correct)
**Action:** No action needed.

### STAB-07: Legacy path (`cascade_enabled=False`) deployment status (P2)

**File:** `src/civpulse_geo/services/geocoding.py` — `_legacy_geocode()` method
**Finding:** Default is `cascade_enabled=True`. Legacy path exists as a feature flag fallback. Per-provider exception handling was added in Plan 18-02, so the path now degrades gracefully. However, the legacy path has no consensus scoring, no auto-set official, and no spell correction — it is functionally incomplete compared to the cascade path.
**Priority:** P2 (determine in a future phase whether to remove the legacy path entirely or document it as intentionally limited)
**Action:** Decision needed: keep as emergency fallback (document limitations) or deprecate and remove.

## Performance Non-Blockers

### PERF-02: No N+1 query patterns (CONFIRMED CLEAN)

**Finding:** All provider queries are parameterized single-row lookups or `SELECT ... LIMIT 1`. The `selectinload(Address.geocoding_results)` in cascade.py and geocoding.py is correct eager-loading usage. No N+1 detected.
**Action:** No action needed. Confirmed clean.

### PERF-03: Re-query after upsert adds roundtrip per remote provider (P2)

**File:** `src/civpulse_geo/services/cascade.py` ~546, `services/geocoding.py` ~304
**Finding:** Same as STAB-05. After upsert `.returning(id)`, a second SELECT loads the full ORM row. 1 extra query per remote provider per cache miss. Bounded by provider count (currently 1 remote: Census).
**Priority:** P2 (performance optimization — use `.returning(*)` to avoid second query)
**Action:** Refactor upsert to return full row in one statement. Not urgent — latency impact is ~1ms per extra query.

### PERF-04: OA fuzzy match uses ORDER BY ABS(CAST) with regex filter (P2)

**File:** `src/civpulse_geo/providers/openaddresses.py` lines 174-198
**Finding:** `_find_oa_fuzzy_match` queries with `street_number.op("~")(r"^\d+$")` and `ORDER BY ABS(CAST(street_number, Integer) - target_num)`. Requires sequential scan on matching `street_name + postcode` rows with numeric street numbers. GIN trigram index from Phase 12 exists on street_name but the regex+CAST ordering may limit index benefit.
**Priority:** P2 (optimize if OA fuzzy match latency shows up in Phase 23 load testing)
**Action:** Consider adding a functional index on `CAST(street_number AS INTEGER)` or using a numeric column. Defer to Phase 23 analysis.

### PERF-05: Legacy path re-queries OfficialGeocoding separately (P3)

**File:** `src/civpulse_geo/services/geocoding.py` `_get_official()` method
**Finding:** After committing results, `_legacy_geocode()` calls `_get_official()` which performs two SELECTs: one for `OfficialGeocoding`, one for `GeocodingResult` by ID. Could be a single JOIN query. Correct but slightly less efficient.
**Priority:** P3 (nice-to-have optimization, legacy path only)
**Action:** If legacy path is kept long-term, refactor to a single JOIN. Otherwise, this goes away when legacy path is removed.

## Priority Summary

| Priority | Count | Description |
|----------|-------|-------------|
| P1 | 0 | Fix before prod — none remaining |
| P2 | 4 | Fix when convenient (STAB-05, STAB-07, PERF-03, PERF-04) |
| P3 | 4 | Nice-to-have (SEC-05, STAB-03, STAB-06, PERF-05) |

---
*Report generated: 2026-03-29*
*Phase: 18-code-review*
