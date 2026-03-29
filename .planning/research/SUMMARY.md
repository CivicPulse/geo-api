# Project Research Summary

**Project:** CivPulse Geo API — v1.3 Production Readiness & Deployment
**Domain:** Python FastAPI microservice — K8s deployment, observability, CI/CD, E2E and load testing
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Summary

The CivPulse Geo API (geo-api) is a fully-functional, multi-provider geocoding service with a 7-stage cascading address resolution pipeline (spell correction → normalization → cache → exact providers → fuzzy matching → LLM sidecar correction → consensus scoring). The v1.2 application logic is complete with 504 tests. The v1.3 milestone is entirely about hardening and deploying this existing application to a k3s Kubernetes cluster — not about new application features. The correct approach is well-understood: multi-stage Dockerfile with non-root user, split health endpoints, K8s Deployment with Ollama sidecar, GitOps CI/CD via GitHub Actions → GHCR → ArgoCD, and observability through the OpenTelemetry + Grafana stack (Alloy, Loki, Tempo, VictoriaMetrics).

The recommended stack adds exactly 7 runtime Python packages and 1 dev package to the existing project. No existing packages are replaced. OpenTelemetry (6 packages at stable 1.40.0 / 0.61b0 contrib) handles distributed tracing; `prometheus-fastapi-instrumentator` (7.1.0) exposes `/metrics`; `locust` (2.43.3) drives load testing. Cluster-level observability infrastructure (Grafana Alloy, Loki, Tempo, VictoriaMetrics) runs as Helm-deployed K8s workloads and is not a Python dependency. The one notable friction point is Loguru's lack of native OpenTelemetry support — trace context injection requires a custom FastAPI middleware using `logger.contextualize()`, not the standard `opentelemetry-instrumentation-logging` package which only patches stdlib logging.

The primary risks are operational rather than architectural: asyncpg prepared statement conflicts if a connection pooler sits in front of PostgreSQL; connection pool exhaustion during rolling updates; the Ollama sidecar starting before its model is available; read-only filesystem errors from symspellpy dictionary writes and Alembic `__pycache__`; and k3s CoreDNS failing to resolve internal PostgreSQL hostnames. All risks are well-documented and have specific, low-complexity mitigations. The phase ordering must address infrastructure prerequisites (DNS, secrets, DB connectivity) before application deployment — skipping this order is the most common cause of stalled K8s first-deploy attempts.

## Key Findings

### Recommended Stack

The v1.3 stack adds minimal Python dependencies. All observability infrastructure is cluster-level Helm charts, not application code. The Loguru + OpenTelemetry integration requires a custom middleware pattern (MEDIUM confidence) due to Loguru's bypass of stdlib logging — this is the only non-standard integration in the stack. All other packages have HIGH confidence based on official docs and stable release versions.

**Core technologies added in v1.3:**
- `opentelemetry-api` / `opentelemetry-sdk` 1.40.0: Distributed tracing primitives — stable CNCF standard, vendor-neutral, works with Grafana Alloy → Tempo
- `opentelemetry-exporter-otlp-proto-http` 1.40.0: OTLP/HTTP trace export to Alloy — chosen over gRPC to avoid `grpcio` native binary dependency
- `opentelemetry-instrumentation-fastapi/httpx/sqlalchemy` 0.61b0: Auto-instrumentation of all HTTP requests, outbound calls, and DB queries with zero application code changes
- `prometheus-fastapi-instrumentator` 7.1.0: Single-call `/metrics` endpoint with correct route-grouping for path parameters
- `locust` 2.43.3 (dev): Python-native load testing; consistent with project's Python toolchain
- Grafana Alloy (DaemonSet + Deployment): Unified log + trace collector, replaces deprecated Promtail
- Grafana Loki 6.x (single-binary): Structured log aggregation; JSON logs from Loguru with `trace_id` field enable Loki → Tempo correlation
- Grafana Tempo: Distributed tracing backend with native Grafana TraceQL datasource
- VictoriaMetrics `victoria-metrics-k8s-stack` 0.72.5: Prometheus-compatible metrics stack with 5–10x less RAM than Prometheus; scrapes geo-api `/metrics` via pod annotations
- ArgoCD 3.3.x: GitOps deployment controller; v3.0 is EOL — must use 3.1+

**Do not add:**
- `opentelemetry-instrumentation-logging`: Has no effect on Loguru
- `opentelemetry-instrumentation-asyncpg`: Creates duplicate spans over SQLAlchemy instrumentation
- Gunicorn in K8s: Conflicts with HPA scaling model (use single Uvicorn per pod + HPA)
- `k6` or JMeter: Non-Python runtimes; Locust is equivalent for this workload
- `:latest` image tag in K8s manifests: Use immutable SHA-based tags

### Expected Features

The v1.3 feature set is binary: either the service is production-ready or it is not. The feature research identified a clear MVP gate and a validated post-launch hardening set.

**Must have (table stakes — gates production-readiness):**
- Split `/health/live` and `/health/ready` endpoints — K8s probes require distinct signals; current `/health` conflates DB check with liveness
- Startup probe (in addition to liveness + readiness) — GDAL deps + provider init takes 15–30s; startup probe prevents liveness killing a slow-starting pod
- Multi-stage Dockerfile with non-root user and exec-form CMD — prerequisite for K8s security and graceful SIGTERM forwarding
- K8s Deployment manifest (geo-api + Ollama sidecar, resource limits, probes, terminationGracePeriodSeconds, preStop hook)
- K8s ClusterIP Service, K8s Secrets, ArgoCD Application manifests (dev + prod)
- GitHub Actions CI workflow (lint + test) and CD workflow (build + GHCR push + ArgoCD trigger)
- Structured JSON logging (Loguru `serialize=True`) with `service`, `environment`, `version`, `git_commit` fields
- Prometheus `/metrics` endpoint — prerequisite for Grafana dashboards and HPA
- E2E smoke test suite (all 5 providers, cascade, batch, validation endpoints)
- Locust load test baseline (P50/P95/P99 at 30 concurrent users, cold-cache run)

**Should have (post-deploy hardening):**
- OpenTelemetry distributed traces (FastAPI + SQLAlchemy + httpx auto-instrumentation)
- Trace ID injection into Loguru via custom middleware (enables Loki → Tempo log correlation)
- HPA — trigger after load test shows scaling benefit; guesswork without a baseline
- Pod Disruption Budget (`minAvailable: 1`)
- Per-provider latency custom Prometheus metrics and cascade pipeline child spans

**Defer to v2+:**
- ArgoCD Image Updater — low priority while team is small
- External secrets operator (Vault/AWS SSM) — K8s Secrets with etcd encryption sufficient for internal API
- KEDA event-driven autoscaling — CPU-based HPA sufficient for current load
- Grafana alerting rules — define after 2 weeks of baseline data to avoid alert fatigue
- Network policy restricting geo-api ingress to specific namespaces

**Anti-features confirmed (explicitly excluded):**
- Public Ingress / IngressRoute — geo-api is internal-only per PROJECT.md, no auth layer
- Service mesh (Istio/Linkerd) — over-engineering; manual OTel provides equivalent tracing
- Separate log aggregation stack per environment — single Loki with `env` label filter is sufficient

### Architecture Approach

The v1.3 architecture adds no new application components — the 7-stage cascade pipeline (SpellCorrector, FuzzyMatcher, LLMAddressCorrector, ConsensusScorer, CascadeOrchestrator) was designed and implemented in v1.2. The v1.3 architecture changes are entirely in infrastructure: Dockerfile, K8s manifests, CI/CD workflows, and observability wiring. The Ollama standalone Deployment from v1.1 must be converted to a sidecar container in the geo-api Deployment spec (shares Pod network namespace, enabling `http://localhost:11434` communication). Kustomize base + dev/prod overlays is the correct manifest strategy to avoid environment drift.

**Major components (v1.3 infrastructure):**
1. Multi-stage Dockerfile — builder stage (uv + build tools) / runtime stage (non-root appuser, no dev deps, pre-compiled bytecode)
2. K8s Deployment (geo-api + Ollama sidecar) — startup/liveness/readiness probes, preStop hook, resource limits, PVC for Ollama model weights
3. GitHub Actions CI/CD — `ci.yml` (lint + test, all PRs) / `cd.yml` (build + GHCR push + ArgoCD trigger, merge to main only)
4. ArgoCD Applications (dev + prod) — automated sync for dev, manual promotion gate for prod
5. Observability wiring — OTel SDK + Loguru trace context middleware + Prometheus endpoint in app; Alloy + Loki + Tempo + VictoriaMetrics in cluster
6. Kustomize overlays — base manifests + dev overlay + prod overlay

### Critical Pitfalls

1. **asyncpg + PgBouncer prepared statement conflicts** — Confirm PostgreSQL is accessed directly (no transaction-mode pooler). If unavoidable, set `prepared_statement_cache_size=0` in `create_async_engine(connect_args=...)`. Verify before any load test.

2. **Connection pool exhaustion during rolling updates** — Size pool conservatively (`min_size=2, max_size=10` per pod). Set `maxSurge: 1, maxUnavailable: 0` in Deployment strategy. Size PostgreSQL `max_connections` to `(pod_count * max_pool_size * 2) + 20`.

3. **Loguru does not auto-propagate OTel trace context** — `opentelemetry-instrumentation-logging` only patches stdlib logging. Must implement a `logger.configure(patcher=...)` that calls `trace.get_current_span()` on every log record, plus a FastAPI middleware to ensure a valid span exists before any log call.

4. **Ollama sidecar ready before model is available** — `/api/tags` returns HTTP 200 with empty model list during pull. Replace HTTP-ping check with body-parsing check that confirms the model name is present in the response. Use init container or postStart hook to pre-pull the model. Store model weights on a PVC (not emptyDir).

5. **k3s CoreDNS does not resolve internal PostgreSQL hostname** — k3s CoreDNS defaults to forwarding to `8.8.8.8`, bypassing internal DNS. Patch CoreDNS ConfigMap to forward to the internal nameserver. Validate with `kubectl run dns-test` before deploying the app.

6. **Read-only root filesystem breaks symspellpy and Alembic** — Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPYCACHEPREFIX=/tmp/pycache`. Mount `emptyDir` at `/tmp` and `/app/data/`. Bake spell dictionary into the Docker image rather than writing it at runtime.

7. **Graceful shutdown race — SIGTERM before kube-proxy endpoint removal** — Add `preStop: exec: command: ["sleep", "5"]` lifecycle hook. Set `terminationGracePeriodSeconds: 60`. Ensure entrypoint script uses `exec uvicorn ...` (not shell-form invocation) so SIGTERM reaches uvicorn, not bash.

8. **Load test cache bias inflates P95 numbers** — Run two explicit modes: cold-cache baseline (clear `geocoding_results` before run) and warm-cache steady-state. Use 500+ unique addresses. Report both P95 values; the cold-cache P95 is the authoritative performance baseline.

9. **Alembic migration race condition with multi-replica init containers** — Two pods starting simultaneously both run `alembic upgrade head`. Use PostgreSQL advisory locks in `env.py`, or run migrations as a K8s Job with `parallelism: 1` before the Deployment starts.

## Implications for Roadmap

Based on combined research, the phase structure must respect hard dependency chains. Infrastructure prerequisites (DNS, secrets, DB connectivity) must be validated before any application deployment. The observability stack should be split into a baseline tier (JSON logs, `/metrics`) that ships with the initial deployment, and an advanced tier (OTel traces, log-trace correlation) that is added after the base deployment is validated.

### Phase 1: Infrastructure Prerequisites
**Rationale:** CoreDNS patching, K8s Secrets creation, and PostgreSQL connectivity validation must be confirmed before any application pod can start. These are cluster-level operations that unblock everything downstream. Skipping this phase is the most common cause of stalled K8s first-deploys.
**Delivers:** Cluster ready to receive geo-api workloads; DB hostname resolves from inside pods; Secrets exist in both namespaces; asyncpg pool mode confirmed (no transaction-mode pooler in front of PG); k3s StorageClass verified for Ollama PVC
**Addresses:** `K8s Secrets` prerequisite from FEATURES.md
**Avoids:** Pitfalls 1 (asyncpg pooler), 8 (k3s CoreDNS)

### Phase 2: Dockerfile Hardening
**Rationale:** The multi-stage Dockerfile is a prerequisite for K8s security policies and for GHCR image availability. It establishes the non-root user and exec-form CMD required for graceful shutdown. Cannot deploy to K8s without a production image.
**Delivers:** Production Docker image pushed to GHCR; non-root `appuser`; no dev deps in runtime stage; pre-compiled bytecode; `exec uvicorn` entrypoint
**Uses:** uv multi-stage Dockerfile pattern from STACK.md (Hynek Schlawack canonical pattern, with `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`, `UV_PYTHON_DOWNLOADS=never`)
**Avoids:** Pitfalls 5 (read-only FS — `PYTHONDONTWRITEBYTECODE=1`, emptyDir mounts), 7 (graceful shutdown — exec-form CMD)

### Phase 3: Health Endpoints + Core Application Manifests
**Rationale:** Split health endpoints are the prerequisite for K8s probes. The K8s Deployment (with probes, sidecar, resource limits, preStop hook) is the core deliverable of this milestone. Ollama sidecar conversion from standalone Deployment to sidecar happens here.
**Delivers:** `/health/live` and `/health/ready` endpoints; K8s Deployment manifest with startup + liveness + readiness probes; Ollama sidecar with PVC for model weights (body-parsing availability check); ClusterIP Service; Kustomize overlays (dev + prod)
**Addresses:** All P1 K8s deployment table-stakes features from FEATURES.md
**Avoids:** Pitfalls 2 (pool exhaustion — `min_size=2, max_size=10`, `maxSurge: 1`), 4 (Ollama model readiness — parse `/api/tags` body), 6 (SIGTERM race — preStop sleep hook), 9 (provider registration timing — startup probe), 12 (Alembic race — advisory lock or K8s Job)

### Phase 4: CI/CD Pipeline
**Rationale:** Repeatable automated deployments are the production operations foundation. Cannot run E2E or load tests against a deployed environment without this. The ArgoCD Image Updater vs. manifest-commit decision must be made here to avoid the git push race condition.
**Delivers:** `ci.yml` (ruff + pytest, all PRs), `cd.yml` (build + GHCR push + ArgoCD trigger, merge to main only), ArgoCD Application manifests (dev auto-sync, prod manual gate), Trivy vulnerability scan in CI
**Addresses:** All CI/CD table-stakes and differentiator features from FEATURES.md
**Avoids:** Pitfall 7 (ArgoCD + CI race condition — use ArgoCD Image Updater or PR-based manifest commit, not concurrent direct pushes)

### Phase 5: Baseline Observability (JSON Logs + Metrics)
**Rationale:** Structured JSON logging and the Prometheus `/metrics` endpoint are prerequisites for Grafana dashboards, HPA, and meaningful load test analysis. These are low-complexity changes that ship with the initial deployment — adding them here means load test results in Phase 6 are immediately visible in Grafana without a second deploy cycle.
**Delivers:** JSON logs in production (Loguru `serialize=True`), `service`/`env`/`version`/`git_commit` fields on every log line, `/metrics` endpoint, VictoriaMetrics scraping via pod annotations, Grafana dashboards for request rate and latency
**Uses:** `prometheus-fastapi-instrumentator` 7.1.0 (single `Instrumentator().instrument(app).expose(app)` call)

### Phase 6: E2E and Load Testing
**Rationale:** Validates the deployed service works end-to-end against all 5 providers in the real K8s environment and establishes the authoritative performance baseline. Must run after the full deployment (Phases 1–5) is stable.
**Delivers:** pytest E2E suite (all 5 providers, cascade, batch, validation); Locust cold-cache P50/P95/P99 baseline at 10/30/60 concurrent users; HPA scaling validation; monitoring validation via Grafana dashboard screenshot (Playwright MCP)
**Addresses:** All E2E and load testing features from FEATURES.md
**Avoids:** Pitfall 10 (cache bias — explicit cold-cache methodology, 500+ unique address corpus, `cache_hit` as a Grafana label)

### Phase 7: Advanced Observability (OTel Traces + Log Correlation)
**Rationale:** OpenTelemetry instrumentation and the Loguru trace context middleware are placed after the base deployment is validated. The Loguru + OTel integration uses a community-pattern (MEDIUM confidence) — safer to add after simpler observability is confirmed working. Traces are most valuable when debugging production issues surfaced by baseline metrics.
**Delivers:** OTel SDK + auto-instrumentation (FastAPI, SQLAlchemy, httpx), Loguru trace context patcher middleware, Grafana Loki → Tempo log correlation (clickable trace links), cascade pipeline child spans
**Uses:** All 6 OTel packages from STACK.md; Loguru `configure(patcher=...)` pattern (custom, not `opentelemetry-instrumentation-logging`)
**Avoids:** Pitfall 3 (Loguru/OTel disconnect — custom `logger.configure(patcher=add_otel_context)` approach, validated by checking `trace_id` in Loki before marking complete)

### Phase Ordering Rationale

- **Infrastructure before application:** CoreDNS and DB connectivity must be confirmed before application pods can start. This dependency (Pitfall 8) is frequently skipped and causes hours of debugging on first K8s deploys.
- **Dockerfile before manifests:** The K8s Deployment references the GHCR image. The production image must exist before manifests can be tested.
- **Health endpoints before probes:** K8s probes reference `/health/live` and `/health/ready`. These must exist in the application before the Deployment manifests are applied.
- **Baseline observability with initial deploy (not after):** JSON logs and `/metrics` are trivial changes. Shipping them in Phase 5 (before load testing) means Phase 6 results are immediately visible in Grafana — no second deploy cycle needed.
- **OTel last:** The custom Loguru/OTel middleware is the most complex integration and is MEDIUM confidence. Deferring it to Phase 7 avoids blocking the core deployment on a non-standard pattern.
- **CI/CD before E2E:** E2E tests run against a deployed environment. The CI/CD pipeline is the mechanism for deploying; Phase 4 must precede Phase 6.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (CI/CD):** The decision between ArgoCD Image Updater and direct manifest commit strategy must be made explicitly — they are mutually exclusive for the same image. Team size and concurrent build frequency should drive the decision. Needs a decision point documented before implementation.
- **Phase 7 (Advanced Observability):** The Loguru + OTel custom middleware is MEDIUM confidence (community pattern, no official first-party support). During planning, verify the `logger.configure(patcher=...)` approach against the Loguru version in use and plan a verification step (confirm `trace_id` in Loki before marking phase complete).

Phases with standard patterns (skip research-phase):
- **Phase 2 (Dockerfile):** Well-documented uv multi-stage pattern. The exact Dockerfile template is already specified in STACK.md.
- **Phase 3 (K8s Manifests):** Standard FastAPI + K8s probe patterns. All resource limit values, probe timing, and sidecar config are specified in FEATURES.md and PITFALLS.md.
- **Phase 5 (Baseline Observability):** `prometheus-fastapi-instrumentator` is a single-call integration. Loguru `serialize=True` is a one-line config change.
- **Phase 6 (E2E/Load Testing):** Locust test structure and cold-cache methodology are fully specified in STACK.md and PITFALLS.md respectively.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | OTel packages: official PyPI + docs. Locust: official docs. Dockerfile: Hynek Schlawack's canonical uv guide. Exception: Loguru/OTel integration is MEDIUM (community pattern, no official first-party support) |
| Features | HIGH | K8s patterns, GitHub Actions/GHCR/ArgoCD verified against current docs. Loguru/OTel friction confirmed via official OTel Python issue tracker (#3615) |
| Architecture | HIGH | Based on direct codebase inspection. v1.2 pipeline is implemented and tested. v1.3 is infrastructure-only |
| Pitfalls | HIGH | asyncpg/K8s lifecycle: official asyncpg FAQ + post-mortems. Graceful shutdown: well-documented K8s pattern. Exceptions: ArgoCD race (MEDIUM — GitHub issue + community), Ollama startup (MEDIUM — community patterns), cache bias (LOW — general load testing literature) |

**Overall confidence:** HIGH

### Gaps to Address

- **PostgreSQL connection mode:** Research assumes no transaction-mode PgBouncer in front of PostgreSQL. Must be confirmed in Phase 1. If a pooler is present, `prepared_statement_cache_size=0` is required before any load testing.
- **Loguru + OTel patcher implementation:** Verify the `logger.configure(patcher=add_otel_context)` pattern against the specific Loguru version in use during Phase 7. Test end-to-end by confirming `trace_id` appears in Loki-captured logs for a traced request.
- **Ollama model pre-pull strategy:** The init container vs. postStart hook decision for model pre-pull is left to Phase 3 planning. Both work; the K8s Job approach is more robust for initial cluster setup.
- **ArgoCD Image Updater vs. manifest commit:** Must be decided explicitly in Phase 4 planning. They are mutually exclusive and the choice affects CI workflow structure.
- **k3s StorageClass for Ollama PVC:** Assumed to be `local-path` (k3s default). Verify with `kubectl get storageclass` during Phase 1 before writing PVC manifests.

## Sources

### Primary (HIGH confidence)
- OpenTelemetry Python SDK — PyPI stable releases 1.40.0 / 0.61b0; official OTel Python docs
- Locust 2.43.3 — official Locust docs (Feb 12, 2026 release)
- uv multi-stage Dockerfile — Hynek Schlawack's "Production-Ready Python Docker Containers with uv" (official uv docs reference)
- asyncpg prepared statement caching — official asyncpg FAQ + GitHub issues
- VictoriaMetrics — `victoria-metrics-k8s-stack` Helm chart 0.72.5 (March 16, 2026 release notes)
- ArgoCD 3.3.x — official docs; v3.0 EOL confirmed Feb 2026
- prometheus-fastapi-instrumentator 7.1.0 — PyPI + official README
- Grafana Loki 6.x Helm chart — `grafana-community/helm-charts` (chart moved from `grafana/helm-charts` at 6.55.0)

### Secondary (MEDIUM confidence)
- Loguru + OTel trace context integration — Dash0 community guide; OpenTelemetry Python GitHub issue #3615; Loguru `contextualize()` documented API
- ArgoCD Image Updater vs. CI manifest commit race condition — ArgoCD GitHub issue + community patterns
- Ollama K8s startup readiness — community K8s deployment guides for Ollama sidecar patterns
- Grafana Alloy `loki.source.kubernetes` — Grafana Alloy docs (replaces deprecated Promtail)

### Tertiary (LOW confidence)
- Geocoding load test cache bias methodology — general load testing literature; geocoding-specific pattern based on caching architecture review (not external benchmark source)

---
*Research completed: 2026-03-29*
*Ready for roadmap: yes*
