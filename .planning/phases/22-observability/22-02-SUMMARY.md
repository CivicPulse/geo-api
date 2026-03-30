---
phase: 22-observability
plan: 02
subsystem: observability
tags: [opentelemetry, tracing, loguru, fastapi, sqlalchemy, httpx, otel-patcher, lifespan]

# Dependency graph
requires:
  - phase: 22-01
    provides: configure_logging(), prometheus metrics, RequestIDMiddleware, /metrics endpoint, OTel deps installed

provides:
  - setup_tracing(app, settings, sync_engine) — TracerProvider init with BatchSpanProcessor, OTLP gRPC exporter
  - teardown_tracing(provider) — TracerProvider shutdown flushing BatchSpanProcessor before engine.dispose()
  - FastAPIInstrumentor auto-instrumentation (health/readiness/metrics excluded)
  - SQLAlchemyInstrumentor auto-instrumentation via sync_engine
  - HTTPXClientInstrumentor auto-instrumentation for Census/Ollama calls
  - _add_otel_context Loguru patcher — injects trace_id/span_id from active OTel span
  - configure_logging() updated with patcher=_add_otel_context (lazy, safe before TracerProvider)
  - main.py lifespan fully wired: configure_logging -> setup_tracing -> providers -> yield -> teardown_tracing -> engine.dispose
  - RequestIDMiddleware wired at app-definition time
  - metrics_router included in app

affects: [22-03-cascade-instrumentation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "setup_tracing() called in lifespan startup with engine.sync_engine (NOT async engine)"
    - "logger.configure(patcher=_add_otel_context) in configure_logging() — patcher reads get_current_span() lazily at emit time"
    - "teardown_tracing() called after http_client.aclose() and before engine.dispose() to flush BatchSpanProcessor"
    - "RequestIDMiddleware registered at app = FastAPI(...) time, not in lifespan (Starlette restriction)"
    - "InMemorySpanExporter via provider.get_tracer() directly to avoid global TracerProvider override restriction in tests"

key-files:
  created:
    - src/civpulse_geo/observability/tracing.py
    - tests/test_tracing.py
  modified:
    - src/civpulse_geo/observability/logging.py
    - src/civpulse_geo/main.py
    - tests/test_logging.py
    - tests/test_shutdown.py

key-decisions:
  - "RequestIDMiddleware moved from lifespan to app-definition time: Starlette raises RuntimeError if add_middleware() is called after app has started (test_shutdown.py reuses the same app singleton)"
  - "InMemorySpanExporter imported from opentelemetry.sdk.trace.export.in_memory_span_exporter (not .in_memory) in OTel 1.40.0"
  - "Use provider.get_tracer() directly in tests instead of global trace.get_tracer() to avoid OTel SDK's single-TracerProvider-set restriction"
  - "test_shutdown.py patched setup_tracing/teardown_tracing to isolate from real SQLAlchemy engine"

requirements-completed: [OBS-03, OBS-04]

# Metrics
duration: 6min
completed: 2026-03-30
---

# Phase 22 Plan 02: OTel Tracing Module, Loguru OTel Patcher, and Lifespan Wiring Summary

**OpenTelemetry TracerProvider with OTLP gRPC exporter, Loguru trace_id/span_id patcher via lazy get_current_span(), and fully wired main.py lifespan (configure_logging -> setup_tracing -> providers -> teardown_tracing -> engine.dispose)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-30T17:32:23Z
- **Completed:** 2026-03-30T17:37:50Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Created `observability/tracing.py` with `setup_tracing()` and `teardown_tracing()` — FastAPIInstrumentor (health/readiness/metrics excluded), SQLAlchemyInstrumentor (sync_engine), HTTPXClientInstrumentor, BatchSpanProcessor + OTLPSpanExporter
- Updated `observability/logging.py` — added `_add_otel_context` patcher (lazy `get_current_span()`, INVALID_SPAN_CONTEXT-safe) and installed it via `logger.configure(patcher=...)` in `configure_logging()`
- Wired `main.py` lifespan: `configure_logging` -> `setup_tracing` -> existing startup -> `yield` -> `teardown_tracing` -> `engine.dispose`
- Added `metrics_router` and `RequestIDMiddleware` to app
- Created 5 tracing tests and 1 OTel patcher logging test — all green
- Fixed pre-existing `test_shutdown.py` to patch `setup_tracing`/`teardown_tracing` for test isolation
- Full test suite: 567 passed, 2 skipped

## Task Commits

1. **Task 1: Create tracing module, add OTel patcher to logging, wire lifespan** - `08db8b2` (feat)
2. **Task 2: Create tracing tests and update logging tests for OTel patcher** - `42be651` (test)

## Files Created/Modified

- `src/civpulse_geo/observability/tracing.py` — setup_tracing() + teardown_tracing(), OTLP gRPC exporter, auto-instrumentation for FastAPI/SQLAlchemy/httpx
- `src/civpulse_geo/observability/logging.py` — _add_otel_context patcher, add_otel_patcher(), updated configure_logging() with patcher installed
- `src/civpulse_geo/main.py` — lifespan wired with configure_logging/setup_tracing/teardown_tracing; RequestIDMiddleware at app-definition time; metrics_router included
- `tests/test_tracing.py` — 5 tests: setup_tracing returns TracerProvider, disabled returns None, teardown None-safe, span creation, excluded_urls
- `tests/test_logging.py` — Added test_trace_id_injection_with_active_span (OBS-04): 32-char trace_id, 16-char span_id confirmed
- `tests/test_shutdown.py` — Patched setup_tracing/teardown_tracing for test isolation

## Decisions Made

- **RequestIDMiddleware at app-definition time:** Starlette/FastAPI raises `RuntimeError: Cannot add middleware after an application has started` when `add_middleware()` is called inside lifespan. The plan showed lifespan wiring, but the correct pattern is registration at `app = FastAPI(...)` time — aligns with existing middleware documentation.
- **InMemorySpanExporter import path:** OTel 1.40.0 uses `opentelemetry.sdk.trace.export.in_memory_span_exporter` (not `.in_memory` as shown in plan). Auto-fixed.
- **Test provider isolation:** Using `provider.get_tracer()` instead of global `trace.get_tracer()` in tests avoids OTel SDK's single-override restriction that causes test-ordering failures.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wrong InMemorySpanExporter import path**
- **Found during:** Task 2
- **Issue:** Plan referenced `from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter` but OTel 1.40.0 uses `in_memory_span_exporter` module name
- **Fix:** Changed import to `from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter`
- **Files modified:** tests/test_tracing.py, tests/test_logging.py
- **Commit:** 42be651

**2. [Rule 1 - Bug] OTel global TracerProvider override restriction in tests**
- **Found during:** Task 2
- **Issue:** `test_tracer_creates_spans` yielded 0 spans because `test_setup_tracing_returns_provider` had already called `trace.set_tracer_provider()` and the SDK logs "Overriding of current TracerProvider is not allowed"
- **Fix:** Changed `memory_exporter` fixture to yield `(exporter, provider)` tuple; tests use `provider.get_tracer()` directly instead of the global `trace.get_tracer()`
- **Files modified:** tests/test_tracing.py, tests/test_logging.py
- **Commit:** 42be651

**3. [Rule 1 - Bug] add_middleware() called inside lifespan causes RuntimeError**
- **Found during:** Task 2 (test_shutdown.py failures)
- **Issue:** Plan specified `app.add_middleware(RequestIDMiddleware)` inside lifespan startup. Starlette raises `RuntimeError: Cannot add middleware after an application has started` because the `conftest.py` test_client fixture starts the same `app` singleton before `test_shutdown.py` calls `lifespan(app)` directly
- **Fix:** Moved `app.add_middleware(RequestIDMiddleware)` to app-definition time (after `app = FastAPI(...)` block), removed from lifespan
- **Files modified:** src/civpulse_geo/main.py
- **Commit:** 42be651

**4. [Rule 1 - Bug] test_shutdown.py fails with SQLAlchemy InvalidRequestError**
- **Found during:** Task 2
- **Issue:** `test_shutdown_disposes_engine` patches `civpulse_geo.database.engine` with a MagicMock, but `SQLAlchemyInstrumentor` tries to attach real SQLAlchemy event listeners to the mock — fails with `No such event 'before_cursor_execute'`
- **Fix:** Added `patch("civpulse_geo.main.setup_tracing", return_value=None)` and `patch("civpulse_geo.main.teardown_tracing")` to both shutdown tests
- **Files modified:** tests/test_shutdown.py
- **Commit:** 42be651

## Known Stubs

None — all data flows are wired. Tracing is disabled when `otel_enabled=False` (graceful no-op, not a stub).

## Self-Check: PASSED

- `src/civpulse_geo/observability/tracing.py` — exists, contains `def setup_tracing`, `def teardown_tracing`, `FastAPIInstrumentor.instrument_app`, `SQLAlchemyInstrumentor`, `BatchSpanProcessor`, `provider.shutdown()`
- `src/civpulse_geo/observability/logging.py` — exists, contains `_add_otel_context`, `get_current_span()`, `format(ctx.trace_id, "032x")`, `INVALID_SPAN_CONTEXT`
- `src/civpulse_geo/main.py` — contains `configure_logging(`, `setup_tracing(`, `teardown_tracing(`, `RequestIDMiddleware`, `metrics_router`
- `tests/test_tracing.py` — exists, 5 tests all passing
- `tests/test_logging.py` — contains `test_trace_id_injection_with_active_span`, 5 tests all passing
- Task commits: 08db8b2 and 42be651 verified in git log
- Full test suite: 567 passed, 2 skipped, 0 failed
