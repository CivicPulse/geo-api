# Bootstrap Runbook — Fresh Cluster Bring-Up

Operator runbook for standing up the CivPulse Geo API OSM stack on a fresh cluster. Follow steps in order; each step has a verification command with expected output. On completion, run the E2E checklist in `docs/E2E.md`.

**Total wall-clock time (first bootstrap, serial):** ~3.5 hours. Tile import + Valhalla build + Nominatim auto-import can run in parallel after the PBF lands.

**Related docs:**
- `docs/ZFS-STORAGE.md` — ZFS dataset layout, PV/PVC binding model
- `docs/DR.md` — snapshot/rollback procedure
- `docs/E2E.md` — end-to-end verification checklist
- `k8s/osm/base/jobs/README.md` — Job runtimes, idempotency guards, manual workflow

---

## Prerequisites

Before starting, confirm:

1. **kubectl context** points at the target cluster:
   ```bash
   kubectl config current-context
   ```
   Expected: the cluster name hosting node `thor` (e.g. `civpulse-prod`).

2. **Required namespaces** exist:
   ```bash
   kubectl get ns argocd civpulse-gis
   ```
   Expected: both listed as `Active`. If `civpulse-gis` is missing, it will be auto-created by the `osm-stack` ArgoCD Application in Step 3 (`CreateNamespace=true`). `argocd` must already exist.

3. **Node `thor`** is Ready and has the ZFS parent dataset mounted:
   ```bash
   kubectl get node thor -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
   ```
   Expected: `True`.

4. **Root access on `thor`** for the `zfs create` commands in Step 1.

---

## Step 1: Create ZFS datasets on `thor`

Run on node `thor` as `root`. `hatch1/geo` is a **new top-level dataset** (sibling to `hatch1/data`, which is Docker's ZFS graphdriver root — we keep OSM storage on its own failure domain). Create the parent first, then the four children. See `docs/ZFS-STORAGE.md` §3 for background.

```bash
# As root on thor
zfs create hatch1/geo
zfs create hatch1/geo/pbf
zfs create hatch1/geo/nominatim
zfs create hatch1/geo/tile-server
zfs create hatch1/geo/valhalla
```

**Verify:**
```bash
zfs list -r hatch1/geo
```

Expected: parent plus four child datasets, each mounted under `/hatch1/geo/`:
```
NAME                      USED  AVAIL  REFER  MOUNTPOINT
hatch1/geo                 96K   ...    96K   /hatch1/geo
hatch1/geo/pbf             96K   ...    96K   /hatch1/geo/pbf
hatch1/geo/nominatim       96K   ...    96K   /hatch1/geo/nominatim
hatch1/geo/tile-server     96K   ...    96K   /hatch1/geo/tile-server
hatch1/geo/valhalla        96K   ...    96K   /hatch1/geo/valhalla
```

---

## Step 2: Apply cluster-scoped storage

Apply the `zfs-local` StorageClass and the four static Local PVs.

```bash
kubectl apply -k k8s/cluster/storage/
```

**Verify StorageClass:**
```bash
kubectl get storageclass zfs-local
```
Expected:
```
NAME         PROVISIONER                    RECLAIMPOLICY   VOLUMEBINDINGMODE      ...
zfs-local    kubernetes.io/no-provisioner   Retain          WaitForFirstConsumer   ...
```

**Verify PVs:**
```bash
kubectl get pv | grep -E 'osm-pbf-pv|nominatim-data-pv|osm-tile-data-pv|valhalla-tiles-pv'
```
Expected: 4 PVs, all `Available`, capacities `5Gi / 50Gi / 20Gi / 10Gi`, `RECLAIMPOLICY=Retain`, `STORAGECLASS=zfs-local`.

(PVs stay `Available` until a pod references the matching PVC — this is normal for `WaitForFirstConsumer`.)

---

## Step 3: Apply the `osm-stack` ArgoCD Application

```bash
kubectl apply -f k8s/osm/overlays/prod/argocd-app.yaml
```

This creates the `osm-stack` Application in the `argocd` namespace, tracking `main` at path `k8s/osm/overlays/prod` with auto-sync + prune + selfHeal + `CreateNamespace=true`.

**Verify Application is registered and syncing:**
```bash
kubectl -n argocd get application osm-stack
```
Expected (within ~60s):
```
NAME        SYNC STATUS   HEALTH STATUS
osm-stack   Synced        Healthy
```

If `SYNC STATUS=OutOfSync`, wait a few seconds then re-check; auto-sync usually converges in under a minute. If it stays OutOfSync, see Troubleshooting below.

**Verify the namespace was created and Deployments exist:**
```bash
kubectl -n civpulse-gis get deploy
```
Expected:
```
NAME          READY   UP-TO-DATE   AVAILABLE
nominatim     0/1     1            0
tile-server   0/1     1            0
valhalla      0/1     1            0
```
(Pods are not yet Ready — they're waiting for the PBF from Step 4.)

**Verify PVCs bound:**
```bash
kubectl -n civpulse-gis get pvc
```
Expected: all 4 PVCs (`osm-pbf-pvc`, `nominatim-data-pvc`, `osm-tile-data-pvc`, `valhalla-tiles-pvc`) `Bound`.

---

## Step 4: Trigger bootstrap Jobs

If the `osm-stack` ArgoCD Application is synced, the bootstrap Jobs fire automatically via `argocd.argoproj.io/hook: Sync` annotations. Verify:

```bash
kubectl -n civpulse-gis get jobs
```
Expected (within ~60s of ArgoCD sync):
```
NAME                 COMPLETIONS   DURATION   AGE
pbf-download-job     0/1           30s        30s
tile-import-job      0/1           30s        30s
valhalla-build-job   0/1           30s        30s
```

**Manual fallback** — if Jobs are not present (sync hooks not firing, or applying out-of-band), follow the manual workflow in `k8s/osm/base/jobs/README.md` §Manual kubectl apply Workflow:

```bash
kubectl -n civpulse-gis apply -f k8s/osm/base/jobs/pbf-download-job.yaml
kubectl -n civpulse-gis wait --for=condition=complete job/pbf-download-job --timeout=15m
kubectl -n civpulse-gis apply -f k8s/osm/base/jobs/tile-import-job.yaml
kubectl -n civpulse-gis apply -f k8s/osm/base/jobs/valhalla-build-job.yaml
kubectl -n civpulse-gis rollout restart deploy/nominatim   # triggers auto-import
```

---

## Step 5: Wait for imports

Expected runtimes on `thor` (Georgia-sized region):

| Workload | Typical runtime | Dependency |
|----------|-----------------|------------|
| pbf-download-job | ~5 min | none (root) |
| nominatim (auto-import on Deployment) | ~90 min | PBF staged |
| tile-import-job | ~90 min | PBF staged |
| valhalla-build-job | ~30 min | PBF staged |

Tile import + Valhalla build + Nominatim auto-import run concurrently after the PBF lands. Serial total: ~3.5h. Concurrent total: ~1h40m (dominated by the 90-minute imports).

**Watch progress:**
```bash
kubectl -n civpulse-gis get jobs -w
kubectl -n civpulse-gis logs -f job/pbf-download-job
kubectl -n civpulse-gis logs -f job/tile-import-job
kubectl -n civpulse-gis logs -f job/valhalla-build-job
kubectl -n civpulse-gis logs -f deploy/nominatim
```

**Verify Jobs completed:**
```bash
kubectl -n civpulse-gis get jobs
```
Expected (eventually):
```
NAME                 COMPLETIONS   DURATION
pbf-download-job     1/1           5m
tile-import-job      1/1           ~90m
valhalla-build-job   1/1           ~30m
```

**Verify Deployments Ready:**
```bash
kubectl -n civpulse-gis get deploy
```
Expected: all three `READY=1/1`.

See `k8s/osm/base/jobs/README.md` §Expected Runtimes for per-job deadline details and idempotency guards (Jobs safely re-run — they skip work when data is already present).

---

## Step 6: Verify via E2E checklist

Once all sidecar Deployments are Ready, run through `docs/E2E.md` against both `civpulse-dev` and `civpulse-prod` environments. At minimum confirm:

```bash
curl -s https://geo-api-prod.example.com/health/ready | jq .sidecars
```
Expected:
```json
{"nominatim": "ready", "tile_server": "ready", "valhalla": "ready"}
```

Then proceed through the full endpoint checklist (`/tiles`, `/geocode/reverse`, `/poi/search`, `/route`) per `docs/E2E.md`.

Bootstrap is complete when every check in `docs/E2E.md` passes.

---

## Troubleshooting

### PVC stays `Pending`

- **Cause:** ZFS dataset missing on `thor`, or pod not scheduling onto `thor`.
- **Fix:** Verify Step 1 (`ls /hatch1/geo/` on the node). Verify pod node affinity landed it on `thor` (`kubectl describe pod <name>`).
- **Reference:** `docs/ZFS-STORAGE.md` §7.

### Pod stuck `ContainerCreating` with mount errors

- **Cause:** ZFS dataset path missing on `thor`.
- **Fix:** `ls /hatch1/geo/` on the node; create any missing dataset with `zfs create hatch1/geo/<name>`.

### Job `CrashLoopBackOff` or failing

- **pbf-download HTTP 4xx:** Geofabrik URL rate-limited or changed — see `k8s/osm/base/jobs/README.md` §Troubleshooting.
- **tile-import hangs at "Setting up postgres":** stale postgres lock file. `kubectl -n civpulse-gis exec -it <tile-server-pod> -- rm /data/database/postgres/postmaster.pid`.
- **valhalla-build OOMKilled:** bump memory limits; Georgia graph spikes over 8Gi on some revisions.
- **Nominatim "PBF not found":** confirm `osm-pbf-pvc` mount at `/nominatim/pbf/` and PBF file exists via `kubectl exec`.

### ArgoCD `ComparisonError` on `osm-stack`

- **Cause:** manifest validation error or missing CRD/namespace.
- **Fix:** `kubectl -n argocd describe application osm-stack` for the error. Most common: `civpulse-gis` namespace creation racing — re-sync after ~30s.

### Jobs never run (no Job objects appear)

- **Cause:** Sync hooks not firing, or `hook-delete-policy: BeforeHookCreation` already cleaned them up post-completion.
- **Check:** `kubectl -n civpulse-gis get jobs --show-labels` and Application events. Fall back to manual `kubectl apply` workflow from Step 4.

For post-bootstrap data loss or corruption, see `docs/DR.md`.
