"""Unit tests for the LLM address corrector service.

Tests cover:
- LLMAddressCorrector.correct_address: request payload shape, structured result, error handling
- _passes_guardrails: state-change rejection, zip/state mismatch rejection, valid pass-through
- _ollama_model_available: model found, model missing, network error
- Config defaults for LLM settings
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from civpulse_geo.config import Settings
from civpulse_geo.services.llm_corrector import (
    AddressCorrection,
    LLMAddressCorrector,
    _ollama_model_available,
    _passes_guardrails,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _mock_ollama_response(content_json: dict) -> MagicMock:
    """Return a mock httpx.Response matching the Ollama /api/chat response shape."""
    payload = {
        "message": {"role": "assistant", "content": json.dumps(content_json)},
        "done": True,
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_corrector(url: str = "http://ollama:11434") -> LLMAddressCorrector:
    return LLMAddressCorrector(ollama_url=url)


# ---------------------------------------------------------------------------
# correct_address — result shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrector_returns_structured_result():
    """Mock httpx POST returns canned Ollama JSON; AddressCorrection fields populated correctly."""
    content = {
        "street_number": "123",
        "street_name": "Main",
        "street_suffix": "St",
        "city": "Macon",
        "state": "GA",
        "zip": "31201",
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=_mock_ollama_response(content))

    corrector = _make_corrector()
    result = await corrector.correct_address("123 Main St, Macon GA 31201", mock_client)

    assert result is not None
    assert isinstance(result, AddressCorrection)
    assert result.street_number == "123"
    assert result.street_name == "Main"
    assert result.street_suffix == "St"
    assert result.city == "Macon"
    assert result.state == "GA"
    assert result.zip == "31201"


@pytest.mark.asyncio
async def test_corrector_request_payload_shape():
    """Mock httpx POST captures request body; assert model, stream, temperature, and format fields."""
    content = {
        "street_number": "456",
        "street_name": "Elm",
        "street_suffix": "Ave",
        "city": "Atlanta",
        "state": "GA",
        "zip": "30301",
    }
    captured_kwargs: dict = {}

    async def capture_post(url, **kwargs):
        captured_kwargs.update(kwargs)
        return _mock_ollama_response(content)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = capture_post

    corrector = _make_corrector()
    await corrector.correct_address("456 Elm Av, Atlanta GA 30301", mock_client)

    # Verify the URL was the /api/chat endpoint
    assert "json" in captured_kwargs
    payload = captured_kwargs["json"]

    assert payload["model"] == "qwen2.5:3b"
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0
    assert "format" in payload  # JSON schema dict

    # Messages: system + user
    messages = payload["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "456 Elm Av, Atlanta GA 30301" in messages[1]["content"]


# ---------------------------------------------------------------------------
# correct_address — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrector_returns_none_on_http_error():
    """Mock httpx POST raises HTTPStatusError; correct_address returns None."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("500", request=request, response=mock_response)
    )

    corrector = _make_corrector()
    result = await corrector.correct_address("some address", mock_client)
    assert result is None


@pytest.mark.asyncio
async def test_corrector_returns_none_on_malformed_json():
    """Mock httpx POST returns invalid JSON content; correct_address returns None (no retry per D-16)."""
    bad_payload = {
        "message": {"role": "assistant", "content": "not valid json {{{"},
        "done": True,
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = bad_payload
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_resp)

    corrector = _make_corrector()
    result = await corrector.correct_address("some address", mock_client)
    assert result is None


# ---------------------------------------------------------------------------
# _passes_guardrails
# ---------------------------------------------------------------------------


def test_guardrail_rejects_state_change():
    """AddressCorrection with state='FL' vs original_state='GA' -> _passes_guardrails returns False."""
    correction = AddressCorrection(
        street_number="123",
        street_name="Main",
        street_suffix="St",
        city="Miami",
        state="FL",
        zip="33101",
    )
    assert _passes_guardrails(correction, original_state="GA") is False


def test_guardrail_rejects_zip_state_mismatch():
    """AddressCorrection with state='GA' zip='90210' (CA zip) -> _passes_guardrails returns False."""
    correction = AddressCorrection(
        street_number="123",
        street_name="Beverly",
        street_suffix="Dr",
        city="Macon",
        state="GA",
        zip="90210",
    )
    assert _passes_guardrails(correction, original_state="GA") is False


def test_guardrail_passes_valid_correction():
    """AddressCorrection with state='GA' zip='31201' -> _passes_guardrails returns True."""
    correction = AddressCorrection(
        street_number="123",
        street_name="Main",
        street_suffix="St",
        city="Macon",
        state="GA",
        zip="31201",
    )
    assert _passes_guardrails(correction, original_state="GA") is True


def test_guardrail_passes_when_no_original_state():
    """original_state=None -> _passes_guardrails returns True (can't validate state change)."""
    correction = AddressCorrection(
        street_number="123",
        street_name="Main",
        street_suffix="St",
        city="Macon",
        state="GA",
        zip="31201",
    )
    assert _passes_guardrails(correction, original_state=None) is True


# ---------------------------------------------------------------------------
# _ollama_model_available
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_model_available_returns_true():
    """Mock GET /api/tags returns models list with qwen2.5:3b -> True."""
    tags_payload = {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3:8b"}]}
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = tags_payload

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await _ollama_model_available("http://ollama:11434", mock_client)
    assert result is True


@pytest.mark.asyncio
async def test_ollama_model_available_returns_false_when_missing():
    """Mock GET /api/tags returns empty models list -> False."""
    tags_payload = {"models": []}
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = tags_payload

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await _ollama_model_available("http://ollama:11434", mock_client)
    assert result is False


@pytest.mark.asyncio
async def test_ollama_model_available_returns_false_on_error():
    """Mock GET /api/tags raises exception -> False."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    result = await _ollama_model_available("http://ollama:11434", mock_client)
    assert result is False


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_llm_disabled_when_flag_false():
    """Assert cascade_llm_enabled defaults to False in Settings."""
    s = Settings()
    assert s.cascade_llm_enabled is False


def test_config_defaults():
    """Assert ollama_url defaults to 'http://ollama:11434', llm_timeout_ms defaults to 5000."""
    s = Settings()
    assert s.ollama_url == "http://ollama:11434"
    assert s.llm_timeout_ms == 5000
