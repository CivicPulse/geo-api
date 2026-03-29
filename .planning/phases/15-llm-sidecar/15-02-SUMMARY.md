---
phase: 15-llm-sidecar
plan: 02
subsystem: cascade-pipeline
tags: [llm, cascade, geocoding, integration]
dependency_graph:
  requires: [15-01]
  provides: [llm-stage-4-cascade, llm-corrected-candidates]
  affects: [cascade.py, geocoding.py, main.py, api/geocoding.py]
tech_stack:
  added: []
  patterns: [conditional-startup-registration, cascade-stage-insertion, app-state-threading]
key_files:
  created: []
  modified:
    - src/civpulse_geo/services/cascade.py
    - src/civpulse_geo/services/geocoding.py
    - src/civpulse_geo/main.py
    - src/civpulse_geo/api/geocoding.py
    - tests/test_cascade.py
decisions:
  - "is_llm_corrected check precedes is_fuzzy in set_by_stage determination — LLM-corrected is more specific stage"
  - "settings mock in LLM tests requires explicit float weight attrs — patching settings globally loses arithmetic"
  - "Stage numbering updated: LLM=4, Consensus=5, Auto-set=6, Commit=7"
metrics:
  duration: "6 min"
  completed: "2026-03-29"
  tasks: 2
  files_modified: 5
requirements: [LLM-01, LLM-02, LLM-03]
---

# Phase 15 Plan 02: LLM Cascade Integration Summary

Wire LLMAddressCorrector into cascade pipeline as Stage 4, initialize at startup, thread parameter through service and API layers, and validate with integration tests.

## What Was Built

**LLM Stage 4 in cascade.py:** Inserted between fuzzy stage (3) and consensus (now 5). Fires only when `CASCADE_LLM_ENABLED=true`, `llm_corrector is not None`, `skip_fuzzy=False` (no high-confidence exact match), and `len(candidates)==0` (all deterministic stages failed). Builds corrected address string from `AddressCorrection`, runs guardrail check, then re-verifies through all registered providers. Only re-verified results enter candidates with `is_llm_corrected=True`.

**ProviderCandidate enhancement:** `is_llm_corrected: bool = False` added after `is_fuzzy`. Powers `set_by_stage = "llm_correction_consensus"` in consensus stage.

**main.py startup:** Conditional LLM corrector initialization using `_ollama_model_available` check. `app.state.llm_corrector = None` always set; populated only when Ollama responds and model is available. Follows same graceful-degradation pattern as spell_corrector.

**GeocodingService threading:** `llm_corrector: LLMAddressCorrector | None = None` parameter added to `geocode()` and forwarded to `orchestrator.run()`.

**API routes:** Both single geocode endpoint and batch `_geocode_one` helper pass `getattr(request.app.state, "llm_corrector", None)` following the established `fuzzy_matcher` pattern.

**Integration tests:** 4 new tests in `TestCascadeOrchestratorLLMStage`:
- `test_llm_correction_enters_reverify_not_candidates` — verifies D-17 re-verify path
- `test_llm_stage_skipped_when_disabled` — `CASCADE_LLM_ENABLED=false` blocks stage
- `test_llm_stage_skipped_when_exact_match_succeeds` — `skip_fuzzy=True` blocks LLM stage
- `test_llm_stage_timeout_degrades_gracefully` — `asyncio.TimeoutError` produces trace entry, no crash

## Truths Verified

- Address failing exact + fuzzy triggers LLM stage when enabled and `llm_corrector` is not None
- LLM correction passing guardrails is re-verified through exact-match providers before entering consensus
- LLM result is never added directly — only re-verified provider results enter candidates
- When Ollama unavailable at startup, `app.state.llm_corrector = None`, cascade proceeds without LLM
- LLM stage timeout degrades gracefully — cascade continues with empty candidates

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed settings mock breaking arithmetic in test**
- **Found during:** Task 2, test run
- **Issue:** Patching `civpulse_geo.services.cascade.settings` with `MagicMock()` made `settings.weight_census` return a MagicMock, which fails in `get_provider_weight` when computing cluster centroid arithmetic (`> 0` comparison)
- **Fix:** Added explicit float assignments for all weight attrs in `mock_settings` for all 3 LLM tests that patch settings
- **Files modified:** tests/test_cascade.py
- **Commit:** 1dc698b

**2. [Rule 1 - Bug] Fixed missing `location_type` in test GeocodingResultSchema**
- **Found during:** Task 2, test run
- **Issue:** `GeocodingResultSchema` requires `location_type` as positional arg; no-match provider in test was omitting it
- **Fix:** Added `location_type="APPROXIMATE"` to no-match provider result in `_geocode_side_effect`
- **Files modified:** tests/test_cascade.py
- **Commit:** 1dc698b

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 874791c | feat(15-02): add LLM stage 4 to cascade and is_llm_corrected to ProviderCandidate |
| 2 | 1dc698b | feat(15-02): thread llm_corrector through GeocodingService, API routes, and startup |

## Known Stubs

None — all integration points are wired through. The LLM stage does not fire until `CASCADE_LLM_ENABLED=true` and Ollama is available; this is intentional feature-flag behavior, not a stub.

## Self-Check: PASSED
