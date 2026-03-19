import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_health_ok(test_client, override_db):
    response = await test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_health_db_down(test_client, mock_db_session):
    from civpulse_geo.main import app
    from civpulse_geo.database import get_db

    mock_db_session.execute = AsyncMock(side_effect=Exception("Connection refused"))

    async def _override():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override
    response = await test_client.get("/health")
    assert response.status_code == 503
    app.dependency_overrides.clear()
