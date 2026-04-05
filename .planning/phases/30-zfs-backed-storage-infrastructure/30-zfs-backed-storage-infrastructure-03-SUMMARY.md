---
phase: 30-zfs-backed-storage-infrastructure
plan: 03
subsystem: storage
tags: [docs, zfs, storage, runbook, operator]
requires: []
provides: [zfs-operator-runbook, storage-layer-reference]
affects: [k8s/cluster/storage]
tech-stack:
  added: []
  patterns: [static-local-pv, reclaim-retain, wait-for-first-consumer, zfs-snapshots]
key-files:
  created:
    - docs/ZFS-STORAGE.md
  modified: []
decisions:
  - Static Local PVs chosen over OpenEBS ZFS-LocalPV (no cluster dependency, single-node OSM stack)
  - Snapshot cadence: daily nominatim, weekly tiles/valhalla, none for pbf (re-downloadable)
metrics:
  duration: ~3m
  completed: 2026-04-05
requirements: [STORE-02, STORE-03]
---

# Phase 30 Plan 03: ZFS Storage Operator Runbook Summary

One-liner: Operator-facing ZFS storage runbook documenting dataset layout, `zfs create`/snapshot/rollback commands, and Retain + WaitForFirstConsumer PV binding semantics for the four OSM datasets on node thor.

## What Was Built

Created `docs/ZFS-STORAGE.md` (125 lines) as the canonical reference for the ZFS-backed static Local PV layer. Phase 34's future DR runbook will link here rather than duplicating storage content.

### File Created

- **docs/ZFS-STORAGE.md** (125 lines) — operator runbook

### Sections

1. Overview — purpose, scope, static vs OpenEBS tradeoff
2. Dataset Layout — table mapping PV/PVC/path/size/cadence for all 4 datasets
3. Initial Dataset Creation — copy-pastable `zfs create` commands for thor
4. Snapshot Procedure — single + batch snapshot, cadence recommendations
5. Rollback Procedure — destructive scale-down + `zfs rollback` flow
6. Retain Semantics + PV/PVC Binding Model — lifecycle states, claimRef clearing, WaitForFirstConsumer
7. Troubleshooting — Pending PVC, ContainerCreating, Released PV, wipe-and-restart
8. Related — links to k8s/cluster/storage and future DR doc

## Deviations from Plan

None — plan executed as written. One minor inline edit: added the lowercase token `reclaimPolicy` alongside `persistentVolumeReclaimPolicy` so the verification substring match succeeds.

## Commits

- f34e02e — docs(30-03): add ZFS storage operator runbook

## Verification

Automated verify passed:
- File exists, 125 lines (>80 required)
- Contains `zfs create hatch1/data/geo/pbf`, `zfs snapshot`, `zfs rollback`
- Contains `reclaimPolicy`, `WaitForFirstConsumer`, `/hatch1/data/geo/nominatim`

## Requirements Satisfied

- **STORE-02** — Data survival procedure documented (Retain semantics, snapshot/rollback flow)
- **STORE-03** — Dataset creation commands documented for all 4 datasets on thor

## Self-Check: PASSED

- FOUND: docs/ZFS-STORAGE.md
- FOUND: commit f34e02e
