# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- ✅ **v1.1 Local Data Sources** — Phases 7-11 (shipped 2026-03-29)
- ✅ **v1.2 Cascading Address Resolution** — Phases 12-16 (shipped 2026-03-29)
- 🚧 **v1.3 Production Readiness & Deployment** — Phases 17-23 (in progress)

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

<details>
<summary>✅ v1.2 Cascading Address Resolution (Phases 12-16) — SHIPPED 2026-03-29</summary>

- [x] **Phase 12: Correctness Fixes and DB Prerequisites** — Fix 4 known provider defects and add GIN trigram indexes (2/2 plans) — completed 2026-03-29
- [x] **Phase 13: Spell Correction and Fuzzy/Phonetic Matching** — Offline spell correction and pg_trgm + Double Metaphone fallback (2/2 plans) — completed 2026-03-29
- [x] **Phase 14: Cascade Orchestrator and Consensus Scoring** — 6-stage cascade pipeline with cross-provider consensus and auto-set official (3/3 plans) — completed 2026-03-29
- [x] **Phase 15: LLM Sidecar** — Local Ollama qwen2.5:3b for address correction when deterministic stages fail (3/3 plans) — completed 2026-03-29
- [x] **Phase 16: Audit Gap Closure** — FuzzyMatcher startup wiring, legacy 5-tuple fix, Phase 13 verification (1/1 plan) — completed 2026-03-29

Full details archived in `milestones/v1.2-ROADMAP.md`.

</details>

### 🚧 v1.3 Production Readiness & Deployment (In Progress)

**Milestone Goal:** Harden, deploy, test, and validate geo-api across dev and prod K8s environments with full observability and all 5 providers verified at scale.

- [x] **Phase 17: Tech Debt Resolution** — Resolve all 4 known defects that corrupt runtime behavior (Tiger timeout, cache_hit hardcode, spell dictionary startup, CLI test failures) (completed 2026-03-29)
- [ ] **Phase 18: Code Review** — Parallel security, stability, and performance audit by three independent agent teams; all blocking findings resolved
- [ ] **Phase 19: Dockerfile and Database Provisioning** — Production multi-stage Docker image pushed to GHCR; dev and prod databases provisioned on shared PostgreSQL instance
- [ ] **Phase 20: Health, Resilience, and K8s Manifests** — Split health endpoints, graceful shutdown, K8s Deployment with Ollama sidecar, ClusterIP Service, ArgoCD apps, and Kustomize overlays for dev and prod
- [ ] **Phase 21: CI/CD Pipeline** — GitHub Actions CI (lint + test) and CD (build + GHCR push + ArgoCD trigger) with Trivy scan; automated dev sync, manual prod gate
- [ ] **Phase 22: Observability** — Structured JSON logging, Prometheus /metrics, OpenTelemetry traces exported to Tempo, and Loguru trace context middleware for Loki-to-Tempo correlation
- [ ] **Phase 23: E2E Testing, Load Baselines, and Final Validation** — E2E suite for all 5 providers, Locust cold-cache/warm-cache baselines, observability verification under load, and a top-to-bottom validation pass that repeats until clean

## Phase Details

### Phase 17: Tech Debt Resolution
**Goal**: All 4 known runtime defects are resolved and the test suite passes cleanly
**Depends on**: Phase 16 (v1.2 complete)
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04
**Success Criteria** (what must be TRUE):
  1. Tiger provider completes geocoding requests without 2000ms timeout errors under normal load
  2. Repeated geocoding calls for the same address return cache_hit=True on subsequent requests
  3. Application startup auto-populates the spell dictionary without any manual CLI intervention required
  4. All 504 test suite entries pass (or pre-existing CLI fixture failures are fixed and eliminated)
**Plans**: 2 plans
Plans:
- [x] 17-01-PLAN.md — Fix OA accuracy parser, per-provider timeouts, Tiger optimization, cascade cache-hit early exit
- [x] 17-02-PLAN.md — Spell dictionary auto-rebuild at startup

### Phase 18: Code Review
**Goal**: Codebase passes a thorough three-team audit with all blocking security, stability, and performance findings resolved
**Depends on**: Phase 17
**Requirements**: REVIEW-01, REVIEW-02, REVIEW-03
**Note**: Code review runs three parallel agent teams — security team (injection vectors, unvalidated inputs, exposed secrets), stability team (uncaught exceptions, error path coverage, graceful degradation), performance team (N+1 queries, pool sizing, logic errors). Each team produces a findings report; blockers are resolved in-phase, non-blockers are logged for subsequent phases per VAL-01/VAL-02 policy.
**Success Criteria** (what must be TRUE):
  1. No unvalidated external inputs, injection vectors, or secrets present in the codebase (security finding list empty or deferred)
  2. Every error path in all providers and pipeline stages returns a handled response (no unguarded exception bubbling to the client)
  3. No N+1 query patterns exist in provider or pipeline code; SQLAlchemy connection pool sizing matches deployment resource limits
**Plans**: TBD

### Phase 19: Dockerfile and Database Provisioning
**Goal**: A production Docker image exists in GHCR and both dev and prod databases are provisioned and reachable from inside K8s pods
**Depends on**: Phase 18
**Requirements**: DEPLOY-01, DEPLOY-08
**Success Criteria** (what must be TRUE):
  1. Docker image builds successfully from a multi-stage Dockerfile using a non-root appuser, no dev dependencies in the runtime layer, and exec-form CMD
  2. Image is pushed to GHCR and pullable by the k3s cluster
  3. geo-api database exists on the shared PostgreSQL instance in both civpulse-dev and civpulse-prod namespaces, with Alembic migrations applied
  4. A test pod inside each namespace can connect to postgresql.civpulse-infra.svc.cluster.local:5432 and run a query
**Plans**: TBD

### Phase 20: Health, Resilience, and K8s Manifests
**Goal**: geo-api is deployed to both dev and prod K8s namespaces with correct probes, Ollama sidecar, graceful shutdown, and ArgoCD managing both environments
**Depends on**: Phase 19
**Requirements**: RESIL-01, RESIL-02, RESIL-03, RESIL-04, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05, DEPLOY-07
**Success Criteria** (what must be TRUE):
  1. /health/live returns 200 immediately (no DB dependency); /health/ready returns 200 only after DB and all registered providers are verified
  2. K8s Deployment in civpulse-dev and civpulse-prod runs geo-api + Ollama sidecar with startup, liveness, and readiness probes configured
  3. Spell dictionary rebuilds and provider data verifies automatically during pod startup (no manual CLI step needed post-deploy)
  4. Sending SIGTERM to the pod results in graceful shutdown — in-flight requests complete, asyncpg pool closes cleanly, pod terminates without error
  5. ArgoCD shows both dev and prod applications in Synced/Healthy state
**Plans**: TBD

### Phase 21: CI/CD Pipeline
**Goal**: Every merge to main automatically builds, scans, and publishes a new image and triggers ArgoCD to deploy to dev; prod requires a manual promotion
**Depends on**: Phase 20
**Requirements**: DEPLOY-06
**Success Criteria** (what must be TRUE):
  1. A pull request to main triggers the CI workflow (ruff lint + full pytest suite) and must pass before merge
  2. A merge to main triggers the CD workflow: Docker image built, Trivy vulnerability scan runs, image pushed to GHCR with immutable SHA tag, and ArgoCD dev sync triggered
  3. Production deployment requires explicit manual approval (not triggered automatically on merge)
**Plans**: TBD

### Phase 22: Observability
**Goal**: Every request produces a structured JSON log entry, a Prometheus metric, and a distributed trace; logs and traces are correlated by trace_id in Grafana
**Depends on**: Phase 21
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-04
**Success Criteria** (what must be TRUE):
  1. Every log line written to stdout is valid JSON with service, environment, version, git_commit, and request_id fields
  2. GET /metrics returns Prometheus-format data and VictoriaMetrics scrapes it successfully (request rate and latency histograms visible in Grafana)
  3. OpenTelemetry traces for geocoding requests appear in Tempo with FastAPI, SQLAlchemy, and httpx spans visible
  4. A Loki log entry for a traced request contains a clickable trace_id that navigates to the correct Tempo trace
**Plans**: TBD
**UI hint**: yes

### Phase 23: E2E Testing, Load Baselines, and Final Validation
**Goal**: All 5 providers work correctly in deployed prod, performance baselines are established, observability is validated under load, and a top-to-bottom clean pass confirms production readiness
**Depends on**: Phase 22
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, VAL-01, VAL-02, VAL-03
**Note**: VAL-01 (blockers resolved in-phase) and VAL-02 (non-blockers logged for subsequent phases) are process constraints that apply across all phases of this milestone; they are formally mapped here because Phase 23 is where compliance is validated. The final validation pass (VAL-03) repeats all checks until the run is clean.
**Success Criteria** (what must be TRUE):
  1. E2E tests pass for all 5 providers (Census, OpenAddresses, Tiger, NAD, Macon-Bibb) — geocode and validate endpoints return correct results against deployed prod
  2. Full cascade pipeline E2E test passes: a degraded address input resolves to a correct official geocode end-to-end in deployed prod
  3. Locust load test produces cold-cache P50/P95/P99 latency baselines at 30 concurrent users; warm-cache baselines derived separately
  4. Structured JSON logs appear in Loki under load with correct request_id and trace_id fields on every entry
  5. Traces appear in Tempo under load with DB and provider child spans; metrics appear in VictoriaMetrics with correct labels
  6. A top-to-bottom validation pass covering all 7 categories (debt, review, observability, deployment, resilience, testing, validation) completes with no blockers
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
| 13. Spell Correction and Fuzzy/Phonetic Matching | v1.2 | 2/2 | Complete | 2026-03-29 |
| 14. Cascade Orchestrator and Consensus Scoring | v1.2 | 3/3 | Complete | 2026-03-29 |
| 15. LLM Sidecar | v1.2 | 3/3 | Complete | 2026-03-29 |
| 16. Audit Gap Closure | v1.2 | 1/1 | Complete | 2026-03-29 |
| 17. Tech Debt Resolution | v1.3 | 2/2 | Complete    | 2026-03-29 |
| 18. Code Review | v1.3 | 0/TBD | Not started | - |
| 19. Dockerfile and Database Provisioning | v1.3 | 0/TBD | Not started | - |
| 20. Health, Resilience, and K8s Manifests | v1.3 | 0/TBD | Not started | - |
| 21. CI/CD Pipeline | v1.3 | 0/TBD | Not started | - |
| 22. Observability | v1.3 | 0/TBD | Not started | - |
| 23. E2E Testing, Load Baselines, and Final Validation | v1.3 | 0/TBD | Not started | - |
