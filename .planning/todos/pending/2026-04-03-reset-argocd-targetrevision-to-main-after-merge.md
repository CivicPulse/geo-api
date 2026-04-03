---
created: 2026-04-03T18:13:59.813Z
title: Reset ArgoCD targetRevision to main after merge
area: planning
files:
  - k8s/overlays/prod/argocd-app.yaml
  - k8s/overlays/dev/argocd-app.yaml
---

## Problem

Phase 23 deployment validation temporarily repointed both ArgoCD Applications to the branch `phase-23-deploy-fix` so Argo could reconcile the overlay paths and deploy the fixed image. That branch target is intentional for validation, but it must not remain as the long-term source of truth after the deployment fixes are merged to `main`.

If the Applications are left targeting the temporary branch, future GitOps syncs will bypass `main`, create drift from the intended release flow, and make later deployments harder to reason about.

## Solution

After the deployment fixes are merged to `main`, update both ArgoCD Application manifests to set `spec.source.targetRevision: main` again in:

- `k8s/overlays/prod/argocd-app.yaml`
- `k8s/overlays/dev/argocd-app.yaml`

Then apply or sync the Applications and verify both ArgoCD apps remain `Synced/Healthy` while pointing at `main`.
