# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- ✅ **v1.1 Local Data Sources** — Phases 7-11 (shipped 2026-03-29)
- ✅ **v1.2 Cascading Address Resolution** — Phases 12-16 (shipped 2026-03-29)
- ✅ **v1.3 Production Readiness & Deployment** — Phases 17-23 (shipped 2026-04-03)
- ✅ **v1.4 Self-Hosted OSM Stack** — Phases 24-28 (shipped 2026-04-04)
- 🚧 **v1.5 Prod/Dev Bootstrap & K8s Jobs** — Phases 29-34 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-6) — SHIPPED 2026-03-19</summary>

- [x] **Phase 1: Foundation** — PostGIS schema, canonical key strategy, plugin contract, and project scaffolding (3/3 plans)
- [x] **Phase 2: Geocoding** — Multi-provider geocoding with cache, official record, and admin override (2/2 plans)
- [x] **Phase 3: Validation and Data Import** — USPS address validation and Bibb County GIS CLI import (3/3 plans)
- [x] **Phase 4: Batch and Hardening** — Batch endpoints, per-item error handling, and HTTP layer completion (2/2 plans)
- [x] **Phase 5: Fix Admin Override & Import Order** — Admin override table write fix and import-order documentation (1/1 plan)
- [x] **Phase 6: Documentation & Traceability Cleanup** — SUMMARY frontmatter and ROADMAP checkbox fixes (1/1 plan)

Full details archived in `milestones/v1.0-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.1 Local Data Sources (Phases 7-11) — SHIPPED 2026-03-29</summary>

- [x] **Phase 7: Pipeline Infrastructure** — Direct-return pipeline bypass, provider ABC extension, and staging table migrations (2/2 plans) — completed 2026-03-22
- [x] **Phase 8: OpenAddresses Provider** — OA geocoding and validation from .geojson.gz files via PostGIS staging table (2/2 plans) — completed 2026-03-22
- [x] **Phase 9: Tiger Provider** — Tiger geocoding and validation via PostGIS geocode() and normalize_address() SQL functions (2/2 plans) — completed 2026-03-24
- [x] **Phase 10: NAD Provider** — NAD geocoding and validation from 80M-row staging table with bulk COPY import (2/2 plans) — completed 2026-03-24
- [x] **Phase 11: Fix Batch Endpoint Local Provider Serialization** — Batch endpoints include local provider results in every response item (1/1 plan) — completed 2026-03-24

Full details archived in `milestones/v1.1-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.2 Cascading Address Resolution (Phases 12-16) — SHIPPED 2026-03-29</summary>

- [x] **Phase 12: Correctness Fixes and DB Prerequisites** — Fix 4 known provider defects and add GIN trigram indexes (2/2 plans) — completed 2026-03-29
- [x] **Phase 13: Spell Correction and Fuzzy/Phonetic Matching** — Offline spell correction and pg_trgm + Double Metaphone fallback (2/2 plans) — completed 2026-03-29
- [x] **Phase 14: Cascade Orchestrator and Consensus Scoring** — 6-stage cascade pipeline with cross-provider consensus and auto-set official (3/3 plans) — completed 2026-03-29
- [x] **Phase 15: LLM Sidecar** — Local Ollama qwen2.5:3b for address correction when deterministic stages fail (3/3 plans) — completed 2026-03-29
- [x] **Phase 16: Audit Gap Closure** — FuzzyMatcher startup wiring, legacy 5-tuple fix, Phase 13 verification (1/1 plan) — completed 2026-03-29

Full details archived in `milestones/v1.2-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.3 Production Readiness & Deployment (Phases 17-23) — SHIPPED 2026-04-03</summary>

- [x] **Phase 17: Tech Debt Resolution** — Resolve all 4 known runtime defects (2/2 plans) — completed 2026-03-29
- [x] **Phase 18: Code Review** — Parallel security, stability, performance audit (3/3 plans) — completed 2026-03-30
- [x] **Phase 19: Dockerfile and Database Provisioning** — Multi-stage Docker image + DB provisioning (2/2 plans) — completed 2026-03-30
- [x] **Phase 20: Health, Resilience, and K8s Manifests** — Health probes, graceful shutdown, K8s manifests (3/3 plans) — completed 2026-03-30
- [x] **Phase 21: CI/CD Pipeline** — GitHub Actions CI/CD with Trivy scan (2/2 plans) — completed 2026-03-30
- [x] **Phase 22: Observability** — Structured logging, Prometheus metrics, OTel traces (3/3 plans) — completed 2026-03-30
- [x] **Phase 23: E2E Testing, Load Baselines, and Final Validation** — Full E2E + load + observability + validation (9/9 plans) — completed 2026-04-03

Full details archived in `milestones/v1.3-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.4 Self-Hosted OSM Stack (Phases 24-28) — SHIPPED 2026-04-04</summary>

- [x] **Phase 24: OSM Data Pipeline & Docker Compose Sidecars** — Georgia PBF download, Nominatim/tile-server/Valhalla Docker Compose sidecars (each with bundled PG), and unified CLI pipeline command (5/5 plans)
- [x] **Phase 25: Tile Server & FastAPI Tile Proxy** — Streaming tile proxy endpoint with caching headers and upstream failure handling (2/2 plans)
- [x] **Phase 26: Nominatim Provider, Reverse Geocoding & POI Search** — 6th cascade provider + reverse geocode + POI search endpoints with conditional startup guard (5/5 plans)
- [x] **Phase 27: Valhalla Routing** — Walking and driving route endpoints backed by Valhalla sidecar (3/3 plans)
- [x] **Phase 28: K8s Manifests & Health Probe Updates** — Kustomize manifests for all sidecars + /health/ready sidecars block (2/2 plans)

Full details archived in `milestones/v1.4-ROADMAP.md`.

</details>

### 🚧 v1.5 Prod/Dev Bootstrap & K8s Jobs (In Progress)

**Milestone Goal:** Hands-off, GitOps-driven K8s deployment of v1.4's OSM stack as a shared service on `thor`, with data persisted on ZFS at `/hatch1/data/geo/` so imports survive cluster rebuilds.

**⚠ Execution order deviation (2026-04-05):** Phase 29's cutover revealed that `main`'s `k8s/base/` contains un-bootstrappable OSM sidecars (from Phase 28) — see `.planning/phases/29-argocd-branch-cutover/29-VERIFICATION.md`. Phases will execute in order **30 → 31 → 29 → 32 → 33 → 34** (numbers unchanged, execution reordered). Phase 29 resumes after Phase 31 removes the blocking sidecars from `k8s/base/`. Phase 29 Plan 01 (`docs/BRANCHING.md`) already complete.

- [~] **Phase 29: ArgoCD Branch Cutover** — Switch `geo-api-dev` + `geo-api-prod` ArgoCD apps from `phase-23-deploy-fix` to `main`, document branching strategy (GIT-01, GIT-02, GIT-03) — *Plan 01 complete, Plan 02 deferred until after Phase 31*
- [x] **Phase 30: ZFS-Backed Storage Infrastructure** — `zfs-local` StorageClass + static Local PVs at `/hatch1/data/geo/*` with nodeAffinity=thor + Retain reclaim (STORE-01..04) (completed 2026-04-05)
- [ ] **Phase 31: OSM Stack in civpulse-gis Namespace** — Move sidecars out of `k8s/base/`, new `k8s/osm/base/` + overlays, new `osm-stack` ArgoCD Application (OSM-01..04)
- [x] **Phase 32: Bootstrap Jobs for OSM Data** — Idempotent K8s Jobs for PBF download, Nominatim import, tile import, Valhalla build (JOB-01..05) (completed 2026-04-05)
- [ ] **Phase 33: Cross-Namespace geo-api Wiring** — Update dev + prod overlays to point at `nominatim.civpulse-gis.svc.cluster.local` etc., verify `/health/ready` sidecars block (WIRE-01..03)
- [ ] **Phase 34: Bootstrap Runbook + DR Docs + E2E** — Runbook for fresh cluster bring-up, ZFS snapshot DR procedure, end-to-end verification (DOC-01..03)

## Phase Details

### Phase 29: ArgoCD Branch Cutover
**Goal**: `geo-api-dev` and `geo-api-prod` ArgoCD Applications track `main` branch instead of `phase-23-deploy-fix`, and the deprecated branch is documented or removed.
**Depends on**: Phase 28 (v1.4 shipped on main)
**Requirements**: GIT-01, GIT-02, GIT-03
**Success Criteria** (what must be TRUE):
  1. `kubectl get application geo-api-dev -n argocd -o jsonpath='{.spec.source.targetRevision}'` returns `main`
  2. `kubectl get application geo-api-prod -n argocd -o jsonpath='{.spec.source.targetRevision}'` returns `main`
  3. Both ArgoCD apps show Sync Status = Synced and Health Status = Healthy after cutover
  4. Branching strategy documented in `docs/BRANCHING.md` or equivalent
**Plans**: TBD
**UI hint**: no

### Phase 30: ZFS-Backed Storage Infrastructure
**Goal**: Static Local PersistentVolumes backed by the ZFS dataset at `/hatch1/data/geo/*` on node `thor`, with `reclaimPolicy: Retain` so data survives PVC deletion and cluster rebuilds.
**Depends on**: Phase 29
**Requirements**: STORE-01, STORE-02, STORE-03, STORE-04
**Success Criteria** (what must be TRUE):
  1. StorageClass `zfs-local` exists with `volumeBindingMode: WaitForFirstConsumer` and no dynamic provisioner
  2. 4 static PersistentVolumes defined (osm-pbf-pv 5Gi, nominatim-data-pv 50Gi, osm-tile-data-pv 20Gi, valhalla-tiles-pv 10Gi) with nodeAffinity to `thor` and `reclaimPolicy: Retain`
  3. PV paths map to `/hatch1/data/geo/{pbf,nominatim,tile-server,valhalla}` respectively
  4. PVC manifests updated to bind to these PVs via `storageClassName: zfs-local`
  5. ZFS snapshot procedure documented
**Plans**: TBD
**UI hint**: no

### Phase 31: OSM Stack in civpulse-gis Namespace
**Goal**: OSM sidecars (Nominatim, tile-server, Valhalla) deploy into the `civpulse-gis` namespace as a shared service, managed by a new `osm-stack` ArgoCD Application.
**Depends on**: Phase 30
**Requirements**: OSM-01, OSM-02, OSM-03, OSM-04
**Success Criteria** (what must be TRUE):
  1. `k8s/osm/base/` directory exists with sidecar manifests (moved out of `k8s/base/`)
  2. `k8s/osm/overlays/` structure mirrors existing convention
  3. New ArgoCD Application `osm-stack` in `argocd` namespace, `spec.destination.namespace=civpulse-gis`, auto-sync + prune + selfHeal
  4. `kubectl get deploy -n civpulse-gis` shows nominatim, tile-server, valhalla Deployments synced by ArgoCD
  5. Resource limits match Phase 28 (nominatim 4Gi/8Gi, tile-server 2Gi/4Gi, valhalla 2Gi/4Gi)
**Plans**: 3 plans
- [x] 31-01-PLAN.md — Create k8s/osm/ tree (base + prod overlay + osm-stack ArgoCD Application)
- [x] 31-02-PLAN.md — Remove OSM sidecars from k8s/base/ (slim geo-api app)
- [ ] 31-03-PLAN.md — Apply osm-stack to live cluster + verify Deployments synced
**UI hint**: no

### Phase 32: Bootstrap Jobs for OSM Data
**Goal**: Idempotent K8s Jobs bootstrap OSM data (PBF download + all 3 imports) without manual `docker compose` invocations. Jobs skip work when data is already present.
**Depends on**: Phase 31
**Requirements**: JOB-01, JOB-02, JOB-03, JOB-04, JOB-05
**Success Criteria** (what must be TRUE):
  1. `pbf-download-job` Job manifest exists; on fresh PVC, downloads Georgia PBF; skips if PBF present
  2. Nominatim import happens via Job OR documented auto-import on Deployment first-startup (behavior is deterministic and idempotent)
  3. `tile-import-job` Job manifest exists; runs `docker compose run --rm tile-server import` equivalent; skips if `renderer` role + data present
  4. `valhalla-build-job` Job manifest exists; runs Valhalla tile build; skips if tiles present
  5. Jobs triggered by ArgoCD sync hooks OR documented `kubectl apply` workflow — never baked into Deployment startup
**Plans**: 2 plans
- [x] 32-01-PLAN.md — Create 3 Job manifests + wire kustomization + add PBF mount to nominatim Deployment
- [x] 32-02-PLAN.md — Write jobs/README.md (ordering, idempotency, manual apply workflow, runtimes, troubleshooting)
**UI hint**: no

### Phase 33: Cross-Namespace geo-api Wiring
**Goal**: geo-api-dev and geo-api-prod both reach the shared OSM stack in `civpulse-gis` via cluster DNS, and `/health/ready` reports all 3 sidecars as ready.
**Depends on**: Phase 31
**Requirements**: WIRE-01, WIRE-02, WIRE-03
**Success Criteria** (what must be TRUE):
  1. `k8s/overlays/dev/` + `k8s/overlays/prod/` set `OSM_NOMINATIM_URL=http://nominatim.civpulse-gis.svc.cluster.local:8080`, `OSM_TILE_URL=http://tile-server.civpulse-gis.svc.cluster.local:8080`, `OSM_VALHALLA_URL=http://valhalla.civpulse-gis.svc.cluster.local:8002`
  2. geo-api startup logs show all 3 `_*_reachable` probes return True in both dev and prod after OSM stack is populated
  3. `curl https://{dev,prod}/health/ready` returns `sidecars: {nominatim: ready, tile_server: ready, valhalla: ready}` after imports complete
**Plans**: TBD
**UI hint**: no

### Phase 34: Bootstrap Runbook + DR Docs + E2E
**Goal**: A fresh cluster can be bootstrapped end-to-end by following a documented runbook; ZFS snapshot DR procedure is validated; all v1.4 endpoints verified against the live K8s stack.
**Depends on**: Phase 33
**Requirements**: DOC-01, DOC-02, DOC-03
**Success Criteria** (what must be TRUE):
  1. `docs/BOOTSTRAP.md` walks through fresh-cluster setup: create ZFS dirs, apply PVs, trigger Jobs, verify health — each step verifiable
  2. `docs/DR.md` documents ZFS snapshot/restore procedure and has been run through at least once (snapshot taken + rollback tested on a non-critical dataset)
  3. E2E checklist confirms `/tiles`, `/geocode/reverse`, `/poi/search`, `/route` all return valid responses in both dev and prod environments
**Plans**: TBD
**UI hint**: no

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-6 | v1.0 | — | Complete | 2026-03-19 |
| 7-11 | v1.1 | — | Complete | 2026-03-29 |
| 12-16 | v1.2 | — | Complete | 2026-03-29 |
| 17-23 | v1.3 | — | Complete | 2026-04-03 |
| 24-28 | v1.4 | — | Complete | 2026-04-04 |
| 29 | v1.5 | 0/TBD | Not started | - |
| 30 | v1.5 | 3/3 | Complete   | 2026-04-05 |
| 31 | v1.5 | 2/3 | In Progress|  |
| 32 | v1.5 | 2/2 | Complete   | 2026-04-05 |
| 33 | v1.5 | 0/TBD | Not started | - |
| 34 | v1.5 | 0/TBD | Not started | - |

## Backlog

Unsequenced ideas captured for future planning. Promote with `/gsd-review-backlog`.

### Phase 999.1: Import-cache PV for non-OSM sources (BACKLOG)

**Goal:** [Captured for future planning] — Persist raw source archives for TIGER/Line, NAD r21, OpenAddresses (points + parcels) on a dedicated ZFS-backed cache PV at `/hatch1/geo/imports/` so re-running `geo-import` CLI commands doesn't require re-downloading from Census (rate-limited), re-sourcing DOT NAD ZIPs, or re-fetching from batch.openaddresses.io. Also audit which Postgres instance each loader targets to determine whether additional DB PVs are needed beyond `/hatch1/geo/nominatim`.

**Requirements:** TBD

**Context:** Surfaced during v1.5 → v1.6 transition while fixing the `hatch1/data/geo` → `hatch1/geo` path rename (commit `c17fa14` on `fix/zfs-dataset-path-hatch1-geo`). Four non-OSM data sources identified via audit:
- **TIGER/Line** (Census) — biggest operator-time win; `wget --mirror` hits 429s, ~20–40min babysitting per re-run
- **NAD r21** (US DOT) — no stable public URL, operator-supplied ZIP, pure institutional-knowledge preservation
- **OpenAddresses points** — manual fetch from `batch.openaddresses.io`
- **OpenAddresses parcels** — same, larger files (up to ~2GB/region)

All four land in Postgres tables, not filesystem. The cache PV is for the raw download artifacts (wget mirror `/gisdata/`, `NAD_r21_TXT.zip`, `.geojson.gz` files), separate from the Postgres DB persistence. Related: Phase 30 (ZFS-backed storage) established the pattern this extends.

**Out of scope:** automating downloads on a schedule (manual operator workflow is fine); replicating the cache off-thor (single-node failure domain acceptable, same as OSM data).

**Plans:** 0 plans

Plans:
- [ ] TBD (promote with `/gsd-review-backlog` when ready)
