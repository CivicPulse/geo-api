# Phase 12: Correctness Fixes and DB Prerequisites - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 12-correctness-fixes-and-db-prerequisites
**Areas discussed:** Tiger county filtering strategy, ZIP prefix fallback scope, Street suffix matching approach, Confidence semantics

---

## Tiger County Filtering Strategy

### Q1: How should Tiger results be filtered to the correct county?

| Option | Description | Selected |
|--------|-------------|----------|
| Spatial post-filter | Run geocode() as-is, then check if result falls within expected county boundary using ST_Contains() against county polygon table | ✓ |
| restrict_region norm_addy param | Pass a norm_addy with state/city hints to geocode(). Lighter weight but less precise | |
| Both (layered) | Use restrict_region for initial narrowing, then spatial post-filter as validation | |

**User's choice:** Spatial post-filter
**Notes:** None

### Q2: Where should county boundary data come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Tiger tabblock/county shapefiles | Census TIGER/Line county boundary shapefiles — new import needed | |
| Existing PostGIS Tiger tables | Query tiger.county or tiger.place directly — no new data import | ✓ |
| You decide | Let Claude pick based on what's available | |

**User's choice:** Existing PostGIS Tiger tables
**Notes:** None

### Q3: How should the county context be passed to the Tiger provider?

| Option | Description | Selected |
|--------|-------------|----------|
| Derive from input address | Parse city/state, resolve to county FIPS via tiger.county lookup | ✓ (default) |
| Explicit county parameter | Add optional county_fips parameter to geocode endpoint | ✓ (optional) |
| You decide | Let Claude pick the approach | |

**User's choice:** Both — derive from input as default, add optional county_fips parameter
**Notes:** User said "default to 1. add optional 2. that could be very useful for one usecase"

### Q4: When Tiger result falls outside expected county, what happens?

| Option | Description | Selected |
|--------|-------------|----------|
| Return NO_MATCH | Discard result entirely — wrong-county results never enter pipeline | ✓ |
| Return with low confidence | Return result with degraded confidence (e.g., 0.2) | |
| Return with a flag | Return at normal confidence with county_mismatch flag | |

**User's choice:** Return NO_MATCH
**Notes:** None

---

## ZIP Prefix Fallback Scope

### Q1: Which providers should get zip prefix fallback?

| Option | Description | Selected |
|--------|-------------|----------|
| OA + Macon-Bibb only (per requirements) | Strictly follow FIX-02 as written | |
| All local providers | Apply to OA, Macon-Bibb, AND NAD — consistent behavior | ✓ |
| You decide | Let Claude apply where it makes sense | |

**User's choice:** All local providers
**Notes:** None

### Q2: How aggressive should the prefix fallback be?

| Option | Description | Selected |
|--------|-------------|----------|
| 4-digit prefix only | LIKE '3120%' — one digit short, narrow match | |
| Progressive: try 4, then 3 | First try 4-digit, then fall back to 3-digit | ✓ |
| Match input length minus 1 | Adapt to however truncated the input is | |

**User's choice:** Progressive: try 4, then 3
**Notes:** None

### Q3: When prefix matching returns multiple candidates, how to pick?

| Option | Description | Selected |
|--------|-------------|----------|
| First match (simplest) | Return first row found — arbitrary without ORDER BY | |
| Closest zip numerically | Order by numeric distance from input zip prefix | ✓ |
| You decide | Let Claude pick the tie-breaking strategy | |

**User's choice:** Closest zip numerically
**Notes:** None

---

## Street Suffix Matching Approach

### Q1: How should the street suffix be incorporated into matching?

| Option | Description | Selected |
|--------|-------------|----------|
| Query both columns separately | Match street_name AND street_suffix as separate WHERE conditions | ✓ |
| Concatenate for comparison | Build full_street = name + suffix, compare against full parsed input | |
| You decide | Let Claude pick based on query patterns and index structure | |

**User's choice:** Query both columns separately
**Notes:** None

### Q2: Should _parse_input_address() also extract post-directionals?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, extract directionals too | Also extract post-directionals while changing parser signature | ✓ |
| No, suffix only | Stick strictly to FIX-03 scope | |
| You decide | Let Claude assess whether directional mismatches are a real problem | |

**User's choice:** Yes, extract directionals too
**Notes:** None

---

## Confidence Semantics

### Q1: What confidence value for 'structurally parsed but not address-verified'?

| Option | Description | Selected |
|--------|-------------|----------|
| 0.5 (per requirements) | Exactly what REQUIREMENTS.md specifies | |
| 0.3 (more conservative) | Lower value for more separation from real geocode results | ✓ |
| You decide | Let Claude pick for Phase 14 consensus scoring compatibility | |

**User's choice:** 0.3
**Notes:** None

### Q2: Should scourgify and Tiger validation get the same confidence?

| Option | Description | Selected |
|--------|-------------|----------|
| Same value (0.3) for both | Both are structural parse only — consistent semantics | |
| Tiger slightly higher (e.g., 0.4) | Tiger cross-references Census street data, more signal | ✓ |
| You decide | Let Claude decide based on what each parser validates | |

**User's choice:** Tiger at 0.4, scourgify at 0.3
**Notes:** None

---

## Claude's Discretion

- GIN trigram index migration strategy (new migration vs. modifying existing)
- pg_trgm extension enablement approach
- Internal refactoring of `_parse_input_address()` tuple expansion

## Deferred Ideas

None — discussion stayed within phase scope
