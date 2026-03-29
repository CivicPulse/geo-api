---
phase: 9
slug: tiger-provider
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/test_tiger_provider.py tests/test_tiger_cli.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_tiger_provider.py tests/test_tiger_cli.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | TIGR-01 | unit | `uv run pytest tests/test_tiger_provider.py -k "geocode" -x` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | TIGR-01 | unit | `uv run pytest tests/test_tiger_provider.py -k "no_match" -x` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | TIGR-02 | unit | `uv run pytest tests/test_tiger_provider.py -k "validate" -x` | ❌ W0 | ⬜ pending |
| 09-01-04 | 01 | 1 | TIGR-02 | unit | `uv run pytest tests/test_tiger_provider.py -k "parsed_false" -x` | ❌ W0 | ⬜ pending |
| 09-01-05 | 01 | 1 | TIGR-03 | unit | `uv run pytest tests/test_tiger_provider.py -k "confidence" -x` | ❌ W0 | ⬜ pending |
| 09-01-06 | 01 | 1 | TIGR-03 | unit | `uv run pytest tests/test_tiger_provider.py -k "clamp" -x` | ❌ W0 | ⬜ pending |
| 09-01-07 | 01 | 1 | TIGR-04 | unit | `uv run pytest tests/test_tiger_provider.py -k "extension" -x` | ❌ W0 | ⬜ pending |
| 09-01-08 | 01 | 1 | TIGR-04 | unit | `uv run pytest tests/test_tiger_provider.py -k "warning" -x` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 2 | TIGR-05 | unit | `uv run pytest tests/test_tiger_cli.py -k "extensions" -x` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 2 | TIGR-05 | unit | `uv run pytest tests/test_tiger_cli.py -k "fips" -x` | ❌ W0 | ⬜ pending |
| 09-INT-01 | 01 | 2 | TIGR-01 | integration | `uv run pytest tests/test_tiger_provider.py -m tiger -x` | ❌ W0 | ⬜ pending |
| 09-INT-02 | 01 | 2 | TIGR-02 | integration | `uv run pytest tests/test_tiger_provider.py -m tiger -k "validate" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tiger_provider.py` — unit tests for TigerGeocodingProvider + TigerValidationProvider (mock pattern from test_oa_provider.py)
- [ ] `tests/test_tiger_cli.py` — unit tests for setup-tiger CLI command (FIPS conversion, extension install)
- [ ] `pyproject.toml` markers config — add `markers = ["tiger: marks tests requiring Tiger/Line data"]` to `[tool.pytest.ini_options]`

*Existing infrastructure covers test framework and conftest.py.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker init script loads GA Tiger data on first startup | TIGR-05 | Requires fresh Docker volume and ~200MB download | 1. `docker compose down -v` 2. `docker compose up -d` 3. Verify `tiger_data.ga_addr` table exists |
| setup-tiger downloads and loads state data | TIGR-05 | Requires running Docker container with network access | 1. `docker compose exec db bash` 2. Run generated loader script 3. Verify tables created |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
