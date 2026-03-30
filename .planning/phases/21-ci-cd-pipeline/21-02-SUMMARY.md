---
phase: 21-ci-cd-pipeline
plan: "02"
subsystem: infra
tags: [github-actions, docker, ghcr, kustomize, argocd, trivy, sarif, gitops, ci-cd]

# Dependency graph
requires:
  - phase: 20-health-resilience-and-k8s-manifests
    provides: k8s/overlays/dev and prod kustomization.yaml with images stanza for manifest-commit updates
  - phase: 19-dockerfile-and-database-provisioning
    provides: multi-stage Dockerfile with ARG GIT_COMMIT, GHCR repo ghcr.io/civicpulse/geo-api
provides:
  - CD pipeline on merge to main (build → Trivy scan → GHCR push → dev manifest commit)
  - Production promotion via v* tag (prod manifest commit → ArgoCD auto-sync)
  - Loop prevention via paths-ignore + [skip ci] on manifest commits
affects: [22-observability, 23-e2e-validation]

# Tech tracking
tech-stack:
  added:
    - github-actions (cd.yml, promote-prod.yml workflows)
    - docker/metadata-action v6.0.0 (SHA-pinned: 030e881283bb7a6894de51c315a6bfe6a94e05cf)
    - docker/login-action v4.0.0 (SHA-pinned: b45d80f862d83dbcd57f89517bcf500b2ab88fb2)
    - docker/build-push-action v7.0.0 (SHA-pinned: d08e5c354a6adb9ed34480a06d141179aa583294)
    - aquasecurity/trivy-action v0.35.0 (SHA-pinned: 57a97c7e7821a5776cebc9bb87c984fa69cba8f1)
    - github/codeql-action/upload-sarif v3 (SHA-pinned: 5c8a8a642e79153f5d047b10ec1cba1d1cc65699)
    - kustomize v5.8.1 (installed via curl in workflow)
  patterns:
    - "GitOps manifest-commit: kustomize edit set image + git push to update overlay, ArgoCD auto-syncs"
    - "SHA-pinned actions: all uses: lines reference full 40-char commit SHAs (D-09 supply chain security)"
    - "Loop prevention: paths-ignore k8s/overlays/** (primary) + [skip ci] commit message (secondary)"
    - "Concurrency group: cd-deploy with cancel-in-progress: false prevents deploy cancellation"
    - "git tag as approval gate: v* tag is the manual production promotion trigger (D-04)"

key-files:
  created:
    - .github/workflows/cd.yml
    - .github/workflows/promote-prod.yml
  modified: []

key-decisions:
  - "D-01 manifest-commit strategy: kustomize edit set image updates k8s/overlays/dev/kustomization.yaml, ArgoCD automated sync deploys"
  - "D-04 git tag as approval gate: v* tag triggers promote-prod.yml, no GitHub environment protection rules"
  - "D-09 SHA-pinned actions enforced: all 6 actions in cd.yml and 1 in promote-prod.yml use full 40-char SHAs"
  - "D-05 Trivy blocks on HIGH,CRITICAL with exit-code 1; SARIF uploaded with if: always() for Security tab"
  - "Loop prevention belt-and-suspenders: paths-ignore k8s/overlays/** as primary, [skip ci] as secondary"
  - "ref: main in promote-prod.yml checkout prevents detached HEAD on tag trigger (Research Pitfall 2)"

patterns-established:
  - "Pattern: manifest-commit loop prevention — paths-ignore must cover the overlay path in cd.yml trigger"
  - "Pattern: SHA-pinned actions — every uses: line has full 40-char SHA + version comment"
  - "Pattern: concurrency guard — cd-deploy group, cancel-in-progress: false for safe GitOps deploys"

requirements-completed: [DEPLOY-06]

# Metrics
duration: 2min
completed: 2026-03-30
---

# Phase 21 Plan 02: CD and Production Promotion Workflows Summary

**GitHub Actions CD pipeline: build→Trivy scan→GHCR push→dev manifest commit on merge to main, plus v* tag-triggered production promotion via kustomize manifest-commit GitOps pattern**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-30T04:57:03Z
- **Completed:** 2026-03-30T04:58:41Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `.github/workflows/cd.yml` with two-job structure: `build-scan-push` (Docker build + Trivy HIGH/CRITICAL scan + GHCR push with sha- tag) and `update-dev-manifest` (kustomize edit + manifest commit to trigger ArgoCD dev sync)
- Created `.github/workflows/promote-prod.yml` with single-job structure triggered only on v* tags: derives SHA tag from tagged commit, updates prod kustomization, pushes manifest commit to main
- Implemented belt-and-suspenders loop prevention: `paths-ignore: ['k8s/overlays/**']` in cd.yml trigger (primary) and `[skip ci]` in all automated commit messages (secondary)
- All 7 action `uses:` lines across both files pinned to full 40-character commit SHAs per D-09 (Trivy supply chain compromise mitigation)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create CD workflow (.github/workflows/cd.yml)** - `6048fc3` (feat)
2. **Task 2: Create production promotion workflow (.github/workflows/promote-prod.yml)** - `87bf252` (feat)

**Plan metadata:** (docs commit pending)

## Files Created/Modified

- `.github/workflows/cd.yml` - Two-job CD pipeline: build/scan/push image + update dev kustomization manifest
- `.github/workflows/promote-prod.yml` - Production promotion workflow triggered on v* tag push

## Decisions Made

- None at execution time — all decisions were locked in CONTEXT.md (D-01 through D-09). Plan executed exactly per spec with SHA-pinned actions, paths-ignore loop prevention, ref: main detached HEAD fix, and concurrency guard.

## Deviations from Plan

None — plan executed exactly as written. Both workflow files match the exact structure specified in the plan, including all SHA pins, loop prevention mechanisms, permissions blocks, and kustomize patterns.

## Issues Encountered

None. The `.github/` directory did not exist yet (expected per CONTEXT.md: "No `.github/` directory exists yet — all three workflow files are net-new"), created it as part of Task 1.

## Known Stubs

None. Both workflow files are complete and production-ready. The `.trivyignore` file is not yet populated with specific CVE IDs — this is by design per the research (CVE IDs must be discovered by running Trivy against the actual built image). A placeholder `.trivyignore` would not be meaningful without actual CVE scan results.

## User Setup Required

None for workflow file creation. However, to complete DEPLOY-06 end-to-end:
- The first merge to main after these workflows are in place will trigger `cd.yml`
- Any HIGH/CRITICAL CVEs in the built image will block the manifest update until either patched or added to `.trivyignore` with justification comments per D-06
- Production promotion requires creating a `v*` tag (e.g., `git tag v1.3.0 && git push origin v1.3.0`)

## Next Phase Readiness

- Phase 21 Plan 02 complete. Together with Plan 01's `ci.yml`, all three CI/CD workflow files are in place.
- Phase 22 (observability) can proceed — workflows are independent of observability stack.
- Phase 23 (E2E validation) will exercise the full pipeline: PR → CI pass → merge → CD deploys to dev → tag → promote to prod.

---
*Phase: 21-ci-cd-pipeline*
*Completed: 2026-03-30*
