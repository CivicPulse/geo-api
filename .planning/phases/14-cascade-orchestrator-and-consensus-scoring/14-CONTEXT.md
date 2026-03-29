# Phase 14: Cascade Orchestrator and Consensus Scoring - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement a staged CascadeOrchestrator that replaces the flat provider loop in GeocodingService.geocode() with: normalize → spell-correct → exact match (all providers) → fuzzy/phonetic → consensus score → auto-set official. The cascade is transparent to callers (same GeocodeResponse shape), feature-flagged via CASCADE_ENABLED, and includes dry-run mode and full cascade tracing. Cross-provider consensus scoring clusters results spatially, weights by provider trust, flags outliers, and auto-sets OfficialGeocoding with audit metadata.

</domain>

<decisions>
## Implementation Decisions

### Cascade Integration (CASC-01, CASC-02)
- **D-01:** CascadeOrchestrator lives in a new `services/cascade.py` file, imported by GeocodingService
- **D-02:** GeocodingService.geocode() delegates to CascadeOrchestrator.run() when `CASCADE_ENABLED=true`; when false, calls `_legacy_geocode()` which preserves the v1.1 flat pipeline
- **D-03:** The "replace internals" pattern — current geocode() body moves to _legacy_geocode(), keeping a single entry point for API routes (no route changes needed)
- **D-04:** Existing tests run parameterized against both CASCADE_ENABLED=true and false via pytest parameterize — both paths tested

### Exact Match Stage (CASC-01)
- **D-05:** Single exact-match stage calls ALL providers (local + remote) in parallel. No separate local-then-remote staging. Remote cache check still applies for remote providers. All results feed into consensus scoring regardless of source

### Consensus Clustering (CONS-01, CONS-02)
- **D-06:** Greedy single-pass clustering: sort results by trust weight descending, first result seeds cluster 1, each subsequent result joins nearest cluster if within 100m, otherwise starts new cluster
- **D-07:** Weighted centroid: `centroid_lat = sum(w*lat) / sum(w)` where w = provider trust weight. More trusted providers pull the centroid position
- **D-08:** Provider trust weights per CONS-02: Census=0.90, OA=0.80, Macon-Bibb=0.80, Tiger=0.40 unrestricted / 0.75 with restrict_region, NAD=0.80
- **D-09:** Fuzzy results use scaled provider weight: `effective_weight = provider_weight * (fuzzy_confidence / 0.80)`. Naturally discounts fuzzy results without separate config
- **D-10:** Winning cluster = highest total weight. Winning centroid auto-set as OfficialGeocoding

### Single-Result Handling
- **D-11:** When only one provider returns a result: auto-set as official if confidence >= 0.80; below 0.80, return the result but do not write OfficialGeocoding (admin can override manually)

### Early-Exit (CASC-03)
- **D-12:** Early-exit triggers when ANY single exact-match provider returns confidence >= 0.80 — skips fuzzy and LLM stages only
- **D-13:** Consensus scoring ALWAYS runs, even on early-exit — just with fewer results. Ensures consistent outlier flagging and set_by_stage audit trail
- **D-14:** Stage sequence: (1) normalize + spell-correct → (2) exact match → [early-exit skips 3-4] → (3) fuzzy match → (4) LLM correction → (5) consensus score → (6) auto-set official

### Latency Budgets (CASC-04)
- **D-15:** Per-stage configurable timeouts via environment variables: EXACT_MATCH_TIMEOUT_MS=2000, FUZZY_MATCH_TIMEOUT_MS=500, CONSENSUS_TIMEOUT_MS=200, CASCADE_TOTAL_TIMEOUT_MS=3000
- **D-16:** If a stage times out, cascade continues with whatever results are available from that stage (graceful degradation)

### Dry-Run and Trace (CONS-06)
- **D-17:** `?dry_run=true` runs the full cascade but does not write OfficialGeocoding; returns `would_set_official` and full `cascade_trace`
- **D-18:** `?trace=true` returns `cascade_trace` on normal (non-dry-run) requests too — useful for debugging production issues without switching to dry-run
- **D-19:** cascade_trace is an array of stage objects: `{stage, input, output, results_count, early_exit, ms, ...}` — stage-specific fields vary

### Outlier Flagging (CONS-03)
- **D-20:** Per-result `is_outlier: bool` field added to GeocodeProviderResult in the API response. Results > 1km from winning cluster centroid are flagged `is_outlier: true`

### Audit Metadata (CONS-05)
- **D-21:** New `set_by_stage` TEXT column on the `official_geocoding` table via Alembic migration. Values: "exact_match_consensus", "fuzzy_consensus", "single_provider", etc.
- **D-22:** Cascade path uses `ON CONFLICT DO UPDATE` for OfficialGeocoding (replacing v1.1's DO NOTHING) so consensus winner can update a previously auto-set record. Admin overrides are NEVER overwritten (check for admin_override provider before updating)

### Claude's Discretion
- Alembic migration strategy for `set_by_stage` column (new migration vs extending existing)
- Internal CascadeOrchestrator method decomposition (how stages are structured as methods/classes)
- Exact cascade_trace schema fields per stage type
- Haversine vs PostGIS ST_Distance for the 100m/1km clustering thresholds (in-Python vs SQL)
- How CASCADE_ENABLED config integrates with existing `settings` (Pydantic BaseSettings)
- asyncio.gather vs sequential for parallel provider calls within exact-match stage

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Services (modification targets)
- `src/civpulse_geo/services/geocoding.py` — Current GeocodingService with geocode(), _apply_spell_correction(), set_official(), _get_official(). Cascade replaces geocode() internals (D-02/D-03)
- `src/civpulse_geo/services/fuzzy.py` — FuzzyMatcher service with find_fuzzy_match(), FuzzyMatchResult. Called as cascade stage 3 (D-14)
- `src/civpulse_geo/services/validation.py` — Existing service pattern to follow

### API Layer
- `src/civpulse_geo/api/geocoding.py` — FastAPI routes for /geocode endpoints. Needs dry_run and trace query params, is_outlier in response
- `src/civpulse_geo/schemas/geocoding.py` — Pydantic models: GeocodeResponse, GeocodeProviderResult. New fields: is_outlier, cascade_trace, dry_run, would_set_official

### Provider Infrastructure
- `src/civpulse_geo/providers/base.py` — GeocodingProvider ABC with is_local property
- `src/civpulse_geo/providers/registry.py` — Provider registration and lookup
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult/ValidationResult dataclasses with confidence field

### Database Models
- `src/civpulse_geo/models/geocoding.py` — OfficialGeocoding model (needs set_by_stage column), GeocodingResult ORM, AdminOverride
- `src/civpulse_geo/models/address.py` — Address model with geocoding_results relationship

### Spell Correction
- `src/civpulse_geo/spell/corrector.py` — SpellCorrector class used in cascade stage 1

### Configuration
- `src/civpulse_geo/config.py` — Pydantic BaseSettings for environment variables. Needs CASCADE_ENABLED, timeout budgets, provider weights

### Requirements
- `.planning/REQUIREMENTS.md` — CASC-01 through CASC-04, CONS-01 through CONS-06

### Prior Phase Context
- `.planning/phases/12-correctness-fixes-and-db-prerequisites/12-CONTEXT.md` — Confidence values: scourgify=0.3, Tiger=0.4 (D-09/D-10); Tiger restrict_region spatial filter
- `.planning/phases/13-spell-correction-and-fuzzy-phonetic-matching/13-CONTEXT.md` — FuzzyMatcher architecture (D-05/D-06), fuzzy confidence 0.50-0.75 (D-07), word_similarity threshold 0.65 (D-13)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GeocodingService` in `services/geocoding.py` — entire geocode() pipeline including spell correction, normalization, provider dispatch, cache check, and OfficialGeocoding auto-set. Body moves to _legacy_geocode()
- `FuzzyMatcher` in `services/fuzzy.py` — ready-made fuzzy stage with find_fuzzy_match() returning FuzzyMatchResult (single best match, confidence 0.50-0.75)
- `SpellCorrector` in `spell/corrector.py` — loaded at app startup into app.state.spell_corrector
- `canonical_key()` / `parse_address_components()` in `normalization.py` — normalization + hashing
- `_parse_input_address()` in `providers/openaddresses.py` — 5-tuple parser shared by local providers
- Provider ABC with `is_local` property — enables local/remote partitioning in the cascade

### Established Patterns
- Services are stateless classes instantiated per-request (`GeocodingService()`)
- Providers accessed via `request.app.state.providers` dict
- SpellCorrector via `request.app.state.spell_corrector`
- Alembic migrations for schema changes with `op.add_column()`, `op.execute()`
- PostgreSQL `pg_insert().on_conflict_do_update()` / `on_conflict_do_nothing()` for upserts
- Pydantic BaseSettings for env config in `config.py`

### Integration Points
- `GeocodingService.geocode()` — primary modification target; cascade delegates to CascadeOrchestrator.run()
- `api/geocoding.py` route handlers — need `dry_run` and `trace` query parameters passed through
- `schemas/geocoding.py` — GeocodeProviderResult needs `is_outlier`, GeocodeResponse needs cascade trace fields
- `models/geocoding.py` OfficialGeocoding — needs `set_by_stage` column + migration
- `config.py` — needs CASCADE_ENABLED, timeout, and weight environment variables

</code_context>

<specifics>
## Specific Ideas

- Confidence tiers are deliberately layered for consensus: scourgify=0.3 (Phase 12), Tiger=0.4, fuzzy=0.50-0.75 (Phase 13), exact local=0.80+, Census=0.95 — consensus scoring should leverage this gradient
- The cascade must preserve backward compatibility: same GeocodeResponse shape, same API routes, no caller changes needed. The only new fields are additive (is_outlier, cascade_trace)
- Admin overrides (admin_override provider) must NEVER be overwritten by cascade auto-set — check for admin_override before ON CONFLICT DO UPDATE
- Per-stage timeouts ensure Census API latency doesn't starve the fuzzy stage — graceful degradation is preferred over hard failure

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-cascade-orchestrator-and-consensus-scoring*
*Context gathered: 2026-03-29*
