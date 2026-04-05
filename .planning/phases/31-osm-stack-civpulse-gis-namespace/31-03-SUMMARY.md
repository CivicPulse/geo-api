---
phase: 31-osm-stack-civpulse-gis-namespace
plan: 03
status: complete
completed: 2026-04-05
requirements:
  - OSM-02
  - OSM-03
mutation: true
---

# Plan 31-03 Summary: Apply osm-stack to Live Cluster

## What was applied

```bash
git push origin main  # 15 commits — user-approved
kubectl apply -f k8s/osm/overlays/prod/argocd-app.yaml
kubectl patch application osm-stack -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

## Verification output

```
# osm-stack Application
kubectl get application osm-stack -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}'
→ Synced/Progressing

# Namespace (pre-existing, ArgoCD CreateNamespace=true was idempotent)
kubectl get ns civpulse-gis
→ Active (34d)

# Deployments
kubectl get deploy -n civpulse-gis
NAME          READY   UP-TO-DATE   AVAILABLE   AGE
nominatim     0/1     1            0           76s
tile-server   0/1     1            0           76s
valhalla      0/1     1            0           76s

# PVCs
kubectl get pvc -n civpulse-gis
NAME                 STATUS    STORAGECLASS
nominatim-data-pvc   Pending   zfs-local
osm-pbf-pvc          Pending   zfs-local
osm-tile-data-pvc    Pending   zfs-local
valhalla-tiles-pvc   Pending   zfs-local
```

## Expected-incomplete state

- **PVCs Pending** — Phase 30's Local PVs were written to git but not applied to the cluster; ZFS datasets on `thor` also need `zfs create`. These are operator-runbook steps deferred to Phase 34.
- **Deployments 0/1 ready** — pods stuck on PVC binding. Once Phase 30 PVs are applied AND Phase 32's bootstrap Jobs populate data, the Deployments will become Ready.
- **Health=Progressing** — not a failure. The Sync=Synced result is the criterion that matters for Phase 31 (OSM-03).

## Success criteria verified

| # | Criterion | Status |
|---|-----------|--------|
| 1 | k8s/osm/base/ directory with sidecar manifests | ✅ (from Plan 01) |
| 2 | k8s/osm/overlays/ structure mirrors convention | ✅ (from Plan 01) |
| 3 | osm-stack ArgoCD Application in argocd ns, destination=civpulse-gis, auto+prune+selfHeal | ✅ Live |
| 4 | `kubectl get deploy -n civpulse-gis` shows nominatim + tile-server + valhalla | ✅ Live |
| 5 | Resource limits match Phase 28 (4Gi/8Gi, 2Gi/4Gi, 2Gi/4Gi) | ✅ (from Plan 01) |

## Requirements satisfied

- OSM-02 ✅ (osm-stack ArgoCD Application live + syncing)
- OSM-03 ✅ (k8s/osm/base/ + overlays structure honored)
- OSM-01 and OSM-04 verified by Plans 01 + 02
