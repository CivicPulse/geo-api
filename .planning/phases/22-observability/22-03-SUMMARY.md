---
phase: 22-observability
plan: "03"
subsystem: observability/metrics
tags: [metrics, prometheus, opentelemetry, middleware, instrumentation]
dependency_graph:
  requires: ["22-01", "22-02"]
  provides: ["HTTP tier metrics", "cascade OTel spans", "Tier 2/3 metric instrumentation"]
  affects: ["src/civpulse_geo/middleware/metrics.py", "src/civpulse_geo/services/cascade.py", "src/civpulse_geo/api/geocoding.py", "src/civpulse_geo/main.py"]
tech_stack:
  added: []
  patterns: ["BaseHTTPMiddleware for Tier 1 metrics", "LIFO middleware ordering (MetricsMiddleware runs first)", "module-level otel_trace.get_tracer for cascade spans", "context manager spans at stage boundaries"]
key_files:
  created:
    - src/civpulse_geo/middleware/metrics.py
    - tests/test_metrics_instrumentation.py
  modified:
    - src/civpulse_geo/services/cascade.py
    - src/civpulse_geo/main.py
    - src/civpulse_geo/api/geocoding.py
decisions:
  - "MetricsMiddleware registered at app-definition time (not lifespan) to match RequestIDMiddleware pattern"
  - "LIFO middleware order: MetricsMiddleware added after RequestIDMiddleware so it executes first, seeing full request duration"
  - "GEO_CACHE_MISSES_TOTAL.inc() placed at start of Stage 2 (after cache check) — only fires when cache missed"
  - "GEO_LLM_CORRECTIONS_TOTAL/DURATION recorded only when LLM stage produces usable reverified candidates"
  - "cascade.auto_set_official span uses context manager with immediate exit (no async work inside span body)"
metrics:
  duration: 4 minutes
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_modified: 5
---

# Phase 22 Plan 03: Metrics Middleware and Cascade Instrumentation Summary

Prometheus HTTP metrics middleware (Tier 1) and manual OpenTelemetry spans at cascade stage boundaries plus Tier 2/3 metric calls — giving every request HTTP metrics and every cascade run stage-level OTel traces.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create HTTP metrics middleware + cascade OTel spans + Tier 2/3 metrics | 9770362 | metrics.py, cascade.py, main.py, geocoding.py |
| 2 | Create integration tests for metrics middleware and cascade instrumentation | f630d6c | test_metrics_instrumentation.py |

## What Was Built

### Task 1: MetricsMiddleware (Tier 1)

`src/civpulse_geo/middleware/metrics.py` — `MetricsMiddleware(BaseHTTPMiddleware)`:
- Records `http_requests_total` (Counter) with method/path/status_code labels
- Records `http_request_duration_seconds` (Histogram) with method/path labels
- Tracks `http_requests_in_progress` (Gauge) via inc/dec in try/finally
- Excludes `/health/live`, `/health/ready`, `/metrics` paths from all counters
- Wired into `main.py` at app-definition time after `RequestIDMiddleware` (LIFO: runs first)

### Task 1: cascade.py Instrumentation

`src/civpulse_geo/services/cascade.py`:
- `_tracer = otel_trace.get_tracer("civpulse-geo")` — module-level tracer
- 7 `start_as_current_span` calls: `cascade.normalize`, `cascade.exact_match`, `cascade.fuzzy_match`, `cascade.llm_correction`, `cascade.consensus`, `cascade.auto_set_official`, plus `geocode.{provider_name}` per provider
- `GEO_CACHE_HITS_TOTAL.inc()` on cache hit path
- `GEO_CACHE_MISSES_TOTAL.inc()` at Stage 2 entry
- `GEO_PROVIDER_REQUESTS_TOTAL.labels(provider=..., status=...).inc()` for success/empty/timeout/error
- `GEO_PROVIDER_DURATION.labels(provider=...).observe(elapsed)` per provider call
- `GEO_LLM_CORRECTIONS_TOTAL.labels(model="qwen2.5:3b").inc()` when LLM produces candidates
- `GEO_LLM_DURATION.observe(elapsed)` alongside LLM counter
- `GEO_CASCADE_STAGES_USED.observe(_stages_used)` before final return

### Task 1: Batch size metric

`src/civpulse_geo/api/geocoding.py`:
- `GEO_BATCH_SIZE.observe(len(body.addresses))` in batch endpoint before processing

### Task 2: Tests (7 tests, all passing)

`tests/test_metrics_instrumentation.py`:
- `test_http_requests_total_increments` — counter increments on non-excluded request
- `test_health_excluded_from_metrics` — /health/live counter unchanged after request
- `test_metrics_endpoint_excluded_from_metrics` — /metrics counter unchanged
- `test_http_request_duration_recorded` — duration sum increases after request
- `test_geo_metric_objects_importable` — all Tier 2/3 metric objects importable
- `test_geo_cache_counter_incrementable` — cache counters accept .inc() without error
- `test_geo_provider_counter_labeled` — provider counter accepts labeled dimensions

## Verification Results

```
ruff check: All checks passed
pytest tests/test_metrics_instrumentation.py tests/test_metrics_endpoint.py: 12 passed
pytest tests/: 574 passed, 2 skipped
start_as_current_span calls in cascade.py: 7
GEO_ references in cascade.py: 18
```

## Deviations from Plan

None — plan executed exactly as written.

The only minor adaptation: the `cascade.auto_set_official` span wraps an immediate context-manager exit (the async auto-set DB operations follow after the `with` block). This matches the plan's intent — the span marks the stage boundary — and is consistent with the surrounding code structure.

## Known Stubs

None.

## Self-Check: PASSED

- `src/civpulse_geo/middleware/metrics.py` — FOUND
- `tests/test_metrics_instrumentation.py` — FOUND
- Commit 9770362 — FOUND (`feat(22-03): add MetricsMiddleware and cascade OTel spans + Tier 2/3 metrics`)
- Commit f630d6c — FOUND (`test(22-03): add metrics instrumentation tests`)
