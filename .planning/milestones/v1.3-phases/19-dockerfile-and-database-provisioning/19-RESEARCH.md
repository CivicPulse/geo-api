# Phase 19: Dockerfile and Database Provisioning - Research

**Researched:** 2026-03-29
**Domain:** Docker multi-stage builds (uv + GDAL), GHCR image publishing, PostgreSQL provisioning on shared host
**Confidence:** HIGH

## Summary

This phase has two well-defined work streams: (1) replace the single-stage dev Dockerfile with a production-quality multi-stage build, and (2) provision the `civpulse_geo_dev` and `civpulse_geo_prod` databases on the shared PostgreSQL 16 host. Both streams are low-risk because the infrastructure is live and reachable, the GHCR org and push pattern are proven from `run-api`, and the host PG already has PostGIS 3.4.2 available as an extension.

The key multi-stage decision (D-02) uses `uv` in a builder stage that compiles dependencies into `.venv`, then a clean runtime stage that copies only `.venv` plus application source. The project already has a `.dockerignore`; it needs minor additions for production. A direct reference implementation exists in the same organization (`debug/voter-api/Dockerfile`) that handles a similar uv + PostGIS runtime stack.

Database provisioning is a one-time manual SQL execution against the host. The server is PostgreSQL 16.13, PostGIS 3.4.2 is available but not yet installed anywhere (`pg_available_extensions` confirms it). Neither `civpulse_geo_dev` nor `civpulse_geo_prod` databases nor their users exist yet. The provisioning script must use `IF NOT EXISTS` guards throughout — this is a live production server with 11 existing databases and 28 active connections against a `max_connections=100` limit.

**Primary recommendation:** Follow the `debug/voter-api/Dockerfile` multi-stage pattern already established in this org. Use `uv sync --locked --no-dev --no-editable` in the builder stage. Authenticate to GHCR via `echo $(gh auth token) | docker login ghcr.io -u kerryhatcher --password-stdin` and push with short-SHA plus `latest` tags matching the `run-api` convention.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Full image — keep geo-import CLI, GDAL/fiona, and all data loading dependencies in the production image. Ops can kubectl exec into pods and run imports directly.
- **D-02:** Multi-stage Dockerfile — builder stage (uv + compile deps), runtime stage (copies .venv + source + GDAL runtime libs). No compilers/headers in final image. Satisfies DEPLOY-01 multi-stage requirement.
- **D-03:** Non-root appuser (UID 1000) owns /app directory.
- **D-04:** PostgreSQL runs natively on host "thor" (accessible via Tailscale at `thor.tailb56d83.ts.net`). A headless K8s Service `postgresql.civpulse-infra.svc.cluster.local:5432` proxies to the host PG (endpoint IP: 100.67.17.69).
- **D-05:** Separate databases for dev and prod — `civpulse_geo_dev` and `civpulse_geo_prod` on the same PostgreSQL server, each with its own database user (`geo_dev` / `geo_prod`).
- **D-06:** Provisioning via SQL script (`scripts/provision-db.sql`) with CREATE DATABASE/USER/EXTENSION statements. One-time manual execution against host PG. WARNING: live production server — provisioning must use IF NOT EXISTS guards, no destructive operations.
- **D-07:** PostGIS extension, pg_trgm, and fuzzystrmatch must be enabled per database.
- **D-08:** GHCR repository: `ghcr.io/civicpulse/geo-api`
- **D-09:** Git SHA tag strategy — images tagged with short git SHA (e.g., `ghcr.io/civicpulse/geo-api:abc1234`) plus `latest` convenience tag.
- **D-10:** Manual build and push to GHCR in this phase to validate full pipeline. Phase 21 CI/CD will automate this.
- **D-11:** Public GHCR image — no imagePullSecret needed in K8s namespaces.
- **D-12:** Production CMD is uvicorn only (exec-form): `CMD ["uvicorn", "civpulse_geo.main:app", "--host", "0.0.0.0", "--port", "8000"]`. No migrations in image startup.
- **D-13:** Single uvicorn worker process. K8s handles scaling via replicas.
- **D-14:** Update docker-compose.yml to use the new multi-stage Dockerfile. Compose overrides CMD to run `docker-entrypoint.sh` for dev.

### Claude's Discretion

- Exact multi-stage Dockerfile layer ordering and cache optimization
- GDAL runtime library selection (which -dev packages to exclude from runtime stage)
- Provisioning SQL script specifics (password generation approach, GRANT permissions scope)
- Whether to add a `.dockerignore` or update existing one for production builds

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 | Multi-stage Dockerfile (uv builder, non-root runtime, exec-form CMD, read-only FS compatible) | uv multi-stage pattern verified from astral docs + org reference Dockerfile; non-root UID 1000 appuser; exec-form CMD confirmed |
| DEPLOY-08 | Database provisioned on shared PostgreSQL instance (dev + prod) | Host PG confirmed reachable (PostgreSQL 16.13); PostGIS 3.4.2 available; databases/users do not yet exist; provisioning SQL pattern documented |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ghcr.io/astral-sh/uv | latest (pinned at build time) | Builder stage uv binary | Official uv Docker image; COPY --from pattern avoids version drift |
| python:3.12-slim-bookworm | 3.12 | Runtime base image | Matches existing pyproject.toml `requires-python = ">=3.12"`; bookworm = Debian 12 stable |
| libgdal-dev | (apt, bookworm) | GDAL runtime libs for fiona | Provides shared libs (.so) fiona needs at runtime; -dev not needed in runtime but package name installs runtime libs on Debian bookworm |
| PostgreSQL 16.13 | live server | Host database | Confirmed via `psql -h thor.tailb56d83.ts.net -U postgres -c "SELECT version();"` |
| PostGIS | 3.4.2 | Spatial extension | Confirmed available via `pg_available_extensions`; not yet installed anywhere |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| libexpat1 | (apt) | XML parsing for GDAL | Already in current Dockerfile; needed for fiona format drivers |
| postgresql-client | (apt) | psql/pg_isready in image | Required for dev entrypoint DB wait loop; include in runtime |
| unzip / wget | (apt) | Tiger data loading (D-01) | Required for geo-import CLI; part of data loading pipeline |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python:3.12-slim-bookworm as runtime base | ghcr.io/astral-sh/uv:python3.12-bookworm-slim | The astral image bundles uv — convenient for single-stage, but for multi-stage the runtime doesn't need uv at all |
| COPY --from=ghcr.io/astral-sh/uv /uv /bin/ | Install uv via pip/curl | COPY pattern is faster and more reproducible; official recommended approach |
| libgdal-dev in runtime | only runtime .so files | Debian packaging doesn't separate runtime vs. dev cleanly for gdal; using libgdal-dev in runtime is the pragmatic choice (already proven in voter-api Dockerfile) |

**Installation (builder stage only):**
```bash
# In builder stage — uv binary injection
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
```

---

## Architecture Patterns

### Recommended Project Structure (Dockerfile)

```
# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# System build-time deps (GDAL headers for fiona compilation)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgdal-dev libexpat1-dev && \
    rm -rf /var/lib/apt/lists/*

# Dependency layer (cached unless lock file changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Application install (non-editable for clean .venv copy)
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ──────────────────────────────────────────────
# Stage 2: Runtime
FROM python:3.12-slim-bookworm

# GDAL runtime + PostgreSQL client + data loading tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgdal-dev libexpat1 postgresql-client unzip wget && \
    rm -rf /var/lib/apt/lists/*

# Non-root user (UID 1000, D-03)
RUN groupadd -r appuser --gid 1000 && \
    useradd -r -g appuser --uid 1000 --home /app appuser

WORKDIR /app

# Transfer only the venv from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
# Copy source (needed because non-editable install still references src/ in some patterns;
# also required for alembic migrations path and scripts/)
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/scripts /app/scripts

# GIS data directory (owned by appuser for runtime writes)
RUN mkdir -p /gisdata/temp && chown -R appuser:appuser /gisdata

ARG GIT_COMMIT=unknown
ENV PATH="/app/.venv/bin:$PATH" \
    GIT_COMMIT=${GIT_COMMIT}

USER appuser

EXPOSE 8000

# Exec-form CMD (D-12, DEPLOY-01)
CMD ["uvicorn", "civpulse_geo.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Pattern 1: uv Non-Editable Install for Multi-Stage

**What:** `uv sync --locked --no-dev --no-editable` installs the project itself into `.venv/lib/pythonX.Y/site-packages/` rather than as a pointer to `/app/src`. This makes the `.venv` self-contained and portable to the runtime stage without needing the full source tree.

**When to use:** Any multi-stage build where you copy `.venv` between stages.

**Example:**
```dockerfile
# Source: https://docs.astral.sh/uv/guides/integration/docker/
# Install deps only (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy source and install project non-editablly
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable
```

### Pattern 2: docker-compose Dev Override

**What:** Compose file uses the same multi-stage Dockerfile but overrides CMD to run `docker-entrypoint.sh` (which handles DB wait, migrations, seeding, then uvicorn).

**When to use:** Local development — runtime stage has all necessary tools; entrypoint handles migration.

**Example:**
```yaml
# docker-compose.yml — api service section
api:
  build: .
  command: ["bash", "scripts/docker-entrypoint.sh"]
  environment:
    DATABASE_URL: postgresql+asyncpg://civpulse:civpulse@db:5432/civpulse_geo
    DATABASE_URL_SYNC: postgresql+psycopg2://civpulse:civpulse@db:5432/civpulse_geo
    # ... rest of env vars
```

### Pattern 3: GHCR Manual Push (matching run-api convention)

**What:** Login via gh token, build with `--build-arg GIT_COMMIT=<sha>`, tag with `sha-<short>` and `latest`, push both tags.

**Example:**
```bash
SHORT_SHA=$(git rev-parse --short HEAD)
# Login
echo $(gh auth token) | docker login ghcr.io -u kerryhatcher --password-stdin
# Build
docker build --build-arg GIT_COMMIT=${SHORT_SHA} -t ghcr.io/civicpulse/geo-api:sha-${SHORT_SHA} -t ghcr.io/civicpulse/geo-api:latest .
# Push
docker push ghcr.io/civicpulse/geo-api:sha-${SHORT_SHA}
docker push ghcr.io/civicpulse/geo-api:latest
```

### Pattern 4: Database Provisioning SQL (IF NOT EXISTS guards)

**What:** SQL script with idempotent guards for user, database, and extension creation. Connects to host PG as superuser and runs against each database in sequence.

**When to use:** One-time execution from a machine with Tailscale access to thor.

**Example skeleton:**
```sql
-- scripts/provision-db.sql
-- Run as: psql -h thor.tailb56d83.ts.net -U postgres -f scripts/provision-db.sql

-- === Dev user and database ===
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'geo_dev') THEN
    CREATE ROLE geo_dev WITH LOGIN PASSWORD 'PLACEHOLDER_DEV';
  END IF;
END $$;

CREATE DATABASE civpulse_geo_dev
  WITH OWNER = geo_dev
  ENCODING = 'UTF8'
  LC_COLLATE = 'en_US.UTF-8'
  LC_CTYPE = 'en_US.UTF-8'
  TEMPLATE = template0;  -- explicit template needed for collate override

\connect civpulse_geo_dev
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
GRANT ALL PRIVILEGES ON DATABASE civpulse_geo_dev TO geo_dev;
GRANT ALL ON SCHEMA public TO geo_dev;

-- === Prod user and database (same pattern) ===
-- (repeat for geo_prod / civpulse_geo_prod)
```

**Important:** `CREATE DATABASE` does not support `IF NOT EXISTS` in PostgreSQL 16. Use `DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_database WHERE datname = '...') THEN CREATE DATABASE ...; END IF; END $$;` OR run in a shell with `psql ... -c "SELECT 1 FROM pg_database WHERE datname='civpulse_geo_dev'" | grep -q 1 || psql ... -c "CREATE DATABASE ..."`. The SQL script approach should wrap database creation similarly.

### Pattern 5: Connectivity Test Pod

**What:** Run a short-lived pod in each namespace to verify the postgresql Service is reachable and credentials work.

**Example:**
```bash
# Dev namespace test
kubectl run pg-test --rm -i --restart=Never \
  --namespace civpulse-dev \
  --image=postgres:16 \
  --env="PGPASSWORD=<geo_dev_password>" \
  -- psql -h postgresql.civpulse-infra.svc.cluster.local \
          -U geo_dev -d civpulse_geo_dev \
          -c "SELECT PostGIS_Version();"

# Prod namespace test (same pattern with geo_prod)
```

### Anti-Patterns to Avoid

- **Shell-form CMD:** `CMD uvicorn ...` creates a shell wrapper process, which prevents clean SIGTERM handling. DEPLOY-01 explicitly requires exec-form.
- **Running as root in production image:** Security risk; UID 1000 appuser is required (D-03).
- **`uv sync` without `--no-editable` in multi-stage:** Without `--no-editable`, the installed package points to `/app/src` as a symlink — copying `.venv` alone won't work; the source must be present too. Use `--no-editable` to embed the package in site-packages.
- **Compilers in runtime stage:** libgdal-dev in runtime provides shared libs (.so files) — this is different from having build-time headers. Avoid gcc, g++, build-essential in the final stage.
- **`CREATE DATABASE` without `TEMPLATE = template0`:** When specifying custom LC_COLLATE, template0 must be the template; template1 will fail with a collation mismatch error.
- **Destructive provisioning SQL:** No DROP DATABASE, DROP ROLE, or TRUNCATE — this is a shared live production server. IF NOT EXISTS guards are mandatory.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker layer caching for uv | Manual COPY + RUN ordering | `--mount=type=bind` for lock/pyproject, `--mount=type=cache` for uv cache | BuildKit cache mounts avoid invalidating dep layer on source change |
| GHCR auth token | Storing PAT in shell profile | `echo $(gh auth token) \| docker login ghcr.io ...` | `gh auth token` rotates automatically; already authenticated via `write:packages` scope |
| Database existence check before CREATE | Scripted IF NOT EXISTS workaround | PostgreSQL `DO $$ BEGIN IF NOT EXISTS ... THEN CREATE DATABASE ...; END IF; END $$;` | The workaround in plpgsql is standard and fully idempotent |
| Image visibility management | Manual GitHub UI | `gh api` or GHCR UI settings | Repo is already public (confirmed); GHCR images for public repos inherit public visibility by default |

**Key insight:** The uv `--mount=type=cache` + `--mount=type=bind` pattern is critical for fast CI rebuilds. Without it, every `docker build` re-downloads all dependencies.

---

## Runtime State Inventory

> This section covers rename/refactor/migration awareness — included here because provisioning creates new runtime state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | No geo-api databases exist yet on host PG (`civpulse_geo_dev`, `civpulse_geo_prod` absent from `\l`) | Create via provision-db.sql (new data, not migration) |
| Live service config | K8s postgresql Service exists: `postgresql.civpulse-infra.svc.cluster.local:5432` endpoint `100.67.17.69:5432` — confirmed operational | None — already configured correctly |
| OS-registered state | No geo-api users in `pg_roles`: `SELECT rolname FROM pg_roles WHERE rolname LIKE 'geo%'` returned 0 rows | Create `geo_dev` and `geo_prod` roles via provision-db.sql |
| Secrets/env vars | `postgresql-credentials` K8s Secret in `civpulse-infra` has `civpulse-password` and `zitadel-password` keys; no geo-api credentials yet | Phase 20 (DEPLOY-05) will create K8s Secrets for `geo_dev` and `geo_prod` credentials; Phase 19 generates the passwords |
| Build artifacts | No prior geo-api Docker image exists in GHCR (`ghcr.io/civicpulse/geo-api` package does not yet exist) | First push in this phase creates it |

---

## Common Pitfalls

### Pitfall 1: fiona Wheel vs. System GDAL Mismatch

**What goes wrong:** `fiona` ships a bundled libgdal in its wheel. If the system also has a different `libgdal.so`, Python imports can pick up the wrong one and crash with symbol errors.

**Why it happens:** The existing Dockerfile uses `libgdal-dev` from apt AND `fiona` from pypi. The pip wheel for fiona >=1.9 ships its own GDAL, but the existing project installs `fiona>=1.10.0` which uses the system GDAL.

**How to avoid:** Verify `fiona` is installed from source (no bundled GDAL wheel) by checking whether the lock file records a wheel or sdist. On `python:3.12-slim-bookworm`, `apt install libgdal-dev` provides GDAL 3.x. Fiona 1.10.x links against system GDAL if installed with `--no-binary fiona` — but if the wheel works, leave it. Test with `uv run python -c "import fiona; print(fiona.__gdal_version__)"` inside the built image.

**Warning signs:** ImportError on `import fiona` or `import gdal`, version mismatch errors mentioning `libgdal.so`.

### Pitfall 2: Non-root User Can't Write to /gisdata

**What goes wrong:** Tiger data loader writes to `/gisdata/temp`. If `appuser` (UID 1000) doesn't own that directory, `kubectl exec` imports will fail with `PermissionError`.

**Why it happens:** The current Dockerfile creates `/gisdata/temp` in the base stage as root. In the multi-stage build, the directory is recreated but may not be chowned.

**How to avoid:** Explicitly `RUN mkdir -p /gisdata/temp && chown -R appuser:appuser /gisdata` in the runtime stage after the user is created.

**Warning signs:** `PermissionError: [Errno 13] Permission denied: '/gisdata/temp/...'` in pod logs.

### Pitfall 3: Alembic Can't Find DATABASE_URL_SYNC at Migration Time

**What goes wrong:** `alembic/env.py` imports `from civpulse_geo.config import settings` which reads `DATABASE_URL_SYNC` from env. If the init container in Phase 20 runs `alembic upgrade head` without the env var set, migrations fail silently or with a CHANGEME connection error.

**Why it happens:** `config.py` has CHANGEME defaults. The CHANGEME string is not a valid connection URL — psycopg2 will raise `OperationalError`.

**How to avoid:** In Phase 19 provisioning, establish what the DATABASE_URL_SYNC values will be for dev and prod (`postgresql+psycopg2://geo_dev:<pass>@postgresql.civpulse-infra.svc.cluster.local:5432/civpulse_geo_dev`). Document these for Phase 20's ConfigMap/Secret creation.

**Warning signs:** Alembic startup error: `could not connect to server: Connection refused` or `password authentication failed for user "CHANGEME"`.

### Pitfall 4: GHCR Image Not Linked to Repository

**What goes wrong:** Pushed image appears in GitHub Packages under the user account, not the `civicpulse` organization, or is not publicly visible.

**Why it happens:** When pushing via CLI (not GitHub Actions), GHCR doesn't automatically link the package to the source repository. The package may default to private.

**How to avoid:** After first push, go to `https://github.com/orgs/civicpulse/packages` and link the `geo-api` package to the `CivicPulse/geo-api` repository. Set visibility to public. Confirmed: `run-api` uses the `ghcr.io/civicpulse/` namespace, so the org already has package write access.

**Warning signs:** `kubectl get pods` shows `ErrImagePull` or `ImagePullBackOff`.

### Pitfall 5: CREATE DATABASE Fails Inside DO $$ Block

**What goes wrong:** `CREATE DATABASE` cannot be run inside a transaction block. `DO $$ ... CREATE DATABASE ... $$` will fail with `ERROR: CREATE DATABASE cannot run inside a transaction block`.

**Why it happens:** PL/pgSQL `DO` blocks execute inside an implicit transaction.

**How to avoid:** Use a shell-level check before calling psql for database creation, OR use the approach: connect to postgres DB, check `pg_database`, run CREATE DATABASE as a separate psql invocation. The safest pattern in a SQL script is to put the CREATE DATABASE after `\connect postgres` and wrap the check in psql meta-commands, or use a bash wrapper script.

**Warning signs:** `ERROR: CREATE DATABASE cannot run inside a transaction block` in provisioning output.

### Pitfall 6: PostGIS Extension Requires superuser

**What goes wrong:** `CREATE EXTENSION postgis;` requires superuser or `pg_extension_owner` role. `geo_dev` / `geo_prod` are regular login roles and cannot create extensions.

**Why it happens:** PostGIS registers C functions that require trust. Standard user cannot do this.

**How to avoid:** Connect to each database AS postgres (superuser) when running extension creation. The provision-db.sql script must use `\connect <dbname>` as postgres and run `CREATE EXTENSION IF NOT EXISTS postgis;` before granting to the app user.

**Warning signs:** `ERROR: permission denied to create extension "postgis"`.

---

## Code Examples

Verified patterns from existing codebase and org references:

### docker-compose.yml CMD Override for Dev
```yaml
# Source: existing docker-compose.yml pattern + D-14
api:
  build: .
  command: ["bash", "scripts/docker-entrypoint.sh"]
  environment:
    DATABASE_URL: postgresql+asyncpg://civpulse:civpulse@db:5432/civpulse_geo
    DATABASE_URL_SYNC: postgresql+psycopg2://civpulse:civpulse@db:5432/civpulse_geo
    LOG_LEVEL: DEBUG
    ENVIRONMENT: development
    DEBUG: "0"
```

### GHCR Push (matching run-api pattern from debug/run-api/publish.yml)
```bash
SHORT_SHA=$(git rev-parse --short HEAD)
echo $(gh auth token) | docker login ghcr.io -u kerryhatcher --password-stdin
docker build \
  --build-arg GIT_COMMIT=${SHORT_SHA} \
  -t ghcr.io/civicpulse/geo-api:sha-${SHORT_SHA} \
  -t ghcr.io/civicpulse/geo-api:latest \
  .
docker push ghcr.io/civicpulse/geo-api:sha-${SHORT_SHA}
docker push ghcr.io/civicpulse/geo-api:latest
```

### Connectivity Test Pod (from namespace)
```bash
# Test from civpulse-dev namespace
kubectl run pg-test --rm -i --restart=Never \
  --namespace civpulse-dev \
  --image=postgres:16 \
  --env="PGPASSWORD=<geo_dev_password>" \
  -- psql -h postgresql.civpulse-infra.svc.cluster.local \
          -U geo_dev -d civpulse_geo_dev \
          -c "SELECT PostGIS_Version();"
```

### Provisioning SQL Structure (safe pattern for shared server)
```sql
-- Idempotent role creation (DO block IS safe for ROLE creation)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'geo_dev') THEN
    CREATE ROLE geo_dev WITH LOGIN PASSWORD 'REPLACE_ME';
  END IF;
END $$;

-- Database creation must be run as separate statement outside transaction
-- Use shell wrapper: check pg_database first, then CREATE if absent
```

### .dockerignore Additions for Production
```
# Add to existing .dockerignore
tiger-data/
screenshots/
*.sql.bak
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-stage Dockerfile with all build tools in production | Multi-stage: builder (uv + headers) → runtime (venv + libs only) | uv 0.4+ / 2024 | Smaller image, no compilers in prod |
| Shell-form CMD | Exec-form CMD `[]` | Docker best practice / K8s signal handling | SIGTERM goes directly to app, enables graceful shutdown |
| COPY project source into image | `uv sync --no-editable` embeds package in .venv/site-packages | uv 0.3+ | .venv can be copied standalone between stages |
| Run container as root | Non-root user (UID 1000) with named user | Security standard / K8s PSP/PSA | Required for read-only FS compatibility and pod security standards |

**Deprecated/outdated:**
- Shell-form CMD (`CMD uvicorn ...`): prevents clean signal handling; always use exec-form for K8s workloads.
- `--mount=type=cache` without `UV_LINK_MODE=copy`: cache mount and copy target on different filesystems require copy mode.

---

## Open Questions

1. **Password generation for geo_dev / geo_prod**
   - What we know: D-05 requires separate DB users; passwords will be stored in K8s Secrets (Phase 20)
   - What's unclear: Should passwords be generated now and stored somewhere, or deferred to Phase 20? Phase 19 needs to create the users to run connectivity tests.
   - Recommendation: Generate passwords during Phase 19 provisioning and store them immediately in K8s Secrets in `civpulse-infra` (or the respective namespaces). Name them consistently: `geo-api-db-credentials` with keys `dev-password` and `prod-password`, or separate secrets per namespace. This is a planning decision — document whichever convention is chosen so Phase 20 can reference it.

2. **fiona wheel vs. system GDAL in bookworm**
   - What we know: `libgdal-dev` on bookworm provides GDAL 3.4.x; fiona 1.10.x works with system GDAL
   - What's unclear: Whether pip/uv installs fiona with a bundled wheel (GDAL 3.6+) or links to system GDAL
   - Recommendation: After building the image, run `docker run --rm ghcr.io/civicpulse/geo-api:sha-<SHA> python -c "import fiona; fiona.open"` as a smoke test. If it segfaults, add `--no-binary fiona` to the uv build flags via `pyproject.toml` source override.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Image build | Yes | 29.3.1 | — |
| docker buildx | BuildKit cache mounts | Yes | 0.31.1 | Remove `--mount=type=cache` (slower builds) |
| gh CLI | GHCR login | Yes | 2.89.0 | Create PAT manually |
| gh auth (write:packages scope) | GHCR push | Yes | Confirmed `write:packages` in token scopes | — |
| kubectl | Connectivity test pods | Yes | v1.29.0 | — |
| k3s cluster | Connectivity tests | Yes | Reachable at thor.tailb56d83.ts.net:6443 | — |
| civpulse-dev namespace | Dev connectivity test | Yes | Active (27d) | — |
| civpulse-prod namespace | Prod connectivity test | Yes | Active (27d) | — |
| postgresql K8s Service | Test pod target | Yes | Headless, endpoint 100.67.17.69:5432 confirmed | — |
| Host PostgreSQL (thor) | DB provisioning | Yes | pg_isready: accepting connections | — |
| psql client (local) | Provision SQL execution | Yes | 14.22 (Ubuntu) | — |
| PostGIS extension | DEPLOY-08 | Yes (available, not installed) | 3.4.2 in pg_available_extensions | — |
| pg_trgm extension | DEPLOY-08 | Yes (available) | 1.6 | — |
| fuzzystrmatch extension | DEPLOY-08 | Yes (available) | 1.2 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — all dependencies confirmed present.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q --ignore=tests/test_import_cli.py --ignore=tests/test_load_oa_cli.py` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPLOY-01 | Dockerfile builds successfully with multi-stage structure | manual/smoke | `docker build -t geo-api-test .` | N/A — build artifact |
| DEPLOY-01 | Runtime container runs as non-root (UID 1000) | manual/smoke | `docker run --rm ghcr.io/civicpulse/geo-api:sha-<sha> id` | N/A — runtime check |
| DEPLOY-01 | Exec-form CMD — uvicorn starts without shell wrapper | manual/smoke | `docker run --rm -d -p 8000:8000 ghcr.io/civicpulse/geo-api:sha-<sha>` | N/A |
| DEPLOY-08 | civpulse_geo_dev database exists on host PG | manual/SQL | `psql -h thor.tailb56d83.ts.net -U postgres -c "\\l civpulse_geo_dev"` | N/A |
| DEPLOY-08 | civpulse_geo_prod database exists on host PG | manual/SQL | `psql -h thor.tailb56d83.ts.net -U postgres -c "\\l civpulse_geo_prod"` | N/A |
| DEPLOY-08 | PostGIS/pg_trgm/fuzzystrmatch enabled in both databases | manual/SQL | `psql ... -c "SELECT extname FROM pg_extension;"` per database | N/A |
| DEPLOY-08 | Test pod in civpulse-dev can connect and query | manual/K8s | kubectl run pg-test (see Code Examples) | N/A — Wave 0 pod |
| DEPLOY-08 | Test pod in civpulse-prod can connect and query | manual/K8s | kubectl run pg-test (see Code Examples) | N/A — Wave 0 pod |
| DEPLOY-08 | k3s can pull image from GHCR | manual/K8s | `kubectl run geo-test --rm --image=ghcr.io/civicpulse/geo-api:sha-<sha> -n civpulse-dev -- id` | N/A |

**Note:** DEPLOY-01 and DEPLOY-08 are infrastructure deliverables, not unit-testable code behaviors. All validation is smoke/manual. The existing pytest suite remains green throughout; no new test files are needed for this phase.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q` (verify no existing tests broken)
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green + all manual smoke tests pass before `/gsd:verify-work`

### Wave 0 Gaps
None — no new test files required for this phase. Validation is manual/smoke (Docker build, GHCR pull, kubectl test pods, psql connectivity checks).

---

## Sources

### Primary (HIGH confidence)
- `debug/voter-api/Dockerfile` — in-org multi-stage uv + PostGIS runtime reference (same org, same stack)
- `debug/run-api/.github/workflows/publish.yml` — in-org GHCR push workflow (exact tagging pattern)
- `psql -h thor.tailb56d83.ts.net -U postgres` — live host verification (PostgreSQL 16.13, PostGIS 3.4.2 available)
- `kubectl get service postgresql -n civpulse-infra` — confirmed endpoint 100.67.17.69:5432
- `gh auth status` — confirmed `write:packages` scope
- [Astral uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/) — multi-stage pattern, ENV vars, --no-editable

### Secondary (MEDIUM confidence)
- [astral-sh/uv-docker-example multistage.Dockerfile](https://github.com/astral-sh/uv-docker-example/blob/main/multistage.Dockerfile) — official reference implementation
- [GitHub Container Registry docs](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) — GHCR login and push commands

### Tertiary (LOW confidence)
- WebSearch findings on GDAL/fiona Docker patterns — cross-verified with voter-api Dockerfile which uses the same approach

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified from live infrastructure + org reference Dockerfile
- Architecture: HIGH — direct reference implementation exists in same org
- Pitfalls: HIGH — verified from actual host PG constraints (max_connections, live databases) and PostgreSQL transaction block behavior
- DB provisioning: HIGH — live host queried; extensions confirmed available; databases confirmed absent

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable infrastructure; uv and GHCR patterns are stable)
