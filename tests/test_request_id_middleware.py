"""Tests for Request-ID middleware (OBS-01, OBS-04)."""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from civpulse_geo.middleware.request_id import RequestIDMiddleware


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_route():
        return {"ok": True}

    @app.get("/health/live")
    async def health_live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready():
        return {"status": "ready"}

    return app


def test_response_has_request_id_header(app_with_middleware):
    """Response includes X-Request-ID header (OBS-04)."""
    client = TestClient(app_with_middleware)
    response = client.get("/test")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Should be a valid UUID4 format (36 chars with hyphens)
    rid = response.headers["X-Request-ID"]
    assert len(rid) == 36


def test_upstream_request_id_preserved(app_with_middleware):
    """Upstream X-Request-ID header is preserved in response."""
    client = TestClient(app_with_middleware)
    response = client.get("/test", headers={"X-Request-ID": "upstream-id-999"})
    assert response.headers["X-Request-ID"] == "upstream-id-999"


def test_health_live_excluded(app_with_middleware):
    """Health live endpoint excluded from request-ID middleware."""
    client = TestClient(app_with_middleware)
    response = client.get("/health/live")
    assert response.status_code == 200
    # Excluded paths should NOT have X-Request-ID header set by middleware
    assert "X-Request-ID" not in response.headers


def test_health_ready_excluded(app_with_middleware):
    """Health ready endpoint excluded from request-ID middleware."""
    client = TestClient(app_with_middleware)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert "X-Request-ID" not in response.headers
