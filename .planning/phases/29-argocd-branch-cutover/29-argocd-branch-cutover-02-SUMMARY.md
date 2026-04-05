---
phase: 29-argocd-branch-cutover
plan: 02
status: complete
completed: 2026-04-05
requirements:
  - GIT-01
  - GIT-02
mutation: true
---

# Plan 29-02 Summary: Live Cluster Cutover to main

## Pre-cutover baseline

```
kubectl get application geo-api-dev  -n argocd ...targetRevision → phase-23-deploy-fix
kubectl get application geo-api-prod -n argocd ...targetRevision → phase-23-deploy-fix
kubectl get application geo-api-dev  -n argocd ...sync/health    → Synced/Healthy
kubectl get application geo-api-prod -n argocd ...sync/health    → Synced/Healthy
```

## Cutover result

```
kubectl apply -f k8s/overlays/dev/argocd-app.yaml    → configured
kubectl apply -f k8s/overlays/prod/argocd-app.yaml   → configured
git push origin --delete phase-23-deploy-fix         → [deleted]

Post-apply, both Applications:
  targetRevision: main
  status.sync.status: Synced
  status.health.status: Healthy
  (first poll after hard refresh)
```

## Why the clean reconcile on second attempt

- Phase 31 removed nominatim, tile-server, valhalla, osm-pvcs from `k8s/base/`
- `kubectl kustomize k8s/overlays/dev/` and `.../prod/` now emit only geo-api resources (Deployment, Service, ConfigMap, ollama-pvc)
- ArgoCD's `prune: true` kept orphaned sidecars out after reconcile
- The `geo-api` pod (29h old in dev, older in prod) was undisturbed throughout

## Requirements satisfied

- GIT-01 ✅ geo-api-dev targetRevision=main, Synced+Healthy
- GIT-02 ✅ phase-23-deploy-fix branch removed from origin
