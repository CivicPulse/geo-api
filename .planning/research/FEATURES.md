# Feature Research

**Domain:** Python FastAPI microservice — production deployment, observability, CI/CD, E2E and load testing
**Researched:** 2026-03-29
**Confidence:** HIGH (K8s patterns, GitHub Actions/GHCR/ArgoCD workflows, OpenTelemetry FastAPI instrumentation verified against official docs and current community practice; Loguru/OTel friction confirmed via official OTel Python issue tracker; Locust/k6 patterns verified against current docs)

---

## Context: What This Milestone Adds

This research covers v1.3: hardening and deploying an existing, fully-functional geocoding API to Kubernetes (civpulse-dev + civpulse-prod). The application is already built and tested in Docker Compose with 504 tests.

**What already exists (do not rebuild):**
- Single-stage Dockerfile with uv, GDAL system deps, and `bash scripts/docker-entrypoint.sh` CMD
- Docker Compose dev environment (PostGIS, optional Ollama sidecar via `--profile llm`)
- Basic `/health` endpoint (DB connectivity check + git commit + version)
- Loguru for logging (`LOG_LEVEL` env var)
- Partial K8s manifests: Ollama Deployment, PVC, Service only
- 504 unit/integration tests (11 known fixture failures)
- Pydantic Settings with env-var config

**What is missing and must be built:**
- Multi-stage Dockerfile (production hardening: non-root user, no dev deps, minimal image)
- K8s manifests for geo-api itself (Deployment, ClusterIP Service, HPA, resource limits)
- ArgoCD Application manifests
- GitHub Actions CI/CD pipeline (build → push GHCR → trigger ArgoCD sync)
- Structured JSON logging with trace-ID correlation
- OpenTelemetry instrumentation (traces to Tempo, logs to Loki via Alloy)
- Prometheus metrics endpoint
- Separate `/health/ready` and `/health/live` endpoints for K8s probes
- Graceful shutdown with SIGTERM handling
- E2E test suite against deployed environment (all 5 providers)
- Load/performance baseline (Locust): P50/P95/P99 targets
- HPA scaling validation

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are the non-negotiable baseline for any K8s-deployed Python microservice. Missing any of these means the service is not production-ready regardless of what the app logic does.

#### K8s Deployment

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Separate `/health/live` and `/health/ready` endpoints | K8s requires distinct liveness and readiness signals; conflating them causes unnecessary pod restarts during startup or provider initialization | LOW | Current `/health` endpoint mixes DB check with metadata — split it: `/health/live` = always 200 if process is running; `/health/ready` = DB connected + providers loaded. Existing code can be refactored in < 1 hour |
| K8s readiness probe on `/health/ready` | Without this, pods receive traffic before providers are registered and spell dictionaries are loaded — startup takes ~10s with full provider init | LOW | `initialDelaySeconds: 15`, `periodSeconds: 10`, `failureThreshold: 3`. The existing lifespan handler loads providers, spell correctors, and checks Ollama — this takes time and must block traffic |
| K8s liveness probe on `/health/live` | Without this, hung or deadlocked pods continue receiving traffic indefinitely | LOW | `initialDelaySeconds: 30`, `periodSeconds: 30`, `failureThreshold: 3`. Must NOT query DB — liveness should only confirm the process responds |
| Startup probe | Prevents liveness killing a slow-starting pod (GDAL deps + provider init can take 15–30s) | LOW | `failureThreshold: 20`, `periodSeconds: 5` = 100s startup budget. K8s only begins liveness checks after startup probe succeeds |
| `terminationGracePeriodSeconds` + preStop sleep | Without this, K8s sends SIGTERM and immediately removes the pod from Service endpoints, cutting off in-flight requests | LOW | Set `terminationGracePeriodSeconds: 60`. Add `preStop: exec: command: ["sleep", "10"]` to give the load balancer time to drain connections before uvicorn begins shutdown |
| Resource requests and limits | Without limits, a single mis-behaving pod can starve other services on the node; without requests, K8s scheduler cannot make good placement decisions | LOW | CPU: request=250m limit=1000m; Memory: request=512Mi limit=1Gi. The cascade pipeline with LLM disabled is CPU-light; LLM-enabled needs more memory headroom. These are starting values — tune from metrics after load testing |
| Non-root container user | CIS Kubernetes Benchmark and most cluster policies require non-root containers; root containers are a significant security finding | LOW | Add `RUN addgroup --system appuser && adduser --system --group appuser` to Dockerfile, then `USER appuser`. uv's `.venv` must be readable by this user |
| Multi-stage Dockerfile | Single-stage builds include build tools, uv cache artifacts, and dev dependencies in the final image; this increases attack surface and image size | MEDIUM | Builder stage: install deps with uv. Runtime stage: copy only `.venv` and `src/`. Separate GDAL system libs (needed at runtime by fiona) from build tools (not needed at runtime). Current Dockerfile is single-stage — needs rework |
| ClusterIP Service manifest | Needed for other cluster services to reach geo-api | LOW | Port 8000. Already planned per PROJECT.md. No Ingress — internal-only |
| ArgoCD Application manifest | Needed for GitOps-driven deployments | LOW | One Application per environment (civpulse-dev, civpulse-prod). Points at K8s manifests path in git repo |

#### Observability

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Structured JSON logs | Plain text logs are unsearchable at scale in Loki; structured logs with consistent key names enable query filters like `{service="geo-api"} \| json \| level="ERROR"` | LOW | Loguru supports `serialize=True` for JSON output. Configure in the logging setup, keyed on `ENVIRONMENT` — JSON in production, human-readable in dev. Output to stdout only (let Alloy collect) |
| Log level via env var | Already exists (`LOG_LEVEL`) — keep it. K8s configmap can adjust level without image rebuild | LOW | Already implemented |
| Request ID / trace ID in every log line | Without this, correlating a specific failed geocode request across log lines is impossible in Loki | MEDIUM | Use OpenTelemetry auto-instrumentation to generate trace IDs per request. Inject trace_id + span_id into Loguru context via middleware. Loguru lacks first-class OTel support — requires a custom FastAPI middleware that extracts `trace_id` from the active span and calls `logger.bind(trace_id=..., span_id=...)` |
| Prometheus `/metrics` endpoint | Needed for HPA custom metrics, Grafana dashboards, and alerting on request rate / error rate | LOW | Use `prometheus-fastapi-instrumentator` — one-line integration. Exposes `http_requests_total`, `http_request_duration_seconds` labeled by path, method, status. Mount at `/metrics` |
| Service name + environment labels in logs | Log queries in Loki require label-based filtering; without consistent `service` and `env` labels, multi-service Loki queries are painful | LOW | Add `service`, `environment`, `version`, `git_commit` as structured fields on every log line. Loguru `logger.configure(extra=...)` sets these once at startup |

#### CI/CD

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Automated container build on push to main | Manual image builds are error-prone and prevent reliable deployments | LOW | GitHub Actions workflow: `docker/build-push-action` + `docker/metadata-action` for tag generation |
| Push to GHCR on merge to main | GHCR is the container registry; ArgoCD watches it | LOW | `ghcr.io/civpulse/geo-api:${{ github.sha }}` as the image tag. Also tag `latest` |
| Run tests before build | Never push a broken image | LOW | `pytest` step before docker build step in the CI workflow |
| ArgoCD sync trigger on new image | Closes the CI→CD gap | LOW | Two approaches: (1) ArgoCD Image Updater polls GHCR and updates the manifest in git, or (2) GitHub Actions commits the updated image tag to the manifests repo directly. Option 2 is simpler for a small team |

#### E2E Testing

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Provider smoke test (all 5 providers) | Deployment validation must confirm each provider returns results in the deployed environment, since providers are conditionally registered based on loaded data | MEDIUM | pytest-based E2E test suite targeting the deployed API via port-forward or NodePort. Test each provider with a known Macon-Bibb address from the existing E2E test corpus |
| Single-address geocode E2E (cascade) | Validates the full pipeline in the real environment, including consensus and auto-set behavior | LOW | Use the 4 known-good Macon addresses from Issue #1 corpus |
| Batch endpoint E2E | Batch endpoint behavior must be validated end-to-end | LOW | Submit a batch of 10 addresses; validate all return results |
| Validation endpoint E2E | The validation pipeline has a known scourgify limitation; must confirm behavior in production | LOW | Submit known-good and known-malformed addresses; assert response structure |

---

### Differentiators (Competitive Advantage)

Features beyond the bare minimum that significantly improve operational quality, debuggability, or reliability.

#### K8s Deployment

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| HPA (Horizontal Pod Autoscaler) | geo-api is I/O-bound during geocoding (DB queries, external Census API calls); HPA on CPU/request-rate allows the cluster to scale under load without manual intervention | MEDIUM | Start with CPU-based HPA: `targetCPUUtilizationPercentage: 70`, `minReplicas: 2`, `maxReplicas: 6`. Two replicas minimum ensures high availability. At 2 replicas and ClusterIP load balancing, request distribution is not perfectly even — acceptable for internal use |
| Pod Disruption Budget (PDB) | Without a PDB, node maintenance or drain can take down all replicas simultaneously | LOW | `minAvailable: 1`. Simple manifest, high value. Ensures at least one pod is always available during voluntary disruptions |
| ConfigMap for non-secret settings | Externalizes config for per-environment tuning without image rebuilds | LOW | `cascade_enabled`, `max_batch_size`, `exact_match_timeout_ms`, etc. → ConfigMap. Secrets (DB credentials) → K8s Secret or external secrets operator |
| Ollama as a sidecar (not a separate Deployment) | For the geocoding use case, the LLM is request-scoped and not shared across geo-api instances; a sidecar model means the LLM is co-located with the consumer, eliminating network latency and auth | HIGH | This is the PROJECT.md requirement. Sidecar container in the geo-api Pod spec. The existing K8s Ollama Deployment manifests should be converted to a sidecar in the geo-api Deployment |

#### Observability

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| OpenTelemetry distributed traces (Tempo) | Traces show the full cascade pipeline as a tree of spans — which provider was called, how long each took, where consensus scoring ran. Essential for diagnosing P95 > 3s cases | MEDIUM | `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-sqlalchemy` + `opentelemetry-instrumentation-httpx`. Configure OTLP exporter pointing to Grafana Alloy. Alloy forwards to Tempo. The trace_id generated here is the same ID injected into Loguru |
| Log→Trace correlation (Loki → Tempo) | In Grafana, a log line with a trace_id becomes a clickable link to the full trace — eliminates manual copy-paste of IDs when debugging | MEDIUM | Requires: (1) trace_id in log lines as a structured field; (2) Loki datasource in Grafana configured with a derived field pointing to Tempo. Alloy handles log collection; the trace_id field name must match exactly |
| Per-provider latency metrics | Prometheus histogram of geocoding duration by provider and stage. Identifies which providers are consistently slow under load | LOW | Custom Prometheus metric: `geocoding_duration_seconds{provider="census", stage="exact_match"}`. Integrate into the cascade orchestrator's existing stage telemetry |
| Cascade pipeline span per stage | OpenTelemetry spans for each cascade stage (normalize, spell-correct, exact match, fuzzy, LLM, consensus) make it trivial to find which stage caused a slow request | MEDIUM | Wrap each stage in `with tracer.start_as_current_span("cascade.exact_match"):`. The FastAPI auto-instrumentation handles the root span; child spans are manual |

#### CI/CD

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Image vulnerability scan in CI (Trivy) | Catches CVEs in the base image or Python deps before deployment | LOW | `aquasecurity/trivy-action` in GitHub Actions. Run after build, before push. Fail build on CRITICAL severity. This is a 5-line addition to the workflow |
| Ruff lint + type check gate in CI | Prevents regressions from landing on main without automated enforcement | LOW | Already use ruff locally per global CLAUDE.md conventions. Add `ruff check` + `ruff format --check` as a CI gate before pytest |
| Separate CI (tests + lint) and CD (build + push) workflows | Decouples test validation from deployment; CI can run on PRs while CD only runs on merge to main | LOW | Two `.github/workflows/` files: `ci.yml` (lint + test, runs on all PRs and pushes) and `cd.yml` (build + push + deploy, runs on merge to main only) |
| Environment-specific ArgoCD Applications | Separate ArgoCD Applications for dev and prod with different resource limits, replica counts, and image tags; prod requires manual sync approval | MEDIUM | ArgoCD `syncPolicy: automated` for dev (auto-sync on image update); `syncPolicy: {} + spec.sync.automated: false` for prod (manual promotion required). This is a GitOps best practice, not just a nice-to-have for a production service |

#### E2E and Load Testing

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Performance baseline establishment (P50/P95/P99) | Without a baseline, you cannot detect regressions or validate HPA effectiveness; the P95 < 3s pipeline target from v1.2 needs production validation | MEDIUM | Use Locust for load generation. Establish baseline at: 10 concurrent users, 30 concurrent users, 60 concurrent users. Record P50/P95/P99 per endpoint. Target: single-address geocode P95 < 3s at 30 concurrent users |
| HPA scaling validation under load | Must confirm HPA triggers and new pods come up before the cluster saturates | MEDIUM | Run Locust ramp test while watching `kubectl get hpa -w`. Confirm pod count increases from 2 → 4+ as load rises. Confirm pod count decreases after load drops. This validates both the HPA config and the readiness probe timing |
| Provider-specific E2E with known fixtures | Five providers must each resolve known addresses independently; cascade masking a broken individual provider is a real risk | MEDIUM | Bypass the cascade for these tests using a provider-specific query parameter (if available) or by directly calling the provider health/debug endpoints. If no bypass exists, add a `?provider=census` debug parameter — internal-only, not part of the public API contract |
| Monitoring validation under load | Confirm that Grafana dashboards show correct metrics during load test | LOW | Run Locust for 5 minutes at 30 users; check Grafana manually (or via Playwright MCP) to confirm request rate, latency histograms, and error rate are updating correctly |

---

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Public Ingress / IngressRoute | Seems obvious for an API | geo-api is internal-only per PROJECT.md; adding Ingress expands the attack surface for a service with no auth layer; it would be accessible from the internet with no authentication | Stick with ClusterIP. Debug access via `kubectl port-forward` or a dedicated NodePort. This is explicit in PROJECT.md |
| Authentication layer | "Every API should have auth" | PROJECT.md explicitly excludes auth as out of scope; adding it now means every consumer (run-api, vote-api) must be updated; it is a cross-cutting concern that should be addressed at the service mesh or network policy level, not application level | Network-level security (K8s NetworkPolicy) to restrict which namespaces can reach geo-api |
| Sidecar proxy (Istio, Linkerd) | "Service mesh gives you tracing for free" | Service mesh adds significant operational complexity, CPU overhead per pod, and a new failure domain; for a small internal deployment with one team, it is over-engineering; OpenTelemetry instrumentation provides equivalent tracing without the sidecar overhead | Manual OTel instrumentation. Lower complexity, equivalent observability |
| Distributed tracing on every DB query | "Maximum visibility" | SQLAlchemy instrumentation creates a span for every query, including the background health checks that run every 30s; this floods Tempo with low-value spans and significantly increases trace storage cost | Instrument SQLAlchemy, but use a sampling rate (e.g., 10%) for routine queries; sample 100% of failed requests and requests with P95+ latency |
| Separate log aggregation stack per environment | "Dev and prod logs should not mix" | A single Loki instance with `environment` label filtering is sufficient; separate stacks double the operational surface and cost for a small deployment with low log volume | Use Grafana Alloy with `environment` labels. Filter by `{env="prod"}` in Loki queries |
| k6 for load testing (over Locust) | k6 is more efficient for very high concurrency | geo-api is I/O-bound and unlikely to need 100k+ virtual users; Locust's Python-based user scripts are simpler to write and maintain by developers already working in Python; k6 requires JavaScript/TypeScript scripting | Locust. If throughput requirements exceed what Locust can generate on a single machine, switch to distributed Locust mode (Locust has native K8s distributed mode) |
| Canary or blue-green deployments | "Zero-downtime deployments" | K8s rolling update strategy with minReadySeconds and appropriate readiness probes already provides near-zero-downtime deployments without additional tooling; canary deployments require traffic splitting infrastructure that does not exist yet | Use K8s `strategy: RollingUpdate` with `maxUnavailable: 0` and `maxSurge: 1`. Combined with readiness probes, this is effectively zero-downtime |
| Secrets management via external secrets operator (Vault, AWS SSM) | "Production secrets should not be in K8s Secrets" | Valid long-term concern, but adding an external secrets operator before the service is deployed at all is premature; K8s Secrets with etcd encryption-at-rest is sufficient for an internal API | Use K8s Secrets for v1.3. Document this as a v2 item if the cluster adds stricter compliance requirements |
| Grafana alerting rules | "Alerts when the service goes down" | Defining meaningful alert thresholds requires post-deployment baseline data; alerting on CPU > 80% before you know what normal CPU looks like produces false positives and alert fatigue | Establish baselines first (from load testing). Define alert thresholds in a subsequent phase |

---

## Feature Dependencies

```
[Structured JSON Logging]
    └──requires──> [Loguru serialize=True config]
    └──enhances──> [Grafana Alloy log collection]

[Trace ID in Logs]
    └──requires──> [OpenTelemetry instrumentation (FastAPI, SQLAlchemy, httpx)]
    └──requires──> [Custom Loguru middleware to inject trace_id per request]
    └──enables──> [Log→Trace correlation in Grafana (Loki → Tempo)]

[OpenTelemetry traces]
    └──requires──> [opentelemetry-instrumentation-fastapi]
    └──requires──> [opentelemetry-instrumentation-sqlalchemy]
    └──requires──> [opentelemetry-instrumentation-httpx]
    └──requires──> [OTLP exporter → Grafana Alloy → Tempo]
    └──enables──> [Cascade pipeline spans (child spans per stage)]

[Prometheus /metrics endpoint]
    └──requires──> [prometheus-fastapi-instrumentator]
    └──enables──> [HPA on custom request-rate metric]
    └──enables──> [Grafana dashboards for request rate, latency]

[/health/live + /health/ready split]
    └──requires──> [Refactor existing /health endpoint]
    └──enables──> [K8s liveness probe]
    └──enables──> [K8s readiness probe]
    └──enables──> [Startup probe]

[Graceful shutdown]
    └──requires──> [preStop hook in K8s Deployment spec]
    └──requires──> [terminationGracePeriodSeconds: 60]
    └──requires──> [Uvicorn JSON exec CMD (not shell form) in Dockerfile]

[Multi-stage Dockerfile]
    └──requires──> [Non-root user creation in builder stage]
    └──enables──> [Reduced image size and attack surface]
    └──enables──> [Trivy vulnerability scan in CI]

[K8s Deployment manifest (geo-api)]
    └──requires──> [Multi-stage Dockerfile]
    └──requires──> [/health/live + /health/ready endpoints]
    └──requires──> [GHCR image available]
    └──requires──> [K8s Secrets for DB credentials]
    └──includes──> [Ollama sidecar container]
    └──includes──> [Resource requests + limits]

[HPA]
    └──requires──> [K8s metrics-server installed in cluster]
    └──requires──> [Resource requests defined in Deployment]
    └──optionally-requires──> [/metrics endpoint for custom metric scaling]

[ArgoCD Application]
    └──requires──> [K8s manifests committed to git]
    └──requires──> [ArgoCD installed in cluster]
    └──enables──> [GitOps deployment workflow]

[GitHub Actions CD workflow]
    └──requires──> [GHCR credentials (GITHUB_TOKEN)]
    └──requires──> [Multi-stage Dockerfile]
    └──triggers──> [ArgoCD sync (via Image Updater or manifest commit)]

[GitHub Actions CI workflow]
    └──requires──> [ruff, pytest]
    └──includes──> [Trivy scan after build]
    └──must-pass-before──> [CD workflow]

[E2E test suite]
    └──requires──> [Deployed environment accessible via port-forward or NodePort]
    └──requires──> [All 5 providers' data loaded in target environment]
    └──uses──> [httpx or pytest + requests against real deployment]

[Load testing (Locust)]
    └──requires──> [Deployed environment accessible]
    └──requires──> [/metrics endpoint for correlation]
    └──enables──> [HPA scaling validation]
    └──enables──> [P50/P95/P99 baseline documentation]

[Monitoring validation under load]
    └──requires──> [Load testing running]
    └──requires──> [Grafana dashboards configured]
    └──uses──> [Playwright MCP for dashboard screenshot verification]
```

### Dependency Notes

- **Health endpoint split is a prerequisite for everything K8s:** The current `/health` endpoint does a DB query — using it as a liveness probe means a DB outage kills all pods (liveness probe fails → restart loop). Split into `/health/live` (no DB check) and `/health/ready` (DB check + provider check) before any K8s deployment.

- **Graceful shutdown requires exec form CMD in Dockerfile:** The current Dockerfile uses `CMD ["bash", "scripts/docker-entrypoint.sh"]`. If the entrypoint script invokes uvicorn via shell form (`uvicorn ...`) rather than exec form (`exec uvicorn ...`), SIGTERM goes to bash (PID 1) not uvicorn. Bash does not forward signals. The entrypoint script must use `exec uvicorn ...` as its last line.

- **OTel trace ID injection into Loguru requires custom middleware:** Loguru does not automatically pick up OTel trace context. Unlike Python's `logging` module (which OTel patches to add trace_id to LogRecords automatically), Loguru requires a FastAPI middleware that extracts the current span's trace_id and calls `logger.bind(trace_id=..., span_id=...)` for the duration of each request. This is a known gap in the OTel Python ecosystem (confirmed in opentelemetry-python issue #3615).

- **Ollama sidecar conversion:** The existing `k8s/ollama-deployment.yaml` is a standalone Deployment. For v1.3, it must become a sidecar container in the geo-api Deployment spec. The sidecar shares the Pod's network namespace, so the `OLLAMA_URL=http://localhost:11434` config works without change. The PVC for model storage must move to a volumeMount in the geo-api Pod.

- **HPA requires metrics-server:** CPU-based HPA depends on `metrics-server` being installed in the cluster. If the cluster does not have it, HPA will not work. Verify `kubectl top pods` works before adding HPA manifests.

- **E2E test suite requires data to be pre-loaded:** The E2E tests assume that OA, NAD, and Macon-Bibb data are loaded in the target environment. Provider availability is conditional on data presence (`_oa_data_available`, `_nad_data_available`, etc.). E2E tests must either skip gracefully when a provider is not registered, or there must be a data loading step as part of the deployment runbook.

---

## MVP Definition

### Launch With (v1.3 milestone — all required before "production-ready")

- [ ] Multi-stage Dockerfile with non-root user and exec-form CMD — prerequisite for K8s security and graceful shutdown
- [ ] Split `/health/live` and `/health/ready` endpoints — prerequisite for K8s probes
- [ ] K8s Deployment manifest for geo-api with readiness + liveness + startup probes, resource limits, terminationGracePeriodSeconds, preStop hook — without this there is no K8s deployment
- [ ] Ollama sidecar in the geo-api Deployment spec — PROJECT.md requirement
- [ ] K8s ClusterIP Service manifest for geo-api — without this other services cannot reach it
- [ ] K8s Secrets for DB credentials (dev + prod) — prerequisite for Deployment
- [ ] ArgoCD Application manifests (dev + prod) — prerequisite for GitOps workflow
- [ ] GitHub Actions CI workflow (lint + test) — prevents broken deployments
- [ ] GitHub Actions CD workflow (build + GHCR push + ArgoCD trigger) — enables repeatable deployments
- [ ] Structured JSON logging (Loguru serialize=True, production env only) — prerequisite for Loki queries
- [ ] Service/environment labels in all logs — prerequisite for multi-service Loki filtering
- [ ] Prometheus `/metrics` endpoint — prerequisite for Grafana dashboards and HPA
- [ ] E2E smoke test suite (all 5 providers, cascade, batch, validation) — validates deployment is functional
- [ ] Load test baseline (Locust, P50/P95/P99 at 30 concurrent users) — validates the service is performant

### Add After Deployment Validated (v1.3 hardening)

- [ ] OpenTelemetry traces (FastAPI + SQLAlchemy + httpx instrumentation) — trigger: first time debugging a production issue; traces make root cause analysis much faster
- [ ] Trace ID injection into Loguru (custom middleware) — trigger: OTel instrumentation is in place; adds the correlation between logs and traces
- [ ] HPA (Horizontal Pod Autoscaler) — trigger: load testing shows the service can benefit from horizontal scaling; HPA without a baseline is guesswork
- [ ] Pod Disruption Budget — trigger: node maintenance or cluster upgrade causes availability issue without it
- [ ] Per-provider latency custom Prometheus metrics — trigger: baseline metrics show need for provider-granular visibility
- [ ] Cascade pipeline child spans (OTel) — trigger: OTel is in place; adds pipeline-stage visibility

### Future Consideration (v2+)

- [ ] ArgoCD Image Updater — trigger: manual ArgoCD sync becomes a bottleneck; low priority while team is small
- [ ] KEDA event-driven autoscaling — trigger: CPU-based HPA proves insufficient (e.g., need to scale on request queue depth); over-engineering for current load
- [ ] External secrets operator (Vault or AWS SSM) — trigger: compliance requirement; current K8s Secrets with etcd encryption is sufficient for internal API
- [ ] Network policy restricting geo-api ingress to specific namespaces — trigger: cluster grows to include untrusted workloads; currently unnecessary in a single-team cluster
- [ ] Grafana alerting rules — trigger: after 2 weeks of production baseline data; alerting before you know normal behavior produces alert fatigue

---

## Feature Prioritization Matrix

| Feature | User/Ops Value | Implementation Cost | Priority |
|---------|----------------|---------------------|----------|
| Health endpoint split (live/ready) | HIGH | LOW | P1 |
| Multi-stage Dockerfile + non-root | HIGH | MEDIUM | P1 |
| K8s Deployment manifest (geo-api + Ollama sidecar) | HIGH | MEDIUM | P1 |
| K8s ClusterIP Service | HIGH | LOW | P1 |
| K8s Secrets (dev + prod) | HIGH | LOW | P1 |
| ArgoCD Application manifests | HIGH | LOW | P1 |
| GitHub Actions CI (lint + test) | HIGH | LOW | P1 |
| GitHub Actions CD (build + push + deploy) | HIGH | MEDIUM | P1 |
| Structured JSON logging | HIGH | LOW | P1 |
| Prometheus /metrics endpoint | HIGH | LOW | P1 |
| E2E smoke test suite | HIGH | MEDIUM | P1 |
| Load test baseline (Locust) | HIGH | MEDIUM | P1 |
| OpenTelemetry traces (FastAPI + SQLAlchemy + httpx) | HIGH | MEDIUM | P2 |
| Trace ID in Loguru (custom middleware) | HIGH | MEDIUM | P2 |
| HPA (CPU-based) | MEDIUM | LOW | P2 |
| Pod Disruption Budget | MEDIUM | LOW | P2 |
| Per-provider latency Prometheus metrics | MEDIUM | LOW | P2 |
| Cascade pipeline OTel child spans | MEDIUM | MEDIUM | P2 |
| ArgoCD Image Updater | LOW | MEDIUM | P3 |
| KEDA event-driven autoscaling | LOW | HIGH | P3 |
| External secrets operator | LOW | HIGH | P3 |
| Network policy | LOW | LOW | P3 |
| Grafana alerting rules | MEDIUM | LOW | P3 — after baseline established |

**Priority key:**
- P1: Required for the v1.3 milestone to be called "production-ready"
- P2: Add after core deployment is validated; makes the service production-grade
- P3: Defer; requires baseline data or addresses speculative future concerns

---

## Complexity and Effort Notes

### LOW complexity (< 1 day each)
- Health endpoint split: refactor existing `/health` function into two routes
- Structured JSON logging: `logger.configure(sink=sys.stdout, serialize=True)` gated on `ENVIRONMENT`
- Service labels in logs: `logger.configure(extra={"service": "geo-api", ...})`
- Prometheus metrics: `prometheus-fastapi-instrumentator`, 3 lines of code
- K8s ClusterIP Service manifest: 15 lines YAML
- K8s Secrets manifests: straightforward, with a note to never commit secret values to git
- ArgoCD Application manifests: standard template
- Ruff + pytest CI workflow: GitHub Actions boilerplate
- Pod Disruption Budget: 10 lines YAML

### MEDIUM complexity (1–3 days each)
- Multi-stage Dockerfile: significant rework of existing single-stage file; must preserve GDAL deps, uv venv, scripts, non-root user setup, exec-form CMD
- K8s Deployment manifest: readiness/liveness/startup probes, preStop hook, resource limits, Ollama sidecar conversion from standalone Deployment
- GitHub Actions CD workflow: GHCR auth, docker build-push-action, image tag strategy, ArgoCD sync step
- E2E test suite: write 20–30 pytest tests covering all 5 providers, cascade, batch, validation against real deployment; requires the deployed environment to be accessible
- Load test baseline (Locust): write locustfile.py covering geocode and batch endpoints; run at multiple concurrency levels; document P50/P95/P99 results
- OpenTelemetry instrumentation: install 3–4 packages, configure OTLP exporter, instrument app startup
- Trace ID Loguru middleware: custom FastAPI middleware to extract OTel span context and bind to Loguru

### HIGH complexity (3–5 days each)
- Ollama sidecar: converting the existing Ollama Deployment + PVC to a sidecar within the geo-api Pod is non-trivial; the init container model-pull pattern must be preserved; PVC attachment changes; the Ollama K8s manifests already exist but need significant rework
- HPA scaling validation: requires both the HPA manifest and load testing to run simultaneously; must observe pod scaling behavior; timing and cluster behavior can be unpredictable

---

## Known Existing Issues (Tech Debt — Must Resolve Before Deployment)

These are known defects documented in PROJECT.md that must be fixed in v1.3 before the system is deployed:

- **Tiger timeout:** Tiger provider has known timeout issues — need to investigate and set appropriate query timeouts before deploying
- **`cache_hit` hardcode:** A field in the geocoding response is hardcoded; needs to reflect actual cache state
- **Empty spell dictionary:** The spell corrector silently fails if no dictionary entries are loaded; needs graceful degradation and clear log warning
- **CLI test failures:** 11 known pre-existing failures in CLI fixture tests; must be resolved or explicitly skipped with documented reason before CI gate is enforced
- **Thorough code review needed:** Security (SQL injection risk in raw SQL queries?), stability (unhandled exceptions in provider dispatch?), performance (N+1 queries in batch endpoints?), logic errors, uncaught exceptions in cascade pipeline

These are not new features — they are blockers that prevent a confident production deployment. They belong in the first phases of v1.3 before any deployment work begins.

---

## Sources

- Kubernetes liveness/readiness/startup probes: [kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- Google Cloud K8s health check best practices: [cloud.google.com/blog/products/containers-kubernetes/kubernetes-best-practices-setting-up-health-checks](https://cloud.google.com/blog/products/containers-kubernetes/kubernetes-best-practices-setting-up-health-checks-with-readiness-and-liveness-probes)
- FastAPI + K8s graceful shutdown (uvicorn SIGTERM): [github.com/fastapi/fastapi/discussions/10609](https://github.com/fastapi/fastapi/discussions/10609)
- Graceful pod termination with preStop hook: [minhpn.com/index.php/2025/02/26/graceful-pod-termination](https://minhpn.com/index.php/2025/02/26/graceful-pod-termination-by-fixing-sigterm-handling-and-using-prestop-hook/)
- Production-ready Python Docker images with uv: [hynek.me/articles/docker-uv](https://hynek.me/articles/docker-uv/)
- Multi-stage Python Dockerfiles with uv (2025): [digon.io/en/blog/2025_07_28_python_docker_images_with_uv](https://digon.io/en/blog/2025_07_28_python_docker_images_with_uv)
- FastAPI + GitHub Actions + GHCR CI/CD: [pyimagesearch.com/2024/11/11/fastapi-with-github-actions-and-ghcr](https://pyimagesearch.com/2024/11/11/fastapi-with-github-actions-and-ghcr-continuous-delivery-made-simple/)
- ArgoCD + GitHub Actions GitOps workflow: [medium.com/@mehmetkanus17/argocd-github-actions](https://medium.com/@mehmetkanus17/argocd-github-actions-a-complete-gitops-ci-cd-workflow-for-kubernetes-applications-ed2f91d37641)
- ArgoCD Image Updater docs: [argocd-image-updater.readthedocs.io](https://argocd-image-updater.readthedocs.io/)
- OpenTelemetry FastAPI instrumentation: [opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
- fastapi-observability reference (Traces+Metrics+Logs): [github.com/blueswen/fastapi-observability](https://github.com/blueswen/fastapi-observability)
- Loguru + OTel trace_id gap (issue #3615): [github.com/open-telemetry/opentelemetry-python/issues/3615](https://github.com/open-telemetry/opentelemetry-python/issues/3615)
- FastAPI logging complete guide: [apitally.io/blog/fastapi-logging-guide](https://apitally.io/blog/fastapi-logging-guide)
- Grafana Alloy sending OTel logs to Loki: [grafana.com/docs/loki/latest/send-data/alloy/examples/alloy-otel-logs](https://grafana.com/docs/loki/latest/send-data/alloy/examples/alloy-otel-logs/)
- Loki + Tempo log/trace correlation: [oneuptime.com/blog/post/2026-01-21-loki-tempo-traces-correlation](https://oneuptime.com/blog/post/2026-01-21-loki-tempo-traces-correlation/view)
- prometheus-fastapi-instrumentator: [github.com/trallnag/prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
- HPA autoscaling tactics for FastAPI: [medium.com/@Nexumo_/8-hpa-autoscaling-tactics-for-fastapi-on-k8s](https://medium.com/@Nexumo_/8-hpa-autoscaling-tactics-for-fastapi-on-k8s-d67635bdf8cc)
- Distributed load testing Locust + K8s + FastAPI: [medium.com/@subhraj07/distributed-load-testing-using-locust-kubernetes-and-fastapi](https://medium.com/@subhraj07/distributed-load-testing-using-locust-kubernetes-and-fastapi-88008d42f13e)
- K8s security hardening 2025: [sealos.io/blog/a-practical-guide-to-kubernetes-security-hardening](https://sealos.io/blog/a-practical-guide-to-kubernetes-security-hardening-your-cluster-in-2025/)
- Kubernetes security checklist: [kubernetes.io/docs/concepts/security/security-checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)
- Trivy container scanning: [github.com/aquasecurity/trivy-action](https://github.com/aquasecurity/trivy-action)

---

*Feature research for: Python FastAPI microservice production deployment, observability, CI/CD, and E2E testing (v1.3)*
*Researched: 2026-03-29*
