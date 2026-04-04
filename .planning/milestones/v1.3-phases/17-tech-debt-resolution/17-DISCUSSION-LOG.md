# Phase 17: Tech Debt Resolution - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 17-tech-debt-resolution
**Areas discussed:** Tiger timeout strategy, Cache hit detection, Spell dictionary auto-population, CLI test fixtures

---

## Tiger Timeout Strategy

### Q1: How should the Tiger timeout issue be addressed?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-provider timeouts (Recommended) | Add provider-specific timeout config so Tiger gets its own budget without affecting other providers | ✓ |
| Increase stage timeout | Raise exact_match_timeout_ms from 2000 to 3000-5000ms for all providers | |
| Optimize Tiger queries | Focus on making Tiger faster rather than changing timeouts | ✓ |
| Tiger-specific retry | Keep current timeout but add a single retry with backoff | |

**User's choice:** Both per-provider timeouts AND Tiger query optimization
**Notes:** User wants both a safety net (per-provider timeouts) and root-cause fix (query optimization)

### Q2: Should Tiger's timeout be higher than 2000ms or match after optimization?

| Option | Description | Selected |
|--------|-------------|----------|
| 3000ms for Tiger | Give Tiger 50% more headroom than other providers | ✓ |
| Keep 2000ms target | Optimize Tiger to fit within same budget | |
| You decide | Claude picks based on optimization results | |

**User's choice:** 3000ms for Tiger

### Q3: Should per-provider timeout config be env-var driven or hardcoded?

| Option | Description | Selected |
|--------|-------------|----------|
| Env-var configurable (Recommended) | Add tiger_timeout_ms to Settings class alongside existing timeouts | ✓ |
| Hardcoded defaults | Set as class-level constant in Tiger provider | |

**User's choice:** Env-var configurable

### Q4: Tiger query optimization focus?

| Option | Description | Selected |
|--------|-------------|----------|
| You decide | Claude investigates and picks most effective optimizations | |
| Both restrict_region + LIMIT | Apply restrict_region AND LIMIT clauses | ✓ |
| restrict_region only | Focus on narrowing search area | |

**User's choice:** Both restrict_region + LIMIT

### Q5: Should per-provider timeout apply to ALL providers or just Tiger?

| Option | Description | Selected |
|--------|-------------|----------|
| All providers (Recommended) | Each provider gets own timeout_ms with sensible defaults | ✓ |
| Tiger only | Only Tiger gets custom timeout | |

**User's choice:** All providers

### Q6: Provider timeout behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-open with warning (Recommended) | Log warning, return empty results, cascade continues | ✓ |
| Raise catchable error | Throw ProviderTimeoutError for cascade to catch | |
| You decide | Claude picks based on existing error patterns | |

**User's choice:** Fail-open with warning

---

## Cache Hit Detection

### Q1: How should cache detection work in cascade path?

| Option | Description | Selected |
|--------|-------------|----------|
| Early-exit with cache check (Recommended) | Add cache check before Stage 2, return with cache_hit=True | ✓ |
| Track cache vs fresh per-result | Run pipeline but track per-result cache status | |
| You decide | Claude implements most consistent approach | |

**User's choice:** Early-exit with cache check

### Q2: On cache hit, re-run consensus scoring or return immediately?

| Option | Description | Selected |
|--------|-------------|----------|
| Return immediately (Recommended) | Mirror legacy path: return cached + fresh local + existing official | |
| Re-run consensus on cached | Return cached but re-run consensus scoring | ✓ |
| You decide | Claude picks based on whether consensus results are persisted | |

**User's choice:** Re-run consensus on cached results
**Notes:** Ensures provider weight changes take effect retroactively on cached results

---

## Spell Dictionary Auto-Population

### Q1: How should spell dictionary auto-populate?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-rebuild at startup (Recommended) | In lifespan, auto-rebuild if empty but staging has data | |
| K8s init container only | Phase 20 adds init container, no app code change | ✓ (initially) |
| Rebuild on first request | Lazy-load on first geocode request | |
| CLI + startup warning | Keep current behavior with louder warning | |

**User's choice:** Initially chose K8s init container only

### Q2: DEBT-03 requires startup auto-population. How handle split across phases?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 17: auto-rebuild in app too | Add startup rebuild AND plan init container in Phase 20 | ✓ |
| Split: Phase 17 marks partial | Document approach, mark DEBT-03 partially addressed | |
| Phase 17 only: auto-rebuild in app | App handles it, skip init container | |

**User's choice:** Phase 17: auto-rebuild in app too (belt and suspenders)

### Q3: Rebuild conditionally or unconditionally at startup?

| Option | Description | Selected |
|--------|-------------|----------|
| Only when empty (Recommended) | Check if spell_dictionary has rows; skip if populated | ✓ |
| Always rebuild | TRUNCATE + re-insert every startup | |
| You decide | Claude picks based on execution time | |

**User's choice:** Only when empty

---

## CLI Test Fixtures

### Data Resolution
Sample fixture files extracted from dev VM (kwhatcher@dev:~/projects/civpulse/geo-api/data/):
- `SAMPLE_Address_Points.geojson` — 5 features from 67,730 total
- `SAMPLE_MBIT2017.DBO.AddressPoint.kml` — 5 features from 67,730 total

This resolved 10 of 11 test failures immediately.

### Q1: Parser accuracy bug fix approach?

| Option | Description | Selected |
|--------|-------------|----------|
| Fix the parser (Recommended) | Change accuracy handling: empty string → None, missing → "parcel" | ✓ |
| Fix the test expectation | Change test to expect "parcel" for empty accuracy | |
| You decide | Claude picks based on OA pipeline semantics | |

**User's choice:** Fix the parser

---

## Claude's Discretion

- Tiger query optimization specifics (restrict_region parameters, LIMIT values)
- Per-provider timeout config pattern (flat vs nested)

## Deferred Ideas

None — discussion stayed within phase scope
