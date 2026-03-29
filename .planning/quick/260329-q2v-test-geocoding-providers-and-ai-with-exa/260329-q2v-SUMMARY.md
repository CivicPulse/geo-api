---
phase: quick
plan: 260329-q2v
subsystem: geocoding-cascade
tags: [testing, cascade, geocoding, bug-fix, fuzzy-match, trace]
dependency_graph:
  requires: [260329-2zn]
  provides: [cascade-validation-report]
  affects: [cascade.py, fuzzy.py, geocoding.py]
tech_stack:
  added: []
  patterns: [cascade-trace, provider-consensus, fuzzy-match]
key_files:
  created:
    - .planning/quick/260329-q2v-test-geocoding-providers-and-ai-with-exa/GEOCODE-COMPARISON-REPORT.md
  modified:
    - src/civpulse_geo/services/cascade.py
    - src/civpulse_geo/services/fuzzy.py
    - src/civpulse_geo/services/geocoding.py
decisions:
  - "Clamp state/zip_code before Address INSERT when parser returns oversized values — prevents crash without altering cascade behavior"
  - "Fuzzy ST_Y/ST_X casts were missing .cast(Geometry) — same pattern as all other providers, fix is consistent"
  - "LLM stage (Ollama) not active in this environment — address 4 unresolvable without it, documented in report"
metrics:
  duration: "~30min (includes 2 bug fix iterations + Docker rebuild cycles)"
  completed: "2026-03-29"
  tasks: 1
  files: 4
---

# Quick Task 260329-q2v: Test Geocoding Providers and AI with Cascade — Summary

**One-liner:** End-to-end cascade trace for 4 progressively degraded addresses with 2 latent bug fixes (VARCHAR(2) overflow + fuzzy ST_Y geography cast) and full provider comparison report.

## What Was Done

Geocoded all 4 test addresses via `POST /geocode?trace=true` against the running local dev environment at http://localhost:8042. Captured full cascade trace data showing which stages activated (normalize, exact_match, fuzzy_match, LLM, consensus, auto_set_official) for each address and produced GEOCODE-COMPARISON-REPORT.md.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] StringDataRightTruncationError crashes on address 4**
- **Found during:** Task 1 — first attempt to geocode "669 Arlngton lace, Mac0n Georgia"
- **Issue:** The address parser returned `state="MAC0N GEORGIA"` (city misidentified, state exceeded VARCHAR(2)) causing a PostgreSQL `StringDataRightTruncationError` on the Address INSERT in Stage 1, crashing the request with HTTP 500 before LLM correction could run.
- **Fix:** Guard `state` and `zip_code` components before Address INSERT in both `cascade.py` and `geocoding.py`: store `None` when `state` exceeds 2 chars or `zip_code` exceeds 5 chars.
- **Files modified:** `src/civpulse_geo/services/cascade.py`, `src/civpulse_geo/services/geocoding.py`
- **Commit:** 06dfe1e

**2. [Rule 1 - Bug] ST_Y(geography) UndefinedFunctionError in fuzzy matcher**
- **Found during:** Task 1 — after Bug 1 was fixed, address 4 now reached the fuzzy stage and triggered `asyncpg.exceptions.UndefinedFunctionError: function st_y(geography) does not exist`
- **Issue:** `services/fuzzy.py` used `func.ST_Y(model.location)` directly on `Geography` columns. PostGIS `ST_Y` requires `geometry`, not `geography`. All other providers in the codebase use `.cast(Geometry)`.
- **Fix:** Added `from geoalchemy2.types import Geometry` to fuzzy.py and applied `.cast(Geometry)` to all 6 `ST_Y`/`ST_X` calls across the three sub-queries.
- **Files modified:** `src/civpulse_geo/services/fuzzy.py`
- **Commit:** 06dfe1e

## Key Findings

1. **Addresses 1-3 resolved correctly** via exact_match_consensus (addresses 1 and 3) or single_provider (address 2). Tiger wrong-county bug produced outlier results for addresses 1 and 3, correctly excluded by the consensus engine.

2. **Address 4 unresolvable** without the LLM sidecar. The zero-for-o substitution ("Mac0n") and street misspelling ("Arlngton") cannot be corrected by the deterministic stages. The spell_dictionary is also empty (not rebuilt after data load), meaning even a correctly populated dictionary would not help with the city-level zero substitution.

3. **LLM stage not active** — `CASCADE_LLM_ENABLED=false` by default, Ollama service requires `--profile llm`. This is expected behavior; the LLM stage is documented as optional and data-driven.

4. **Tiger wrong-county bug** confirmed for 2 of 4 addresses (1 and 3) — outliers at 112km and 185km from the correct location. FIX-01 (`restrict_region`) remains a documented prerequisite for including Tiger in auto-set logic.

5. **Spell dictionary empty** in dev environment — `spell_corrected=true` in traces indicates the corrector was available but no corrections were applied. Run `rebuild-spell-dictionary` CLI command to populate.

## Self-Check: PASSED

- FOUND: GEOCODE-COMPARISON-REPORT.md
- FOUND: cascade.py (modified)
- FOUND: fuzzy.py (modified)
- FOUND: geocoding.py (modified)
- FOUND: commit 06dfe1e
