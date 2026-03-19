---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` section (Wave 0 creates) |
| **Quick run command** | `uv run pytest tests/ -x -q --ignore=tests/integration` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds (unit only), ~15 seconds (full with integration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --ignore=tests/integration`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/test_normalization.py -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/test_normalization.py::test_zip5_only -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/test_normalization.py::test_unit_excluded -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | INFRA-02 | unit | `uv run pytest tests/test_providers.py::test_missing_method_raises -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | INFRA-02 | unit | `uv run pytest tests/test_providers.py::test_registry_enforces -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | INFRA-05 | integration | `uv run pytest tests/test_health.py -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | INFRA-05 | unit | `uv run pytest tests/test_health.py::test_health_db_down -x` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | INFRA-07 | smoke | `docker compose up -d && curl localhost:8000/health` | manual | ⬜ pending |
| 01-04-02 | 04 | 2 | INFRA-07 | integration | `uv run pytest tests/test_migrations.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — async engine, test session, TestClient fixtures; `TEST_DATABASE_URL` env variable gating for integration tests
- [ ] `tests/test_normalization.py` — stubs for INFRA-01 (canonical key, ZIP5, unit exclusion)
- [ ] `tests/test_providers.py` — stubs for INFRA-02 (ABC enforcement, registry eager load)
- [ ] `tests/test_health.py` — stubs for INFRA-05 (happy path + mocked DB failure)
- [ ] `tests/test_migrations.py` — stubs for INFRA-07 (schema existence smoke test)
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"` for pytest-asyncio

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` starts API + PostGIS with seed data | INFRA-07 | Requires Docker daemon and full container orchestration | 1. Run `docker compose up -d` 2. Wait for healthy status 3. `curl localhost:8000/health` returns 200 4. Check seed data: `docker compose exec db psql -U civpulse -d civpulse_geo -c "SELECT count(*) FROM addresses"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
