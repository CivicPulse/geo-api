---
phase: 31-osm-stack-civpulse-gis-namespace
plan: 02
subsystem: k8s
tags: [kustomize, k8s, refactor, osm-stack]
requires: ["31-01"]
provides:
  - "k8s/base/ slimmed to geo-api resources only"
  - "k8s/base/kustomization.yaml referencing 4 geo-api files only"
affects:
  - "k8s/overlays/dev/"
  - "k8s/overlays/prod/"
tech-stack:
  added: []
  patterns: ["separation of concerns: geo-api base vs osm stack"]
key-files:
  created: []
  modified:
    - k8s/base/kustomization.yaml
  removed:
    - k8s/base/nominatim.yaml
    - k8s/base/tile-server.yaml
    - k8s/base/valhalla.yaml
    - k8s/base/osm-pvcs.yaml
decisions:
  - "Trimmed kustomization.yaml comment to reflect geo-api-only scope"
metrics:
  duration: "~1m"
  completed: "2026-04-04"
---

# Phase 31 Plan 02: Remove OSM Sidecars from geo-api Base Summary

Removed nominatim/tile-server/valhalla/osm-pvcs manifests and references from
`k8s/base/` so the geo-api-dev and geo-api-prod ArgoCD apps no longer manage
OSM resources that now live under `k8s/osm/` (Plan 01).

## What Changed

- Deleted (via `git rm`): `k8s/base/nominatim.yaml`, `tile-server.yaml`,
  `valhalla.yaml`, `osm-pvcs.yaml`.
- Updated `k8s/base/kustomization.yaml`: resources list shrunk from 8 to 4
  entries (`deployment.yaml`, `service.yaml`, `configmap.yaml`, `pvc.yaml`).
- Trimmed the explanatory comment to reflect geo-api-only scope while
  preserving the `commonLabels` warning about `app.kubernetes.io/name`.
- `commonLabels.app.kubernetes.io/part-of: civpulse-geo` preserved.

## Precondition Check

Waited 20s for Plan 01 to land `k8s/osm/base/` + `k8s/osm/overlays/prod/`,
then verified:
- All 4 target files exist in `k8s/osm/base/`.
- `kubectl kustomize k8s/osm/overlays/prod/` builds cleanly.

Only then removed the originals from `k8s/base/`.

## Verification

- `kubectl kustomize k8s/overlays/dev/` → builds cleanly, names:
  `geo-api`, `geo-api-config`, `geo-api-dev`, `ollama-pvc`.
- `kubectl kustomize k8s/overlays/prod/` → builds cleanly, names:
  `geo-api`, `geo-api-config`, `geo-api-prod`, `ollama-pvc`.
- No `nominatim`, `tile-server`, `valhalla`, or OSM PVC names in either
  overlay output.

## Deviations from Plan

None - plan executed exactly as written.

## Commits

- `3093517` refactor(31-02): remove OSM sidecars from geo-api k8s base

## Self-Check: PASSED

- FOUND: k8s/base/kustomization.yaml (4 resources only)
- MISSING (expected): k8s/base/nominatim.yaml, tile-server.yaml, valhalla.yaml, osm-pvcs.yaml
- FOUND commit: 3093517
