# Pitfalls Research

**Domain:** FastAPI + asyncpg + Loguru + Ollama sidecar — Production K8s Deployment with Observability
**Project:** CivPulse Geo API — v1.3 Production Readiness & Deployment
**Researched:** 2026-03-29
**Confidence:** HIGH for asyncpg/K8s lifecycle (official asyncpg FAQ + community post-mortems); HIGH for Loguru+OTLP (official OTEL Python docs + GitHub issues); MEDIUM for ArgoCD race conditions (GitHub issue + community patterns); MEDIUM for Ollama K8s startup (community patterns, no official K8s guide); LOW for geocoding load test cache bias (general load testing literature, geocoding-specific experience only)

---

## Critical Pitfalls

Mistakes that cause data loss, deployment failures, or silent observability gaps.

---

### Pitfall 1: asyncpg + PgBouncer in Transaction Mode — Prepared Statement Errors

**What goes wrong:**
If a connection pool (PgBouncer, Supabase pooler, or any middleware) is placed in front of PostgreSQL in transaction or statement pool mode, asyncpg's default prepared statement caching causes intermittent errors: `prepared statement "__asyncpg_stmt_xx__" does not exist` or `prepared statement "__asyncpg_stmt_xx__" already exists`. These appear under load or during rolling restarts when connections are reassigned across PgBouncer backends. The errors are non-deterministic and hard to reproduce in dev.

**Why it happens:**
asyncpg caches prepared statements on the underlying TCP connection. In PgBouncer transaction mode, the same asyncpg connection object may be backed by different PostgreSQL server connections on different requests — the prepared statement cached on connection A does not exist on connection B. asyncpg issues `PREPARE` on first use and assumes that statement persists for the connection lifetime. PgBouncer invalidates that assumption.

**How to avoid:**
- Connect asyncpg directly to PostgreSQL, bypassing any transaction-mode pooler. asyncpg's built-in `asyncpg.create_pool()` is the correct pool for async workloads — do not add PgBouncer on top.
- If a pooler is unavoidable (e.g., shared PG instance requires it), use PgBouncer in session mode only — this preserves the prepared statement assumption.
- If transaction-mode pooler cannot be avoided: set `statement_cache_size=0` on the asyncpg connection/pool. This disables prepared statement caching, trading a small per-request overhead for correctness. Add `prepared_statement_cache_size=0` to the SQLAlchemy `create_async_engine()` call via `connect_args`.
- The external PostgreSQL 17 instance for this project must be confirmed to have no pooler in front, or be configured in session mode.

**Warning signs:**
- Intermittent `asyncpg.exceptions.InvalidCachedStatementError` in logs under concurrent load.
- Errors disappear at low concurrency (1-2 workers) but appear at 10+ concurrent requests.
- Error rate correlates with pod restarts or rolling updates.

**Phase to address:** K8s manifests phase (database connectivity validation). Verify connection mode before any load test.

---

### Pitfall 2: Connection Pool Exhaustion During Rolling Updates

**What goes wrong:**
During a K8s rolling update, new pods spin up while old pods are still draining. If each pod opens its full asyncpg pool (e.g., `max_size=20`) at startup, the in-progress update temporarily doubles the active connection count against PostgreSQL. For a 2-replica deployment with `max_size=20`, this peaks at 80 connections (2 old + 2 new pods, each at max pool). If PostgreSQL's `max_connections` is 100 (default), the remaining 20 connections are shared with all other services. New pods fail readiness probes because the pool cannot be created — `asyncpg.TooManyConnectionsError` — causing the rolling update to stall and leaving the deployment in a broken state.

**Why it happens:**
Pool initialization happens at app startup (lifespan). Kubernetes begins health checks immediately. If the pool is exhausted before the app signals readiness, the readiness probe fails, the pod is killed, and a new pod is spawned — which also tries to open the same pool, entering an infinite failure loop.

**How to avoid:**
- Size the pool conservatively: `min_size=2, max_size=10` per pod for this workload. Each geocoding request holds a connection for the duration of the DB query only (asyncpg releases on `async with pool.acquire()`). 10 connections per pod handles high concurrency.
- Set `max_connections` on the PostgreSQL instance to at least `(pod_count * max_pool_size * 2) + 20` buffer. For 2 replicas at max_size=10: `2 * 10 * 2 + 20 = 60` minimum. Request this from the DB provisioning phase.
- During rolling updates, K8s `maxSurge=1` limits the temporary extra pods to 1 at a time. Set `strategy.rollingUpdate.maxSurge: 1` and `maxUnavailable: 0` in the Deployment spec.
- Use `pool.min_size` equal to a small baseline, not `max_size`. Don't pre-open all connections at startup.
- Add `acquire_timeout=5` to pool.acquire() calls so slow-connection errors surface quickly rather than hanging.

**Warning signs:**
- `asyncpg.TooManyConnectionsError` in pod startup logs.
- Readiness probe fails on new pods but existing pods are healthy.
- Rolling update stalls with `0/1 ready` for the new pod.
- `pg_stat_activity` shows connection count near max during deployments.

**Phase to address:** K8s manifests phase. Pool sizing must be set before E2E load testing.

---

### Pitfall 3: Loguru Does Not Auto-Propagate OpenTelemetry Trace Context

**What goes wrong:**
After adding OTLP tracing (FastAPI + opentelemetry-sdk), log lines emitted by Loguru do not contain `trace_id` or `span_id`. In Grafana, trace view and log view are disconnected — you cannot click a trace and see the correlated log lines. The standard `opentelemetry-instrumentation-logging` package patches Python's stdlib `logging` module to inject `otelTraceID` and `otelSpanID` into log records automatically. Loguru bypasses stdlib logging entirely and is not patched by this instrumentation.

**Why it happens:**
Loguru is a completely independent logging framework that does not use `logging.Handler` or `logging.LogRecord`. The OTEL Python contrib package's logging instrumentation hooks into `logging.setLogRecordFactory()` — a stdlib-only mechanism. Since Loguru never creates `LogRecord` objects, no trace context is ever injected. Developers see OTLP spans in Tempo and Loguru output in Loki but have no way to correlate them without manually embedding the trace ID in the log message.

**How to avoid:**
- Add a Loguru `patcher` that extracts the current OTEL span context and injects `trace_id` and `span_id` into every log record:
  ```python
  from opentelemetry import trace

  def add_otel_context(record):
      span = trace.get_current_span()
      ctx = span.get_span_context()
      record["extra"]["trace_id"] = format(ctx.trace_id, "032x") if ctx.is_valid else ""
      record["extra"]["span_id"] = format(ctx.span_id, "016x") if ctx.is_valid else ""

  logger.configure(patcher=add_otel_context)
  ```
- Add a FastAPI middleware that creates a root OTEL span for each request before any Loguru logging occurs — otherwise `get_current_span()` returns a no-op span with no valid context.
- If using `opentelemetry-instrumentation-fastapi`, the instrumentation creates spans automatically. The Loguru patcher will see a valid span context on all in-request log calls.
- Output Loguru logs in JSON format with `trace_id` and `span_id` as structured fields. Loki label `{trace_id="..."}` then links directly to the Tempo trace.
- Test the correlation by issuing a traced request, noting the trace ID in the response header, and verifying that Loki logs contain the same trace ID.

**Warning signs:**
- Grafana Loki logs show no `trace_id` field.
- OTEL spans in Tempo have no correlated log entries.
- `trace_id` field in Loguru output is always empty string or `"0000...0000"`.
- OTEL instrumentation-logging docs reference `logging.basicConfig()` — this has no effect on Loguru.

**Phase to address:** Structured logging + distributed tracing phase. Must be verified before load testing — otherwise load test failures have no traceable log correlation.

---

### Pitfall 4: Ollama Sidecar Readiness — geo-api Starts Before Model Is Available

**What goes wrong:**
The geo-api container and the Ollama sidecar start in parallel in the same pod. geo-api's conditional provider registration checks `_ollama_available()` at startup (an HTTP call to `http://localhost:11434/api/tags`). On first pod start or after a pod restart, Ollama may be pulling the `qwen2.5:3b` model (2+ GB download). The readiness check against port 11434 succeeds immediately after Ollama starts (the server answers requests), but the model is not yet loaded. geo-api registers the LLM provider as available. The first geocoding request that triggers the LLM cascade stage receives a 404 or empty response from Ollama (`model not found`), causing the LLM stage to fail and the cascade to skip that stage silently.

**Why it happens:**
Ollama's HTTP server starts and responds to `/api/tags` before model pull completes. The `/api/tags` endpoint returns an empty list during download, not an error. geo-api treats a successful HTTP response (200 OK) as proof of availability, not the presence of the required model. A standard K8s readiness probe on port 11434 also passes immediately, so the pod is marked ready before the model exists.

**How to avoid:**
- The Ollama availability check must verify model presence, not just server reachability. Replace the HTTP-ping check with a call to `/api/tags` that parses the response body and confirms `qwen2.5:3b` (or the configured model name) appears in the `models` list.
  ```python
  async def _ollama_model_available(model: str) -> bool:
      resp = await client.get("http://localhost:11434/api/tags")
      tags = resp.json().get("models", [])
      return any(m["name"].startswith(model) for m in tags)
  ```
- On first deploy, use a Kubernetes init container or a postStart lifecycle hook on the Ollama container that runs `ollama pull qwen2.5:3b` and blocks until the pull is complete. The main geo-api container only starts after init containers finish.
- Set `initialDelaySeconds: 120` on the Ollama sidecar's readiness probe to give the model pull time before Kubernetes begins health checks.
- Store the Ollama model data on a PersistentVolumeClaim (not emptyDir) so model pulls survive pod restarts. Without PVC, every pod restart triggers a full model re-download.
- The model PVC must be created and the initial `ollama pull` must run before the first production deployment.

**Warning signs:**
- `GET /api/generate` to Ollama returns `{"error":"model 'qwen2.5:3b' not found, try pulling it first"}`.
- LLM cascade stage silently skipped on first requests after pod start.
- Ollama sidecar logs show `pulling manifest` during active request handling.
- geo-api logs show `LLM provider registered` but LLM requests return empty or error.

**Phase to address:** K8s manifests phase (sidecar configuration) and Ollama model provisioning phase.

---

### Pitfall 5: Read-Only Root Filesystem Breaks symspellpy Dictionary Rebuild and Alembic Migrations

**What goes wrong:**
With `securityContext.readOnlyRootFilesystem: true`, any write to the container filesystem fails with `Read-only file system`. Two specific failure modes for this project:

1. **symspellpy dictionary file:** The `geo-api spell rebuild` CLI command writes a `.pkl` or `.txt` dictionary file to a path under the project directory (e.g., `/app/data/spell_dict.pkl`). On a read-only filesystem, this command fails with an OS error. If the dictionary file is absent at startup, symspellpy loads with an empty dictionary and spell correction is silently disabled — no exception, just zero corrections applied.

2. **Alembic migrations via init container:** The Alembic migration init container writes `__pycache__` directories and SQLite lock files when importing the migration environment. On a read-only FS, Python's import machinery fails to write `__pycache__` for the alembic/ package, causing import errors. The init container exits non-zero, blocking the main container from starting.

**Why it happens:**
`readOnlyRootFilesystem: true` is a security best practice. It blocks writes everywhere in the container FS except explicitly mounted volumes. Applications that assume they can write anywhere under their install directory (including `__pycache__`, temp dirs, or data dirs) break silently or noisily.

**How to avoid:**
- Mount `emptyDir` volumes at every path that needs writes:
  - `/tmp` — Python tempfile, httpx, and other libraries use this
  - `/app/data/` — symspellpy dictionary output and any data files written at runtime
  - `/__pycache__` paths — avoid this by setting `PYTHONDONTWRITEBYTECODE=1` in the container environment, which prevents Python from writing `.pyc` files entirely
- For the spell dictionary: the dictionary must be pre-built and baked into the Docker image, or built during the init container phase and stored on the shared emptyDir volume. Do not attempt to write it at runtime in a read-only FS environment.
- For Alembic migrations: the migration init container needs `readOnlyRootFilesystem: false` (or an emptyDir at `/app/.cache`), or `PYTHONDONTWRITEBYTECODE=1` set. Alembic itself does not write files, but Python's import cache does.
- Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPYCACHEPREFIX=/tmp/pycache` as container env vars. `PYTHONPYCACHEPREFIX` redirects all `__pycache__` writes to `/tmp/pycache`, which can be an emptyDir mount.

**Warning signs:**
- `OSError: [Errno 30] Read-only file system` in container logs.
- Spell correction returning zero corrections for clearly misspelled inputs.
- Init container exits with `ModuleNotFoundError` or `PermissionError` during Alembic run.
- `PYTHONPYCACHEPREFIX` not set and `/tmp` not mounted as emptyDir.

**Phase to address:** Dockerfile + K8s manifests phase. Must be verified before any migration or spell rebuild is attempted in K8s.

---

### Pitfall 6: Graceful Shutdown Race — SIGTERM Before kube-proxy Endpoint Removal

**What goes wrong:**
Kubernetes sends SIGTERM to the pod at the same time it begins propagating the endpoint removal to kube-proxy and CoreDNS. These are asynchronous processes. For 2-15 seconds after SIGTERM is delivered, other pods in the cluster may still route requests to the terminating pod (because their kube-proxy hasn't updated yet). FastAPI/uvicorn stops accepting new connections immediately on SIGTERM, causing those late-arriving requests to receive connection refused errors. Upstream callers (run-api, vote-api) see intermittent 503s or connection failures during every rolling update.

**Why it happens:**
The Kubernetes control plane endpoint reconciliation (API server → etcd → kube-proxy on each node → iptables rules) is eventually consistent, not synchronous with SIGTERM delivery. The pod is removed from the service endpoints list in etcd immediately, but kube-proxy on other nodes may take several seconds to apply the updated iptables rules.

**How to avoid:**
- Add a `preStop` lifecycle hook that sleeps for 5-10 seconds before uvicorn receives SIGTERM. This gives kube-proxy time to drain the pod from the load balancer rotation before the server stops accepting connections:
  ```yaml
  lifecycle:
    preStop:
      exec:
        command: ["/bin/sh", "-c", "sleep 5"]
  ```
- Set `terminationGracePeriodSeconds: 60` (or greater than the sum of preStop sleep + max request duration + asyncpg pool drain time). The default 30s is often insufficient for an API that may have long-running cascade geocoding requests (P95 < 3s per PROJECT.md, so 30s should suffice if preStop is 5s — but set 60s for safety).
- In the lifespan shutdown handler, call `await pool.close()` only after uvicorn has stopped accepting requests. The `lifespan` context manager's `finally` block runs after uvicorn shutdown, so asyncpg pool cleanup there is correct.
- Do not send SIGKILL forcefully before the grace period — let the default Kubernetes behavior run.

**Warning signs:**
- Caller services (run-api, vote-api) log connection refused errors during geo-api deployments.
- 503 errors spike in metrics during rolling updates.
- asyncpg pool raises `InterfaceError: connection closed` on in-flight requests during shutdown.
- `terminationGracePeriodSeconds` less than the actual shutdown time observed in logs.

**Phase to address:** K8s manifests phase. Verify during E2E load testing by watching error rates during a rolling update.

---

### Pitfall 7: ArgoCD Auto-Sync + CI Image Tag Commit — Race Condition on Concurrent Builds

**What goes wrong:**
GitHub Actions builds an image, pushes it to GHCR, then commits an updated image tag to the K8s manifests repo. ArgoCD detects the commit and syncs. If two CI pipelines run concurrently (e.g., two PRs merged close together), both pipelines commit image tag updates. The second commit's `git push` may fail with a merge conflict (two pipelines both updated `image: geo-api:sha-xxx` at the same time). Alternatively, ArgoCD begins syncing the first commit's tag while the second pipeline's commit overwrites it — ArgoCD syncs the wrong image and then immediately detects drift and syncs again, causing a double-deploy with a transient wrong image.

**Why it happens:**
CI pipelines that do `git pull`, `sed -i image tag`, `git commit`, `git push` are not atomic. Under concurrent builds, two processes reading the same file, modifying it, and pushing will collide. ArgoCD Image Updater was built to solve this — it uses a write-once annotation mechanism — but if the project uses direct manifest commits instead, race conditions are inherent.

**How to avoid:**
- Use ArgoCD Image Updater with the `argocd-image-updater.argoproj.io/image-list` annotation on the ArgoCD Application resource. CI only pushes images; ArgoCD Image Updater detects new tags and updates manifests using its own lock-free annotation approach (`argocd-image-updater.argoproj.io/write-back-method: argocd` stores state in ArgoCD annotations, not git commits — this eliminates the git collision entirely).
- If direct manifest commits are preferred: use a separate `manifests` branch with branch protection. CI opens a PR, not a direct commit. ArgoCD watches the `manifests` branch. Only one PR at a time can merge, eliminating the collision.
- At minimum: add `--retry` logic to the CI git push step and use `git pull --rebase` before commit to reduce collision probability.
- Never enable both ArgoCD Image Updater AND CI manifest commits for the same image — they will conflict.

**Warning signs:**
- `git push` fails with `rejected - non-fast-forward` in CI logs.
- ArgoCD Application shows `OutOfSync` immediately after a successful sync.
- Two different image SHAs deployed briefly to the same namespace during concurrent builds.
- ArgoCD sync history shows rapid consecutive syncs seconds apart.

**Phase to address:** CI/CD pipeline phase. Decide on Image Updater vs. manifest-commit pattern before wiring CI.

---

### Pitfall 8: k3s CoreDNS Does Not Resolve External PostgreSQL Hostname

**What goes wrong:**
The geo-api's `DATABASE_URL` uses a hostname (e.g., `postgres.internal.civpulse.io`) that is resolvable on the host node but not inside pods. k3s defaults CoreDNS to use Google's DNS (`8.8.8.8`) as the upstream resolver rather than the host's configured nameservers (`/etc/resolv.conf`). If `postgres.internal.civpulse.io` is on an internal DNS server (common for a self-hosted PostgreSQL instance), pods cannot resolve it. asyncpg connection attempts fail immediately at startup with `socket.gaierror: [Errno -2] Name or service not known`. The app fails to start.

**Why it happens:**
k3s injects its own `resolv.conf` into pods that points to CoreDNS (kube-dns IP). CoreDNS in k3s is configured by the `coredns` ConfigMap in `kube-system`. Its default `forward . 8.8.8.8 8.8.4.4` directive forwards unresolved names to Google DNS, bypassing any internal nameservers configured on the host. External hostnames on private DNS are invisible to pods unless CoreDNS is patched.

**How to avoid:**
- Patch the CoreDNS ConfigMap in `kube-system` to forward to the host's DNS server(s):
  ```
  forward . 192.168.x.x  # internal DNS server IP
  ```
  Or add a stub zone for the internal domain:
  ```
  civpulse.io:53 {
      forward . 192.168.x.x
  }
  ```
- Alternatively, use the PostgreSQL server's IP address in `DATABASE_URL` instead of hostname — this bypasses DNS entirely but loses DNS-based failover.
- Validate DNS resolution from inside a pod before deploying the app: `kubectl run dns-test --image=busybox --rm -it -- nslookup postgres.internal.civpulse.io`
- For the geo-api specifically: test this as the very first step of the K8s connectivity validation, before any application deployment.

**Warning signs:**
- `socket.gaierror: [Errno -2] Name or service not known` at pod startup.
- Pod fails liveness/readiness probe immediately after start.
- `nslookup` from inside the pod fails for the DB hostname but succeeds from the host.
- `kubectl logs -n kube-system coredns-...` shows forwarded queries timing out.

**Phase to address:** Infrastructure provisioning phase, before any application deployment.

---

### Pitfall 9: Conditional Provider Registration — K8s Readiness Probe Marks Pod Ready Before Data Loads

**What goes wrong:**
geo-api uses conditional provider registration: `_oa_data_available()`, `_nad_data_available()`, `_tiger_extension_available()` are checked at startup. These checks query the database at startup. The readiness probe (`GET /health`) returns 200 once the app is listening on its port. If the readiness probe is wired to just port availability (not application health), the pod is marked ready before the database connectivity check in lifespan has completed. Worse: if staging tables (oa_data, nad_data) are empty in a fresh deployment (data hasn't been imported yet), all local providers register as unavailable — and this state persists for the lifetime of the pod. No mechanism re-checks provider availability after startup.

**Why it happens:**
K8s readiness probes default to checking TCP port connectivity, not application-layer health. FastAPI starts listening on port 8000 before the lifespan startup handler finishes. If the lifespan handler is slow (e.g., connecting to external PostgreSQL at startup), there's a window where the pod is routable but not ready. Additionally, since provider availability is evaluated once at startup, a pod deployed before data loading completes will remain in a degraded state with fewer providers.

**How to avoid:**
- Implement a proper health endpoint that reports provider availability status:
  ```python
  @app.get("/health")
  async def health():
      return {
          "status": "ok",
          "providers": {
              "oa": oa_provider is not None,
              "nad": nad_provider is not None,
              "tiger": tiger_provider is not None,
              "census": True,  # always available
              "ollama": await _ollama_model_available("qwen2.5:3b"),
          }
      }
  ```
- Add a startup probe (separate from readiness probe) that waits until the asyncpg pool is created and at least one provider is registered before the pod is marked ready. Startup probe: `failureThreshold: 30, periodSeconds: 5` (150 seconds total window).
- For data-loading workflows (oa import, nad import): run these as a K8s Job with its own pod, separate from the application deployment. The Job completes, then the Deployment is updated (rolling restart) to pick up the newly loaded data.
- Document the deploy order: (1) run data-loading Jobs, (2) deploy geo-api pods, (3) verify provider registration in health endpoint.

**Warning signs:**
- `/health` returns 200 but all local providers show `false` in provider status.
- All geocoding requests return Census results only (other providers unavailable).
- Pod is marked ready before asyncpg pool creation log line appears.
- Provider registration log lines appear seconds after the readiness probe succeeds.

**Phase to address:** K8s manifests phase (health endpoint definition) and data provisioning phase (Job ordering).

---

### Pitfall 10: Load Testing False Positives — Cache Bias Inflates Performance Numbers

**What goes wrong:**
Load tests run the same set of test addresses repeatedly. The geo-api caches external provider results (Census Geocoder, etc.) in PostgreSQL after the first call. By the second request, the response comes from the database cache (`cache_hit: true`) rather than the full cascade pipeline. P95 latency looks excellent (sub-100ms) because 99% of load test traffic hits the cache. This masks the true P95 for uncached addresses, which involves the full cascade: normalize → spell-correct → parallel provider dispatch → fuzzy match → (optionally) LLM. The actual P95 for cold-cache traffic may be 3-10x worse than the load test result suggests.

**Why it happens:**
The geocoding cache is by design — it is the core value proposition of the system. But in a load test scenario with a fixed address corpus, the cache fills after the first pass through the corpus, and all subsequent passes are cache reads. Test results look unrealistically good. This is compounded by the warmup period: early requests (cold cache) are fast for local providers (which bypass cache by design) and slow for Census (first external call), creating a bimodal latency distribution that is easy to misread.

**How to avoid:**
- Run load tests in two explicit modes:
  1. **Cold cache baseline**: before each test run, clear the geocoding cache tables (`DELETE FROM geocoding_results; DELETE FROM official_geocoding;`). This forces all providers to execute the full pipeline. Report P50/P95/P99 from this run as the authoritative baseline.
  2. **Warm cache steady-state**: run the test corpus once (warm up), then measure the second pass. This tests cache read throughput separately.
- Use a large, diverse address corpus (>500 addresses) to prevent complete cache saturation during the test. The corpus should include addresses across all providers: Census-only addresses, addresses in oa_data, addresses in nad_data, and addresses not in any local provider.
- Include at least 20% "intentionally bad" addresses (typos, truncated zips) in the corpus to test the spell correction and fuzzy match paths under load. These will never be cached and will always exercise the full pipeline.
- Set `cache_hit` as a label in the load test metrics. Grafana should show separate P95 for `cache_hit: true` vs `cache_hit: false` requests.
- Report both numbers in performance baseline documentation.

**Warning signs:**
- P95 latency drops dramatically after the first minute of a load test (cache filling up).
- `cache_hit` rate approaches 100% within seconds of test start.
- All provider latency percentiles look identical (cache returns same path regardless of provider).
- Load test corpus contains fewer than 100 unique addresses.

**Phase to address:** E2E testing and performance baseline phase. Define the two-mode test methodology before running any load tests.

---

### Pitfall 11: Ollama Model Volume Not Persisted — Full Model Re-Download on Every Pod Restart

**What goes wrong:**
The Ollama sidecar stores its model weights at `/root/.ollama` by default. If this path is not backed by a PersistentVolumeClaim, the directory is ephemeral (lives in the container's writable layer or an emptyDir). Every pod restart — including rolling updates, OOM kills, node evictions — triggers a full model download: `qwen2.5:3b` is approximately 2GB. On a slow connection or during a production incident, this can take 10-30 minutes. During that time the LLM stage is unavailable and all cascade requests skip it, degrading geocoding quality.

**Why it happens:**
Kubernetes pods are ephemeral by design. The default Ollama Docker image stores models in the container's writable layer. Unless explicitly configured with a volume mount, model data is lost on pod restart. This is rarely a problem in development (Docker volume persists) but always a problem in K8s (pod restart = new writable layer).

**How to avoid:**
- Create a PersistentVolumeClaim for Ollama model storage in k3s:
  ```yaml
  volumeMounts:
    - name: ollama-models
      mountPath: /root/.ollama
  volumes:
    - name: ollama-models
      persistentVolumeClaim:
        claimName: ollama-models-pvc
  ```
- Use k3s's default local-path StorageClass for the PVC (storage class: `local-path`). This provisions a PVC on the node's local disk — sufficient for model weights since they don't need to be shared across nodes.
- Provision the PVC and run the initial model pull as a K8s Job before any Deployment that includes the Ollama sidecar. The Deployment's Ollama sidecar then only needs to pull the model once; subsequent restarts find it already on the PVC.
- Set `resources.requests.memory` on the Ollama container to at least 4Gi (qwen2.5:3b requires ~2.8GB RAM for inference). Without a memory request, the container is likely to be OOM-killed under load, triggering the re-download loop.

**Warning signs:**
- Ollama logs show `pulling manifest` on every pod restart.
- First geocoding requests after a pod restart time out at the LLM stage.
- Ollama container memory usage close to node limit without a memory limit set.
- No PVC or hostPath volume in the Deployment spec for Ollama.

**Phase to address:** Ollama sidecar provisioning phase, before first Deployment deployment.

---

### Pitfall 12: Alembic Migration Init Container — Concurrent Pods Trigger Duplicate Migration

**What goes wrong:**
In a multi-replica deployment with an Alembic migration init container, every replica runs `alembic upgrade head` at startup. If two pods start at the same time (e.g., initial deployment with `replicas: 2`), both init containers run migrations concurrently. Alembic does not use advisory locks by default — the second migration run sees the schema already at the target version (from the first run), but if the migration includes data transforms or uses `IF NOT EXISTS`, the concurrent run may succeed harmlessly or may fail with a `DuplicateTableError`. The failure causes the init container to exit non-zero, blocking the main container.

**Why it happens:**
Alembic's version tracking uses a `alembic_version` table row. Without explicit locking, two concurrent processes can both read `current_version = old`, both attempt to apply the migration, and the second one collides on table creation or constraint addition.

**How to avoid:**
- Implement advisory lock around `alembic upgrade head` using a pre-migration script:
  ```python
  # In env.py run_migrations_online():
  with engine.connect() as conn:
      conn.execute(text("SELECT pg_advisory_lock(12345)"))
      context.run_migrations()
      conn.execute(text("SELECT pg_advisory_unlock(12345)"))
  ```
- Alternatively, run migrations as a Kubernetes Job (not an init container), with `parallelism: 1` and `completions: 1`. Use an init container that waits for the Job to complete before starting the main container. This guarantees exactly-once migration execution.
- At minimum, make all migrations idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX CONCURRENTLY IF NOT EXISTS`). This prevents hard failures on duplicate execution.
- Add `--lock-timeout=5s` to the PostgreSQL session used by migrations to fail fast rather than deadlock.

**Warning signs:**
- Init container exits with `DuplicateTableError` or `UniqueViolationError` on initial multi-replica deploy.
- One pod starts successfully while another is stuck in `Init:Error` state.
- `alembic_version` table shows two rows (concurrent write split).

**Phase to address:** K8s manifests phase. Run a 2-replica deployment immediately after the manifests are written to catch this before production.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| emptyDir for Ollama model storage | No PVC provisioning needed | Full re-download on every restart; 10-30 min downtime | Never in production |
| Hardcode `cache_hit: True` in response | Unblocks dev while provider logic is WIP | Silent lie in production metrics; cache stats always wrong | Never — fix or remove |
| Single init container for migrate + data load | Simpler manifest | Data load blocks migration start; long init delays readiness | Never in production with large datasets |
| Skip preStop sleep hook | Simpler manifests | Intermittent 503s during every rolling update | Never if callers are other services |
| `readOnlyRootFilesystem: false` to unblock FS errors | Unblocks quickly | Security regression; masks paths that need explicit volume mounts | Temporarily in dev only, must be fixed before prod |
| `PYTHONDONTWRITEBYTECODE` not set | Slightly faster Python startup | Writes `__pycache__` to read-only FS, crashes init container | Never in K8s with readOnlyRootFilesystem |
| P95 measured with warm cache only | Good-looking numbers | Hides cold-path P95 which is the user-visible first-geocode experience | Never as the reported baseline |

---

## Integration Gotchas

Common mistakes when connecting specific components in this stack.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Loguru + OTLP | Assume OTEL auto-instruments Loguru via `opentelemetry-instrumentation-logging` | Loguru bypasses stdlib logging; must add manual patcher with `trace.get_current_span()` |
| asyncpg + external PG | Assume PgBouncer or shared pool is transparent | Disable prepared statement caching or use session-mode pooler only |
| Ollama sidecar + geo-api | Check Ollama via HTTP ping only (`/api/tags` returns 200) | Parse `/api/tags` response body to confirm model name present in the list |
| ArgoCD + GitHub Actions | Commit image tag directly to manifests in CI | Use ArgoCD Image Updater or a PR-based workflow to avoid git push collisions |
| k3s + internal DNS | Assume pod DNS resolves internal hostnames same as host | Patch CoreDNS ConfigMap `forward` directive to point to internal nameservers |
| K8s readiness probe + async lifespan | Wire probe to TCP port (fast) | Wire probe to `/health` endpoint that checks DB pool and provider registration |
| Alembic + multi-replica init containers | Run migration from each pod's init container | Use K8s Job with advisory lock or single-pod init strategy |
| symspellpy + read-only FS | Write dictionary at startup to app dir | Bake dictionary into image or write to emptyDir volume at a known mount path |

---

## Performance Traps

Patterns that work at small scale but fail under load.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Load test with fixed small corpus | P95 looks excellent; all traffic is cache hits | Use 500+ unique addresses, clear cache before cold-run | Any load test with repeat addresses |
| asyncpg pool too large per pod | Rolling update exhausts `max_connections` | `max_size=10` per pod; size DB `max_connections` accordingly | 2+ replicas during rolling update |
| Ollama synchronous in cascade | LLM calls block cascade for 3-10s per request | LLM stage timeout set to max 2s; skip on timeout gracefully | Any moderate concurrency (5+ rps) |
| Provider timeout too generous | Slow Census response backs up connection pool | Set `httpx.AsyncClient` timeouts: `connect=2.0, read=5.0, total=8.0` | Under sustained load when Census is slow |
| No connection retry on startup | App fails permanently if PG is 2s slow at startup | Implement exponential backoff retry (3 attempts, 2s/4s/8s) in lifespan | Cold start when PG takes a moment to accept connections |

---

## Security Mistakes

Domain-specific security issues for this internal API.

| Mistake | Risk | Prevention |
|---------|------|------------|
| `readOnlyRootFilesystem: false` in prod | Container can write arbitrary files; backdoor persistence | Enforce `readOnlyRootFilesystem: true` with explicit emptyDir mounts for required paths |
| Image tag `latest` in K8s manifests | ArgoCD cannot detect drift; rolling updates silent | Always use immutable SHA-tagged images in manifests |
| Database credentials in K8s Deployment env vars (not Secret) | Credentials visible in `kubectl describe pod` | Use K8s Secret with `envFrom: secretRef` |
| Ollama model API exposed on non-loopback | Ollama answers any caller with raw LLM access | Set `OLLAMA_HOST=127.0.0.1:11434` in sidecar env; geo-api communicates over loopback only |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **OTLP tracing integrated:** Verify `trace_id` appears in Loguru-emitted Loki logs for a traced request — not just that spans appear in Tempo
- [ ] **Ollama provider available:** Verify `/health` endpoint shows `ollama: true` AND that a geocoding request actually reaches the LLM stage (trigger with a badly misspelled address)
- [ ] **Graceful shutdown working:** During a rolling update, verify callers see zero 503 errors by watching caller-side error metrics
- [ ] **Read-only FS enforced:** Deploy with `readOnlyRootFilesystem: true` and confirm the app starts and spell rebuild works (writes to emptyDir path)
- [ ] **Alembic idempotent:** Deploy 2 replicas simultaneously and confirm both pods reach Running state without init container collisions
- [ ] **Cold-cache P95 measured:** Report performance baseline from a cold-cache run (cache tables cleared), not just steady-state
- [ ] **CoreDNS resolves external PG:** Confirm from inside a pod that the PostgreSQL hostname resolves before deploying the application
- [ ] **Model persists across restart:** Kill and restart the Ollama sidecar pod; confirm model is available immediately without re-download
- [ ] **Connection pool sized for rolling update:** Confirm `max_connections` on PostgreSQL >= `replicas * max_pool_size * 2 + 20`
- [ ] **provider registration verified at startup:** Check that `/health` shows all expected providers after a fresh pod start with data loaded

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Prepared statement errors | LOW | Set `statement_cache_size=0` in connection string; rolling restart |
| Connection pool exhaustion | MEDIUM | Reduce `max_size` in config; restart pods; check PG `max_connections` |
| Missing trace_id in logs | LOW | Add Loguru patcher; redeploy; no data loss |
| Ollama model missing after restart | HIGH | Run `kubectl exec` into Ollama container and `ollama pull qwen2.5:3b`; wait 10-30 min |
| Read-only FS crash | MEDIUM | Add emptyDir mounts; set `PYTHONDONTWRITEBYTECODE=1`; rebuild and redeploy |
| ArgoCD sync race | LOW | Revert the manifests to known-good state; re-trigger CI for the correct commit |
| CoreDNS resolution failure | LOW | Patch CoreDNS ConfigMap; pods resolve without restart |
| Alembic migration collision | MEDIUM | Manually verify schema is correct; delete the failed pod; let it retry |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| asyncpg + PgBouncer prepared statements | DB provisioning + manifests phase | Integration test hitting DB 50x concurrently; zero prepared statement errors |
| Connection pool exhaustion during rolling update | K8s manifests phase | Trigger rolling update under light load; watch PG `pg_stat_activity` |
| Loguru + OTLP trace_id missing | Structured logging + tracing phase | Request with known trace_id; confirm same ID in Loki log entry |
| Ollama ready before model available | Sidecar provisioning + manifests phase | Delete Ollama pod; wait for restart; confirm LLM stage works within 30s |
| Read-only FS breaks spell rebuild + Alembic | Dockerfile + manifests phase | Deploy with `readOnlyRootFilesystem: true`; run spell rebuild; run migrations |
| SIGTERM before kube-proxy drains | Manifests phase (preStop hook) | Watch caller errors during rolling update; zero 503s expected |
| ArgoCD + CI race condition | CI/CD pipeline phase | Trigger two concurrent builds; confirm no manifest collision |
| k3s CoreDNS external DNS failure | Infrastructure provisioning phase | nslookup from pod before app deployment |
| Conditional provider registration | Manifests phase (health endpoint) + data provisioning | `/health` shows all providers after data load |
| Load test cache bias | E2E + performance baseline phase | Report both cold-cache and warm-cache P95 separately |
| Ollama model not persisted | Sidecar provisioning phase | Restart Ollama pod; confirm model present in `/api/tags` immediately |
| Alembic migration collision | Manifests phase | 2-replica initial deploy; both pods reach Running |

---

## Sources

- asyncpg FAQ — prepared statements with PgBouncer: https://magicstack.github.io/asyncpg/current/faq.html
- asyncpg GitHub issue #239 — DuplicatePreparedStatementError with PgBouncer HA: https://github.com/MagicStack/asyncpg/issues/239
- SQLAlchemy issue #6467 — statement_cache_size with asyncpg + PgBouncer: https://github.com/sqlalchemy/sqlalchemy/issues/6467
- OpenTelemetry Python issue #3615 — trace_id with Loguru: https://github.com/open-telemetry/opentelemetry-python/issues/3615
- OpenTelemetry Python contrib — logging instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html
- Loguru GitHub issue #1222 — use with Azure App Insights/OTEL: https://github.com/Delgan/loguru/issues/1222
- DoltHub blog — pull-first Ollama Docker image (model readiness pattern): https://www.dolthub.com/blog/2025-03-19-a-pull-first-ollama-docker-image/
- Kubernetes docs — Container Lifecycle Hooks (preStop): https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/
- Google Cloud blog — Kubernetes graceful termination: https://cloud.google.com/blog/products/containers-kubernetes/kubernetes-best-practices-terminating-with-grace
- ArgoCD GitHub issue #16419 — race condition updating parameters during sync: https://github.com/argoproj/argo-cd/issues/16419
- ArgoCD Image Updater update methods: https://argocd-image-updater.readthedocs.io/en/stable/basics/update-methods/
- k3s issue #6171 — DNS resolution failure: https://github.com/k3s-io/k3s/issues/6171
- Support Tools — resolving pod DNS problems in k3s with CoreDNS: https://support.tools/resolving-pod-dns-problems-in-k3s-with-coredns/
- Atlas Guides — run DB migrations using init containers: https://atlasgo.io/guides/deploying/k8s-init-container
- Kubernetes docs — init containers: https://kubernetes.io/docs/concepts/workloads/pods/init-containers/
- Thorsten Hans — read-only filesystems in Docker and Kubernetes: https://www.thorsten-hans.com/read-only-filesystems-in-docker-and-kubernetes/
- Uvicorn graceful shutdown discussion: https://github.com/Kludex/uvicorn/discussions/2257
- FastAPI lifespan events: https://fastapi.tiangolo.com/advanced/events/
- Medium — connection pool exhaustion in FastAPI: https://medium.com/@rameshkannanyt0078/handling-postgresql-connection-limits-in-fastapi-efficiently-379ff44bdac5

---

*Pitfalls research for: FastAPI + asyncpg + Loguru + Ollama sidecar — K8s production deployment*
*Researched: 2026-03-29*
*Supersedes v1.2 pitfalls (cascading address resolution). v1.2 pitfalls remain in the same file above this entry.*
