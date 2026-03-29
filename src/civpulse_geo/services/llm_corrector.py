"""LLM address corrector service using a local Ollama sidecar.

Sends a raw address string to a local Ollama instance running qwen2.5:3b
and receives a structured JSON component extraction (D-02). The LLM output
is never used as a geocode result directly — it is re-verified against
provider databases before entering consensus scoring (D-17, LLM-03).

Design decisions from Phase 15 CONTEXT.md:
- D-01: LLM receives raw address string only
- D-02: Returns structured JSON with street_number, street_name, street_suffix, city, state, zip
- D-03: Single best correction, temperature=0 for deterministic output
- D-04: Structured output enforced via Ollama format parameter (JSON schema dict)
- D-14: Hard-reject guardrails: state change + zip/state mismatch
- D-16: Malformed JSON -> no retry, return None
"""
from __future__ import annotations

import httpx
from loguru import logger
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Pydantic model for structured LLM output (D-02)
# ---------------------------------------------------------------------------


class AddressCorrection(BaseModel):
    """Structured address components extracted/corrected by the LLM.

    Mirrors the _parse_input_address 5-tuple from openaddresses.py.
    All fields are nullable — the LLM may not be able to extract every field.
    """

    street_number: str | None = None
    street_name: str | None = None
    street_suffix: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None


# ---------------------------------------------------------------------------
# Zip-prefix-to-state guardrail table (D-14, RESEARCH.md Pattern 7)
# ---------------------------------------------------------------------------

_ZIP_FIRST_DIGIT_STATES: dict[str, set[str]] = {
    "0": {"CT", "MA", "ME", "NH", "NJ", "PR", "RI", "VT", "VI"},
    "1": {"DE", "NY", "PA"},
    "2": {"DC", "MD", "NC", "SC", "VA", "WV"},
    "3": {"AL", "FL", "GA", "MS", "TN"},
    "4": {"IN", "KY", "MI", "OH"},
    "5": {"IA", "MN", "MT", "ND", "SD", "WI"},
    "6": {"IL", "KS", "MO", "NE"},
    "7": {"AR", "LA", "OK", "TX"},
    "8": {"AZ", "CO", "ID", "NM", "NV", "UT", "WY"},
    "9": {"AK", "AS", "CA", "GU", "HI", "OR", "WA"},
}


# ---------------------------------------------------------------------------
# Guardrail logic (D-14)
# ---------------------------------------------------------------------------


def _passes_guardrails(
    correction: AddressCorrection,
    original_state: str | None,
) -> bool:
    """Apply hard-reject guardrails to an LLM correction before re-verification.

    Rules (D-14):
    1. If original_state is known, reject if LLM changed the state.
    2. If zip and state are both present, reject if the state is not valid
       for the zip code's first digit (catches gross hallucinations cheaply).

    Args:
        correction: The AddressCorrection produced by the LLM.
        original_state: The two-letter state code from the original input, or None.

    Returns:
        True if the correction passes all guardrails, False if rejected.
    """
    # Guard 1: reject state changes
    if original_state is not None and correction.state is not None:
        if correction.state.upper() != original_state.upper():
            logger.debug(
                "LLM guardrail: state change rejected ({} -> {})",
                original_state,
                correction.state,
            )
            return False

    # Guard 2: reject zip/state mismatches
    if correction.zip and correction.state and len(correction.zip) >= 1:
        valid_states = _ZIP_FIRST_DIGIT_STATES.get(correction.zip[0], set())
        if correction.state.upper() not in valid_states:
            logger.debug(
                "LLM guardrail: zip/state mismatch rejected (zip={}, state={})",
                correction.zip,
                correction.state,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# System prompt for qwen2.5:3b
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an address parsing and correction assistant for US addresses. "
    "Given a raw address string, extract and correct the address components. "
    "Fix common typos, abbreviations, and formatting issues. "
    "Return the corrected components as JSON.\n\n"
    "Examples:\n"
    "Input: 123 Main St, Macon GA 31201\n"
    '{"street_number": "123", "street_name": "Main", "street_suffix": "St", "city": "Macon", "state": "GA", "zip": "31201"}\n\n'
    "Input: 456 Elm Av Apt 2B, Atlanta Georgia 30301\n"
    '{"street_number": "456", "street_name": "Elm", "street_suffix": "Ave", "city": "Atlanta", "state": "GA", "zip": "30301"}\n\n'
    "Input: 789 Oake Stret, Macn GA\n"
    '{"street_number": "789", "street_name": "Oak", "street_suffix": "St", "city": "Macon", "state": "GA", "zip": null}'
)


# ---------------------------------------------------------------------------
# LLM address corrector class
# ---------------------------------------------------------------------------


class LLMAddressCorrector:
    """Sends raw address strings to a local Ollama instance for structured correction.

    Isolates all Ollama API interaction and LLM-specific logic into a single
    testable module. Cascade integration is handled by Plan 02.

    Design decisions:
    - D-03: temperature=0, stream=False for deterministic output
    - D-04: format=JSON schema dict to constrain model output
    - D-16: Any exception (HTTP error, parse failure) returns None — no retry
    """

    def __init__(self, ollama_url: str, model: str = "qwen2.5:3b") -> None:
        self._ollama_url = ollama_url
        self._model = model
        self._schema = AddressCorrection.model_json_schema()

    async def correct_address(
        self,
        raw_address: str,
        http_client: httpx.AsyncClient,
    ) -> AddressCorrection | None:
        """Send raw_address to Ollama and return a structured AddressCorrection.

        Args:
            raw_address: The unmodified address string from the original request.
            http_client: An active httpx.AsyncClient to use for the request.

        Returns:
            An AddressCorrection if successful, or None on any error (D-16).
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_address},
            ],
            "stream": False,
            "format": self._schema,
            "options": {"temperature": 0},
        }
        try:
            resp = await http_client.post(
                f"{self._ollama_url}/api/chat",
                json=payload,
                timeout=6.0,  # slightly above 5s asyncio.wait_for — let wait_for handle cancellation
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return AddressCorrection.model_validate_json(content)
        except Exception as exc:
            logger.warning("LLMAddressCorrector.correct_address failed: {}", exc)
            return None


# ---------------------------------------------------------------------------
# Ollama model availability check (D-13, D-15)
# ---------------------------------------------------------------------------


async def _ollama_model_available(
    ollama_url: str,
    http_client: httpx.AsyncClient,
    model_name: str = "qwen2.5:3b",
) -> bool:
    """Check whether the target model is available on the Ollama instance.

    Used at API startup for conditional LLM stage registration (similar to
    the _oa_data_available / _tiger_extension_available pattern).

    Args:
        ollama_url: Base URL for the Ollama server (e.g. "http://ollama:11434").
        http_client: An active httpx.AsyncClient.
        model_name: The model name prefix to look for (default "qwen2.5:3b").

    Returns:
        True if a model with a name starting with model_name is available,
        False on any error or if the model is absent (D-15: silent failure).
    """
    try:
        resp = await http_client.get(f"{ollama_url}/api/tags", timeout=5.0)
        models = resp.json().get("models", [])
        return any(m["name"].startswith(model_name) for m in models)
    except Exception as exc:
        logger.warning("_ollama_model_available check failed: {}", exc)
        return False
