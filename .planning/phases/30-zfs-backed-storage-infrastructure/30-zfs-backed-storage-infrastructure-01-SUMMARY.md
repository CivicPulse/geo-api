---
phase: 30-zfs-backed-storage-infrastructure
plan: 01
subsystem: storage
tags: [k8s, storage, zfs, persistent-volumes, kustomize]
requires: []
provides:
  - zfs-local StorageClass
  - osm-pbf-pv (5Gi)
  - nominatim-data-pv (50Gi)
  - osm-tile-data-pv (20Gi)
  - valhalla-tiles-pv (10Gi)
affects:
  - Phase 31 OSM stack PVCs (will bind via WaitForFirstConsumer)
tech-stack:
  added: []
  patterns:
    - Static Local PVs with nodeAffinity
    - WaitForFirstConsumer binding for cross-namespace PVC claims
key-files:
  created:
    - k8s/cluster/storage/storageclass-zfs-local.yaml
    - k8s/cluster/storage/pv-osm-pbf.yaml
    - k8s/cluster/storage/pv-nominatim-data.yaml
    - k8s/cluster/storage/pv-osm-tile-data.yaml
    - k8s/cluster/storage/pv-valhalla-tiles.yaml
    - k8s/cluster/storage/kustomization.yaml
  modified: []
decisions:
  - Used spec.local (not hostPath) - standard K8s type for node-pinned static volumes
  - No claimRef - binding controlled by WaitForFirstConsumer + storageClassName + capacity
metrics:
  duration: ~2m
  completed: 2026-04-04
---

# Phase 30 Plan 01: ZFS-Backed Storage Manifests Summary

Created 6 cluster-scoped storage YAMLs: a `zfs-local` StorageClass (no-provisioner, WaitForFirstConsumer) and 4 static Local PersistentVolumes pinned to node `thor` via `kubernetes.io/hostname` nodeAffinity, wired through a kustomization.yaml entrypoint.

## Files Created

All under `k8s/cluster/storage/`:

| File | Kind | Key Spec |
|------|------|----------|
| storageclass-zfs-local.yaml | StorageClass | provisioner: no-provisioner, volumeBindingMode: WaitForFirstConsumer, reclaimPolicy: Retain |
| pv-osm-pbf.yaml | PersistentVolume | osm-pbf-pv, 5Gi, /hatch1/data/geo/pbf |
| pv-nominatim-data.yaml | PersistentVolume | nominatim-data-pv, 50Gi, /hatch1/data/geo/nominatim |
| pv-osm-tile-data.yaml | PersistentVolume | osm-tile-data-pv, 20Gi, /hatch1/data/geo/tile-server |
| pv-valhalla-tiles.yaml | PersistentVolume | valhalla-tiles-pv, 10Gi, /hatch1/data/geo/valhalla |
| kustomization.yaml | Kustomization | lists all 5 resources above |

## PV Mapping

| PV Name | Size | Host Path (ZFS) | Dataset Label |
|---------|------|-----------------|---------------|
| osm-pbf-pv | 5Gi | /hatch1/data/geo/pbf | osm-pbf |
| nominatim-data-pv | 50Gi | /hatch1/data/geo/nominatim | nominatim |
| osm-tile-data-pv | 20Gi | /hatch1/data/geo/tile-server | osm-tile-data |
| valhalla-tiles-pv | 10Gi | /hatch1/data/geo/valhalla | valhalla-tiles |

All PVs: `accessModes: [ReadWriteOnce]`, `persistentVolumeReclaimPolicy: Retain`, `storageClassName: zfs-local`, `nodeAffinity` to `thor`.

## Verification Results

- `kubectl kustomize k8s/cluster/storage/` succeeded: emitted 5 documents (1 StorageClass + 4 PersistentVolume).
- Grep confirms: 4x `reclaimPolicy: Retain`, 4x `kubernetes.io/hostname`, 4x `storageClassName: zfs-local`, 1x `WaitForFirstConsumer`, 1x `no-provisioner`.

## Deviations from Plan

None - plan executed exactly as written.

## Notes

- **Disk-only deliverable.** Manifests were NOT applied to any cluster during this plan. Applying via `kubectl apply -k k8s/cluster/storage/` is deferred to a future App-of-Apps integration.
- Local PVs will fail loudly at pod mount time if `/hatch1/data/geo/<subpath>` directories are missing on node thor - maintaining the fail-loud semantics from CONTEXT.

## Requirements Completed

- STORE-01: zfs-local StorageClass defined
- STORE-02: All 4 PVs use reclaimPolicy: Retain
- STORE-03: All 4 PVs pin to node thor via nodeAffinity

## Self-Check: PASSED

- FOUND: k8s/cluster/storage/storageclass-zfs-local.yaml
- FOUND: k8s/cluster/storage/kustomization.yaml
- FOUND: k8s/cluster/storage/pv-osm-pbf.yaml
- FOUND: k8s/cluster/storage/pv-nominatim-data.yaml
- FOUND: k8s/cluster/storage/pv-osm-tile-data.yaml
- FOUND: k8s/cluster/storage/pv-valhalla-tiles.yaml
- FOUND commits: f38e4a3, 9ea290b
