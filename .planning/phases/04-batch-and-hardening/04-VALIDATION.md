---
phase: 4
slug: batch-and-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | pyproject.toml — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| **Quick run command** | `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | INFRA-03 | unit | `uv run pytest tests/test_batch_geocoding_api.py -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | INFRA-03 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_partial_failure -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | INFRA-03 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_exceeds_limit -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | INFRA-03 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_empty -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | INFRA-04 | unit | `uv run pytest tests/test_batch_validation_api.py -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | INFRA-04 | unit | `uv run pytest tests/test_batch_validation_api.py::test_batch_validate_partial_failure -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 01 | 1 | INFRA-06 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_response_structure -x` | ❌ W0 | ⬜ pending |
| 04-03-02 | 01 | 1 | INFRA-06 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_all_fail_returns_422 -x` | ❌ W0 | ⬜ pending |
| 04-03-03 | 01 | 1 | INFRA-06 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_partial_failure -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_batch_geocoding_api.py` — stubs for INFRA-03 and INFRA-06 (geocode path)
- [ ] `tests/test_batch_validation_api.py` — stubs for INFRA-04 and INFRA-06 (validate path)

*conftest.py and all fixtures already exist — no framework install needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
