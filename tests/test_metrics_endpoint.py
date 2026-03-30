"""Tests for Prometheus /metrics endpoint (OBS-02)."""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from civpulse_geo.api.metrics import router as metrics_router
from civpulse_geo.observability.metrics import HTTP_REQUESTS_TOTAL  # noqa: F401


@pytest.fixture
def app_with_metrics():
    app = FastAPI()
    app.include_router(metrics_router)
    return app


def test_metrics_endpoint_returns_200(app_with_metrics):
    """GET /metrics returns 200."""
    client = TestClient(app_with_metrics)
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_content_type(app_with_metrics):
    """GET /metrics returns text/plain content type."""
    client = TestClient(app_with_metrics)
    response = client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]


def test_metrics_contains_http_requests_total(app_with_metrics):
    """GET /metrics output contains http_requests_total metric family."""
    client = TestClient(app_with_metrics)
    response = client.get("/metrics")
    body = response.text
    assert "http_requests_total" in body


def test_metrics_contains_geo_provider_requests(app_with_metrics):
    """GET /metrics output contains geo_provider_requests_total metric."""
    client = TestClient(app_with_metrics)
    response = client.get("/metrics")
    body = response.text
    assert "geo_provider_requests_total" in body


def test_metrics_no_307_redirect(app_with_metrics):
    """GET /metrics does NOT redirect (avoids make_asgi_app 307 bug)."""
    client = TestClient(app_with_metrics, follow_redirects=False)
    response = client.get("/metrics")
    assert response.status_code == 200  # not 307
