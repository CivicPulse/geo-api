---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Cascading Address Resolution
status: verifying
stopped_at: Completed 15-02-PLAN.md
last_updated: "2026-03-29T16:59:41.228Z"
last_activity: 2026-03-29
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 10
  completed_plans: 10
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-29)

**Core value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching, local data sources, and giving admins authority over the official answer
**Current focus:** Phase 15 — llm-sidecar

## Current Position

Phase: 15 (llm-sidecar) — EXECUTING
Plan: 3 of 3
Status: Phase complete — ready for verification
Last activity: 2026-03-29

```
v1.2 Progress: [----------] 0/4 phases
```

## Performance Metrics

| Metric | v1.0 | v1.1 | v1.2 |
|--------|------|------|------|
| Requirements | 26/26 | 6/6 | 0/25 |
| Phases | 6 | 5 | 0/4 |
| Tests | 179 | 379 | - |
| Phase 12-correctness-fixes-and-db-prerequisites P01 | 470 | 2 tasks | 6 files |
| Phase 12-correctness-fixes-and-db-prerequisites P02 | 15 | 2 tasks | 5 files |
| Phase 13-spell-correction-and-fuzzy-phonetic-matching P01 | 7 | 3 tasks | 11 files |
| Phase 13-spell-correction-and-fuzzy-phonetic-matching P02 | 9 | 2 tasks | 3 files |
| Phase 14-cascade-orchestrator-and-consensus-scoring P02 | 6min | 1 tasks | 2 files |
| Phase 14-cascade-orchestrator-and-consensus-scoring P03 | 7 | 3 tasks | 4 files |
| Phase 15-llm-sidecar P01 | 12 | 1 tasks | 3 files |
| Phase 15-llm-sidecar P03 | 8 | 2 tasks | 5 files |
| Phase 15-llm-sidecar P02 | 6min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

- [Phase 12]: _parse_input_address 5-tuple: street_suffix and street_directional added at positions 4 and 5; suffix condition uses tuple unpacking in WHERE clause so it is omitted when None
- [Phase 12]: ZIP prefix ordering uses lexicographic .asc() on zip column rather than integer math; progressive fallback tries 4-digit prefix then 3-digit
- [Phase 12]: COUNTY_CONTAINS_SQL uses ST_Transform to convert WGS84 geocode result to NAD83 before ST_Contains check against tiger.county
- [Phase 12]: SCOURGIFY_CONFIDENCE=0.3 and TIGER_VALIDATION_CONFIDENCE=0.4 replace hardcoded 1.0 — parse-only providers mislead consensus scoring if confidence is too high (D-09, D-10)
- [Phase 13]: symspellpy Verbosity.TOP returns single top candidate per token; tokens < 4 chars bypass correction to avoid over-correcting short street names
- [Phase 13]: rebuild_dictionary uses TRUNCATE + unnest(string_to_array) for per-word tokenization; Tiger featnames included with bare except guard (SPELL-02)
- [Phase 13]: SpellCorrector uses sync engine at API startup for SymSpell.create_dictionary_entry (D-09); graceful fallback sets app.state.spell_corrector = None on error
- [Phase 13]: UNION ALL across OA/NAD/Macon-Bibb staging tables in single query (D-06) for FuzzyMatcher
- [Phase 13]: dmetaphone() SQL tiebreaker as second query when candidates within 0.05 gap (D-12)
- [Phase 13]: Calibration corpus uses mock session for CI-compatible D-15 regression testing
- [Phase 14-02]: official_loaded flag prevents double _get_official() call when admin override blocks auto-set
- [Phase 14-02]: best_candidate selected as cluster member closest to weighted centroid (not first/highest-weight)
- [Phase 14]: patch settings via civpulse_geo.services.geocoding.settings (not the module directly) for test isolation
- [Phase 14]: outlier_providers defaults to empty set() in legacy path result dict to avoid KeyError in API
- [Phase 15-llm-sidecar]: Direct httpx for Ollama client — reuses existing AsyncClient, no new dependency, full timeout control
- [Phase 15-llm-sidecar]: POST timeout 6.0s (above 5s asyncio.wait_for) lets wait_for handle cancellation cleanly
- [Phase 15-llm-sidecar]: _ZIP_FIRST_DIGIT_STATES hardcoded dict covers all 50 states plus territories — complete guardrail coverage, zero dependencies
- [Phase 15-llm-sidecar]: Docker Compose profiles (profiles: [llm]) for optional Ollama activation — avoids 2GB model download for devs not using LLM
- [Phase 15-llm-sidecar]: K8s initContainer pulls qwen2.5:3b before main container starts — model warm on first request
- [Phase 15-llm-sidecar]: No CPU limit in K8s or Docker (D-11) — LLM inference is CPU-bursty; limits cause starvation
- [Phase 15-llm-sidecar]: is_llm_corrected check precedes is_fuzzy in set_by_stage — LLM stage is more specific than fuzzy and takes priority in set_by_stage labeling

### Phase Ordering Notes

- Phase 12 is a hard prerequisite for all v1.2 phases: Tiger wrong-county bug and confidence semantics corruption must be fixed before any cascade auto-set logic is built
- Phase 13 (spell correction + fuzzy) depends on Phase 12 GIN indexes existing and normalization being consistent on both sides of the comparison
- Phase 14 (orchestrator + consensus) depends on Phase 13 components existing so the orchestrator has meaningful fuzzy results to score
- Phase 15 (LLM sidecar) is data-driven: execute only if Phase 14 telemetry shows > 1-2% of addresses remain unresolved after deterministic stages

### Pending Todos

None.

### Blockers/Concerns (Carry Forward)

- Google Maps excluded — ToS incompatible with caching model (moved to Out of Scope)
- VAL-06 delivery_point_verified is always False with scourgify — real DPV needs a paid USPS API adapter (v1.3 candidate)
- Tiger wrong-county bug is a hard gate: Tiger results must not contribute to auto-set logic until FIX-01 (restrict_region) is deployed and verified

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260324-lqg | fix Tiger extension check predicate | 2026-03-24 | 86ef71b | [260324-lqg-fix-tiger-extension-check-predicate](./quick/260324-lqg-fix-tiger-extension-check-predicate/) |
| 260324-m7o | add debugpy support to Docker dev setup | 2026-03-24 | a437ca3 | [260324-m7o-modify-the-entrypoint-to-optionally-star](./quick/260324-m7o-modify-the-entrypoint-to-optionally-star/) |
| 260324-n1e | write comprehensive README.md | 2026-03-24 | d07da6b | [260324-n1e-create-a-well-formatted-and-visually-ple](./quick/260324-n1e-create-a-well-formatted-and-visually-ple/) |
| 260324-n3c | create Postman collection for all 8 API endpoints | 2026-03-24 | e464ddb | [260324-n3c-create-a-postman-config-that-can-test-al](./quick/260324-n3c-create-a-postman-config-that-can-test-al/) |
| 260325-0pw | add OpenAddresses parcel boundary staging table and CLI command | 2026-03-25 | fcc0de9 | [260325-0pw-add-openaddresses-parcel-boundary-stagin](./quick/260325-0pw-add-openaddresses-parcel-boundary-stagin/) |
| 260325-0th | add 4th local geocoder using Macon-Bibb County GIS address points | 2026-03-25 | a99a45d | [260325-0th-add-4th-local-geocoder-using-macon-bibb-](./quick/260325-0th-add-4th-local-geocoder-using-macon-bibb-/) |
| 260329-2zn | complete local dev env setup with all 5 providers registered | 2026-03-29 | c7ac438 | [260329-2zn-start-a-local-dev-env-ensure-all-5-provi](./quick/260329-2zn-start-a-local-dev-env-ensure-all-5-provi/) |

## Session Continuity

Last activity: 2026-03-29 — v1.2 roadmap created
Stopped at: Completed 15-02-PLAN.md
Resume file: None
Next action: `/gsd:plan-phase 12`
