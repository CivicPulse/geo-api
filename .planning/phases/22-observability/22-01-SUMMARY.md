---
phase: 22-observability
plan: 01
subsystem: observability
tags: [loguru, prometheus, opentelemetry, fastapi, middleware, structured-logging, metrics]

# Dependency graph
requires:
  - phase: 21-ci-cd-pipeline
    provides: CI/CD pipeline with ruff + pytest gates that validates all new code

provides:
  - Loguru JSON sink (configure_logging) with service/env/request_id/trace_id fields
  - Prometheus metric definitions (Tier 1 HTTP, Tier 2 geocoding, Tier 3 LLM/batch)
  - RequestIDMiddleware that propagates X-Request-ID and excludes health endpoints
  - GET /metrics endpoint using generate_latest() (no 307 redirect)
  - Settings extensions: log_format, otel_enabled, otel_exporter_endpoint, is_json_logging
  - K8s ConfigMap entries for OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_ENABLED, LOG_FORMAT

affects: [22-02-tracing-lifespan, 22-03-cascade-instrumentation, 23-e2e-validation]

# Tech tracking
tech-stack:
  added:
    - opentelemetry-api==1.40.0
    - opentelemetry-sdk==1.40.0
    - opentelemetry-exporter-otlp-proto-grpc==1.40.0
    - opentelemetry-instrumentation-fastapi==0.61b0
    - opentelemetry-instrumentation-sqlalchemy==0.61b0
    - opentelemetry-instrumentation-httpx==0.61b0
    - prometheus-client==0.24.1
  patterns:
    - "Loguru JSON sink via print(json.dumps(entry)) to stdout — K8s log collector reads stdout"
    - "Prometheus metrics as module-level objects — imported by instrumentation code in Plan 03"
    - "RequestIDMiddleware using BaseHTTPMiddleware.dispatch with logger.contextualize()"
    - "is_json_logging as @property on Settings — auto=JSON when environment != local"

key-files:
  created:
    - src/civpulse_geo/observability/__init__.py
    - src/civpulse_geo/observability/logging.py
    - src/civpulse_geo/observability/metrics.py
    - src/civpulse_geo/middleware/__init__.py
    - src/civpulse_geo/middleware/request_id.py
    - src/civpulse_geo/api/metrics.py
    - tests/test_logging.py
    - tests/test_request_id_middleware.py
    - tests/test_metrics_endpoint.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/civpulse_geo/config.py
    - k8s/base/configmap.yaml

key-decisions:
  - "OTel patcher for trace_id/span_id is NOT added in configure_logging — deferred to Plan 02 after TracerProvider is available"
  - "generate_latest() + plain FastAPI Response used for /metrics — avoids prometheus_client.make_asgi_app() 307 redirect bug"
  - "arbitrary_types_allowed=True added to SettingsConfigDict — required to allow @property on Pydantic BaseSettings"

patterns-established:
  - "configure_logging() is safe to call before OTel setup — no coupling to TracerProvider"
  - "All Prometheus metric objects are module-level constants in observability/metrics.py — imported directly by instrumentation"
  - "EXCLUDED_PATHS set in request_id.py — health endpoints bypass middleware entirely"

requirements-completed: [OBS-01, OBS-02]

# Metrics
duration: 4min
completed: 2026-03-30
---

# Phase 22 Plan 01: Observability Foundation Modules Summary

**Loguru JSON structured logging, Prometheus metric definitions (3 tiers), RequestIDMiddleware with UUID4 propagation, and GET /metrics endpoint installed as standalone importable modules**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-30T17:25:55Z
- **Completed:** 2026-03-30T17:29:30Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

- Installed 7 OpenTelemetry and Prometheus dependencies, all importable without errors
- Created four production source files (logging.py, metrics.py, request_id.py, api/metrics.py) with full ruff compliance
- All 13 unit tests pass across logging, request-ID middleware, and /metrics endpoint test files

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies, extend Settings, create observability and middleware modules** - `09e836a` (feat)
2. **Task 2: Create unit and integration tests for logging, request-ID middleware, and /metrics endpoint** - `314c91f` (test)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `src/civpulse_geo/observability/logging.py` — Loguru JSON sink + configure_logging() with service/env/request_id/trace_id/span_id fields
- `src/civpulse_geo/observability/metrics.py` — Tier 1 (HTTP), Tier 2 (geocoding), Tier 3 (LLM/batch) Prometheus metric objects
- `src/civpulse_geo/middleware/request_id.py` — RequestIDMiddleware: UUID4 generation, upstream propagation, health endpoint exclusions
- `src/civpulse_geo/api/metrics.py` — GET /metrics using generate_latest() + CONTENT_TYPE_LATEST (no 307 redirect)
- `src/civpulse_geo/config.py` — Added log_format, otel_enabled, otel_exporter_endpoint fields and is_json_logging property
- `k8s/base/configmap.yaml` — Added OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_ENABLED, LOG_FORMAT entries
- `pyproject.toml` / `uv.lock` — 7 new OTel + Prometheus dependencies
- `tests/test_logging.py` — 4 tests: JSON output validity, environment field, text mode, request_id contextualization
- `tests/test_request_id_middleware.py` — 4 tests: UUID4 generation, upstream preservation, health exclusions
- `tests/test_metrics_endpoint.py` — 5 tests: 200 status, content-type, metric presence, no-redirect

## Decisions Made

- **OTel patcher deferred to Plan 02:** `configure_logging()` does not patch trace_id/span_id — the TracerProvider is not yet initialized at Plan 01 scope. Plan 02 adds `add_otel_patcher()` separately after lifespan wiring.
- **Plain FastAPI Response for /metrics:** `prometheus_client.make_asgi_app()` causes 307 redirects; `generate_latest()` with `Response(content=..., media_type=CONTENT_TYPE_LATEST)` avoids this pitfall.
- **`arbitrary_types_allowed=True` on SettingsConfigDict:** Required so Pydantic v2 BaseSettings accepts the `@property` decorator on the Settings class without raising a validation error at import time.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All Plan 02 dependencies satisfied: `configure_logging()`, metric objects, and `RequestIDMiddleware` are importable
- Plan 02 (tracing + lifespan wiring) can now wire `TracerProvider`, call `configure_logging()`, add `RequestIDMiddleware`, and register `/metrics` router in `main.py` lifespan
- No blockers

---
*Phase: 22-observability*
*Completed: 2026-03-30*

## Self-Check: PASSED

All created files exist on disk. Both task commits (09e836a, 314c91f) verified in git log.
