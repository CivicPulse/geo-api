---
phase: 18
slug: code-review
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode="auto") |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run ruff check src/ && uv run pytest tests/ -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green + ruff clean
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | REVIEW-01 | unit + review | `uv run pytest tests/test_geocoding_api.py tests/test_validation_api.py -v` | ✅ | ⬜ pending |
| 18-02-01 | 02 | 1 | REVIEW-02 | unit + review | `uv run pytest tests/test_geocoding_api.py tests/test_geocoding_service.py -v` | ✅ | ⬜ pending |
| 18-03-01 | 03 | 1 | REVIEW-03 | unit + review | `uv run pytest tests/test_cascade.py tests/test_providers.py -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_geocoding_api.py` — add test: POST /geocode with oversized address returns 422
- [ ] `tests/test_geocoding_api.py` — add test: POST /geocode with DB error propagates a handled 500 (not raw SQLAlchemy exception)
- [ ] `tests/test_geocoding_api.py` — add test: PUT /geocode/{hash}/official with out-of-range lat/lng returns 422
- [ ] `tests/test_cascade.py` — add test: `get_provider_weight("postgis_tiger")` returns correct weight (not 0.50 default)
- [ ] `tests/test_validation_api.py` — add test: POST /validate with oversized address returns 422

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full codebase security audit | REVIEW-01 | Requires human/agent code reading of all 45 source files | Read each file through security lens; verify all external inputs flow through Pydantic |
| Full codebase stability audit | REVIEW-02 | Requires tracing exception paths across modules | Trace each exception source to its handler; verify no unguarded bubbling |
| Full codebase performance audit | REVIEW-03 | Requires analyzing query patterns in context | Review each SQL query for N+1 patterns; check pool sizing against deployment limits |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
