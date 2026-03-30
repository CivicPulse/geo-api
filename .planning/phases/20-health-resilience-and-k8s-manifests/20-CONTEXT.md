# Phase 20: Health, Resilience, and K8s Manifests - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Deploy geo-api to both K8s environments (civpulse-dev, civpulse-prod) with health probes, Ollama sidecar, graceful shutdown, init containers for data initialization, and ArgoCD management. Covers RESIL-01 through RESIL-04 and DEPLOY-02 through DEPLOY-07.

</domain>

<decisions>
## Implementation Decisions

### Health Endpoints (RESIL-01, RESIL-02)
- **D-01:** Add `/health/live` — process-only liveness probe, no DB dependency. Returns 200 immediately. Used by K8s liveness probe.
- **D-02:** Add `/health/ready` — readiness probe checks DB connectivity AND provider count threshold: at least 2 geocoding providers AND at least 2 validation providers registered. Returns 200 only when all checks pass.
- **D-03:** Keep existing `/health` endpoint as-is for backward compatibility and human inspection (shows version, commit, DB status). New probe endpoints are separate.

### K8s Manifest Organization (DEPLOY-02, DEPLOY-03, DEPLOY-05)
- **D-04:** Kustomize base + overlays structure. `k8s/base/` has shared Deployment, Service, ConfigMap. `k8s/overlays/dev/` and `k8s/overlays/prod/` patch env-specific values (namespace, image tag, secrets, resource limits). ArgoCD Application CRs point to overlay paths.
- **D-05:** Remove existing standalone Ollama manifests (`k8s/ollama-deployment.yaml`, `k8s/ollama-service.yaml`, `k8s/ollama-pvc.yaml`) after Ollama is merged as sidecar into the geo-api Deployment.
- **D-06:** Secrets as placeholder YAML with CHANGEME values committed to repo. Real credentials applied manually via `kubectl create secret`. No SealedSecrets or external secrets operator.

### Ollama Sidecar (DEPLOY-02)
- **D-07:** PVC (10Gi ReadWriteOnce) for Ollama model persistence. Model-pull init container runs only when PVC is empty. Survives pod restarts without re-downloading 2GB model. PVC definition moves to base/ kustomization.
- **D-08:** K8s 1.29+ native sidecar (`initContainers` with `restartPolicy: Always`) for Ollama. Guarantees Ollama is running before geo-api main container starts. Must verify k3s version >= 1.29 during implementation.
- **D-09:** Ollama sidecar config: `ollama_url` set to `http://localhost:11434` in ConfigMap (shares Pod network). `cascade_llm_enabled=true` in production ConfigMap.

### Graceful Shutdown (RESIL-03)
- **D-10:** Belt and suspenders — primary: `await engine.dispose()` in lifespan shutdown block (after yield) for asyncpg pool cleanup. Safety net: SIGTERM signal handler that also triggers pool disposal.
- **D-11:** 10-second preStop hook sleep for graceful drain. `terminationGracePeriodSeconds=30` leaves 20s for in-flight requests to complete after drain.
- **D-12:** Shutdown sequence: preStop sleep (10s) → SIGTERM → uvicorn drain → lifespan shutdown (close httpx client, dispose async engine, dispose sync engine) → pod terminates.

### Init Containers (DEPLOY-04, RESIL-04)
- **D-13:** Two separate init containers, both using the geo-api image:
  1. `alembic-migrate` — runs `alembic upgrade head` against target database
  2. `spell-rebuild` — runs spell dictionary rebuild CLI command
- **D-14:** Init containers receive DB credentials via envFrom (ConfigMap + Secret refs). Clear separation of concerns — independent failure and retry per container.

### Claude's Discretion
- Resource requests/limits for geo-api and Ollama sidecar containers
- Exact Kustomize patch strategy (strategic merge vs JSON patch)
- ConfigMap key naming conventions
- ArgoCD Application CR sync policy and auto-heal settings
- Whether to add a DB-wait init container before alembic-migrate or rely on alembic's built-in retry

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — RESIL-01, RESIL-02, RESIL-03, RESIL-04, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05, DEPLOY-07 acceptance criteria
- `.planning/ROADMAP.md` §Phase 20 — Success criteria (5 items: health probes, K8s Deployment with sidecar, startup initialization, graceful shutdown, ArgoCD sync)

### Prior Phase Context
- `.planning/phases/17-tech-debt-resolution/17-CONTEXT.md` — D-09: K8s init container for spell dictionary rebuild (belt and suspenders)
- `.planning/phases/18-code-review/18-CONTEXT.md` — CHANGEME placeholders in config.py, pool sizing (PERF-01: db_pool_size=5, db_max_overflow=5)
- `.planning/phases/19-dockerfile-and-database-provisioning/19-CONTEXT.md` — Dockerfile structure (D-01 through D-14), DB provisioning (civpulse_geo_dev/prod), GHCR image, PostgreSQL headless Service

### Source Files (primary targets)
- `src/civpulse_geo/api/health.py` — Existing /health endpoint (to be extended with /health/live and /health/ready)
- `src/civpulse_geo/main.py` — Lifespan function (shutdown cleanup, provider registration for readiness counting)
- `src/civpulse_geo/config.py` — Settings class (ConfigMap/Secret values will override CHANGEME defaults)
- `src/civpulse_geo/database.py` — Engine and session factory (dispose on shutdown)

### Existing K8s Manifests (to be replaced/reorganized)
- `k8s/ollama-deployment.yaml` — Standalone Ollama deployment (model-pull init container pattern to be reused in sidecar)
- `k8s/ollama-pvc.yaml` — Ollama PVC (moves to Kustomize base)
- `k8s/ollama-service.yaml` — Standalone Ollama Service (removed — sidecar uses localhost)

### Docker & Entrypoint
- `Dockerfile` — Multi-stage production image (Phase 19, init containers use this image)
- `scripts/docker-entrypoint.sh` — Dev entrypoint with DB wait + migrate + seed (reference for init container logic)

### Infrastructure Reference
- K8s Service: `postgresql.civpulse-infra.svc.cluster.local:5432` (headless, endpoint 100.67.17.69)
- K8s namespaces: `civpulse-dev` and `civpulse-prod`
- GHCR: `ghcr.io/civicpulse/geo-api` (public, no imagePullSecret)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/health.py` — Existing health endpoint with version/commit metadata. Extend with `/health/live` and `/health/ready` routes in the same module.
- `k8s/ollama-deployment.yaml` — Model-pull init container pattern (start Ollama, pull model, kill) to reuse in sidecar configuration.
- `scripts/docker-entrypoint.sh` — DB wait logic (psycopg2 connect retry loop) as reference for init container approach.
- `main.py` lifespan — Provider registration (app.state.providers, app.state.validation_providers) provides the counts for readiness checks.

### Established Patterns
- **Config via env vars**: `Settings(BaseSettings)` reads from environment. K8s ConfigMap/Secret will set DATABASE_URL, DATABASE_URL_SYNC, ENVIRONMENT, CASCADE_LLM_ENABLED, OLLAMA_URL.
- **Two database URLs**: asyncpg for app, psycopg2 for Alembic. Both ConfigMap/Secret entries needed.
- **Connection pool**: `db_pool_size=5`, `db_max_overflow=5`. Single worker = max 10 connections per pod.
- **K8s labels**: `app.kubernetes.io/part-of: civpulse-geo` established in existing Ollama manifests.
- **Conditional provider registration**: `_*_data_available()` guards at startup. Provider count at lifespan end reflects what's actually available.

### Integration Points
- Readiness probe: `/health/ready` needs access to `app.state.providers` and `app.state.validation_providers` — must be checked via the FastAPI app instance.
- Shutdown: `database.py` exports the async engine. Lifespan shutdown must import and dispose it.
- Init containers: Use same geo-api Docker image but with different CMD overrides.
- ArgoCD: Application CRs point to `k8s/overlays/dev/` and `k8s/overlays/prod/` paths in the repo.

</code_context>

<specifics>
## Specific Ideas

- K8s 1.29+ native sidecar feature must be verified on the k3s cluster before implementation. If k3s version is < 1.29, fall back to regular sidecar container with geo-api's existing graceful fallback (llm_corrector=None when Ollama unavailable).
- The 10s preStop sleep is conservative given cascade P95 < 3s, but accounts for potential load testing scenarios in Phase 23.
- Belt-and-suspenders shutdown (lifespan + SIGTERM handler) mirrors the Phase 17 spell dictionary approach (app auto-rebuild + init container).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 20-health-resilience-and-k8s-manifests*
*Context gathered: 2026-03-29*
