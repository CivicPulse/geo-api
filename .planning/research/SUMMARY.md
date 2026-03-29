# Project Research Summary

**Project:** CivPulse Geo API — v1.2 Cascading Address Resolution
**Domain:** Multi-provider geocoding pipeline with fuzzy/phonetic fallback, LLM correction, and consensus scoring
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Summary

The v1.2 milestone transforms an existing multi-provider exact-match geocoding API (v1.1) into a self-healing cascade that handles degraded address input. The pipeline stages are: input normalization, spell correction (symspellpy with a domain dictionary bootstrapped from the local address corpus), exact provider dispatch, fuzzy SQL matching via pg_trgm and Double Metaphone, optional LLM correction via an Ollama sidecar, cross-provider consensus scoring, and auto-set of the official geocode. The recommended approach is strictly sequential with early-exit at each stage — cheap deterministic stages first, expensive probabilistic stages only as fallback. The critical architectural decision is that all new logic lives in a `correction/` package and a `CascadeOrchestrator` service; the existing `providers/` package is frozen and requires zero changes.

The stack impact is minimal: only one new Python library (`symspellpy 6.9.0`) is required. PostgreSQL extensions `pg_trgm` and `fuzzystrmatch` are already bundled in the `postgis/postgis:17-3.5` Docker image. The Ollama sidecar is a Docker Compose addition, not a Python dependency, and is feature-flagged off by default (`CASCADE_LLM_ENABLED=false`). Consensus scoring uses PostGIS spatial functions and stdlib math — no new libraries. The net result is a meaningfully more capable pipeline with an extremely contained dependency footprint.

The most significant risks are not technical: they are operational. The Tiger geocoder has a documented wrong-county bug (Issue #1) that causes ~50% error rates when no county boundary restriction is applied. This bug must be fixed before any cascade auto-set logic is enabled, or the pipeline will auto-promote wrong official geocodes at batch scale. Confidence semantics are also currently broken — `scourgify` returns `confidence=1.0` for structural parse success, which is not the same as geocode verification. This semantic issue must be resolved in Phase 1 before any downstream consensus scoring or auto-set logic is built, or those systems will be built on a corrupted confidence scale.

## Key Findings

### Recommended Stack

The v1.2 stack additions are minimal by design. All four new capabilities (spell correction, fuzzy SQL matching, LLM correction, consensus scoring) are implemented using the existing dependency footprint plus one new Python library and one Docker sidecar.

**Core new technologies:**
- `symspellpy 6.9.0`: Symmetric Delete spell correction — 1M+ words/second, custom dictionary support via `create_dictionary_entry()`, compound multi-word correction via `lookup_compound()`. MIT license. The only new Python dependency.
- `pg_trgm` (PostgreSQL contrib): Trigram-based fuzzy string similarity. `word_similarity()` is the correct function for matching a short street name token against a stored value (not `similarity()` which scores poorly when the query is a small fraction of the target). Requires a GIN index per table; without it, trigram scans are unusable at NAD scale (80M rows).
- `fuzzystrmatch` (PostgreSQL contrib): Already enabled as a Tiger prerequisite. `dmetaphone()` and `dmetaphone_alt()` preferred over `soundex()` — Soundex collapses "Main" and "Macon" to the same 4-character code.
- `ollama/ollama` (Docker, `qwen2.5:3b` model): Structured JSON output via REST API. `qwen2.5:3b` (~1.9 GB, ~2.5 GB RAM) is the correct size for CPU-only address string correction. Invoked via existing `httpx.AsyncClient` — no new Python client required.
- Consensus scoring: Custom implementation using PostGIS `ST_Distance(Geography, Geography)` and stdlib `math`. No new library.

**Critical version notes:**
- `httpx==0.28.1` must be >= 0.26.0 for `ollama==0.6.1` (optional package if httpx direct calls are sufficient).
- GIN indexes on `openaddresses_points.street` and `nad_points.street_name` are a prerequisite, not optional — add via Alembic migration.
- `pg_trgm.word_similarity_threshold` default is 0.6; raise to 0.65–0.75 for street name matching.

### Expected Features

The v1.2 pipeline has 11 required features (P1) and 3 deferred features (P2/P3). All P1 features are needed for the milestone to deliver a functional cascade.

**Must have (table stakes — P1):**
- Validation confidence semantics fix: add `confidence_basis` field to `GeocodingResult` distinguishing `STRUCTURAL_PARSE` from `GEOCODED_MATCH` from `FUZZY_MATCH` from `LLM_SUGGESTION`. Without this, consensus scoring operates on corrupted confidence values.
- Street name normalization mismatch fix: USPS suffix expansion applied right-to-left (find last valid suffix token); bidirectional St/Street, Dr/Drive etc. Both sides of any comparison must be normalized identically.
- Input normalization (USPS suffix expansion both directions, uppercase normalize, state canonicalization, zero-pad zip): prerequisite for all provider dispatch.
- Zip prefix fallback: `zip_code LIKE :prefix%` for truncated/4-digit ZIP input; only when street+number match is otherwise unambiguous.
- Tiger county disambiguation via `restrict_region`: pass county polygon from `tiger.county` to `geocode()` to fix the wrong-county bug. This is a hard gate — Tiger results must not feed into auto-set logic until this fix is deployed.
- pg_trgm fuzzy street matching with GIN index (threshold 0.65–0.75 on street_name field).
- Double Metaphone phonetic fallback as tiebreaker when trigram similarity is ambiguous.
- Spell correction layer (symspellpy + domain dictionary bootstrapped from NAD/OA street names corpus).
- Cross-provider consensus scoring (cluster-based, 100m–200m radius, outlier flagging).
- Auto-set official geocode from consensus (confidence >= 0.8 + spatial plausibility `ST_Within` county boundary check; audit metadata required).
- Pipeline stage telemetry (`resolution_stage`, `similarity_score`, elapsed ms per stage, logged via Loguru).

**Should have (differentiators — P2, after validation):**
- Local LLM sidecar (Ollama + qwen2.5:3b): only after telemetry shows >1–2% of addresses fail all deterministic stages. Feature-flagged off (`CASCADE_LLM_ENABLED=false`).
- Per-provider confidence weight tuning: adjust starting weights (Macon-Bibb 1.0, OA 0.9, NAD 0.85, Census 0.80, Tiger-restricted 0.75, Tiger-unrestricted 0.40) based on observed error patterns from telemetry.
- Spell correction dictionary refresh from updated NAD/OA imports.

**Defer (v2+):**
- ML-based address confidence scoring (requires labeled data).
- Real-time USPS DPV validation via USPS API (cost implications).

### Architecture Approach

The cascade is implemented as a 7-stage pipeline coordinated by a new `CascadeOrchestrator` service. The `providers/` package is frozen — all new logic lives in a new `correction/` package. `GeocodingService` delegates to `CascadeOrchestrator` when `CASCADE_ENABLED=true`; behavior is unchanged for deployments without the feature flag. All stages implement early-exit: if a stage produces a result with sufficient confidence (e.g., 2+ providers agree within 100m), subsequent stages are skipped.

**Major components:**
1. `SpellCorrector` (`correction/spell.py`) — symspellpy token correction on `StreetName` tokens only, before scourgify, using a domain dictionary bootstrapped from NAD/OA at startup.
2. `FuzzyMatcher` (`correction/fuzzy.py`) — pg_trgm + Metaphone SQL against `openaddresses_points` and `nad_points`; NOT a provider subclass; called only by the orchestrator after all exact providers return `confidence == 0.0`.
3. `LLMAddressCorrector` (`correction/llm.py`) — thin async httpx client to Ollama; structured JSON output; maximum one re-attempt; 10-second hard timeout; graceful skip when Ollama unavailable.
4. `ConsensusScorer` (`correction/consensus.py`) — pairwise Haversine distance, cluster-based agreement at configurable distance threshold (default 200m), provider weighting, outlier flagging.
5. `CascadeOrchestrator` (`services/cascade.py`) — coordinates all 7 stages; owns early-exit logic, latency budgets, and audit metadata.
6. Modified `GeocodingService` — delegates to `CascadeOrchestrator`; `OfficialGeocoding` upsert changed from `DO NOTHING` to `DO UPDATE` on the cascade path only.
7. Ollama Docker Compose sidecar — model storage on named volume (ZFS/NFS PVC in K8s production); default off via `CASCADE_LLM_ENABLED` env var.

### Critical Pitfalls

1. **Confidence semantics conflation** — `scourgify` returns `confidence=1.0` for structural parse; Tiger returns `confidence=1.0` for normalized geocode. These are different concepts. Fix by adding `confidence_basis` enum field to `GeocodingResult` before building any consensus or auto-set logic. Only `GEOCODED_MATCH` and `FUZZY_MATCH` results contribute to spatial consensus. Avoid by treating `STRUCTURAL_PARSE` results as normalization artifacts, not spatial evidence.

2. **Tiger wrong-county bug auto-sets bad official records at scale** — Tiger without `restrict_region` returns results in neighboring counties (Issue #1 ~50% error rate). If Tiger feeds into cascade auto-set before the county disambiguation fix, wrong official geocodes are written at batch scale and poison downstream vote-api and run-api district assignments. Tiger county disambiguation is a hard gate: Tiger results may not contribute to auto-set logic until `restrict_region` is deployed and verified.

3. **Fuzzy threshold miscalibration** — threshold too low (< 0.65) matches different streets with similar names ("CHERRY ST" vs "CHERRY LN" at similarity ~0.57); threshold too high (> 0.85) catches nothing beyond exact match. Calibrate against the known-bad inputs from the E2E test suite (Issue #1 cases) before wiring downstream auto-set logic. Log raw similarity scores on every fuzzy match for empirical tuning.

4. **Spell correction "corrects" valid street names** — general English dictionaries correct "MERCER" to "MERCY", "LANEY" to "LANE". Use symspellpy with a domain dictionary bootstrapped from the local address corpus. Only apply spell correction to tokens classified as `StreetName` by `usaddress.tag()`. Treat corrections as candidates — if the corrected form still fails exact and fuzzy match, abandon and proceed with original input.

5. **Cascade latency explosion** — sequential stages with no early-exit or per-stage timeouts accumulate: LLM alone is 1–10 seconds on CPU. Define a total budget (3s P95 for single address) before implementing any stage. Implement early-exit at each stage, LLM trigger threshold (only when fuzzy confidence < 0.6), and per-stage timeouts (LLM: 10s, pg_trgm: 500ms statement_timeout). Run local providers concurrently via `asyncio.gather()`.

## Implications for Roadmap

Based on research, the natural phase structure follows the dependency order of the cascade: correctness fixes before new capabilities, foundational DB changes before query logic, deterministic stages before probabilistic stages.

### Phase 1: Foundation Fixes and Schema Prerequisites

**Rationale:** Three correctness bugs from Issue #1 E2E testing must be fixed before any new cascade logic is built. Confidence semantics corruption and the Tiger wrong-county bug are systemic defects that corrupt every downstream stage if not resolved first. The pg_trgm schema migration (GIN indexes) must also land here — fuzzy matching cannot run at production scale without it.

**Delivers:**
- `confidence_basis` field on `GeocodingResult` distinguishing parse quality from geocode quality
- USPS suffix normalization applied right-to-left, bidirectional (fixes multi-word suffix mismatch)
- Tiger `restrict_region` county boundary filter (fixes wrong-county bug — hard gate for auto-set)
- Alembic migration: `CREATE EXTENSION pg_trgm`, GIN index on `openaddresses_points.street`, GIN index on `nad_points.street_name`

**Addresses:** Validation confidence semantics fix, street name normalization mismatch fix, Tiger county disambiguation
**Avoids:** Pitfall 7 (auto-sets wrong official at scale), Pitfall 8 (corrupted confidence), Pitfall 9 (normalization mismatch)
**Research flag:** Standard patterns — well-documented; no phase-level research needed

---

### Phase 2: Input Pre-Processing (Normalization + Spell Correction)

**Rationale:** Normalization and spell correction run before any provider is dispatched. Fixing input quality at this layer reduces failure load on every downstream stage. Both are low-complexity and use existing or minimal new dependencies. The domain dictionary bootstrap requires the NAD/OA data to already be imported (v1.1 milestone complete).

**Delivers:**
- Input normalization: USPS suffix expansion both directions, uppercase normalize, zero-pad zip, state canonicalization
- Zip prefix fallback matching (`LIKE :prefix%` with unambiguous-match guard)
- `SpellCorrector` with symspellpy + domain dictionary bootstrapped from NAD/OA street names at startup
- `usaddress.tag()` scope constraint: spell correction only on `StreetName` tokens
- Correction audit logging (original input, corrected form, canonical normalized — as separate traceable fields)

**Uses:** `symspellpy 6.9.0` (only new Python dependency for the entire milestone)
**Implements:** Architecture Pattern 1 (spell correction before scourgify)
**Avoids:** Pitfall 3 (general dictionary corrects valid street names), Pitfall 10 (zip prefix wrong-city match)
**Research flag:** Standard patterns for symspellpy; no phase-level research needed

---

### Phase 3: Fuzzy and Phonetic Matching

**Rationale:** This is the primary recovery mechanism for typo-laden input that exact match cannot handle. It depends on Phase 1 (GIN indexes must exist, normalization must be consistent on both sides of the comparison) and Phase 2 (spell correction primes input). The `FuzzyMatcher` component is architecturally a service-layer component, not a provider — this boundary must be established before implementation.

**Delivers:**
- `FuzzyMatcher` (`correction/fuzzy.py`): pg_trgm `word_similarity()` on `street_name` field (threshold 0.65–0.75)
- Double Metaphone phonetic fallback as tiebreaker when trigram ambiguous
- Fuzzy confidence assignment: `similarity_score * 0.8`, capped at 0.8 (ensures fuzzy ranks below exact in consensus)
- Query order: `openaddresses_points` first (denser for Macon-Bibb), then `nad_points`
- Threshold calibration against E2E test suite (Issue #1 known-bad inputs) before wiring to auto-set

**Implements:** Architecture Pattern 2 (FuzzyMatcher as service-layer component)
**Avoids:** Pitfall 1 (threshold too low — cross-match different streets), Pitfall 2 (threshold too high — no improvement over exact)
**Research flag:** Threshold calibration is empirical — requires testing against Issue #1 E2E corpus; no external research needed

---

### Phase 4: CascadeOrchestrator and Consensus Scoring

**Rationale:** All individual correction components (Phases 1–3) exist; this phase wires them into the coordinated pipeline. Consensus scoring cannot be built meaningfully until both exact providers (v1.1) and fuzzy matching (Phase 3) can contribute results. The OfficialGeocoding `DO NOTHING` vs. `DO UPDATE` database change lands here and requires the audit metadata fields from Phase 1.

**Delivers:**
- `CascadeOrchestrator` (`services/cascade.py`): 7-stage pipeline with early-exit, per-stage timeouts, total latency budget (3s P95 single address)
- `ConsensusScorer` (`correction/consensus.py`): pairwise Haversine clustering, provider weighting, outlier flagging, `ST_Within` spatial plausibility check
- Provider weights: Macon-Bibb 1.0, OA 0.9, NAD 0.85, Census 0.80, Tiger-restricted 0.75, Tiger-unrestricted 0.40
- Auto-set OfficialGeocoding: `ON CONFLICT DO UPDATE` on cascade path; audit metadata (`set_by_stage`, `winning_confidence`); minimum confidence 0.8; spatial plausibility check
- Dry-run mode (`dry_run=True`) flag for batch validation before production use
- `GeocodingService` modified to delegate to `CascadeOrchestrator` when `CASCADE_ENABLED=true`
- Pipeline stage telemetry: `resolution_stage`, `similarity_score`, elapsed ms per stage

**Implements:** Architecture Patterns 4 (ConsensusScorer) + Stage 7 (OfficialGeocoding auto-set)
**Avoids:** Pitfall 5 (consensus where all providers share same data lineage — weight by independence), Pitfall 6 (latency explosion), Pitfall 7 (auto-sets wrong records at scale)
**Research flag:** Needs code inspection of `ON CONFLICT DO UPDATE` cascade path interaction with v1.0 admin override mechanism; 200m consensus distance threshold should be validated against Macon-Bibb address distribution before setting as default

---

### Phase 5: LLM Sidecar (Optional, Data-Driven)

**Rationale:** Gated behind Phase 4 telemetry. Only proceed if >1–2% of addresses fail all deterministic stages. If that threshold is not reached, Phase 5 is not needed. This is not a speculative build — it is an evidence-based decision.

**Delivers (if triggered):**
- `LLMAddressCorrector` (`correction/llm.py`): async httpx client to Ollama; `qwen2.5:3b`; structured JSON via Pydantic schema; temperature=0; 10-second timeout; graceful skip when unavailable
- Docker Compose `ollama` service with named volume (ZFS/NFS PVC in K8s production on thor)
- Re-entry rule: max one LLM re-attempt; re-enter at Stage 1 on corrected input
- Post-LLM verification: corrected form must pass exact or fuzzy match; never auto-set from LLM suggestion alone
- Hard reject heuristics: state code change, zip/state mismatch

**Implements:** Architecture Pattern 3 (LLM sidecar with graceful degradation)
**Avoids:** Pitfall 4 (LLM hallucinating plausible-but-wrong addresses)
**Research flag:** If triggered, research the `qwen2.5:3b` model pull behavior and K8s PVC configuration for the bare-metal thor cluster storage class.

---

### Phase Ordering Rationale

- Phase 1 must precede all others: confidence semantics corruption and Tiger wrong-county bug are systemic defects that corrupt every downstream stage if not fixed first. The pg_trgm GIN indexes are also a hard prerequisite for Phase 3.
- Phase 2 before Phase 3: spell correction primes input quality; fuzzy matching should see spell-corrected input to produce accurate similarity scores and avoid wasting GIN index scans on corrupted tokens.
- Phase 3 before Phase 4: the orchestrator and consensus scorer need fuzzy results to be meaningful; building consensus scoring against exact-match-only results is a partial implementation requiring rework.
- Phase 5 is optional and data-driven: never build the LLM sidecar speculatively; build Phase 4 telemetry first and let observed failure rates decide.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4:** The interaction between the cascade `ON CONFLICT DO UPDATE` path and the existing admin override mechanism needs explicit code inspection. The v1.0 first-writer-wins semantics must be preserved for admin overrides while the cascade path uses update-if-higher-confidence semantics.
- **Phase 5 (if triggered):** K8s PVC configuration for Ollama model storage on the ZFS/NFS fileserver (bare-metal thor cluster) needs verification against the available storage class.

Phases with standard patterns (skip research):
- **Phase 1:** PostgreSQL `CREATE EXTENSION` migrations and Tiger `restrict_region` parameter are fully documented in official PostGIS docs.
- **Phase 2:** symspellpy API patterns are verified against official docs; normalization logic is algorithmic with no external dependencies.
- **Phase 3:** pg_trgm and fuzzystrmatch SQL patterns are verified against official PostgreSQL 17 docs.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All new dependencies verified against official docs and actual project venv/lock file. Single new Python library. PostgreSQL extensions confirmed bundled in existing Docker image. |
| Features | MEDIUM-HIGH | Feature requirements derived from known defects (Issue #1 E2E failures) and official geocoding research. Fuzzy thresholds (0.65–0.75) are empirically-supported recommendations, not verified values — calibration against the actual corpus is required in Phase 3. |
| Architecture | HIGH | Based on direct codebase inspection of v1.1 implementation. Provider ABCs, OfficialGeocoding upsert pattern, and service layer structure confirmed from existing code. Component boundaries are clear and non-invasive to existing providers. |
| Pitfalls | HIGH | Structural pitfalls (Tiger bug, confidence semantics, latency explosion, auto-set at scale) are all drawn from existing Issue #1 defects and verified code behavior. Threshold-specific pitfalls (fuzzy calibration, spell correction proper-noun collisions) are MEDIUM — empirical risk, not verifiable in advance. |

**Overall confidence:** HIGH for structural decisions; MEDIUM for threshold values requiring empirical calibration against real address data.

### Gaps to Address

- **Fuzzy threshold calibration**: Recommended range 0.65–0.75 for `street_name` field. Actual calibration must be done during Phase 3 against the Issue #1 E2E corpus. Define a test fixture of known-bad to known-good address pairs; measure false positive and false negative rates; adjust threshold in 0.05 steps. Do not wire auto-set logic until calibration is complete.
- **Consensus distance threshold (200m)**: Starting value from published geocoding consensus research. Validate against the Macon-Bibb address distribution before setting as default — in dense downtown neighborhoods, 200m may be too permissive and collapse distinct street intersections into a single cluster.
- **LLM decision gate**: Phase 5 trigger depends on Phase 4 telemetry. No commitment on whether Phase 5 is needed until at least 2–4 weeks of production telemetry from the Phase 4 cascade is available.
- **OfficialGeocoding audit metadata schema**: `set_by_stage`, `winning_confidence`, `alternatives_considered` fields need to be added to the `official_geocodings` table in the Phase 4 Alembic migration. Schema must support bulk rollback queries if a batch auto-set produces incorrect results.

## Sources

### Primary (HIGH confidence)
- [PostgreSQL 17 pg_trgm official docs](https://www.postgresql.org/docs/current/pgtrgm.html) — all operators, functions, GIN vs GiST index types, threshold tuning
- [PostgreSQL 17 fuzzystrmatch official docs](https://www.postgresql.org/docs/17/fuzzystrmatch.html) — dmetaphone, soundex, levenshtein function signatures and encoding caveats
- [symspellpy GitHub](https://github.com/mammothb/symspellpy) — `load_dictionary()`, `load_bigram_dictionary()`, `create_dictionary_entry()`, `lookup_compound()` API
- [Ollama structured outputs official docs](https://docs.ollama.com/capabilities/structured-outputs) — `format` parameter JSON schema, structured output behavior
- [PostGIS geocode() function docs](https://postgis.net/docs/Geocode.html) — `restrict_region` parameter, return type, rating semantics
- Direct codebase inspection — provider ABCs, OfficialGeocoding upsert pattern, GeocodingService structure, v1.1 implementation

### Secondary (MEDIUM confidence)
- [EarthDaily Geocoding Consensus Algorithm](https://earthdaily.com/blog/geocoding-consensus-algorithm-a-foundation-for-accurate-risk-assessment) — cluster-based spatial agreement approach
- [Multi-provider geocoding optimization research](https://www.tandfonline.com/doi/full/10.1080/17538947.2025.2578735) — provider weighting approaches
- [Geocoding systematic review 2025](https://arxiv.org/pdf/2503.18888) — LLM hallucination on rural address geocoding
- [Ollama Docker Hub](https://hub.docker.com/r/ollama/ollama) — container environment variables, model storage
- [Qwen2.5-3B hardware specs](https://apxml.com/models/qwen2-5-3b) — quantization sizes, RAM requirements, CPU inference speed

### Tertiary (LOW confidence)
- LLM trigger threshold (fuzzy confidence < 0.6) — derived from architectural reasoning; needs empirical validation from Phase 4 telemetry before treating as a fixed value

---
*Research completed: 2026-03-29*
*Ready for roadmap: yes*
