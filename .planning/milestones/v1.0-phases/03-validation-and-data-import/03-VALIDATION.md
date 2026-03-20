---
phase: 3
slug: validation-and-data-import
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~1 second (baseline 90 tests in 0.47s) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | VAL-01 | integration | `uv run pytest tests/test_validation_api.py -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | VAL-02 | unit | `uv run pytest tests/test_scourgify_provider.py::test_validate_freeform -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | VAL-03 | unit | `uv run pytest tests/test_scourgify_provider.py::test_validate_structured -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | VAL-04 | unit | `uv run pytest tests/test_validation_api.py::test_confidence_in_response -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | VAL-05 | unit | `uv run pytest tests/test_scourgify_provider.py::test_usps_abbreviations -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | VAL-06 | unit | `uv run pytest tests/test_scourgify_provider.py::test_dpv_always_false -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 1 | VAL-02 | integration | `uv run pytest tests/test_validation_api.py::test_unparseable_returns_422 -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | DATA-01 | unit | `uv run pytest tests/test_import_cli.py::test_import_geojson -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 2 | DATA-01 | unit | `uv run pytest tests/test_import_cli.py::test_import_kml -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | DATA-01 | unit | `uv run pytest tests/test_import_cli.py::test_import_shp -x` | ❌ W0 | ⬜ pending |
| 03-02-04 | 02 | 2 | DATA-02 | unit | `uv run pytest tests/test_import_cli.py::test_provider_name -x` | ❌ W0 | ⬜ pending |
| 03-02-05 | 02 | 2 | DATA-03 | unit | `uv run pytest tests/test_import_cli.py::test_official_set_on_import -x` | ❌ W0 | ⬜ pending |
| 03-02-06 | 02 | 2 | DATA-03 | unit | `uv run pytest tests/test_import_cli.py::test_official_not_overwritten -x` | ❌ W0 | ⬜ pending |
| 03-02-07 | 02 | 2 | DATA-04 | unit | `uv run pytest tests/test_import_cli.py::test_upsert_idempotent -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_scourgify_provider.py` — stubs for VAL-02, VAL-03, VAL-05, VAL-06 provider unit tests
- [ ] `tests/test_validation_api.py` — stubs for VAL-01, VAL-04 API integration tests + 422 error case
- [ ] `tests/test_validation_service.py` — stubs for ValidationService cache-first logic
- [ ] `tests/test_import_cli.py` — stubs for DATA-01, DATA-02, DATA-03, DATA-04

*Existing infrastructure covers framework installation — pytest already configured.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SHP CRS reprojection accuracy | DATA-01 | Requires visual/numeric verification of coordinate transform from EPSG:2240 to WGS84 | Import sample SHP, verify lat/lon values are in expected Bibb County range (32.8°N, -83.6°W) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
