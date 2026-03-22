---
phase: 7
slug: pipeline-infrastructure
status: draft
nyquist_compliant: false
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
| 07-01-01 | 01 | 1 | PIPE-02 | unit | `uv run pytest tests/test_provider_abc.py -x -q` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | PIPE-01 | unit | `uv run pytest tests/test_service_bypass.py -x -q` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | PIPE-03 | integration | `uv run pytest tests/test_staging_tables.py -x -q` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | PIPE-04 | integration | `uv run pytest tests/test_staging_tables.py -x -q` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | PIPE-05 | unit | `uv run pytest tests/test_cli_load.py -x -q` | ❌ W0 | ⬜ pending |
| 07-03-02 | 03 | 2 | PIPE-06 | unit | `uv run pytest tests/test_cli_load.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_provider_abc.py` — stubs for PIPE-02 (is_local property)
- [ ] `tests/test_service_bypass.py` — stubs for PIPE-01 (bypass caching for local providers)
- [ ] `tests/test_staging_tables.py` — stubs for PIPE-03, PIPE-04 (staging table existence and indexes)
- [ ] `tests/test_cli_load.py` — stubs for PIPE-05, PIPE-06 (CLI command registration)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GiST spatial index verified in DB | PIPE-03, PIPE-04 | Requires running DB with PostGIS | `SELECT indexname FROM pg_indexes WHERE tablename = 'openaddresses_points'` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
