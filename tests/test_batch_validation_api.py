"""Tests for POST /validate/batch endpoint.

Tests verify:
- All-success batch returns 200 with correct counts and result structure
- Partial-failure batch returns 200; failing item has error, success has data
- All-fail batch returns outer HTTP 422
- Empty batch returns 200 with zero counts
- Batch exceeding 100 addresses returns 422 before processing
- Response structure: each item has index, original_input, status_code, status, data, error
- ProviderNetworkError on one item produces status_code=500, status="provider_error"
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from civpulse_geo.main import app
from civpulse_geo.database import get_db


def _make_mock_validation_orm_row(
    provider_name="scourgify",
    normalized_address="123 MAIN ST MACON GA 31201",
    address_line_1="123 MAIN ST",
    address_line_2=None,
    city="MACON",
    state="GA",
    postal_code="31201",
    confidence=1.0,
    delivery_point_verified=False,
):
    """Build a mock ValidationResultORM row for response construction."""
    from civpulse_geo.models.validation import ValidationResult as ValidationResultORM

    row = MagicMock(spec=ValidationResultORM)
    row.provider_name = provider_name
    row.normalized_address = normalized_address
    row.address_line_1 = address_line_1
    row.address_line_2 = address_line_2
    row.city = city
    row.state = state
    row.postal_code = postal_code
    row.confidence = confidence
    row.delivery_point_verified = delivery_point_verified
    return row


def _make_validate_success_return(address_hash=None, original_input="123 Main St, Macon, GA 31201"):
    """Build a mock ValidationService.validate() return value dict."""
    if address_hash is None:
        address_hash = "a" * 64
    return {
        "address_hash": address_hash,
        "original_input": original_input,
        "cache_hit": False,
        "candidates": [_make_mock_validation_orm_row()],
    }


@pytest.fixture
def patched_app_state():
    """Set app.state.validation_providers and app.state.http_client to avoid lifespan dependency."""
    app.state.validation_providers = {"scourgify": AsyncMock()}
    app.state.http_client = AsyncMock()
    yield
    try:
        del app.state.validation_providers
    except AttributeError:
        pass
    try:
        del app.state.http_client
    except AttributeError:
        pass


@pytest.mark.asyncio
async def test_batch_validate_all_success(patched_app_state):
    """POST /validate/batch with 2 valid addresses returns 200, total=2, succeeded=2, failed=0."""
    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value=_make_validate_success_return(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/validate/batch",
                json={"addresses": ["123 Main St, Macon GA 31201", "456 Oak Ave, Atlanta GA 30301"]},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert len(data["results"]) == 2
    for item in data["results"]:
        assert item["status"] == "success"
        assert item["data"] is not None
        assert item["error"] is None


@pytest.mark.asyncio
async def test_batch_validate_partial_failure(patched_app_state):
    """POST /validate/batch with 1 success + 1 failure returns 200, total=2, succeeded=1, failed=1."""
    from civpulse_geo.providers.exceptions import ProviderError

    call_count = 0

    async def validate_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_validate_success_return()
        raise ProviderError("Address unparseable")

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        side_effect=validate_side_effect,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/validate/batch",
                json={"addresses": ["123 Main St, Macon GA 31201", "bad address!!"]},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1

    success_item = next(item for item in data["results"] if item["status"] == "success")
    fail_item = next(item for item in data["results"] if item["status"] != "success")
    assert success_item["data"] is not None
    assert success_item["error"] is None
    assert fail_item["error"] is not None
    assert fail_item["error"]["message"] != ""


@pytest.mark.asyncio
async def test_batch_validate_all_fail_returns_422(patched_app_state):
    """POST /validate/batch where all addresses fail returns outer HTTP 422."""
    from civpulse_geo.providers.exceptions import ProviderError

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        side_effect=ProviderError("Address unparseable"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/validate/batch",
                json={"addresses": ["bad1", "bad2"]},
            )

    assert response.status_code == 422
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 0
    assert data["failed"] == 2


@pytest.mark.asyncio
async def test_batch_validate_empty(patched_app_state):
    """POST /validate/batch with empty addresses returns 200, total=0, succeeded=0, failed=0."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/validate/batch", json={"addresses": []})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["succeeded"] == 0
    assert data["failed"] == 0
    assert data["results"] == []


@pytest.mark.asyncio
async def test_batch_validate_exceeds_limit(patched_app_state):
    """POST /validate/batch with 101 addresses returns 422 (Pydantic validation, no processing)."""
    addresses = [f"Address {i}, Macon GA 31201" for i in range(101)]

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
    ) as mock_validate:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/validate/batch", json={"addresses": addresses})

        # Pydantic validation fires before the handler -- validate should never be called
        mock_validate.assert_not_called()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_batch_validate_response_structure(patched_app_state):
    """Each item in batch response has index, original_input, status_code, status, data, error."""
    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value=_make_validate_success_return(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/validate/batch",
                json={"addresses": ["123 Main St, Macon GA 31201"]},
            )

    assert response.status_code == 200
    data = response.json()
    item = data["results"][0]
    assert "index" in item
    assert item["index"] == 0
    assert "original_input" in item
    assert item["original_input"] == "123 Main St, Macon GA 31201"
    assert "status_code" in item
    assert "status" in item
    assert "data" in item
    assert "error" in item


@pytest.mark.asyncio
async def test_batch_validate_provider_network_error(patched_app_state):
    """ProviderNetworkError on one item produces status_code=500, status='provider_error'."""
    from civpulse_geo.providers.exceptions import ProviderNetworkError

    call_count = 0

    async def validate_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_validate_success_return()
        raise ProviderNetworkError("timeout connecting to provider")

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        side_effect=validate_side_effect,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/validate/batch",
                json={"addresses": ["123 Main St, Macon GA 31201", "456 Oak Ave, Atlanta GA 30301"]},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1

    fail_item = next(item for item in data["results"] if item["status"] != "success")
    assert fail_item["status_code"] == 500
    assert fail_item["status"] == "provider_error"
    assert fail_item["error"] is not None
    assert "timeout" in fail_item["error"]["message"]


def _make_validate_success_return_with_local(
    address_hash=None, original_input="123 Main St, Macon, GA 31201"
):
    """Build a service result dict that includes a local validation candidate."""
    from civpulse_geo.providers.schemas import ValidationResult

    if address_hash is None:
        address_hash = "b" * 64
    local = ValidationResult(
        normalized_address="123 MAIN ST MACON GA 31201",
        address_line_1="123 MAIN ST",
        address_line_2=None,
        city="MACON",
        state="GA",
        postal_code="31201",
        confidence=1.0,
        delivery_point_verified=False,
        provider_name="test-local-validator",
        original_input=original_input,
    )
    return {
        "address_hash": address_hash,
        "original_input": original_input,
        "cache_hit": False,
        "candidates": [],
        "local_candidates": [local],
    }


@pytest.mark.asyncio
async def test_batch_validate_local_candidates_included(patched_app_state):
    """POST /validate/batch passes local_candidates through to each response item (closes GAP-INT-01)."""
    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value=_make_validate_success_return_with_local(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/validate/batch",
                json={"addresses": ["123 Main St, Macon GA 31201"]},
            )

    assert response.status_code == 200
    data = response.json()
    item = data["results"][0]
    assert item["status"] == "success"
    local_candidates = item["data"]["local_candidates"]
    assert len(local_candidates) == 1
    assert local_candidates[0]["provider_name"] == "test-local-validator"
    assert local_candidates[0]["normalized_address"] == "123 MAIN ST MACON GA 31201"
    assert local_candidates[0]["address_line_1"] == "123 MAIN ST"
    assert local_candidates[0]["city"] == "MACON"
    assert local_candidates[0]["state"] == "GA"
    assert local_candidates[0]["confidence"] == pytest.approx(1.0)
