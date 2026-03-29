# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- ✅ **v1.1 Local Data Sources** — Phases 7-11 (shipped 2026-03-29)
- 🔄 **v1.2 Cascading Address Resolution** — Phases 12-15 (active)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-6) — SHIPPED 2026-03-19</summary>

- [x] **Phase 1: Foundation** — PostGIS schema, canonical key strategy, plugin contract, and project scaffolding (3/3 plans)
- [x] **Phase 2: Geocoding** — Multi-provider geocoding with cache, official record, and admin override (2/2 plans)
- [x] **Phase 3: Validation and Data Import** — USPS address validation and Bibb County GIS CLI import (3/3 plans)
- [x] **Phase 4: Batch and Hardening** — Batch endpoints, per-item error handling, and HTTP layer completion (2/2 plans)
- [x] **Phase 5: Fix Admin Override & Import Order** — Admin override table write fix and import-order documentation (1/1 plan)
- [x] **Phase 6: Documentation & Traceability Cleanup** — SUMMARY frontmatter and ROADMAP checkbox fixes (1/1 plan)

Full details archived in `milestones/v1.0-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.1 Local Data Sources (Phases 7-11) — SHIPPED 2026-03-29</summary>

- [x] **Phase 7: Pipeline Infrastructure** — Direct-return pipeline bypass, provider ABC extension, and staging table migrations (2/2 plans) — completed 2026-03-22
- [x] **Phase 8: OpenAddresses Provider** — OA geocoding and validation from .geojson.gz files via PostGIS staging table (2/2 plans) — completed 2026-03-22
- [x] **Phase 9: Tiger Provider** — Tiger geocoding and validation via PostGIS geocode() and normalize_address() SQL functions (2/2 plans) — completed 2026-03-24
- [x] **Phase 10: NAD Provider** — NAD geocoding and validation from 80M-row staging table with bulk COPY import (2/2 plans) — completed 2026-03-24
- [x] **Phase 11: Fix Batch Endpoint Local Provider Serialization** — Batch endpoints include local provider results in every response item (1/1 plan) — completed 2026-03-24

Full details archived in `milestones/v1.1-ROADMAP.md`.

</details>

### v1.2 Cascading Address Resolution (Phases 12-15)

- [x] **Phase 12: Correctness Fixes and DB Prerequisites** — Fix 4 known provider defects and add GIN trigram indexes before any cascade logic is built (completed 2026-03-29)
- [x] **Phase 13: Spell Correction and Fuzzy/Phonetic Matching** — Offline spell correction layer and pg_trgm + Double Metaphone fallback matching (completed 2026-03-29)
- [ ] **Phase 14: Cascade Orchestrator and Consensus Scoring** — Wire all components into a staged pipeline with cross-provider consensus and auto-set official geocode
- [ ] **Phase 15: LLM Sidecar** — Local Ollama sidecar for address correction when deterministic stages fail (data-driven: execute only if Phase 14 telemetry shows > 1-2% unresolved)

## Phase Details

### Phase 12: Correctness Fixes and DB Prerequisites
**Goal**: Provider defects that would corrupt cascade results are eliminated and the database is prepared for fuzzy matching
**Depends on**: Nothing (first v1.2 phase)
**Requirements**: FIX-01, FIX-02, FIX-03, FIX-04, FUZZ-01
**Success Criteria** (what must be TRUE):
  1. Tiger geocode results no longer match addresses in neighboring counties — a query for a Macon-Bibb address returns only Bibb County results
  2. A truncated 4-digit zip (e.g., "3120") resolves correctly in OA and Macon-Bibb providers via prefix fallback rather than returning NO_MATCH
  3. A street named "Beaver Falls" (where scourgify extracts "Falls" as a suffix token) matches successfully because the query includes the suffix field
  4. Scourgify and Tiger validation responses carry `confidence=0.5` rather than `1.0`, distinguishing structural parse from verified geocode
  5. GIN trigram indexes exist on `openaddresses_points.street` and `nad_points.street_name` — a pg_trgm similarity query against NAD completes within 500ms
**Plans**: 2 plans

Plans:
- [x] 12-01-PLAN.md — Parse expansion (5-tuple), suffix matching, and zip prefix fallback across OA/NAD/Macon-Bibb
- [x] 12-02-PLAN.md — Tiger county spatial post-filter, confidence constants, and GIN trigram migration

### Phase 13: Spell Correction and Fuzzy/Phonetic Matching
**Goal**: Addresses with typoed or phonetically misspelled street names are recovered before they reach the cascade orchestrator
**Depends on**: Phase 12
**Requirements**: SPELL-01, SPELL-02, SPELL-03, FUZZ-02, FUZZ-03, FUZZ-04
**Success Criteria** (what must be TRUE):
  1. A street name token with a single-character typo (e.g., "Mrccer Rd" for "Mercer Rd") is corrected by SpellCorrector before scourgify normalization, and the corrected form matches at exact match
  2. House numbers, zip codes, and state abbreviations are never altered by spell correction — only the StreetName token is touched
  3. An address that fails all exact-match providers but has a street name within trigram similarity 0.65-0.75 of a known street returns a candidate via FuzzyMatcher
  4. When trigram similarity is ambiguous, Double Metaphone selects the phonetically closest street name as tiebreaker
  5. The spell correction dictionary auto-rebuilds when `load-oa`, `load-nad`, or `gis import` CLI commands complete, without requiring manual intervention
**Plans**: 2 plans

Plans:
- [x] 13-01-PLAN.md — SpellCorrector with symspellpy, spell_dictionary table, rebuild hooks, and startup loading
- [x] 13-02-PLAN.md — FuzzyMatcher service with word_similarity() + dmetaphone() tiebreaker and 30-address calibration corpus

### Phase 14: Cascade Orchestrator and Consensus Scoring
**Goal**: The geocoding pipeline auto-resolves degraded input into an official geocode without any caller-side changes
**Depends on**: Phase 13
**Requirements**: CASC-01, CASC-02, CASC-03, CASC-04, CONS-01, CONS-02, CONS-03, CONS-04, CONS-05, CONS-06
**Success Criteria** (what must be TRUE):
  1. A geocode request for a degraded address (typo, truncated zip, wrong suffix) returns an official geocode set automatically by the cascade — the caller sees the same response shape as a direct hit
  2. When two or more providers agree within 100m, the cascade exits early and skips fuzzy and later stages — single-address P95 latency stays under 3 seconds
  3. Provider results more than 1km from the winning cluster centroid are flagged as low-confidence outliers in the response
  4. A new OfficialGeocoding record is auto-set from the consensus winner with `set_by_stage` audit metadata; an existing admin override is never overwritten
  5. Sending `?dry_run=true` runs the full cascade and returns what would have been set without writing any OfficialGeocoding record
  6. Disabling cascade via `CASCADE_ENABLED=false` restores the v1.1 exact-match-only behavior — no regressions on the existing test suite
**Plans**: TBD
**UI hint**: no

### Phase 15: LLM Sidecar
**Goal**: Addresses that survive all deterministic cascade stages without resolution are corrected by a local LLM and re-verified before auto-set
**Depends on**: Phase 14
**Requirements**: LLM-01, LLM-02, LLM-03, LLM-04
**Success Criteria** (what must be TRUE):
  1. The Ollama service starts via Docker Compose with `CASCADE_LLM_ENABLED=true` and the qwen2.5:3b model is available without any manual pull step at startup
  2. An address that fails exact and fuzzy match is sent to the LLM, which returns a structured JSON correction; the corrected form is then re-verified against provider databases before any geocode result is returned
  3. An LLM suggestion that would change the state code or produce a zip/state mismatch is hard-rejected and the cascade returns NO_MATCH rather than a bad geocode
  4. When the Ollama service is unavailable, the cascade degrades gracefully — requests complete with whatever result the deterministic stages produced, no errors surfaced to the caller
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-03-19 |
| 2. Geocoding | v1.0 | 2/2 | Complete | 2026-03-19 |
| 3. Validation and Data Import | v1.0 | 3/3 | Complete | 2026-03-19 |
| 4. Batch and Hardening | v1.0 | 2/2 | Complete | 2026-03-19 |
| 5. Fix Admin Override & Import Order | v1.0 | 1/1 | Complete | 2026-03-19 |
| 6. Documentation & Traceability Cleanup | v1.0 | 1/1 | Complete | 2026-03-19 |
| 7. Pipeline Infrastructure | v1.1 | 2/2 | Complete | 2026-03-22 |
| 8. OpenAddresses Provider | v1.1 | 2/2 | Complete | 2026-03-22 |
| 9. Tiger Provider | v1.1 | 2/2 | Complete | 2026-03-24 |
| 10. NAD Provider | v1.1 | 2/2 | Complete | 2026-03-24 |
| 11. Fix Batch Local Serialization | v1.1 | 1/1 | Complete | 2026-03-24 |
| 12. Correctness Fixes and DB Prerequisites | v1.2 | 2/2 | Complete | 2026-03-29 |
| 13. Spell Correction and Fuzzy/Phonetic Matching | v1.2 | 2/2 | Complete   | 2026-03-29 |
| 14. Cascade Orchestrator and Consensus Scoring | v1.2 | 0/? | Not started | - |
| 15. LLM Sidecar | v1.2 | 0/? | Not started | - |
