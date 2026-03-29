---
phase: 15
slug: llm-sidecar
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-29
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | LLM-01 | integration | `uv run pytest tests/test_llm_corrector.py -k ollama_model_available -x` | ✅ `test_ollama_model_available_returns_true`, `_false_when_missing`, `_false_on_error` | ✅ green |
| 15-01-02 | 01 | 1 | LLM-01 | integration | `uv run pytest tests/test_llm_corrector.py -k config -x` | ✅ `test_llm_disabled_when_flag_false`, `test_config_defaults` | ✅ green |
| 15-02-01 | 02 | 2 | LLM-02 | unit | `uv run pytest tests/test_llm_corrector.py -k structured_result -x` | ✅ `test_corrector_returns_structured_result`, `test_corrector_request_payload_shape` | ✅ green |
| 15-02-02 | 02 | 2 | LLM-02 | integration | `uv run pytest tests/test_cascade.py -k llm_correction_enters_reverify -x` | ✅ `test_llm_correction_enters_reverify_not_candidates` | ✅ green |
| 15-03-01 | 02 | 2 | LLM-03 | unit | `uv run pytest tests/test_llm_corrector.py -k rejects_state_change -x` | ✅ `test_guardrail_rejects_state_change` | ✅ green |
| 15-03-02 | 02 | 2 | LLM-03 | unit | `uv run pytest tests/test_llm_corrector.py -k zip_state_mismatch -x` | ✅ `test_guardrail_rejects_zip_state_mismatch` | ✅ green |
| 15-04-01 | 02 | 2 | LLM-04 | integration | `uv run pytest tests/test_cascade.py -k llm_stage_timeout -x` | ✅ `test_llm_stage_timeout_degrades_gracefully` | ✅ green |
| 15-04-02 | 02 | 2 | LLM-04 | integration | `uv run pytest tests/test_llm_corrector.py -k http_error -x` | ✅ `test_corrector_returns_none_on_http_error`, `test_corrector_returns_none_on_malformed_json` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_llm_corrector.py` — resolved by Plan 15-01 T1 (tdd=true, creates tests before implementation)
- [x] Test fixtures for mocking Ollama HTTP responses — resolved by Plan 15-01 T1 TDD task

*Wave 0 satisfied by TDD approach in Plan 15-01 Task 1 which creates tests/test_llm_corrector.py as part of Wave 1 execution.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose model pull on first start | LLM-01 | Requires fresh Docker volume | Start with empty volume, verify qwen2.5:3b pulled automatically |

*All other behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (TDD in Plan 15-01)
- [x] No watch-mode flags
- [x] Feedback latency < 45s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-29

## Validation Audit 2026-03-29
| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

*All LLM tests in `test_llm_corrector.py` (unit) + cascade integration tests in `test_cascade.py`. VALIDATION.md updated retroactively.*
