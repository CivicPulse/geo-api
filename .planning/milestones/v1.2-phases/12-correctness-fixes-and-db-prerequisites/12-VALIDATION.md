---
phase: 12
slug: correctness-fixes-and-db-prerequisites
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-29
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| **Quick run command** | `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py tests/test_oa_provider.py tests/test_nad_provider.py tests/test_macon_bibb_provider.py tests/test_scourgify_provider.py -q` |
| **Full suite command** | `docker exec geo-api-api-1 python -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py tests/test_oa_provider.py tests/test_nad_provider.py tests/test_macon_bibb_provider.py tests/test_scourgify_provider.py -q`
- **After every plan wave:** Run `docker exec geo-api-api-1 python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | FIX-01 | unit | `uv run pytest tests/test_tiger_provider.py -x -q` | ✅ county filter tests added | ✅ green |
| 12-01-02 | 01 | 1 | FIX-02 | unit | `uv run pytest tests/test_oa_provider.py tests/test_nad_provider.py tests/test_macon_bibb_provider.py -x -q` | ✅ zip prefix fallback tests added | ✅ green |
| 12-01-03 | 01 | 1 | FIX-03 | unit | `uv run pytest tests/test_oa_provider.py -x -q` | ✅ suffix match tests added | ✅ green |
| 12-01-04 | 01 | 1 | FIX-04 | unit | `uv run pytest tests/test_scourgify_provider.py tests/test_tiger_provider.py -x -q` | ✅ confidence 0.3/0.4 asserted | ✅ green |
| 12-02-01 | 02 | 1 | FUZZ-01 | integration | manual — GIN trigram index | Manual-only (requires real data) | ⚠️ manual |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] New test cases in `tests/test_tiger_provider.py` — FIX-01 county filter: `test_tiger_geocode_wrong_county_returns_no_match`, `test_tiger_geocode_correct_county_returns_match`, `test_tiger_geocode_county_fips_kwarg_mismatch`, `test_tiger_geocode_county_fips_kwarg_match`, `test_tiger_geocode_no_state_skips_county_filter`
- [x] New test cases in `tests/test_oa_provider.py` — FIX-02 zip prefix: `test_oa_geocode_zip_prefix_fallback`; FIX-03 suffix: `test_oa_geocode_suffix_match`, `test_parse_input_address_suffix_beaver_falls`; 5-tuple: `test_parse_input_address_returns_5_tuple`
- [x] New test cases in `tests/test_nad_provider.py` — FIX-02 zip prefix: `test_nad_geocode_zip_prefix_fallback`
- [x] New test cases in `tests/test_macon_bibb_provider.py` — FIX-02 zip prefix: `test_macon_bibb_geocode_zip_prefix_fallback`
- [x] Updated assertions in `tests/test_scourgify_provider.py` — `confidence == 0.3` confirmed in `test_confidence_always_0_3`
- [x] Updated assertions in `tests/test_tiger_provider.py` — `confidence == 0.4` confirmed in `test_validate_match_parsed_true_returns_confidence`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GIN trigram indexes performant under load | FUZZ-01 | Requires real NAD data (80M rows) | Query `SELECT similarity('MERCER', street_name) FROM nad_points LIMIT 10` and check < 500ms |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (tests created during execution)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-29

## Validation Audit 2026-03-29
| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

*All requirements had automated tests created during phase execution. VALIDATION.md updated retroactively.*
