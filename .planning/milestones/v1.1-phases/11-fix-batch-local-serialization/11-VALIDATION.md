---
phase: 11
slug: fix-batch-local-serialization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | GAP-INT-01 | regression | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_local_results_included tests/test_batch_validation_api.py::test_batch_validate_local_candidates_included -v` | ✅ | ⬜ pending |
| 11-01-02 | 01 | 1 | GAP-INT-01 | integration | `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Regression tests `test_batch_geocode_local_results_included` and `test_batch_validate_local_candidates_included` were committed in `f6f904d` alongside the fix.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
