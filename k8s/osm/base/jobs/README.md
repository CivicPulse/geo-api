# OSM Bootstrap Jobs

## Overview

These Jobs bootstrap OpenStreetMap data into PVCs on node `thor` in the
`civpulse-gis` namespace. They are idempotent — shell guards in each Job skip
work when data is already present — and trigger automatically on ArgoCD Sync
via `argocd.argoproj.io/hook: Sync` annotations. Together they stage the
Geofabrik Georgia PBF, import it into the tile-server PostgreSQL, build the
Valhalla routing graph, and (indirectly) drive the Nominatim Deployment's
auto-import entrypoint.

## Job Ordering

The bootstrap DAG has one root and three dependent workloads:

1. `pbf-download-job` runs first (no deps). It fetches
   `georgia-latest.osm.pbf` from Geofabrik into `osm-pbf-pvc` at the
   PVC root (`georgia-latest.osm.pbf`).
2. `tile-import-job`, `valhalla-build-job`, and the `nominatim` Deployment's
   auto-import entrypoint all depend on the PBF being staged at
   `osm-pbf-pvc:/georgia-latest.osm.pbf` (PVC root, not a subdirectory).
3. With ArgoCD sync hooks, all Jobs submit concurrently. The
   tile/valhalla/nominatim workloads will block (`CrashLoopBackOff` or
   `ContainerCreating`) until the PBF exists. Re-running the sync after
   `pbf-download-job` completes unblocks them. Operators can also apply
   `pbf-download-job` first, wait for completion, then apply the remaining
   Jobs — see the Manual kubectl apply Workflow section.

## Idempotency Guards

Each Job's entrypoint checks for a marker before doing work:

| Job | Skip if | Marker checked |
|-----|---------|----------------|
| pbf-download-job | PBF file present and >100MB | `/data/pbf/georgia-latest.osm.pbf` size via `stat` |
| tile-import-job | postgres data already initialized | `/data/database/postgres/PG_VERSION` exists |
| valhalla-build-job | routing tiles present | `/custom_files/valhalla_tiles/` non-empty |
| nominatim (Deployment auto-import) | DB already imported | internal — `mediagis/nominatim:5.2` entrypoint handles it |

## Manual kubectl apply Workflow

For clusters not using ArgoCD, or when running the bootstrap out-of-band:

```bash
# Prereqs: Phase 31 PVCs already bound; civpulse-gis namespace exists.
kubectl -n civpulse-gis apply -f k8s/osm/base/jobs/pbf-download-job.yaml
kubectl -n civpulse-gis wait --for=condition=complete job/pbf-download-job --timeout=15m

kubectl -n civpulse-gis apply -f k8s/osm/base/jobs/tile-import-job.yaml
kubectl -n civpulse-gis apply -f k8s/osm/base/jobs/valhalla-build-job.yaml
kubectl -n civpulse-gis rollout restart deploy/nominatim   # triggers auto-import

# Watch progress
kubectl -n civpulse-gis get jobs -w
kubectl -n civpulse-gis logs -f job/tile-import-job
```

Note: `hook-delete-policy: BeforeHookCreation` means ArgoCD replaces prior
Jobs on each sync. For manual apply, `kubectl delete job <name>` first if
re-running after a failure.

## Expected Runtimes (Georgia-sized region, node `thor`)

| Job | Typical runtime | activeDeadlineSeconds |
|-----|-----------------|-----------------------|
| pbf-download-job | ~5 min | 900 (15 min) |
| tile-import-job | ~90 min | 10800 (3 hr) |
| valhalla-build-job | ~30 min | 3600 (60 min) |
| nominatim auto-import (Deployment) | ~90 min | — (Deployment, not Job) |

The tile-import deadline has ~2× headroom over the typical 90-min runtime to
absorb cold-cache variance on first bootstrap. Tighten later if desired once
per-host runtime is well characterized.

## Troubleshooting

- **pbf-download fails with HTTP 4xx**: Geofabrik URL changed or rate-limited.
  Verify <https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf>
  still exists.
- **tile-import hangs at "Setting up postgres"**: Stale postgres lock file.
  `kubectl -n civpulse-gis exec -it <tile-server-pod> -- rm /data/database/postgres/postmaster.pid`
- **valhalla-build OOMKilled**: Limits are 10Gi request / 16Gi limit to
  absorb ~8Gi peak on Georgia-sized graphs; bump further if still OOMKilled
  on larger regions or newer Valhalla revisions.
- **Nominatim Deployment CrashLoopBackOff with "PBF not found"**: Confirm
  `osm-pbf-pvc` is mounted at `/nominatim/pbf/` (Plan 01 Task 2) and PBF file
  exists via `kubectl exec`.
- **Job stays Pending**: Check `kubectl describe job <name>` — most likely
  the `thor` nodeSelector + PVC nodeAffinity require the pod to schedule on
  node `thor`. Ensure node is Ready.

## Re-running After Data Corruption

To force a full rebuild (e.g., after corruption or to ingest a fresh PBF):

1. `kubectl -n civpulse-gis scale deploy/nominatim deploy/tile-server deploy/valhalla --replicas=0`
2. `kubectl -n civpulse-gis delete pvc osm-pbf-pvc osm-tile-data-pvc valhalla-tiles-pvc nominatim-data-pvc`
3. Re-apply PVCs (Phase 31), then Jobs per the manual workflow above.

Implements requirement JOB-05 (documented kubectl apply workflow).
