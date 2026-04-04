# Phase 20: Health, Resilience, and K8s Manifests - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 20-health-resilience-and-k8s-manifests
**Areas discussed:** Health endpoint design, Manifest organization, Ollama sidecar lifecycle, Graceful shutdown & init containers

---

## Health Endpoint Design

### Readiness probe verification strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Registration check | Verify providers are registered in app.state and DB is reachable. Fast (<50ms), no external calls. | |
| Active probe per provider | Call each provider with test address. Thorough but slow (3-5s), Census timeout makes pod unready. | |
| DB + provider count threshold | Check DB connectivity and minimum N providers registered. Tolerates individual absence, catches catastrophic. | ✓ |

**User's choice:** DB + provider count threshold
**Notes:** None

### Minimum provider count for readiness

| Option | Description | Selected |
|--------|-------------|----------|
| At least 1 provider | Minimum viable — any geocoding provider. Works for dev. | |
| At least 2 providers | Census + at least one local provider. Catches missing local data. | ✓ |
| At least 3 providers | Stricter — Census + 2 local. May be too aggressive for dev. | |

**User's choice:** At least 2 providers
**Notes:** None

### Existing /health endpoint fate

| Option | Description | Selected |
|--------|-------------|----------|
| Keep as-is | Stays for backward compat and human inspection. New probe endpoints separate. | ✓ |
| Replace with /health/ready | Remove old /health, redirect to /health/ready. Breaks existing callers. | |

**User's choice:** Keep as-is
**Notes:** None

### Readiness provider scope

| Option | Description | Selected |
|--------|-------------|----------|
| Both geocoding + validation | Check both app.state.providers and app.state.validation_providers. | ✓ |
| Geocoding providers only | Simpler check, validation mirrors geocoding anyway. | |

**User's choice:** Both geocoding + validation
**Notes:** None

---

## Manifest Organization

### Environment manifest structure

| Option | Description | Selected |
|--------|-------------|----------|
| Kustomize base + overlays | k8s/base/ shared, k8s/overlays/dev/ and prod/ patch env-specific values. DRY and standard. | ✓ |
| Plain per-environment YAMLs | Full copies in k8s/dev/ and k8s/prod/. Simple but duplicated. | |
| Flat with naming convention | All in k8s/ root with env suffixes. Simplest but messy at scale. | |

**User's choice:** Kustomize base + overlays
**Notes:** None

### Existing standalone Ollama manifests

| Option | Description | Selected |
|--------|-------------|----------|
| Remove after sidecar merge | Delete dead code. PVC moves to base Deployment. | ✓ |
| Keep alongside sidecar | Rename to k8s/ollama-standalone/ as fallback option. | |
| Move to k8s/archive/ | Archive for reference, not used by ArgoCD. | |

**User's choice:** Remove after sidecar merge
**Notes:** None

### K8s Secrets handling

| Option | Description | Selected |
|--------|-------------|----------|
| SealedSecrets | Encrypt with Bitnami SealedSecrets controller. Safe to commit. | |
| Placeholder + manual apply | Commit YAML with CHANGEME values. Real values applied via kubectl. | ✓ |
| External Secrets Operator | Sync from external stores. Overkill — no external store in place. | |

**User's choice:** Placeholder + manual apply
**Notes:** None

---

## Ollama Sidecar Lifecycle

### Model data persistence

| Option | Description | Selected |
|--------|-------------|----------|
| PVC | 10Gi ReadWriteOnce PVC. Model-pull init container runs when empty. Survives restarts. | ✓ |
| EmptyDir + always pull | No PVC. Model re-downloaded every pod start (~2min, 2GB). | |
| Baked into custom image | Custom Ollama image with model pre-loaded. No PVC/init needed. | |

**User's choice:** PVC
**Notes:** None

### Startup ordering strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Existing graceful fallback | geo-api already handles missing Ollama (llm_corrector=None). No K8s ordering needed. | |
| K8s native sidecar | K8s 1.29+ initContainers with restartPolicy: Always. Guaranteed ordering. | ✓ |
| Startup probe dependency | Startup probe checks localhost:11434. Blocks all traffic until Ollama ready. Overkill. | |

**User's choice:** K8s native sidecar (restartPolicy: Always)
**Notes:** Must verify k3s version >= 1.29

---

## Graceful Shutdown & Init Containers

### asyncpg pool cleanup approach

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit dispose in lifespan | `await engine.dispose()` in shutdown block after yield. | ✓ (primary) |
| SIGTERM signal handler | Register signal handler for SIGTERM that triggers pool cleanup. | ✓ (safety net) |

**User's choice:** Both — belt and suspenders
**Notes:** User explicitly requested both approaches for redundancy, consistent with Phase 17 spell dictionary pattern.

### Init container structure

| Option | Description | Selected |
|--------|-------------|----------|
| Two separate init containers | 1) alembic-migrate, 2) spell-rebuild. Clear separation, independent failure/retry. | ✓ |
| Single combined init container | One shell script: migrate then rebuild. Fewer containers but coupled failure. | |

**User's choice:** Two separate init containers
**Notes:** None

### preStop hook sleep duration

| Option | Description | Selected |
|--------|-------------|----------|
| 5 seconds | Standard for internal services. 25s remaining for in-flight. | |
| 10 seconds | Conservative. 20s remaining. Safety margin for load testing. | ✓ |
| You decide | Claude picks based on P95 latency. | |

**User's choice:** 10 seconds
**Notes:** None

---

## Claude's Discretion

- Resource requests/limits for geo-api and Ollama sidecar containers
- Exact Kustomize patch strategy (strategic merge vs JSON patch)
- ConfigMap key naming conventions
- ArgoCD Application CR sync policy and auto-heal settings
- Whether to add a DB-wait init container before alembic-migrate or rely on alembic's built-in retry

## Deferred Ideas

None — discussion stayed within phase scope
