# Phase 31: OSM Stack in civpulse-gis Namespace - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Relocate the OSM sidecars (nominatim, tile-server, valhalla) and their PVCs out of `k8s/base/` into a new top-level `k8s/osm/` tree (base + single prod overlay), with a new `osm-stack` ArgoCD Application targeting the shared `civpulse-gis` namespace. Delete the sidecar manifests from `k8s/base/` so geo-api's overlays produce clean, self-contained apps. Unblocks Phase 29's cutover.

</domain>

<decisions>
## Implementation Decisions

### Directory Structure
- New: `k8s/osm/base/` — nominatim.yaml, tile-server.yaml, valhalla.yaml, osm-pvcs.yaml, namespace.yaml, kustomization.yaml
- New: `k8s/osm/overlays/prod/` — single shared-instance overlay with kustomization.yaml + argocd-app.yaml (no dev overlay since stack is shared)
- Moved manifests retain Phase 28's structure (Deployment + Service in one file per sidecar, PVCs in osm-pvcs.yaml)
- PVCs keep `storageClassName: zfs-local` from Phase 30

### Namespace Management
- `k8s/osm/base/namespace.yaml` commits the `civpulse-gis` Namespace resource
- ArgoCD Application uses `syncOption: CreateNamespace=true` + `ServerSideApply=true`
- ensures clean bootstrap from empty cluster

### ArgoCD Application
- Location: `k8s/osm/overlays/prod/argocd-app.yaml` (mirrors geo-api pattern)
- Name: `osm-stack`, namespace: `argocd`
- `spec.destination.namespace: civpulse-gis`
- `spec.source.targetRevision: main` (per BRANCHING.md policy from Phase 29)
- `spec.source.path: k8s/osm/overlays/prod`
- `syncPolicy: automated + prune + selfHeal`
- `syncOptions: [CreateNamespace=true, ServerSideApply=true]`

### k8s/base/ Cleanup
- Delete from `k8s/base/`: nominatim.yaml, tile-server.yaml, valhalla.yaml, osm-pvcs.yaml
- Update `k8s/base/kustomization.yaml` resources list to remove the 4 files
- Rationale: these sidecars don't belong in the geo-api app — they're a shared service. Once removed, geo-api overlays only manage geo-api Deployment + Service + ConfigMap + ollama PVC. This is precisely what unblocks Phase 29.

### Resource Limits
- Preserve Phase 28 values exactly: nominatim 4Gi/8Gi (500m/2000m), tile-server 2Gi/4Gi (250m/1000m), valhalla 2Gi/4Gi (250m/1000m)
- Do not re-tune limits in this phase — that's a DOC-01 runbook concern

### Claude's Discretion
- commonLabels on `k8s/osm/base/kustomization.yaml` — use `app.kubernetes.io/part-of: civpulse-osm` (parallel to geo-api's `civpulse-geo`)
- Whether to add a small README inside `k8s/osm/` explaining the separation
- Exact order of kubectl apply steps if run manually (doesn't matter — namespace first, then rest)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `k8s/base/nominatim.yaml`, `tile-server.yaml`, `valhalla.yaml`, `osm-pvcs.yaml` — move verbatim to `k8s/osm/base/` (adjust kustomization.yaml references only)
- `k8s/overlays/dev/argocd-app.yaml` — template for new osm-stack ArgoCD Application

### Established Patterns
- One Deployment + Service per sidecar file
- `commonLabels: app.kubernetes.io/part-of: <group>` at kustomization level
- Explicit `app.kubernetes.io/name: <sidecar>` on each Deployment selector to avoid selector collision (Phase 28 decision)
- ArgoCD Applications use `automated.prune: true, selfHeal: true`

### Integration Points
- Phase 33 will update `k8s/overlays/{dev,prod}/configmap-patch.yaml` to point geo-api at `http://{nominatim,tile-server,valhalla}.civpulse-gis.svc.cluster.local`
- Phase 32's bootstrap Jobs will live alongside sidecars in `k8s/osm/base/jobs/` (bootstrap concern, not this phase)
- Phase 30's PVs (static Local PVs with nodeAffinity=thor) will bind to these PVCs when a pod in `civpulse-gis` namespace schedules on `thor`

</code_context>

<specifics>
## Specific Ideas

- Single `prod` overlay (not dev+prod) since `civpulse-gis` is one shared namespace
- `CreateNamespace=true` so ArgoCD manages the namespace declaratively
- `ServerSideApply=true` for better handling of third-party CRDs/large resources (best practice for modern ArgoCD)

</specifics>

<deferred>
## Deferred Ideas

- Bootstrap Jobs (PBF download, imports) — Phase 32
- geo-api cross-namespace wiring — Phase 33
- NetworkPolicy to restrict who can reach civpulse-gis services — out of scope for v1.5
- Service mesh/authz between namespaces — out of scope for v1.5

</deferred>
