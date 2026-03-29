---
phase: 13
slug: spell-correction-and-fuzzy-phonetic-matching
status: draft
nyquist_compliant: true
wave_0_complete: true
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
| 13-01-T1 | 01 | 1 | SPELL-02 | unit | `uv run python -c "from civpulse_geo.models.spell_dictionary import SpellDictionary"` | TDD | ⬜ pending |
| 13-01-T2 | 01 | 1 | SPELL-01 | unit | `uv run pytest tests/test_spell_corrector.py -x -q` | TDD | ⬜ pending |
| 13-01-T3 | 01 | 1 | SPELL-03 | unit | `uv run pytest -x -q` | TDD | ⬜ pending |
| 13-02-T1 | 02 | 2 | FUZZ-02, FUZZ-03 | unit | `uv run pytest tests/test_fuzzy_matcher.py -x -q` | TDD | ⬜ pending |
| 13-02-T2 | 02 | 2 | FUZZ-04 | integration | `uv run pytest tests/test_fuzzy_calibration.py -x -q` | TDD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Test files created via TDD within each task — no separate Wave 0 plan needed.*

- [x] `tests/test_spell_corrector.py` — created in Plan 01 Task 2 (TDD)
- [x] `tests/test_fuzzy_matcher.py` — created in Plan 02 Task 1 (TDD)
- [x] `tests/test_fuzzy_calibration.py` — created in Plan 02 Task 2 (TDD)
- [x] `uv add symspellpy>=6.9.0` — Plan 01 Task 1

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (TDD — tests co-created with implementation)
- [x] No watch-mode flags
- [x] Feedback latency < 45s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-29
