---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Production Readiness & Deployment
status: verifying
stopped_at: Phase 22 context gathered
last_updated: "2026-03-30T17:03:17.377Z"
last_activity: 2026-03-30
progress:
  total_phases: 7
  completed_phases: 5
  total_plans: 12
  completed_plans: 12
  percent: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-29)

**Core value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching, local data sources, and giving admins authority over the official answer
**Current focus:** Phase 21 — ci-cd-pipeline

## Current Position

Phase: 22
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-03-30

Progress: [█░░░░░░░░░] 7% (v1.3)

## Performance Metrics

| Milestone | Phases | Requirements | Notes |
|-----------|--------|--------------|-------|
| v1.0 | 6 | 26/26 | Shipped 2026-03-19 |
| v1.1 | 5 | 6/6 | Shipped 2026-03-29 |
| v1.2 | 5 | 25/25 | Shipped 2026-03-29 |
| v1.3 | 7 planned | 0/30 | In progress |

*Updated after each plan completion*
| Phase 18-code-review P02 | 3min | 2 tasks | 3 files |
| Phase 18-code-review P01 | 3min | 2 tasks | 10 files |
| Phase 18-code-review P03 | 10min | 2 tasks | 6 files |
| Phase 20-health-resilience-and-k8s-manifests P01 | 4min | 2 tasks | 4 files |
| Phase 20-health-resilience-and-k8s-manifests P02 | 2min | 2 tasks | 5 files |
| Phase 20-health-resilience-and-k8s-manifests P03 | 4min | 2 tasks | 9 files |
| Phase 21-ci-cd-pipeline P02 | 2min | 2 tasks | 2 files |
| Phase 21-ci-cd-pipeline P01 | 2min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

Key decisions affecting v1.3 execution:

- [Phase 17-tech-debt-resolution]: DEBT-03: Only auto-rebuild when spell_dictionary is empty — never TRUNCATE on every restart (D-08)
- [Phase 17-tech-debt-resolution]: DEBT-03: Only rebuild when staging tables have data — skip with warning when no source data (D-07)

- [Phase 17-01]: DEBT-04: accuracy parser uses None default (not 'parcel') — empty string from OA features must not become a fake accuracy value
- [Phase 17-01]: DEBT-01: tiger_timeout_ms=3000 separate from exact_match_timeout_ms=2000 — PostGIS geocode() needs more time than HTTP providers
- [Phase 17-01]: DEBT-01: _timeout_map dict inside _call_provider — reads current settings at call time for test patchability
- [Phase 17-01]: DEBT-02: selectinload(Address.geocoding_results) in Stage 1 query — required for cache detection without N+1 lazy load
- [Phase 17-01]: DEBT-02: would_set_official wired from consensus winning cluster best candidate on cache hit — D-05 retroactive provider weight changes
- [Infra]: Ollama sidecar (not standalone Deployment) — shares Pod network, httpx to localhost:11434
- [Infra]: No transaction-mode PgBouncer assumed — must confirm in Phase 19 or set prepared_statement_cache_size=0
- [Infra]: k3s StorageClass for Ollama PVC assumed to be local-path — verify with kubectl get storageclass in Phase 19
- [CI/CD]: ArgoCD Image Updater vs. manifest-commit strategy is mutually exclusive — decision required in Phase 21 planning
- [OTel]: opentelemetry-instrumentation-logging has no effect on Loguru — must use logger.configure(patcher=add_otel_context) custom pattern
- [Phase 18]: Code review uses three parallel agent teams: security, stability, performance
- [Phase 18-code-review]: TestClient(raise_server_exceptions=False) required for generic exception handler testing in Starlette 0.52 — ASGITransport ServerErrorMiddleware re-raises exceptions before handler fires
- [Phase 18-code-review]: Per-provider try/except wraps entire remote loop body (including DB upsert) so any error during result handling also degrades gracefully (STAB-04)
- [Phase 18-code-review]: CHANGEME placeholders in config.py defaults allow Settings() instantiation without .env while making required credentials obvious; Field(required=...) would break pytest
- [Phase 18-code-review]: KNOWN_PROVIDERS frozenset in api/geocoding.py as module-level allowlist — O(1) check before service dispatch, sanitized error messages prevent input reflection
- [Phase 18-code-review]: Annotated[str, Field(min_length=1, max_length=500)] for per-item constraints in Pydantic v2 list fields (batch schemas)
- [Phase 18-code-review]: PERF-01: db_pool_size=5, db_max_overflow=5 (max 10 connections per worker) — within PostgreSQL default 100 max_connections for single-replica K8s deployment
- [Phase 18-code-review]: PERF-06: weight_map now uses 'postgis_tiger' and 'national_address_database' matching main.py registration — old 'tiger'/'nad' aliases removed; pool_pre_ping hardcoded True in database.py
- [Phase 20-01]: /health/live has NO Depends -- returns 200 if process is alive (RESIL-01); /health/ready checks DB and >= 2 geocoding/validation providers (RESIL-02); Shutdown order: http_client.aclose() then engine.dispose(); ASGITransport does not trigger ASGI lifespan -- shutdown tests use lifespan(app) context manager directly
- [Phase 20-health-resilience-and-k8s-manifests]: Ollama native sidecar as last initContainer (restartPolicy: Always) — guarantees Ollama ready before geo-api main container
- [Phase 20-health-resilience-and-k8s-manifests]: db-wait init container uses pg_isready (postgresql-client from Phase 19 Dockerfile) before alembic-migrate
- [Phase 20-health-resilience-and-k8s-manifests]: model-pull skip-if-cached guard (ollama list | grep qwen2.5:3b) avoids 2GB re-download on pod restarts
- [Phase 20-health-resilience-and-k8s-manifests]: ArgoCD Application CRs must be applied directly (kubectl apply -f) not via kustomize build — top-level namespace: field overrides Application namespace in kustomize v5.0.4 output
- [Phase 20-health-resilience-and-k8s-manifests]: Secrets excluded from Kustomize resources per D-06/Pitfall 3 — ArgoCD selfHeal would overwrite real credentials with CHANGEME placeholders if managed via kustomize
- [Phase 21-ci-cd-pipeline]: D-01 manifest-commit strategy: kustomize edit set image updates k8s/overlays/dev/kustomization.yaml, ArgoCD automated sync deploys
- [Phase 21-ci-cd-pipeline]: D-09 SHA-pinned actions enforced across all workflow files (Trivy supply chain compromise mitigation, March 2026)
- [Phase 21-ci-cd-pipeline]: Loop prevention belt-and-suspenders: paths-ignore k8s/overlays/** (primary) + [skip ci] in automated commit messages (secondary)
- [Phase 21-ci-cd-pipeline]: All GitHub Actions pinned to full 40-char commit SHAs per D-09 (Trivy supply chain compromise March 2026)
- [Phase 21-ci-cd-pipeline]: ci.yml uses permissions: contents: read (least-privilege per D-08); write permissions in cd.yml only
- [Phase 21-ci-cd-pipeline]: ruff installed via astral-sh/ruff-action in CI, not as project dev dep; [tool.ruff] target-version=py312 ensures CI/local parity

### Phase Ordering Constraint

17 (debt) → 18 (review) → 19 (Dockerfile + DB) → 20 (health + K8s manifests) → 21 (CI/CD) → 22 (observability) → 23 (E2E + validation)

Each phase is a hard gate for the next. Infrastructure prerequisites (DNS, DB connectivity) validated in Phase 19 before any pod deployment.

### Pending Todos

None.

### Blockers/Concerns (Carry Forward from v1.2)

- Tiger 2000ms timeout under load — RESOLVED by Phase 17 Plan 1 (DEBT-01)
- cache_hit hardcoded False — RESOLVED by Phase 17 Plan 1 (DEBT-02)
- OA accuracy empty string defaulting to 'parcel' — RESOLVED by Phase 17 Plan 1 (DEBT-04)
- Spell dictionary empty at startup — addressed in Phase 17 Plan 2 (DEBT-03)

## Session Continuity

Last activity: 2026-03-29 — Phase 17 Plans 1 & 2 complete
Stopped at: Phase 22 context gathered
Resume file: .planning/phases/22-observability/22-CONTEXT.md
Next action: Phase 17 verification
