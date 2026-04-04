# Phase 22: Observability - Research

**Researched:** 2026-03-30
**Domain:** OpenTelemetry + Prometheus + Loguru structured logging (Python/FastAPI)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: Env-based log format switching** — `log_format: str = "auto"` in Settings (`auto|json|text`). JSON when `ENVIRONMENT != "local"`, human-readable otherwise. JSON output includes: `timestamp`, `level`, `message`, `request_id`, `trace_id`, `span_id`, `service`, `environment`, `module`, `function`, `line`. Implemented in `src/civpulse_geo/observability/logging.py`, called from `main.py` lifespan.
- **D-02: Full three-tier Prometheus metrics** — `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_progress` (Tier 1); `geo_provider_*`, `geo_cascade_*`, `geo_cache_*` (Tier 2); `geo_llm_*`, `geo_batch_size` (Tier 3). Library: `prometheus-client`. `/metrics` endpoint route.
- **D-03: Manual spans for cascade stages + providers** — Auto-instrumentation for FastAPI, SQLAlchemy (asyncpg), httpx. Manual spans at each of 7 cascade stage boundaries and each `provider.geocode()` call. Tracer via `opentelemetry.trace.get_tracer("civpulse-geo")`. OTLP exporter via `OTEL_EXPORTER_OTLP_ENDPOINT` env var.
- **D-04: Accept-or-generate request IDs** — Middleware checks `X-Request-ID` header; uses if present, generates UUID4 if absent. Binds `request_id` via `logger.contextualize(request_id=...)`. Sets `X-Request-ID` response header. Health/readiness excluded.
- **Logging framework**: Loguru (already used in 7+ modules, no migration).
- **OTel + Loguru incompatibility**: `opentelemetry-instrumentation-logging` has no effect on Loguru — must use `logger.configure(patcher=add_otel_context)` pattern.
- **Observability stack targets**: Logs → stdout → Grafana Alloy → Loki; Traces → OTLP → Tempo; Metrics → `/metrics` → VictoriaMetrics.
- **New modules**: `observability/logging.py`, `observability/tracing.py`, `observability/metrics.py`, `middleware/request_id.py`.
- **New dependencies**: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-instrumentation-httpx`, `prometheus-client`.

### Claude's Discretion

No open discretion items. All major decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- LLM token count tracking as span attributes
- Custom Grafana dashboards (infrastructure concern, not app code)
- Alerting rules for VictoriaMetrics (ops concern)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | Structured JSON logging via Loguru to stdout with per-request request_id correlation | Loguru custom JSON sink pattern + patcher for trace_id injection; `logger.contextualize()` for request_id binding |
| OBS-02 | Prometheus /metrics endpoint exposed for VictoriaMetrics scraping | `prometheus-client` 0.24.1 with `generate_latest()` route; single-process `Response` handler avoids trailing-slash redirect issue |
| OBS-03 | OpenTelemetry traces exported via OTLP to Tempo with FastAPI/SQLAlchemy auto-instrumentation | `opentelemetry-sdk` 1.40.0 + `opentelemetry-instrumentation-fastapi` 0.61b0 + SQLAlchemy `engine.sync_engine` pattern + OTLP gRPC exporter |
| OBS-04 | Loguru trace_id/span_id injection via custom middleware for log-trace correlation in Grafana | `logger.configure(patcher=add_otel_context)` reads `get_current_span()` at log time; request-ID middleware binds `request_id` via `logger.contextualize()` |
</phase_requirements>

---

## Summary

Phase 22 adds the three observability pillars (logs, metrics, traces) to the civpulse-geo FastAPI service. All architectural decisions are locked in CONTEXT.md, so research focuses on exact API usage, version selection, pitfalls, and testability.

The OTel Python ecosystem uses beta versioning (e.g., `0.61b0`) for contrib instrumentation packages that correspond to stable SDK `1.40.0`. All packages are released simultaneously and must stay version-locked. The critical Loguru integration gap — that `opentelemetry-instrumentation-logging` has no effect on Loguru — is confirmed by both the OTel GitHub issue tracker and community documentation. The correct pattern is `logger.configure(patcher=add_otel_context)` which reads `get_current_span()` dynamically at log-emit time.

For Prometheus, the standard `make_asgi_app()` mount introduces a 307 redirect (`/metrics` → `/metrics/`). The clean workaround for single-process uvicorn is a plain `Response` route using `generate_latest()` + `CONTENT_TYPE_LATEST`. Multiprocess mode (PROMETHEUS_MULTIPROC_DIR) is not needed since this is a single-worker K8s pod.

**Primary recommendation:** Use `opentelemetry-sdk==1.40.0` / `opentelemetry-instrumentation-fastapi==0.61b0` / `prometheus-client==0.24.1`. Wire everything in `main.py` lifespan: OTel TracerProvider setup first, then FastAPIInstrumentor, then request-ID middleware, then Loguru patcher.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| opentelemetry-api | 1.40.0 | Tracer/span API surface | Stable API; locked decision |
| opentelemetry-sdk | 1.40.0 | TracerProvider, BatchSpanProcessor | Stable SDK; required for resource/exporter setup |
| opentelemetry-exporter-otlp-proto-grpc | 1.40.0 | Sends traces to Tempo via gRPC OTLP | Locked decision; gRPC preferred for Tempo |
| opentelemetry-instrumentation-fastapi | 0.61b0 | Auto-instruments HTTP spans | Locked decision; 0.61b0 = contrib paired with SDK 1.40.0 |
| opentelemetry-instrumentation-sqlalchemy | 0.61b0 | Auto-instruments DB spans | Locked decision; pairs with SDK 1.40.0 |
| opentelemetry-instrumentation-httpx | 0.61b0 | Auto-instruments outbound HTTP | Locked decision; covers Census/Ollama calls |
| prometheus-client | 0.24.1 | Metrics registry + exposition | Locked decision; official Python Prometheus client |
| loguru | 0.7.3 | Structured logging (already installed) | Already in use; no migration needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| opentelemetry-instrumentation-asyncpg | 0.61b0 | Driver-level asyncpg spans | Optional — adds spans at driver level below SQLAlchemy; use if SQLAlchemy spans miss queries |
| grpcio | 1.80.0 | gRPC transport (pulled by otlp-proto-grpc) | Transitive dependency of `opentelemetry-exporter-otlp-proto-grpc`; will auto-install |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| opentelemetry-exporter-otlp-proto-grpc | opentelemetry-exporter-otlp-proto-http | HTTP is simpler for dev; gRPC is locked decision for Tempo |
| prometheus-client make_asgi_app() | prometheus-fastapi-instrumentator | Locked decision for custom metrics; instrumentator only handles HTTP tier |
| Custom JSON sink | loguru serialize=True | serialize=True produces nested structure; custom sink gives exact field control (locked decision) |

**Installation:**
```bash
uv add opentelemetry-api==1.40.0 opentelemetry-sdk==1.40.0 \
  opentelemetry-exporter-otlp-proto-grpc==1.40.0 \
  opentelemetry-instrumentation-fastapi==0.61b0 \
  opentelemetry-instrumentation-sqlalchemy==0.61b0 \
  opentelemetry-instrumentation-httpx==0.61b0 \
  prometheus-client==0.24.1
```

**Version verification (as of 2026-03-30):**
- `opentelemetry-sdk`: 1.40.0 (PyPI verified)
- `opentelemetry-api`: 1.40.0 (PyPI verified)
- `opentelemetry-exporter-otlp-proto-grpc`: 1.40.0 (PyPI verified)
- `opentelemetry-instrumentation-fastapi`: 0.61b0 (PyPI verified, latest pre-release March 2026)
- `opentelemetry-instrumentation-sqlalchemy`: 0.61b0 (PyPI verified)
- `opentelemetry-instrumentation-httpx`: 0.61b0 (PyPI verified)
- `prometheus-client`: 0.24.1 (PyPI verified)

---

## Architecture Patterns

### Recommended Project Structure

```
src/civpulse_geo/
├── observability/
│   ├── __init__.py
│   ├── logging.py       # Loguru JSON sink + OTel patcher
│   ├── tracing.py       # TracerProvider + FastAPIInstrumentor + SQLAlchemy
│   └── metrics.py       # Prometheus metric definitions (registry)
├── middleware/
│   ├── __init__.py
│   └── request_id.py    # X-Request-ID accept/generate middleware
└── api/
    └── metrics.py       # GET /metrics route (generate_latest)
```

### Pattern 1: OTel TracerProvider Setup (tracing.py)

**What:** Initialize TracerProvider with Resource, BatchSpanProcessor, and OTLPSpanExporter. Call FastAPIInstrumentor and SQLAlchemy instrumentation.
**When to use:** Called once at lifespan startup, before `yield`. Shutdown called after `yield`.

```python
# Source: opentelemetry-python GitHub + community guides (verified Feb 2026)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

def setup_tracing(app, settings, sync_engine) -> TracerProvider:
    resource = Resource(attributes={
        SERVICE_NAME: "civpulse-geo",
        SERVICE_VERSION: settings.git_commit,
        "deployment.environment": settings.environment,
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/health/live,/health/ready,/metrics",
    )
    SQLAlchemyInstrumentor().instrument(
        engine=sync_engine,
        service="civpulse-geo",
        enable_commenter=True,
    )
    HTTPXClientInstrumentor().instrument()
    return provider

def teardown_tracing(provider: TracerProvider) -> None:
    provider.shutdown()
```

### Pattern 2: Loguru OTel Patcher + JSON Sink (logging.py)

**What:** Configure Loguru once with a custom JSON serializer sink and an OTel patcher that injects trace_id/span_id at log-emit time.
**When to use:** Called before any `logger.info()` calls in lifespan startup.

```python
# Source: Loguru GitHub Issue #1222 (Delgan/loguru) + OTel Issue #3615
import sys
import json
from datetime import timezone
from loguru import logger
from opentelemetry import trace as otel_trace
from opentelemetry.trace import INVALID_SPAN_CONTEXT

def _add_otel_context(record: dict) -> None:
    """Patcher: inject trace_id and span_id from active OTel span."""
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx != INVALID_SPAN_CONTEXT:
        record["extra"]["trace_id"] = format(ctx.trace_id, "032x")
        record["extra"]["span_id"] = format(ctx.span_id, "016x")
    else:
        record["extra"].setdefault("trace_id", "")
        record["extra"].setdefault("span_id", "")

def _json_sink(message) -> None:
    """Custom JSON serializer for structured log output."""
    record = message.record
    entry = {
        "timestamp": record["time"].astimezone(timezone.utc).isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "service": "civpulse-geo",
        "environment": record["extra"].get("environment", ""),
        "version": record["extra"].get("version", ""),
        "git_commit": record["extra"].get("git_commit", ""),
        "request_id": record["extra"].get("request_id", ""),
        "trace_id": record["extra"].get("trace_id", ""),
        "span_id": record["extra"].get("span_id", ""),
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }
    print(json.dumps(entry), flush=True)

def configure_logging(settings) -> None:
    logger.remove()  # Remove default handler
    logger.configure(patcher=_add_otel_context)
    if settings.is_json_logging:
        logger.add(_json_sink, level=settings.log_level)
    else:
        # Human-readable colorized for local dev
        logger.add(sys.stderr, level=settings.log_level)
```

**CRITICAL — patcher timing:** `logger.configure(patcher=...)` MUST be called before `logger.add()` calls, or the patcher does not apply to existing sinks. Calling `configure_logging()` before OTel `TracerProvider` is set is safe — the patcher reads `get_current_span()` lazily at log-emit time, so empty spans just produce empty trace_id strings.

### Pattern 3: Request-ID Middleware (middleware/request_id.py)

**What:** Starlette `BaseHTTPMiddleware` that reads `X-Request-ID` header or generates UUID4, binds to Loguru context, sets response header.
**When to use:** Added via `app.add_middleware()` in `main.py` after OTel setup.

```python
# Source: Starlette docs + D-04 locked decision
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from loguru import logger

EXCLUDED_PATHS = {"/health/live", "/health/ready"}

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

### Pattern 4: Prometheus Metrics Endpoint (api/metrics.py)

**What:** Single route returning `generate_latest()` output with `CONTENT_TYPE_LATEST`. Avoids the 307 redirect bug from `make_asgi_app()`.
**When to use:** Single-process uvicorn deployment (K8s single-replica pod).

```python
# Source: prometheus.github.io/client_python/exporting/http/fastapi-gunicorn/
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()

@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
```

**Multiprocess note:** This project uses single-worker uvicorn (K8s single replica). Do NOT set `PROMETHEUS_MULTIPROC_DIR`. If future multi-worker is added, replace with `MultiProcessCollector(registry)` pattern.

### Pattern 5: Manual Cascade Spans (services/cascade.py additions)

**What:** Manual spans wrapping each stage boundary and each `provider.geocode()` call.
**When to use:** Added alongside existing `time.monotonic()` timing in `CascadeOrchestrator.run()`.

```python
# Source: opentelemetry.io/docs/languages/python/instrumentation/
from opentelemetry import trace

_tracer = trace.get_tracer("civpulse-geo")

# Inside CascadeOrchestrator.run():
with _tracer.start_as_current_span("cascade.normalize") as span:
    span.set_attribute("stage", "normalize")
    # existing normalize code

# For each provider call:
with _tracer.start_as_current_span(f"geocode.{provider_name}") as span:
    span.set_attribute("provider", provider_name)
    result = await provider.geocode(...)
```

### Pattern 6: Settings Extensions (config.py additions)

```python
# New fields to add to Settings:
log_format: str = "auto"           # auto|json|text
otel_enabled: bool = True
otel_exporter_endpoint: str = "http://tempo:4317"

@property
def is_json_logging(self) -> bool:
    if self.log_format == "json":
        return True
    if self.log_format == "text":
        return False
    return self.environment != "local"
```

### Anti-Patterns to Avoid

- **Using `make_asgi_app()` for /metrics:** Causes 307 redirect `GET /metrics → /metrics/`. Use `generate_latest()` Response route instead.
- **Calling `logger.configure(patcher=...)` after `logger.add()`:** The patcher only applies to sinks added after the configure call. Remove default sink first, configure patcher, then add sink.
- **Calling `SQLAlchemyInstrumentor().instrument(engine=async_engine)`:** This does not work. Must pass `async_engine.sync_engine`. The async engine wrapper is not instrumentable directly.
- **Initializing TracerProvider at module level:** Global module-level setup runs at import time before settings are loaded. Always initialize in `lifespan` startup.
- **Forgetting `provider.shutdown()` in lifespan teardown:** `BatchSpanProcessor` buffers spans and will drop unsent spans on process exit without explicit `shutdown()`.
- **Using `SimpleSpanProcessor` in production:** Only appropriate for tests. `BatchSpanProcessor` is required for production throughput.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP span generation | Custom middleware tracking every route | `FastAPIInstrumentor.instrument_app()` | Handles async, route templates, error codes, W3C trace context propagation |
| SQL query spans | Wrapping every SQLAlchemy call | `SQLAlchemyInstrumentor(engine=sync_engine)` | Intercepts at event level, handles transactions, connection pooling |
| Outbound HTTP spans | Wrapping every httpx call | `HTTPXClientInstrumentor().instrument()` | Handles async clients, injects traceparent headers automatically |
| Trace context propagation | Custom header parsing | OTel auto-instrumentation | W3C traceparent/tracestate spec compliance is complex |
| Prometheus text format | Custom metrics serialization | `generate_latest()` + `CONTENT_TYPE_LATEST` | Official Prometheus text exposition format with escape rules |
| UUID generation for request IDs | Custom ID scheme | `uuid.uuid4()` | Standard practice; UUID4 collision probability negligible |

**Key insight:** The OTel instrumentation packages handle async context propagation across `await` boundaries correctly. This is not trivial to implement correctly by hand in asyncio.

---

## Common Pitfalls

### Pitfall 1: OTel Instrumentation Package Version Mismatch

**What goes wrong:** `opentelemetry-instrumentation-fastapi==0.60b0` paired with `opentelemetry-sdk==1.40.0` causes import errors at startup (`AttributeError` or `ImportError` on internal APIs).
**Why it happens:** Contrib instrumentation packages (`0.Xb0`) pair 1:1 with SDK stable releases (`1.X.0`). `0.61b0` pairs with `1.40.0`.
**How to avoid:** Always install all OTel packages together. If `opentelemetry-sdk==1.40.0`, then `opentelemetry-instrumentation-*==0.61b0`. Lock versions in `pyproject.toml`.
**Warning signs:** `ImportError: cannot import name 'X' from 'opentelemetry'` at startup.

### Pitfall 2: Loguru Patcher Not Applying to Existing Sinks

**What goes wrong:** `trace_id` and `span_id` fields are empty in all log records even though `_add_otel_context` is defined.
**Why it happens:** `logger.configure(patcher=...)` only applies to sinks added *after* the configure call. If the default stderr sink is still registered when configure is called, it doesn't benefit.
**How to avoid:** Call `logger.remove()` first, then `logger.configure(patcher=...)`, then `logger.add(sink, ...)`.
**Warning signs:** `"trace_id": ""` in every JSON log line including lines emitted during traced requests.

### Pitfall 3: SQLAlchemy async engine instrumentation failure

**What goes wrong:** `SQLAlchemyInstrumentor().instrument(engine=async_engine)` silently does nothing — no DB spans appear in Tempo.
**Why it happens:** `create_async_engine()` returns an `AsyncEngine` wrapper. The instrumentor requires the underlying sync engine to hook into SQLAlchemy events.
**How to avoid:** Always pass `engine=async_engine.sync_engine`.
**Warning signs:** FastAPI spans visible in Tempo, but no `db.*` child spans.

### Pitfall 4: prometheus-client make_asgi_app() 307 Redirect

**What goes wrong:** VictoriaMetrics scrape job hits `GET /metrics` and gets a 307 redirect to `/metrics/`. Most scrapers do not follow redirects by default, so metrics never reach VictoriaMetrics.
**Why it happens:** Starlette `Mount("/metrics", ...)` appends a trailing slash. This is a known upstream issue in prometheus/client_python.
**How to avoid:** Use `generate_latest()` in a plain FastAPI `Response` route (`@router.get("/metrics")`).
**Warning signs:** Prometheus scrape logs show `307` status codes; VictoriaMetrics shows the target as `UP` but no metrics appear.

### Pitfall 5: TracerProvider Not Shut Down on Lifespan Exit

**What goes wrong:** Last batch of spans is lost when the pod shuts down — the BatchSpanProcessor buffer is not flushed.
**Why it happens:** `BatchSpanProcessor` uses a background thread that is not automatically joined on process exit.
**How to avoid:** Call `tracer_provider.shutdown()` in lifespan teardown after `http_client.aclose()` and before `engine.dispose()`.
**Warning signs:** Traces for in-flight requests at shutdown time are truncated or missing.

### Pitfall 6: Request-ID Middleware Applied After OTel Middleware

**What goes wrong:** `request_id` is not visible in OTel spans because the request_id middleware runs after OTel's middleware already started the span.
**Why it happens:** FastAPI middleware stack is LIFO (last added = first executed). OTel FastAPI instrumentation installs its own middleware.
**How to avoid:** Add request-ID middleware after `FastAPIInstrumentor.instrument_app()`. Span attributes for request_id can be set via `span.set_attribute("request_id", request_id)` inside the middleware if correlation to spans is needed.
**Warning signs:** Loki logs show `request_id` but Tempo spans have no `request_id` attribute.

### Pitfall 7: OTel Disabled Makes Patcher Crash

**What goes wrong:** When `otel_enabled=False`, calling `get_current_span()` may return a `NonRecordingSpan` with an invalid context. Code that assumes a valid ctx will crash.
**Why it happens:** OTel API always returns a span object, but its context may be `INVALID_SPAN_CONTEXT`.
**How to avoid:** Check `ctx and ctx != INVALID_SPAN_CONTEXT` before accessing `ctx.trace_id`. The code pattern in the patcher above does this correctly with `setdefault` fallback.
**Warning signs:** `AttributeError` on `ctx.trace_id` when running without OTel initialized.

---

## Code Examples

### Lifespan Initialization Order

```python
# Source: Community patterns verified against OTel + Loguru docs
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Configure Loguru FIRST (before any logger.info calls)
    from civpulse_geo.observability.logging import configure_logging
    configure_logging(settings)

    # 2. Set up OTel TracerProvider (needed so patcher sees real spans)
    from civpulse_geo.observability.tracing import setup_tracing, teardown_tracing
    from civpulse_geo.database import engine as _async_engine
    _tracer_provider = setup_tracing(app, settings, _async_engine.sync_engine)

    # 3. Add Request-ID middleware (middleware order: last-added = first-executed)
    app.add_middleware(RequestIDMiddleware)

    # ... existing provider loading, spell corrector, etc. ...

    yield

    # Shutdown: flush OTel spans before closing engine
    logger.info("Shutting down CivPulse Geo API")
    await app.state.http_client.aclose()
    teardown_tracing(_tracer_provider)  # flushes BatchSpanProcessor
    from civpulse_geo.database import engine as _async_engine
    await _async_engine.dispose()
```

### OTel InMemorySpanExporter for Tests

```python
# Source: opentelemetry-python GitHub + oneuptime.com guide (Feb 2026)
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

@pytest.fixture
def memory_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Set as global for the test
    from opentelemetry import trace
    trace.set_tracer_provider(provider)
    yield exporter
    exporter.clear()
    # Reset to NoOp after test
    trace.set_tracer_provider(trace.ProxyTracerProvider())
```

### Prometheus Metric Definitions (metrics.py)

```python
# Source: prometheus-client 0.24.1 official API
from prometheus_client import Counter, Histogram, Gauge

# Tier 1 — HTTP
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being processed",
)

# Tier 2 — Geocoding service
GEO_PROVIDER_REQUESTS_TOTAL = Counter(
    "geo_provider_requests_total",
    "Geocoding provider requests",
    ["provider", "status"],
)
GEO_PROVIDER_DURATION = Histogram(
    "geo_provider_duration_seconds",
    "Geocoding provider call duration",
    ["provider"],
)
GEO_CASCADE_STAGES_USED = Histogram(
    "geo_cascade_stages_used",
    "Number of cascade stages before result",
    buckets=[1, 2, 3, 4, 5, 6, 7],
)
GEO_CACHE_HITS_TOTAL = Counter("geo_cache_hits_total", "Geocoding cache hits")
GEO_CACHE_MISSES_TOTAL = Counter("geo_cache_misses_total", "Geocoding cache misses")

# Tier 3 — LLM
GEO_LLM_CORRECTIONS_TOTAL = Counter(
    "geo_llm_corrections_total",
    "LLM address corrections",
    ["model"],
)
GEO_LLM_DURATION = Histogram(
    "geo_llm_duration_seconds",
    "LLM correction call duration",
    ["model"],
)
GEO_BATCH_SIZE = Histogram(
    "geo_batch_size",
    "Batch endpoint request sizes",
    buckets=[1, 5, 10, 25, 50, 100],
)
```

### K8s ConfigMap addition

```yaml
# Add to k8s/base/configmap.yaml
data:
  # ... existing fields ...
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://tempo.civpulse-infra.svc.cluster.local:4317"
  OTEL_ENABLED: "true"
  LOG_FORMAT: "auto"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `opentelemetry-instrumentation-logging` for Loguru | `logger.configure(patcher=add_otel_context)` | Loguru never supported OTel instrumentation | Confirmed by OTel maintainers: std-lib logging only |
| `make_asgi_app()` mount for Prometheus | `Response(generate_latest(), CONTENT_TYPE_LATEST)` | Ongoing Starlette issue | Avoids 307 redirect on scrape |
| Module-level OTel init | Lifespan-scoped init | Multi-worker awareness 2024+ | Safe for future scale-out |
| `BatchSpanProcessor` default timeout | Explicit `provider.shutdown()` in teardown | Good practice since OTel SDK 1.x | Prevents span loss on graceful shutdown |

**Deprecated/outdated:**
- `opentelemetry-instrumentation-logging` for Loguru: this package patches only `logging.Logger`; has zero effect on Loguru. Do not add it.
- `opentelemetry-auto-instrumentation` CLI: not appropriate for production FastAPI apps with lifespan — use programmatic setup.

---

## Open Questions

1. **OTLP Endpoint hostname in K8s**
   - What we know: Tempo is deployed to the `civpulse-infra` namespace at some service name.
   - What's unclear: Exact hostname (`tempo`, `tempo-distributor`, `grafana-tempo`, etc.).
   - Recommendation: Use `OTEL_EXPORTER_OTLP_ENDPOINT` env var rather than hardcoding. Set a reasonable default in Settings. The K8s ConfigMap overlay can override per environment.

2. **asyncpg-level instrumentation needed?**
   - What we know: `SQLAlchemyInstrumentor(engine=sync_engine)` should capture queries at the SQLAlchemy event level.
   - What's unclear: Whether asyncpg connection-level operations (connect, acquire) appear as child spans.
   - Recommendation: Start with SQLAlchemy instrumentation only. Add `opentelemetry-instrumentation-asyncpg` as an optional follow-on if driver-level spans are missing.

3. **Prometheus histogram bucket calibration**
   - What we know: The defaults above use standard Prometheus recommended buckets.
   - What's unclear: Actual P50/P99 latency before load testing (Phase 23).
   - Recommendation: Use standard buckets for Phase 22; adjust after Phase 23 baselines are established.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All packages | ✓ | 3.12.11 | — |
| uvicorn | FastAPI runtime | ✓ | 0.34.3 | — |
| uv | Package management | ✓ | (present) | — |
| grpcio | OTel gRPC exporter | ✗ (not installed) | — | Auto-installed as transitive dep of otlp-proto-grpc |
| kubectl | K8s manifest deployment | ✓ | v1.29.0 client | — |
| Tempo endpoint | OTel OTLP export | ✗ (not reachable from dev) | — | App starts without error; exporter retries silently |
| VictoriaMetrics | Prometheus scrape | ✗ (not reachable from dev) | — | /metrics endpoint works locally; scrape verified in K8s |
| Loki | Log aggregation | ✗ (infra layer) | — | Logs go to stdout; Grafana Alloy handles forwarding |

**Missing dependencies with no fallback:**
- None that block local development or test execution.

**Missing dependencies with fallback:**
- `grpcio`: Installed automatically when `opentelemetry-exporter-otlp-proto-grpc` is installed via `uv add`.
- Tempo/VictoriaMetrics/Loki: Infrastructure-layer; application code does not require them to start. OTLP exporter logs connection failures as warnings (does not crash). The `/metrics` endpoint is testable locally.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already installed) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-01 | JSON log output includes required fields (service, environment, version, git_commit, request_id) | unit | `uv run pytest tests/test_logging.py -x` | ❌ Wave 0 |
| OBS-01 | `request_id` present in log context during request | integration | `uv run pytest tests/test_request_id_middleware.py -x` | ❌ Wave 0 |
| OBS-02 | `GET /metrics` returns 200 with `text/plain` content-type | integration | `uv run pytest tests/test_metrics_endpoint.py -x` | ❌ Wave 0 |
| OBS-02 | `http_requests_total` counter increments after geocode request | integration | `uv run pytest tests/test_metrics_endpoint.py::test_counter_increments -x` | ❌ Wave 0 |
| OBS-03 | TracerProvider setup does not crash on startup | unit | `uv run pytest tests/test_tracing.py::test_setup -x` | ❌ Wave 0 |
| OBS-03 | FastAPI span created for geocode request (InMemorySpanExporter) | integration | `uv run pytest tests/test_tracing.py::test_fastapi_span -x` | ❌ Wave 0 |
| OBS-04 | Loguru patcher injects non-empty trace_id during active span | unit | `uv run pytest tests/test_logging.py::test_trace_id_injection -x` | ❌ Wave 0 |
| OBS-04 | Response has `X-Request-ID` header | integration | `uv run pytest tests/test_request_id_middleware.py::test_response_header -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_logging.py` — covers OBS-01, OBS-04 (JSON format, trace_id injection)
- [ ] `tests/test_request_id_middleware.py` — covers OBS-01, OBS-04 (request_id binding, response header)
- [ ] `tests/test_metrics_endpoint.py` — covers OBS-02 (endpoint, counter increment)
- [ ] `tests/test_tracing.py` — covers OBS-03 (TracerProvider setup, FastAPI span creation)

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 22 |
|-----------|-------------------|
| Always use `uv add` / `uv remove` for packages | Install all 7 new packages via `uv add` |
| Always use `ruff` to lint Python code; lint before git commit | Run `uv run ruff check src/ tests/` before each commit |
| Never use system Python; prefix with `uv run` | All test and lint commands use `uv run` |
| Git commits on branches unless specifically requested | Phase 22 work should be on a branch |
| Always commit after completing each task | Commit after each plan's tasks complete |
| Conventional Commits for commit messages | Use `feat(obs):` prefix for observability changes |
| Never push to GitHub unless specifically requested | Do not push phase 22 branch automatically |
| After UI changes: visually verify with Playwright | Phase 22 is backend-only; no UI changes — Playwright not needed |

---

## Sources

### Primary (HIGH confidence)

- PyPI registry (verified 2026-03-30) — all package version numbers
- opentelemetry-python GitHub Issue #3615 — Loguru patcher pattern confirmation by OTel maintainers
- Loguru GitHub Issue #1222 — patcher + trace_id injection working code
- prometheus.github.io/client_python — FastAPI + Gunicorn `make_asgi_app()` official docs + trailing slash issue
- oneuptime.com/blog/post/2026-02-06-instrument-async-sqlalchemy-2-opentelemetry — async SQLAlchemy `sync_engine` pattern (Feb 2026)
- oneuptime.com/blog/post/2026-02-06-instrument-fastapi-opentelemetry-fastapiinstrumentor — FastAPIInstrumentor complete setup (Feb 2026)

### Secondary (MEDIUM confidence)

- WebSearch: OTel FastAPI `excluded_urls` parameter — confirmed via pypi.org package description
- WebSearch: `provider.shutdown()` in lifespan — confirmed via OTel GitHub issues and community patterns
- WebSearch: OTel environment variables (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`) — consistent across multiple official OTel docs pages

### Tertiary (LOW confidence)

- WebSearch results claiming asyncpg-level instrumentation required — not yet verified against the specific asyncpg+SQLAlchemy 2.0 async combination in this project; flagged as Open Question 2.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI registry 2026-03-30
- Architecture: HIGH — patterns derived from official docs and confirmed GitHub issues; Loguru patcher pattern verified by maintainer commentary
- Pitfalls: HIGH — most pitfalls are from confirmed upstream issues (prometheus #1016, loguru #1222, otel #3615)
- Test map: MEDIUM — test file names are projections; exact test assertions require implementation knowledge

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (OTel contrib packages release frequently; re-verify versions if planning is delayed more than 30 days)
