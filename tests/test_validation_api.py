"""Integration tests for POST /validate endpoint.

Tests verify:
- POST /validate with valid freeform address returns HTTP 200
- POST /validate with valid structured fields returns HTTP 200
- POST /validate with empty body returns HTTP 422 (Pydantic validation)
- POST /validate with unparseable address returns HTTP 422 (ProviderError -> 422)
- Response contains address_hash, original_input, candidates, cache_hit fields
- Each candidate has confidence, delivery_point_verified, provider_name fields
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


from civpulse_geo.main import app


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


@pytest.mark.asyncio
async def test_validate_freeform_returns_200(test_client, override_db, mock_db_session, mock_validation_providers):
    """POST /validate with freeform address returns HTTP 200 with required fields."""
    app.state.validation_providers = mock_validation_providers

    mock_orm_row = _make_mock_validation_orm_row()

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "a" * 64,
            "original_input": "123 Main Street, Macon, GA 31201",
            "cache_hit": False,
            "candidates": [mock_orm_row],
        },
    ):
        response = await test_client.post("/validate", json={"address": "123 Main Street, Macon, GA 31201"})

    assert response.status_code == 200
    data = response.json()
    assert "address_hash" in data
    assert "candidates" in data
    assert "cache_hit" in data
    assert data["original_input"] == "123 Main Street, Macon, GA 31201"


@pytest.mark.asyncio
async def test_validate_structured_returns_200(test_client, override_db, mock_db_session, mock_validation_providers):
    """POST /validate with structured fields returns HTTP 200."""
    app.state.validation_providers = mock_validation_providers

    mock_orm_row = _make_mock_validation_orm_row()

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "b" * 64,
            "original_input": "123 Main Street, Macon, GA, 31201",
            "cache_hit": False,
            "candidates": [mock_orm_row],
        },
    ):
        response = await test_client.post("/validate", json={
            "street": "123 Main Street",
            "city": "Macon",
            "state": "GA",
            "zip_code": "31201",
        })

    assert response.status_code == 200
    data = response.json()
    assert "address_hash" in data
    assert "candidates" in data
    assert "cache_hit" in data


@pytest.mark.asyncio
async def test_validate_no_input_returns_422(test_client):
    """POST /validate with empty body returns HTTP 422 (Pydantic validation error)."""
    response = await test_client.post("/validate", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unparseable_returns_422(test_client, override_db, mock_db_session):
    """POST /validate with unparseable address returns 422 with error detail."""
    from civpulse_geo.providers.exceptions import ProviderError

    app.state.validation_providers = {"scourgify": AsyncMock()}

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        side_effect=ProviderError("Address unparseable by scourgify: PO Box not supported"),
    ):
        response = await test_client.post("/validate", json={"address": "PO Box 123, Macon, GA 31201"})

    assert response.status_code == 422
    assert "unparseable" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confidence_in_response(test_client, override_db, mock_db_session, mock_validation_providers):
    """Response candidates include confidence, delivery_point_verified, and provider_name fields."""
    app.state.validation_providers = mock_validation_providers

    mock_orm_row = _make_mock_validation_orm_row(
        confidence=1.0,
        delivery_point_verified=False,
        provider_name="scourgify",
    )

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "c" * 64,
            "original_input": "123 Main St, Macon, GA 31201",
            "cache_hit": False,
            "candidates": [mock_orm_row],
        },
    ):
        response = await test_client.post("/validate", json={"address": "123 Main St, Macon, GA 31201"})

    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["confidence"] == 1.0
    assert candidate["delivery_point_verified"] is False
    assert candidate["provider_name"] == "scourgify"


@pytest.mark.asyncio
async def test_validate_cache_hit_response(test_client, override_db, mock_db_session, mock_validation_providers):
    """POST /validate returns cache_hit=True when result comes from cache."""
    app.state.validation_providers = mock_validation_providers

    mock_orm_row = _make_mock_validation_orm_row()

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "d" * 64,
            "original_input": "123 Main St, Macon, GA 31201",
            "cache_hit": True,
            "candidates": [mock_orm_row],
        },
    ):
        response = await test_client.post("/validate", json={"address": "123 Main St, Macon, GA 31201"})

    assert response.status_code == 200
    data = response.json()
    assert data["cache_hit"] is True


@pytest.mark.asyncio
async def test_validate_response_structure(test_client, override_db, mock_db_session, mock_validation_providers):
    """Response contains all required ValidateResponse fields with correct types."""
    app.state.validation_providers = mock_validation_providers

    mock_orm_row = _make_mock_validation_orm_row()

    with patch(
        "civpulse_geo.services.validation.ValidationService.validate",
        new_callable=AsyncMock,
        return_value={
            "address_hash": "e" * 64,
            "original_input": "123 Main Street, Macon, GA 31201",
            "cache_hit": False,
            "candidates": [mock_orm_row],
        },
    ):
        response = await test_client.post("/validate", json={"address": "123 Main Street, Macon, GA 31201"})

    assert response.status_code == 200
    data = response.json()

    # Required top-level fields
    assert "address_hash" in data
    assert len(data["address_hash"]) == 64  # SHA-256 hex is 64 chars
    assert "original_input" in data
    assert isinstance(data["original_input"], str)
    assert "cache_hit" in data
    assert isinstance(data["cache_hit"], bool)
    assert "candidates" in data
    assert isinstance(data["candidates"], list)
    assert len(data["candidates"]) == 1

    # Per-candidate structure
    candidate = data["candidates"][0]
    assert "normalized_address" in candidate
    assert "confidence" in candidate
    assert "delivery_point_verified" in candidate
    assert "provider_name" in candidate


# ---------------------------------------------------------------------------
# Phase 18: Security regression tests (SEC-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_rejects_oversized_freeform_address(test_client, override_db):
    """SEC-02: Freeform address > 500 chars rejected at schema level."""
    long_address = "A" * 501
    resp = await test_client.post("/validate", json={"address": long_address})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_rejects_oversized_street(test_client, override_db):
    """SEC-02: Street field > 200 chars rejected at schema level."""
    long_street = "A" * 201
    resp = await test_client.post("/validate", json={"street": long_street})
    assert resp.status_code == 422
