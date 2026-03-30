# Phase 21: CI/CD Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 21-ci-cd-pipeline
**Areas discussed:** ArgoCD sync strategy, Production promotion, Trivy scan policy, Workflow structure

---

## ArgoCD Sync Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Manifest-commit | CD workflow updates kustomization.yaml with new SHA tag and commits. ArgoCD syncs from Git. Full audit trail. | ✓ |
| ArgoCD Image Updater | In-cluster controller watches GHCR for new tags. No Git commits for deploys. Requires extra controller + RBAC. | |
| ArgoCD CLI sync | CD workflow calls `argocd app set` + `argocd app sync` directly. Fast but breaks GitOps audit trail. | |

**User's choice:** Manifest-commit
**Notes:** Aligns with GitOps — every deployment traceable to a Git commit. No additional infrastructure needed.

---

## Production Promotion

| Option | Description | Selected |
|--------|-------------|----------|
| Manual workflow dispatch | Separate workflow triggered via workflow_dispatch. Operator inputs SHA tag. | |
| Git tag release | Creating a `v*` tag triggers prod promotion workflow. Tag acts as approval gate. | ✓ |
| Environment protection rules | Same CD workflow deploys to both, prod job requires GitHub environment approval. | |

**User's choice:** Git tag release
**Notes:** Ties production deployments to versioned releases. Only maintainers with push access can create tags.

---

## Trivy Scan Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Block CRITICAL only | Fail on CRITICAL severity. HIGH and below reported only. | |
| Block HIGH + CRITICAL | Fail on HIGH and CRITICAL. May need .trivyignore for known base image issues. | ✓ |
| Report only, no block | Scan runs and uploads artifacts but never fails pipeline. | |

**User's choice:** Block HIGH + CRITICAL
**Notes:** Stricter security posture. `.trivyignore` file for known unfixable base image vulnerabilities with mandatory comments.

---

## Workflow Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Separate files | ci.yml (PR), cd.yml (merge to main), promote-prod.yml (tag). Single responsibility per file. | ✓ |
| Single file, conditional jobs | One pipeline.yml with conditional jobs based on event type. Less files but shared permissions. | |

**User's choice:** Separate files
**Notes:** Enables least-privilege permissions per workflow. Only cd.yml needs write access to GHCR and repo.

---

## Cross-Cutting: Supply Chain Security

User raised the Trivy supply chain compromise (March 2026) as a hard requirement. All GitHub Actions must be pinned to full commit SHAs, not mutable tags. Reference: https://www.microsoft.com/en-us/security/blog/2026/03/24/detecting-investigating-defending-against-trivy-supply-chain-compromise/

## Claude's Discretion

- Exact commit SHAs for each pinned action
- `uv` caching strategy in CI
- Concurrency guards for deploy commits
- Git bot identity for automated commits
- SARIF upload for Trivy results
- Branch protection rule configuration

## Deferred Ideas

None — discussion stayed within phase scope
