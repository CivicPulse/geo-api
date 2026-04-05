---
phase: 31-osm-stack-civpulse-gis-namespace
plan: 01
subsystem: k8s-gitops
tags: [kustomize, argocd, osm, civpulse-gis, namespace]
requires: []
provides:
  - k8s/osm/base kustomize tree (namespace, sidecars, PVCs)
  - k8s/osm/overlays/prod overlay
  - osm-stack ArgoCD Application manifest
affects:
  - k8s/osm/ (new tree)
tech-stack:
  added: []
  patterns: [kustomize-base-overlay, argocd-application-manifest, commonLabels-part-of]
key-files:
  created:
    - k8s/osm/base/namespace.yaml
    - k8s/osm/base/nominatim.yaml
    - k8s/osm/base/tile-server.yaml
    - k8s/osm/base/valhalla.yaml
    - k8s/osm/base/osm-pvcs.yaml
    - k8s/osm/base/kustomization.yaml
    - k8s/osm/overlays/prod/kustomization.yaml
    - k8s/osm/overlays/prod/argocd-app.yaml
  modified: []
decisions:
  - "D-01 applied: civpulse-gis Namespace committed to git (namespace.yaml)"
  - "D-02 applied: commonLabels app.kubernetes.io/part-of=civpulse-osm on base"
  - "D-03 applied: single prod overlay only (no dev) — civpulse-gis is shared"
  - "D-04 applied: syncOptions CreateNamespace=true + ServerSideApply=true"
metrics:
  duration: "~2 min"
  completed: "2026-04-05"
  tasks: 2
  files: 8
---

# Phase 31 Plan 01: OSM Stack Kustomize Tree Summary

One-liner: Created `k8s/osm/` kustomize tree (base + prod overlay) with civpulse-gis Namespace, three OSM sidecars (nominatim, tile-server, valhalla) copied verbatim from Phase 28, four zfs-local PVCs from Phase 30, and the `osm-stack` ArgoCD Application targeting the civpulse-gis namespace with CreateNamespace=true + ServerSideApply=true.

## What Was Built

**k8s/osm/base/** (6 files):
- `namespace.yaml` — civpulse-gis Namespace
- `nominatim.yaml` — Deployment + Service (verbatim from k8s/base, 4Gi/8Gi mem, 500m/2000m cpu)
- `tile-server.yaml` — Deployment + Service (verbatim, 2Gi/4Gi mem, 500m/1500m cpu)
- `valhalla.yaml` — Deployment + Service (verbatim, 2Gi/4Gi mem, 500m/1500m cpu)
- `osm-pvcs.yaml` — 4 PVCs on zfs-local (nominatim 50Gi, osm-tile 20Gi, valhalla 10Gi, osm-pbf 5Gi)
- `kustomization.yaml` — commonLabels `app.kubernetes.io/part-of: civpulse-osm`

**k8s/osm/overlays/prod/** (2 files):
- `kustomization.yaml` — references `../../base`
- `argocd-app.yaml` — osm-stack Application: path=k8s/osm/overlays/prod, namespace=civpulse-gis, targetRevision=main, automated prune+selfHeal, syncOptions=[CreateNamespace=true, ServerSideApply=true]

## Verification

`kubectl kustomize k8s/osm/overlays/prod/` built cleanly, producing 11 resources:
- 1 Namespace (civpulse-gis)
- 3 Deployments (nominatim, tile-server, valhalla)
- 3 Services (ClusterIP)
- 4 PersistentVolumeClaims
- commonLabel `app.kubernetes.io/part-of: civpulse-osm` applied to 20 occurrences (all resource/selector sites)
- ArgoCD Application NOT included in kustomize build (as designed — applied separately)

## Commits

- `b8e2204` — feat(31-01): create k8s/osm/base with civpulse-gis namespace and OSM sidecars
- `6c5798d` — feat(31-01): add k8s/osm prod overlay and osm-stack ArgoCD Application

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- FOUND: k8s/osm/base/namespace.yaml
- FOUND: k8s/osm/base/nominatim.yaml
- FOUND: k8s/osm/base/tile-server.yaml
- FOUND: k8s/osm/base/valhalla.yaml
- FOUND: k8s/osm/base/osm-pvcs.yaml
- FOUND: k8s/osm/base/kustomization.yaml
- FOUND: k8s/osm/overlays/prod/kustomization.yaml
- FOUND: k8s/osm/overlays/prod/argocd-app.yaml
- FOUND commit: b8e2204
- FOUND commit: 6c5798d
