# Phase 19: Dockerfile and Database Provisioning - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 19-dockerfile-and-database-provisioning
**Areas discussed:** Production image contents, Database provisioning method, Image registry & tagging, Entrypoint & startup

---

## Production Image Contents

### CLI Tools in Production

| Option | Description | Selected |
|--------|-------------|----------|
| API-only prod image | Strip CLI tools, GDAL, shp2pgsql. Smallest, most secure (~200MB). | |
| Full image with CLI tools | Keep geo-import CLI and GDAL/fiona. Larger (~1GB+) but operationally convenient. | ✓ |
| Separate CLI image variant | Two Dockerfile targets: slim API + full CLI. Best of both but two images. | |

**User's choice:** Full image with CLI tools
**Notes:** Ops needs to run geo-import inside production pods for data loading.

### Build Stages

| Option | Description | Selected |
|--------|-------------|----------|
| Multi-stage | Builder stage compiles, runtime stage copies artifacts. Meets DEPLOY-01. | ✓ |
| Single stage optimized | Keep single stage with cleanup. Simpler but larger. | |

**User's choice:** Multi-stage
**Notes:** None

### User Permissions

| Option | Description | Selected |
|--------|-------------|----------|
| Appuser owns /app | UID 1000, chown /app. Standard Python pattern. | ✓ |
| Root-owned, read-only /app | More restrictive, writes only to /tmp or volumes. | |

**User's choice:** Appuser owns /app
**Notes:** None

---

## Database Provisioning Method

### PostgreSQL Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Shared PG in civpulse-infra | StatefulSet or Deployment in civpulse-infra namespace. | |
| CloudNativePG operator | Databases provisioned via CRDs. | |
| No PG yet in cluster | Need to set up PostgreSQL in k3s. | |

**User's choice:** Other — PG runs natively on host, K8s Service proxies to it.
**Notes:** "There is a service proxy that runs in k8s that actually connects to the postgres running natively on the host." Direct access via `psql -h thor.tailb56d83.ts.net -U postgres`. WARNING: Live prod DB for other apps.

### Provisioning Method

| Option | Description | Selected |
|--------|-------------|----------|
| SQL script + docs | scripts/provision-db.sql with CREATE statements, run manually. | ✓ |
| K8s Job | Job manifest that runs psql against service proxy. | |
| Alembic handles it all | Extend Alembic for database creation. | |

**User's choice:** Direct management — SQL script approach with direct access to host PG.
**Notes:** User gave direct access credentials for provisioning.

### Dev vs Prod Isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Separate databases | civpulse_geo_dev and civpulse_geo_prod with own users. | ✓ |
| Schema separation | One database, dev and prod schemas. | |
| Single database | One database for both environments. | |

**User's choice:** Separate databases
**Notes:** None

### PG Service Verification

| Option | Description | Selected |
|--------|-------------|----------|
| postgresql.civpulse-infra | Service 'postgresql' in namespace 'civpulse-infra'. | ✓ |
| Different name/namespace | User provides actual name. | |

**User's choice:** postgresql.civpulse-infra (confirmed via kubectl)
**Notes:** Headless ClusterIP (None), endpoint 100.67.17.69. Also has postgres-exporter on port 9187.

---

## Image Registry & Tagging

### GHCR Path

| Option | Description | Selected |
|--------|-------------|----------|
| ghcr.io/civicpulse/geo-api | Under civicpulse GitHub org. | ✓ |
| ghcr.io/<username>/geo-api | Under personal GitHub account. | |

**User's choice:** ghcr.io/civicpulse/geo-api
**Notes:** None

### Tag Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Git SHA tags | Short git SHA + latest. Immutable, traceable. | ✓ |
| Semver tags | Version numbers (v1.3.0). Human-readable. | |
| Both SHA + semver | Every build gets SHA; releases get semver. | |

**User's choice:** Git SHA tags
**Notes:** None

### First Push Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Manual push now | Build and push in this phase to validate pipeline. | ✓ |
| Defer to Phase 21 | Only create Dockerfile, push when CI/CD is built. | |

**User's choice:** Manual push now
**Notes:** None

### Pull Credentials

| Option | Description | Selected |
|--------|-------------|----------|
| Already configured | k3s has GHCR pull secret. | |
| Needs setup | Create imagePullSecret in namespaces. | |
| Public image | No pull credentials needed. | ✓ |

**User's choice:** Public image
**Notes:** No imagePullSecret required.

---

## Entrypoint & Startup

### Production CMD

| Option | Description | Selected |
|--------|-------------|----------|
| Uvicorn only | CMD runs uvicorn directly. Migrations via init containers (Phase 20). | ✓ |
| Keep entrypoint script | docker-entrypoint.sh with DB wait + migrate + start. | |
| Entrypoint with skip flags | Entrypoint with env flags to disable features. | |

**User's choice:** Uvicorn only
**Notes:** None

### Worker Count

| Option | Description | Selected |
|--------|-------------|----------|
| Single worker | 1 worker, K8s handles scaling via replicas. | ✓ |
| CPU-based workers | 2 * CPU + 1 workers per pod. | |
| You decide | Claude picks based on constraints. | |

**User's choice:** Single worker
**Notes:** None

### Dev Compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| Update compose | Update docker-compose.yml to use new Dockerfile with CMD override. | ✓ |
| Separate dev Dockerfile | Keep current as Dockerfile.dev, new as Dockerfile. | |

**User's choice:** Update compose
**Notes:** None

---

## Claude's Discretion

- Exact multi-stage Dockerfile layer ordering and cache optimization
- GDAL runtime library selection
- Provisioning SQL script specifics (password generation, GRANT scope)
- .dockerignore updates

## Deferred Ideas

None — discussion stayed within phase scope
