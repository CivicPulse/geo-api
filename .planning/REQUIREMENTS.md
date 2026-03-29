# Requirements: CivPulse Geo API

**Defined:** 2026-03-29
**Core Value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching, local data sources, and giving admins authority over the official answer

## v1.2 Requirements

Requirements for v1.2 Cascading Address Resolution. Each maps to roadmap phases.

### Correctness Fixes

- [x] **FIX-01**: Tiger geocode results are filtered by expected county/city boundary via PostGIS `restrict_region` parameter, discarding wrong-county matches
- [x] **FIX-02**: Local providers (OA, Macon-Bibb) fall back to zip prefix matching (`LIKE '3120%'`) when input zip is < 5 digits, instead of exact equality
- [x] **FIX-03**: Street name matching includes `street_suffix` in the query to prevent multi-word street names (e.g., "Beaver Falls") from failing when scourgify extracts the suffix token
- [x] **FIX-04**: Scourgify validation confidence reduced from 1.0 to 0.3; Tiger validation confidence reduced to 0.4 — reflecting "structurally parsed but not address-verified" semantics (per locked decisions D-09, D-10)

### Spell Correction

- [x] **SPELL-01**: Address input is spell-corrected via symspellpy before scourgify normalization, scoped to the street name token only (house numbers, zips, and state abbreviations are excluded)
- [x] **SPELL-02**: Spell correction dictionary is built from NAD, OA, and Macon-Bibb staging table street names, supplemented with Tiger `featnames` where available
- [x] **SPELL-03**: Dictionary auto-rebuilds when `load-oa`, `load-nad`, or `gis import` CLI commands complete

### Fuzzy Matching

- [x] **FUZZ-01**: pg_trgm extension enabled via Alembic migration with GIN trigram indexes on `openaddresses_points.street` and `nad_points.street_name`
- [x] **FUZZ-02**: FuzzyMatcher service uses `word_similarity()` with threshold 0.65-0.70 for street name matching as fallback when all exact providers return NO_MATCH
- [x] **FUZZ-03**: Double Metaphone (`dmetaphone()` from fuzzystrmatch) used as secondary phonetic fallback when trigram similarity is below threshold
- [x] **FUZZ-04**: Fuzzy match thresholds calibrated against Issue #1 E2E test corpus (4 addresses with known ground truth)

### Cascade Pipeline

- [ ] **CASC-01**: CascadeOrchestrator implements staged resolution: normalize → spell-correct → exact match → fuzzy/phonetic → consensus score → auto-set official
- [ ] **CASC-02**: Cascade is feature-flagged via `CASCADE_ENABLED` environment variable (default: true for new installs)
- [ ] **CASC-03**: Early-exit optimization: if any exact-match provider returns confidence >= 0.80, skip fuzzy and later stages
- [ ] **CASC-04**: Per-stage latency budgets enforced (P95 target: < 3s total cascade for single address)

### Consensus Scoring

- [ ] **CONS-01**: Cross-provider consensus scoring groups geocode results into spatial clusters (within 100m) and selects the cluster with highest weighted agreement
- [ ] **CONS-02**: Provider trust weights are configurable (Census: 0.90, OA: 0.80, Macon-Bibb: 0.80, Tiger: 0.40 unrestricted / 0.75 with restrict_region, NAD: 0.80)
- [ ] **CONS-03**: Outlier results (> 1km from winning cluster centroid) are flagged as low-confidence in the response
- [ ] **CONS-04**: Winning cluster centroid is auto-set as OfficialGeocoding when no admin override exists (`ON CONFLICT DO UPDATE` in cascade path; admin overrides are never overwritten)
- [ ] **CONS-05**: All auto-set official records include `set_by_stage` audit metadata indicating which cascade stage produced the result
- [ ] **CONS-06**: Dry-run mode available via query parameter (`?dry_run=true`) — runs full cascade but does not write OfficialGeocoding, returns what would have been set

### LLM Sidecar (Data-Driven)

- [ ] **LLM-01**: Ollama + qwen2.5:3b Docker Compose service added, feature-flagged off by default (`CASCADE_LLM_ENABLED=false`)
- [ ] **LLM-02**: LLMAddressCorrector sends address to local LLM with structured JSON schema output (temperature=0) for component extraction and correction
- [ ] **LLM-03**: Every LLM-corrected address is re-verified against provider databases before use — LLM output is never used as a geocode result directly
- [ ] **LLM-04**: K8s manifests for Ollama deployment with PVC for model storage (ArgoCD-compatible)

> **Note:** LLM phase (LLM-01 through LLM-04) is executed only if Phase 14 telemetry shows > 1-2% of addresses remain unresolved after deterministic cascade stages. Otherwise deferred to v1.3.

## Future Requirements

### v1.3 Candidates

- **PAID-01**: USPS DPV verification via paid API adapter (real delivery_point_verified)
- **EXT-01**: Amazon Location Service provider for additional external geocoding coverage
- **EXT-02**: Geoapify provider for additional external geocoding coverage
- **PERF-01**: Batch cascade processing with configurable concurrency

## Out of Scope

| Feature | Reason |
|---------|--------|
| Google Geocoding API | ToS Section 3.2.3(a) prohibits caching geocoding results — incompatible with geo-api's core model |
| International addresses | US only for v1.x |
| Admin UI | API serves data; admin interface is a separate system |
| Authentication | Internal service, network-level security only |
| Reverse geocoding (lat/lng → address) | v2 candidate |
| Real-time fuzzy matching on every request | FuzzyMatcher only fires as fallback after exact match fails — performance concern |
| LLM-based geocoding | LLM provides parse/correction suggestions only; never used as a geocode source |
| Online/cloud LLM services | Local-only LLM requirement — no data leaves the network |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FIX-01 | Phase 12 | Complete |
| FIX-02 | Phase 12 | Complete |
| FIX-03 | Phase 12 | Complete |
| FIX-04 | Phase 12 | Complete |
| FUZZ-01 | Phase 12 | Complete |
| SPELL-01 | Phase 13 | Complete |
| SPELL-02 | Phase 13 | Complete |
| SPELL-03 | Phase 13 | Complete |
| FUZZ-02 | Phase 13 | Complete |
| FUZZ-03 | Phase 13 | Complete |
| FUZZ-04 | Phase 13 | Complete |
| CASC-01 | Phase 14 | Pending |
| CASC-02 | Phase 14 | Pending |
| CASC-03 | Phase 14 | Pending |
| CASC-04 | Phase 14 | Pending |
| CONS-01 | Phase 14 | Pending |
| CONS-02 | Phase 14 | Pending |
| CONS-03 | Phase 14 | Pending |
| CONS-04 | Phase 14 | Pending |
| CONS-05 | Phase 14 | Pending |
| CONS-06 | Phase 14 | Pending |
| LLM-01 | Phase 15 | Pending |
| LLM-02 | Phase 15 | Pending |
| LLM-03 | Phase 15 | Pending |
| LLM-04 | Phase 15 | Pending |

**Coverage:**
- v1.2 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after v1.2 roadmap creation*
