---
status: passed
phase: 32-bootstrap-jobs-for-osm-data
verified: 2026-04-05
must_haves_verified: 5/5
deferred: live_apply_jobs_long_runtime
---

# Phase 32 Verification — PASSED (disk-only)

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | pbf-download-job exists, skips when PBF present | `k8s/osm/base/jobs/pbf-download-job.yaml` — shell-guard on file size >100MB |
| 2 | Nominatim import deterministic+idempotent | nominatim Deployment now mounts `osm-pbf-pvc` at `/nominatim/pbf/`; image auto-imports on first PG-volume-empty startup (Phase 24 documented behavior) |
| 3 | tile-import-job exists, skips when renderer role present | `k8s/osm/base/jobs/tile-import-job.yaml` — shell-guard checks renderer role |
| 4 | valhalla-build-job exists, skips when tiles present | `k8s/osm/base/jobs/valhalla-build-job.yaml` — shell-guard on non-empty tiles dir |
| 5 | Triggered by ArgoCD sync hooks OR documented kubectl apply | All 3 Jobs carry `argocd.argoproj.io/hook: Sync` + `hook-delete-policy: BeforeHookCreation`; operator README (`k8s/osm/base/jobs/README.md`) documents both paths |

## Validation

- `kubectl apply --dry-run=client` passes on all 3 Job manifests
- `kubectl kustomize k8s/osm/base/` renders Jobs + updated nominatim Deployment cleanly
- `k8s/osm/base/jobs/README.md` covers ordering, idempotency, runtimes, troubleshooting

## Deferred — live apply

Not run in this phase — bootstrap Jobs take substantial wall time (pbf-download ~5min, tile-import ~90min, valhalla-build ~30min, nominatim auto-import ~90min). ArgoCD will trigger these as sync hooks on next osm-stack sync. Operator runs a sync at their discretion. Phase 34 documents the end-to-end bootstrap runbook.

## Requirements satisfied

- JOB-01 ✅ pbf-download Job with idempotency guard
- JOB-02 ✅ Nominatim auto-import via Deployment (PBF mount added)
- JOB-03 ✅ tile-import Job with idempotency guard
- JOB-04 ✅ valhalla-build Job with idempotency guard
- JOB-05 ✅ ArgoCD sync hooks + documented kubectl apply workflow
