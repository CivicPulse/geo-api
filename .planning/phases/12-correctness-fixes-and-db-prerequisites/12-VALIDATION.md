---
phase: 12
slug: correctness-fixes-and-db-prerequisites
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 12-01-01 | 01 | 1 | FIX-01 | unit | `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py -q` | Partial — needs county filter tests | ⬜ pending |
| 12-01-02 | 01 | 1 | FIX-02 | unit | `docker exec geo-api-api-1 python -m pytest tests/test_oa_provider.py tests/test_nad_provider.py tests/test_macon_bibb_provider.py -q` | Partial — needs zip prefix tests | ⬜ pending |
| 12-01-03 | 01 | 1 | FIX-03 | unit | `docker exec geo-api-api-1 python -m pytest tests/test_oa_provider.py tests/test_nad_provider.py -q` | Needs new suffix tests | ⬜ pending |
| 12-01-04 | 01 | 1 | FIX-04 | unit | `docker exec geo-api-api-1 python -m pytest tests/test_scourgify_provider.py tests/test_tiger_provider.py -q` | Needs assertion updates (1.0→0.3/0.4) | ⬜ pending |
| 12-02-01 | 02 | 1 | FUZZ-01 | integration | `docker exec geo-api-db-1 psql -U postgres -d civpulse_geo -c "SELECT indexname FROM pg_indexes WHERE indexname LIKE '%trgm%';"` | New test needed | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New test cases in `tests/test_tiger_provider.py` — covers FIX-01 county filter behavior (wrong-county → NO_MATCH, correct-county → match)
- [ ] New test cases in `tests/test_oa_provider.py` — covers FIX-02 zip prefix fallback, FIX-03 suffix matching, 5-tuple destructuring
- [ ] New test cases in `tests/test_nad_provider.py` — covers FIX-02 zip prefix fallback for NAD
- [ ] New test cases in `tests/test_macon_bibb_provider.py` — covers FIX-02 zip prefix fallback for Macon-Bibb
- [ ] Updated assertions in `tests/test_scourgify_provider.py` — `confidence == 1.0` must change to `== 0.3`
- [ ] Updated assertions in `tests/test_tiger_provider.py` — Tiger validation `confidence == 1.0` must change to `== 0.4`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GIN trigram indexes performant under load | FUZZ-01 | Requires real NAD data (80M rows) | Query `SELECT similarity('MERCER', street_name) FROM nad_points LIMIT 10` and check < 500ms |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
