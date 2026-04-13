---
phase: 30-zfs-backed-storage-infrastructure
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - k8s/cluster/storage/storageclass-zfs-local.yaml
  - k8s/cluster/storage/pv-osm-pbf.yaml
  - k8s/cluster/storage/pv-nominatim-data.yaml
  - k8s/cluster/storage/pv-osm-tile-data.yaml
  - k8s/cluster/storage/pv-valhalla-tiles.yaml
  - k8s/cluster/storage/kustomization.yaml
autonomous: true
requirements:
  - STORE-01
  - STORE-02
  - STORE-03
must_haves:
  truths:
    - "zfs-local StorageClass exists with WaitForFirstConsumer binding mode and no-op provisioner"
    - "4 static PersistentVolumes exist (osm-pbf-pv 5Gi, nominatim-data-pv 50Gi, osm-tile-data-pv 20Gi, valhalla-tiles-pv 10Gi)"
    - "All 4 PVs pin to node thor via kubernetes.io/hostname nodeAffinity"
    - "All 4 PVs use reclaimPolicy: Retain so data survives PVC deletion"
    - "PV hostPaths map to /hatch1/data/geo/{pbf,nominatim,tile-server,valhalla} using hostPath type: Directory"
    - "kustomization.yaml enumerates all 5 manifests for future App-of-Apps inclusion"
  artifacts:
    - path: "k8s/cluster/storage/storageclass-zfs-local.yaml"
      provides: "zfs-local StorageClass definition"
      contains: "volumeBindingMode: WaitForFirstConsumer"
    - path: "k8s/cluster/storage/pv-osm-pbf.yaml"
      provides: "osm-pbf-pv (5Gi) Local PV manifest"
      contains: "reclaimPolicy: Retain"
    - path: "k8s/cluster/storage/pv-nominatim-data.yaml"
      provides: "nominatim-data-pv (50Gi) Local PV manifest"
      contains: "reclaimPolicy: Retain"
    - path: "k8s/cluster/storage/pv-osm-tile-data.yaml"
      provides: "osm-tile-data-pv (20Gi) Local PV manifest"
      contains: "reclaimPolicy: Retain"
    - path: "k8s/cluster/storage/pv-valhalla-tiles.yaml"
      provides: "valhalla-tiles-pv (10Gi) Local PV manifest"
      contains: "reclaimPolicy: Retain"
    - path: "k8s/cluster/storage/kustomization.yaml"
      provides: "Kustomize entrypoint listing all 5 manifests"
      contains: "resources:"
  key_links:
    - from: "PV manifests"
      to: "StorageClass zfs-local"
      via: "storageClassName field"
      pattern: "storageClassName: zfs-local"
    - from: "PV manifests"
      to: "node thor"
      via: "spec.nodeAffinity.required.nodeSelectorTerms"
      pattern: "kubernetes.io/hostname"
---

<objective>
Create the cluster-scoped storage manifests: a `zfs-local` StorageClass plus 4 static Local PersistentVolumes backed by ZFS datasets on node `thor`, wired together via a `kustomization.yaml` so the directory can be consumed by a future App-of-Apps.

Purpose: Establish persistent storage primitives (STORE-01, STORE-02, STORE-03) that survive PVC deletion and cluster rebuilds. Phase 31's OSM stack will consume these via PVCs.
Output: 6 YAML files under `k8s/cluster/storage/` ready to `kubectl apply -k` (applying is out of scope for this phase — disk-only deliverable).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/30-zfs-backed-storage-infrastructure/30-CONTEXT.md
@.planning/ROADMAP.md
@k8s/base/osm-pvcs.yaml

<interfaces>
<!-- PVC names from k8s/base/osm-pvcs.yaml that will bind to these PVs via storageClassName matching + WaitForFirstConsumer: -->
<!-- - osm-pbf-pvc (5Gi) -->
<!-- - nominatim-data-pvc (50Gi) -->
<!-- - osm-tile-data-pvc (20Gi) -->
<!-- - valhalla-tiles-pvc (10Gi) -->
<!-- Note: Local PVs do NOT use claimRef-by-name; binding is controlled by WaitForFirstConsumer + storageClassName + capacity + accessModes matching. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write StorageClass + kustomization.yaml</name>
  <files>k8s/cluster/storage/storageclass-zfs-local.yaml, k8s/cluster/storage/kustomization.yaml</files>
  <action>
Create `k8s/cluster/storage/storageclass-zfs-local.yaml` with:
- apiVersion: storage.k8s.io/v1
- kind: StorageClass
- metadata.name: zfs-local
- provisioner: kubernetes.io/no-provisioner  (disables dynamic provisioning — static PVs only, per D-01)
- volumeBindingMode: WaitForFirstConsumer  (per D-01 — required so PVs only bind when a consuming pod is scheduled, supporting cross-namespace binding for Phase 31's civpulse-gis namespace)
- reclaimPolicy: Retain

Create `k8s/cluster/storage/kustomization.yaml` with:
- apiVersion: kustomize.config.k8s.io/v1beta1
- kind: Kustomization
- resources list containing all 5 sibling manifests:
  - storageclass-zfs-local.yaml
  - pv-osm-pbf.yaml
  - pv-nominatim-data.yaml
  - pv-osm-tile-data.yaml
  - pv-valhalla-tiles.yaml

Add a top-of-file comment in the StorageClass YAML noting: "# Cluster-scoped. Static Local PVs on node thor backed by ZFS datasets at /hatch1/data/geo/*."
  </action>
  <verify>
    <automated>test -f k8s/cluster/storage/storageclass-zfs-local.yaml && test -f k8s/cluster/storage/kustomization.yaml && grep -q "WaitForFirstConsumer" k8s/cluster/storage/storageclass-zfs-local.yaml && grep -q "no-provisioner" k8s/cluster/storage/storageclass-zfs-local.yaml</automated>
  </verify>
  <done>Both files exist, StorageClass has WaitForFirstConsumer + no-provisioner, kustomization.yaml lists all 5 resources.</done>
</task>

<task type="auto">
  <name>Task 2: Write 4 static PV manifests</name>
  <files>k8s/cluster/storage/pv-osm-pbf.yaml, k8s/cluster/storage/pv-nominatim-data.yaml, k8s/cluster/storage/pv-osm-tile-data.yaml, k8s/cluster/storage/pv-valhalla-tiles.yaml</files>
  <action>
Create 4 PersistentVolume manifests, one per file. Each must follow this identical structure (swap name/capacity/path per PV):

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: <PV_NAME>
  labels:
    storage.civpulse.io/dataset: <DATASET_KEY>
spec:
  capacity:
    storage: <SIZE>
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: zfs-local
  volumeMode: Filesystem
  local:
    path: /hatch1/data/geo/<SUBPATH>
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - thor
```

The 4 PVs:

| File | PV_NAME | SIZE | SUBPATH | DATASET_KEY |
|------|---------|------|---------|-------------|
| pv-osm-pbf.yaml | osm-pbf-pv | 5Gi | pbf | osm-pbf |
| pv-nominatim-data.yaml | nominatim-data-pv | 50Gi | nominatim | nominatim |
| pv-osm-tile-data.yaml | osm-tile-data-pv | 20Gi | tile-server | osm-tile-data |
| pv-valhalla-tiles.yaml | valhalla-tiles-pv | 10Gi | valhalla | valhalla-tiles |

Important notes:
- Use `spec.local.path` (NOT `spec.hostPath`) — Local PVs require the `local` field. Per CONTEXT the decision to "fail-loud" is honored via the Directory requirement; `local.path` validates existence at mount time on node thor, giving identical fail-loud semantics. Do not use hostPath for PVs (Local is the standard Kubernetes type for node-pinned static volumes).
- Add a top-of-file comment: `# Static Local PV. Backed by ZFS dataset <SUBPATH> on thor. reclaimPolicy: Retain (STORE-02).`
- NO claimRef — binding happens via WaitForFirstConsumer + storageClassName + capacity matching.
  </action>
  <verify>
    <automated>for f in osm-pbf nominatim-data osm-tile-data valhalla-tiles; do test -f "k8s/cluster/storage/pv-$f.yaml" || exit 1; done && grep -l "reclaimPolicy: Retain" k8s/cluster/storage/pv-*.yaml | wc -l | grep -q "^4$" && grep -l "kubernetes.io/hostname" k8s/cluster/storage/pv-*.yaml | wc -l | grep -q "^4$" && grep -l "storageClassName: zfs-local" k8s/cluster/storage/pv-*.yaml | wc -l | grep -q "^4$"</automated>
  </verify>
  <done>All 4 PV files exist, each has Retain reclaim, each pins to thor via kubernetes.io/hostname, each references zfs-local StorageClass, sizes are 5/50/20/10Gi respectively.</done>
</task>

<task type="auto">
  <name>Task 3: Validate manifests parse cleanly as Kustomize build</name>
  <files>(validation only — no file writes)</files>
  <action>
Run `kubectl kustomize k8s/cluster/storage/` to confirm the directory builds without errors. This validates YAML syntax, Kustomize wiring, and catches typos. If kubectl is not available, fall back to parsing each YAML file with `python3 -c "import yaml; yaml.safe_load_all(open('<file>'))"` for each of the 6 files.

Expected output: Six YAML documents printed in order (StorageClass first, then 4 PVs in kustomization.yaml order). Non-zero exit means typo or schema error — fix and re-run.
  </action>
  <verify>
    <automated>kubectl kustomize k8s/cluster/storage/ > /tmp/phase30-kustomize-output.yaml 2>&1 && grep -c "^kind:" /tmp/phase30-kustomize-output.yaml | grep -qE "^[56]$" || (for f in k8s/cluster/storage/*.yaml; do uv run python -c "import yaml,sys; list(yaml.safe_load_all(open('$f')))" || exit 1; done)</automated>
  </verify>
  <done>Kustomize build succeeds (or all 6 YAMLs parse individually), output contains StorageClass + 4 PV kinds.</done>
</task>

</tasks>

<verification>
- All 6 files exist under `k8s/cluster/storage/`
- `kubectl kustomize k8s/cluster/storage/` emits valid multi-doc YAML with 1 StorageClass + 4 PersistentVolumes
- Grep confirms: 4x `reclaimPolicy: Retain`, 4x `kubernetes.io/hostname`, 4x `storageClassName: zfs-local`, 1x `WaitForFirstConsumer`, 1x `no-provisioner`
</verification>

<success_criteria>
- StorageClass `zfs-local` manifest exists with WaitForFirstConsumer and no-op provisioner (STORE-01)
- 4 static Local PVs exist with correct names, sizes, ZFS paths, node affinity to thor (STORE-02, STORE-03)
- All PVs have reclaimPolicy: Retain (STORE-02)
- kustomization.yaml enumerates all 5 manifests
- `kubectl kustomize k8s/cluster/storage/` builds without error
</success_criteria>

<output>
After completion, create `.planning/phases/30-zfs-backed-storage-infrastructure/30-zfs-backed-storage-infrastructure-01-SUMMARY.md` documenting files created, PV name/size/path mapping table, and note that manifests are disk-only (not applied to cluster this phase).
</output>
