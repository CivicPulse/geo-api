---
phase: 33-cross-namespace-geo-api-wiring
plan: 01
status: complete
completed: 2026-04-05
requirements:
  - WIRE-01
---

# Plan 33-01 Summary: Cross-Namespace URL Wiring

## What was built

Wired geo-api (in civpulse-dev and civpulse-prod) to the shared OSM stack in civpulse-gis via FQDN URLs:

1. **`k8s/base/configmap.yaml`** — added 3 entries:
   - `OSM_NOMINATIM_URL=http://nominatim.civpulse-gis.svc.cluster.local:8080`
   - `OSM_TILE_URL=http://tile-server.civpulse-gis.svc.cluster.local:8080`
   - `OSM_VALHALLA_URL=http://valhalla.civpulse-gis.svc.cluster.local:8002`

2. **`src/civpulse_geo/config.py`** — updated defaults on lines 54-56 to match FQDNs (from bare `nominatim:8080` → civpulse-gis FQDN)

3. **`src/civpulse_geo/providers/nominatim.py`** — docstring default updated for accuracy

## Why base ConfigMap

Both dev and prod reach the SAME shared OSM stack in civpulse-gis, so the URLs are identical. Setting in base eliminates duplication and ensures env parity.

## Verification

- `kubectl kustomize k8s/overlays/{dev,prod}/` both emit the 3 OSM_*_URL entries
- Settings load correctly in Python; defaults match env var values
- `ruff check` clean

## Requirements

- WIRE-01 ✅ (FQDN URLs wired into both overlays via base ConfigMap)
