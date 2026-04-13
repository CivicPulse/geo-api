---
phase: 30-zfs-backed-storage-infrastructure
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - k8s/base/osm-pvcs.yaml
autonomous: true
requirements:
  - STORE-04
must_haves:
  truths:
    - "All 4 OSM PVCs (osm-pbf-pvc, nominatim-data-pvc, osm-tile-data-pvc, valhalla-tiles-pvc) declare storageClassName: zfs-local"
    - "PVC names, sizes, and accessModes are unchanged from prior state"
    - "File still parses as valid multi-doc YAML"
  artifacts:
    - path: "k8s/base/osm-pvcs.yaml"
      provides: "4 OSM PVCs wired to zfs-local StorageClass"
      contains: "storageClassName: zfs-local"
  key_links:
    - from: "k8s/base/osm-pvcs.yaml PVCs"
      to: "StorageClass zfs-local (Plan 01)"
      via: "storageClassName field on each PVC spec"
      pattern: "storageClassName: zfs-local"
---

<objective>
Update the 4 existing OSM PVCs in `k8s/base/osm-pvcs.yaml` to add `storageClassName: zfs-local` so they bind to the static Local PVs created in Plan 01.

Purpose: Wire the consumer side (PVCs) to the provider side (static PVs) via matching storageClassName (STORE-04, per D-04 in CONTEXT). This binding travels with the PVC manifest, so Phase 31's relocation of these PVCs to `k8s/osm/base/` will be a pure file-move with no wiring changes.
Output: One modified file — `k8s/base/osm-pvcs.yaml` — with `storageClassName: zfs-local` added to all 4 PVC specs. No apply to cluster.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/30-zfs-backed-storage-infrastructure/30-CONTEXT.md
@k8s/base/osm-pvcs.yaml

<interfaces>
<!-- Current structure of k8s/base/osm-pvcs.yaml: 4 PVCs, each with accessModes + resources.requests.storage only. No storageClassName set (binds to cluster default). -->
<!-- Target: add `storageClassName: zfs-local` under each spec, preserving all other fields and ordering. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add storageClassName to all 4 PVCs</name>
  <files>k8s/base/osm-pvcs.yaml</files>
  <action>
Edit `k8s/base/osm-pvcs.yaml` to add `storageClassName: zfs-local` to the spec of each of the 4 PVCs. Place it immediately after `accessModes:` block and before `resources:` in each PVC for consistent ordering.

The 4 PVCs to update (all of them in this file):
1. `nominatim-data-pvc`
2. `osm-tile-data-pvc`
3. `valhalla-tiles-pvc`
4. `osm-pbf-pvc`

Example of target structure for each PVC:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: <pvc-name>
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: zfs-local
  resources:
    requests:
      storage: <size>
```

Do NOT change names, sizes, or accessModes. Do NOT remove the `---` document separators. Leave `k8s/base/pvc.yaml` (the unrelated ollama-pvc) untouched.
  </action>
  <verify>
    <automated>grep -c "storageClassName: zfs-local" k8s/base/osm-pvcs.yaml | grep -q "^4$" && uv run python -c "import yaml; docs=list(yaml.safe_load_all(open('k8s/base/osm-pvcs.yaml'))); assert len(docs)==4; assert all(d['spec']['storageClassName']=='zfs-local' for d in docs); assert {d['metadata']['name'] for d in docs}=={'nominatim-data-pvc','osm-tile-data-pvc','valhalla-tiles-pvc','osm-pbf-pvc'}; print('OK')"</automated>
  </verify>
  <done>File has exactly 4 occurrences of `storageClassName: zfs-local`, still parses as 4 PVC documents, all 4 expected PVC names present with unchanged sizes.</done>
</task>

<task type="auto">
  <name>Task 2: Confirm sizes and PVC identity preserved</name>
  <files>(validation only)</files>
  <action>
Run a focused diff-style check to ensure no regressions: parse the file and confirm each PVC still declares the exact size from the original (5Gi/50Gi/20Gi/10Gi mapped correctly to osm-pbf/nominatim-data/osm-tile-data/valhalla-tiles) and accessModes is still `[ReadWriteOnce]`.
  </action>
  <verify>
    <automated>uv run python -c "import yaml; docs={d['metadata']['name']:d for d in yaml.safe_load_all(open('k8s/base/osm-pvcs.yaml'))}; expected={'osm-pbf-pvc':'5Gi','nominatim-data-pvc':'50Gi','osm-tile-data-pvc':'20Gi','valhalla-tiles-pvc':'10Gi'}; [print(n,':', docs[n]['spec']['resources']['requests']['storage']) or (docs[n]['spec']['resources']['requests']['storage']==s or exit(1)) for n,s in expected.items()]; [docs[n]['spec']['accessModes']==['ReadWriteOnce'] or exit(1) for n in expected]; print('sizes+access OK')"</automated>
  </verify>
  <done>All 4 PVCs retain original sizes and accessModes; only storageClassName is newly added.</done>
</task>

</tasks>

<verification>
- `k8s/base/osm-pvcs.yaml` contains 4 PVCs, each with `storageClassName: zfs-local`
- Original sizes preserved (5Gi, 50Gi, 20Gi, 10Gi)
- File parses as valid YAML
</verification>

<success_criteria>
- All 4 OSM PVCs reference `storageClassName: zfs-local` (STORE-04)
- No other fields changed
- YAML still valid and parseable
</success_criteria>

<output>
After completion, create `.planning/phases/30-zfs-backed-storage-infrastructure/30-zfs-backed-storage-infrastructure-02-SUMMARY.md` documenting the single-file diff (4 lines added), preserved fields, and note that the PVCs will only bind once Plan 01's PVs are applied AND a consuming pod is scheduled (per WaitForFirstConsumer).
</output>
