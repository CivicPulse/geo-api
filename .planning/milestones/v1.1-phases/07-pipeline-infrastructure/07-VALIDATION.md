---
phase: 7
slug: pipeline-infrastructure
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-22
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `uv run pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `uv run pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | PIPE-02 | unit | `uv run pytest tests/test_providers.py -x -q` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | PIPE-01 | unit | `uv run pytest tests/test_geocoding_service.py tests/test_validation_service.py -x -q` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | PIPE-03, PIPE-04 | integration | `uv run python -c "from civpulse_geo.models import OpenAddressesPoint, NADPoint"` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | PIPE-05, PIPE-06 | unit | `uv run pytest tests/test_load_oa_cli.py tests/test_load_nad_cli.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_providers.py` — extend with is_local property tests (PIPE-02)
- [ ] `tests/test_geocoding_service.py` — add local provider bypass tests (PIPE-01)
- [ ] `tests/test_validation_service.py` — add local provider bypass tests (PIPE-01)
- [ ] `tests/test_load_oa_cli.py` — CLI command registration tests (PIPE-05)
- [ ] `tests/test_load_nad_cli.py` — CLI command registration tests (PIPE-06)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GiST spatial index verified in DB | PIPE-03, PIPE-04 | Requires running DB with PostGIS | `SELECT indexname FROM pg_indexes WHERE tablename = 'openaddresses_points'` |

---

## Carry-Forward Notes

- OfficialGeocoding auto-set for local providers is deliberately deferred to Phase 8. Local results have no ORM row (no geocoding_result_id), so the FK-based OfficialGeocoding machinery cannot reference them yet. Phase 8 must address this when OA provider produces real results.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-22
