"""Tests for Prometheus metrics instrumentation (OBS-02).

Tests the MetricsMiddleware (Tier 1) and verifies that Tier 2/3
metric objects are accessible and incrementable.
"""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from civpulse_geo.middleware.metrics import MetricsMiddleware
from civpulse_geo.observability.metrics import (
    GEO_BATCH_SIZE,
    GEO_CACHE_HITS_TOTAL,
    GEO_CACHE_MISSES_TOTAL,
    GEO_CASCADE_STAGES_USED,
    GEO_LLM_CORRECTIONS_TOTAL,
    GEO_PROVIDER_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
)


@pytest.fixture
def app_with_metrics_middleware():
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/test")
    async def test_route():
        return {"ok": True}

    @app.get("/health/live")
    async def health_live():
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics():
        return {"status": "ok"}

    return app


def test_http_requests_total_increments(app_with_metrics_middleware):
    """HTTP requests total counter increments on request."""
    client = TestClient(app_with_metrics_middleware)
    # Get current value before request
    before = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/test", status_code="200"
    )._value.get()
    client.get("/test")
    after = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/test", status_code="200"
    )._value.get()
    assert after > before


def test_health_excluded_from_metrics(app_with_metrics_middleware):
    """Health endpoints excluded from HTTP metrics."""
    client = TestClient(app_with_metrics_middleware)
    before = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/health/live", status_code="200"
    )._value.get()
    client.get("/health/live")
    after = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/health/live", status_code="200"
    )._value.get()
    assert after == before  # should NOT increment


def test_metrics_endpoint_excluded_from_metrics(app_with_metrics_middleware):
    """/metrics endpoint excluded from HTTP metrics collection."""
    client = TestClient(app_with_metrics_middleware)
    before = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/metrics", status_code="200"
    )._value.get()
    client.get("/metrics")
    after = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/metrics", status_code="200"
    )._value.get()
    assert after == before


def test_http_request_duration_recorded(app_with_metrics_middleware):
    """HTTP request duration histogram has at least one observation after a request."""
    client = TestClient(app_with_metrics_middleware)
    before_sum = HTTP_REQUEST_DURATION.labels(
        method="GET", path="/test"
    )._sum.get()
    client.get("/test")
    after_sum = HTTP_REQUEST_DURATION.labels(
        method="GET", path="/test"
    )._sum.get()
    assert after_sum > before_sum


def test_geo_metric_objects_importable():
    """All Tier 2/3 metric objects are importable and non-None."""
    assert GEO_PROVIDER_REQUESTS_TOTAL is not None
    assert GEO_CACHE_HITS_TOTAL is not None
    assert GEO_CACHE_MISSES_TOTAL is not None
    assert GEO_CASCADE_STAGES_USED is not None
    assert GEO_LLM_CORRECTIONS_TOTAL is not None
    assert GEO_BATCH_SIZE is not None


def test_geo_cache_counter_incrementable():
    """Cache hit/miss counters can be incremented without error."""
    before_hits = GEO_CACHE_HITS_TOTAL._value.get()
    GEO_CACHE_HITS_TOTAL.inc()
    assert GEO_CACHE_HITS_TOTAL._value.get() == before_hits + 1

    before_misses = GEO_CACHE_MISSES_TOTAL._value.get()
    GEO_CACHE_MISSES_TOTAL.inc()
    assert GEO_CACHE_MISSES_TOTAL._value.get() == before_misses + 1


def test_geo_provider_counter_labeled():
    """Provider request counter accepts provider and status labels."""
    before = GEO_PROVIDER_REQUESTS_TOTAL.labels(
        provider="census", status="success"
    )._value.get()
    GEO_PROVIDER_REQUESTS_TOTAL.labels(
        provider="census", status="success"
    ).inc()
    after = GEO_PROVIDER_REQUESTS_TOTAL.labels(
        provider="census", status="success"
    )._value.get()
    assert after == before + 1
