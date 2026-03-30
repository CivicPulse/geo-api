# Phase 20: Health, Resilience, and K8s Manifests - Research

**Researched:** 2026-03-29
**Domain:** FastAPI health endpoints, Kubernetes Kustomize manifests, native sidecar containers, graceful shutdown, ArgoCD GitOps
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Add `/health/live` — process-only liveness probe, no DB dependency. Returns 200 immediately.
- **D-02:** Add `/health/ready` — readiness probe checks DB connectivity AND provider count threshold: at least 2 geocoding providers AND at least 2 validation providers registered.
- **D-03:** Keep existing `/health` endpoint as-is for backward compatibility.
- **D-04:** Kustomize base + overlays structure. `k8s/base/` shared Deployment/Service/ConfigMap. `k8s/overlays/dev/` and `k8s/overlays/prod/` patch env-specific values. ArgoCD Application CRs point to overlay paths.
- **D-05:** Remove `k8s/ollama-deployment.yaml`, `k8s/ollama-pvc.yaml`, `k8s/ollama-service.yaml` after Ollama merges into sidecar.
- **D-06:** Secrets as placeholder YAML with CHANGEME values committed to repo. Real credentials applied manually via `kubectl create secret`. No SealedSecrets or external secrets operator.
- **D-07:** PVC (10Gi ReadWriteOnce) for Ollama model persistence. Model-pull init container runs only when PVC is empty. PVC definition moves to base/ kustomization.
- **D-08:** K8s 1.29+ native sidecar (`initContainers` with `restartPolicy: Always`) for Ollama. Must verify k3s version >= 1.29 during implementation.
- **D-09:** Ollama sidecar config: `ollama_url` = `http://localhost:11434` in ConfigMap. `cascade_llm_enabled=true` in production ConfigMap.
- **D-10:** Belt and suspenders — `await engine.dispose()` in lifespan shutdown block + SIGTERM signal handler.
- **D-11:** 10-second preStop hook sleep. `terminationGracePeriodSeconds=30`.
- **D-12:** Shutdown sequence: preStop sleep (10s) → SIGTERM → uvicorn drain → lifespan shutdown → pod terminates.
- **D-13:** Two separate init containers (both using geo-api image): `alembic-migrate` (runs `alembic upgrade head`) and `spell-rebuild` (runs `geo-import rebuild-dictionary`).
- **D-14:** Init containers receive DB credentials via envFrom (ConfigMap + Secret refs).

### Claude's Discretion

- Resource requests/limits for geo-api and Ollama sidecar containers
- Exact Kustomize patch strategy (strategic merge vs JSON patch)
- ConfigMap key naming conventions
- ArgoCD Application CR sync policy and auto-heal settings
- Whether to add a DB-wait init container before alembic-migrate or rely on alembic's built-in retry

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESIL-01 | /health/live endpoint (process-only, no DB) for K8s liveness probe | FastAPI router extension pattern; no DB dep; returns 200 immediately |
| RESIL-02 | /health/ready endpoint (DB + all registered providers verified) for K8s readiness probe | SQLAlchemy `SELECT 1` check + `app.state.providers` count from request context |
| RESIL-03 | Graceful shutdown with preStop hook and SIGTERM handling for asyncpg pool cleanup | uvicorn 0.42 handles SIGTERM natively; lifespan shutdown block disposes `engine`; preStop lifecycle hook documented |
| RESIL-04 | Startup data initialization — spell dictionary rebuild and provider data verification on boot | Init container pattern using geo-api image with CMD override; `geo-import rebuild-dictionary` is the CLI command |
| DEPLOY-02 | K8s Deployment manifests for civpulse-dev and civpulse-prod with Ollama sidecar | k3s v1.34 supports native sidecar; Kustomize base+overlay structure documented |
| DEPLOY-03 | ClusterIP Service (internal only) for both environments | Standard K8s Service with ClusterIP type; overlay sets namespace |
| DEPLOY-04 | Init containers for Alembic migrations and spell dictionary rebuild | geo-api image has alembic + geo-import CLI; postgresql-client in image for pg_isready |
| DEPLOY-05 | ConfigMap and Secret resources for environment-specific configuration | Kustomize overlay adds env-specific ConfigMap/Secret; CHANGEME placeholder secret pattern |
| DEPLOY-07 | ArgoCD Application CRs for dev and prod pointing to manifest paths | ArgoCD v3.3.2; voter-api pattern as template; overlay path = `k8s/overlays/dev` |
</phase_requirements>

---

## Summary

Phase 20 deploys geo-api to both `civpulse-dev` and `civpulse-prod` K8s namespaces. The work divides into four tracks: (1) FastAPI health endpoint extension, (2) graceful shutdown wiring, (3) Kustomize manifest authoring, and (4) ArgoCD Application CR creation.

The environment is well-characterized. k3s is v1.34.4+k3s1 — the native sidecar feature (`initContainers` with `restartPolicy: Always`) is stable and available. Both namespaces exist. ArgoCD v3.3.2 is running with 7 healthy applications as reference templates. The `local-path` StorageClass is the only available class and matches the pattern used by existing PVCs. PostgreSQL is reachable at `postgresql.civpulse-infra.svc.cluster.local:5432` with a confirmed endpoint of `100.67.17.69:5432`.

The geo-api Dockerfile already uses exec-form CMD, which means uvicorn runs as PID 1 and receives SIGTERM directly. The lifespan pattern in `main.py` is the correct place for `await engine.dispose()`. The existing `k8s/ollama-deployment.yaml` provides a reusable model-pull init container pattern that must be adapted for the sidecar context. DB credentials for dev/prod are stored in project memory and must not be committed to the repo — only CHANGEME placeholders go in version control.

**Primary recommendation:** Use the voter-api ArgoCD Application CR as the template for geo-api CRs. Use strategic merge patches in Kustomize overlays (simpler, less error-prone than JSON patches for Deployment spec changes). Add a DB-wait init container before `alembic-migrate` using `pg_isready` — the geo-api image already includes `postgresql-client`.

---

## Project Constraints (from CLAUDE.md)

Global `~/.claude/CLAUDE.md` directives that apply to this phase:

- Use `uv run` for all Python commands — never bare `python` or `python3`
- Lint with `ruff` before committing
- Commit on branches, not main (unless requested)
- Always commit after each task/story/phase
- Never push to GitHub unless explicitly requested
- Use Conventional Commits for commit messages
- After any UI changes, visually verify with Playwright (not applicable to this phase — no UI changes)

**Impact on this phase:** Init container commands inside K8s manifests that invoke Python must use the venv path (`/app/.venv/bin/geo-import` or `alembic`) — the container already has `/app/.venv/bin` on PATH via the Dockerfile ENV. No bare `python` calls in YAML.

---

## Standard Stack

### Core
| Component | Version | Purpose | Why |
|-----------|---------|---------|-----|
| FastAPI | 0.135.1 (installed) | Health endpoint router extension | Already in project; add two routes to existing `api/health.py` |
| SQLAlchemy async | 2.0.48 (installed) | DB check in readiness probe and engine disposal on shutdown | Already in project; `engine.dispose()` is the correct async teardown |
| uvicorn | 0.42.0 (installed) | ASGI server; receives SIGTERM as PID 1 (exec-form CMD) | Already in project; handles SIGTERM natively |
| Kustomize | v5.0.4 (kubectl bundled) | K8s manifest base+overlay management | Bundled in kubectl v1.29; standalone not needed |
| ArgoCD | v3.3.2 (cluster) | GitOps CD; detects kustomization.yaml automatically | Running in cluster; no configuration changes needed |
| k3s | v1.34.4+k3s1 (cluster) | Target Kubernetes runtime | Native sidecar feature stable and enabled |

### Supporting
| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| ollama/ollama | latest (existing manifest) | Ollama sidecar image | Sidecar container in Deployment |
| postgresql-client | in geo-api image | `pg_isready` for DB-wait init container | Before `alembic-migrate` init container |
| psycopg2-binary | 2.9.11 (installed) | Alembic sync migrations | Used by alembic env.py via `database_url_sync` |
| local-path | default StorageClass | Ollama PVC provisioning | Only StorageClass in cluster; 10Gi RWO |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Strategic merge patches | JSON patches | JSON patches are more precise but harder to read; strategic merge is sufficient for env vars, image tags, replicas |
| CHANGEME placeholder secrets | SealedSecrets / external-secrets | CHANGEME is simpler, no additional operators needed, consistent with Phase 18 decision |
| pg_isready DB-wait init container | Rely on alembic retry | alembic has no built-in retry; a DB-wait container is safer and explicit |

---

## Architecture Patterns

### Recommended K8s Directory Structure

```
k8s/
├── base/
│   ├── kustomization.yaml          # lists all base resources
│   ├── deployment.yaml             # geo-api Deployment with Ollama sidecar + init containers
│   ├── service.yaml                # ClusterIP Service port 8000
│   ├── configmap.yaml              # shared non-secret config keys
│   └── pvc.yaml                    # Ollama PVC (10Gi RWO, local-path)
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml      # namespace, patches, image tag, env-specific resources
    │   ├── configmap-patch.yaml    # dev DATABASE_URL, ENVIRONMENT=development, cascade_llm_enabled=false
    │   ├── secret.yaml             # CHANGEME placeholder for dev credentials
    │   └── argocd-app.yaml         # ArgoCD Application CR for civpulse-dev
    └── prod/
        ├── kustomization.yaml      # namespace, patches, image tag, env-specific resources
        ├── configmap-patch.yaml    # prod DATABASE_URL, ENVIRONMENT=production, cascade_llm_enabled=true
        ├── secret.yaml             # CHANGEME placeholder for prod credentials
        └── argocd-app.yaml         # ArgoCD Application CR for civpulse-prod
```

### Pattern 1: Health Endpoints — Liveness and Readiness

**What:** Two new routes added to `src/civpulse_geo/api/health.py`. Liveness has zero dependencies. Readiness checks DB and provider registry counts.

**When to use:** K8s probes exclusively. The existing `/health` endpoint remains for human use.

**Key constraint:** The readiness endpoint needs `app.state.providers` — this requires a `Request` parameter to access `request.app.state`. Do NOT use `Depends(get_db)` for the liveness endpoint.

```python
# Source: FastAPI docs + project pattern
from fastapi import APIRouter, Request
from sqlalchemy import text

@router.get("/health/live")
async def health_live():
    # No dependencies — process-only, returns immediately
    return {"status": "ok"}

@router.get("/health/ready")
async def health_ready(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "reason": f"db: {exc}"})

    geo_count = len(request.app.state.providers)
    val_count = len(request.app.state.validation_providers)
    if geo_count < 2 or val_count < 2:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "reason": f"providers: {geo_count} geocoding, {val_count} validation (need ≥2 each)",
            },
        )
    return {"status": "ready", "geocoding_providers": geo_count, "validation_providers": val_count}
```

### Pattern 2: Graceful Shutdown (lifespan + SIGTERM handler)

**What:** Lifespan shutdown block disposes `engine`. Optional SIGTERM signal handler as safety net. preStop hook sleeps 10s to drain.

**When to use:** Apply to `main.py` lifespan function. uvicorn 0.42 with exec-form CMD handles SIGTERM natively — lifespan `yield` cleanup runs automatically.

**Critical detail:** The sync engine created inline in the lifespan startup block (for spell dictionary) is local to the block. Only the module-level `engine` from `database.py` persists and needs explicit disposal.

```python
# Source: SQLAlchemy 2.0 async docs + FastAPI lifespan pattern
# In lifespan, after yield:
yield
await app.state.http_client.aclose()
from civpulse_geo.database import engine as _async_engine
await _async_engine.dispose()
logger.info("Shutting down CivPulse Geo API — async engine disposed")
```

**preStop hook (in Deployment spec):**
```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sleep", "10"]
```

**terminationGracePeriodSeconds: 30** — 10s preStop + 20s for uvicorn to drain in-flight requests.

**SIGTERM signal handler (belt and suspenders):**
```python
import asyncio
import signal

def _install_sigterm_handler(app: FastAPI) -> None:
    loop = asyncio.get_event_loop()
    def _handle_sigterm():
        loop.create_task(_sigterm_shutdown(app))
    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

async def _sigterm_shutdown(app: FastAPI) -> None:
    from civpulse_geo.database import engine as _engine
    logger.info("SIGTERM received — disposing async engine")
    await _engine.dispose()
```

Install in lifespan before yield. This is safety net only; uvicorn's own SIGTERM handling triggers the lifespan shutdown which also disposes the engine.

### Pattern 3: Native K8s Sidecar (Ollama)

**What:** Ollama defined in `initContainers` with `restartPolicy: Always`. Runs before and throughout main container lifetime. Model-pull is a separate regular init container that runs to completion before the sidecar starts.

**Ordering in initContainers list matters:**
1. `db-wait` (regular init) — waits for PostgreSQL to be reachable
2. `alembic-migrate` (regular init) — runs `alembic upgrade head`
3. `spell-rebuild` (regular init) — runs `geo-import rebuild-dictionary`
4. `model-pull` (regular init) — pulls qwen2.5:3b if PVC is empty
5. `ollama` (sidecar, `restartPolicy: Always`) — must be LAST in initContainers list

**Critical:** The sidecar must be the last item in `initContainers`. All regular init containers above it must complete before the sidecar starts. Main containers start only after the sidecar's `startupProbe` passes.

```yaml
# Source: kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/
initContainers:
  - name: db-wait
    image: ghcr.io/civicpulse/geo-api:latest
    command: ["sh", "-c"]
    args:
      - |
        until pg_isready -h postgresql.civpulse-infra.svc.cluster.local -p 5432 -U geo_dev; do
          echo "waiting for postgres..."; sleep 2
        done
    envFrom:
      - configMapRef:
          name: geo-api-config
      - secretRef:
          name: geo-api-secret

  - name: alembic-migrate
    image: ghcr.io/civicpulse/geo-api:latest
    command: ["alembic", "upgrade", "head"]
    envFrom:
      - configMapRef:
          name: geo-api-config
      - secretRef:
          name: geo-api-secret

  - name: spell-rebuild
    image: ghcr.io/civicpulse/geo-api:latest
    command: ["geo-import", "rebuild-dictionary"]
    envFrom:
      - configMapRef:
          name: geo-api-config
      - secretRef:
          name: geo-api-secret

  - name: model-pull
    image: ollama/ollama:latest
    command: ["sh", "-c"]
    args:
      - |
        /bin/ollama serve &
        until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do sleep 2; done
        if ! ollama list | grep -q "qwen2.5:3b"; then
          ollama pull qwen2.5:3b
        fi
        kill %1
    volumeMounts:
      - name: ollama-data
        mountPath: /root/.ollama

  - name: ollama          # SIDECAR — must be last
    image: ollama/ollama:latest
    restartPolicy: Always
    ports:
      - containerPort: 11434
    volumeMounts:
      - name: ollama-data
        mountPath: /root/.ollama
    startupProbe:
      httpGet:
        path: /api/tags
        port: 11434
      failureThreshold: 30
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /api/tags
        port: 11434
      initialDelaySeconds: 5
      periodSeconds: 10
      failureThreshold: 6
    livenessProbe:
      httpGet:
        path: /api/tags
        port: 11434
      initialDelaySeconds: 30
      periodSeconds: 30
      failureThreshold: 3
    resources:
      requests:
        memory: "2Gi"
        cpu: "500m"
      limits:
        memory: "4Gi"
```

### Pattern 4: Kustomize Base + Overlay

**What:** Base contains the Deployment/Service/PVC/ConfigMap with dev-neutral defaults. Overlay patches set namespace, image tag, and env-specific ConfigMap/Secret values.

**Overlay kustomization.yaml structure:**
```yaml
# k8s/overlays/dev/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: civpulse-dev

resources:
  - ../../base
  - secret.yaml
  - argocd-app.yaml

images:
  - name: ghcr.io/civicpulse/geo-api
    newTag: latest   # Phase 21 CI/CD will update to SHA tag

patches:
  - path: configmap-patch.yaml
    target:
      kind: ConfigMap
      name: geo-api-config
```

**Base kustomization.yaml:**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml
  - pvc.yaml

commonLabels:
  app.kubernetes.io/name: geo-api
  app.kubernetes.io/part-of: civpulse-geo
```

### Pattern 5: ArgoCD Application CR

**What:** Declarative Application resource placed in `argocd` namespace. ArgoCD auto-detects Kustomize when `kustomization.yaml` is present in the source path.

**Reference:** All 7 existing CivicPulse apps (voter-api, run-api, contact-api, bibbunited) use identical structure with `automated: prune + selfHeal`, `CreateNamespace=false`, pointing to flat manifest directories. For geo-api, the path points to the overlay.

```yaml
# Source: live cluster voter-api-dev Application CR (verified)
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: geo-api-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/CivicPulse/geo-api.git
    targetRevision: main
    path: k8s/overlays/dev
  destination:
    server: https://kubernetes.default.svc
    namespace: civpulse-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
```

### Anti-Patterns to Avoid

- **Shell-form CMD in Dockerfile** — would make the shell PID 1, not uvicorn. SIGTERM would not reach uvicorn. The Dockerfile already uses exec-form CMD; do not change it.
- **Sidecar as regular container** — Old pattern (Ollama in `spec.containers`) provides no ordering guarantee. Geo-api would start before Ollama is ready, causing LLM corrector initialization to fail. Use native sidecar.
- **Model-pull in sidecar** — The sidecar `restartPolicy: Always` means the container restarts on failure. If model-pull logic is in the sidecar, it re-pulls on every restart. Keep model-pull as a separate regular init container.
- **DB credentials in ConfigMap** — DATABASE_URL and DATABASE_URL_SYNC contain passwords. Put them in Secret, not ConfigMap. ConfigMap holds non-secret config (ENVIRONMENT, LOG_LEVEL, OLLAMA_URL, CASCADE_LLM_ENABLED).
- **patchesStrategicMerge field** — Deprecated in Kustomize v5. Use the `patches` field instead.
- **Sidecar probe blocking pod readiness** — If Ollama's `readinessProbe` is set, it affects pod-level readiness. In production where `cascade_llm_enabled=false` in dev, the Ollama sidecar may still be installed. Since the readiness check for geo-api does NOT require Ollama, either (a) omit Ollama `readinessProbe` or (b) accept that pod readiness requires Ollama to be ready. Decision: keep readiness probe on Ollama but set generous thresholds — model load takes 10-30s.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DB wait before migrations | Custom retry loop in Python script | `pg_isready` in a shell one-liner | geo-api image already has postgresql-client; pg_isready is purpose-built |
| Kustomize templating | Helm-style template variables | Kustomize strategic merge patches | Plain YAML patches, no templating engine needed; kubectl bundles kustomize v5 |
| Pod readiness signaling | Custom health check HTTP server | FastAPI route `/health/ready` | Already inside the app, no sidecar needed |
| Secret rotation | Manual kubectl apply per deploy | CHANGEME placeholders + manual `kubectl create secret` | Decided in D-06; no external operator required |
| Model presence check in pull | Always pull (slow) | `ollama list | grep -q` before pull | Avoids re-downloading 2GB model on restart when PVC already has it |

**Key insight:** This phase is almost entirely configuration and wiring, not new code. The existing infrastructure (ArgoCD, k3s, PostgreSQL service, geo-api image) provides all building blocks. The code changes are minimal: two new FastAPI routes and lifespan shutdown cleanup.

---

## Common Pitfalls

### Pitfall 1: sidecar ordering — sidecar must be LAST in initContainers
**What goes wrong:** If the `ollama` sidecar is placed before any regular init container, that regular init container runs AFTER the sidecar starts. The regular init containers will try to connect to Ollama (which may not be ready) or block startup unnecessarily.
**Why it happens:** Kubernetes processes `initContainers` in array order. Sidecars (`restartPolicy: Always`) start like regular init containers but then continue running. Items listed AFTER the sidecar start while the sidecar is already running.
**How to avoid:** Always declare the sidecar as the LAST item in `initContainers`. Regular init containers should all precede it.
**Warning signs:** If `kubectl describe pod` shows the sidecar starting before `alembic-migrate` completes.

### Pitfall 2: Secret placeholder values must not be valid connection strings
**What goes wrong:** If CHANGEME placeholders accidentally look like valid connection strings, the app starts with wrong credentials and silently connects to nothing (or the wrong DB).
**Why it happens:** Python's `pydantic-settings` reads env vars at import time. If the Secret is applied with CHANGEME values, `Settings()` instantiates with those values.
**How to avoid:** Use literal `CHANGEME` strings. Document that real credentials must be applied via `kubectl create secret --from-literal` before ArgoCD can sync to Healthy. Put a comment in the secret.yaml explaining this.
**Warning signs:** Pod starts but readiness probe returns 503 with `db: unavailable`.

### Pitfall 3: ArgoCD syncing the Secret with CHANGEME credentials to the cluster
**What goes wrong:** ArgoCD auto-sync applies the placeholder Secret, overwriting real credentials that were manually applied.
**Why it happens:** ArgoCD `selfHeal: true` treats any out-of-sync resource (including secrets modified outside git) as drift and resets it.
**How to avoid:** Two options: (a) exclude the Secret from ArgoCD management using `argocd.argoproj.io/managed: "false"` annotation, or (b) accept that real credentials must be re-applied after each ArgoCD sync (not ideal). **Recommended:** Use option (a) — annotate the Secret to exclude it from sync, or put the secret.yaml outside the kustomization resources list and manage it manually. This matches D-06 (no external secrets operator).
**Warning signs:** `kubectl get secret geo-api-secret -n civpulse-dev -o jsonpath='{.data.DATABASE_URL}'` decodes to CHANGEME after ArgoCD sync.

### Pitfall 4: Readiness probe during slow Ollama model load
**What goes wrong:** Pod stays NotReady for extended periods (30-120s) if Ollama startup probe is too aggressive. This causes ArgoCD to show degraded health.
**Why it happens:** Ollama loads the qwen2.5:3b model (2GB) into memory on first startup. The `/api/tags` endpoint is unavailable during load.
**How to avoid:** Use `startupProbe` on Ollama sidecar with `failureThreshold: 30, periodSeconds: 10` (300s max). Once startup probe passes, liveness probe takes over with gentler settings.
**Warning signs:** Pod restarts repeatedly, logs show `Startup probe failed`.

### Pitfall 5: geo-api readiness check depends on provider count — cold environment
**What goes wrong:** In a freshly provisioned namespace with no GIS data loaded, all conditional providers (OA, Tiger, NAD, Macon-Bibb) are absent. Only census and scourgify register. Provider count = 1 geocoding, 1 validation → readiness check fails → pod never becomes ready.
**Why it happens:** D-02 requires ≥2 geocoding AND ≥2 validation providers. In a data-empty environment, only census (geocoding) and scourgify (validation) register.
**How to avoid:** Before first deploy to a namespace, load at minimum OA or NAD data so ≥2 providers register. Document this as a prerequisite in the deployment runbook (or in a DEPLOYMENT.md).
**Warning signs:** `/health/ready` returns 503 with `providers: 1 geocoding, 1 validation` even after successful DB connection.

### Pitfall 6: `kubectl kustomize` version mismatch with Kustomize features
**What goes wrong:** Kustomize features available in standalone kustomize may not be available in the version bundled with kubectl.
**Why it happens:** kubectl bundles Kustomize v5.0.4; standalone latest may be newer.
**How to avoid:** Use only features documented in v5.0.4. All features used in this phase (strategic merge patches, `images:` field, `namespace:` field) are in v5.0.4. Validate with `kubectl kustomize k8s/overlays/dev` before committing.

---

## Code Examples

### /health/live endpoint
```python
# Source: FastAPI docs + RESIL-01 requirement
@router.get("/health/live")
async def health_live():
    """Liveness probe — process-only, no external dependencies."""
    return {"status": "ok"}
```

### /health/ready endpoint
```python
# Source: RESIL-02 requirement + app.state provider pattern from main.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from civpulse_geo.database import get_db

@router.get("/health/ready")
async def health_ready(request: Request, db: AsyncSession = Depends(get_db)):
    """Readiness probe — DB connected AND provider threshold met."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "reason": f"db: {exc}"},
        )
    geo_count = len(request.app.state.providers)
    val_count = len(request.app.state.validation_providers)
    if geo_count < 2 or val_count < 2:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "geocoding_providers": geo_count,
                "validation_providers": val_count,
                "reason": "insufficient providers",
            },
        )
    return {
        "status": "ready",
        "geocoding_providers": geo_count,
        "validation_providers": val_count,
    }
```

### Lifespan shutdown cleanup
```python
# Source: SQLAlchemy 2.0 asyncio docs + existing main.py lifespan pattern
# After yield in lifespan():
yield
await app.state.http_client.aclose()
from civpulse_geo.database import engine as _async_engine
await _async_engine.dispose()
logger.info("Async engine disposed — shutdown complete")
```

### K8s Deployment probe configuration
```yaml
# Source: kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
# geo-api main container probes
startupProbe:
  httpGet:
    path: /health/live
    port: 8000
  failureThreshold: 30      # 300s max for startup (spell load + provider registration)
  periodSeconds: 10
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 0
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 0
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

### K8s preStop hook and terminationGracePeriodSeconds
```yaml
# Source: kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/
spec:
  terminationGracePeriodSeconds: 30
  containers:
    - name: geo-api
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sleep", "10"]
```

### ArgoCD Application CR (geo-api-dev)
```yaml
# Source: live cluster voter-api-dev Application CR (verified 2026-03-29)
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: geo-api-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/CivicPulse/geo-api.git
    targetRevision: main
    path: k8s/overlays/dev
  destination:
    server: https://kubernetes.default.svc
    namespace: civpulse-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ollama as separate Deployment + Service | Native sidecar in initContainers | k3s v1.29+ (this project: v1.34) | No headless service needed; localhost communication; guaranteed startup ordering |
| patchesStrategicMerge in kustomization | `patches:` field | Kustomize v5 | Old field deprecated but still works; use new `patches:` field |
| `initialDelaySeconds` on liveness | startupProbe pattern | K8s 1.16+ | startupProbe gives large startup window without penalizing steady-state restarts |
| Gunicorn + Uvicorn workers for graceful shutdown | Single uvicorn worker + exec-form CMD | Project decision (Phase 19 D-13) | Simpler pool management; K8s handles scaling via replicas |

**Deprecated/outdated patterns for this project:**
- `k8s/ollama-deployment.yaml`, `k8s/ollama-service.yaml`: Replaced by sidecar in Deployment (D-05)
- `k8s/ollama-pvc.yaml`: Moves to `k8s/base/pvc.yaml` (D-07)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| k3s cluster | All K8s manifests | Yes | v1.34.4+k3s1 | — |
| kubectl | Manifest validation, apply | Yes | v1.29.0 client | — |
| kustomize (bundled) | Overlay build | Yes | v5.0.4 | — |
| ArgoCD | DEPLOY-07 | Yes | v3.3.2 | — |
| civpulse-dev namespace | Dev deployment | Yes | Active 28d | — |
| civpulse-prod namespace | Prod deployment | Yes | Active 28d | — |
| local-path StorageClass | Ollama PVC | Yes | Default | — |
| postgresql.civpulse-infra | DB connectivity | Yes | Endpoint 100.67.17.69:5432 | — |
| GHCR image | Init containers + main container | Pending Phase 19 | Must be pushed before deploy | Cannot deploy without image |
| GIS data (OA/NAD/Macon-Bibb) | Provider count ≥2 for readiness | Unknown | Must be loaded before readiness passes | Readiness probe fails until loaded |

**Missing dependencies with no fallback:**
- GHCR image (`ghcr.io/civicpulse/geo-api`) must be published to GHCR before any K8s deployment. Phase 19 covers this. If Phase 19 is not complete, pods will ImagePullBackOff.

**Missing dependencies with fallback:**
- GIS data: Readiness probe will fail (503) but pod starts. A startup runbook note is sufficient. This is not a blocker for manifest authoring.

---

## Resource Sizing (Claude's Discretion)

Based on Phase 18 pool sizing (5+5=10 connections), single worker, and existing cluster patterns:

### geo-api main container
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```
Rationale: asyncpg pool (10 connections) + SymSpell dictionary (varies by data size) + in-flight requests. 256Mi request is conservative; 512Mi limit gives headroom. 100m CPU request mirrors other CivicPulse services; 500m limit for burst geocoding.

### Ollama sidecar
```yaml
resources:
  requests:
    memory: "2Gi"
    cpu: "500m"
  limits:
    memory: "4Gi"
```
Rationale: Carries forward from existing `ollama-deployment.yaml`. qwen2.5:3b requires ~2GB RAM minimum; 4Gi limit for model inference. CPU is CPU-based inference so limit high.

### Init containers (alembic-migrate, spell-rebuild, db-wait)
```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "50m"
  limits:
    memory: "256Mi"
    cpu: "200m"
```
Rationale: Short-lived, limited activity. Matches pattern from opendismissal project.

### Model-pull init container
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "100m"
  limits:
    memory: "1Gi"
    cpu: "500m"
```
Rationale: Downloads 2GB model file to PVC, some decompression overhead.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/test_health.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESIL-01 | `/health/live` returns 200, no DB needed | unit | `uv run pytest tests/test_health.py::test_health_live -x` | ❌ Wave 0 |
| RESIL-01 | `/health/live` returns 200 even when DB unavailable | unit | `uv run pytest tests/test_health.py::test_health_live_db_down -x` | ❌ Wave 0 |
| RESIL-02 | `/health/ready` returns 200 with DB connected and ≥2 providers | unit | `uv run pytest tests/test_health.py::test_health_ready_ok -x` | ❌ Wave 0 |
| RESIL-02 | `/health/ready` returns 503 with DB down | unit | `uv run pytest tests/test_health.py::test_health_ready_db_down -x` | ❌ Wave 0 |
| RESIL-02 | `/health/ready` returns 503 with insufficient providers | unit | `uv run pytest tests/test_health.py::test_health_ready_insufficient_providers -x` | ❌ Wave 0 |
| RESIL-03 | Shutdown disposes async engine (lifespan teardown) | unit | `uv run pytest tests/test_shutdown.py -x` | ❌ Wave 0 |
| RESIL-04 | Spell-rebuild init container command resolves (CLI callable) | smoke | `uv run geo-import rebuild-dictionary --help` | ✅ (CLI exists) |
| DEPLOY-04 | Alembic-migrate init container command works | smoke | `uv run alembic upgrade head --help` | ✅ (alembic installed) |
| DEPLOY-02/03/05 | Kustomize overlays build without errors | smoke | `kubectl kustomize k8s/overlays/dev` | ❌ Wave 0 (manifests don't exist yet) |
| DEPLOY-07 | ArgoCD Application CRs valid schema | smoke | `kubectl apply --dry-run=client -f k8s/overlays/dev/argocd-app.yaml` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_health.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green + `kubectl kustomize k8s/overlays/dev` and `k8s/overlays/prod` build clean before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_health.py` — extend with `test_health_live`, `test_health_live_db_down`, `test_health_ready_ok`, `test_health_ready_db_down`, `test_health_ready_insufficient_providers`
- [ ] `tests/test_shutdown.py` — verify lifespan shutdown calls `engine.dispose()`
- [ ] `k8s/base/` directory and all base manifest files
- [ ] `k8s/overlays/dev/` and `k8s/overlays/prod/` directories and all overlay files

---

## Open Questions

1. **Should the ArgoCD Secret be excluded from ArgoCD sync management?**
   - What we know: ArgoCD `selfHeal: true` will overwrite manually-applied secrets with the CHANGEME placeholder values on the next sync cycle.
   - What's unclear: Whether to use `argocd.argoproj.io/managed: "false"` annotation on the Secret or exclude it from the Kustomize resources list.
   - Recommendation: Exclude the Secret from the `resources:` list in `kustomization.yaml`. Apply it manually once with `kubectl create secret`. Do not include it in Kustomize at all. This is the simplest approach that avoids all sync conflict. Document in a `DEPLOYMENT.md` or comment.

2. **Should dev deployment include the Ollama sidecar?**
   - What we know: D-09 says `cascade_llm_enabled=false` in dev ConfigMap. The sidecar still starts and loads the model even when cascade_llm_enabled=false.
   - What's unclear: Whether it's worth the 2GB PVC and 2Gi memory overhead in dev where LLM is disabled.
   - Recommendation: Include the sidecar in dev but with lower resource limits. This validates the sidecar manifest pattern in dev before prod. The dev PVC will require a separate `ollama-pvc` per namespace (two PVCs total, each 10Gi).

3. **Does `alembic upgrade head` need DATABASE_URL_SYNC or DATABASE_URL?**
   - What we know: `alembic/env.py` reads `settings.database_url_sync` which is `postgresql+psycopg2://...`. The init container CMD is `alembic upgrade head`.
   - What's unclear: Whether the environment variable name is `DATABASE_URL_SYNC` or `SQLALCHEMY_URL` for the init container.
   - Recommendation: The `DATABASE_URL_SYNC` env var maps directly to `Settings.database_url_sync` via pydantic-settings (lowercased). Include `DATABASE_URL_SYNC` in the Secret with the psycopg2 connection string.

---

## Sources

### Primary (HIGH confidence)
- Live cluster inspection (kubectl) — k3s v1.34.4, namespaces, StorageClass, ArgoCD v3.3.2, voter-api CR template, PVC patterns
- `kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/` — Native sidecar feature (restartPolicy: Always), startup ordering, probe behavior, pod termination
- `kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/` — Probe field defaults and startupProbe behavior
- Existing project source files — `health.py`, `main.py`, `database.py`, `config.py`, `Dockerfile`, `k8s/ollama-deployment.yaml` — verified patterns
- `opendismissal` project `k8s/` — Kustomize base+overlay pattern used in the same CivicPulse infrastructure

### Secondary (MEDIUM confidence)
- WebSearch: FastAPI graceful shutdown + SIGTERM handling — confirmed uvicorn 0.42 handles SIGTERM natively via exec-form CMD
- WebSearch: SQLAlchemy async engine dispose — confirmed `await engine.dispose()` is the correct async teardown pattern; lifespan shutdown is the right location
- WebSearch: Kustomize strategic merge patches — confirmed `patches:` replaces deprecated `patchesStrategicMerge`
- WebSearch: ArgoCD Application CR with Kustomize path — confirmed auto-detection of kustomization.yaml, path points to overlay

### Tertiary (LOW confidence)
- Resource sizing recommendations — based on existing cluster patterns and Ollama documentation; actual values should be tuned after initial deploy

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against installed packages and live cluster
- Architecture patterns: HIGH — native sidecar from official K8s docs, ArgoCD CR from live cluster template, health endpoint from existing code
- Environment: HIGH — all verified via kubectl against live cluster
- Resource sizing: MEDIUM — reasonable estimates, cluster-specific tuning needed post-deploy
- Pitfalls: HIGH — sourced from official docs and known production patterns

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (30 days; k3s, ArgoCD, FastAPI versions stable)
