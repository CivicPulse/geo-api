# Requirements: v1.5 Prod/Dev Bootstrap & K8s Jobs

**Milestone goal:** Hands-off, GitOps-driven K8s deployment of v1.4's OSM stack as a shared service on node `thor`, with data persisted on ZFS at `/hatch1/data/geo/` so imports survive cluster rebuilds.

---

## Active Requirements

### Storage (ZFS-backed static Local PVs)

- [x] **STORE-01**: OSM data persists on ZFS dataset `/hatch1/data/geo/*` on node `thor` (survives cluster rebuilds)
- [x] **STORE-02**: Static Local PersistentVolumes with `nodeAffinity: thor` and `reclaimPolicy: Retain` for PBF, Nominatim, tile-server, and Valhalla data
- [x] **STORE-03**: `zfs-local` StorageClass defined with `volumeBindingMode: WaitForFirstConsumer` and no dynamic provisioner (static binding only)
- [x] **STORE-04**: ZFS snapshot procedure documented for disaster recovery of imported OSM data

### OSM Stack Deployment

- [x] **OSM-01**: OSM sidecars (Nominatim, tile-server, Valhalla) deployed into `civpulse-gis` namespace (shared across dev/prod)
- [x] **OSM-02**: New ArgoCD Application `osm-stack` in `argocd` namespace syncs OSM sidecars + Jobs from git (auto-sync + prune + selfHeal enabled)
- [x] **OSM-03**: OSM stack manifests live under `k8s/osm/base/` with overlays structure matching existing convention
- [ ] **OSM-04**: Sidecar Deployments use resource limits from Phase 28 (nominatim 4Gi/8Gi, tile-server 2Gi/4Gi, valhalla 2Gi/4Gi)

### Bootstrap Jobs

- [x] **JOB-01**: Idempotent K8s Job downloads Georgia OSM PBF extract to `osm-pbf-pvc` (skips if PBF already present)
- [x] **JOB-02**: Idempotent K8s Job imports PBF into Nominatim (or configures Deployment to auto-import on first startup with empty volume)
- [x] **JOB-03**: Idempotent K8s Job imports PBF into tile-server internal PG (skips if `renderer` role + data present)
- [x] **JOB-04**: Idempotent K8s Job builds Valhalla routing tiles (skips if tiles present; re-runs when PBF is newer)
- [x] **JOB-05**: Bootstrap Jobs are triggered by ArgoCD sync hooks OR manually via `kubectl apply` — not baked into Deployment startup

### Cross-Namespace Wiring

- [ ] **WIRE-01**: geo-api dev + prod overlays configure `osm_nominatim_url=http://nominatim.civpulse-gis.svc.cluster.local:8080` (+ tile_url, valhalla_url)
- [ ] **WIRE-02**: `_nominatim_reachable`, `_tile_server_reachable`, `_valhalla_reachable` probes succeed against cross-namespace services during startup in both dev and prod
- [ ] **WIRE-03**: `/health/ready` sidecars block reports `ready` for all 3 sidecars in dev and prod after OSM stack is populated

### GitOps Cleanup

- [ ] **GIT-01**: `geo-api-dev` and `geo-api-prod` ArgoCD Applications track `main` branch (not `phase-23-deploy-fix`)
- [ ] **GIT-02**: `phase-23-deploy-fix` branch removed or documented as deprecated after cutover verified
- [ ] **GIT-03**: Branching strategy documented (trunk-based from `main`, feature branches for in-progress work, no long-lived deploy branches)

### Bootstrap & Documentation

- [ ] **DOC-01**: Bootstrap runbook — how to stand up the OSM stack on a fresh cluster from scratch (PV creation, Job trigger, verification steps)
- [ ] **DOC-02**: Disaster recovery runbook — how to restore OSM data from ZFS snapshot after data loss
- [ ] **DOC-03**: End-to-end verification checklist — post-deploy checks that confirm geo-api endpoints work against the OSM stack in both dev and prod

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STORE-01..04 | Phase 30 | Not started |
| OSM-01..04 | Phase 31 | Not started |
| JOB-01..05 | Phase 32 | Not started |
| WIRE-01..03 | Phase 33 | Not started |
| GIT-01..03 | Phase 29 | Not started |
| DOC-01..03 | Phase 34 | Not started |

---

## Out of Scope (deferred)

- Pinned semver image tags (`:latest` → `:v1.4.0`) — CI/CD refactor, future milestone
- Frontend integration of `/tiles`, `/route`, `/poi/search` endpoints — consumer apps (voter-web, run-web)
- Rate limiting, CDN edge caching, HPA autoscaling — operational hardening
- Per-env separate OSM stacks (accepted Option A: shared stack)
- Tile vector format (MVT/protobuf) — raster only for v1.5
