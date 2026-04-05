---
status: passed
phase: 29-argocd-branch-cutover
verified: 2026-04-05
must_haves_verified: 4/4
notes: resumed after Phase 31 removed blocking sidecars from k8s/base/
---

# Phase 29 Verification — PASSED (resumed)

## Timeline

1. **First attempt (2026-04-05 early):** Dev cutover applied, revealed that `main`'s `k8s/base/` contained un-bootstrappable OSM sidecars from Phase 28. Reverted dev to `phase-23-deploy-fix`. Recommended execution reorder (30 → 31 → 29). See git history.
2. **Resume (after Phase 31):** Phase 31 moved sidecars out of `k8s/base/` into `k8s/osm/base/` + `civpulse-gis` namespace via new osm-stack ArgoCD Application. Re-applied cutover.

## Success criteria — all 4 met

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | `kubectl get application geo-api-dev ...targetRevision` returns `main` | Verified live |
| 2 | `kubectl get application geo-api-prod ...targetRevision` returns `main` | Verified live |
| 3 | Both apps Synced AND Healthy after cutover | Both `Synced/Healthy` on first poll post-apply |
| 4 | Branching strategy documented | `docs/BRANCHING.md` (54 lines) |

## Actions taken in resume

```bash
# Dev cutover
kubectl apply -f k8s/overlays/dev/argocd-app.yaml       # configured
kubectl patch application geo-api-dev ... refresh=hard  # force reconcile
# → targetRevision=main, Synced/Healthy (1 poll)

# Prod cutover
kubectl apply -f k8s/overlays/prod/argocd-app.yaml      # configured
kubectl patch application geo-api-prod ... refresh=hard # force reconcile
# → targetRevision=main, Synced/Healthy (1 poll)

# Branch cleanup
git push origin --delete phase-23-deploy-fix            # deleted
git ls-remote --heads origin phase-23-deploy-fix        # empty (confirmed)
```

## Side-effect cluster state

- `civpulse-dev` / `civpulse-prod`: `geo-api` Deployment running normally; OSM sidecars no longer present in these namespaces (pruned by ArgoCD because `k8s/base/` no longer declares them)
- `civpulse-gis`: osm-stack Application synced; nominatim/tile-server/valhalla Deployments present but pods crash-looping (expected until Phase 30 PVs apply + Phase 32 bootstrap Jobs run)

## Requirements satisfied

- GIT-01 ✅ (geo-api-dev on main, Synced/Healthy)
- GIT-02 ✅ (phase-23-deploy-fix deleted from origin)
- GIT-03 ✅ (docs/BRANCHING.md committed)

## Related todo

`.planning/todos/done/2026-04-03-reset-argocd-targetrevision-to-main-after-merge.md` — this todo was the original tracking item for Phase 29; previously moved to done/.
