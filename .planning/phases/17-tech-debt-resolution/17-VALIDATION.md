---
phase: 17
slug: tech-debt-resolution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` |
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
| 17-01-01 | 01 | 1 | DEBT-01 | unit | `uv run pytest tests/test_cascade.py -k timeout -v` | ❌ W0 | ⬜ pending |
| 17-01-02 | 01 | 1 | DEBT-01 | unit | `uv run pytest tests/test_cascade.py -k tiger -v` | ❌ W0 | ⬜ pending |
| 17-02-01 | 02 | 1 | DEBT-02 | unit | `uv run pytest tests/test_cascade.py -k cache_hit -v` | ❌ W0 | ⬜ pending |
| 17-03-01 | 03 | 2 | DEBT-03 | unit | `uv run pytest tests/test_spell_corrector.py -k rebuild -v` | ❌ W0 | ⬜ pending |
| 17-04-01 | 04 | 1 | DEBT-04 | unit | `uv run pytest tests/test_load_oa_cli.py -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_cascade.py` — add timeout and cache_hit test stubs for DEBT-01, DEBT-02
- [ ] `tests/test_spell_corrector.py` — add rebuild_dictionary auto-populate test stub for DEBT-03

*Existing `tests/test_load_oa_cli.py` covers DEBT-04.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Tiger geocode under real PostGIS load | DEBT-01 | Requires live Tiger database | Run `uv run pytest tests/ -k tiger --timeout=10` against dev database |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
