# Phase 19: Dockerfile and Database Provisioning - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Create a production-ready multi-stage Docker image pushed to GHCR, and provision geo-api databases (dev + prod) on the shared PostgreSQL instance running natively on the host. The image must be pullable by the k3s cluster and the databases reachable from inside K8s pods.

</domain>

<decisions>
## Implementation Decisions

### Production Image Contents
- **D-01:** Full image with CLI tools — keep geo-import CLI, GDAL/fiona, and all data loading dependencies in the production image. Ops can kubectl exec into pods and run imports directly.
- **D-02:** Multi-stage Dockerfile — builder stage (uv + compile deps), runtime stage (copies .venv + source + GDAL runtime libs). No compilers/headers in final image. Satisfies DEPLOY-01 multi-stage requirement.
- **D-03:** Non-root appuser (UID 1000) owns /app directory. Standard pattern for Python apps, allows writing logs/temp files if needed.

### Database Provisioning
- **D-04:** PostgreSQL runs natively on host "thor" (accessible via Tailscale at `thor.tailb56d83.ts.net`). A headless K8s Service `postgresql.civpulse-infra.svc.cluster.local:5432` proxies to the host PG (endpoint IP: 100.67.17.69).
- **D-05:** Separate databases for dev and prod — `civpulse_geo_dev` and `civpulse_geo_prod` on the same PostgreSQL server, each with its own database user (`geo_dev` / `geo_prod`).
- **D-06:** Provisioning via SQL script (`scripts/provision-db.sql`) with CREATE DATABASE/USER/EXTENSION statements. One-time manual execution against host PG. WARNING: This is a live production server shared with other applications — provisioning must be conservative (IF NOT EXISTS guards, no destructive operations).
- **D-07:** PostGIS extension, pg_trgm, and fuzzystrmatch must be enabled per database (required by geo-api's spatial queries, fuzzy matching, and phonetic search).

### Image Registry & Tagging
- **D-08:** GHCR repository: `ghcr.io/civicpulse/geo-api`
- **D-09:** Git SHA tag strategy — images tagged with short git SHA (e.g., `ghcr.io/civicpulse/geo-api:abc1234`) plus `latest` convenience tag. Immutable, traceable to exact commit.
- **D-10:** Manual build and push to GHCR in this phase to validate full pipeline: build -> push -> k3s can pull. Phase 21 CI/CD will automate this.
- **D-11:** Public GHCR image — no imagePullSecret needed in K8s namespaces.

### Entrypoint & Startup
- **D-12:** Production CMD is uvicorn only (exec-form per DEPLOY-01): `CMD ["uvicorn", "civpulse_geo.main:app", "--host", "0.0.0.0", "--port", "8000"]`. No migrations, no seeding — those are delegated to K8s init containers in Phase 20.
- **D-13:** Single uvicorn worker process. K8s handles scaling via replicas. Simpler memory model with one SQLAlchemy async connection pool per pod.
- **D-14:** Update docker-compose.yml to use the new multi-stage Dockerfile. Compose overrides CMD to run the existing docker-entrypoint.sh for dev (migrations + seeding + uvicorn). One Dockerfile for dev and prod.

### Claude's Discretion
- Exact multi-stage Dockerfile layer ordering and cache optimization
- GDAL runtime library selection (which -dev packages to exclude from runtime stage)
- Provisioning SQL script specifics (password generation approach, GRANT permissions scope)
- Whether to add a `.dockerignore` or update existing one for production builds

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — DEPLOY-01, DEPLOY-08 acceptance criteria
- `.planning/ROADMAP.md` §Phase 19 — Success criteria (4 items: multi-stage Dockerfile, GHCR push, DB provisioned, pod connectivity test)

### Existing Docker/Infrastructure Files
- `Dockerfile` — Current single-stage dev Dockerfile (to be replaced with multi-stage)
- `docker-compose.yml` — Dev compose setup (to be updated to use new Dockerfile)
- `scripts/docker-entrypoint.sh` — Current entrypoint (DB wait + migrate + seed + uvicorn) — dev only going forward
- `alembic.ini` — Alembic configuration (migrations directory)
- `migrations/` — Alembic migrations directory
- `pyproject.toml` — Python project config (dependencies, entry points)

### Existing K8s Manifests
- `k8s/ollama-deployment.yaml` — Existing Ollama K8s deployment (reference for manifest style)
- `k8s/ollama-pvc.yaml` — Existing Ollama PVC
- `k8s/ollama-service.yaml` — Existing Ollama Service

### Prior Phase Context
- `.planning/phases/17-tech-debt-resolution/17-CONTEXT.md` — D-09: Phase 20 adds K8s init container for spell dictionary rebuild
- `.planning/phases/18-code-review/18-CONTEXT.md` — Code review decisions affecting deployment (CHANGEME placeholders, pool sizing)

### Infrastructure Reference
- K8s Service: `postgresql.civpulse-infra.svc.cluster.local:5432` (headless, endpoint 100.67.17.69)
- Host PG access: `psql -h thor.tailb56d83.ts.net -U postgres`
- K8s postgres-exporter: `postgres-exporter.civpulse-infra.svc.cluster.local:9187`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/docker-entrypoint.sh` — Existing entrypoint with DB wait + migrate + seed logic. Dev compose will continue using this via CMD override.
- `k8s/ollama-*.yaml` — Existing K8s manifests establish the pattern for manifest style and namespace conventions.
- `src/civpulse_geo/config.py` — Settings class with CHANGEME DB URL defaults. Prod will inject real credentials via K8s ConfigMap/Secret (Phase 20, DEPLOY-05).

### Established Patterns
- **Config via env vars**: `Settings(BaseSettings)` reads from environment. K8s Secret/ConfigMap will set DATABASE_URL, DATABASE_URL_SYNC.
- **Two database URLs**: asyncpg for app, psycopg2 for Alembic. Both need to be configured per environment.
- **Connection pool**: `db_pool_size=5`, `db_max_overflow=5` (max 10 connections per worker). Single worker = max 10 connections to PG.
- **PostGIS extensions**: Requires `postgis`, `pg_trgm`, `fuzzystrmatch` — all must be enabled in both dev and prod databases.

### Integration Points
- `docker-compose.yml` currently builds from Dockerfile and mounts source for dev. Needs CMD override for dev entrypoint.
- K8s namespaces: `civpulse-dev` and `civpulse-prod` — confirmed convention from existing Ollama manifests.
- GHCR: `ghcr.io/civicpulse/geo-api` — public, no imagePullSecret needed.

</code_context>

<specifics>
## Specific Ideas

- Host PG is on Tailscale network (thor.tailb56d83.ts.net) — provisioning SQL must be run from a machine with Tailscale access.
- The PostgreSQL server is shared with other production applications — all provisioning SQL must use IF NOT EXISTS guards and avoid any destructive operations.
- No PgBouncer in the path (from STATE.md infra decisions) — direct connections to host PG. No need for `prepared_statement_cache_size=0`.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 19-dockerfile-and-database-provisioning*
*Context gathered: 2026-03-29*
