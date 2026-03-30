---
phase: 22
slug: observability
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (already installed) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | OBS-01 | unit | `uv run pytest tests/test_logging.py -x` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | OBS-01, OBS-04 | integration | `uv run pytest tests/test_request_id_middleware.py -x` | ❌ W0 | ⬜ pending |
| 22-02-01 | 02 | 1 | OBS-02 | integration | `uv run pytest tests/test_metrics_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 22-02-02 | 02 | 1 | OBS-02 | integration | `uv run pytest tests/test_metrics_endpoint.py::test_counter_increments -x` | ❌ W0 | ⬜ pending |
| 22-03-01 | 03 | 2 | OBS-03 | unit | `uv run pytest tests/test_tracing.py::test_setup -x` | ❌ W0 | ⬜ pending |
| 22-03-02 | 03 | 2 | OBS-03 | integration | `uv run pytest tests/test_tracing.py::test_fastapi_span -x` | ❌ W0 | ⬜ pending |
| 22-04-01 | 04 | 2 | OBS-04 | unit | `uv run pytest tests/test_logging.py::test_trace_id_injection -x` | ❌ W0 | ⬜ pending |
| 22-04-02 | 04 | 2 | OBS-04 | integration | `uv run pytest tests/test_request_id_middleware.py::test_response_header -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_logging.py` — stubs for OBS-01, OBS-04 (JSON format, trace_id injection)
- [ ] `tests/test_request_id_middleware.py` — stubs for OBS-01, OBS-04 (request_id binding, response header)
- [ ] `tests/test_metrics_endpoint.py` — stubs for OBS-02 (endpoint, counter increment)
- [ ] `tests/test_tracing.py` — stubs for OBS-03 (TracerProvider setup, FastAPI span creation)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| VictoriaMetrics scrapes /metrics successfully | OBS-02 | Requires deployed K8s cluster with VictoriaMetrics | Port-forward, curl /metrics, verify VM target shows UP |
| Traces appear in Tempo | OBS-03 | Requires deployed Tempo instance | Port-forward Tempo, query for civpulse-geo service traces |
| Loki log entry has clickable trace_id to Tempo | OBS-04 | Requires deployed Grafana + Loki + Tempo | Port-forward Grafana, search Loki logs, click trace_id link |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
