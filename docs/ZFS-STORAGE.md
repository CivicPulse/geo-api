# ZFS-Backed Storage — Operator Reference

This document is the canonical reference for the static Local PV storage layer that backs the OSM stack (Nominatim, tile-server, Valhalla, raw PBF). Future DR runbooks (Phase 34) link here for the storage layer rather than duplicating content.

## 1. Overview

The `civpulse-gis` namespace consumes four persistent volumes that are statically provisioned against ZFS datasets on node `thor`. Each PV uses `persistentVolumeReclaimPolicy: Retain`, so deleting a PVC — or even tearing down and recreating the cluster — leaves the underlying OSM data intact on disk. This is a deliberate tradeoff: OSM data is expensive to rebuild (hours to days for Nominatim imports), and must survive cluster rebuilds.

**Scope:** four datasets under `/hatch1/data/geo/`:

- `pbf` — raw OSM `.osm.pbf` downloads (re-downloadable source data)
- `nominatim` — PostgreSQL data directory for the Nominatim geocoder
- `tile-server` — rendered tile cache for the OSM tile server
- `valhalla` — graph tiles for the Valhalla routing engine

**Why static PVs (and not OpenEBS ZFS-LocalPV):** static Local PVs add zero cluster dependencies — no CSI driver, no controller pod, no CRDs. The OSM stack is pinned to node `thor` anyway, so the flexibility of dynamic provisioning buys us nothing. OpenEBS ZFS-LocalPV is the correct choice for multi-node dynamic workloads, but it is explicitly deferred here and is not used.

## 2. Dataset Layout

| PV | PVC | Path | Size | Snapshot cadence |
|----|-----|------|------|------------------|
| osm-pbf-pv | osm-pbf-pvc | /hatch1/data/geo/pbf | 5Gi | none (re-downloadable) |
| nominatim-data-pv | nominatim-data-pvc | /hatch1/data/geo/nominatim | 50Gi | daily |
| osm-tile-data-pv | osm-tile-data-pvc | /hatch1/data/geo/tile-server | 20Gi | weekly |
| valhalla-tiles-pv | valhalla-tiles-pvc | /hatch1/data/geo/valhalla | 10Gi | weekly |

All PVCs live in the `civpulse-gis` namespace. PVs are cluster-scoped. Node affinity on each PV restricts binding to node `thor`.

## 3. Initial Dataset Creation

Run as `root` on `thor`. The parent `hatch1/data/geo` dataset is assumed to exist and be mounted at `/hatch1/data/geo`.

```bash
# Run as root on thor
zfs create hatch1/data/geo/pbf
zfs create hatch1/data/geo/nominatim
zfs create hatch1/data/geo/tile-server
zfs create hatch1/data/geo/valhalla

# Verify mountpoints
zfs list -r hatch1/data/geo
```

Expected output is four child datasets, each mounted at `/hatch1/data/geo/<name>`.

**Note:** The PV manifests use `local.path` with the filesystem path. If a dataset is missing when a pod tries to mount, kubelet fails the mount loudly (pod stuck in `ContainerCreating` with an `mount failed` event). PVs with `volumeBindingMode: WaitForFirstConsumer` stay `Available` with no pod-side error until a consumer is scheduled — absence of a dataset does not surface until the first pod lands.

## 4. Snapshot Procedure

ZFS snapshots are cheap (copy-on-write) and fast. Name snapshots with ISO dates so `zfs list -t snapshot` output is sortable.

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

**Recommended cadence:**

- `nominatim` — **daily** (heavy writes during imports, expensive to rebuild)
- `tile-server`, `valhalla` — **weekly** (moderate change rate, regenerable from source)
- `pbf` — **none** (source data, re-downloadable from Geofabrik)

Prune old snapshots with `zfs destroy hatch1/data/geo/<ds>@<snapname>` as space requires.

## 5. Rollback Procedure

`zfs rollback` reverts a dataset to the state captured in a snapshot. This is destructive — it discards every change made since the snapshot.

```bash
# Scale consumer pods to 0 first so the mount is not in use
kubectl -n civpulse-gis scale deployment nominatim --replicas=0

# Roll a dataset back to a snapshot (DESTRUCTIVE — discards changes since snapshot)
zfs rollback hatch1/data/geo/nominatim@2026-04-01

# Bring the consumer back
kubectl -n civpulse-gis scale deployment nominatim --replicas=1
```

**Warning:** `zfs rollback` destroys any snapshots taken *after* the target snapshot. If intermediate snapshots exist, ZFS will refuse and require `zfs rollback -r` to acknowledge and discard them.

## 6. Retain Semantics + PV/PVC Binding Model

Each static PV is declared with `persistentVolumeReclaimPolicy: Retain` (the `reclaimPolicy` field). The binding lifecycle:

- **Available** — PV created, no claim yet. With `WaitForFirstConsumer`, the PV stays here until a pod referencing the matching PVC is scheduled.
- **Bound** — a PVC has bound to the PV; the pod can mount it.
- **Released** — the PVC has been deleted, but the PV still holds a `spec.claimRef` referencing the old (now-gone) PVC. **The on-disk data is untouched.**
- **Available (again)** — after manually clearing `claimRef`, the PV can be re-bound.

To reuse a `Released` PV:

```bash
kubectl patch pv <name> --type=json \
  -p='[{"op":"remove","path":"/spec/claimRef"}]'
```

`Retain` deliberately prevents Kubernetes from ever touching the disk. Deleting a PVC does not delete data; destroying the cluster does not delete data. The only way data is lost is by running `zfs destroy` on `thor`.

**Binding model:** `WaitForFirstConsumer` (from the StorageClass) defers binding until a pod using the PVC is scheduled. This is mandatory for Local PVs because the scheduler must co-locate the pod with the node the PV lives on. It also means PVCs can be declared in `civpulse-gis` even though PVs are cluster-scoped — binding waits until a consumer pod is scheduled onto `thor`.

**Capacity matching:** Kubernetes binds the smallest PV whose `capacity >= PVC.spec.resources.requests.storage`, and whose `storageClassName` and `accessModes` also match. Our capacities are exact per PV/PVC pair, so there is no ambiguity in matching.

## 7. Troubleshooting

- **PVC stays `Pending` forever** — check that (a) a pod that mounts the PVC is actually scheduled (`WaitForFirstConsumer` is normal until then), (b) the ZFS dataset exists on `thor`, (c) the pod's node affinity or nodeSelector lands it on `thor`.
- **Pod stuck `ContainerCreating` with mount errors** — the dataset path is missing on `thor`. Run `ls /hatch1/data/geo/` on the node and create any missing dataset with `zfs create`.
- **PV stuck `Released` after PVC delete** — expected behavior with `Retain`. Clear `claimRef` as shown above to reuse, or `kubectl delete pv <name>` to remove the PV object (the data remains on disk under `/hatch1/data/geo/<name>`).
- **Need to wipe and start over for one dataset** — scale consumers to 0, delete the PVC, delete the PV, then on `thor`: `zfs destroy -r hatch1/data/geo/<name>`, recreate with `zfs create`, and reapply the PV manifest.
- **Snapshot rollback refuses** — later snapshots exist. Add `-r` to `zfs rollback` to discard them, or destroy them explicitly first.

## 8. Related

- `k8s/cluster/storage/` — static PV + StorageClass manifests (Plan 01)
- `k8s/base/osm-pvcs.yaml` — OSM PVCs that bind to these PVs
- Phase 34 `docs/DR.md` (future) — will link here for the storage layer
