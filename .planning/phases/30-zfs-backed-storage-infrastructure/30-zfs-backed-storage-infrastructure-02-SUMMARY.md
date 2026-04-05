---
phase: 30-zfs-backed-storage-infrastructure
plan: 02
subsystem: k8s-storage
tags: [k8s, pvc, storage, zfs]
requires: [STORE-01]
provides: [STORE-04]
affects: [osm-pbf-pvc, nominatim-data-pvc, osm-tile-data-pvc, valhalla-tiles-pvc]
tech_stack:
  added: []
  patterns: [static-pv-binding, storageClassName-wiring]
key_files:
  created: []
  modified:
    - k8s/base/osm-pvcs.yaml
decisions:
  - "PVCs reference storageClassName: zfs-local to bind to static Local PVs from Plan 01"
metrics:
  duration_seconds: 27
  completed_date: 2026-04-05
  tasks_completed: 2
  files_modified: 1
---

# Phase 30 Plan 02: Wire OSM PVCs to zfs-local StorageClass Summary

Added `storageClassName: zfs-local` to all 4 OSM PVCs so they bind to the static Local PVs created in Plan 01 (STORE-04).

## Tasks Completed

| Task | Name                                     | Commit  | Files                    |
| ---- | ---------------------------------------- | ------- | ------------------------ |
| 1    | Add storageClassName to all 4 PVCs       | bbe0edc | k8s/base/osm-pvcs.yaml   |
| 2    | Confirm sizes and PVC identity preserved | (val)   | (validation only)        |

## Changes

**File:** `k8s/base/osm-pvcs.yaml` — 4 lines added (one `storageClassName: zfs-local` per PVC, placed between `accessModes` and `resources`).

**PVCs wired:**
- `nominatim-data-pvc` (50Gi)
- `osm-tile-data-pvc` (20Gi)
- `valhalla-tiles-pvc` (10Gi)
- `osm-pbf-pvc` (5Gi)

**Preserved unchanged:** PVC names, sizes, `accessModes: [ReadWriteOnce]`, and document separators. `k8s/base/pvc.yaml` (ollama-pvc) was not touched.

## Verification

- `grep -c "storageClassName: zfs-local"` → 4
- YAML parses as exactly 4 PVC documents
- All 4 expected PVC names present with original sizes (50Gi/20Gi/10Gi/5Gi)
- All accessModes remain `[ReadWriteOnce]`

## Binding Notes

These PVCs will remain `Pending` until BOTH conditions are met:
1. Plan 01's static Local PVs are applied to the cluster
2. A consuming pod is scheduled (per `volumeBindingMode: WaitForFirstConsumer` on the `zfs-local` StorageClass)

Phase 31's relocation of these PVCs to `k8s/osm/base/` will be a pure file-move — the wiring travels with the PVC manifest.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- FOUND: k8s/base/osm-pvcs.yaml
- FOUND: commit bbe0edc
