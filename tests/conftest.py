import pytest
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from civpulse_geo.main import app
from civpulse_geo.database import get_db
from civpulse_geo.providers.schemas import GeocodingResult
from civpulse_geo.providers.schemas import ValidationResult as ValidationResultSchema


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


@pytest.fixture
def mock_validation_providers():
    """Mock validation provider registry with a fake scourgify provider."""
    provider = AsyncMock()
    provider.provider_name = "scourgify"
    provider.validate = AsyncMock(
        return_value=ValidationResultSchema(
            normalized_address="123 MAIN ST MACON GA 31201",
            address_line_1="123 MAIN ST",
            address_line_2=None,
            city="MACON",
            state="GA",
            postal_code="31201",
            confidence=1.0,
            delivery_point_verified=False,
            provider_name="scourgify",
            original_input="123 Main Street, Macon, GA 31201",
        )
    )
    return {"scourgify": provider}
