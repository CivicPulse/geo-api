# Phase 23: Final Validation Checklist

**Created:** 2026-04-03
**Last run:** _not yet_
**Status:** Not started
**Pass count:** 0

## Instructions

Run each category top-to-bottom. Record PASS/FAIL with date.
- **FAIL (blocker):** Fix in-phase per VAL-01, then re-run FULL checklist from category 1.
- **FAIL (non-blocker):** Log in Non-Blockers section per VAL-02, continue.
- **Complete when:** All items show PASS with no open blockers (VAL-03).

---

## 1. Tech Debt (DEBT-01 through DEBT-04)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 1.1 | Tiger provider timeout resolved | `uv run pytest tests/test_tiger_provider.py -x` passes | | |
| 1.2 | Cache hit works on repeated calls | `uv run pytest tests/test_geocoding_service.py -k cache -x` passes | | |
| 1.3 | Spell dictionary auto-populates | `uv run pytest tests/test_spell_startup.py -x` passes | | |
| 1.4 | CLI tests pass | `uv run pytest tests/test_import_cli.py tests/test_load_oa_cli.py -x` passes | | |
| 1.5 | Full test suite passes | `uv run pytest tests/ --ignore=tests/e2e -x` passes (all non-E2E tests) | | |

## 2. Code Review (REVIEW-01 through REVIEW-03)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 2.1 | No hardcoded credentials in source | `grep -rn "CHANGEME" src/ --include="*.py"` returns only config defaults, if any | | |
| 2.2 | Input validation on geocode endpoint | `grep "max_length=500" src/civpulse_geo/schemas/geocoding.py` shows constraint | | |
| 2.3 | Provider name allowlist exists | `grep "KNOWN_PROVIDERS" src/civpulse_geo/api/geocoding.py` shows frozenset | | |
| 2.4 | Global exception handler present | `grep "exception_handler" src/civpulse_geo/main.py` shows registration | | |
| 2.5 | Pool sizing configured | `grep "db_pool_size" src/civpulse_geo/config.py src/civpulse_geo/database.py` shows explicit setting | | |

## 3. Observability (OBS-01 through OBS-04)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 3.1 | Structured JSON logging configured | `uv run pytest tests/test_logging.py -x` passes | | |
| 3.2 | Prometheus /metrics endpoint exists | `grep "generate_latest" src/civpulse_geo/api/metrics.py` | | |
| 3.3 | OTel tracing module configured | `grep "civpulse-geo" src/civpulse_geo/observability/tracing.py` shows service name | | |
| 3.4 | Request ID middleware exists | `grep "RequestIDMiddleware" src/civpulse_geo/middleware/request_id.py` | | |
| 3.5 | Metrics middleware records durations | `grep "HTTP_REQUEST_DURATION" src/civpulse_geo/middleware/metrics.py` | | |
| 3.6 | Metrics instrumentation tests pass | `uv run pytest tests/test_metrics_instrumentation.py -x` passes | | |
| 3.7 | Tracing tests pass | `uv run pytest tests/test_tracing.py -x` passes | | |
| 3.8 | Loki logs verified under load | `uv run python scripts/verify/verify_loki.py` exits 0 | | |
| 3.9 | Tempo traces verified under load | `uv run python scripts/verify/verify_tempo.py` exits 0 | | |
| 3.10 | VictoriaMetrics metrics verified | `uv run python scripts/verify/verify_victoriametrics.py` exits 0 | | |

## 4. Deployment (DEPLOY-01 through DEPLOY-08)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 4.1 | Dockerfile exists and builds | `docker build -t geo-api:test .` succeeds | | |
| 4.2 | Dockerfile uses non-root user | `grep "appuser" Dockerfile` shows USER directive | | |
| 4.3 | K8s deployment manifest exists | `test -f k8s/base/deployment.yaml` | | |
| 4.4 | K8s service manifest exists | `test -f k8s/base/service.yaml` | | |
| 4.5 | Dev overlay exists | `test -f k8s/overlays/dev/kustomization.yaml` | | |
| 4.6 | Prod overlay exists | `test -f k8s/overlays/prod/kustomization.yaml` | | |
| 4.7 | ArgoCD apps synced and healthy | `kubectl get applications -n argocd | grep geo-api` shows both Synced/Healthy; if not, apply the two ArgoCD app manifests | | |
| 4.8 | K8s Secret exists in prod | `kubectl get secret geo-api-secret -n civpulse-prod -o jsonpath='{.metadata.name}'` returns geo-api-secret | | |
| 4.9 | Pod running in prod | `kubectl get pods -n civpulse-prod -l app.kubernetes.io/name=geo-api -o jsonpath='{.items[0].status.phase}'` returns Running | | |
| 4.10 | DB reachable from pod | `kubectl port-forward -n civpulse-prod svc/geo-api 8000:8000` then `curl -sf http://localhost:8000/health/ready` returns 200 | | |

## 5. Resilience (RESIL-01 through RESIL-04)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 5.1 | Liveness probe works | `kubectl port-forward -n civpulse-prod svc/geo-api 8000:8000` then `curl -sf http://localhost:8000/health/live` returns 200 | | |
| 5.2 | Readiness probe works | `kubectl port-forward -n civpulse-prod svc/geo-api 8000:8000` then `curl -sf http://localhost:8000/health/ready` returns 200 | | |
| 5.3 | Graceful shutdown tested | `uv run pytest tests/test_shutdown.py -x` passes | | |
| 5.4 | Health tests pass | `uv run pytest tests/test_health.py -x` passes | | |
| 5.5 | Startup init containers succeed | `kubectl get pods -n civpulse-prod -l app.kubernetes.io/name=geo-api -o jsonpath='{.items[0].status.initContainerStatuses[*].ready}'` shows all true | | |

## 6. Testing (TEST-01 through TEST-06)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 6.1 | E2E geocode tests pass all 5 providers | `GEO_API_BASE_URL=http://localhost:8000 uv run pytest tests/e2e/test_providers_geocode.py -v -m e2e` (with port-forward active) | | |
| 6.2 | E2E validate tests pass all 4 providers | `GEO_API_BASE_URL=http://localhost:8000 uv run pytest tests/e2e/test_providers_validate.py -v -m e2e` (with port-forward active) | | |
| 6.3 | E2E cascade pipeline test passes | `GEO_API_BASE_URL=http://localhost:8000 uv run pytest tests/e2e/test_cascade_pipeline.py -v -m e2e` (with port-forward active) | | |
| 6.4 | Cold-cache Locust baseline captured | `locust -f loadtests/geo_api_locustfile.py --headless --users 30 --spawn-rate 0.25 --run-time 7m --host http://localhost:8000 --csv loadtests/reports/cold_cache --csv-full-history` completes with CSV output | | |
| 6.5 | Warm-cache Locust baseline captured | `GEO_LOADTEST_WARM=1 locust -f loadtests/geo_api_locustfile.py --headless --users 30 --spawn-rate 0.25 --run-time 7m --host http://localhost:8000 --csv loadtests/reports/warm_cache --csv-full-history` completes with CSV output | | |
| 6.6 | Cold-cache P95 below 10s | Review `loadtests/reports/cold_cache_stats.csv` - Aggregated row P95 < 10000ms | | |
| 6.7 | Warm-cache P95 below 2s | Review `loadtests/reports/warm_cache_stats.csv` - Aggregated row P95 < 2000ms | | |

## 7. Validation Process (VAL-01 through VAL-03)

| # | Check | Command / Verification | Status | Date |
|---|-------|------------------------|--------|------|
| 7.1 | All blockers resolved in-phase | No items in Blockers Found below, or all are resolved | | |
| 7.2 | Non-blockers logged | All non-blocker items documented in Non-Blockers Logged below | | |
| 7.3 | Full pass clean | All items in categories 1-6 show PASS | | |

---

## Blockers Found

_Items that must be fixed before the validation pass can be marked clean._

| # | Category | Item | Description | Resolution | Date Fixed |
|---|----------|------|-------------|------------|------------|
| | | | _none yet_ | | |

## Non-Blockers Logged

_Items deferred to subsequent phases or future milestones per VAL-02._

| # | Category | Item | Description | Severity | Deferred To |
|---|----------|------|-------------|----------|-------------|
| | | | _none yet_ | | |

---

## Run Log

| Run # | Date | Result | Notes |
|-------|------|--------|-------|
| | | | _not yet run_ |
