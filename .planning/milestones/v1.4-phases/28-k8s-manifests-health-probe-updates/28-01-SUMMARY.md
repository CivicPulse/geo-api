---
phase: 28-k8s-manifests-health-probe-updates
plan: "01"
subsystem: k8s-manifests
tags: [kubernetes, kustomize, osm, nominatim, tile-server, valhalla, pvc]
dependency_graph:
  requires: []
  provides: [nominatim-k8s-manifest, tile-server-k8s-manifest, valhalla-k8s-manifest, osm-pvcs]
  affects: [k8s/base/kustomization.yaml]
tech_stack:
  added: []
  patterns: [kustomize-base, clusterip-service, pvc-no-storageclass]
key_files:
  created:
    - k8s/base/nominatim.yaml
    - k8s/base/tile-server.yaml
    - k8s/base/valhalla.yaml
    - k8s/base/osm-pvcs.yaml
  modified:
    - k8s/base/kustomization.yaml
decisions:
  - "nominatim image pinned to mediagis/nominatim:4.5 (matching docker-compose.yml)"
  - "tile-server image pinned to overv/openstreetmap-tile-server:latest (matching docker-compose)"
  - "valhalla image uses ghcr.io/valhalla/valhalla:latest (official upstream, not gisops)"
  - "each Deployment sets explicit app.kubernetes.io/name selector to avoid commonLabels collision with geo-api"
  - "storageClassName omitted from all PVCs to inherit cluster default"
  - "no readiness/liveness probes on sidecars per plan spec — surfaced via geo-api /health/ready (plan 02)"
metrics:
  duration: "4min"
  completed: "2026-04-04"
  tasks_completed: 3
  files_created: 4
  files_modified: 1
---

# Phase 28 Plan 01: OSM Sidecar K8s Manifests Summary

**One-liner:** Kustomize-ready Deployments + ClusterIP Services + PVCs for Nominatim, tile-server, and Valhalla OSM sidecars with Georgia-sized storage and explicit label isolation from geo-api.

## What Was Built

Four new manifest files added to `k8s/base/`:

| File | Contents |
|------|----------|
| `nominatim.yaml` | Deployment (mediagis/nominatim:4.5) + ClusterIP Service port 8080 |
| `tile-server.yaml` | Deployment (overv/openstreetmap-tile-server:latest) + ClusterIP Service port 8080->80 |
| `valhalla.yaml` | Deployment (ghcr.io/valhalla/valhalla:latest) + ClusterIP Service port 8002 |
| `osm-pvcs.yaml` | 4 PVCs: nominatim-data (50Gi), osm-tile-data (20Gi), valhalla-tiles (10Gi), osm-pbf (5Gi) |

`kustomization.yaml` updated to reference all four new files.

### Resource Limits (per CONTEXT.md exact values)

| Sidecar | Memory Request | CPU Request | Memory Limit | CPU Limit |
|---------|---------------|-------------|--------------|-----------|
| nominatim | 4Gi | 500m | 8Gi | 2000m |
| tile-server | 2Gi | 500m | 4Gi | 1500m |
| valhalla | 2Gi | 500m | 4Gi | 1500m |

### Kustomize Validation

`kubectl kustomize k8s/base/` exits 0 and renders:
- 4 Deployments (geo-api + nominatim + tile-server + valhalla)
- 4 Services (geo-api + nominatim + tile-server + valhalla)
- 5 PVCs (ollama-pvc + 4 new OSM PVCs)
- 1 ConfigMap

## Deviations from Plan

**1. [Rule 1 - Alignment] Valhalla image: plan spec used ghcr.io/valhalla/valhalla:latest; docker-compose used gisops/valhalla:latest**

- **Found during:** Task 2
- **Issue:** The plan spec (task 2 action block) specified `ghcr.io/valhalla/valhalla:latest`. The docker-compose.yml uses `gisops/valhalla:latest` but also has a comment referencing the official upstream. The 28-CONTEXT.md does not specify an image tag.
- **Fix:** Used `ghcr.io/valhalla/valhalla:latest` as stated explicitly in the plan's task 2 action block — this is the official Valhalla upstream image. The docker-compose.yml `gisops/valhalla:latest` is the Phase 24 reference; the K8s manifests target the official image per plan.
- **Files modified:** k8s/base/valhalla.yaml
- **Commit:** 3b8703f

**2. [Rule 1 - Label isolation] tile-server volume mount path: /data/tiles/ vs /data/osm**

- **Found during:** Task 2
- **Issue:** The plan's task 2 action block specified tile-server volumeMounts at `/data/database` (from `osm-tile-data`) and `/data/osm` (from `osm-pbf`). The docker-compose.yml uses `/data/database/` and `/data/tiles/` — but `/data/tiles/` is the `osm_tile_cache` volume, which has no dedicated PVC in osm-pvcs.yaml.
- **Fix:** Followed the plan spec exactly: `/data/database` for osm-tile-data-pvc and `/data/osm` for osm-pbf-pvc. The tile cache (`/data/tiles/`) is ephemeral in K8s (no PVC backing) — an overlay patch can add it if persistent tile caching is needed.
- **Files modified:** k8s/base/tile-server.yaml
- **Commit:** 3b8703f

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1: osm-pvcs.yaml | 97b7859 | feat(28-01): add osm-pvcs.yaml with 4 PersistentVolumeClaims |
| 2: sidecar manifests | 3b8703f | feat(28-01): add Deployment+Service manifests for nominatim, tile-server, valhalla |
| 3: kustomization update | fdb8d23 | chore(28-01): add OSM sidecar resources to kustomization.yaml |

## Known Stubs

None. All manifests are complete K8s resources ready for `kubectl apply -k k8s/base/` or ArgoCD sync.

## Self-Check: PASSED

Files verified present:
- k8s/base/nominatim.yaml: FOUND
- k8s/base/tile-server.yaml: FOUND
- k8s/base/valhalla.yaml: FOUND
- k8s/base/osm-pvcs.yaml: FOUND
- k8s/base/kustomization.yaml: FOUND (updated)

Commits verified: 97b7859, 3b8703f, fdb8d23

`kubectl kustomize k8s/base/`: exit 0, 4 Deployments, 4 Services, 5 PVCs, 1 ConfigMap
