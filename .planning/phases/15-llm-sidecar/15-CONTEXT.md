# Phase 15: LLM Sidecar - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a local Ollama LLM sidecar (qwen2.5:3b) as a cascade stage for address correction when all deterministic stages (exact match + fuzzy/phonetic) fail to resolve an address. The LLM parses/corrects the address into structured components, which are re-verified against provider databases before use. The LLM never produces geocode results directly. Feature-flagged off by default. Includes Docker Compose service, K8s manifests, and graceful degradation when Ollama is unavailable.

</domain>

<decisions>
## Implementation Decisions

### LLM Interaction Design (LLM-02)
- **D-01:** LLM receives raw address string only — no provider failure context, no fuzzy near-misses. Simplest prompt, fastest inference
- **D-02:** LLM returns structured JSON with full component extraction: street_number, street_name, street_suffix, city, state, zip — mirrors the 5-tuple used by local providers (_parse_input_address)
- **D-03:** Single best correction only (not multiple variants). temperature=0 for deterministic output. One JSON object per request
- **D-04:** Structured JSON schema output enforced via Ollama's format parameter — the model is constrained to the expected schema

### Cascade Integration (LLM-02, LLM-03)
- **D-05:** LLM fires as stage 4 (between fuzzy and consensus) ONLY when exact + fuzzy stages produced zero geocode results. Most conservative trigger — LLM is a last resort before NO_MATCH
- **D-06:** Re-verified results only enter consensus scoring. The LLM itself has no trust weight — it just fixes the input. Re-verified results carry their normal provider trust weights (Census=0.90, OA=0.80, etc.)
- **D-07:** LLM stage timeout: 5000ms (generous). Since LLM only fires when everything else failed, extra latency is acceptable — the alternative is NO_MATCH anyway
- **D-08:** LLM timeout follows existing graceful degradation pattern (D-16 from Phase 14): if timeout hits, skip stage and continue cascade with whatever prior stages produced
- **D-09:** CASCADE_LLM_ENABLED env var (default: false) follows the CASCADE_ENABLED feature flag pattern from Phase 14

### Infrastructure & Deployment (LLM-01, LLM-04)
- **D-10:** Docker Compose: Ollama service using ollama/ollama image, auto-pull qwen2.5:3b on first start via entrypoint script. Volume for model persistence — subsequent starts are instant
- **D-11:** Resource limits: mem_limit: 4g only, no CPU limit. qwen2.5:3b uses ~2-3GB RAM; let it use available CPU for faster inference
- **D-12:** K8s manifests: CPU-only Deployment + PVC for model storage. No GPU requirements — matches bare-metal K8s on thor. ArgoCD-compatible (plain manifests or Kustomize)
- **D-13:** Health check: Ollama exposes GET /api/tags — use as readiness probe. Model availability checked at API startup (similar to conditional provider registration pattern)

### Safety Guardrails (LLM-03)
- **D-14:** Hard-reject before re-verification: reject if LLM changed the state code from original input, or if LLM's zip doesn't match the state (basic zip-prefix-to-state mapping). Catches worst hallucinations cheaply
- **D-15:** When Ollama is unavailable: silent skip — log warning, skip LLM stage, cascade continues with deterministic results. Caller never knows LLM was attempted. Per success criterion 4
- **D-16:** Malformed JSON (parse failure, missing required fields): no retry, skip stage. With temperature=0 and structured output, retrying the same input produces the same bad output. Log raw response for debugging
- **D-17:** LLM output is NEVER used as a geocode result directly (LLM-03). The corrected address is re-run through exact-match providers. If no provider confirms the correction, it's discarded

### Claude's Discretion
- LLMAddressCorrector class structure and method decomposition
- Exact prompt engineering for qwen2.5:3b (system prompt, few-shot examples)
- Ollama client implementation (httpx async client vs ollama-python library)
- Zip-prefix-to-state mapping implementation (hardcoded dict vs database lookup)
- How re-verification calls providers (reuse existing exact-match stage logic vs dedicated re-verify method)
- K8s manifest format (plain YAML vs Kustomize overlays)
- Ollama Docker entrypoint script details (pull retry logic, startup ordering)
- cascade_trace fields for the LLM stage
- set_by_stage value for LLM-assisted results (e.g., "llm_correction_consensus")

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Services (modification targets)
- `src/civpulse_geo/services/cascade.py` — CascadeOrchestrator with 6-stage pipeline. LLM stage slots between fuzzy (stage 3) and consensus (stage 4→5). Key: run() method, early-exit logic, stage timeout pattern
- `src/civpulse_geo/services/geocoding.py` — GeocodingService delegates to CascadeOrchestrator.run(). May need LLM client passed through
- `src/civpulse_geo/services/fuzzy.py` — FuzzyMatcher as reference for how a service integrates as a cascade stage

### Provider Infrastructure
- `src/civpulse_geo/providers/base.py` — GeocodingProvider ABC. Re-verification calls providers through this interface
- `src/civpulse_geo/providers/openaddresses.py` — `_parse_input_address()` 5-tuple parser that LLM output should mirror
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult dataclass with confidence field

### Configuration
- `src/civpulse_geo/config.py` — Pydantic BaseSettings. Needs CASCADE_LLM_ENABLED, LLM timeout, Ollama URL

### Infrastructure
- `docker-compose.yml` — Current db + api services. Ollama becomes third service
- No K8s manifests exist yet — LLM-04 requires creating them (new `k8s/` directory)

### Spell Correction (startup pattern reference)
- `src/civpulse_geo/spell/corrector.py` — SpellCorrector loaded at app startup into app.state. LLM client should follow same pattern

### Requirements
- `.planning/REQUIREMENTS.md` — LLM-01 through LLM-04

### Prior Phase Context
- `.planning/phases/14-cascade-orchestrator-and-consensus-scoring/14-CONTEXT.md` — Cascade design decisions D-01 through D-22. Especially: D-05 (parallel exact match), D-12 (early-exit), D-13 (consensus always runs), D-14 (stage sequence), D-16 (graceful degradation), D-22 (ON CONFLICT DO UPDATE)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CascadeOrchestrator` in `services/cascade.py` — stage timeout pattern (asyncio.wait_for with graceful fallback) reusable for LLM stage
- `_parse_input_address()` in `providers/openaddresses.py` — 5-tuple parser defines the target format for LLM JSON output
- `SpellCorrector` startup pattern in `spell/corrector.py` — model for how LLM client should be loaded into app.state
- Conditional provider registration pattern (_oa_data_available, _tiger_extension_available) — model for Ollama availability check at startup

### Established Patterns
- Services are stateless classes instantiated per-request
- External service clients loaded at startup into `app.state` (SpellCorrector, providers dict)
- Feature flags via Pydantic BaseSettings env vars (CASCADE_ENABLED pattern)
- Per-stage timeouts with graceful degradation (empty result, cascade continues)
- Structured output via Pydantic models for all API responses

### Integration Points
- `CascadeOrchestrator.run()` — new LLM stage between current stage 3 (fuzzy) and stage 4 (consensus)
- `config.py` Settings class — needs CASCADE_LLM_ENABLED, OLLAMA_URL, LLM_TIMEOUT_MS
- `docker-compose.yml` — new ollama service with volume, health check, mem_limit
- New `k8s/` directory for Ollama Deployment + PVC + Service manifests
- API startup (`main.py` or equivalent) — LLM client initialization into app.state

</code_context>

<specifics>
## Specific Ideas

- LLM stage fires only on zero results from deterministic stages — this is the most conservative approach and means LLM latency only affects the hardest cases
- 5000ms timeout is generous because users hitting this path would otherwise get NO_MATCH — even slow CPU inference is better than no answer
- The re-verification loop (LLM corrects → re-query providers → results enter consensus) means the LLM is never a source of truth, only an input fixer
- Auto-pull model strategy keeps Docker Compose simple — volume persistence means the ~2GB download only happens once

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-llm-sidecar*
*Context gathered: 2026-03-29*
