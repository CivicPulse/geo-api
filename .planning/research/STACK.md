# Technology Stack

**Project:** CivPulse Geo API — v1.3 Production Readiness & Deployment
**Researched:** 2026-03-29
**Confidence:** HIGH (OpenTelemetry SDK — PyPI + official docs), HIGH (Locust — PyPI), HIGH (Dockerfile pattern — official uv docs), MEDIUM (Loguru+OTel integration — community pattern, no official first-party support), MEDIUM (observability infrastructure versions — Helm chart changelogs + community sources)

---

## v1.3 Milestone: Stack Additions for Production Deployment, Observability, and Testing

**Research date:** 2026-03-29
**Scope:** New capabilities only. Everything from v1.0–v1.2 is unchanged and validated. This section covers: OpenTelemetry SDK + instrumentation, Loguru/trace-context integration, Prometheus metrics endpoint, Dockerfile hardening, K8s deployment patterns, CI/CD (GitHub Actions → GHCR → ArgoCD), and load/E2E testing.

### Executive Finding

**Six Python packages are required. No existing packages are replaced.** Loguru is retained as-is; trace context is injected via a lightweight FastAPI middleware patcher, not by replacing Loguru with stdlib logging. The observability stack (Alloy, Loki, Tempo, VictoriaMetrics) is infrastructure running in the cluster — not Python dependencies. ArgoCD and GitHub Actions are CI/CD infrastructure, not application code.

---

### OpenTelemetry SDK and Instrumentation

The OpenTelemetry Python SDK is at stable 1.40.0 (API + SDK) and 0.61b0 (contrib/instrumentation packages). The 0.x beta version numbering for contrib is the project's permanent release cadence — these are production-ready despite the beta label. All packages released 2026-03-04.

| Package | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `opentelemetry-api` | 1.40.0 | OTel API primitives — tracer, span, context | Stable API layer; required by all instrumentation packages. Zero-overhead no-op when no SDK configured. |
| `opentelemetry-sdk` | 1.40.0 | SDK implementation — TracerProvider, SpanProcessor, Sampler | Stable. Provides BatchSpanProcessor for async-safe span export without blocking the event loop. |
| `opentelemetry-exporter-otlp-proto-http` | 1.40.0 | Export traces and metrics via OTLP/HTTP to Grafana Alloy | HTTP/protobuf preferred over gRPC for this stack — avoids grpcio binary dependency (~10 MB), Alloy's OTLP receiver supports HTTP natively, firewall-friendlier. |
| `opentelemetry-instrumentation-fastapi` | 0.61b0 | Auto-instrument FastAPI: creates spans for every HTTP request, propagates W3C traceparent headers | Zero application code changes. Records request method, route, status code, duration. Integrates with existing Starlette middleware stack. |
| `opentelemetry-instrumentation-httpx` | 0.61b0 | Auto-instrument httpx: creates child spans for outbound HTTP calls (Census Geocoder, Ollama) | Traces external provider calls as child spans within the geocoding request span. No code changes needed beyond one-time `HTTPXClientInstrumentor().instrument()` call. |
| `opentelemetry-instrumentation-sqlalchemy` | 0.61b0 | Auto-instrument SQLAlchemy: creates spans for all DB queries | Use `SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)` — asyncpg via SQLAlchemy's async engine exposes the sync engine for instrumentation. Traces query latency, table, operation for every ORM call. |

**Why not `opentelemetry-instrumentation-asyncpg` separately:** `opentelemetry-instrumentation-sqlalchemy` instruments at the SQLAlchemy layer, which covers all asyncpg calls already. Adding asyncpg instrumentation on top creates duplicate spans. Use SQLAlchemy instrumentation only.

**Why OTLP/HTTP not gRPC:** The `grpc` transport requires `grpcio`, a native binary extension with a large install footprint and frequent version conflicts. The HTTP exporter uses the already-present `httpx` transport model and sends to the same Alloy receiver endpoint.

**Why OpenTelemetry not a commercial APM agent:** OpenTelemetry is the CNCF standard, vendor-neutral, and works with Grafana Alloy → Tempo (the chosen stack). APM agents (Datadog, New Relic) require managed cloud accounts and send data off-premises — incompatible with the internal-only network constraint.

**Installation:**
```bash
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
uv add opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-httpx opentelemetry-instrumentation-sqlalchemy
```

---

### Loguru + OpenTelemetry Trace Context Integration

**Critical finding: Loguru has no official first-party OpenTelemetry integration.** The `opentelemetry-instrumentation-logging` package patches stdlib `logging` only — it does NOT patch Loguru. Do not replace Loguru with stdlib logging; Loguru is a hard project constraint.

**Recommended pattern: FastAPI middleware patcher using `logger.contextualize()`**

```python
from opentelemetry import trace
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

class TraceContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        span = trace.get_current_span()
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else "0" * 32
        span_id = format(ctx.span_id, "016x") if ctx.is_valid else "0" * 16
        with logger.contextualize(trace_id=trace_id, span_id=span_id):
            return await call_next(request)
```

This middleware runs after `FastAPIInstrumentor` has created and activated the span for the request, so `get_current_span()` returns a valid span. The `contextualize()` context manager binds `trace_id` and `span_id` to all Loguru log calls within the request's async scope. No Loguru replacement required.

**Structured JSON logging for Loki:** Loguru's JSON serialization is enabled at startup, not per-request:
```python
import sys
logger.remove()
logger.add(sys.stdout, serialize=True)  # emits newline-delimited JSON
```
Grafana Alloy's `loki.source.kubernetes` component discovers container stdout logs automatically. No file sink, no file path configuration needed in K8s.

**Confidence:** MEDIUM. This pattern is validated by community implementations (Dash0 guide, OpenTelemetry GitHub issue #3615) and leverages Loguru's documented `contextualize()` API. The Loguru maintainer is considering native OTel support but it is not yet merged.

---

### Prometheus Metrics Endpoint (for VictoriaMetrics scraping)

| Package | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `prometheus-fastapi-instrumentator` | 7.1.0 | Exposes `/metrics` endpoint in Prometheus exposition format for VictoriaMetrics scraping | The standard approach for FastAPI + Prometheus. Automatically instruments all routes with request count, duration histograms, and in-flight gauge. Single `Instrumentator().instrument(app).expose(app)` call. Released March 19, 2025. Python 3.8–3.13. |

**Why this over bare `prometheus_client`:** The bare client requires manual middleware boilerplate to collect per-route latency histograms. `prometheus-fastapi-instrumentator` wraps this correctly and matches FastAPI's route-grouping semantics (routes with path parameters like `/geocode/{id}` are correctly labeled, not exploded into per-ID metrics).

**Why Prometheus format (not OTLP metrics):** VictoriaMetrics scrapes Prometheus exposition format via its built-in Prometheus-compatible scraper. This is simpler than configuring an OTLP metrics pipeline through Alloy. The OpenTelemetry SDK metrics pipeline is available if needed later but adds complexity for minimal gain at this stage.

**Installation:**
```bash
uv add prometheus-fastapi-instrumentator
```

---

### Dockerfile Hardening (Multi-Stage + Non-Root + uv)

The existing Dockerfile is a single-stage image that runs as root. For K8s production deployment the recommended pattern is two-stage (builder + runtime) with a non-root user. No new Python packages are needed — this is a Dockerfile change.

**Recommended pattern (from Hynek Schlawack's "Production-Ready Python Docker Containers with uv"):**

```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Install system build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev libexpat1 && rm -rf /var/lib/apt/lists/*

# Install dependencies (cached until lockfile changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev libexpat1 postgis postgresql-client unzip wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -d /app -g appuser -N appuser \
    && mkdir -p /gisdata/temp && chown -R appuser:appuser /gisdata

COPY --from=builder --chown=appuser:appuser /app /app

ENV PATH="/app/.venv/bin:$PATH"
USER appuser
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

CMD ["bash", "scripts/docker-entrypoint.sh"]
```

**Key improvements over current Dockerfile:**
- `UV_COMPILE_BYTECODE=1`: pre-compiles `.pyc` files at build time → faster container startup
- `UV_LINK_MODE=copy`: copies files instead of hardlinks (required when build/runtime differ)
- `UV_PYTHON_DOWNLOADS=never`: uses system Python, no Astral download at build time
- Non-root `appuser`: K8s security best practice; many clusters enforce non-root via PodSecurityAdmission
- Build tools (`libgdal-dev`) stay in builder stage; runtime stage installs only shared libs, not headers
- `--no-dev` in sync: excludes pytest/debugpy from production image

**Important: do NOT use `FROM ghcr.io/astral-sh/uv AS uv` base image for the runtime stage** — it's Debian-based and larger. Copy only the `/uv` binary and keep `python:3.12-slim` as the base.

---

### K8s Deployment Patterns

No new Python packages. Infrastructure manifest patterns only.

**API Deployment configuration:**
- Single Uvicorn process per pod (not Gunicorn workers) — K8s HPA handles horizontal scaling
- `replicas: 1` initially, HPA target at 70% CPU
- `resources.requests`: 256m CPU / 512Mi RAM; `resources.limits`: 1000m CPU / 1Gi RAM
- Liveness probe: `GET /health` (implement if not present)
- Readiness probe: `GET /health` with `initialDelaySeconds: 5`
- `terminationGracePeriodSeconds: 30` — allows in-flight requests to complete

**Service:** ClusterIP only (per PROJECT.md constraint). Port 8000. No Ingress.

**Access:** `kubectl port-forward svc/geo-api 8000:8000` for debugging. No NodePort required given k3s environment.

**Namespace strategy:** `civpulse-dev` and `civpulse-prod` namespaces. Use `kustomize` overlays (base + dev overlay + prod overlay) rather than separate manifests — reduces drift between environments.

**ConfigMap vs Secrets:** Database DSN, API keys → K8s Secrets. Non-sensitive config (log level, provider toggles) → ConfigMap. Mount as env vars, not files, for this use case.

---

### CI/CD: GitHub Actions → GHCR → ArgoCD

No new Python packages. Infrastructure/workflow patterns only.

**GitHub Actions workflow structure:**

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}
      sha_short: ${{ steps.sha.outputs.sha_short }}
    steps:
      - uses: actions/checkout@v4
      - id: sha
        run: echo "sha_short=$(git rev-parse --short HEAD)" >> $GITHUB_OUTPUT
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/civpulse/geo-api:${{ steps.sha.outputs.sha_short }}
          build-args: GIT_COMMIT=${{ steps.sha.outputs.sha_short }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  update-manifests:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: civpulse/k8s-manifests  # separate GitOps repo
          token: ${{ secrets.GITOPS_TOKEN }}
      - name: Update image tag
        run: |
          sed -i "s|image: ghcr.io/civpulse/geo-api:.*|image: ghcr.io/civpulse/geo-api:${{ needs.build.outputs.sha_short }}|" \
            apps/geo-api/dev/deployment.yaml
      - uses: actions/create-github-app-token@v1  # or use PAT
      - run: |
          git config user.email "ci@civpulse.org"
          git config user.name "CivPulse CI"
          git commit -am "chore: update geo-api to ${{ needs.build.outputs.sha_short }}"
          git push
```

**Image tagging:** Use 7-char commit SHA as immutable tag. Never use `:latest` in K8s manifests. SHA tags are traceable and support rollback via ArgoCD.

**ArgoCD version:** 3.3.x (latest as of March 2026). ArgoCD 3.0 is EOL. Use 3.1 or higher. v3.1+ supports native OCI registry for Helm charts.

**ArgoCD Application pattern:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: geo-api-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/civpulse/k8s-manifests
    targetRevision: HEAD
    path: apps/geo-api/dev
  destination:
    server: https://kubernetes.default.svc
    namespace: civpulse-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Secret strategy:** Never commit plaintext secrets to the GitOps repo. Use K8s Secrets created out-of-band (via `kubectl create secret`) or Sealed Secrets for encrypted-in-Git approach. ExternalSecrets requires a secrets backend (Vault, cloud SM) — overkill for this deployment scale.

---

### Observability Infrastructure (Cluster-Level, Not Python Packages)

These run in the K8s cluster. No Python dependencies added to the geo-api.

#### Grafana Alloy (Log + Trace Collector)

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `grafana/alloy` Helm chart | v1.14.x (app version) / chart 0.x | DaemonSet (log collection) + Deployment (OTLP receiver) | Collects container stdout logs via `loki.source.kubernetes`, receives OTLP traces from geo-api, forwards to Loki and Tempo |

**Why Alloy not Promtail:** Alloy is Grafana's official replacement for Promtail (now deprecated). Alloy handles both logs and traces in a single agent, reducing the number of components to manage.

**Why DaemonSet for logs:** `loki.source.kubernetes` uses the Kubernetes API to tail pod logs without requiring node-level file access — runs as DaemonSet with `spec.nodeName` selector to collect only local node logs.

**Alloy OTLP receiver config for traces:**
```alloy
otelcol.receiver.otlp "default" {
  http { endpoint = "0.0.0.0:4318" }
  output {
    traces = [otelcol.exporter.otlp.tempo.input]
  }
}
```

#### Grafana Loki (Log Aggregation)

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `grafana/loki` Helm chart | 6.x (single-binary mode) | StatefulSet | Receives structured JSON logs from Alloy, queryable from Grafana |

**Why single-binary mode:** The microservices (distributed) mode requires 5+ separate StatefulSets. Single-binary (`loki.deploymentMode: SingleBinary`) runs all components in one pod — appropriate for internal, low-volume geo-api log traffic.

**Note (March 2026):** The OSS Loki Helm chart has moved from `grafana/helm-charts` to `grafana-community/helm-charts` at chart version 6.55.0. Use `helm repo add grafana-community https://grafana.github.io/helm-charts` when installing.

#### Grafana Tempo (Distributed Tracing Backend)

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `grafana/tempo` Helm chart | latest stable | Deployment | Receives OTLP traces from Alloy, stores and queries spans |

**Why Tempo not Jaeger:** Tempo is the native Grafana Labs tracing backend with built-in Grafana datasource integration (TraceQL, span linking to logs). Jaeger requires separate UI and storage configuration. Tempo also supports parquet-based object storage backends for long retention.

#### VictoriaMetrics (Metrics Storage)

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `victoria-metrics-k8s-stack` Helm chart | 0.72.5 (March 16, 2026) | Includes VMSingle, VMAgent, VMAlert, Grafana, node-exporter, kube-state-metrics | Prometheus-compatible metrics storage + K8s cluster monitoring in one chart |

**Why VictoriaMetrics not Prometheus:** VictoriaMetrics uses 5–10x less RAM than Prometheus for equivalent retention. VMSingle (single-node) scales vertically and is simpler to operate than Prometheus with Thanos. PromQL-compatible — all existing Prometheus dashboards work unchanged.

**Why `victoria-metrics-k8s-stack` not just VMSingle:** The all-in-one chart installs node-exporter, kube-state-metrics, VMAgent (scrape layer), and Grafana together — significantly reduces bootstrap effort. VictoriaMetrics components updated to v1.138.0 in chart 0.72.5.

**geo-api metrics scraping:** VMAgent discovers geo-api pods via Prometheus annotations (`prometheus.io/scrape: "true"`, `prometheus.io/port: "8000"`, `prometheus.io/path: "/metrics"`). No additional ServiceMonitor CRDs needed for basic scraping.

#### ArgoCD

| Component | Version | Notes |
|-----------|---------|-------|
| ArgoCD | 3.3.x | Latest as of March 2026. v3.0 EOL Feb 2026. v3.1+ required. |

---

### Load Testing

| Package | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `locust` | 2.43.3 | HTTP load testing with configurable user tasks and ramp-up profiles | Python-native (tasks written as Python classes), built-in web UI for real-time P50/P95/P99 visualization, supports `--headless` mode for CI execution, CSV export for baseline comparison. No JVM/Go toolchain required. Released Feb 12, 2026. Python 3.10–3.14. |

**Why Locust not k6:** k6 requires a separate JavaScript/TypeScript toolchain and binary. Locust test scripts are Python — consistent with the rest of the CivPulse project. Locust also supports distributed load generation on K8s (master + worker pods) if single-node capacity is insufficient.

**Why Locust not Gatling/JMeter:** JVM-based, require Java, not Python. Heavier operational overhead for a Python shop.

**Locust test structure for geo-api:**
```python
from locust import HttpUser, task, between

class GeoApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def geocode_single(self):
        self.client.post("/geocode", json={"address": "123 Elm St, Macon GA 31201"})

    @task(1)
    def geocode_batch(self):
        self.client.post("/geocode/batch", json={"addresses": [
            "100 Cherry St, Macon GA 31201",
            "200 Forsyth St, Macon GA 31201",
        ]})
```

**Baseline targets (from PROJECT.md):** P50 < 500ms, P95 < 3s (established in v1.2 cascade research). Load test must verify these hold under concurrent load.

**Installation (dev dependency):**
```bash
uv add --dev locust
```

---

### E2E Testing

**Recommended approach: pytest + httpx.AsyncClient against deployed cluster (via port-forward)**

No new testing frameworks are needed beyond Locust. The existing `pytest` + `pytest-asyncio` + `httpx` dev stack is sufficient for E2E integration tests that validate all 5 providers in the deployed environment.

**Pattern:**
```python
import httpx
import pytest

BASE_URL = "http://localhost:8000"  # via kubectl port-forward

@pytest.mark.asyncio
async def test_census_provider_e2e():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        resp = await client.post("/geocode", json={"address": "100 Cherry St Macon GA 31201"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["official"]["latitude"] is not None
        assert any(r["provider"] == "census" for r in data["results"])
```

**Why not Playwright for API E2E:** Playwright is a browser automation tool — not appropriate for a headless REST API. `httpx.AsyncClient` is already in the project's test stack and is the correct tool for async API integration tests.

**Why not a separate E2E framework (RestAssured, Karate):** All would require additional language runtimes (Java/Kotlin). Python + httpx + pytest is idiomatic for this project.

**No additional packages required for E2E.** `httpx` and `pytest-asyncio` are already in `[dependency-groups.dev]`.

---

### New Packages Summary (v1.3)

| Package | Version | Install Command | Category |
|---------|---------|----------------|----------|
| `opentelemetry-api` | 1.40.0 | `uv add opentelemetry-api` | Runtime |
| `opentelemetry-sdk` | 1.40.0 | `uv add opentelemetry-sdk` | Runtime |
| `opentelemetry-exporter-otlp-proto-http` | 1.40.0 | `uv add opentelemetry-exporter-otlp-proto-http` | Runtime |
| `opentelemetry-instrumentation-fastapi` | 0.61b0 | `uv add opentelemetry-instrumentation-fastapi` | Runtime |
| `opentelemetry-instrumentation-httpx` | 0.61b0 | `uv add opentelemetry-instrumentation-httpx` | Runtime |
| `opentelemetry-instrumentation-sqlalchemy` | 0.61b0 | `uv add opentelemetry-instrumentation-sqlalchemy` | Runtime |
| `prometheus-fastapi-instrumentator` | 7.1.0 | `uv add prometheus-fastapi-instrumentator` | Runtime |
| `locust` | 2.43.3 | `uv add --dev locust` | Dev only |

**Total new runtime packages: 7. One new dev package: 1.**

---

### What NOT to Add (v1.3)

| Do Not Add | Why | Use Instead |
|------------|-----|-------------|
| `opentelemetry-instrumentation-logging` | Patches stdlib `logging` only — has no effect on Loguru. Replacing Loguru with stdlib logging is a hard constraint violation. | `logger.contextualize()` in FastAPI middleware (custom pattern) |
| `opentelemetry-instrumentation-asyncpg` | Duplicates spans already created by SQLAlchemy instrumentation — creates nested duplicate DB spans | `opentelemetry-instrumentation-sqlalchemy` only |
| `opentelemetry-exporter-otlp-proto-grpc` | Requires `grpcio` native binary (~10 MB, frequent install issues). HTTP exporter reaches the same Alloy endpoint. | `opentelemetry-exporter-otlp-proto-http` |
| `gunicorn` in K8s | Multiple Uvicorn workers per pod conflicts with K8s HPA scaling model. HPA scales pods, not processes. | Single Uvicorn process per pod + HPA |
| `prometheus_client` (bare) | Requires manual middleware for per-route metrics. Does not handle path-parameter route grouping. | `prometheus-fastapi-instrumentator` |
| `structlog` | Would require replacing Loguru, which is a project constraint. Structlog's JSON output is equivalent to Loguru's `serialize=True`. | Loguru `serialize=True` + `contextualize()` |
| `k6` or `JMeter` | Require non-Python runtimes (Go/Java). Locust achieves equivalent load generation in Python. | `locust` |
| Playwright for API E2E | Browser automation tool — inappropriate for headless REST API testing. | `httpx.AsyncClient` + `pytest` (already in stack) |
| Jaeger | Separate UI, storage config overhead. Grafana has native Tempo datasource with TraceQL. | Grafana Tempo |
| Promtail | Deprecated by Grafana Labs in favor of Alloy. No future development. | Grafana Alloy |
| Grafana Mimir | Enterprise-scale distributed metrics — overkill for single internal API. Higher operational complexity. | VictoriaMetrics VMSingle |
| `:latest` image tag in K8s manifests | Not immutable — rollback impossible, pod restarts can change behavior silently | Git SHA-based tag (e.g., `geo-api:a3f7b12`) |
| Sealed Secrets (if out-of-band K8s Secrets suffice) | Adds controller dependency and key management overhead. Only needed if Secrets must live in Git. | `kubectl create secret` out-of-band |

---

### Loguru JSON Output Format for Loki

When Loguru emits JSON (`serialize=True`), the output structure is:
```json
{
  "text": "Geocoding request completed",
  "record": {
    "level": {"name": "INFO"},
    "time": {"timestamp": 1711728000.0},
    "message": "Geocoding request completed",
    "extra": {"trace_id": "4bf92f3577b34da6...", "span_id": "00f067aa0ba902b7..."}
  }
}
```

Alloy's `loki.process` pipeline stage extracts `record.level.name` as the log level label and `record.extra.trace_id` for Loki-to-Tempo trace linking. Configure the Loki datasource in Grafana with a "Derived Field" that matches the `trace_id` pattern and links to the Tempo datasource.

---

### Version Compatibility (v1.3 Additions)

| Package | Compatible With | Notes |
|---------|----------------|-------|
| `opentelemetry-api==1.40.0` | Python 3.9–3.14 | No conflict with existing stack |
| `opentelemetry-sdk==1.40.0` | Python 3.9–3.14 | Requires opentelemetry-api ~= 1.40.0 |
| `opentelemetry-exporter-otlp-proto-http==1.40.0` | opentelemetry-sdk ~= 1.40.0; httpx (already present) | Uses httpx transport internally — verify httpx >= 0.26.0 (project has 0.28.1 — compatible) |
| `opentelemetry-instrumentation-fastapi==0.61b0` | FastAPI >= 0.51.0 (project has 0.135.1 — compatible); opentelemetry-api ~= 1.40 | |
| `opentelemetry-instrumentation-httpx==0.61b0` | httpx >= 0.23.0 (project has 0.28.1 — compatible) | |
| `opentelemetry-instrumentation-sqlalchemy==0.61b0` | SQLAlchemy >= 1.4 (project has 2.0.x — compatible); GeoAlchemy2 unaffected (uses same engine) | |
| `prometheus-fastapi-instrumentator==7.1.0` | FastAPI >= 0.51.0; Python >= 3.8; prometheus-client auto-installed | |
| `locust==2.43.3` | Python >= 3.10 (project uses 3.12 — compatible) | Dev-only; no runtime footprint |

---

### Sources (v1.3)

- [opentelemetry-sdk on PyPI](https://pypi.org/project/opentelemetry-sdk/) — version 1.40.0, released March 4, 2026 (HIGH confidence, verified)
- [opentelemetry-exporter-otlp-proto-http on PyPI](https://pypi.org/project/opentelemetry-exporter-otlp-proto-http/) — version 1.40.0, March 4, 2026 (HIGH confidence, verified)
- [opentelemetry-instrumentation-fastapi on PyPI](https://pypi.org/project/opentelemetry-instrumentation-fastapi/) — version 0.61b0, March 4, 2026, Python 3.9–3.14 (HIGH confidence, verified)
- [opentelemetry-python GitHub releases](https://github.com/open-telemetry/opentelemetry-python/releases) — confirmed 1.40.0/0.61b0 release date (HIGH confidence)
- [OpenTelemetry Python instrumentation docs](https://opentelemetry.io/docs/languages/python/) — stable traces/metrics, dev logs (HIGH confidence)
- [OpenTelemetry SQLAlchemy async engine pattern](https://oneuptime.com/blog/post/2026-02-06-instrument-async-sqlalchemy-2-opentelemetry/view) — `engine.sync_engine` pattern for async SQLAlchemy (MEDIUM confidence)
- [Loguru + OpenTelemetry GitHub issue #3615](https://github.com/open-telemetry/opentelemetry-python/issues/3615) — confirmed no official Loguru integration; `contextualize()` workaround community pattern (MEDIUM confidence)
- [Production-Grade Python Logging Made Easier with Loguru · Dash0](https://www.dash0.com/guides/python-logging-with-loguru) — `logger.contextualize()` + FastAPI middleware pattern (MEDIUM confidence)
- [prometheus-fastapi-instrumentator on PyPI](https://pypi.org/project/prometheus-fastapi-instrumentator/) — version 7.1.0, March 19, 2025 (HIGH confidence, verified)
- [locust on PyPI](https://pypi.org/project/locust/) — version 2.43.3, Feb 12, 2026, Python >= 3.10 (HIGH confidence, verified)
- [Grafana Alloy Kubernetes log collection docs](https://grafana.com/docs/alloy/latest/collect/logs-in-kubernetes/) — v1.14, DaemonSet deployment, `loki.source.kubernetes` component (HIGH confidence, official docs)
- [Grafana Alloy OTLP → Tempo docs](https://grafana.com/docs/tempo/latest/set-up-for-tracing/instrument-send/set-up-collector/grafana-alloy/) — Alloy as OTLP receiver (HIGH confidence, official docs)
- [VictoriaMetrics K8s stack Helm chart docs](https://docs.victoriametrics.com/helm/victoria-metrics-k8s-stack/) — chart 0.72.5 released March 16, 2026 (HIGH confidence, official docs)
- [ArgoCD releases](https://github.com/argoproj/argo-cd/releases) — v3.3.6 latest as of March 27, 2026; v3.0 EOL Feb 2026 (HIGH confidence)
- [FastAPI Kubernetes deployment — single uvicorn per pod](https://fastapi.tiangolo.com/deployment/server-workers/) — official FastAPI docs recommending single process per K8s pod (HIGH confidence)
- [Production-ready Python Docker containers with uv](https://hynek.me/articles/docker-uv/) — multi-stage pattern, `UV_COMPILE_BYTECODE`, non-root user (HIGH confidence, authoritative uv article)
- [GitHub Actions + GHCR + ArgoCD GitOps pattern](https://medium.com/@nathanieldarko100/building-a-kubernetes-ci-cd-pipeline-with-github-actions-argocd-and-github-container-registry-236fcc58601e) — SHA-tag pattern, GitOps repo update step (MEDIUM confidence)
- [Grafana Loki Helm chart move to grafana-community](https://grafana.com/docs/helm-charts/) — chart 6.55.0 moved repo March 2026 (MEDIUM confidence, official Grafana docs)

---

## v1.2 Milestone: Stack Additions for Cascading Address Resolution

**Research date:** 2026-03-29
**Confidence:** HIGH (PostgreSQL extensions — official docs), HIGH (symspellpy — PyPI + official docs), MEDIUM (Ollama/LLM — community benchmarks), MEDIUM (consensus scoring — no standard library exists)

### Executive Finding

**Only one new Python library is required: `symspellpy`.** The Ollama Docker sidecar is infrastructure, not a Python dependency (called via existing `httpx`). PostgreSQL fuzzy/phonetic extensions are already bundled in the `postgis/postgis:17-3.5` Docker image. Consensus scoring is implemented with existing PostGIS spatial functions and Python stdlib.

---

### PostgreSQL Extensions (Fuzzy/Phonetic Matching)

Both extensions are bundled with the `postgis/postgis:17-3.5` Docker image as PostgreSQL contrib modules. No new Docker images, no apt installs, no version management.

| Extension | Setup | Purpose |
|-----------|-------|---------|
| `pg_trgm` | `CREATE EXTENSION IF NOT EXISTS pg_trgm;` | Trigram-based fuzzy string similarity for street name matching |
| `fuzzystrmatch` | `CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;` | Phonetic matching (Soundex, Metaphone, Double Metaphone, Levenshtein) |

**Note:** `fuzzystrmatch` is already created by the Tiger geocoder setup (v1.1). The `CREATE EXTENSION IF NOT EXISTS` form is idempotent — safe to call again in v1.2 migrations.

**Key functions by use case:**

| Use Case | Function / Operator | Notes |
|----------|---------------------|-------|
| "Does this street name approximately match?" | `word_similarity(query, street_name) > 0.5` with `<%` operator | Use `<%` operator, not `%`, to get index support |
| Ordered fuzzy results | `ORDER BY street_name <<-> query ASC` | Requires GiST index (not GIN) |
| Full address similarity | `similarity(a, b)` | Only for comparing two strings of equal length/scope |
| Phonetic match (English US street names) | `dmetaphone(s) = dmetaphone(q) OR dmetaphone_alt(s) = dmetaphone_alt(q)` | Covers alternate pronunciations ("Fischer" / "Fisher") |
| Edit distance ceiling | `levenshtein_less_equal(a, b, 3)` | Returns -1 if distance > max_d; cheaper than full `levenshtein()` |

**Why `word_similarity()` not `similarity()` for street matching:**
`similarity('elm', 'elm street macon ga 31201')` scores poorly because the query string is a tiny fraction of the target. `word_similarity('elm', 'elm street macon ga 31201')` finds the best matching continuous substring, returning a high score. This is the right function for matching a short street name query against a full address string.

**Why `dmetaphone()` not `soundex()` for phonetic matching:**
Soundex 4-char code space has extreme collisions for US street names — "Main" and "Macon" produce the same Soundex code. `dmetaphone()` returns longer codes with primary and alternate forms, dramatically reducing false positives.

**Index strategy:**
```sql
-- GIN for fast similarity threshold queries (WHERE word_similarity(...) > 0.5)
CREATE INDEX idx_street_gin ON addresses USING GIN (street_name gin_trgm_ops);

-- GiST when ORDER BY similarity score is needed
CREATE INDEX idx_street_gist ON addresses USING GIST (street_name gist_trgm_ops);

-- Functional index for phonetic matching
CREATE INDEX idx_street_dmetaphone ON addresses (dmetaphone(street_name));
```

**Threshold tuning guidance:**
- `pg_trgm.similarity_threshold` default: 0.3 — too loose for street names; raise to 0.5
- `pg_trgm.word_similarity_threshold` default: 0.6 — reasonable starting point
- Set per-session: `SET pg_trgm.word_similarity_threshold = 0.5;`

**Important encoding caveat:** `soundex`, `metaphone`, `dmetaphone`, and `dmetaphone_alt` do not work correctly with UTF-8 multibyte characters. US street names are ASCII-safe in practice — not a concern for this project, but document for future international work. `levenshtein` and `daitch_mokotoff` are safe with UTF-8.

---

### Python Spell Correction (Offline, Pre-Dispatch Layer)

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `symspellpy` | 6.9.0 | Address typo correction before provider dispatch | 1M+ words/second via Symmetric Delete algorithm. Supports `lookup_compound()` for multi-word correction of full address strings. Custom dictionary via `load_dictionary()` and `create_dictionary_entry()` — critical for loading US street names as high-frequency terms. Supports bigram dictionaries via `load_bigram_dictionary()` for multi-word street names ("Peachtree Battle" etc.). MIT license. Python 3.9–3.13. |

**Why not `pyspellchecker`:** Generates all Levenshtein permutations at lookup time — much slower. No compound/multi-word correction. Cannot bootstrap from a domain-specific address dictionary efficiently.

**Why not textblob / spaCy / nltk:** General-purpose NLP with heavy dependency chains. No custom domain dictionary appropriate for address correction. Overkill for this task.

**Integration pattern:**
```python
from symspellpy import SymSpell, Verbosity

sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
# Load general English frequency dictionary (bundled with symspellpy)
sym_spell.load_dictionary("frequency_dictionary_en_82_765.txt", term_index=0, count_index=1)
# Bootstrap with street names from local address data at startup
# High frequency count = symspellpy prefers these over general English words
sym_spell.create_dictionary_entry("peachtree", 50000)
sym_spell.create_dictionary_entry("forsyth", 50000)

# Multi-word correction for full address string
suggestions = sym_spell.lookup_compound("123 Peechtre St", max_edit_distance=2)
corrected = suggestions[0].term  # "123 peachtree st"
```

**Dictionary bootstrap at startup:** Query distinct street names from local address tables and inject as high-frequency entries. This primes symspellpy to prefer local street names over phonetically similar English words.

---

### LLM Sidecar (Last-Resort Address Correction)

This is the final fallback in the cascade — invoked only when deterministic methods (spell correction, fuzzy matching) cannot resolve an address.

| Technology | Version / Tag | Purpose | Why Recommended |
|------------|--------------|---------|-----------------|
| `ollama/ollama` (Docker image) | `latest` (pin digest in prod) | Serve small LLM as Docker Compose sidecar | Official image; sets `OLLAMA_HOST=0.0.0.0:11434` for inter-container access. Manages model storage, CPU/GPU detection automatically. REST API maps directly to existing httpx patterns. |
| `qwen2.5:3b` (model) | Q4_K_M quantized (~1.9 GB on disk, ~2.5 GB RAM) | Address correction and completion via structured JSON | Best instruction-following at 3B scale. Qwen2.5 was explicitly designed for structured JSON output as a primary goal. CPU-only inference: ~8–12 tok/s; first call after container start: 6–40s (model load); subsequent: 2–5s for short address strings. Acceptable for a tail-of-cascade fallback. |
| `ollama` (Python package) | 0.6.1 | Async client for Ollama; wraps `httpx.AsyncClient` | Matches existing httpx dependency; `AsyncClient` provides `await client.chat()`. Use only if raw httpx is insufficient (streaming, retry logic). For simple one-shot calls, raw httpx is preferred to avoid an extra dependency. |

**Why not `phi-3-mini:3.8b`:** Documented JSON schema compliance failures at 3.8B with strict schemas (empty results in outlines/guidance). Qwen2.5 was designed with JSON as an explicit target. phi-3-mini is also slightly larger.

**Why not `qwen2.5:7b`:** Requires ~4.5 GB RAM — 2x the 3B model for marginal gains on short address strings. Model upgrade is trivial (change one string); start with 3B.

**Why not `llama.cpp` directly:** Manual C++ build, GGUF file management, no model library. Ollama wraps all of this with an identical REST API.

**Why not `transformers` in-process:** Adds 2–3 GB to API process memory; inference blocks the async event loop without an explicit process pool; complex integration.

**Structured output via raw httpx (no additional dependency):**
```python
# Uses existing httpx.AsyncClient — zero new dependencies
response = await http_client.post(
    "http://ollama:11434/api/chat",
    json={
        "model": "qwen2.5:3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": AddressCorrectionResult.model_json_schema(),
    },
    timeout=30.0,
)
result = AddressCorrectionResult.model_validate_json(response.json()["message"]["content"])
```

**Docker Compose service:**
```yaml
ollama:
  image: ollama/ollama:latest
  volumes:
    - ollama_models:/root/.ollama
  environment:
    - OLLAMA_HOST=0.0.0.0:11434
  # No GPU required — CPU inference acceptable for fallback path

volumes:
  ollama_models:
```

**K8s / ArgoCD production consideration:** Use a PVC backed by the ZFS/NFS fileserver for model storage — `emptyDir` causes model re-download on every pod restart. Consider a dedicated Ollama Deployment + ClusterIP Service if multiple API pod replicas share the same model.

---

### Cross-Provider Consensus Scoring

No general-purpose Python library matches this domain. (VoteM8, CoVIRA, etc. are for molecular docking and bioinformatics.) Implement with existing dependencies — no new libraries needed.

**Approach: Weighted Spatial Agreement Score**

| Capability | Implementation | Existing Dependency |
|------------|---------------|---------------------|
| Coordinate distance between provider results | `ST_Distance(Geography, Geography)` returns meters | PostGIS / GeoAlchemy2 (present) |
| Spatial clustering of provider results | `ST_ClusterDBSCAN` or Python distance matrix | PostGIS 3.5 (present) |
| Provider weight config | Dict of `{provider_name: weight}` | Python stdlib |
| Outlier detection | Results > N meters from cluster centroid | `ST_Centroid` + `ST_Distance` (PostGIS) |
| Score aggregation | Weighted mean of agreement ratios | Python `statistics.mean` |

**Algorithm sketch (no new libraries):**
```python
from statistics import mean

PROVIDER_WEIGHTS = {
    "census": 0.8,
    "tiger": 0.9,
    "openaddresses": 0.95,
    "nad": 0.85,
    "macon_bibb": 1.0,
}

def compute_consensus(results: list[ProviderCoordinate], agreement_radius_m: float = 100.0) -> ConsensusScore:
    # 1. For each pair, compute distance via haversine or PostGIS
    # 2. Build adjacency: providers within agreement_radius_m of each other "agree"
    # 3. Largest agreement cluster = winning group
    # 4. score = (agreeing_providers / total_providers) * mean(weighted_confidences)
    # 5. Outliers = providers outside the winning cluster — flag, do not use for official
    ...
```

**PostGIS distance query (already available):**
```sql
SELECT
    p1.provider, p2.provider,
    ST_Distance(
        Geography(ST_MakePoint(p1.lon, p1.lat)),
        Geography(ST_MakePoint(p2.lon, p2.lat))
    ) AS distance_meters
FROM provider_results p1, provider_results p2
WHERE p1.address_id = p2.address_id AND p1.provider != p2.provider
```

---

### New Packages Summary

| Package | Version | Install Command | Notes |
|---------|---------|----------------|-------|
| `symspellpy` | 6.9.0 | `uv add symspellpy` | Only new Python dep for v1.2 |
| `ollama` | 0.6.1 | `uv add ollama` (optional) | Only if raw httpx insufficient |

**PostgreSQL extensions** — no install needed, activated via SQL migration:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- bundled in postgis/postgis:17-3.5
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch; -- already present from v1.1 Tiger setup
```

**Docker infrastructure** — add `ollama` service to `docker-compose.yml` (see above).

---

### What NOT to Add

| Do Not Add | Why | Use Instead |
|------------|-----|-------------|
| `pyspellchecker` | Slow Levenshtein permutation approach; no compound correction; no custom dictionary bootstrapping | `symspellpy` |
| `textblob` / `spaCy` / `nltk` | General NLP — heavy dependencies, not designed for address domain dictionaries | `symspellpy` with custom dictionary |
| `soundex()` for street phonetics | 4-char Soundex codes collide aggressively — "Main" and "Macon" share a code | `dmetaphone()` + `dmetaphone_alt()` |
| `similarity()` for street-name-vs-full-address | Scores poorly when query is tiny fraction of target string | `word_similarity()` or `strict_word_similarity()` |
| GIN index for ORDER BY similarity | GIN supports threshold `WHERE` but not distance `ORDER BY` | GiST index for ordered results |
| `phi-3-mini:3.8b` | Documented JSON schema compliance issues; slightly larger than qwen2.5:3b | `qwen2.5:3b` |
| `qwen2.5:7b` or larger | 2x memory for marginal gain on short address strings; model upgrade is trivial if needed | `qwen2.5:3b` |
| `transformers` in-process | Adds 2–3 GB to API process; blocks async event loop without process pool | Ollama sidecar via HTTP |
| `llama.cpp` directly | Manual binary build and GGUF management; no model library | Ollama |
| `scipy` / `sklearn` for DBSCAN | Heavy import for a single use case; PostGIS ST_ClusterDBSCAN already available | `ST_ClusterDBSCAN` via asyncpg |
| `VoteM8` / `CoVIRA` | Designed for molecular docking / bioinformatics — wrong domain | Custom weighted scoring with PostGIS |

---

### Version Compatibility (v1.2 Additions)

| Package / Extension | Compatible With | Notes |
|--------------------|----------------|-------|
| `symspellpy==6.9.0` | Python 3.9–3.13, `editdistpy` (auto-installed) | No conflict with existing stack |
| `ollama==0.6.1` | Python >=3.8, `httpx` (already present) | Requires httpx >=0.26.0 — verify `httpx==0.28.1` in lock file is compatible |
| `pg_trgm` | PostgreSQL 17 (contrib, bundled) | Idempotent `CREATE EXTENSION IF NOT EXISTS` |
| `fuzzystrmatch` | PostgreSQL 17 (contrib, already present from Tiger) | Already active; `CREATE EXTENSION IF NOT EXISTS` is safe no-op |
| `ollama/ollama:latest` | CPU + GPU; `OLLAMA_HOST=0.0.0.0:11434` default in container | Pin to version tag (e.g., `0.6.x`) in production |

---

### Sources (v1.2)

- [PostgreSQL 17 fuzzystrmatch official docs](https://www.postgresql.org/docs/17/fuzzystrmatch.html) — HIGH confidence; all function signatures verified directly
- [PostgreSQL pg_trgm official docs (current)](https://www.postgresql.org/docs/current/pgtrgm.html) — HIGH confidence; all operators, functions, index types verified directly
- [symspellpy PyPI](https://pypi.org/project/symspellpy/) — HIGH confidence; version 6.9.0 released 2025-03-09, Python 3.9–3.13
- [symspellpy GitHub](https://github.com/mammothb/symspellpy) — HIGH confidence; `load_dictionary()`, `load_bigram_dictionary()`, `create_dictionary_entry()`, `lookup_compound()` API verified
- [ollama PyPI](https://pypi.org/project/ollama/) — HIGH confidence; version 0.6.1, Python >=3.8, httpx-backed `AsyncClient`
- [Ollama structured outputs official docs](https://docs.ollama.com/capabilities/structured-outputs) — HIGH confidence; raw HTTP `format` parameter schema verified
- [ollama/ollama Docker Hub](https://hub.docker.com/r/ollama/ollama) — MEDIUM confidence; `OLLAMA_HOST=0.0.0.0:11434` default in container image
- [Qwen2.5 model on Ollama library](https://ollama.com/library/qwen2.5) — MEDIUM confidence; quantization sizes and memory requirements
- [Qwen2.5-3B hardware specs](https://apxml.com/models/qwen2-5-3b) — MEDIUM confidence; ~1.9 GB Q4_K_M, ~2.5 GB RAM, CPU inference 8–12 tok/s
- [spell-checkers-comparison repo](https://github.com/diffitask/spell-checkers-comparison) — MEDIUM confidence; symspellpy outperforms pyspellchecker on speed and accuracy benchmarks
- [EarthDaily geocoding consensus algorithm](https://earthdaily.com/blog/geocoding-consensus-algorithm-a-foundation-for-accurate-risk-assessment) — MEDIUM confidence; spatial clustering approach validated for multi-provider consensus

---

## v1.1 Milestone: Stack Additions for Local Providers

### Executive Finding

**No new Python libraries are required.** The full implementation of all three local providers (OpenAddresses, NAD, PostGIS Tiger) fits entirely within the existing dependency footprint. The critical insight is that each data source maps to capabilities already present:

| Provider | Data Format | Reading Method | Status |
|----------|-------------|----------------|--------|
| OpenAddresses | `.geojson.gz` (GeoJSONL) | stdlib `gzip` + `json` | In stdlib |
| NAD r21 TXT | CSV with BOM in zip | stdlib `csv.DictReader` + `zipfile` | In stdlib |
| NAD r21 FGDB | Esri File GDB | `fiona` OpenFileGDB driver | Already installed |
| PostGIS Tiger | PostgreSQL extension | `sqlalchemy.text()` + `asyncpg` | Already installed |
| Address parsing for lookup | Freeform → components | `usaddress` | Already in `uv.lock` (transitive dep) |

---

### Format Verification (Against Actual Files)

#### OpenAddresses `.geojson.gz` — GeoJSONL, not GeoJSON

Files are **newline-delimited GeoJSONL**, one Feature per line. `json.load(f)` raises `JSONDecodeError: Extra data` — do not use it. Confirmed from `US_GA_Bibb_Addresses_2026-03-20.geojson.gz`:

```
{"type":"Feature","properties":{"hash":"bed3195d","number":"489","street":"NORTHMINISTER DR",
 "unit":"","city":"MACON","district":"","region":"","postcode":"31204","id":"","accuracy":""},
 "geometry":{"type":"Point","coordinates":[-83.687444,32.872083]}}
```

Fields: `number` (house number), `street` (full street), `unit`, `city`, `postcode`. No state field — state is encoded in the filename (`US_GA_Bibb_*`). Coordinates are `[lng, lat]`.

Correct reading pattern:
```python
import gzip, json

with gzip.open(path, 'rt', encoding='utf-8') as f:
    for line in f:
        feature = json.loads(line)           # NOT json.load(f)
        props = feature['properties']
        lng, lat = feature['geometry']['coordinates']
```

#### NAD r21 TXT — CSV with BOM, 60 fields

Standard CSV, `utf-8-sig` encoding (byte-order mark). 7.3 GB zip containing `TXT/NAD_r21.txt`. Key address fields:

| Field | Content | Example |
|-------|---------|---------|
| `Add_Number` | House number integer | `1000` |
| `StNam_Full` | Full street name with type | `Sand Point Avenue` |
| `Post_City` | Mailing city | `Not stated` |
| `State` | 2-letter state code | `AK` |
| `Zip_Code` | ZIP (may have spaces) | `99661` |
| `Latitude` | Decimal degrees | `55.335591` |
| `Longitude` | Decimal degrees | `-160.502740` |

Streaming pattern (do NOT load full 7.3 GB into memory):
```python
import csv, zipfile, io

with zipfile.ZipFile('NAD_r21_TXT.zip') as z:
    with z.open('TXT/NAD_r21.txt') as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))
        for row in reader:
            lat = float(row['Latitude']) if row['Latitude'] else None
            lon = float(row['Longitude']) if row['Longitude'] else None
```

#### NAD r21 FGDB — Esri File GDB, readable with existing fiona

`fiona` 1.10.1 (already installed) supports the `OpenFileGDB` driver — no ESRI license required. Verified: `'OpenFileGDB'` is in `fiona.supported_drivers` in the project virtualenv.

The `.gdb` directory must be extracted from the zip before fiona can read it. Same schema as TXT.

**Decision: prefer TXT over FGDB for the runtime provider.** TXT is streamable from inside the zip without extraction. FGDB support belongs in the CLI import command only, not the live provider.

#### PostGIS Tiger Geocoder — SQL extensions, no Python library

The `postgis/postgis:17-3.5` Docker image includes Tiger geocoder binaries. One-time SQL to enable:

```sql
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS address_standardizer;
```

The `geocode()` function signature (unchanged since PostGIS 2.1):
```sql
geocode(address varchar, max_results int DEFAULT 10)
  RETURNS SETOF RECORD (addy norm_addy, geomout geometry, rating integer)
```

Calling from existing async session:
```python
from sqlalchemy import text

result = await session.execute(
    text("SELECT geomout, rating FROM geocode(:address, 1)"),
    {"address": normalized_address}
)
row = result.first()
# row.rating: integer, lower = better match; 0 is exact
# row.geomout: WKB geometry in NAD83 lon/lat
```

The Tiger schema must be on `search_path`. Add `tiger,tiger_data` to the DB `search_path` or use fully-qualified `tiger.geocode(...)`.

**Tiger data is not included in the Docker image** — it must be loaded separately via Census Bureau download scripts. The provider must check for Tiger availability at startup and surface a structured "not configured" response rather than raising an unhandled error.

#### Address Parsing for Local Lookups — `usaddress` already in lock file

`usaddress` 0.5.16 (released August 2025) is already locked in `uv.lock` as a transitive dependency of `usaddress-scourgify`. Use it directly without adding to `pyproject.toml`.

```python
import usaddress

tags, address_type = usaddress.tag("489 Northminister Dr, Macon GA 31204")
# tags: OrderedDict([('AddressNumber', '489'), ('StreetName', 'Northminister'),
#        ('StreetNamePostType', 'Dr'), ('PlaceName', 'Macon'), ('StateName', 'GA'),
#        ('ZipCode', '31204')])
```

Use this to decompose freeform input before field-matching against NAD or OA data. Do not add `usaddress` to `pyproject.toml` — it is already available.

---

### What NOT to Add (v1.1)

| Do Not Add | Why | Use Instead |
|------------|-----|-------------|
| `pyogrio` | Faster than fiona for bulk DataFrame reads, but adds geopandas dependency chain (~200 MB). Providers stream single records — fiona overhead is negligible | `fiona` (already installed) |
| `geopandas` | Heavy: numpy + pandas + shapely + pyogrio. Providers are stream-and-filter, not bulk DataFrame operations | stdlib + fiona |
| `shapely` (explicit) | No geometric operations needed in providers. Coordinates are simple floats; distance checks belong in PostGIS | Not needed |
| `rtree` / `libspatialindex` | In-memory nearest-neighbor for millions of points is only needed if loading all data into application memory — don't do this. Import to PostGIS and use GIST indexes | PostGIS GIST indexes |
| `pandas` | NAD TXT is 7.3 GB; chunked pandas adds complexity with no benefit over `csv.DictReader` streaming | stdlib `csv.DictReader` |
| `usaddress` in pyproject.toml | Already a transitive dep — adding explicitly creates version conflict risk | `import usaddress` directly |
| `geocoder` (PyPI) | In `uv.lock` as a transitive dep but is a separate geocoding library. Do not use in providers | Custom provider ABCs |

---

### Direct-Return Pipeline: No New Libraries Required

The requirement for a "direct-return pipeline that bypasses DB caching for local providers" is a service-layer concern, not a library concern. The existing `GeocodingProvider` and `ValidationProvider` ABCs support this — local providers implement the same ABCs but the calling service skips the cache write step. No new infrastructure needed.

---

### Tiger Setup Script: Not a Migration

Tiger extension creation and data loading are operational setup, not schema migrations. Do not add to Alembic. Implement as `scripts/setup_tiger.sql` or `scripts/load_tiger.sh` that:
1. Creates three SQL extensions
2. Updates `tiger.loader_variables` with TIGER data year and staging dir
3. Calls `Loader_Generate_Nation_Script()` / `Loader_Generate_Script()` for required states
4. Documents that data download is a one-time manual step per deployment

---

### Spatial Indexing for Imported OA/NAD Data

If OA and NAD data are imported into PostGIS via the existing CLI (recommended), spatial indexing is free — the existing GIST index pattern already applies. Implement providers against PostGIS tables, not against raw files streamed at query time.

If file-based lookup is required (no import step), stream and filter by pre-indexing in Python dicts keyed by state+zip. No spatial index library needed for exact address matching; spatial indexing only matters for nearest-neighbor / bounding-box queries, which are not in scope.

---

## Version Compatibility

| Package | Locked Version | Notes |
|---------|---------------|-------|
| `fiona` | 1.10.1 | OpenFileGDB driver confirmed present in venv |
| `usaddress` | 0.5.16 (transitive) | Released Aug 2025, locked in uv.lock |
| PostGIS | 3.5 | `geocode()` signature unchanged since PostGIS 2.1 |
| `sqlalchemy` | 2.0.x | `text()` + `await session.execute()` confirmed working |
| `asyncpg` | 0.31.0 | No changes needed for Tiger calls |

---

## Sources (v1.1)

- File inspection: `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` — confirmed GeoJSONL line-delimited format, field schema (HIGH confidence)
- File inspection: `data/NAD_r21_TXT.zip/TXT/schema.ini` + `NAD_r21.txt` — confirmed 60-field CSV schema, BOM encoding (HIGH confidence)
- `fiona.supported_drivers` in project venv — confirmed `OpenFileGDB` driver available in fiona 1.10.1 (HIGH confidence)
- `uv.lock` — confirmed `usaddress==0.5.16` already locked (HIGH confidence)
- [PostGIS geocode() function docs](https://postgis.net/docs/Geocode.html) — function signature, return type (HIGH confidence)
- [PostGIS Tiger setup — RustProof Labs](https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup) — extension creation steps (MEDIUM confidence)
- [GDAL OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html) — no ESRI license required for read (HIGH confidence)
- [pyogrio about](https://pyogrio.readthedocs.io/en/latest/about.html) — why it's not needed here (HIGH confidence)
- [postgis/docker-postgis](https://github.com/postgis/docker-postgis) — Tiger extension included in official image (MEDIUM confidence)

---

## v1.0 Stack (Pre-existing, Validated — No Changes)

The entries below document the validated v1.0 stack. No changes are required for v1.1.

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12+ | Runtime | Matches other CivPulse APIs; 3.12 has significant perf improvements over 3.11 |
| FastAPI | 0.135+ | HTTP API framework | Pre-decided; async-native, Pydantic v2 integration, OpenAPI autodoc |
| Pydantic | v2 (2.x) | Request/response models, validation | Ships with FastAPI; v2 significantly faster than v1 |
| Loguru | 0.7+ | Structured logging | Pre-decided; simpler than stdlib logging |
| Typer | 0.24+ | CLI commands | Pre-decided; pairs with FastAPI for management commands |

### Database Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 17 | Primary datastore | Pre-decided; required for PostGIS |
| PostGIS | 3.5 | Spatial types and queries | Pre-decided; Geography(POINT,4326) provides distance-in-meters semantics |
| GeoAlchemy2 | 0.18.4 | SQLAlchemy spatial type integration | Standard bridge; handles WKB serialization and Alembic migration types |
| SQLAlchemy | 2.0+ | ORM / query builder | Async support via asyncpg; required by GeoAlchemy2 |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async Postgres driver; required for SQLAlchemy async engine |
| psycopg2-binary | 2.9.11 | Synchronous Postgres driver for Alembic | Alembic requires synchronous driver; asyncpg cannot be used for migrations |
| Alembic | 1.18.4 | Schema migrations | Standard SQLAlchemy migration tool |

### Address Parsing and HTTP

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| usaddress-scourgify | 0.6.0 | USPS-standard address normalization | Offline normalization for cache key generation; no external API needed |
| httpx | 0.28.1 | Async HTTP client for external providers | Async-native; used for Census Geocoder provider |
| fiona | 1.10.1 | Spatial file I/O (SHP, GDB, KML) | Used in GIS import CLI; OpenFileGDB driver for NAD FGDB |

---
*Stack research for: CivPulse Geo API v1.3 Production Readiness & Deployment — new capabilities*
*Researched: 2026-03-29*


---

## v1.4 Milestone: Stack Additions for Self-Hosted OSM Stack

**Research date:** 2026-04-04
**Scope:** New capabilities only — OSM data pipeline, raster tile serving, Nominatim geocoding/POI/reverse-geocoding, and routing. Everything from v1.0–v1.3 is unchanged and validated. No existing Python packages are removed or upgraded by this milestone.

**Confidence:** HIGH (osm2pgsql — official releases page), HIGH (Nominatim — official docs + PyPI), HIGH (OSRM — GitHub releases), HIGH (overv/openstreetmap-tile-server — GitHub), MEDIUM (mediagis/nominatim external DB — community issue reports), MEDIUM (Python integration patterns — community + official FastAPI patterns)

---

### Executive Finding

**No new Python runtime packages are required.** The OSM stack consists entirely of infrastructure sidecar services (Docker images) that the existing FastAPI app calls via HTTP using the already-present `httpx.AsyncClient`. One new Python provider class (OSM Nominatim geocoding provider) plugs into the existing cascade pipeline using zero new library dependencies. The data pipeline (PBF import) is a CLI-triggered one-time operation, not runtime code.

The v1.4 additions are:

1. **overv/openstreetmap-tile-server** — raster tile server sidecar (Docker Compose service)
2. **mediagis/nominatim** — geocoding/POI/reverse-geocoding sidecar (Docker Compose service)
3. **osrm/osrm-backend** — routing engine sidecar, two instances: one `car` profile, one `foot` profile (Docker Compose services)
4. **NominatimGeocodingProvider** — new provider class (Python, no new dependencies)
5. **OSM data pipeline** — Typer CLI command + shell script for PBF download and import (no new dependencies)

---

### Raster Tile Server

**Chosen: `overv/openstreetmap-tile-server` v2.3.0**

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `overv/openstreetmap-tile-server` | 2.3.0 | Docker Compose service | Self-contained OSM raster tile server exposing `/{z}/{x}/{y}.png` tiles for Leaflet |

**What it bundles:**
- `osm2pgsql` (OSM data import to PostGIS)
- `renderd` + `mod_tile` (tile rendering daemon + Apache module)
- `Mapnik` (rendering engine using openstreetmap-carto style)
- Embedded PostgreSQL/PostGIS (used internally for tile rendering data — **separate from the geo-api application database**)
- Apache HTTP server (serves tiles via `mod_tile`)

**Why this image over bare mod_tile + Mapnik + Apache:**
The `overv` image provides a single-container, batteries-included tile stack that handles all configuration (renderd.conf, mapnik style, Postgres tuning) with a documented Docker Compose pattern. Setting up Apache + mod_tile + Mapnik + renderd manually from the switch2osm guide requires 2–3 hours of system configuration that adds no value to the geo-api project. The image is well-maintained, actively used in production OSM self-hosting deployments, and the source is open on GitHub. Confidence: HIGH.

**Docker Compose pattern:**

```yaml
# Import service (one-shot, run before server)
tile-import:
  image: overv/openstreetmap-tile-server:2.3.0
  volumes:
    - ./data/georgia-latest.osm.pbf:/data/region.osm.pbf
    - osm-data:/data/database/
  command: import
  environment:
    THREADS: "4"
    FLAT_NODES: "false"   # set true for planet-scale imports; Georgia at ~330MB does not need it

# Tile server (persistent service)
tile-server:
  image: overv/openstreetmap-tile-server:2.3.0
  volumes:
    - osm-data:/data/database/
    - osm-tiles:/data/tiles/
  ports:
    - "8080:80"
  environment:
    UPDATES: "disabled"
    ALLOW_CORS: "true"
    THREADS: "4"
  restart: unless-stopped
  depends_on:
    tile-import:
      condition: service_completed_successfully

volumes:
  osm-data:
  osm-tiles:
```

**Tile URL pattern for Leaflet:**
```
http://{tile-server-host}:8080/tile/{z}/{x}/{y}.png
```

**Key environment variables:**
- `UPDATES`: `disabled` (for static Georgia extract) — no replication polling
- `ALLOW_CORS`: `true` — required for browser-side Leaflet
- `THREADS`: Match available CPU cores (4 is safe default)
- `FLAT_NODES`: `false` for state-level extracts; `true` only needed for planet-scale

**Georgia PBF source:** `https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf` (~330 MB as of late 2025). Download via the OSM data pipeline CLI command before first import.

**Important: Tile rendering database is isolated.** The `overv` container runs its own PostgreSQL instance internally. It does NOT connect to the geo-api application database. They share no schema. Keep them completely separate — do not attempt to share the PostGIS instance.

---

### Geocoding / POI Search / Reverse Geocoding

**Chosen: `mediagis/nominatim` 5.2 Docker image + `NominatimGeocodingProvider` (new provider class)**

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `mediagis/nominatim` | 5.2 | Docker Compose service | Self-hosted Nominatim geocoding/reverse-geocoding/POI search API |

**What Nominatim 5.2 provides (HIGH confidence — official docs):**

- Forward geocoding: address string → `(lat, lon)` (plugs into cascade pipeline as `NominatimGeocodingProvider`)
- Reverse geocoding: `(lat, lon)` → address string (new endpoint capability)
- POI search: find amenities, landmarks, businesses by name or type near a location
- Structured search: `street=`, `city=`, `county=`, `state=`, `country=` parameter-based lookup
- HTTP API: `/search`, `/reverse`, `/lookup`, `/details` endpoints — all JSON
- Built on OSM data — same source as the tile server

**Why Nominatim over custom PostGIS geocoder:**
Nominatim has 15+ years of production use as the geocoder for openstreetmap.org. It handles address ambiguity, abbreviations, POI indexing, and the full OSM feature graph out of the box. Building equivalent functionality on raw PostGIS + osm2pgsql data would require months of query engineering. For the geo-api cascade, Nominatim is a single additional HTTP provider call — the integration cost is minimal.

**Why version 5.2 not 5.3:**
`mediagis/nominatim:5.2` is the current stable Docker image tag as confirmed from the mediagis/nominatim-docker README. The nominatim-api PyPI package is at 5.3.0 (April 3, 2026), but the mediagis Docker image lags by one minor version. Use `5.2` for the Docker deployment. The `nominatim-api` PyPI package is NOT used — see below.

**Database isolation:** Nominatim requires its own PostgreSQL database (`nominatim` db). The mediagis image bundles its own PostgreSQL. While `NOMINATIM_DATABASE_DSN` theoretically allows pointing at an external PostgreSQL, there are reported issues (mediagis/nominatim-docker issue #615) where external DSN is ignored during import. Use the bundled PostgreSQL. Keep Nominatim's PostgreSQL instance completely separate from the geo-api application database.

**Docker Compose pattern:**

```yaml
nominatim:
  image: mediagis/nominatim:5.2
  ports:
    - "8081:8080"
  environment:
    PBF_URL: ""          # leave empty when using local file
    PBF_PATH: /nominatim/data/georgia-latest.osm.pbf
    NOMINATIM_PASSWORD: nominatim_secret
    REPLICATION_URL: ""  # disabled — static Georgia extract
    IMPORT_WIKIPEDIA: "false"   # reduces import time; not needed for address geocoding
    IMPORT_STYLE: "extratags"   # includes amenity/POI tags needed for POI search
  volumes:
    - ./data/georgia-latest.osm.pbf:/nominatim/data/georgia-latest.osm.pbf:ro
    - nominatim-data:/var/lib/postgresql/14/main
  restart: unless-stopped

volumes:
  nominatim-data:
```

**Python integration — no new dependencies:**

The `NominatimGeocodingProvider` calls the Nominatim HTTP `/search` endpoint via the existing `httpx.AsyncClient`. This is identical to how the Census Geocoder provider works today. No new Python packages are required.

Do NOT install `nominatim-api` (the PyPI package). That package is for running Nominatim as a Python ASGI app connected to a local Nominatim database on the same host — it is not a client library. For geo-api, Nominatim is a sidecar service accessed over HTTP. Use `httpx`.

**Example provider sketch (no new imports):**

```python
# src/civpulse_geo/providers/nominatim.py
import httpx
from .base import GeocodingProvider, GeocodingResult

class NominatimGeocodingProvider(GeocodingProvider):
    BASE_URL = "http://nominatim:8080"   # Docker Compose service name

    async def geocode(self, address: str) -> list[GeocodingResult]:
        params = {"q": address, "format": "jsonv2", "limit": 5,
                  "countrycodes": "us", "addressdetails": 1}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.BASE_URL}/search", params=params)
            resp.raise_for_status()
        return [self._parse(r) for r in resp.json()]
```

**Reverse geocoding endpoint:**

Nominatim `/reverse?lat={lat}&lon={lon}&format=jsonv2` — call via `httpx`. No additional provider base class changes needed; implement as a separate `/geocode/reverse` FastAPI endpoint that calls Nominatim directly.

**POI search:**

Nominatim `/search?q={poi_name}&format=jsonv2&amenity={type}&bounded=1&viewbox={bbox}` — same pattern. Implement as `/search/poi` endpoint.

---

### Routing Engine

**Chosen: `osrm/osrm-backend` v6.0.0 — two Docker Compose instances (car + foot)**

| Component | Version | Deployment | Purpose |
|-----------|---------|-----------|---------|
| `osrm/osrm-backend` | v6.0.0 | Docker Compose service (×2) | Self-hosted OSRM routing for driving (car profile) and walking (foot profile) |

**Why OSRM over Valhalla:**

| Criterion | OSRM | Valhalla |
|-----------|------|---------|
| Routing speed | Sub-millisecond for regional routes (highest confidence) | Fast but slower for matrix queries |
| Setup complexity | Pre-process PBF once; simple Docker run | More configuration, thinner Docker docs |
| Walking + driving | foot.lua + car.lua profiles, both well-tested | Both supported but profile tuning more complex |
| Memory use | Higher (pre-computed graph in RAM) | Lower (operates on raw OSM data) |
| API surface | Focused: route, table, match, nearest, trip | Broader: isochrone, elevation, time-aware |

For CivPulse's use case (canvass routing for run-api, polling place directions for vote-api) OSRM's speed advantage is decisive. Routing requests will be small (1–10 waypoints), not matrix operations, so Valhalla's memory advantage is irrelevant. OSRM's Docker documentation and profiles are more mature for a state-level deployment. Confidence: MEDIUM (comparative analysis; OSRM is more widely deployed for this scale).

**Why two instances (not one multi-profile instance):**
OSRM requires PBF pre-processing at startup for a single profile — you cannot serve car and foot from the same container. The standard pattern is two separate containers, each pre-processed with a different profile and bound to a different port.

**Docker Compose pattern:**

```yaml
# One-time data prep (run as CLI command before compose up):
# docker run -t -v $(pwd)/data:/data osrm/osrm-backend:v6.0.0 osrm-extract -p /opt/car.lua /data/georgia-latest.osm.pbf
# docker run -t -v $(pwd)/data:/data osrm/osrm-backend:v6.0.0 osrm-partition /data/georgia-latest.osrm
# docker run -t -v $(pwd)/data:/data osrm/osrm-backend:v6.0.0 osrm-customize /data/georgia-latest.osrm
# Repeat for foot.lua → produces georgia-foot.osrm

osrm-car:
  image: osrm/osrm-backend:v6.0.0
  volumes:
    - ./data:/data
  ports:
    - "5000:5000"
  command: osrm-routed --algorithm mld /data/georgia-latest.osrm
  restart: unless-stopped

osrm-foot:
  image: osrm/osrm-backend:v6.0.0
  volumes:
    - ./data:/data
  ports:
    - "5001:5000"
  command: osrm-routed --algorithm mld /data/georgia-foot.osrm
  restart: unless-stopped
```

**Python integration — no new dependencies:**

OSRM exposes a REST API at `/route/v1/{profile}/{coordinates}`. Call via existing `httpx`. Implement `/directions` FastAPI endpoint that proxies to the appropriate OSRM instance based on `mode` parameter (`driving` → port 5000, `walking` → port 5001).

**OSRM API response contains:**
- `routes[].geometry` (encoded polyline or GeoJSON)
- `routes[].legs[].steps[]` (turn-by-turn instructions)
- `routes[].distance` (meters)
- `routes[].duration` (seconds)

**v6.0.0 notable change:** Pedestrian routing now includes highways marked as `platform` in the foot profile — relevant for urban walking routes in Atlanta and Macon. (HIGH confidence — OSRM v6.0.0 release notes, April 21, 2025.)

---

### OSM Data Pipeline

**No new Python packages.** Pipeline uses Typer (already installed), subprocess calls to Docker CLI, and `httpx` for PBF download.

**OSM data source:** Geofabrik Georgia extract — `https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf`
- Size: ~330 MB as of late 2025
- Updated daily by Geofabrik
- Covers all of Georgia (USA)
- Suitable for osm2pgsql (tile server), Nominatim, and OSRM

**Pipeline flow:**

```
1. download_pbf()       → curl/httpx download to ./data/georgia-latest.osm.pbf
2. import_tiles()       → docker run overv/openstreetmap-tile-server:2.3.0 import
3. import_nominatim()   → docker-compose up nominatim (first run triggers import automatically)
4. preprocess_osrm()    → docker run osrm/osrm-backend:v6.0.0 osrm-extract/partition/customize (×2 profiles)
```

**CLI command (Typer):**

```python
# uv run python -m civpulse_geo.cli osm import-data [--skip-download] [--profile car|foot|both]
```

This follows the existing CLI pattern (Typer + Rich) used for GIS data import commands. No new packages needed.

---

### New Packages Summary (v1.4)

**Zero new Python runtime packages. Zero new Python dev packages.**

| Component | Type | Version | Install |
|-----------|------|---------|---------|
| `overv/openstreetmap-tile-server` | Docker image | 2.3.0 | `docker pull overv/openstreetmap-tile-server:2.3.0` |
| `mediagis/nominatim` | Docker image | 5.2 | `docker pull mediagis/nominatim:5.2` |
| `osrm/osrm-backend` | Docker image | v6.0.0 | `docker pull osrm/osrm-backend:v6.0.0` |
| `NominatimGeocodingProvider` | New Python class | — | Implement in `src/civpulse_geo/providers/nominatim.py` |
| OSM data pipeline CLI | New Typer command | — | Implement in `src/civpulse_geo/cli/osm.py` |

---

### What NOT to Add (v1.4)

| Do Not Add | Why | Use Instead |
|------------|-----|-------------|
| `nominatim-api` (PyPI) | That package runs Nominatim as an in-process ASGI app on the same host as the database — it is NOT a client library. geo-api calls a remote Nominatim sidecar over HTTP. | `httpx` (already installed) to call `mediagis/nominatim` HTTP API |
| `geopy` | Wrapper around public Nominatim API — not appropriate for a self-hosted instance. Adds an abstraction layer with no value. | Direct `httpx` calls to the sidecar |
| Valhalla routing engine | Heavier setup, thinner Docker documentation, no significant feature advantage for the CivPulse routing use case (small waypoint counts, no isochrone needed) | `osrm/osrm-backend` |
| MapTiler Server | Commercial; requires license for production. Adds cost and vendor dependency. | `overv/openstreetmap-tile-server` (Apache-2.0, free) |
| OpenMapTiles (vector tiles) | Leaflet 1.9.4 uses raster tiles only. Vector tiles require a GL renderer (MapLibre GL) which is a separate frontend decision outside this milestone's scope. | `overv/openstreetmap-tile-server` raster tiles |
| `osm2pgsql` Python bindings | No mature Python bindings exist. `osm2pgsql` is a CLI tool; invoke via subprocess or Docker CLI command from the Typer pipeline. | Docker CLI invocation via `subprocess` or direct Docker Compose |
| Shared PostgreSQL for Nominatim | mediagis/nominatim has known issues with external DB via `NOMINATIM_DATABASE_DSN` during import (issue #615). Simplest and most reliable path is bundled PostgreSQL. | Let `mediagis/nominatim` manage its own PostgreSQL |
| Shared PostgreSQL for tile server | `overv/openstreetmap-tile-server` uses a different schema (osm2pgsql rendering schema) and heavily tunes its own PostgreSQL for tile rendering. Merging with geo-api DB creates schema conflicts and tuning conflicts. | Keep tile server PostgreSQL fully separate |
| `TileJSON` or `WMTS` endpoint from geo-api | Tile serving is handled entirely by the `overv` container. geo-api does not need to proxy or wrap tiles. | Let Leaflet connect directly to the tile server container |
| OSRM matrix API for batch routing | Matrix operations are expensive and not needed for the canvass/polling use case. The `/route/v1/` endpoint with 2–10 waypoints covers all current use cases. | OSRM `/route/v1/` only |

---

### Integration Points with Existing FastAPI Stack

| Existing Component | v1.4 Touch Point |
|-------------------|-----------------|
| `CascadeOrchestrator` | Add `NominatimGeocodingProvider` to provider registry with appropriate weight (recommend weight=3, below Census but above Tiger for Georgia addresses) |
| `providers/base.py` | No changes — new provider inherits existing `GeocodingProvider` ABC |
| `httpx.AsyncClient` | Reuse for Nominatim + OSRM HTTP calls — no new HTTP client |
| `Docker Compose` dev environment | Add `tile-import`, `tile-server`, `nominatim`, `osrm-car`, `osrm-foot` services |
| `Typer CLI` | Add `osm import-data` command to existing CLI module |
| `/health/ready` endpoint | Add Nominatim and OSRM HTTP reachability checks to readiness probe |

---

### Version Compatibility (v1.4)

| Component | Requires | Geo-API Has | Compatible |
|-----------|----------|-------------|------------|
| `overv/openstreetmap-tile-server:2.3.0` | Docker, volume mounts | Docker Compose dev env | Yes — new service only |
| `mediagis/nominatim:5.2` | PostgreSQL 12+ (bundled), PostGIS 3+ (bundled) | N/A — separate container | Yes |
| `osrm/osrm-backend:v6.0.0` | PBF pre-processed data, Alpine Linux | N/A — separate container | Yes |
| `NominatimGeocodingProvider` | Python 3.12+, `httpx` >= 0.23.0 | Python 3.12, httpx 0.28.1 | Yes |
| Geofabrik Georgia PBF | Disk: ~330 MB download, ~3 GB Nominatim DB, ~500 MB OSRM graph | Dev host disk | Verify host has ≥5 GB free |

---

### Sources (v1.4)

- [osm2pgsql 2.2.0 release notes](https://osm2pgsql.org/releases/2-2-0.html) — latest stable 2.2.0, Sep 17, 2025 (HIGH confidence)
- [Nominatim 5.3.0 on PyPI](https://pypi.org/project/nominatim-api/) — current PyPI version; confirmed `nominatim-api` is NOT a client library (HIGH confidence, official)
- [Nominatim 5.3.0 installation docs](https://nominatim.org/release-docs/latest/admin/Installation/) — system requirements, osm2pgsql 1.8+ required (HIGH confidence, official)
- [mediagis/nominatim-docker GitHub](https://github.com/mediagis/nominatim-docker) — current stable image tag 5.2 (HIGH confidence, official Docker image)
- [mediagis/nominatim external PostgreSQL issue #615](https://github.com/mediagis/nominatim-docker/issues/615) — external DSN ignored during import; use bundled PostgreSQL (MEDIUM confidence, community report)
- [Nominatim Python deployment docs](https://nominatim.org/release-docs/latest/admin/Deployment-Python/) — `nominatim-api` is an ASGI server package, not a client library (HIGH confidence, official)
- [OSRM v6.0.0 release](https://github.com/Project-OSRM/osrm-backend/releases/tag/v6.0.0) — latest stable, April 21, 2025; foot profile enhancement (HIGH confidence, official)
- [OSRM Docker Hub](https://hub.docker.com/r/osrm/osrm-backend/) — image available (HIGH confidence, official)
- [OSRM car/foot profiles documented](https://github.com/Project-OSRM/osrm-backend) — car.lua, foot.lua, bicycle.lua profiles available (HIGH confidence, official)
- [overv/openstreetmap-tile-server GitHub](https://github.com/Overv/openstreetmap-tile-server) — v2.3.0 latest release March 18, 2023; bundles renderd/mod_tile/Mapnik/Apache/osm2pgsql (HIGH confidence, official)
- [Geofabrik Georgia download page](https://download.geofabrik.de/north-america/us/georgia.html) — `georgia-latest.osm.pbf`, ~330 MB, updated daily (HIGH confidence, official)
- [switch2osm tile server guide](https://switch2osm.org/serving-tiles/) — Apache + mod_tile + Mapnik + osm2pgsql canonical stack (HIGH confidence, community standard)
- [Nominatim Advanced Installations — external DB](https://nominatim.org/release-docs/latest/admin/Advanced-Installations/) — `NOMINATIM_DATABASE_DSN` supports external PostgreSQL (HIGH confidence, official; but Docker image support is MEDIUM due to known import bug)
- [Valhalla vs OSRM comparison (StackShare)](https://stackshare.io/stackups/osrm-vs-valhalla) — OSRM faster for routing; Valhalla more flexible (MEDIUM confidence, community)
- [OSRM Docker Recipes wiki](https://github.com/Project-OSRM/osrm-backend/wiki/Docker-Recipes) — single-profile pattern; multi-profile requires separate containers (HIGH confidence, official)

---
*Stack research for: CivPulse Geo API v1.4 Self-Hosted OSM Stack — new capabilities only*
*Researched: 2026-04-04*
