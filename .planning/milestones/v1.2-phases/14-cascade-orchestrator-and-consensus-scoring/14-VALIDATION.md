---
phase: 14
slug: cascade-orchestrator-and-consensus-scoring
status: approved
nyquist_compliant: true
wave_0_complete: true
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
| 14-01-01 | 01 | 1 | CASC-01 | unit | `uv run pytest tests/test_cascade.py -x` | ✅ `test_cascade.py` (consolidated) | ✅ green |
| 14-01-02 | 01 | 1 | CASC-02 | unit + param | `uv run pytest tests/test_geocoding_service.py -x` | ✅ cascade_enabled parametrize | ✅ green |
| 14-01-03 | 01 | 1 | CASC-03 | unit | `uv run pytest tests/test_cascade.py -k early_exit -x` | ✅ `test_early_exit_skips_fuzzy_when_high_confidence`, `test_early_exit_does_not_skip_consensus` | ✅ green |
| 14-01-04 | 01 | 1 | CASC-04 | unit | `uv run pytest tests/test_cascade.py -k timeout -x` | ✅ `test_stage_timeout_cascade_continues_with_empty` | ✅ green |
| 14-02-01 | 02 | 1 | CONS-01 | unit | `uv run pytest tests/test_cascade.py -k cluster -x` | ✅ `test_seed_creates_cluster_*`, `test_two_results_within_100m_cluster_together`, `test_result_over_100m_starts_new_cluster` | ✅ green |
| 14-02-02 | 02 | 1 | CONS-02 | unit | `uv run pytest tests/test_cascade.py -k weight -x` | ✅ `test_census_weight`, `test_openaddresses_weight`, `test_tiger_weight`, etc. | ✅ green |
| 14-02-03 | 02 | 1 | CONS-03 | unit | `uv run pytest tests/test_cascade.py -k outlier -x` | ✅ `test_outlier_flagging_over_1km`, `test_no_outlier_when_within_1km` | ✅ green |
| 14-02-04 | 02 | 1 | CONS-04 | unit | `uv run pytest tests/test_cascade.py -k admin_override -x` | ✅ `test_admin_override_blocks_cascade_auto_set` | ✅ green |
| 14-02-05 | 02 | 1 | CONS-05 | unit | `uv run pytest tests/test_cascade.py -k auto_sets_official -x` | ✅ `test_single_high_confidence_auto_sets_official`, `test_single_low_confidence_does_not_auto_set_official` | ✅ green |
| 14-02-06 | 02 | 1 | CONS-06 | unit | `uv run pytest tests/test_cascade.py -k dry_run -x` | ✅ `test_dry_run_populates_would_set_official_not_writes` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_cascade.py` — consolidated cascade + consensus tests (34 test functions covering CASC-01..04, CONS-01..06)
- [x] `tests/test_geocoding_service.py` — cascade_enabled parametrize for CASC-02

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| P95 latency under 3s | CASC-03 | Requires real provider latency | Run 10 geocode requests against test DB, check timing |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (tests created via TDD during execution)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-29

## Validation Audit 2026-03-29
| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

*Implementation consolidated planned `test_cascade_orchestrator.py` + `test_consensus_scoring.py` into single `test_cascade.py`. All requirements covered. VALIDATION.md updated retroactively.*
