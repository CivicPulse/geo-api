---
phase: 8
slug: openaddresses-provider
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 8 — Validation Strategy

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
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | OA-01, OA-03 | unit+integration | `uv run pytest tests/test_oa_provider.py -v` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | OA-02 | unit | `uv run pytest tests/test_oa_validation.py -v` | ❌ W0 | ⬜ pending |
| 08-01-03 | 01 | 1 | OA-04 | unit | `uv run pytest tests/test_oa_registration.py -v` | ❌ W0 | ⬜ pending |
| 08-02-01 | 02 | 1 | OA-01 | integration | `uv run pytest tests/test_load_oa.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_oa_provider.py` — stubs for OA geocoding provider tests
- [ ] `tests/test_oa_validation.py` — stubs for OA validation provider tests
- [ ] `tests/test_oa_registration.py` — stubs for OA provider registration tests
- [ ] `tests/test_load_oa.py` — stubs for load-oa CLI import tests

*Existing test infrastructure (pytest, conftest.py) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| load-oa imports real .geojson.gz | OA-01 | Requires PostGIS and sample data file | Run `uv run python -m civpulse_geo.cli load-oa data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` and verify row count |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
