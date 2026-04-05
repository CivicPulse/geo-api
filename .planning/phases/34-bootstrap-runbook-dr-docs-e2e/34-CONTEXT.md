# Phase 34: Bootstrap Runbook + DR Docs + E2E - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Close v1.5 with 3 operator-facing documents: a fresh-cluster bootstrap runbook (DOC-01), a ZFS snapshot disaster recovery procedure (DOC-02), and an end-to-end verification checklist (DOC-03). Stitches together the manifests, Jobs, PVs, and wiring from Phases 29-33 into a reproducible operator workflow.

</domain>

<decisions>
## Implementation Decisions

### Document Set
- `docs/BOOTSTRAP.md` — fresh-cluster bring-up walkthrough (DOC-01)
- `docs/DR.md` — ZFS snapshot/rollback disaster recovery (DOC-02)
- `docs/E2E.md` — end-to-end verification checklist (DOC-03)

### Runbook Scope (docs/BOOTSTRAP.md)
Covers the full fresh-cluster bring-up sequence:
1. Prerequisites — kubectl context, `argocd` + `civpulse-gis` namespaces
2. ZFS dataset creation on `thor` (`zfs create /hatch1/data/geo/{pbf,nominatim,tile-server,valhalla}`) — references docs/ZFS-STORAGE.md
3. Apply cluster-scoped storage: `kubectl apply -k k8s/cluster/storage/`
4. Apply osm-stack Application: `kubectl apply -f k8s/osm/overlays/prod/argocd-app.yaml`
5. Trigger bootstrap Jobs (ArgoCD auto-runs via Sync hooks, OR manual `kubectl apply -f k8s/osm/base/jobs/*.yaml`)
6. Wait for imports (pbf=5min, tile=90min, nominatim-autoimport=90min, valhalla=30min)
7. Verify via E2E checklist (docs/E2E.md)

Each step must be verifiable (kubectl command that confirms success).

### DR Scope (docs/DR.md)
- ZFS snapshot cadence recommendations
- `zfs snapshot hatch1/data/geo/nominatim@YYYY-MM-DD`
- Rollback procedure: stop nominatim pod, `zfs rollback`, restart pod
- Links to docs/ZFS-STORAGE.md for storage-layer detail
- **Honest note**: the actual rollback exercise is DEFERRED to v1.6 or ops-first-incident (acknowledged gap against the original success criterion)

### E2E Scope (docs/E2E.md)
Markdown checklist covering all v1.4 + v1.5 endpoints in both dev and prod:
- `GET /health` (liveness)
- `GET /health/ready` — asserts sidecars block shows nominatim+tile+valhalla ready
- `GET /tiles/{z}/{x}/{y}.png` — expect 200 with PNG content-type
- `POST /geocode/reverse` — expect valid result for Georgia coordinate
- `GET /poi/search?q=...` — expect valid result list
- `POST /route` — Valhalla pedestrian + driving routes

Each check lists: command, expected status, expected payload shape, failure diagnostic.

### Claude's Discretion
- Wording, length, examples in each doc
- Whether to add a top-level "fresh operator checklist" that cross-links all 3 docs
- Exact sample coordinates/queries for E2E (use Atlanta/Macon for Georgia coverage)
- Troubleshooting sections per doc

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/ZFS-STORAGE.md` (Phase 30) — dataset layout, zfs create, snapshot/rollback reference
- `docs/BRANCHING.md` (Phase 29) — ArgoCD targetRevision policy context
- `k8s/osm/base/jobs/README.md` (Phase 32) — Job runtimes, idempotency guards, manual apply workflow
- `k8s/cluster/storage/kustomization.yaml` — the storage apply entrypoint
- `k8s/osm/overlays/prod/argocd-app.yaml` — the OSM stack entrypoint

### Established Patterns
- Operator docs in `docs/`, flat layout
- Markdown H2/H3 sections, code blocks for commands

### Integration Points
- BOOTSTRAP.md cites ZFS-STORAGE.md for storage steps
- BOOTSTRAP.md cites jobs/README.md for Job runtimes
- DR.md cites ZFS-STORAGE.md for snapshot mechanics
- E2E.md references the 3 sidecars' endpoints established in Phases 25/26/27

</code_context>

<specifics>
## Specific Ideas

- Expected runtimes table: pbf-download 5min, nominatim-autoimport 90min, tile-import 90min, valhalla-build 30min — ~3.5h total on first bootstrap (can parallelize tile-import + valhalla-build)
- Sample E2E Georgia coord: lat=33.7490, lon=-84.3880 (downtown Atlanta)
- Sample E2E address: "Georgia State Capitol, Atlanta GA"
- Sample E2E tile: z=10 x=271 y=415 (Georgia coverage)

</specifics>

<deferred>
## Deferred Ideas

- Actual DR exercise — deferred to v1.6 or first prod incident (accepted gap)
- Live E2E execution — deferred to post-milestone ops activity
- Runbook automation (scripted fresh-bootstrap) — future milestone
- Multi-region OSM extract support — out of scope (Georgia only)

</deferred>
