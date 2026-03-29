---
phase: 13
slug: spell-correction-and-fuzzy-phonetic-matching
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_spell_corrector.py tests/test_fuzzy_matcher.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~15 seconds (unit), ~45 seconds (full with calibration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_spell_corrector.py tests/test_fuzzy_matcher.py -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 0 | SPELL-01 | unit | `uv run pytest tests/test_spell_corrector.py -x` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 0 | FUZZ-02 | unit | `uv run pytest tests/test_fuzzy_matcher.py -x` | ❌ W0 | ⬜ pending |
| 13-01-03 | 01 | 0 | FUZZ-04 | integration | `uv run pytest tests/test_fuzzy_calibration.py -x` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | SPELL-01 | unit | `uv run pytest tests/test_spell_corrector.py -x` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 1 | SPELL-02 | unit | `uv run pytest tests/test_spell_corrector.py::test_rebuild_dictionary -x` | ❌ W0 | ⬜ pending |
| 13-03-01 | 03 | 1 | FUZZ-02 | unit | `uv run pytest tests/test_fuzzy_matcher.py::test_fuzzy_above_threshold -x` | ❌ W0 | ⬜ pending |
| 13-03-02 | 03 | 1 | FUZZ-03 | unit | `uv run pytest tests/test_fuzzy_matcher.py::test_dmetaphone_tiebreaker -x` | ❌ W0 | ⬜ pending |
| 13-04-01 | 04 | 2 | SPELL-03 | unit | `uv run pytest tests/test_spell_corrector.py::test_rebuild_triggered_after_cli -x` | ❌ W0 | ⬜ pending |
| 13-05-01 | 05 | 2 | FUZZ-04 | integration | `uv run pytest tests/test_fuzzy_calibration.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_spell_corrector.py` — stubs for SPELL-01, SPELL-02, SPELL-03
- [ ] `tests/test_fuzzy_matcher.py` — stubs for FUZZ-02, FUZZ-03
- [ ] `tests/test_fuzzy_calibration.py` — stubs for FUZZ-04 (30-address corpus)
- [ ] `uv add symspellpy>=6.9.0` — required before any spell corrector tests can run

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
