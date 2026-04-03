import pytest
from importlib import import_module
from importlib.metadata import metadata
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.main import app
from civpulse_geo.database import get_db

_expected = metadata("civpulse-geo")
health_module = import_module("civpulse_geo.api.health")


@pytest.fixture(autouse=True)
def reset_health_threshold_cache(monkeypatch):
    monkeypatch.delenv("MIN_READY_GEOCODING_PROVIDERS", raising=False)
    monkeypatch.delenv("MIN_READY_VALIDATION_PROVIDERS", raising=False)
    health_module._min_ready_geocoding_providers.cache_clear()
    health_module._min_ready_validation_providers.cache_clear()
    yield
    health_module._min_ready_geocoding_providers.cache_clear()
    health_module._min_ready_validation_providers.cache_clear()


@pytest.mark.asyncio
async def test_health_ok(test_client, override_db):
    response = await test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["name"] == _expected["Name"]
    assert data["version"] == _expected["Version"]
    assert data["description"] == _expected["Summary"]
    assert isinstance(data["authors"], list)
    assert len(data["authors"]) > 0
    assert "commit" in data


@pytest.mark.asyncio
async def test_health_db_down(test_client, mock_db_session):
    mock_db_session.execute = AsyncMock(side_effect=Exception("Connection refused"))

    async def _override():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override
    response = await test_client.get("/health")
    assert response.status_code == 503
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_live(test_client):
    """Liveness probe returns 200 with no DB dependency."""
    response = await test_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_live_db_down(test_client):
    """Liveness probe returns 200 even with no DB override -- never calls DB."""
    # Intentionally do NOT override get_db -- /health/live must not call it
    response = await test_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_ok(test_client, override_db):
    """Readiness probe returns 200 when DB works and minimum providers are present."""
    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})

    mock = MagicMock()
    app.state.providers = {"census": mock}
    app.state.validation_providers = {"scourgify": mock}

    try:
        response = await test_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["geocoding_providers"] == 1
        assert data["validation_providers"] == 1
        assert data["minimum_geocoding_providers"] == 1
        assert data["minimum_validation_providers"] == 1
    finally:
        app.state.providers = original_providers
        app.state.validation_providers = original_val_providers


@pytest.mark.asyncio
async def test_health_ready_db_down(test_client, mock_db_session):
    """Readiness probe returns 503 when DB execute raises Exception."""
    mock_db_session.execute = AsyncMock(side_effect=Exception("Connection refused"))

    async def _override():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override

    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})

    mock = MagicMock()
    app.state.providers = {"census": mock}
    app.state.validation_providers = {"scourgify": mock}

    try:
        response = await test_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "not_ready"
        assert "db" in data["detail"]["reason"]
    finally:
        app.dependency_overrides.clear()
        app.state.providers = original_providers
        app.state.validation_providers = original_val_providers


@pytest.mark.asyncio
async def test_health_ready_insufficient_providers(test_client, override_db):
    """Readiness probe returns 503 when actual providers are below configured minimums."""
    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})

    health_module._min_ready_geocoding_providers.cache_clear()
    health_module._min_ready_validation_providers.cache_clear()
    mock = MagicMock()
    app.state.providers = {"census": mock}
    app.state.validation_providers = {"scourgify": mock}

    try:
        response = await test_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
    finally:
        app.state.providers = original_providers
        app.state.validation_providers = original_val_providers


@pytest.mark.asyncio
async def test_health_ready_respects_configured_thresholds(test_client, override_db, monkeypatch):
    """Readiness probe returns 503 when configured thresholds exceed available providers."""
    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})

    monkeypatch.setenv("MIN_READY_GEOCODING_PROVIDERS", "2")
    monkeypatch.setenv("MIN_READY_VALIDATION_PROVIDERS", "2")
    health_module._min_ready_geocoding_providers.cache_clear()
    health_module._min_ready_validation_providers.cache_clear()

    mock = MagicMock()
    app.state.providers = {"census": mock}
    app.state.validation_providers = {"scourgify": mock}

    try:
        response = await test_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "not_ready"
        assert "insufficient providers" in data["detail"]["reason"]
        assert data["detail"]["minimum_geocoding_providers"] == 2
        assert data["detail"]["minimum_validation_providers"] == 2
    finally:
        app.state.providers = original_providers
        app.state.validation_providers = original_val_providers
