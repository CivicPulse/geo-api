import pytest
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.main import app
from civpulse_geo.database import get_db
from civpulse_geo.providers.schemas import GeocodingResult


@pytest.fixture
async def test_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession for unit tests that don't need real PostGIS."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    return session


@pytest.fixture
def override_db(mock_db_session):
    """Override get_db dependency with mock session."""
    async def _override():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override
    yield mock_db_session
    app.dependency_overrides.clear()


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for provider calls in tests."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def mock_providers():
    """Mock provider registry with a fake census provider returning a match."""
    provider = AsyncMock()
    provider.provider_name = "census"
    provider.geocode = AsyncMock(
        return_value=GeocodingResult(
            lat=38.845,
            lng=-76.928,
            location_type="RANGE_INTERPOLATED",
            confidence=0.8,
            raw_response={},
            provider_name="census",
        )
    )
    return {"census": provider}
