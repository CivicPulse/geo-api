---
phase: 16
slug: audit-gap-closure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_geocoding_service.py tests/test_fuzzy_matcher.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_geocoding_service.py tests/test_fuzzy_matcher.py -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green (11 pre-existing failures allowed, no new failures)
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | FUZZ-02 | unit | `uv run pytest tests/test_startup_wiring.py -x -q` | No — Wave 0 | pending |
| 16-01-02 | 01 | 1 | FUZZ-02, FUZZ-03 | unit | `uv run pytest tests/test_geocoding_service.py -x -q` | Partial — needs cascade stage 3 test | pending |
| 16-01-03 | 01 | 1 | Legacy path | unit | `uv run pytest tests/test_geocoding_service.py -x -q` | No — Wave 0 | pending |
| 16-01-04 | 01 | 1 | SPELL-01/02/03, FUZZ-02/03/04 | docs | File existence check | No — created by task | pending |
| 16-01-05 | 01 | 1 | FIX-04 | docs | `grep "scourgify=0.3" .planning/REQUIREMENTS.md` | Yes — already correct | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_startup_wiring.py` — test that `app.state.fuzzy_matcher` is assigned during startup
- [ ] `tests/test_geocoding_service.py` — add test for `_legacy_geocode` NO_MATCH path (5-tuple unpack)

*Existing infrastructure covers FUZZ-03, FUZZ-04, FIX-01, FIX-02, FIX-03 requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Pre-Existing Test Failures (Do Not Regress)

11 pre-existing failures unrelated to Phase 16:
- `tests/test_import_cli.py` — 10 failures (missing `data/SAMPLE_Address_Points.geojson`)
- `tests/test_load_oa_cli.py` — 1 failure (same reason)

Phase 16 must add zero new failures.

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
