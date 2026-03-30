---
phase: 19-dockerfile-and-database-provisioning
plan: "02"
subsystem: infra
tags: [ghcr, docker, postgresql, k8s, connectivity, provisioning, alembic]
dependency_graph:
  requires: [19-01]
  provides: [DEPLOY-01-validated, DEPLOY-08-validated]
  affects: [20-health-resilience-and-k8s-manifests, 21-ci-cd-pipeline]
tech_stack:
  added: []
  patterns:
    - GHCR sha-tag + latest for image tagging
    - Headless K8s Service proxy to host PostgreSQL
    - Separate databases per environment (civpulse_geo_dev, civpulse_geo_prod) with dedicated users
key_files:
  created: []
  modified: []
key_decisions:
  - "GHCR package set to public — no imagePullSecret needed for k3s"
  - "Database passwords generated with openssl rand — stored for Phase 20 K8s Secrets"
  - "Extensions installed as postgres superuser, default privileges granted to app users"
  - "Alembic migrations run against both databases — all 8 migrations applied (12 tables each)"
patterns_established:
  - "K8s connectivity testing pattern: kubectl run ephemeral postgres:16 pod with PGPASSWORD env"
  - "Database provisioning pattern: roles via DO block, databases via standalone CREATE DATABASE, extensions as superuser"
requirements_completed: [DEPLOY-01, DEPLOY-08]
duration: 12min
completed: 2026-03-29
---

# Phase 19 Plan 02: GHCR Push, DB Provisioning, and K8s Connectivity

**Docker image pushed to ghcr.io/civicpulse/geo-api:sha-42d5282 (public), both dev/prod databases provisioned on host PG with PostGIS/pg_trgm/fuzzystrmatch, Alembic migrations applied (12 tables), and connectivity verified from K8s pods in both namespaces**

## Performance

- **Duration:** 12 min
- **Tasks:** 3
- **Files modified:** 0 (infrastructure operations only)

## Accomplishments
- Docker image built and pushed to GHCR with sha-42d5282 and latest tags, pullable by k3s (uid=1000 appuser confirmed)
- civpulse_geo_dev and civpulse_geo_prod databases provisioned on shared host PostgreSQL (thor.tailb56d83.ts.net) with geo_dev/geo_prod users
- PostGIS 3.4, pg_trgm, and fuzzystrmatch extensions enabled and functional in both databases
- All 8 Alembic migrations applied to both databases (12 application tables each)
- End-to-end connectivity verified: K8s pods in civpulse-dev and civpulse-prod namespaces connect via postgresql.civpulse-infra.svc.cluster.local:5432
- Extension functions verified from K8s pods: similarity() returns 0.111, soundex() returns T230

## Task Commits

1. **Task 1: Build and push Docker image to GHCR** — infrastructure operation, no file changes
2. **Task 2: Provision databases on host PostgreSQL** — manual checkpoint, SQL + Alembic against live server
3. **Task 3: K8s pod connectivity tests** — kubectl validation, no file changes

## Decisions Made
- GHCR package visibility set to public (required for k3s pull without imagePullSecret)
- Passwords generated via openssl rand -base64 (32 chars each) — needed in Phase 20 K8s Secrets
- Alembic migrations run in this phase (satisfies ROADMAP success criterion 3)

## Deviations from Plan
- Initial k3s pull test timed out on first image pull — succeeded with longer timeout
- GHCR package defaulted to private — resolved by setting to public
- Alembic migrations run here rather than deferring entirely to Phase 20 init containers

## Issues Encountered
- kubectl run --rm -i can timeout before large image pull completes — use --pod-running-timeout=180s

## Next Phase Readiness
- Docker image at ghcr.io/civicpulse/geo-api:sha-42d5282 and :latest — Phase 20 can reference it
- Both databases fully migrated — Phase 20 init containers run alembic upgrade head idempotently
- Database passwords needed in Phase 20 for K8s Secret creation (DEPLOY-05)
- postgresql.civpulse-infra.svc.cluster.local:5432 reachable from both namespaces

---
*Phase: 19-dockerfile-and-database-provisioning*
*Completed: 2026-03-29*
