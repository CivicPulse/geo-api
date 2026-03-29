---
phase: 14
slug: cascade-orchestrator-and-consensus-scoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0.2 + pytest-asyncio >= 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/test_cascade_orchestrator.py tests/test_consensus_scoring.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_cascade_orchestrator.py tests/test_consensus_scoring.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | CASC-01 | unit | `uv run pytest tests/test_cascade_orchestrator.py -x` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | CASC-02 | unit + param | `uv run pytest tests/test_geocoding_service.py -x` | ✅ (extend) | ⬜ pending |
| 14-01-03 | 01 | 1 | CASC-03 | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_early_exit -x` | ❌ W0 | ⬜ pending |
| 14-01-04 | 01 | 1 | CASC-04 | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_timeout_graceful_degradation -x` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | CONS-01 | unit | `uv run pytest tests/test_consensus_scoring.py::test_clustering -x` | ❌ W0 | ⬜ pending |
| 14-02-02 | 02 | 1 | CONS-02 | unit | `uv run pytest tests/test_consensus_scoring.py::test_weights -x` | ❌ W0 | ⬜ pending |
| 14-02-03 | 02 | 1 | CONS-03 | unit | `uv run pytest tests/test_consensus_scoring.py::test_outlier_flagging -x` | ❌ W0 | ⬜ pending |
| 14-02-04 | 02 | 1 | CONS-04 | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_admin_override_protected -x` | ❌ W0 | ⬜ pending |
| 14-02-05 | 02 | 1 | CONS-05 | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_set_by_stage_audit -x` | ❌ W0 | ⬜ pending |
| 14-02-06 | 02 | 1 | CONS-06 | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_dry_run -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_cascade_orchestrator.py` — stubs for CASC-01, CASC-03, CASC-04, CONS-04, CONS-05, CONS-06
- [ ] `tests/test_consensus_scoring.py` — stubs for CONS-01, CONS-02, CONS-03
- [ ] Extend `tests/test_geocoding_service.py` with `@pytest.mark.parametrize("cascade_enabled", [True, False])` for CASC-02

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| P95 latency under 3s | CASC-03 | Requires real provider latency | Run 10 geocode requests against test DB, check timing |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
