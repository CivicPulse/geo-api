---
phase: 18
slug: code-review
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-29
validated: 2026-03-29
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
| 18-01-01 | 01 | 1 | REVIEW-01 | unit + review | `uv run pytest tests/test_geocoding_api.py tests/test_validation_api.py -v` | ✅ | ✅ green |
| 18-02-01 | 02 | 1 | REVIEW-02 | unit + review | `uv run pytest tests/test_exception_handling.py -v` | ✅ | ✅ green |
| 18-03-01 | 03 | 1 | REVIEW-03 | unit + review | `uv run pytest tests/test_cascade.py -k "WeightMapping or ProviderWeight" -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_geocoding_api.py` — test_geocode_rejects_oversized_address (POST /geocode oversized → 422)
- [x] `tests/test_exception_handling.py` — test_geocode_sqlalchemy_error_returns_500_json (DB error → handled 500)
- [x] `tests/test_geocoding_api.py` — test_set_official_rejects_out_of_range_latitude/longitude (PUT lat/lng → 422)
- [x] `tests/test_cascade.py` — test_postgis_tiger_gets_correct_weight (weight != 0.50 default)
- [x] `tests/test_validation_api.py` — test_validate_rejects_oversized_freeform_address (POST /validate oversized → 422)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full codebase security audit | REVIEW-01 | Requires human/agent code reading of all 45 source files | Read each file through security lens; verify all external inputs flow through Pydantic |
| Full codebase stability audit | REVIEW-02 | Requires tracing exception paths across modules | Trace each exception source to its handler; verify no unguarded bubbling |
| Full codebase performance audit | REVIEW-03 | Requires analyzing query patterns in context | Review each SQL query for N+1 patterns; check pool sizing against deployment limits |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved

## Validation Audit 2026-03-29

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 3 tasks have automated test coverage. 9 security regression tests (Plan 01), 3 exception handling tests (Plan 02), 4 weight mapping tests (Plan 03). Suite: 529 passed.
