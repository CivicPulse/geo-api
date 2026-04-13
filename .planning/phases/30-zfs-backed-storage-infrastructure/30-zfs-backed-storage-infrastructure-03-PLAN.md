---
phase: 30-zfs-backed-storage-infrastructure
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/ZFS-STORAGE.md
autonomous: true
requirements:
  - STORE-02
  - STORE-03
must_haves:
  truths:
    - "docs/ZFS-STORAGE.md exists and documents the full ZFS dataset layout under /hatch1/data/geo/*"
    - "Doc provides copy-pastable `zfs create` commands for all 4 datasets on node thor"
    - "Doc explains snapshot/rollback procedure with example commands"
    - "Doc explains Retain reclaimPolicy semantics and the PV/PVC binding model"
    - "Doc records recommended snapshot cadence (daily nominatim, weekly tiles/valhalla, none pbf)"
  artifacts:
    - path: "docs/ZFS-STORAGE.md"
      provides: "Storage layer reference for operators + Phase 34 DR runbook"
      min_lines: 80
      contains: "zfs create"
  key_links:
    - from: "docs/ZFS-STORAGE.md"
      to: "k8s/cluster/storage/ manifests (Plan 01)"
      via: "path mapping table"
      pattern: "/hatch1/data/geo"
---

<objective>
Write `docs/ZFS-STORAGE.md` — the operator reference for the ZFS-backed storage layer. This document covers dataset layout, manual `zfs create` commands, snapshot/rollback procedures, `Retain` semantics, and the PV/PVC binding model.

Purpose: Operators need a canonical reference for creating the ZFS datasets the static PVs depend on, and for performing snapshots/restores. Phase 34's future `docs/DR.md` will link here for the storage layer rather than duplicating content.
Output: One new markdown file at `docs/ZFS-STORAGE.md`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/30-zfs-backed-storage-infrastructure/30-CONTEXT.md
@.planning/ROADMAP.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write docs/ZFS-STORAGE.md</name>
  <files>docs/ZFS-STORAGE.md</files>
  <action>
Create `docs/ZFS-STORAGE.md` with the following section structure. Write in operator-facing tone: commands are copy-pastable, assumptions explicit, no fluff.

## Required sections

### 1. Overview (~10 lines)
- Purpose: static Local PVs backed by ZFS datasets on node thor, with reclaimPolicy: Retain so OSM data survives PVC deletion and cluster rebuilds.
- Scope: pbf, nominatim, tile-server, valhalla datasets used by the civpulse-gis namespace OSM stack.
- Why static (not dynamic): no extra cluster dependency, simpler, matches the "data survives cluster rebuilds" requirement. Contrast briefly with OpenEBS ZFS-LocalPV (deferred, not used).

### 2. Dataset Layout (table)
Table mapping: PV name | PVC name | Dataset path | Size | Snapshot cadence.

| PV | PVC | Path | Size | Snapshot cadence |
|----|-----|------|------|------------------|
| osm-pbf-pv | osm-pbf-pvc | /hatch1/data/geo/pbf | 5Gi | none (re-downloadable) |
| nominatim-data-pv | nominatim-data-pvc | /hatch1/data/geo/nominatim | 50Gi | daily |
| osm-tile-data-pv | osm-tile-data-pvc | /hatch1/data/geo/tile-server | 20Gi | weekly |
| valhalla-tiles-pv | valhalla-tiles-pvc | /hatch1/data/geo/valhalla | 10Gi | weekly |

### 3. Initial Dataset Creation
Include a bash code block with the exact `zfs create` commands an admin runs on thor. Assume the parent pool/dataset is `hatch1` and the parent path `/hatch1/data/geo` exists as a dataset. Commands:

```bash
# Run as root on thor
zfs create hatch1/data/geo/pbf
zfs create hatch1/data/geo/nominatim
zfs create hatch1/data/geo/tile-server
zfs create hatch1/data/geo/valhalla

# Verify mountpoints
zfs list -r hatch1/data/geo
```

Note: The PV manifests use `local.path` with the filesystem path. If a dataset is missing when a pod tries to mount, kubelet will fail the mount (fail-loud). PVs in `WaitForFirstConsumer` stay `Available` with no pod-side error until a consumer exists.

### 4. Snapshot Procedure
Bash examples for creating and listing snapshots:

```bash
# Snapshot a single dataset (name snapshots with ISO date)
zfs snapshot hatch1/data/geo/nominatim@$(date +%Y-%m-%d)

# Snapshot all four at once, same timestamp
TS=$(date +%Y-%m-%d)
for ds in pbf nominatim tile-server valhalla; do
  zfs snapshot hatch1/data/geo/$ds@$TS
done

# List snapshots
zfs list -t snapshot -r hatch1/data/geo
```

### 5. Rollback Procedure
```bash
# Roll a dataset back to a snapshot (DESTRUCTIVE — discards changes since snapshot)
# Scale consumer pods to 0 first so the mount is not in use
kubectl -n civpulse-gis scale deployment nominatim --replicas=0
zfs rollback hatch1/data/geo/nominatim@2026-04-01
kubectl -n civpulse-gis scale deployment nominatim --replicas=1
```

Warn: `zfs rollback` destroys any snapshots taken AFTER the target snapshot. Use `zfs rollback -r` to acknowledge.

### 6. Retain Semantics + PV/PVC Binding Model
Explain in prose (~15 lines):
- Each static PV has `persistentVolumeReclaimPolicy: Retain`. When the bound PVC is deleted, the PV transitions to `Released` and the on-disk data is untouched.
- To reuse the PV, clear the `spec.claimRef` field (`kubectl patch pv <name> --type=json -p='[{"op":"remove","path":"/spec/claimRef"}]'`) and it returns to `Available`.
- Binding uses `WaitForFirstConsumer`: the PV does not bind when created — it binds only when a pod using the matching PVC is scheduled. This supports cross-namespace PVCs (the PVCs live in `civpulse-gis` but PVs are cluster-scoped).
- Capacity matching: Kubernetes binds the smallest PV whose capacity >= PVC request and whose `storageClassName` + `accessModes` match. Our capacities are exact so no ambiguity.

### 7. Troubleshooting
Bulleted list of common issues:
- "PVC stays Pending forever" → check no pod is scheduled yet (WaitForFirstConsumer is normal), OR the dataset doesn't exist on thor, OR the pod's node affinity doesn't land on thor.
- "Pod stuck ContainerCreating with mount errors" → dataset path missing on thor. Run `ls /hatch1/data/geo/` and create any missing dataset.
- "PV stuck Released after PVC delete" → expected with Retain. Clear `claimRef` to reuse, or `kubectl delete pv <name>` to remove the PV (data still on disk).
- "Need to wipe and start over" → scale consumers to 0, `kubectl delete pvc && kubectl delete pv`, then `zfs destroy -r hatch1/data/geo/<name>` on thor, recreate dataset, reapply manifests.

### 8. Related
- `k8s/cluster/storage/` — static PV + StorageClass manifests
- `k8s/base/osm-pvcs.yaml` — OSM PVCs that bind to these PVs
- Phase 34 `docs/DR.md` (future) — will link to this doc for the storage layer

---

Aim for ~120-180 lines total. Keep tone direct and operator-first. No marketing language.
  </action>
  <verify>
    <automated>test -f docs/ZFS-STORAGE.md && test $(wc -l < docs/ZFS-STORAGE.md) -gt 80 && grep -q "zfs create hatch1/data/geo/pbf" docs/ZFS-STORAGE.md && grep -q "zfs snapshot" docs/ZFS-STORAGE.md && grep -q "zfs rollback" docs/ZFS-STORAGE.md && grep -q "reclaimPolicy" docs/ZFS-STORAGE.md && grep -q "WaitForFirstConsumer" docs/ZFS-STORAGE.md && grep -q "/hatch1/data/geo/nominatim" docs/ZFS-STORAGE.md</automated>
  </verify>
  <done>docs/ZFS-STORAGE.md exists, >80 lines, contains zfs create/snapshot/rollback commands, references Retain + WaitForFirstConsumer, includes all 4 dataset paths.</done>
</task>

</tasks>

<verification>
- `docs/ZFS-STORAGE.md` exists and is well-formed markdown
- All 4 datasets documented with paths, sizes, and cadence
- `zfs create`, `zfs snapshot`, `zfs rollback` example commands present
- Retain + WaitForFirstConsumer semantics explained
- Troubleshooting section covers common Pending/ContainerCreating/Released scenarios
</verification>

<success_criteria>
- Operator can run the documented `zfs create` commands on thor and have all 4 datasets ready for PV binding (STORE-03)
- Operator knows how to snapshot + rollback (STORE-02 data survival procedure)
- Phase 34's DR doc will have a concrete file to link to for the storage layer
</success_criteria>

<output>
After completion, create `.planning/phases/30-zfs-backed-storage-infrastructure/30-zfs-backed-storage-infrastructure-03-SUMMARY.md` listing the doc file created, line count, and section titles.
</output>
