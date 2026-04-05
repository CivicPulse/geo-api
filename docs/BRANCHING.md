# Branching Strategy

CivPulse Geo API uses a **trunk-based development** model. This document codifies the branching workflow and the `targetRevision` pinning policy that governs our ArgoCD Applications.

## Trunk-Based Development

- `main` is the single long-lived branch and the **deployment source of truth**.
- There are no long-lived `develop`, `release`, or environment-specific branches.
- All work happens on short-lived branches that merge back to `main` via pull request.
- Every commit on `main` is a candidate for deployment — keep it green.

## Phase Branch Convention

Work tracked by the GSD workflow uses phase branches named:

```
phase-{NN}-{slug}
```

Examples: `phase-29-argocd-branch-cutover`, `phase-30-zfs-backed-storage`.

- One active phase branch at a time per contributor.
- Phase branches are **deleted from the remote after merge to `main`**.
- Before opening planning for a new phase, the previous phase branch must already be merged to `main`. This guarantees the phase's artifacts (code, ArgoCD state, STATE.md, ROADMAP.md) are reconcilable from `main` alone.

## ArgoCD `targetRevision` Policy

All committed ArgoCD Application manifests under `k8s/overlays/{env}/argocd-app.yaml` **MUST** pin:

```yaml
spec:
  source:
    targetRevision: main
```

### Temporary phase-branch pinning

Pinning a live Application to a phase branch is permitted **only** as an in-cluster live edit during active deploy debugging (for example, when iterating on a deployment fix that can't be safely tested from `main`). When doing so:

1. Do the live edit via `kubectl edit` or `argocd app set` — **never** commit a non-`main` `targetRevision` to git.
2. Revert the live Application to `main` before the phase branch is merged and deleted.
3. If the live edit outlives a single session, track it as a pending todo so it isn't forgotten.

### Rationale

The two geo-api Applications (`geo-api-dev`, `geo-api-prod`) are installed directly into the `argocd` namespace and are **not** managed by a parent App-of-Apps. As a result, manual live edits to their `targetRevision` do not self-heal from git — drift between live state and committed state is only resolved by an explicit `kubectl apply` or `argocd app set`. Phase 29 of milestone v1.5 was created specifically to reconcile this kind of drift after v1.3's deploy-fix work. Keep committed manifests honest and phase-branch pinning strictly temporary.

## PR Workflow

1. Open a PR from the phase/feature branch to `main`.
2. PR title and commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
3. CI must be green before merge.
4. Squash-or-merge at maintainer discretion; delete the remote branch after merge.
5. After merge, pull `main` locally and delete the local branch.
