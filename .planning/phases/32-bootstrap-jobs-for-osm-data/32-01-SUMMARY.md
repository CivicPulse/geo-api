---
phase: 32-bootstrap-jobs-for-osm-data
plan: 01
subsystem: k8s-osm-bootstrap
tags: [k8s, jobs, osm, argocd, kustomize, nominatim, valhalla, tile-server]
requires:
  - osm-pbf-pvc (Phase 31)
  - osm-tile-data-pvc (Phase 31)
  - valhalla-tiles-pvc (Phase 31)
  - nominatim-data-pvc (Phase 31)
provides:
  - pbf-download-job (Georgia PBF downloader)
  - tile-import-job (tile-server import)
  - valhalla-build-job (routing tiles builder)
  - nominatim PBF volume mount at /nominatim/pbf/
affects:
  - k8s/osm/base/kustomization.yaml
  - k8s/osm/base/nominatim.yaml
tech-stack:
  added:
    - curlimages/curl:8
    - ArgoCD Sync hooks (hook-delete-policy: BeforeHookCreation)
  patterns:
    - shell-guard idempotency (size threshold, marker files, populated dir checks)
    - nodeSelector kubernetes.io/hostname=thor pinning
key-files:
  created:
    - k8s/osm/base/jobs/pbf-download-job.yaml
    - k8s/osm/base/jobs/tile-import-job.yaml
    - k8s/osm/base/jobs/valhalla-build-job.yaml
  modified:
    - k8s/osm/base/kustomization.yaml
    - k8s/osm/base/nominatim.yaml
decisions:
  - tile-import idempotency uses PG_VERSION marker file (avoids starting postgres to probe)
  - valhalla PBF copied into /custom_files/ since entrypoint expects it there
  - nominatim osm-pbf volume mount is read-only to prevent accidental writes by import
metrics:
  duration: "~4 min"
  tasks_completed: 2
  files_changed: 5
  completed: "2026-04-04"
---

# Phase 32 Plan 01: OSM Bootstrap Jobs Summary

**One-liner:** Three idempotent K8s Jobs (PBF download, tile import, Valhalla build) wired into kustomize with ArgoCD sync-hook annotations, plus nominatim Deployment mounting osm-pbf-pvc at /nominatim/pbf/ for auto-import.

## What Was Built

### Task 1 — Job Manifests (commit `fa764e2`)

Created `k8s/osm/base/jobs/` with three Job manifests. All Jobs share namespace `civpulse-gis`, ArgoCD `Sync` + `BeforeHookCreation` annotations, `nodeSelector: kubernetes.io/hostname=thor`, `restartPolicy: OnFailure`, and `imagePullPolicy: IfNotPresent`.

- **pbf-download-job.yaml** (JOB-01): `curlimages/curl:8`, backoffLimit=2, deadline=900s. Shell-guard skips if PBF already exists and is >100MB; otherwise curl-downloads georgia-latest.osm.pbf from Geofabrik to `/data/pbf/` on `osm-pbf-pvc`.
- **tile-import-job.yaml** (JOB-03): `overv/openstreetmap-tile-server:2.3.0`, backoffLimit=1, deadline=3600s. Shell-guard skips if `/data/database/postgres/PG_VERSION` exists; otherwise `exec /run.sh import`. Mounts `osm-tile-data-pvc` at `/data/database` and `osm-pbf-pvc` read-only at `/data/region.osm.pbf` (subPath `pbf/georgia-latest.osm.pbf`).
- **valhalla-build-job.yaml** (JOB-04): `ghcr.io/valhalla/valhalla:latest`, backoffLimit=1, deadline=3600s. Env `serve_tiles=False`, `force_rebuild=True`, `build_admins=False`, `build_elevation=False`. Shell-guard skips if `/custom_files/valhalla_tiles/` is populated; otherwise copies PBF into `/custom_files/` and runs `/valhalla/scripts/run.sh`.

All three passed `kubectl apply --dry-run=client`.

### Task 2 — Kustomize Wiring & Nominatim PBF Mount (commit `0eda78f`)

- **kustomization.yaml**: Added `jobs/pbf-download-job.yaml`, `jobs/tile-import-job.yaml`, `jobs/valhalla-build-job.yaml` to `resources:` list (commonLabels preserved verbatim).
- **nominatim.yaml** (JOB-02): Added `osm-pbf` volume (claim `osm-pbf-pvc`) + volumeMount at `/nominatim/pbf` readOnly. Existing `nominatim-data` volume and Service untouched. Matches existing `PBF_PATH=/nominatim/pbf/georgia-latest.osm.pbf` env var.

`kubectl kustomize k8s/osm/base` renders successfully; all 3 Jobs and the `/nominatim/pbf` mount are present in rendered output.

## Requirements Implemented

- JOB-01 — pbf-download-job manifest with curl + size-guard idempotency
- JOB-02 — nominatim mounts osm-pbf-pvc at /nominatim/pbf/ read-only
- JOB-03 — tile-import-job manifest with PG_VERSION marker idempotency
- JOB-04 — valhalla-build-job manifest with valhalla_tiles/ idempotency
- JOB-05 — All Jobs wired into kustomization.yaml with ArgoCD sync-hook annotations

## Deviations from Plan

None - plan executed exactly as written.

## Commits

- `fa764e2` feat(32-01): add OSM bootstrap Job manifests
- `0eda78f` feat(32-01): wire OSM jobs into kustomize and mount PBF in nominatim

## Self-Check: PASSED

Files verified present:
- FOUND: k8s/osm/base/jobs/pbf-download-job.yaml
- FOUND: k8s/osm/base/jobs/tile-import-job.yaml
- FOUND: k8s/osm/base/jobs/valhalla-build-job.yaml
- FOUND: k8s/osm/base/kustomization.yaml (modified)
- FOUND: k8s/osm/base/nominatim.yaml (modified)

Commits verified:
- FOUND: fa764e2
- FOUND: 0eda78f

Verifications passed:
- kubectl apply --dry-run=client on all 3 Jobs
- kubectl kustomize k8s/osm/base rendered and contains all 3 Jobs + /nominatim/pbf
