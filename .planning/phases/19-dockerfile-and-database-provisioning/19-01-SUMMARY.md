---
phase: 19-dockerfile-and-database-provisioning
plan: "01"
subsystem: infrastructure
tags: [docker, multi-stage, provisioning, postgresql, postgis]
dependency_graph:
  requires: []
  provides: [multi-stage-dockerfile, db-provisioning-sql]
  affects: [docker-compose.yml]
tech_stack:
  added: []
  patterns: [uv-multi-stage-docker, exec-form-cmd, non-root-appuser, gexec-create-database]
key_files:
  created:
    - scripts/provision-db.sql
  modified:
    - Dockerfile
    - .dockerignore
    - docker-compose.yml
decisions:
  - "Multi-stage Dockerfile uses python:3.12-slim-bookworm for both builder and runtime stages"
  - "Non-editable uv install (--no-dev --no-editable) makes .venv portable between stages"
  - "docker-compose dev workflow preserved via command override to docker-entrypoint.sh"
  - "CREATE DATABASE uses \\gexec pattern to safely run outside transaction block (Pitfall 5)"
  - "PostGIS extension creation runs as postgres superuser (Pitfall 6) — not as geo_dev/geo_prod"
metrics:
  duration: "3 min"
  completed: "2026-03-30"
  tasks: 2
  files_changed: 4
---

# Phase 19 Plan 01: Dockerfile and Database Provisioning Summary

Multi-stage production Dockerfile with non-root appuser (UID 1000), exec-form uvicorn CMD, and uv non-editable install; idempotent DB provisioning SQL for dev and prod on shared PostgreSQL host.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Create multi-stage Dockerfile and update .dockerignore | 17d2490 | Dockerfile, .dockerignore |
| 2 | Update docker-compose.yml CMD override and create provision-db.sql | c72838a | docker-compose.yml, scripts/provision-db.sql |

## Verification Results

- `docker build -t geo-api-test .` — builds successfully (exit 0)
- `docker run --rm geo-api-test id` — `uid=1000(appuser) gid=1000(appuser) groups=1000(appuser)`
- `docker compose config` — validates successfully (exit 0)
- `grep -c "AS builder" Dockerfile` — 1 (multi-stage confirmed)
- `grep "CMD" Dockerfile` — exec-form JSON array, not shell form
- `grep -c "IF NOT EXISTS" scripts/provision-db.sql` — 10 (at least 8 required)
- `uv run pytest tests/ -x -q` — 490 passed, 0 failures, no regressions

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

1. **Multi-stage base image**: Used `python:3.12-slim-bookworm` for both builder and runtime stages (as specified). Builder stage installs `libgdal-dev libexpat1-dev` for fiona compilation; runtime stage installs `libgdal-dev libexpat1 postgresql-client unzip wget` for ops imports.

2. **uv --no-editable**: `uv sync --locked --no-dev --no-editable` in builder stage embeds the package into `.venv/site-packages/` rather than leaving a source pointer. This makes the `.venv` copy between stages fully self-contained.

3. **CMD override in docker-compose.yml**: Added `command: ["bash", "scripts/docker-entrypoint.sh"]` to the api service only. All other service configs (db, ollama, volumes) remain unchanged.

4. **provision-db.sql \gexec pattern**: `CREATE DATABASE` cannot run inside a DO block (transaction). Used `SELECT 'CREATE DATABASE ...' WHERE NOT EXISTS (...) \gexec` as the idempotent workaround.

5. **ALTER DEFAULT PRIVILEGES**: Added to ensure future Alembic-created tables automatically receive full access for geo_dev/geo_prod without additional grants.

## Known Stubs

None — all deliverables are complete and functional. Password placeholders (`CHANGE_ME_DEV`, `CHANGE_ME_PROD`) in provision-db.sql are intentional — operator must replace with real passwords before running against the production PostgreSQL host.

## Self-Check

Checking created/modified files exist:
- Dockerfile: FOUND
- .dockerignore: FOUND (tiger-data/ added)
- docker-compose.yml: FOUND (command override added)
- scripts/provision-db.sql: FOUND

Checking commits exist:
- 17d2490: feat(19-01): create multi-stage production Dockerfile
- c72838a: feat(19-01): add CMD override to docker-compose for dev

## Self-Check: PASSED
