---
phase: 17
slug: tech-debt-resolution
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-29
validated: 2026-03-29
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
| 17-01-01 | 01 | 1 | DEBT-01 | unit | `uv run pytest tests/test_cascade.py -k timeout -v` | ✅ | ✅ green |
| 17-01-02 | 01 | 1 | DEBT-01 | unit | `uv run pytest tests/test_cascade.py -k tiger -v` | ✅ | ✅ green |
| 17-02-01 | 02 | 1 | DEBT-02 | unit | `uv run pytest tests/test_cascade.py -k cache_hit -v` | ✅ | ✅ green |
| 17-03-01 | 03 | 2 | DEBT-03 | unit | `uv run pytest tests/test_spell_startup.py -v` | ✅ | ✅ green |
| 17-04-01 | 04 | 1 | DEBT-04 | unit | `uv run pytest tests/test_load_oa_cli.py -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_cascade.py` — TestPerProviderTimeout, TestCacheHitEarlyExit, TestCacheHitLocalProvidersStillCalled, TestCacheHitConsensusReRun cover DEBT-01, DEBT-02
- [x] `tests/test_spell_startup.py` — test_spell_dict_auto_rebuild_when_empty, test_spell_dict_skip_rebuild_when_populated, test_spell_dict_skip_rebuild_when_staging_empty cover DEBT-03

*Existing `tests/test_load_oa_cli.py` covers DEBT-04.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Tiger geocode under real PostGIS load | DEBT-01 | Requires live Tiger database | Run `uv run pytest tests/ -k tiger --timeout=10` against dev database |

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

All 5 tasks have automated test coverage. Tests created during TDD execution (Plans 01 and 02). Suite: 529 passed.
