---
phase: 19
slug: dockerfile-and-database-provisioning
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q --ignore=tests/test_import_cli.py --ignore=tests/test_load_oa_cli.py` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --ignore=tests/test_import_cli.py --ignore=tests/test_load_oa_cli.py`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green + all manual smoke tests pass
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | DEPLOY-01 | smoke | `docker build -t geo-api-test .` | N/A — build artifact | ⬜ pending |
| 19-01-02 | 01 | 1 | DEPLOY-01 | smoke | `docker run --rm geo-api-test id` (verify UID 1000) | N/A — runtime check | ⬜ pending |
| 19-01-03 | 01 | 1 | DEPLOY-01 | smoke | `docker run --rm geo-api-test python -c "import fiona"` | N/A — runtime check | ⬜ pending |
| 19-02-01 | 02 | 1 | DEPLOY-08 | SQL | `psql -h thor.tailb56d83.ts.net -U postgres -c "\l civpulse_geo_dev"` | N/A | ⬜ pending |
| 19-02-02 | 02 | 1 | DEPLOY-08 | SQL | `psql -h thor.tailb56d83.ts.net -U postgres -c "\l civpulse_geo_prod"` | N/A | ⬜ pending |
| 19-02-03 | 02 | 1 | DEPLOY-08 | K8s | `kubectl run pg-test --rm -it --image=postgres:16 -n civpulse-dev -- psql ...` | N/A — Wave 0 pod | ⬜ pending |
| 19-02-04 | 02 | 1 | DEPLOY-08 | K8s | `kubectl run pg-test --rm -it --image=postgres:16 -n civpulse-prod -- psql ...` | N/A — Wave 0 pod | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files required — DEPLOY-01 and DEPLOY-08 are infrastructure deliverables validated by smoke tests and manual checks.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker image builds with multi-stage | DEPLOY-01 | Build artifact, not code behavior | `docker build -t geo-api-test .` exits 0 |
| Container runs as non-root UID 1000 | DEPLOY-01 | Runtime container property | `docker run --rm geo-api-test id` shows uid=1000 |
| Image pushed to GHCR and pullable | DEPLOY-01 | Registry operation | `docker pull ghcr.io/civicpulse/geo-api:<tag>` exits 0 |
| Databases provisioned on host PG | DEPLOY-08 | One-time SQL operation | `\l civpulse_geo_dev` and `\l civpulse_geo_prod` exist |
| Extensions enabled per database | DEPLOY-08 | Database configuration | `SELECT extname FROM pg_extension;` includes postgis, pg_trgm, fuzzystrmatch |
| Test pod connectivity from K8s | DEPLOY-08 | Cross-network validation | kubectl run ephemeral pod, connect to PG service |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
