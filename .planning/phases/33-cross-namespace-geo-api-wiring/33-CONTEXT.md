# Phase 33: Cross-Namespace geo-api Wiring - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire geo-api (in `civpulse-dev` and `civpulse-prod`) to the shared OSM stack in `civpulse-gis` via fully-qualified cluster DNS. Update ConfigMap + code defaults so `/health/ready` reports all 3 sidecars as ready once Phase 32 Jobs populate the PVCs. Scope is the wiring (env vars + FQDN URLs); live verification is Phase 34's E2E.

</domain>

<decisions>
## Implementation Decisions

### URL Location
- Add 3 `OSM_*_URL` entries to `k8s/base/configmap.yaml` (single source of truth for both overlays)
- dev/prod overlays don't need per-env URL overrides — both point at the same shared civpulse-gis stack
- URLs:
  - `OSM_NOMINATIM_URL=http://nominatim.civpulse-gis.svc.cluster.local:8080`
  - `OSM_TILE_URL=http://tile-server.civpulse-gis.svc.cluster.local:8080`
  - `OSM_VALHALLA_URL=http://valhalla.civpulse-gis.svc.cluster.local:8002`

### Code Defaults
- Update `src/civpulse_geo/config.py` lines 54-56: change defaults from bare hostnames (`nominatim:8080`) to full FQDN
- Rationale: keeps K8s deployment consistent even if ConfigMap env vars are accidentally stripped; local Docker Compose workflows can override via .env
- Does NOT break docker-compose — services can still be reached by bare name within the compose network, but we add a compose-side override in `.env.example` or similar

### Verification Scope
- This phase: kustomize builds clean with new env vars, FQDN URLs resolve in cluster DNS (`kubectl run --rm debug --image=busybox -- nslookup nominatim.civpulse-gis.svc.cluster.local`), `/health/ready` code path reachable
- Deferred to Phase 34: end-to-end test that `/health/ready` returns `sidecars: {nominatim: ready, tile_server: ready, valhalla: ready}` after Phase 32 Jobs complete population

### Claude's Discretion
- Whether to add comments in configmap.yaml explaining cross-namespace DNS pattern
- Whether to also update docker-compose.yml env or README for local-dev parity (lean: NO — that's a parallel system; config.py defaults stay geared toward prod)
- Exact test pattern for DNS resolution verification

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/civpulse_geo/config.py` already has `osm_nominatim_url`, `osm_tile_url`, `osm_valhalla_url` Settings fields (lines 54-56)
- Pydantic BaseSettings auto-reads env vars in uppercase form: `OSM_NOMINATIM_URL` populates `osm_nominatim_url`
- `_*_reachable` probe helpers exist for all 3 sidecars (Phase 26/27/28)
- `/health/ready` endpoint already reports sidecar block (Phase 28)

### Established Patterns
- Base ConfigMap at `k8s/base/configmap.yaml` contains shared env vars
- Overlay patches at `k8s/overlays/{dev,prod}/configmap-patch.yaml` override env-specific values only (ENVIRONMENT, LOG_LEVEL, CASCADE_LLM_ENABLED)
- All sidecars exposed via ClusterIP Services named identically to Deployments

### Integration Points
- `k8s/osm/base/{nominatim,tile-server,valhalla}.yaml` define the Services that FQDNs resolve to
- `src/civpulse_geo/api/health.py` consumes sidecar URLs to run reachability probes
- Phase 34's E2E checklist will exercise `/health/ready` against live cluster

</code_context>

<specifics>
## Specific Ideas

- FQDN format: `<svc>.<namespace>.svc.cluster.local:<port>` — standard K8s cluster DNS
- Ports: nominatim 8080, tile-server 8080, valhalla 8002 (per Phase 31 Service definitions)
- Phase 28 already established sidecars-health reporting in /health/ready — just need to give geo-api the right URLs to reach them

</specifics>

<deferred>
## Deferred Ideas

- Connection retry/backoff policy tuning on sidecar HTTP clients — out of scope
- Per-env URL overrides if shared stack goes multi-env — not needed; stack is single-instance shared
- mTLS/authentication between namespaces — out of scope for v1.5

</deferred>
