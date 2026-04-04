---
phase: 21
slug: ci-cd-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 0 | DEPLOY-06 | smoke | `uv run ruff check src/` | N/A | ⬜ pending |
| 21-01-02 | 01 | 0 | DEPLOY-06 | smoke | `cat .trivyignore` | N/A | ⬜ pending |
| 21-02-01 | 02 | 1 | DEPLOY-06 | manual-only | N/A — verify in Actions tab after PR | N/A | ⬜ pending |
| 21-03-01 | 03 | 1 | DEPLOY-06 | manual-only | N/A — verify in Actions tab + GHCR + Security tab after merge | N/A | ⬜ pending |
| 21-04-01 | 04 | 2 | DEPLOY-06 | manual-only | N/A — verify in Actions tab after v* tag push | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `[tool.ruff]` section in `pyproject.toml` — needed before `ci.yml` ruff check can pass
- [ ] `.trivyignore` file created — needed before `cd.yml` Trivy scan step (placeholder with format)

*Existing test infrastructure covers all phase requirements. No new test files needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI workflow triggers on PR to main | DEPLOY-06 | GitHub Actions triggers cannot be unit tested | Create a test PR and verify CI workflow runs in Actions tab |
| CD workflow builds, scans, pushes image | DEPLOY-06 | GHCR push and Trivy scan require live infrastructure | Merge a PR and verify in Actions run, GHCR packages, Security tab |
| Dev kustomization updated with SHA tag | DEPLOY-06 | Manifest commit requires live CD workflow | Check `git log k8s/overlays/dev/kustomization.yaml` after merge |
| ArgoCD syncs dev after manifest change | DEPLOY-06 | Requires running ArgoCD cluster | `kubectl get pods -n civpulse-dev` after sync |
| Prod requires v* tag, not triggered by merge | DEPLOY-06 | Requires verifying absence of automated trigger | Merge to main, verify prod overlay unchanged; then push v* tag and verify prod updates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
