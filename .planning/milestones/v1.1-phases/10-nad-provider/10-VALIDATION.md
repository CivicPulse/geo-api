---
phase: 10
slug: nad-provider
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — asyncio_mode = "auto" |
| **Quick run command** | `.venv/bin/pytest tests/test_nad_provider.py tests/test_load_nad_cli.py -x` |
| **Full suite command** | `.venv/bin/pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/test_nad_provider.py tests/test_load_nad_cli.py -x`
- **After every plan wave:** Run `.venv/bin/pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 0 | NAD-01 | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestPlacementMapping -x` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 0 | NAD-01 | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADGeocodingProvider -x` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 1 | NAD-01 | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADGeocodingProvider::test_geocode_no_match_on_parse_failure -x` | ❌ W0 | ⬜ pending |
| 10-02-01 | 01 | 1 | NAD-02 | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADValidationProvider::test_validate_match -x` | ❌ W0 | ⬜ pending |
| 10-02-02 | 01 | 1 | NAD-02 | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADValidationProvider::test_validate_scourgify_fallback -x` | ❌ W0 | ⬜ pending |
| 10-03-01 | 02 | 0 | NAD-03 | unit | `.venv/bin/pytest tests/test_load_nad_cli.py::TestLoadNadCli::test_load_nad_requires_state -x` | ❌ W0 | ⬜ pending |
| 10-03-02 | 02 | 1 | NAD-03 | unit | `.venv/bin/pytest tests/test_load_nad_cli.py -x` | ✅ (partial) | ⬜ pending |
| 10-04-01 | 01 | 1 | NAD-04 | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNadDataAvailable -x` | ❌ W0 | ⬜ pending |
| 10-04-02 | 01 | 2 | NAD-04 | integration | `.venv/bin/pytest tests/test_nad_provider.py::TestNADRegistration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_nad_provider.py` — stubs covering NAD-01, NAD-02, NAD-04 (providers + `_nad_data_available` + PLACEMENT_MAP)
- [ ] `tests/test_load_nad_cli.py` — extend existing file with NAD-03 cases (--state required, ZIP input, state filtering, COPY pipeline smoke test with mock DB)

*Existing `tests/test_load_nad_cli.py` covers stub behavior only. Full implementation tests are Wave 0 additions.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| load-nad with real NAD_r21_TXT.zip file populates nad_points via COPY | NAD-03 | Requires 35.8 GB uncompressed dataset; not suitable for CI | Run `civpulse-geo load-nad data/NAD_r21_TXT.zip --state GA`; verify `SELECT COUNT(*) FROM nad_points` > 0; verify row populated via COPY not row-by-row INSERT |
| Geocode call against real NAD data returns Placement-mapped result | NAD-01 | Requires real loaded dataset | POST `/geocode` with GA address; verify `location_type` and `confidence` match PLACEMENT_MAP |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
