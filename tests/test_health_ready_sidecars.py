"""Tests for /health/ready sidecars block (INFRA-05).

Verifies that GET /health/ready returns a sidecars dict reporting
nominatim, tile_server, and valhalla readiness without blocking
the readiness probe on sidecar failure.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.main import app
from civpulse_geo.config import settings


@pytest.fixture
def _providers_setup(monkeypatch, override_db):
    """Set up minimal providers so provider count checks pass."""
    original_providers = getattr(app.state, "providers", {})
    original_val_providers = getattr(app.state, "validation_providers", {})
    mock = MagicMock()
    app.state.providers = {"census": mock}
    app.state.validation_providers = {"scourgify": mock}
    yield
    app.state.providers = original_providers
    app.state.validation_providers = original_val_providers


@pytest.mark.asyncio
async def test_health_ready_includes_sidecars_key(test_client, _providers_setup, monkeypatch):
    """GET /health/ready response includes top-level sidecars dict with 3 keys."""
    monkeypatch.setattr("civpulse_geo.api.health._nominatim_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("civpulse_geo.api.health._tile_server_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("civpulse_geo.api.health._valhalla_reachable", AsyncMock(return_value=True))

    response = await test_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "sidecars" in data
    assert set(data["sidecars"].keys()) == {"nominatim", "tile_server", "valhalla"}


@pytest.mark.asyncio
async def test_health_ready_all_sidecars_ready(test_client, _providers_setup, monkeypatch):
    """All 3 probes return True → each sidecar reports 'ready', response is 200."""
    monkeypatch.setattr("civpulse_geo.api.health._nominatim_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("civpulse_geo.api.health._tile_server_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("civpulse_geo.api.health._valhalla_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("civpulse_geo.api.health.settings", MagicMock(
        nominatim_enabled=True,
        valhalla_enabled=True,
        osm_nominatim_url=settings.osm_nominatim_url,
        osm_tile_url=settings.osm_tile_url,
        osm_valhalla_url=settings.osm_valhalla_url,
    ))

    response = await test_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["sidecars"]["nominatim"] == "ready"
    assert data["sidecars"]["tile_server"] == "ready"
    assert data["sidecars"]["valhalla"] == "ready"


@pytest.mark.asyncio
async def test_health_ready_sidecars_unavailable_does_not_fail_readiness(
    test_client, _providers_setup, monkeypatch
):
    """All 3 probes return False → sidecars report 'unavailable', response is still 200 (not 503)."""
    monkeypatch.setattr("civpulse_geo.api.health._nominatim_reachable", AsyncMock(return_value=False))
    monkeypatch.setattr("civpulse_geo.api.health._tile_server_reachable", AsyncMock(return_value=False))
    monkeypatch.setattr("civpulse_geo.api.health._valhalla_reachable", AsyncMock(return_value=False))
    monkeypatch.setattr("civpulse_geo.api.health.settings", MagicMock(
        nominatim_enabled=True,
        valhalla_enabled=True,
        osm_nominatim_url=settings.osm_nominatim_url,
        osm_tile_url=settings.osm_tile_url,
        osm_valhalla_url=settings.osm_valhalla_url,
    ))

    response = await test_client.get("/health/ready")
    # Sidecar failures must NOT cause 503
    assert response.status_code == 200
    data = response.json()
    assert data["sidecars"]["nominatim"] == "unavailable"
    assert data["sidecars"]["tile_server"] == "unavailable"
    assert data["sidecars"]["valhalla"] == "unavailable"


@pytest.mark.asyncio
async def test_health_ready_nominatim_disabled_when_setting_false(
    test_client, _providers_setup, monkeypatch
):
    """When nominatim_enabled=False, sidecars.nominatim == 'disabled' and probe is NOT called."""
    nom_mock = AsyncMock(return_value=True)
    tile_mock = AsyncMock(return_value=True)
    val_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("civpulse_geo.api.health._nominatim_reachable", nom_mock)
    monkeypatch.setattr("civpulse_geo.api.health._tile_server_reachable", tile_mock)
    monkeypatch.setattr("civpulse_geo.api.health._valhalla_reachable", val_mock)
    monkeypatch.setattr("civpulse_geo.api.health.settings", MagicMock(
        nominatim_enabled=False,
        valhalla_enabled=True,
        osm_nominatim_url=settings.osm_nominatim_url,
        osm_tile_url=settings.osm_tile_url,
        osm_valhalla_url=settings.osm_valhalla_url,
    ))

    response = await test_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["sidecars"]["nominatim"] == "disabled"
    # Probe must NOT have been called when disabled
    assert nom_mock.call_count == 0


@pytest.mark.asyncio
async def test_health_ready_valhalla_disabled_when_setting_false(
    test_client, _providers_setup, monkeypatch
):
    """When valhalla_enabled=False, sidecars.valhalla == 'disabled' and probe is NOT called."""
    nom_mock = AsyncMock(return_value=True)
    tile_mock = AsyncMock(return_value=True)
    val_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("civpulse_geo.api.health._nominatim_reachable", nom_mock)
    monkeypatch.setattr("civpulse_geo.api.health._tile_server_reachable", tile_mock)
    monkeypatch.setattr("civpulse_geo.api.health._valhalla_reachable", val_mock)
    monkeypatch.setattr("civpulse_geo.api.health.settings", MagicMock(
        nominatim_enabled=True,
        valhalla_enabled=False,
        osm_nominatim_url=settings.osm_nominatim_url,
        osm_tile_url=settings.osm_tile_url,
        osm_valhalla_url=settings.osm_valhalla_url,
    ))

    response = await test_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["sidecars"]["valhalla"] == "disabled"
    # Probe must NOT have been called when disabled
    assert val_mock.call_count == 0


@pytest.mark.asyncio
async def test_health_ready_mixed_sidecar_states(test_client, _providers_setup, monkeypatch):
    """nominatim=ready, tile_server=unavailable, valhalla=disabled → mixed sidecars block."""
    nom_mock = AsyncMock(return_value=True)
    tile_mock = AsyncMock(return_value=False)
    val_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("civpulse_geo.api.health._nominatim_reachable", nom_mock)
    monkeypatch.setattr("civpulse_geo.api.health._tile_server_reachable", tile_mock)
    monkeypatch.setattr("civpulse_geo.api.health._valhalla_reachable", val_mock)
    monkeypatch.setattr("civpulse_geo.api.health.settings", MagicMock(
        nominatim_enabled=True,
        valhalla_enabled=False,
        osm_nominatim_url=settings.osm_nominatim_url,
        osm_tile_url=settings.osm_tile_url,
        osm_valhalla_url=settings.osm_valhalla_url,
    ))

    response = await test_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["sidecars"]["nominatim"] == "ready"
    assert data["sidecars"]["tile_server"] == "unavailable"
    assert data["sidecars"]["valhalla"] == "disabled"
