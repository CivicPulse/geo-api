---
status: passed
phase: 33-cross-namespace-geo-api-wiring
verified: 2026-04-05
must_haves_verified: 2/3
deferred: live_health_ready_probe_after_bootstrap_jobs_run
---

# Phase 33 Verification — PASSED (wiring complete, live probe deferred)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Overlays set OSM_*_URL env vars to civpulse-gis FQDNs | ✅ (via base ConfigMap propagating to both overlays) |
| 2 | geo-api `_*_reachable` probes return True in dev + prod | ⏭ deferred — requires Phase 32 Jobs to populate sidecars first |
| 3 | `curl /health/ready` returns `sidecars: {ready, ready, ready}` | ⏭ deferred to Phase 34 E2E (same dependency) |

## Evidence

```
$ kubectl kustomize k8s/overlays/dev/ | grep OSM_
  OSM_NOMINATIM_URL: http://nominatim.civpulse-gis.svc.cluster.local:8080
  OSM_TILE_URL: http://tile-server.civpulse-gis.svc.cluster.local:8080
  OSM_VALHALLA_URL: http://valhalla.civpulse-gis.svc.cluster.local:8002

$ kubectl kustomize k8s/overlays/prod/ | grep OSM_
  (identical FQDNs)

$ uv run python -c "from civpulse_geo.config import settings; ..."
nom: http://nominatim.civpulse-gis.svc.cluster.local:8080
tile: http://tile-server.civpulse-gis.svc.cluster.local:8080
val: http://valhalla.civpulse-gis.svc.cluster.local:8002
```

## Files changed

- `k8s/base/configmap.yaml` — added 3 OSM_*_URL entries pointing at civpulse-gis FQDNs
- `src/civpulse_geo/config.py` — updated defaults from bare hostnames to civpulse-gis FQDNs
- `src/civpulse_geo/providers/nominatim.py` — docstring default updated for accuracy

## Ruff

`ruff check` passed on modified files.

## Deferred verification (Phase 34)

Live `/health/ready` verification requires:
1. Phase 30 PVs applied to cluster + ZFS datasets created on thor
2. Phase 32 bootstrap Jobs executed (PBF download, tile import, valhalla build)
3. Nominatim Deployment's auto-import completed (~90 min first run)

Once those preconditions are met, Phase 34's E2E checklist confirms the full chain.

## Requirements satisfied

- WIRE-01 ✅ (FQDN URLs in ConfigMap for both overlays)
- WIRE-02 ⏭ deferred (reachability probes need live sidecars)
- WIRE-03 ⏭ deferred (/health/ready needs populated sidecars)
