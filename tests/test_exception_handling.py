"""Tests for global exception handler and stability fixes (STAB-01, STAB-02).

Verifies that unhandled exceptions from service layer are caught by the
global exception handler in main.py and returned as structured 500 JSON.

Note: Uses starlette.testclient.TestClient with raise_server_exceptions=False
to bypass Starlette's ServerErrorMiddleware re-raise behavior in tests.
This is the standard pattern for testing generic exception handlers in FastAPI.
"""
import pytest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from civpulse_geo.main import app
from civpulse_geo.database import get_db


@pytest.fixture
def override_db():
    mock_session = AsyncMock()

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    yield mock_session
    app.dependency_overrides.clear()


@pytest.fixture
def patched_app_state():
    app.state.http_client = AsyncMock()
    app.state.providers = {}
    app.state.validation_providers = {}
    app.state.spell_corrector = None
    app.state.fuzzy_matcher = None
    app.state.llm_corrector = None
    yield
    for attr in [
        "http_client",
        "providers",
        "validation_providers",
        "spell_corrector",
        "fuzzy_matcher",
        "llm_corrector",
    ]:
        try:
            delattr(app.state, attr)
        except AttributeError:
            pass


def test_geocode_unhandled_exception_returns_500_json(override_db, patched_app_state):
    """STAB-01: RuntimeError in geocode service returns structured 500, not raw traceback."""
    with patch("civpulse_geo.api.geocoding.GeocodingService") as MockService:
        MockService.return_value.geocode = AsyncMock(side_effect=RuntimeError("DB exploded"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/geocode", json={"address": "123 Main St"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"
    assert "application/json" in resp.headers.get("content-type", "")


def test_validate_unhandled_exception_returns_500_json(override_db, patched_app_state):
    """STAB-02: RuntimeError in validate service returns structured 500, not raw traceback."""
    with patch("civpulse_geo.api.validation.ValidationService") as MockService:
        MockService.return_value.validate = AsyncMock(side_effect=RuntimeError("DB exploded"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/validate", json={"address": "123 Main St"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"
    assert "application/json" in resp.headers.get("content-type", "")


def test_geocode_sqlalchemy_error_returns_500_json(override_db, patched_app_state):
    """STAB-01: SQLAlchemy-type error returns structured 500, not raw traceback."""
    with patch("civpulse_geo.api.geocoding.GeocodingService") as MockService:
        MockService.return_value.geocode = AsyncMock(
            side_effect=Exception("connection refused")
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/geocode", json={"address": "456 Oak Ave"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error"
    # Ensure the raw exception message is NOT in the response body
    assert "connection refused" not in str(body)
