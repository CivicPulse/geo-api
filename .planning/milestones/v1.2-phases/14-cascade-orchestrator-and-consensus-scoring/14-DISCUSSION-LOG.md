# Phase 14: Cascade Orchestrator and Consensus Scoring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 14-cascade-orchestrator-and-consensus-scoring
**Areas discussed:** Cascade integration point, Consensus clustering, Early-exit strategy, Dry-run and audit

---

## Cascade Integration Point

### How should CascadeOrchestrator integrate with GeocodingService?

| Option | Description | Selected |
|--------|-------------|----------|
| Replace geocode() internals | CascadeOrchestrator becomes new implementation inside GeocodingService.geocode(). CASCADE_ENABLED=false runs _legacy_geocode(). Single entry point. | ✓ |
| Wrapper service | New CascadeOrchestrator wraps GeocodingService. API routes switch to calling CascadeOrchestrator. | |
| Parallel service | Separate service, API route decides which to call. More duplication. | |

**User's choice:** Replace geocode() internals
**Notes:** Keeps a single entry point for callers — API routes don't change at all.

### Should CascadeOrchestrator live in same file or new file?

| Option | Description | Selected |
|--------|-------------|----------|
| New services/cascade.py | Own file, imported by GeocodingService. Follows existing services/ pattern. | ✓ |
| Inline in geocoding.py | Private class inside geocoding.py. Fewer files but geocoding.py already 555 lines. | |

**User's choice:** New services/cascade.py
**Notes:** None

### Test strategy for CASCADE_ENABLED toggle?

| Option | Description | Selected |
|--------|-------------|----------|
| Legacy path inherits existing tests | Existing 379 tests pass unchanged when CASCADE_ENABLED=false. New tests for cascade path. | |
| Parameterized tests for both paths | Key tests run with CASCADE_ENABLED=true and false via pytest parameterize. | ✓ |

**User's choice:** Parameterized tests for both paths
**Notes:** More thorough — both paths tested with same test cases.

### How should cascade handle local vs remote providers?

| Option | Description | Selected |
|--------|-------------|----------|
| Single exact-match stage | All providers (local + remote) called in parallel in one stage. Results all feed consensus. | ✓ |
| Separate local then remote stages | Stage 3a local, Stage 3b remote. If locals agree, skip remote. Could save Census API calls. | |

**User's choice:** Single exact-match stage
**Notes:** None

---

## Consensus Clustering

### How should consensus scorer compute winning cluster centroid?

| Option | Description | Selected |
|--------|-------------|----------|
| Weighted centroid | Position weighted by provider trust weight. Census pulls harder than Tiger. | ✓ |
| Simple average centroid | All cluster members contribute equally. Trust weights only determine winning cluster. | |
| Best-provider point | Use exact lat/lng from highest-trust provider. No synthetic coordinates. | |

**User's choice:** Weighted centroid
**Notes:** Matches the spirit of CONS-02 trust weights.

### How should fuzzy results participate in consensus?

| Option | Description | Selected |
|--------|-------------|----------|
| Scaled provider weight | effective_weight = provider_weight * (fuzzy_confidence / 0.80). Natural discount. | ✓ |
| Fixed fuzzy weight | Single configurable weight for all fuzzy results regardless of source. | |
| Exclude fuzzy from consensus | Fuzzy only used if no consensus from exact providers. | |

**User's choice:** Scaled provider weight
**Notes:** None

### What clustering algorithm?

| Option | Description | Selected |
|--------|-------------|----------|
| Greedy single-pass | Sort by weight desc, seed clusters, join nearest within 100m. | ✓ |
| All-pairs distance matrix | Compute pairwise distances, group where all pairs within 100m. | |
| Claude decides | Pick based on performance testing. | |

**User's choice:** Greedy single-pass
**Notes:** For 3-5 results this is equivalent to more complex algorithms.

### Single-result handling?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-set if confidence >= 0.80 | High-confidence single results become official. Low-confidence returned but not auto-set. | ✓ |
| Always auto-set | Any single result becomes official. Better than nothing. | |
| Never auto-set singles | Require 2+ providers for auto-set. | |

**User's choice:** Auto-set if confidence >= 0.80
**Notes:** Prevents low-confidence fuzzy/Tiger results from becoming official without consensus.

---

## Early-Exit Strategy

### Should consensus still run on early-exit?

| Option | Description | Selected |
|--------|-------------|----------|
| Always score consensus | Early-exit skips fuzzy/LLM only. Consensus always runs for consistency. | ✓ |
| Skip consensus too | High-confidence result goes directly to official. Fastest path. | |
| Configurable threshold | Threshold configurable via env var. Consensus always runs. | |

**User's choice:** Always score consensus
**Notes:** Ensures consistent outlier flagging and set_by_stage audit trail.

### Early-exit trigger: single provider or 2+?

| Option | Description | Selected |
|--------|-------------|----------|
| Single provider >= 0.80 | Any one provider at 0.80+ triggers early exit. Matches CASC-03 wording. | ✓ |
| Two+ providers >= 0.80 | More conservative, ensures material for consensus. | |
| Claude decides | Based on performance testing. | |

**User's choice:** Single provider >= 0.80
**Notes:** Matches CASC-03 literal wording.

### Per-stage timeouts or total elapsed budget?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-stage timeouts | Configurable per-stage timeouts via env vars. Graceful degradation. | ✓ |
| Total elapsed budget only | Track total cascade time, skip remaining stages if approaching 3s. | |
| Claude decides | Based on observed provider latencies. | |

**User's choice:** Per-stage timeouts
**Notes:** Prevents Census API latency from starving later stages.

---

## Dry-Run and Audit

### Should dry-run return cascade trace?

| Option | Description | Selected |
|--------|-------------|----------|
| Full cascade trace | cascade_trace array showing each stage, timing, results. | ✓ |
| Just the would-be result | Same response shape with dry_run flag. No trace. | |
| Trace as opt-in header | Trace via X-Cascade-Trace header. Dry-run shows result only by default. | |

**User's choice:** Full cascade trace
**Notes:** Invaluable for debugging and understanding cascade decisions.

### Should trace be available on non-dry-run requests?

| Option | Description | Selected |
|--------|-------------|----------|
| Both dry-run and ?trace=true | cascade_trace returned when either flag is set. | ✓ |
| Dry-run only | Trace exclusively part of dry-run responses. | |
| Always include trace | Every response includes trace. | |

**User's choice:** Both dry-run and ?trace=true
**Notes:** Useful for debugging production issues without switching to dry-run mode.

### Where should set_by_stage audit metadata live?

| Option | Description | Selected |
|--------|-------------|----------|
| New column on OfficialGeocoding | set_by_stage TEXT column via Alembic migration. | ✓ |
| JSON field in raw_response | In GeocodingResult's raw_response JSON. No migration. | |
| Separate audit_log table | New table tracking all events. Most complete but heavier. | |

**User's choice:** New column on OfficialGeocoding
**Notes:** Clean — audit data lives with the thing it describes.

### How should outlier flag surface in API response?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-result is_outlier boolean | is_outlier field on GeocodeProviderResult. Simple, filterable. | ✓ |
| Outliers in separate array | results vs outliers arrays. Cleaner separation. | |
| Confidence override | Override outlier confidence to 0.10. Loses original confidence. | |

**User's choice:** Per-result is_outlier boolean
**Notes:** None

---

## Claude's Discretion

- Alembic migration strategy for set_by_stage column
- CascadeOrchestrator internal method decomposition
- cascade_trace schema fields per stage type
- Haversine vs ST_Distance for clustering thresholds
- CASCADE_ENABLED integration with Pydantic BaseSettings
- asyncio.gather vs sequential for parallel provider calls

## Deferred Ideas

None — discussion stayed within phase scope
