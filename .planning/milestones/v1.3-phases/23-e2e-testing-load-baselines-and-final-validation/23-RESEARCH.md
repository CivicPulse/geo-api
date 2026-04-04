# Phase 23: E2E Testing, Load Baselines, and Final Validation - Research

**Researched:** 2026-03-30
**Domain:** pytest E2E testing against real HTTP; Locust load testing; Loki/Tempo/VictoriaMetrics query API verification; kubectl port-forward connectivity
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**E2E Test Execution**
- D-01: E2E tests live in `tests/e2e/` directory, separate from unit tests. Distinguished by pytest markers (`@pytest.mark.e2e`) for selective runs.
- D-02: Framework is pytest + httpx hitting real HTTP endpoints (same stack as unit tests, familiar patterns).
- D-03: Tests connect to deployed service via `kubectl port-forward` — no cluster changes needed.
- D-04: Test data uses a per-provider fixture file (JSON/YAML) mapping each provider to known-good addresses. Primary addresses are real Macon-Bibb County addresses since GIS data is loaded for that jurisdiction.
- D-05: E2E tests cover all 5 providers (geocode + validate per provider) plus a full cascade pipeline E2E test per TEST-01 and TEST-02.

**Load Test Design**
- D-06: Locust load test files live in `loadtests/` at project root (separate from pytest tests — Locust runs via its own CLI).
- D-07: Cold-cache and warm-cache are separate Locust runs with separate reports. Run 1: unique addresses (cold). Run 2: repeated addresses (warm).
- D-08: Load tests exercise `/geocode` (single), `/validate` (single), and cascade pipeline endpoints. Batch endpoints excluded from baseline runs to avoid skewing latency profiles.
- D-09: Ramp-up profile: 0→30 users over 2 minutes, sustain 30 users for 5 minutes (~7 min total per run). Produces stable P50/P95/P99 percentiles.

**Observability Verification**
- D-10: Verification uses Python scripts with httpx in `scripts/verify/`, querying Loki, Tempo, and VictoriaMetrics APIs after load tests complete.
- D-11: Scripts assert: (a) structured JSON logs in Loki with `request_id` and `trace_id` fields (TEST-04), (b) traces in Tempo with DB and provider child spans (TEST-05), (c) metrics in VictoriaMetrics with correct labels — request rate, latency histograms, error rate (TEST-06).
- D-12: Scripts exit non-zero on assertion failures for scripted pipeline use.

**Final Validation Pass**
- D-13: Validation is a structured Markdown checklist (`23-VALIDATION-CHECKLIST.md`) in the phase directory covering all 7 categories: debt, review, observability, deployment, resilience, testing, validation.
- D-14: Blockers found during the pass are fixed in-phase per VAL-01, then the FULL validation pass is re-run until clean (not just the failed category).
- D-15: Non-blockers are logged per VAL-02 for subsequent phases or future milestones.
- D-16: Results recorded directly in the checklist with dates and pass/fail status for audit trail.

### Claude's Discretion
- Specific Macon-Bibb addresses to include in the fixture file (based on loaded GIS data)
- Locust task weighting between geocode/validate/cascade endpoints
- Exact Loki/Tempo/VictoriaMetrics query syntax in verification scripts
- Validation checklist item granularity within each of the 7 categories
- Whether to include a helper script/Makefile target to orchestrate the port-forward + test run

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | E2E tests for all 5 providers against deployed prod (geocode + validate per provider) | pytest + httpx AsyncClient with real base URL; port-forward connectivity pattern; per-provider fixture file |
| TEST-02 | E2E test of full cascade pipeline end-to-end on deployed prod | POST /geocode with degraded input; assert `cascade_trace` stages populated and `would_set_official` set |
| TEST-03 | Locust load tests with cold-cache/warm-cache separation, P50/P95/P99 baselines derived | Locust 2.43.3 `--headless --csv` mode; 30 users / 2-min ramp / 5-min sustain |
| TEST-04 | Logs verified in Loki under load (structured JSON, request_id, trace correlation) | Loki LogQL query via `GET /loki/api/v1/query_range`; httpx script asserting `request_id` and `trace_id` fields present |
| TEST-05 | Traces verified in Tempo under load (request spans, DB spans, provider spans) | Tempo TraceQL search via `GET /api/search`; assert child spans with `db.system` and `provider` attributes |
| TEST-06 | Metrics verified in VictoriaMetrics under load (request rate, latency histograms, error rate) | VictoriaMetrics PromQL query via `GET /api/v1/query`; assert `http_requests_total`, `http_request_duration_seconds`, `geo_provider_requests_total` |
| VAL-01 | Blockers identified during any phase are resolved within that phase before proceeding | Checklist-driven: any FAIL item in 7 categories triggers in-phase fix + full re-run |
| VAL-02 | Non-blockers logged and planned for subsequent bug-fix phases | Non-blocker section in checklist with date and severity tag |
| VAL-03 | Final top-to-bottom validation pass covering all categories passes clean | 23-VALIDATION-CHECKLIST.md all items PASS with no open blockers |
</phase_requirements>

---

## Summary

Phase 23 is a validation-and-measurement phase, not a feature phase. The primary deliverables are: (1) an E2E pytest suite in `tests/e2e/` that exercises all 5 providers against deployed prod via port-forward, (2) Locust load tests in `loadtests/` producing cold and warm latency baseline CSV reports, (3) Python verification scripts in `scripts/verify/` that query Loki, Tempo, and VictoriaMetrics APIs to assert observability is working under load, and (4) a structured `23-VALIDATION-CHECKLIST.md` that is run repeatedly until clean.

The critical prerequisite is that geo-api is deployed to `civpulse-prod` namespace before any E2E or load test can run. The ArgoCD Application CRs exist in the repo (`k8s/overlays/prod/argocd-app.yaml`) but have not been applied to the cluster yet — no `geo-api-prod` or `geo-api-dev` ArgoCD app currently exists. DEPLOY-01 (Dockerfile) and DEPLOY-08 (DB provisioning) are also still marked pending in REQUIREMENTS.md. The planner must include a Wave 0 or prerequisite task to apply the ArgoCD apps, create the K8s Secrets with real DB credentials, and confirm pod is Running before E2E tests can execute.

The observability backends (Loki port 3100, Tempo port 3200, VictoriaMetrics port 8428) are all ClusterIP-only services in `civpulse-infra`. Verification scripts reach them via `kubectl port-forward`. All five providers have separate registration guards in `main.py` — the E2E fixture file must use addresses from the Macon-Bibb jurisdiction where data is confirmed loaded.

**Primary recommendation:** Structure the phase into 4 plans: (1) deployment prerequisite + E2E suite scaffolding, (2) Locust load baselines, (3) observability verification scripts, (4) final validation pass + checklist.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | E2E test runner | Already installed; `asyncio_mode=auto` configured in pyproject.toml |
| pytest-asyncio | 1.3.0 | Async test support | Already installed; project uses async pattern throughout |
| httpx | 0.28.1 | HTTP client for E2E tests | Already installed; used in all providers and existing tests |
| locust | 2.43.3 | Load testing | Latest stable; headless CSV mode for baseline capture |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | 1.3.0 | async fixture support | E2E conftest needs async fixtures for httpx.AsyncClient |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| locust | k6, wrk, ab | Locust is Python-native, programmable test logic, CSV output; k6 requires JS; wrk/ab lack per-endpoint breakdown |
| httpx in verify scripts | requests | httpx already a project dep; consistent with provider pattern |

**Installation:**
```bash
uv add --dev locust
```

**Version verification:**
```
locust: 2.43.3 (verified via uv pip index versions, 2026-03-30)
pytest: 9.0.2 (already installed)
httpx: 0.28.1 (already installed)
pytest-asyncio: 1.3.0 (already installed)
```

---

## Architecture Patterns

### Recommended Project Structure
```
tests/
└── e2e/
    ├── conftest.py            # E2E-specific fixtures: base_url from env, AsyncClient
    ├── fixtures/
    │   └── provider_addresses.yaml  # per-provider known-good address data
    ├── test_providers_geocode.py    # TEST-01: geocode per provider
    ├── test_providers_validate.py   # TEST-01: validate per provider
    └── test_cascade_pipeline.py     # TEST-02: full cascade E2E

loadtests/
├── geo_api_locustfile.py      # Locust HttpUser task definitions
├── addresses/
│   ├── cold_cache_addresses.txt     # unique addresses for cold-cache run
│   └── warm_cache_addresses.txt     # repeated subset for warm-cache run
└── reports/                         # gitignored; Locust CSV output lands here

scripts/
└── verify/
    ├── verify_loki.py         # TEST-04: Loki LogQL query + assertions
    ├── verify_tempo.py        # TEST-05: Tempo TraceQL search + assertions
    └── verify_victoriametrics.py    # TEST-06: VM PromQL query + assertions

.planning/phases/23-e2e-testing-load-baselines-and-final-validation/
└── 23-VALIDATION-CHECKLIST.md      # VAL-03: 7-category final validation pass
```

### Pattern 1: E2E conftest with real HTTP base URL

**What:** E2E tests use `httpx.AsyncClient` with a real `base_url` sourced from env var. The fixture is distinct from the unit test `ASGITransport` pattern.
**When to use:** All `tests/e2e/` test files.

```python
# tests/e2e/conftest.py
import os
import pytest
import httpx

E2E_BASE_URL = os.environ.get("GEO_API_BASE_URL", "http://localhost:8000")

@pytest.fixture
async def e2e_client():
    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=30.0) as client:
        yield client

@pytest.fixture(scope="session")
def provider_addresses():
    """Load per-provider test address fixtures."""
    import yaml
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "provider_addresses.yaml")
    with open(fixture_path) as f:
        return yaml.safe_load(f)
```

### Pattern 2: Provider E2E test with pytest parametrize

**What:** Parametrize over providers from the fixture file — one test invocation per provider. Use `@pytest.mark.e2e` to distinguish from unit tests.
**When to use:** `test_providers_geocode.py` and `test_providers_validate.py`.

```python
# tests/e2e/test_providers_geocode.py
import pytest

pytestmark = pytest.mark.e2e

@pytest.mark.parametrize("provider_name", [
    "census", "openaddresses", "postgis_tiger",
    "national_address_database", "macon_bibb"
])
async def test_geocode_provider(e2e_client, provider_addresses, provider_name):
    address = provider_addresses[provider_name]["geocode_address"]
    resp = await e2e_client.post("/geocode", json={"address": address})
    assert resp.status_code == 200
    body = resp.json()
    assert body["address_hash"]
    # At least one result returned
    all_results = body["results"] + body.get("local_results", [])
    providers = [r["provider_name"] for r in all_results]
    assert provider_name in providers, f"{provider_name} not in results: {providers}"
```

### Pattern 3: Cascade pipeline E2E test

**What:** POST a degraded/misspelled address with `trace=true` and assert the cascade stages fired and produced an official result.
**When to use:** `test_cascade_pipeline.py` (TEST-02).

```python
async def test_cascade_pipeline_resolves_degraded_input(e2e_client):
    # A slightly misspelled Macon-Bibb address forces spell-correct + cascade
    resp = await e2e_client.post(
        "/geocode",
        params={"trace": "true", "dry_run": "true"},
        json={"address": "123 Coliseum Dr, Mcon, GA 31201"},
    )
    assert resp.status_code == 200
    body = resp.json()
    trace = body.get("cascade_trace", [])
    stage_names = [s["stage"] for s in trace]
    assert "spell_correct" in stage_names or len(body["results"]) > 0
    # Official or would_set_official should be set after cascade
    assert body.get("would_set_official") is not None or body.get("official") is not None
```

### Pattern 4: Locust headless run with CSV output

**What:** `locust` CLI in `--headless` mode with `--csv` for machine-readable P50/P95/P99 output. Two separate invocations for cold and warm cache.
**When to use:** Load baseline capture (TEST-03).

```bash
# Cold-cache run (unique addresses)
locust -f loadtests/geo_api_locustfile.py \
  --headless \
  --users 30 \
  --spawn-rate 0.25 \
  --run-time 7m \
  --host http://localhost:8000 \
  --csv loadtests/reports/cold_cache \
  --csv-full-history

# Warm-cache run (repeated addresses — flush between runs OR run second)
locust -f loadtests/geo_api_locustfile.py \
  --headless \
  --users 30 \
  --spawn-rate 0.25 \
  --run-time 7m \
  --host http://localhost:8000 \
  --csv loadtests/reports/warm_cache \
  --csv-full-history
```

Spawn rate: 30 users / 120 seconds = 0.25 users/sec. This matches the D-09 ramp profile of 0→30 users over 2 minutes.

### Pattern 5: Locust HttpUser task file

**What:** A single `HttpUser` class with weighted tasks for geocode, validate, and cascade endpoints.
**When to use:** `loadtests/geo_api_locustfile.py`.

```python
# loadtests/geo_api_locustfile.py
import random
from locust import HttpUser, task, between

GEOCODE_ADDRESSES = [...]   # loaded from addresses/cold_cache_addresses.txt
VALIDATE_ADDRESSES = [...]

class GeoApiUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(5)
    def geocode(self):
        addr = random.choice(GEOCODE_ADDRESSES)
        self.client.post("/geocode", json={"address": addr})

    @task(3)
    def validate(self):
        addr = random.choice(VALIDATE_ADDRESSES)
        self.client.post("/validate", json={"address": addr})

    @task(2)
    def cascade_trace(self):
        addr = random.choice(GEOCODE_ADDRESSES)
        self.client.post("/geocode", json={"address": addr},
                        params={"trace": "true"})
```

### Pattern 6: Observability verification scripts

**What:** httpx sync or async scripts that port-forward to the observability backends and assert data is present.
**When to use:** `scripts/verify/*.py` (TEST-04, TEST-05, TEST-06). Scripts exit non-zero on failures (D-12).

```python
# scripts/verify/verify_loki.py  (simplified)
import sys
import json
import httpx

LOKI_URL = "http://localhost:3100"  # reached via kubectl port-forward

def verify_loki_logs():
    # LogQL: find log lines in last 30 minutes with request_id field
    params = {
        "query": '{service="civpulse-geo"} | json | request_id != ""',
        "start": str(int((time.time() - 1800) * 1e9)),
        "end": str(int(time.time() * 1e9)),
        "limit": 100,
    }
    r = httpx.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params)
    r.raise_for_status()
    results = r.json()["data"]["result"]
    if not results:
        print("FAIL: No logs found in Loki with service=civpulse-geo and request_id", file=sys.stderr)
        sys.exit(1)
    # Check trace_id present
    for stream in results:
        for ts, line in stream["values"]:
            entry = json.loads(line)
            assert "trace_id" in entry, f"FAIL: trace_id missing from log entry: {entry}"
    print(f"PASS: {sum(len(s['values']) for s in results)} log entries verified")

if __name__ == "__main__":
    verify_loki_logs()
```

### Pattern 7: kubectl port-forward for E2E connectivity

**What:** Start a port-forward in background before running E2E tests. The E2E conftest expects the service at `GEO_API_BASE_URL` (default `http://localhost:8000`).
**When to use:** Described in test README or Makefile target.

```bash
# Start port-forward to geo-api in prod namespace
kubectl port-forward -n civpulse-prod svc/geo-api 8000:8000 &
PF_PID=$!

# Run E2E tests
GEO_API_BASE_URL=http://localhost:8000 uv run pytest tests/e2e/ -v -m e2e

# Cleanup
kill $PF_PID
```

### Anti-Patterns to Avoid

- **Using ASGITransport in E2E tests:** E2E tests must use real HTTP — using ASGITransport bypasses middleware, OTel instrumentation, and the deployed environment entirely.
- **Sharing fixtures between unit and E2E conftest:** The `tests/e2e/conftest.py` is a separate conftest. Do NOT import from `tests/conftest.py` — the app instance, `override_db`, and `ASGITransport` fixtures are incompatible with E2E intent.
- **Running Locust with web UI in baseline capture:** Always use `--headless` for reproducible automated runs. The web UI is for exploratory use only.
- **Mixing cold/warm addresses in one Locust run:** Cold and warm cache runs MUST be separate invocations with separate address pools to avoid statistical contamination (D-07).
- **Hardcoding VictoriaMetrics pod IP:** VictoriaMetrics uses a headless Service (ClusterIP: None). Always port-forward to the pod: `kubectl port-forward -n civpulse-infra pod/victoria-metrics-victoria-metrics-single-server-0 8428:8428`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP load generation | Custom asyncio loop | Locust 2.43.3 | Built-in P50/P95/P99 statistics, CSV output, correct spawn rate math |
| Percentile calculation | Manual CSV aggregation | Locust `--csv` output | `_stats.csv` has per-endpoint percentiles already computed |
| Loki log querying | Parsing raw stdout logs | Loki HTTP API `/loki/api/v1/query_range` | Structured query against indexed data |
| Tempo trace querying | OTel collector inspection | Tempo HTTP API `/api/search` and `/api/traces/{traceID}` | Search by service name and time range |
| PromQL execution | Direct scrape endpoint parse | VictoriaMetrics `/api/v1/query` | PromQL supports rate/histogram queries needed for latency validation |
| Port-forward lifecycle | K8s client Python library | `kubectl port-forward` via subprocess | Simple, no extra Python deps, works identically to developer workflow |

**Key insight:** All three observability backends have stable HTTP query APIs. The verification scripts need only `httpx` (already installed) plus `kubectl port-forward` for access. No additional observability client libraries needed.

---

## Common Pitfalls

### Pitfall 1: geo-api not deployed before running E2E tests

**What goes wrong:** E2E tests fail with connection refused — geo-api pod doesn't exist in `civpulse-prod`.
**Why it happens:** ArgoCD Application CRs are in the repo but have never been applied to the cluster. `kubectl get applications -n argocd` confirms `geo-api-prod` and `geo-api-dev` are absent.
**How to avoid:** Wave 0 task must apply the ArgoCD apps AND create the K8s Secrets with real credentials, then wait for pod to become Running. DEPLOY-01 (Dockerfile) and DEPLOY-08 (DB provisioning) are still marked pending in REQUIREMENTS.md and must be verified complete.
**Warning signs:** `kubectl get pods -n civpulse-prod | grep geo-api` returns nothing.

### Pitfall 2: E2E marker not registered in pyproject.toml

**What goes wrong:** `pytest --markers` warns about unknown marker `e2e`; CI may fail with strict marker enforcement.
**Why it happens:** `pyproject.toml` currently only registers the `tiger` marker. The `e2e` marker must be added.
**How to avoid:** Add `"e2e: marks tests as end-to-end requiring a deployed service"` to `[tool.pytest.ini_options] markers` in `pyproject.toml`.
**Warning signs:** `PytestUnknownMarkWarning` in test output.

### Pitfall 3: Provider not registered because data tables are empty

**What goes wrong:** E2E test asserts `provider_name in results` but the provider was never registered at startup.
**Why it happens:** `main.py` guards each provider registration with a data-availability check (`_*_data_available()`). If OA/NAD/Tiger/Macon-Bibb staging tables are empty in prod, those providers won't appear in results.
**How to avoid:** Verify `/health/ready` returns 200 AND check provider count before running E2E. The ready endpoint returns 200 only when >= 2 geocoding and >= 2 validation providers are registered. Consider adding an E2E fixture that polls `/health/ready` before the test session starts.
**Warning signs:** `local_results` is empty for local providers; `results` contains only `census`.

### Pitfall 4: VictoriaMetrics headless Service requires pod-targeted port-forward

**What goes wrong:** `kubectl port-forward svc/victoria-metrics-victoria-metrics-single-server` fails — headless Services (ClusterIP: None) cannot be port-forwarded via the Service object.
**Why it happens:** Headless Services have no cluster IP, so there's no stable endpoint to forward.
**How to avoid:** Port-forward directly to the pod: `kubectl port-forward -n civpulse-infra pod/victoria-metrics-victoria-metrics-single-server-0 8428:8428`.
**Warning signs:** `error: Service victoria-metrics-victoria-metrics-single-server does not have a cluster IP`.

### Pitfall 5: Locust `spawn_rate` math for 2-minute ramp

**What goes wrong:** Ramp completes in wrong time window, corrupting cold vs. warm separation.
**Why it happens:** D-09 specifies 0→30 users over 2 minutes = 30 users / 120 seconds = 0.25 users/sec. Using `--spawn-rate 1` (default) ramps in 30 seconds, not 2 minutes.
**How to avoid:** Explicitly pass `--spawn-rate 0.25` in the Locust CLI command.
**Warning signs:** Locust output shows all users active well before the 2-minute mark.

### Pitfall 6: Loki query returns empty if service label not matching

**What goes wrong:** LogQL query `{service="civpulse-geo"}` returns no results.
**Why it happens:** Grafana Alloy scrapes pod logs and applies its own labels. The actual label key/value depends on Alloy's pipeline config. The `service` label in the JSON log body differs from Alloy's `service_name` stream label.
**How to avoid:** Use a broader label selector `{namespace="civpulse-prod"}` combined with JSON filter `| json | service="civpulse-geo"` OR use `{app_kubernetes_io_name="geo-api"}` if Alloy uses k8s labels. Verify label availability by browsing Loki labels in Grafana before writing the assertion query.
**Warning signs:** Query returns 0 streams but pod logs are visible in Grafana.

### Pitfall 7: Tempo search returns no traces if OTLP export failed

**What goes wrong:** `GET /api/search` returns no traces despite requests being made.
**Why it happens:** OTLP export to Tempo requires the pod's `OTEL_EXPORTER_OTLP_ENDPOINT` to be set to `http://tempo.civpulse-infra.svc.cluster.local:4317`. The base ConfigMap has this value. However, if `otel_enabled=false` in the overlay ConfigMap or the endpoint is misconfigured, no traces reach Tempo.
**How to avoid:** Verify `OTEL_ENABLED=true` and correct endpoint in prod ConfigMap patch. Confirm BatchSpanProcessor is flushing by checking pod logs for the "OpenTelemetry tracing initialized" message.
**Warning signs:** Prod pod logs show `otel_enabled=False`; Tempo `/api/search` returns empty.

### Pitfall 8: pytest-asyncio 1.3.0 fixture scope in E2E conftest

**What goes wrong:** `ScopeMismatchError` when using session-scoped async fixtures.
**Why it happens:** pytest-asyncio 1.3.0 supports session-scoped async fixtures but the event loop scope must be explicitly set.
**How to avoid:** Use function-scoped `e2e_client` fixture (creates a new `AsyncClient` per test). Session-scoped fixtures are fine for non-async data like `provider_addresses`. Keep async fixtures at function scope.
**Warning signs:** `ScopeMismatchError: 'session'-scoped fixture cannot use 'function'-scoped fixture`.

---

## Code Examples

Verified patterns from existing codebase:

### Existing unit test async client pattern (for contrast)
```python
# tests/conftest.py — DO NOT use in E2E tests
# Source: /home/kwhatcher/projects/civicpulse/geo-api/tests/conftest.py
@pytest.fixture
async def test_client():
    transport = ASGITransport(app=app)  # in-process — NO real HTTP, NO middleware cascade
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

### Real HTTP E2E client (what E2E tests must use)
```python
# tests/e2e/conftest.py
import os, pytest, httpx

@pytest.fixture
async def e2e_client():
    base_url = os.environ.get("GEO_API_BASE_URL", "http://localhost:8000")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        yield client
```

### Provider registration guard (shows why data tables must be loaded)
```python
# Source: src/civpulse_geo/main.py (confirmed pattern)
if _macon_bibb_data_available():
    app.state.validation_providers["macon_bibb"] = MaconBibbValidationProvider(AsyncSessionLocal)
else:
    logger.warning("macon_bibb_points table is empty — Macon-Bibb provider not registered")
```

### Loki LogQL structured JSON query
```
# Source: Loki HTTP API docs (standard LogQL syntax)
GET /loki/api/v1/query_range
  ?query={namespace="civpulse-prod"} | json | request_id != "" | trace_id != ""
  &start=<unix-ns>
  &end=<unix-ns>
  &limit=100
```

### VictoriaMetrics PromQL query for latency
```
# Source: VictoriaMetrics HTTP API docs (PromQL compatible)
GET /api/v1/query
  ?query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="geo-api"}[5m]))

# For request rate
GET /api/v1/query
  ?query=rate(http_requests_total{job="geo-api"}[1m])
```

### Tempo search for recent traces
```
# Source: Tempo HTTP API docs
GET /api/search
  ?tags=service.name%3Dcivpulse-geo
  &start=<unix-seconds>
  &end=<unix-seconds>
  &limit=20
```

### Locust CSV output columns (for baseline reporting)
Locust `--csv` produces `{prefix}_stats.csv` with columns including:
- `Name` — endpoint name (e.g., "POST /geocode")
- `50%`, `66%`, `75%`, `80%`, `90%`, `95%`, `98%`, `99%`, `99.9%`, `99.99%`, `100%` — response time percentiles in ms
- `Requests/s` — throughput
- `Failures/s` — failure rate

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| kubectl | E2E port-forward, observability port-forward | ✓ | current context: default | — |
| civpulse-prod namespace | E2E tests | ✓ | Active | — |
| civpulse-infra namespace | Observability verify | ✓ | Active | — |
| Loki (svc, port 3100) | TEST-04 | ✓ | Running (28d) | — |
| Tempo (svc, port 3200) | TEST-05 | ✓ | Running (28d) | — |
| VictoriaMetrics (pod, port 8428) | TEST-06 | ✓ | Running (28d) | — |
| geo-api pod in civpulse-prod | TEST-01, TEST-02, TEST-03 | **✗** | Not deployed | Deploy in Wave 0 |
| ArgoCD Application CRs applied | geo-api deployment | **✗** | geo-api-prod/dev absent from ArgoCD | Apply `kubectl apply -f k8s/overlays/prod/argocd-app.yaml` |
| K8s Secret `geo-api-secret` in civpulse-prod | geo-api DB connectivity | **✗** | Not created | Create manually with real DB credentials |
| locust | TEST-03 | **✗** | Not installed | `uv add --dev locust` in Wave 0 |
| pyyaml (for fixture loading) | TEST-01, TEST-02 | Check — likely present via other dep | — | `uv add --dev pyyaml` |

**Missing dependencies with no fallback:**
- geo-api pod must be deployed and Running in `civpulse-prod` before any E2E or load test. This requires applying ArgoCD apps + creating K8s Secrets + verifying image built in GHCR.
- K8s Secret `geo-api-secret` with real DB credentials must be created manually in `civpulse-prod` (excluded from Kustomize per D-06 of Phase 20).

**Missing dependencies with fallback:**
- locust: install via `uv add --dev locust` (Wave 0)
- pyyaml: install via `uv add --dev pyyaml` if not already a transitive dep

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| E2E only command | `uv run pytest tests/e2e/ -v -m e2e` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | All 5 providers return geocode results | E2E (real HTTP) | `uv run pytest tests/e2e/test_providers_geocode.py -v -m e2e` | ❌ Wave 0 |
| TEST-01 | All 5 providers return validate results | E2E (real HTTP) | `uv run pytest tests/e2e/test_providers_validate.py -v -m e2e` | ❌ Wave 0 |
| TEST-02 | Cascade resolves degraded address end-to-end | E2E (real HTTP) | `uv run pytest tests/e2e/test_cascade_pipeline.py -v -m e2e` | ❌ Wave 0 |
| TEST-03 | P50/P95/P99 baselines captured | Load test (Locust CLI) | `locust -f loadtests/geo_api_locustfile.py --headless ...` | ❌ Wave 0 |
| TEST-04 | Loki has structured JSON logs with request_id + trace_id | Integration script | `uv run python scripts/verify/verify_loki.py` | ❌ Wave 0 |
| TEST-05 | Tempo has request+DB+provider spans | Integration script | `uv run python scripts/verify/verify_tempo.py` | ❌ Wave 0 |
| TEST-06 | VictoriaMetrics has http_requests_total, latency histograms | Integration script | `uv run python scripts/verify/verify_victoriametrics.py` | ❌ Wave 0 |
| VAL-01 | Blockers fixed in-phase | Process | Manual checklist enforcement | ❌ Wave 0 |
| VAL-02 | Non-blockers logged | Process | Manual checklist annotation | ❌ Wave 0 |
| VAL-03 | Clean final validation pass | Manual checklist | `cat .planning/phases/23-*/23-VALIDATION-CHECKLIST.md` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q` (unit tests only; E2E requires deployed service)
- **Per wave merge:** `uv run pytest tests/ -v` (full unit suite)
- **E2E gate:** `uv run pytest tests/e2e/ -v -m e2e` run once with port-forward active
- **Phase gate:** Full unit suite green AND E2E green AND Locust CSVs produced AND all verify scripts exit 0

### Wave 0 Gaps
- [ ] `tests/e2e/__init__.py` — package marker
- [ ] `tests/e2e/conftest.py` — `e2e_client` and `provider_addresses` fixtures
- [ ] `tests/e2e/fixtures/provider_addresses.yaml` — per-provider known-good address data
- [ ] `tests/e2e/test_providers_geocode.py` — parametrized geocode E2E per provider
- [ ] `tests/e2e/test_providers_validate.py` — parametrized validate E2E per provider
- [ ] `tests/e2e/test_cascade_pipeline.py` — cascade E2E (TEST-02)
- [ ] `loadtests/geo_api_locustfile.py` — Locust HttpUser task definitions
- [ ] `loadtests/addresses/cold_cache_addresses.txt` — unique addresses
- [ ] `loadtests/addresses/warm_cache_addresses.txt` — repeated addresses
- [ ] `scripts/verify/verify_loki.py` — Loki assertions
- [ ] `scripts/verify/verify_tempo.py` — Tempo assertions
- [ ] `scripts/verify/verify_victoriametrics.py` — VictoriaMetrics assertions
- [ ] `.planning/phases/23-e2e-testing-load-baselines-and-final-validation/23-VALIDATION-CHECKLIST.md` — 7-category final validation checklist
- [ ] `pyproject.toml` — add `"e2e"` pytest marker to avoid PytestUnknownMarkWarning
- [ ] `uv add --dev locust` — install Locust 2.43.3
- [ ] Apply `k8s/overlays/prod/argocd-app.yaml` + create K8s Secrets in civpulse-prod (prerequisite deployment)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Locust 1.x with `locustfile.py` at root | Locust 2.x `HttpUser` with `--headless --csv` | Locust 2.0 (2021) | `HttpLocust` removed; must use `HttpUser` class |
| Loki push API only | Loki HTTP query API `/loki/api/v1/query_range` | Loki 2.0+ | Full LogQL query support from scripts |
| Tempo gRPC only | Tempo HTTP API `/api/search` + `/api/traces/{id}` | Tempo 1.0+ | REST-accessible trace search |

**Deprecated/outdated:**
- `locust.HttpLocust`: removed in Locust 2.0 — use `locust.HttpUser`
- `@seq_task`: removed in Locust 2.0 — use `@task(weight)`

---

## Open Questions

1. **Loki stream label for geo-api logs**
   - What we know: Grafana Alloy in `civpulse-infra` scrapes pod logs. Other services (voter-api, run-api, etc.) are running and presumably have logs in Loki.
   - What's unclear: The exact Alloy pipeline config determines which labels appear on geo-api log streams. The JSON body contains `service="civpulse-geo"` but Alloy may index by k8s labels (`app.kubernetes.io/name`, `namespace`) rather than log body fields.
   - Recommendation: Before writing the Loki verify script assertion, run `kubectl port-forward -n civpulse-infra svc/loki 3100:3100` and `curl 'http://localhost:3100/loki/api/v1/labels'` to confirm available label keys after geo-api is deployed.

2. **pyyaml availability as transitive dependency**
   - What we know: `pyproject.toml` does not list pyyaml directly. It may come in via a transitive dep.
   - What's unclear: Whether pyyaml is available without explicit install.
   - Recommendation: Use JSON for the fixture file instead of YAML to eliminate the dependency entirely. `json` is stdlib.

3. **DB credentials for civpulse-prod geo-api-secret**
   - What we know: K8s Secret is excluded from Kustomize (D-06 Phase 20). The `project_db_credentials.md` file referenced in MEMORY.md has `geo_dev/geo_prod` passwords for Phase 20 K8s Secrets.
   - What's unclear: Whether the Secret was already created in civpulse-prod during prior phases or is still pending.
   - Recommendation: Add a prerequisite check: `kubectl get secret geo-api-secret -n civpulse-prod` — if missing, create it using credentials from `project_db_credentials.md` before applying ArgoCD app.

4. **Validation checklist categories: exact items within each of the 7 categories**
   - What we know: The 7 categories are: debt, review, observability, deployment, resilience, testing, validation. REQUIREMENTS.md has all v1.3 items with completion status.
   - What's unclear: Granularity — should each REQUIREMENTS.md item be a checklist row, or higher-level?
   - Recommendation: Use each named requirement (DEBT-01 through VAL-03) as a row with PASS/FAIL/DEFER status. This maps directly to REQUIREMENTS.md and avoids ambiguity.

---

## Sources

### Primary (HIGH confidence)
- Codebase inspection — `pyproject.toml`, `tests/conftest.py`, `src/civpulse_geo/observability/`, `src/civpulse_geo/main.py`, `k8s/` manifests
- `kubectl get` cluster state — confirmed namespaces, running services, absent geo-api deployment
- `uv pip index versions locust` — confirmed Locust 2.43.3 latest as of 2026-03-30
- Phase 22 CONTEXT.md — D-01 through D-04: confirmed log field names, metric names, span attributes
- Phase 20 CONTEXT.md — D-04 through D-14: K8s manifest structure, port-forward approach, ClusterIP service

### Secondary (MEDIUM confidence)
- Locust 2.x CLI help (`--headless`, `--csv`, `--spawn-rate` flags): confirmed via `locust --help` against 2.43.3
- Loki HTTP API query endpoint pattern: standard LogQL `/loki/api/v1/query_range` — consistent across Loki 2.x/3.x
- Tempo HTTP API search pattern: `/api/search` — standard endpoint, confirmed available on port 3200

### Tertiary (LOW confidence)
- VictoriaMetrics PromQL query endpoint `/api/v1/query`: knowledge-based; headless Service confirmed present but query API behavior not verified against running instance

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — locust version verified via PyPI, all other deps already installed
- Architecture: HIGH — E2E pattern derived from existing conftest.py; Locust patterns from CLI help
- Pitfalls: HIGH — geo-api non-deployment confirmed by `kubectl` cluster inspection; VictoriaMetrics headless confirmed; Loki label uncertainty documented
- Environment: HIGH — all observability backends confirmed running; geo-api absence confirmed

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable stack — Locust/Loki/Tempo APIs stable)
