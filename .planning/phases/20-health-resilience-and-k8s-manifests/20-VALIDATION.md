---
phase: 20
slug: health-resilience-and-k8s-manifests
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/test_health.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_health.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green + `kubectl kustomize k8s/overlays/dev` and `k8s/overlays/prod` build clean
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | RESIL-01 | unit | `uv run pytest tests/test_health.py::test_health_live -x` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | RESIL-01 | unit | `uv run pytest tests/test_health.py::test_health_live_db_down -x` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | RESIL-02 | unit | `uv run pytest tests/test_health.py::test_health_ready_ok -x` | ❌ W0 | ⬜ pending |
| 20-01-04 | 01 | 1 | RESIL-02 | unit | `uv run pytest tests/test_health.py::test_health_ready_db_down -x` | ❌ W0 | ⬜ pending |
| 20-01-05 | 01 | 1 | RESIL-02 | unit | `uv run pytest tests/test_health.py::test_health_ready_insufficient_providers -x` | ❌ W0 | ⬜ pending |
| 20-02-01 | 02 | 1 | RESIL-03 | unit | `uv run pytest tests/test_shutdown.py -x` | ❌ W0 | ⬜ pending |
| 20-03-01 | 03 | 2 | DEPLOY-02/03/05 | smoke | `kubectl kustomize k8s/overlays/dev` | ❌ W0 | ⬜ pending |
| 20-03-02 | 03 | 2 | DEPLOY-07 | smoke | `kubectl apply --dry-run=client -f k8s/overlays/dev/argocd-app.yaml` | ❌ W0 | ⬜ pending |
| 20-04-01 | 04 | 2 | RESIL-04 | smoke | `uv run geo-import rebuild-dictionary --help` | ✅ | ⬜ pending |
| 20-04-02 | 04 | 2 | DEPLOY-04 | smoke | `uv run alembic --help` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_health.py` — extend with `test_health_live`, `test_health_live_db_down`, `test_health_ready_ok`, `test_health_ready_db_down`, `test_health_ready_insufficient_providers`
- [ ] `tests/test_shutdown.py` — verify lifespan shutdown calls `engine.dispose()`
- [ ] `k8s/base/` directory and all base manifest files
- [ ] `k8s/overlays/dev/` and `k8s/overlays/prod/` directories and all overlay files

*Existing infrastructure covers CLI smoke tests (RESIL-04, DEPLOY-04).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ArgoCD shows Synced/Healthy state | DEPLOY-07 | Requires live ArgoCD cluster | `kubectl get application geo-api-dev -n argocd -o jsonpath='{.status.sync.status}'` → `Synced` |
| SIGTERM graceful shutdown | RESIL-03 | Requires running pod | `kubectl exec -it <pod> -- kill -SIGTERM 1` then check logs for clean shutdown |
| Spell-rebuild init completes | RESIL-04 | Requires live DB with data | Check init container logs: `kubectl logs <pod> -c spell-rebuild` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
