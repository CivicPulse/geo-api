import pytest
from importlib.metadata import metadata
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.main import app
from civpulse_geo.database import get_db

_expected = metadata("civpulse-geo")


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
    """Readiness probe returns 200 when DB works and >= 2 geocoding + 2 validation providers."""
    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})

    mock = MagicMock()
    app.state.providers = {"census": mock, "openaddresses": mock}
    app.state.validation_providers = {"scourgify": mock, "openaddresses": mock}

    try:
        response = await test_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["geocoding_providers"] == 2
        assert data["validation_providers"] == 2
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
    app.state.providers = {"census": mock, "openaddresses": mock}
    app.state.validation_providers = {"scourgify": mock, "openaddresses": mock}

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
    """Readiness probe returns 503 when geocoding providers < 2."""
    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})

    mock = MagicMock()
    app.state.providers = {"census": mock}  # only 1 geocoding provider
    app.state.validation_providers = {"scourgify": mock, "openaddresses": mock}

    try:
        response = await test_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "not_ready"
        assert "insufficient providers" in data["detail"]["reason"]
    finally:
        app.state.providers = original_providers
        app.state.validation_providers = original_val_providers
