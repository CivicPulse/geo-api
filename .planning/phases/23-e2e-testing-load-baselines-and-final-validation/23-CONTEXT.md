# Phase 23: E2E Testing, Load Baselines, and Final Validation - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate that all 5 providers (Census, OpenAddresses, Tiger, NAD, Macon-Bibb) work correctly in deployed prod, establish cold-cache and warm-cache performance baselines via Locust, verify observability (logs/traces/metrics) under load, and run a top-to-bottom validation pass across all 7 milestone categories until clean. This phase does NOT add new features — it confirms production readiness of everything built in Phases 17–22.

</domain>

<decisions>
## Implementation Decisions

### E2E Test Execution
- **D-01:** E2E tests live in `tests/e2e/` directory, separate from unit tests. Distinguished by pytest markers (`@pytest.mark.e2e`) for selective runs.
- **D-02:** Framework is pytest + httpx hitting real HTTP endpoints (same stack as unit tests, familiar patterns).
- **D-03:** Tests connect to deployed service via `kubectl port-forward` — no cluster changes needed.
- **D-04:** Test data uses a per-provider fixture file (JSON/YAML) mapping each provider to known-good addresses. Primary addresses are real Macon-Bibb County addresses since GIS data is loaded for that jurisdiction.
- **D-05:** E2E tests cover all 5 providers (geocode + validate per provider) plus a full cascade pipeline E2E test per TEST-01 and TEST-02.

### Load Test Design
- **D-06:** Locust load test files live in `loadtests/` at project root (separate from pytest tests — Locust runs via its own CLI).
- **D-07:** Cold-cache and warm-cache are separate Locust runs with separate reports. Run 1: unique addresses (cold). Run 2: repeated addresses (warm).
- **D-08:** Load tests exercise `/geocode` (single), `/validate` (single), and cascade pipeline endpoints. Batch endpoints excluded from baseline runs to avoid skewing latency profiles.
- **D-09:** Ramp-up profile: 0→30 users over 2 minutes, sustain 30 users for 5 minutes (~7 min total per run). Produces stable P50/P95/P99 percentiles.

### Observability Verification
- **D-10:** Verification uses Python scripts with httpx in `scripts/verify/`, querying Loki, Tempo, and VictoriaMetrics APIs after load tests complete.
- **D-11:** Scripts assert: (a) structured JSON logs in Loki with `request_id` and `trace_id` fields (TEST-04), (b) traces in Tempo with DB and provider child spans (TEST-05), (c) metrics in VictoriaMetrics with correct labels — request rate, latency histograms, error rate (TEST-06).
- **D-12:** Scripts exit non-zero on assertion failures for scripted pipeline use.

### Final Validation Pass
- **D-13:** Validation is a structured Markdown checklist (`23-VALIDATION-CHECKLIST.md`) in the phase directory covering all 7 categories: debt, review, observability, deployment, resilience, testing, validation.
- **D-14:** Blockers found during the pass are fixed in-phase per VAL-01, then the FULL validation pass is re-run until clean (not just the failed category).
- **D-15:** Non-blockers are logged per VAL-02 for subsequent phases or future milestones.
- **D-16:** Results recorded directly in the checklist with dates and pass/fail status for audit trail.

### Claude's Discretion
- Specific Macon-Bibb addresses to include in the fixture file (based on loaded GIS data)
- Locust task weighting between geocode/validate/cascade endpoints
- Exact Loki/Tempo/VictoriaMetrics query syntax in verification scripts
- Validation checklist item granularity within each of the 7 categories
- Whether to include a helper script/Makefile target to orchestrate the port-forward + test run

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — TEST-01 through TEST-06, VAL-01 through VAL-03 acceptance criteria
- `.planning/ROADMAP.md` §Phase 23 — Success criteria (6 items: provider E2E, cascade E2E, Locust baselines, Loki logs, Tempo traces + VictoriaMetrics metrics, clean validation pass)

### Prior Phase Context (Observability — critical for verification scripts)
- `.planning/phases/22-observability/22-CONTEXT.md` — D-01 through D-04: log format, metric tiers, manual spans, request IDs. Defines what verification scripts must check for.

### Prior Phase Context (Deployment — critical for E2E connectivity)
- `.planning/phases/20-health-resilience-and-k8s-manifests/20-CONTEXT.md` — D-04: Kustomize structure, D-06: ClusterIP service, D-09: Ollama sidecar config, D-10/D-11/D-12: graceful shutdown

### K8s Manifests (deployment targets)
- `k8s/base/deployment.yaml` — Base Deployment with Ollama sidecar
- `k8s/base/service.yaml` — ClusterIP Service definition
- `k8s/overlays/dev/` — Dev-specific patches
- `k8s/overlays/prod/` — Prod-specific patches

### Source Files (providers under test)
- `src/civpulse_geo/providers/census.py` — CensusGeocodingProvider
- `src/civpulse_geo/providers/openaddresses.py` — OAGeocodingProvider, OAValidationProvider
- `src/civpulse_geo/providers/tiger.py` — TigerGeocodingProvider, TigerValidationProvider
- `src/civpulse_geo/providers/nad.py` — NADGeocodingProvider, NADValidationProvider
- `src/civpulse_geo/providers/macon_bibb.py` — MaconBibbGeocodingProvider, MaconBibbValidationProvider

### Existing Test Infrastructure (patterns to follow)
- `tests/conftest.py` — Existing fixtures (ASGI mock pattern — E2E will use different fixtures for real HTTP)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/conftest.py` fixture patterns (pytest + httpx): E2E conftest will mirror structure but use real HTTP base URL instead of ASGITransport
- Provider class registry (`providers/registry.py`): reference for which providers exist and their interface contracts
- `src/civpulse_geo/observability/` modules: reference for what log fields, metric names, and span attributes to verify

### Established Patterns
- All tests use pytest with async support (`pytest-asyncio`)
- httpx is the HTTP client throughout the codebase (both in providers and tests)
- Settings via pydantic-settings `BaseSettings` class in `config.py` — E2E tests may need a separate config for base URL

### Integration Points
- E2E tests hit the service via port-forwarded localhost — base URL is configurable (env var or pytest fixture)
- Load tests connect to the same port-forwarded endpoint
- Verification scripts query observability backends (Loki, Tempo, VictoriaMetrics) — these have separate endpoints from the geo-api service

</code_context>

<specifics>
## Specific Ideas

- Test addresses should be real Macon-Bibb County addresses since that's the project's home jurisdiction and GIS data is loaded for it
- Per-provider fixture file allows testing each provider's strengths with addresses known to resolve correctly
- Separate cold/warm cache runs give clean baseline separation without statistical artifacts from mixed workloads

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 23-e2e-testing-load-baselines-and-final-validation*
*Context gathered: 2026-03-30*
