# Requirements: CivPulse Geo API

**Defined:** 2026-03-29
**Core Value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching, local data sources, and admin authority over the official answer

## v1.3 Requirements

Requirements for Production Readiness & Deployment milestone. Each maps to roadmap phases.

### Tech Debt

- [ ] **DEBT-01**: Tiger provider responds consistently under load (2000ms timeout resolved)
- [ ] **DEBT-02**: Cascade path uses cached results for repeated calls (cache_hit=False hardcode removed)
- [ ] **DEBT-03**: Spell dictionary auto-populates at application startup without manual CLI intervention
- [ ] **DEBT-04**: CLI test failures fixed (test_import_cli.py, test_load_oa_cli.py fixture data resolved)

### Code Review

- [ ] **REVIEW-01**: Codebase passes security audit (no unvalidated inputs, injection vectors, or exposed secrets)
- [ ] **REVIEW-02**: Codebase passes stability audit (no uncaught exceptions, all error paths handled gracefully)
- [ ] **REVIEW-03**: Codebase passes performance audit (no N+1 queries, pool sizing correct, no logic errors)

### Observability

- [ ] **OBS-01**: Structured JSON logging via Loguru to stdout with per-request request_id correlation
- [ ] **OBS-02**: Prometheus /metrics endpoint exposed for VictoriaMetrics scraping
- [ ] **OBS-03**: OpenTelemetry traces exported via OTLP to Tempo with FastAPI/SQLAlchemy auto-instrumentation
- [ ] **OBS-04**: Loguru trace_id/span_id injection via custom middleware for log-trace correlation in Grafana

### Deployment

- [ ] **DEPLOY-01**: Multi-stage Dockerfile (uv builder, non-root runtime, exec-form CMD, read-only FS compatible)
- [ ] **DEPLOY-02**: K8s Deployment manifests for civpulse-dev and civpulse-prod with Ollama sidecar container
- [ ] **DEPLOY-03**: ClusterIP Service (internal only) for both environments
- [ ] **DEPLOY-04**: Init containers for Alembic migrations and spell dictionary rebuild
- [ ] **DEPLOY-05**: ConfigMap and Secret resources for environment-specific configuration
- [ ] **DEPLOY-06**: GitHub Actions workflow (build → GHCR push with sha-tag → manifest update)
- [ ] **DEPLOY-07**: ArgoCD Application CRs for dev and prod pointing to manifest paths
- [ ] **DEPLOY-08**: Database provisioned on shared PostgreSQL instance (dev + prod)

### Health & Resilience

- [ ] **RESIL-01**: /health/live endpoint (process-only, no DB) for K8s liveness probe
- [ ] **RESIL-02**: /health/ready endpoint (DB + all registered providers verified) for K8s readiness probe
- [ ] **RESIL-03**: Graceful shutdown with preStop hook and SIGTERM handling for asyncpg pool cleanup
- [ ] **RESIL-04**: Startup data initialization — spell dictionary rebuild and provider data verification on boot

### E2E & Load Testing

- [ ] **TEST-01**: E2E tests for all 5 providers against deployed prod (geocode + validate per provider)
- [ ] **TEST-02**: E2E test of full cascade pipeline end-to-end on deployed prod
- [ ] **TEST-03**: Locust load tests with cold-cache/warm-cache separation, P50/P95/P99 baselines derived
- [ ] **TEST-04**: Logs verified in Loki under load (structured JSON, request_id, trace correlation)
- [ ] **TEST-05**: Traces verified in Tempo under load (request spans, DB spans, provider spans)
- [ ] **TEST-06**: Metrics verified in VictoriaMetrics under load (request rate, latency histograms, error rate)

### Iterative Validation

- [ ] **VAL-01**: Blockers identified during any phase are resolved within that phase before proceeding
- [ ] **VAL-02**: Non-blockers logged and planned for subsequent bug-fix phases
- [ ] **VAL-03**: Final top-to-bottom validation pass covering all categories passes clean

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Access & Networking

- **ACCESS-01**: Tailscale controller for secure internal user access to geo-api
- **ACCESS-02**: Authentication layer for cross-service API calls

### Observability Enhancements

- **OBS-05**: Grafana dashboards pre-built for geo-api (geocode latency, provider hit rates, cache ratios)
- **OBS-06**: Alerting rules for provider failures, latency spikes, error rate thresholds

### Data Operations

- **DATA-01**: Automated GIS data refresh pipeline (scheduled OA/NAD/Tiger updates)
- **DATA-02**: Horizontal pod autoscaling (HPA) based on load test baselines

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Public Ingress/IngressRoute | geo-api is internal-only, accessed by in-cluster services |
| Tailscale controller | Future milestone — not needed for internal service communication |
| Grafana dashboards | Observability validation covers data flow; dashboard creation is a follow-up |
| HPA autoscaling | Baselines must be established first; HPA tuning is a follow-up |
| Helm chart packaging | Plain manifests + Kustomize sufficient for current team size |
| Multi-replica deployment | Single replica sufficient for initial prod; scale after baselines |
| Google Geocoding API | ToS prohibits caching — incompatible with geo-api's core model |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 17 | Pending |
| DEBT-02 | Phase 17 | Pending |
| DEBT-03 | Phase 17 | Pending |
| DEBT-04 | Phase 17 | Pending |
| REVIEW-01 | Phase 18 | Pending |
| REVIEW-02 | Phase 18 | Pending |
| REVIEW-03 | Phase 18 | Pending |
| DEPLOY-01 | Phase 19 | Pending |
| DEPLOY-08 | Phase 19 | Pending |
| RESIL-01 | Phase 20 | Pending |
| RESIL-02 | Phase 20 | Pending |
| RESIL-03 | Phase 20 | Pending |
| RESIL-04 | Phase 20 | Pending |
| DEPLOY-02 | Phase 20 | Pending |
| DEPLOY-03 | Phase 20 | Pending |
| DEPLOY-04 | Phase 20 | Pending |
| DEPLOY-05 | Phase 20 | Pending |
| DEPLOY-07 | Phase 20 | Pending |
| DEPLOY-06 | Phase 21 | Pending |
| OBS-01 | Phase 22 | Pending |
| OBS-02 | Phase 22 | Pending |
| OBS-03 | Phase 22 | Pending |
| OBS-04 | Phase 22 | Pending |
| TEST-01 | Phase 23 | Pending |
| TEST-02 | Phase 23 | Pending |
| TEST-03 | Phase 23 | Pending |
| TEST-04 | Phase 23 | Pending |
| TEST-05 | Phase 23 | Pending |
| TEST-06 | Phase 23 | Pending |
| VAL-01 | Phase 23 | Pending |
| VAL-02 | Phase 23 | Pending |
| VAL-03 | Phase 23 | Pending |

**Coverage:**
- v1.3 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after roadmap creation*
