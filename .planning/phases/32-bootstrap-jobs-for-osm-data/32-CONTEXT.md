# Phase 32: Bootstrap Jobs for OSM Data - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Translate the Docker Compose-based OSM pipeline (Phase 24) into native K8s Jobs that run inside `civpulse-gis` namespace against the PVCs Phase 31 created. Jobs are idempotent (skip when data present), triggered by ArgoCD sync hooks, and populate PVCs so sidecars from Phase 31 become Healthy.

</domain>

<decisions>
## Implementation Decisions

### Job Roster
- **3 Jobs**: `pbf-download-job`, `tile-import-job`, `valhalla-build-job`
- Nominatim import is NOT a separate Job — the `mediagis/nominatim:5.2` image auto-imports during first container startup (per Phase 24 CLI docs). `pbf-download-job` stages the PBF so Nominatim's auto-import can run. This matches success criterion #2's "OR" clause.

### Idempotency
- Shell-guard pattern inside each Job's command: `[ -f /marker ] && echo "already present, skipping" && exit 0`
- pbf-download: skip if `/data/pbf/georgia-latest.osm.pbf` exists AND size > 100MB
- tile-import: skip if `renderer` PG role exists in tile-server's internal PG (requires exec-in approach — use a pre-check shell loop against a mounted check script)
- valhalla-build: skip if `/data/valhalla/tiles/` non-empty

### Trigger Mechanism
- ArgoCD sync hooks: `metadata.annotations: argocd.argoproj.io/hook: Sync` + `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`
- Jobs re-run on each ArgoCD sync (idempotency guards prevent redundant work)
- `BeforeHookCreation` deletes the previous Job before re-running so names stay stable

### Manifest Location
- `k8s/osm/base/jobs/` — new subdirectory grouping bootstrap Jobs
- Files: `pbf-download-job.yaml`, `tile-import-job.yaml`, `valhalla-build-job.yaml`
- Include each in `k8s/osm/base/kustomization.yaml` resources list

### Scheduling
- All Jobs pinned to node `thor` via `nodeSelector: kubernetes.io/hostname: thor` (same node as Local PVs from Phase 30)
- Required — Local PVs have nodeAffinity=thor

### Runtime / Images
- pbf-download: `curlimages/curl:8` image, one-liner `curl -fsSL -o /data/pbf/georgia-latest.osm.pbf https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf`
- tile-import: `overv/openstreetmap-tile-server:2.3.0` image with `import` command (same as Docker Compose `docker compose run --rm tile-server import`)
- valhalla-build: `ghcr.io/valhalla/valhalla:latest` with `serve_tiles=False force_rebuild=True build_admins=False build_elevation=False` env vars

### Resource Requests
- pbf-download: 100m CPU / 256Mi memory (trivial)
- tile-import: 1 CPU / 4Gi memory (Phase 24 observed usage)
- valhalla-build: 2 CPU / 8Gi memory (Phase 24 observed peak during graph build)

### Claude's Discretion
- Exact backoffLimit value per Job — use 2 for download (network-retry), 1 for compute Jobs (fail fast)
- Job activeDeadlineSeconds — 3600 (1h) for tile-import and valhalla-build; 900 for pbf-download
- restartPolicy: OnFailure across all Jobs
- Whether to add Job labels that match sidecar Deployments (informational only)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 24 CLI functions in `src/civpulse_geo/cli/__init__.py`:
  - `osm_download` (line 1215): Georgia PBF URL and path constants — `GEORGIA_PBF_URL`, `PBF_PATH`
  - `osm_import_tiles` (line 1303): uses `docker compose run --rm` with volume mount `{abs_pbf}:/data/region.osm.pbf:ro`
  - `osm_build_valhalla` (line 1326): exact env flag set
- Phase 24 Docker Compose at `docker-compose.yml` — service names, images, command args serve as reference for Job command/args fields
- Phase 31's `k8s/osm/base/osm-pvcs.yaml` — the 4 PVCs Jobs will mount (`osm-pbf-pvc`, `nominatim-data-pvc`, `osm-tile-data-pvc`, `valhalla-tiles-pvc`)

### Established Patterns
- Phase 24 documented "pitfalls": tile-server import needs `run --rm` (new container) not exec; PBF mounted at exact `/data/region.osm.pbf`; Valhalla needs all 4 build env flags
- Kustomize base+overlay with commonLabels `app.kubernetes.io/part-of: civpulse-osm` (from Phase 31)
- All-lowercase resource names with hyphen separators

### Integration Points
- Jobs mount `osm-pbf-pvc` at `/data/pbf` for download + shared read access
- tile-import mounts `osm-tile-data-pvc` + reads PBF from `osm-pbf-pvc`
- valhalla-build mounts `valhalla-tiles-pvc` + reads PBF from `osm-pbf-pvc`
- Nominatim auto-import reads PBF from `osm-pbf-pvc` — its Deployment must gain a second volumeMount for `osm-pbf-pvc` at a path the image's auto-import expects (check existing nominatim.yaml — Phase 31 moved it, might need update)

</code_context>

<specifics>
## Specific Ideas

- Georgia PBF URL (Phase 24 constant): `https://download.geofabrik.de/north-america/us/georgia-latest.osm.pbf`
- Image `mediagis/nominatim:5.2` expects PBF at `/nominatim/pbf/georgia-latest.osm.pbf` — the nominatim Deployment from Phase 28 already has `PBF_PATH=/nominatim/pbf/georgia-latest.osm.pbf` env var. Need to ensure `osm-pbf-pvc` is mounted at `/nominatim/pbf/` in nominatim Deployment.
- Check `k8s/osm/base/nominatim.yaml` — does it currently mount osm-pbf-pvc? If not, this phase adds that mount (part of JOB-02).

</specifics>

<deferred>
## Deferred Ideas

- CronJob for periodic re-downloads of fresh Georgia PBF — out of scope (current goal is first bootstrap)
- S3-based PBF archive for disaster recovery — Phase 34 DR concern
- Progress/telemetry from Jobs to Prometheus — out of scope for v1.5

</deferred>
