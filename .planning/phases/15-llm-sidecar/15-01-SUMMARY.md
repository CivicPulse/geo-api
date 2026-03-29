---
phase: 15-llm-sidecar
plan: "01"
subsystem: api
tags: [ollama, llm, pydantic, httpx, address-correction, guardrails]

# Dependency graph
requires:
  - phase: 14-cascade-orchestrator-and-consensus-scoring
    provides: CascadeOrchestrator stage pattern, graceful degradation, config Settings class
  - phase: 13-spell-correction-and-fuzzy-phonetic-matching
    provides: SpellCorrector startup pattern for app.state service loading
provides:
  - LLMAddressCorrector class with correct_address async method
  - AddressCorrection Pydantic model (6 nullable string fields)
  - _passes_guardrails function with state-change and zip/state validation
  - _ollama_model_available async function for startup health check
  - Config settings: cascade_llm_enabled (default False), ollama_url, llm_timeout_ms
affects: [15-llm-sidecar/15-02, cascade integration, docker-compose, k8s manifests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LLM interaction via direct httpx (no new dependency) — POST /api/chat with format=JSON schema dict"
    - "Guardrail hard-reject before re-verification: state-change + zip-first-digit-to-state validation"
    - "All LLM errors (HTTP error, malformed JSON, timeout) return None — no retry (D-16)"

key-files:
  created:
    - src/civpulse_geo/services/llm_corrector.py
    - tests/test_llm_corrector.py
  modified:
    - src/civpulse_geo/config.py

key-decisions:
  - "Direct httpx for Ollama client — reuses existing AsyncClient from app.state, no new dependency"
  - "temperature=0 + Ollama format parameter with AddressCorrection.model_json_schema() for deterministic structured output"
  - "ZIP first-digit-to-state-group dict (_ZIP_FIRST_DIGIT_STATES) hardcoded inline — simpler than library, full coverage"
  - "POST timeout 6.0s (slightly above 5s asyncio.wait_for) — lets wait_for handle cancellation cleanly"

patterns-established:
  - "LLM error handling: bare except -> log warning -> return None (no retry, per D-16)"
  - "Guardrail pattern: hard-reject before provider re-verification (not after)"

requirements-completed: [LLM-01, LLM-02, LLM-03]

# Metrics
duration: 12min
completed: 2026-03-29
---

# Phase 15 Plan 01: LLM Sidecar — Corrector Service Summary

**Ollama LLM address corrector with temperature=0 structured JSON output, zip/state guardrails, and feature-flag config — standalone module ready for cascade wiring in Plan 02**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-29T16:08:00Z
- **Completed:** 2026-03-29T16:20:00Z
- **Tasks:** 1 (TDD: RED -> GREEN)
- **Files modified:** 3

## Accomplishments

- LLMAddressCorrector class sends raw address to Ollama /api/chat with temperature=0 and JSON schema format enforcement (D-03, D-04)
- AddressCorrection Pydantic model with 6 nullable string fields mirrors _parse_input_address 5-tuple (D-02)
- _passes_guardrails rejects state-code changes and zip/state mismatches before re-verification (D-14)
- _ollama_model_available async function for startup health check (D-13, D-15)
- Config extended with cascade_llm_enabled=False, ollama_url, llm_timeout_ms=5000 (D-09)
- 13 unit tests pass; pre-existing test_import_cli failure is unrelated (missing sample data file)

## Task Commits

1. **Task 1: LLMAddressCorrector service, AddressCorrection model, guardrails, config settings** - `7a914d6` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD task — tests written first (RED), then implementation (GREEN)_

## Files Created/Modified

- `src/civpulse_geo/services/llm_corrector.py` — LLMAddressCorrector class, AddressCorrection model, _passes_guardrails, _ollama_model_available, _ZIP_FIRST_DIGIT_STATES dict, SYSTEM_PROMPT
- `tests/test_llm_corrector.py` — 13 unit tests covering all behaviors: request payload shape, structured result, HTTP error, malformed JSON, guardrail pass/fail cases, model availability, config defaults
- `src/civpulse_geo/config.py` — Added cascade_llm_enabled, ollama_url, llm_timeout_ms settings

## Decisions Made

- Used direct httpx for Ollama client instead of ollama-python package — reuses existing httpx.AsyncClient from app.state, avoids new dependency, full timeout control
- POST timeout set to 6.0s (slightly above 5s asyncio.wait_for budget) so wait_for handles cancellation rather than httpx raising its own timeout exception
- _ZIP_FIRST_DIGIT_STATES covers 10 digit groups with all 50 states plus territories (PR, VI, AS, GU) — complete coverage with zero dependencies

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None — implementation matched plan specification precisely.

## User Setup Required

None - no external service configuration required in this plan. Docker Compose Ollama service and K8s manifests are in Plans 01 and 04 (LLM-01 and LLM-04).

## Known Stubs

None — this plan builds a pure service module. The LLM stage is not wired into the cascade pipeline yet; that is the explicit scope of Plan 02.

## Next Phase Readiness

- Plan 02 can import LLMAddressCorrector and wire it into CascadeOrchestrator as stage 4 (between fuzzy and consensus)
- All integration points documented: LLMAddressCorrector(ollama_url=settings.ollama_url), correct_address(raw_address, http_client), _passes_guardrails(correction, original_state), _ollama_model_available(url, http_client)
- Config settings are live: settings.cascade_llm_enabled, settings.ollama_url, settings.llm_timeout_ms

---
*Phase: 15-llm-sidecar*
*Completed: 2026-03-29*
