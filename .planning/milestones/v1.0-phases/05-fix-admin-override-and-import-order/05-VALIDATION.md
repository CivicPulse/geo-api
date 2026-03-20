---
phase: 5
slug: fix-admin-override-and-import-order
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | GEO-07 | unit | `uv run pytest tests/test_geocoding.py -k admin_override -v` | ✅ | ⬜ pending |
| 05-01-02 | 01 | 1 | GEO-07 | unit | `uv run pytest tests/test_geocoding.py -k set_custom_official -v` | ✅ | ⬜ pending |
| 05-01-03 | 01 | 1 | DATA-03 | integration | `uv run pytest tests/test_cli.py -k admin_override -v` | ✅ | ⬜ pending |
| 05-01-04 | 01 | 1 | DATA-03 | docs | `grep -q "DO NOTHING" src/civpulse_geo/cli/__init__.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test framework or fixture setup needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| admin_overrides row visible in DB after API call | GEO-07 | Requires running DB | `docker compose exec db psql -c "SELECT * FROM admin_overrides"` after `PUT /geocode/{hash}/official` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
