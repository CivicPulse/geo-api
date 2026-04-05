# Phase 30: ZFS-Backed Storage Infrastructure - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Create a `zfs-local` StorageClass + 4 static Local PersistentVolumes backed by the ZFS dataset at `/hatch1/data/geo/*` on node `thor`, with `reclaimPolicy: Retain` so OSM data survives PVC deletion and cluster rebuilds. Update the 4 existing OSM PVCs to bind via `storageClassName: zfs-local`. Document the ZFS snapshot/restore procedure.

Scope includes manifest authorship + PVC wiring + snapshot docs. Scope excludes Phase 34's full bootstrap runbook and full DR playbook — this phase writes the storage-specific reference (`docs/ZFS-STORAGE.md`) that Phase 34's `docs/DR.md` will cite.

</domain>

<decisions>
## Implementation Decisions

### Manifest Organization
- Cluster-scoped manifests live in `k8s/cluster/storage/` — new top-level directory, clearly separated from namespace-scoped overlays
- Expected files: `storageclass-zfs-local.yaml`, `pv-osm-pbf.yaml`, `pv-nominatim-data.yaml`, `pv-osm-tile-data.yaml`, `pv-valhalla-tiles.yaml` (5 files)
- Add a `k8s/cluster/storage/kustomization.yaml` that lists all 5 so future App-of-Apps can include the directory

### ZFS Dataset Creation
- Datasets at `/hatch1/data/geo/{pbf,nominatim,tile-server,valhalla}` are created manually by a ZFS admin running `zfs create` on `thor` — documented in the runbook, NOT wrapped in a K8s Job
- Manifests assume paths exist; PVs with `WaitForFirstConsumer` will stay unbound harmlessly if datasets are missing (fail-loud for humans, fail-safe for cluster)

### ZFS Documentation
- `docs/ZFS-STORAGE.md` (new file) — dataset layout, `zfs create` commands, snapshot/rollback procedure, Retain semantics, PV/PVC binding model
- Phase 34's future `docs/DR.md` will link to this for the storage layer

### PVC Wiring
- Update `k8s/base/osm-pvcs.yaml` to add `storageClassName: zfs-local` on all 4 OSM PVCs now, even though Phase 31 will relocate them
- Rationale: the `storageClassName` travels with the PVC manifest, so Phase 31's move is just a file-path change; wiring the storageClassName here avoids Phase 31 having to touch two things

### Claude's Discretion
- Exact volume sizes already specified in ROADMAP (5/50/20/10 Gi) — no choice
- `accessModes: [ReadWriteOnce]` — only valid choice for Local PVs
- PV names follow ROADMAP: `osm-pbf-pv`, `nominatim-data-pv`, `osm-tile-data-pv`, `valhalla-tiles-pv`
- `hostPath.type: DirectoryOrCreate` vs `Directory` — use `Directory` to require manual ZFS dataset creation (fail-loud)
- Exact nodeAffinity selector key — use `kubernetes.io/hostname=thor` (standard)
- Whether to add a cluster-wide note comment at top of each PV YAML explaining the ZFS binding

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `k8s/base/osm-pvcs.yaml` — 4 PVCs already defined with correct names and sizes (osm-pbf 5Gi, nominatim-data 50Gi, osm-tile-data 20Gi, valhalla-tiles 10Gi). Just need `storageClassName: zfs-local` added.
- `k8s/base/pvc.yaml` — the ollama-pvc (10Gi), unrelated to OSM, leave untouched.

### Established Patterns
- Kustomize overlays under `k8s/overlays/{dev,prod}/` with base at `k8s/base/` — these are namespace-scoped
- Phase 28 established the convention of separate deployment/service files per sidecar
- No existing cluster-scoped resource manifests yet — `k8s/cluster/storage/` is the first

### Integration Points
- The 4 static PVs are the persistence layer that Phase 31's OSM stack (in `civpulse-gis` namespace) will consume
- Phase 31's PVCs will reference the same `storageClassName: zfs-local` when they relocate to `k8s/osm/base/`
- Phase 32's bootstrap Jobs (PBF download, Nominatim import, etc.) write to these PVCs — import data survives rebuilds thanks to `Retain`

</code_context>

<specifics>
## Specific Ideas

- `nodeAffinity: kubernetes.io/hostname=thor` — same node as the existing v1.4 sidecars
- `WaitForFirstConsumer` binding mode — PVs only bind when a pod in the target namespace actually needs them (supports cross-namespace PVC binding via Phase 31)
- `reclaimPolicy: Retain` — surviving PVC deletion is the whole point
- Document snapshot cadence as operator-choice (suggest daily for nominatim, weekly for tiles/valhalla, none for pbf since it's re-downloadable)

</specifics>

<deferred>
## Deferred Ideas

- Automated `zfs snapshot` cron on `thor` — out of scope; document as operator responsibility in Phase 34's runbook
- Dynamic provisioning via an actual ZFS CSI driver (OpenEBS ZFS-LocalPV) — explicitly excluded; static PVs are simpler and match the "data survives cluster rebuilds" requirement without new cluster deps
- Monitoring/alerting on ZFS pool health — out of scope for v1.5

</deferred>
