---
phase: 32-bootstrap-jobs-for-osm-data
plan: 02
subsystem: k8s-docs
tags: [k8s, osm, docs, jobs, operator]
requires: [32-01]
provides: [operator-runbook-osm-bootstrap]
affects: [k8s/osm/base/jobs/]
tech-stack:
  added: []
  patterns: [operator-runbook, kubectl-apply-workflow]
key-files:
  created:
    - k8s/osm/base/jobs/README.md
  modified: []
decisions:
  - "README lives alongside Job manifests in k8s/osm/base/jobs/ for co-location with the resources it documents"
  - "Manual kubectl apply workflow uses `wait --for=condition=complete` on pbf-download-job to gate dependent Jobs, mirroring ArgoCD hook ordering"
metrics:
  duration: 2min
  tasks: 1
  files: 1
  completed: 2026-04-05
---

# Phase 32 Plan 02: OSM Bootstrap Jobs Operator README Summary

One-liner: Operator-facing runbook documenting Job ordering DAG, idempotency guards, manual kubectl apply workflow, runtimes, and troubleshooting for OSM bootstrap Jobs.

## What Was Built

Created `k8s/osm/base/jobs/README.md` (100 lines) with seven sections:

- **Overview** — namespace, node pinning, idempotency, ArgoCD hook trigger
- **Job Ordering** — DAG: pbf-download root -> tile-import + valhalla-build + nominatim auto-import
- **Idempotency Guards** — table of skip conditions and markers per Job
- **Manual kubectl apply Workflow** — gated sequence with `wait --for=condition=complete`
- **Expected Runtimes** — pbf ~5m / tile-import ~90m / valhalla ~30m / nominatim ~90m, with activeDeadlineSeconds
- **Troubleshooting** — 5 common failure modes (HTTP 4xx, stale pg lock, OOMKilled, missing PBF mount, Pending scheduling)
- **Re-running After Data Corruption** — scale-to-zero + PVC delete + re-apply sequence

## Verification Results

- `test -f k8s/osm/base/jobs/README.md` — PASSED
- `wc -l` >= 80 — PASSED (100 lines)
- All six required sections present — PASSED
- Runtime table covers all 4 workloads — PASSED
- Namespace `civpulse-gis` used consistently in manual workflow — PASSED

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created missing k8s/osm/base/jobs/ directory**
- **Found during:** Task 1
- **Issue:** Plan 32-01 (which creates Job YAML manifests in this directory) has not yet been executed, so `k8s/osm/base/jobs/` did not exist.
- **Fix:** Created directory via `mkdir -p` before writing README.md. The README documents manifests that Plan 32-01 will create; forward references are intentional per plan objective.
- **Files modified:** k8s/osm/base/jobs/ (new directory)
- **Commit:** 5ecdea4

## Commits

- 5ecdea4: docs(32-02): add OSM bootstrap jobs operator README

## Requirements Satisfied

- **JOB-05**: Documented kubectl apply workflow exists at k8s/osm/base/jobs/README.md

## Self-Check: PASSED

- FOUND: k8s/osm/base/jobs/README.md
- FOUND: 5ecdea4
