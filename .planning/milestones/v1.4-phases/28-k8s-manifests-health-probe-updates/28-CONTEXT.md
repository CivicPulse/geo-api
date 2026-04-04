# Phase 28: K8s Manifests & Health Probe Updates - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning
**Mode:** Smart discuss (batch-accepted recommended defaults)

<domain>
## Phase Boundary

Make the 3 OSM sidecar services (Nominatim, tile server, Valhalla) deployable via Kustomize to dev and prod clusters, and extend `GET /health/ready` so it reflects their reachability. This phase delivers new Kubernetes manifests (Deployment + Service + PVC for each sidecar) and updates the readiness probe to report sidecar status. It does NOT implement: HPA autoscaling, PodDisruptionBudgets, NetworkPolicies, Ingress/TLS termination, secrets management for tile-server/valhalla, or cluster-specific ArgoCD sync. ArgoCD sync to a real dev cluster is a human-verification item — Claude generates correct manifests but cannot validate against a live cluster.

</domain>

<decisions>
## Implementation Decisions

### Manifest Structure
- New files under `k8s/base/`: `nominatim.yaml`, `tile-server.yaml`, `valhalla.yaml`, `osm-pvcs.yaml`
- Each `*.yaml` contains a `Deployment` + `Service` (ClusterIP) for that sidecar
- `osm-pvcs.yaml` contains all 4 PersistentVolumeClaims (nominatim-data, osm-tile-data, osm-pbf, valhalla-tiles)
- Updated: `k8s/base/kustomization.yaml` — add new resources to the `resources:` list
- Overlay files (`k8s/overlays/dev/`, `k8s/overlays/prod/`) — no changes needed unless per-env patching is required

### Resource Limits (per sidecar)
- **nominatim**: requests `{memory: 4Gi, cpu: 500m}`, limits `{memory: 8Gi, cpu: 2000m}` — bundled PG + import workload
- **tile-server**: requests `{memory: 2Gi, cpu: 500m}`, limits `{memory: 4Gi, cpu: 1500m}` — rendering workload
- **valhalla**: requests `{memory: 2Gi, cpu: 500m}`, limits `{memory: 4Gi, cpu: 1500m}` — tile serving

### PVC Sizing (Georgia coverage)
- `nominatim-data-pvc`: 50Gi (Nominatim DB for Georgia extract ~10-15GB, growth headroom)
- `osm-tile-data-pvc`: 20Gi (tile-server internal PG + tile cache)
- `valhalla-tiles-pvc`: 10Gi (routing tiles)
- `osm-pbf-pvc`: 5Gi (shared, read-write for PBF downloads)
- Access mode: `ReadWriteOnce` for all (single-pod sidecars)
- StorageClass: omit (let each overlay specify, inherits cluster default)

### Service Definitions
- Port names match Docker Compose: `nominatim:8080`, `tile-server:8080`, `valhalla:8002`
- ClusterIP services named `nominatim`, `tile-server`, `valhalla` (match service names used by geo-api via `settings.osm_nominatim_url` etc.)

### Health Endpoint Updates
- Extend `GET /health/ready` response with optional keys (non-blocking):
  ```json
  {
    "status": "ready",
    "db": "connected",
    "geocoding_providers": 5,
    "validation_providers": 3,
    "sidecars": {
      "nominatim": "ready" | "unavailable" | "disabled",
      "tile_server": "ready" | "unavailable" | "disabled",
      "valhalla": "ready" | "unavailable" | "disabled"
    }
  }
  ```
- Sidecar checks are **non-blocking** (they don't fail the readiness probe — they're informational)
- `disabled` means the `*_enabled` setting is False; `unavailable` means probe failed at startup OR a live check times out
- Live check on each `/health/ready` call: HTTP probe with 1s timeout (budget: 3s total for 3 sidecars)

### Sidecar Probe Endpoints
- **nominatim**: `GET {osm_nominatim_url}/status` → expect 200
- **tile-server**: `GET {osm_tile_url}/tile/0/0/0.png` → expect 200 (only if imported) OR HEAD → accept any response that's reachable
- **valhalla**: `GET {osm_valhalla_url}/status` → expect 200 (only if tiles built)
- For tile-server/valhalla, also accept `status: "unavailable"` without failing readiness (they may not be imported yet)

### ArgoCD Sync (Human Verification)
- Claude generates Kubernetes manifests that conform to Kustomize structure
- `kubectl kustomize k8s/base/` can be run locally to validate YAML syntax and structure — this IS automated
- Actual cluster sync (`argocd app sync`, checking pod readiness in dev cluster) is a **human verification item** — documented in VERIFICATION.md

### Claude's Discretion
- Exact label structure for new manifests — match `commonLabels` from existing `k8s/base/kustomization.yaml` (`app.kubernetes.io/name`, `app.kubernetes.io/part-of`)
- Whether to include `imagePullPolicy: IfNotPresent` or rely on overlay defaults
- Security context (runAsNonRoot, etc.) — follow existing `k8s/base/deployment.yaml` conventions if present, else omit (images set their own)
- Whether to generate example ConfigMap for OSM service URLs — not needed since they're served via Service DNS

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `k8s/base/` — existing Kustomize base with Deployment + Service + PVC + ConfigMap for geo-api
- `k8s/base/kustomization.yaml` — existing base with `commonLabels` + `resources` list
- `k8s/overlays/dev/` + `k8s/overlays/prod/` — per-env overlays (no changes needed for this phase)
- `src/civpulse_geo/api/health.py` — existing `/health/ready` with DB + provider count checks
- `app.state.valhalla_enabled` (Phase 27), `app.state.providers` dict (contains nominatim post-Phase-26)
- httpx probe pattern from `_nominatim_reachable` + `_valhalla_reachable`

### Established Patterns
- Deployments in `k8s/base/` use `commonLabels` inherited from kustomization.yaml
- Resource limits pattern (see geo-api deployment): `requests` + `limits` with mem (Mi/Gi) + cpu (m)
- Readiness probe reports structured JSON with 503 on hard failures, 200 with info on soft degradation
- `@lru_cache(maxsize=1)` for env-var-derived constants

### Integration Points
- New: `k8s/base/nominatim.yaml`, `tile-server.yaml`, `valhalla.yaml`, `osm-pvcs.yaml`
- Modify: `k8s/base/kustomization.yaml` — append new resources
- Modify: `src/civpulse_geo/api/health.py` — extend `/health/ready` with `sidecars` block
- New tests: `tests/test_health_ready_sidecars.py` (mock sidecar HTTP responses, assert response shape)

</code_context>

<specifics>
## Specific Ideas

- `kubectl kustomize k8s/base/` MUST succeed without errors (automated check)
- `/health/ready` response MUST NOT fail (i.e., still returns 200) when sidecars are unavailable — they're informational
- Manifest service names MUST match `nominatim`, `tile-server`, `valhalla` (the hostnames referenced by existing settings)

</specifics>

<deferred>
## Deferred Ideas

- HorizontalPodAutoscaler for sidecars
- PodDisruptionBudgets
- NetworkPolicies (ingress/egress restrictions)
- Ingress/TLS termination for external access (if sidecars ever become externally accessible)
- Secrets management (though osm-postgres password was removed, future integrations may need secrets)
- Per-env (dev/prod) resource limit overrides via Kustomize patches
- Prometheus ServiceMonitor CRDs

</deferred>
