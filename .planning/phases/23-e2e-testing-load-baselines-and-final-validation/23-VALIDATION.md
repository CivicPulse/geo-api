---
phase: 23
slug: e2e-testing-load-baselines-and-final-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **E2E only command** | `uv run pytest tests/e2e/ -v -m e2e` |
| **Estimated runtime** | ~30 seconds (unit), ~120 seconds (E2E with port-forward) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **E2E gate (after deployment):** `uv run pytest tests/e2e/ -v -m e2e`
- **Before `/gsd:verify-work`:** Full suite must be green AND E2E green AND Locust CSVs produced AND all verify scripts exit 0
- **Max feedback latency:** 30 seconds (unit), 120 seconds (E2E)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | TEST-01 | E2E (real HTTP) | `uv run pytest tests/e2e/test_providers_geocode.py -v -m e2e` | ❌ W0 | ⬜ pending |
| 23-01-02 | 01 | 1 | TEST-01 | E2E (real HTTP) | `uv run pytest tests/e2e/test_providers_validate.py -v -m e2e` | ❌ W0 | ⬜ pending |
| 23-01-03 | 01 | 1 | TEST-02 | E2E (real HTTP) | `uv run pytest tests/e2e/test_cascade_pipeline.py -v -m e2e` | ❌ W0 | ⬜ pending |
| 23-02-01 | 02 | 2 | TEST-03 | Load test (Locust) | `locust -f loadtests/geo_api_locustfile.py --headless --csv=results/baselines ...` | ❌ W0 | ⬜ pending |
| 23-03-01 | 03 | 2 | TEST-04 | Integration script | `uv run python scripts/verify/verify_loki.py` | ❌ W0 | ⬜ pending |
| 23-03-02 | 03 | 2 | TEST-05 | Integration script | `uv run python scripts/verify/verify_tempo.py` | ❌ W0 | ⬜ pending |
| 23-03-03 | 03 | 2 | TEST-06 | Integration script | `uv run python scripts/verify/verify_victoriametrics.py` | ❌ W0 | ⬜ pending |
| 23-04-01 | 04 | 3 | VAL-01 | Process checklist | Manual checklist enforcement | ❌ W0 | ⬜ pending |
| 23-04-02 | 04 | 3 | VAL-02 | Process checklist | Manual checklist annotation | ❌ W0 | ⬜ pending |
| 23-04-03 | 04 | 3 | VAL-03 | Manual checklist | `cat .planning/phases/23-*/23-VALIDATION-CHECKLIST.md` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/e2e/__init__.py` — package marker
- [ ] `tests/e2e/conftest.py` — `e2e_client` and `provider_addresses` fixtures
- [ ] `tests/e2e/fixtures/provider_addresses.json` — per-provider known-good address data (JSON, not YAML — avoids pyyaml dep)
- [ ] `tests/e2e/test_providers_geocode.py` — parametrized geocode E2E per provider
- [ ] `tests/e2e/test_providers_validate.py` — parametrized validate E2E per provider
- [ ] `tests/e2e/test_cascade_pipeline.py` — cascade E2E (TEST-02)
- [ ] `loadtests/geo_api_locustfile.py` — Locust HttpUser task definitions
- [ ] `loadtests/addresses/cold_cache_addresses.txt` — unique addresses for cold-cache baseline
- [ ] `loadtests/addresses/warm_cache_addresses.txt` — repeated addresses for warm-cache baseline
- [ ] `scripts/verify/verify_loki.py` — Loki log field assertions
- [ ] `scripts/verify/verify_tempo.py` — Tempo trace span assertions
- [ ] `scripts/verify/verify_victoriametrics.py` — VictoriaMetrics metric assertions
- [ ] `.planning/phases/23-e2e-testing-load-baselines-and-final-validation/23-VALIDATION-CHECKLIST.md` — 7-category final validation checklist
- [ ] `pyproject.toml` — register `e2e` pytest marker
- [ ] `uv add --dev locust` — install Locust 2.43.3

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Blockers fixed in-phase | VAL-01 | Process constraint — requires human judgment on blocker severity | Review each REQUIREMENTS.md item flagged as blocker; resolve or defer with justification |
| Non-blockers logged | VAL-02 | Process constraint — requires human annotation | Annotate non-blocker items in REQUIREMENTS.md with deferral notes |
| Clean validation pass | VAL-03 | Comprehensive 7-category checklist needs human sign-off | Run 23-VALIDATION-CHECKLIST.md; all 7 categories must show no blockers |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (unit), < 120s (E2E)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
