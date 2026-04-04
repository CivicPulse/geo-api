---
phase: 20-health-resilience-and-k8s-manifests
plan: "02"
subsystem: kubernetes
tags: [k8s, kustomize, deployment, sidecar, init-containers, probes, graceful-shutdown]
completed: "2026-03-30T04:02:34Z"
duration: "2 minutes"
tasks_completed: 2
tasks_total: 2
files_created: 5
files_modified: 0

dependency_graph:
  requires:
    - 20-01-PLAN.md (health endpoints /health/live and /health/ready implemented)
    - 19-01-SUMMARY.md (Dockerfile with postgresql-client, geo-import CLI on PATH)
    - k8s/ollama-deployment.yaml (model-pull init container pattern reused)
  provides:
    - k8s/base/kustomization.yaml (Kustomize base resource list and common labels)
    - k8s/base/deployment.yaml (Deployment with sidecar, init containers, probes, preStop)
    - k8s/base/service.yaml (ClusterIP Service on port 8000)
    - k8s/base/configmap.yaml (non-secret configuration keys)
    - k8s/base/pvc.yaml (Ollama PVC 10Gi RWO)
  affects:
    - k8s/overlays/dev/ (will patch namespace, image tag, secret refs)
    - k8s/overlays/prod/ (will patch namespace, image tag, replica count, LLM flag)

tech_stack:
  added: []
  patterns:
    - Kustomize base+overlay pattern with commonLabels
    - K8s 1.29+ native sidecar (initContainers with restartPolicy: Always)
    - Init container sequencing: db-wait → alembic-migrate → spell-rebuild → model-pull → ollama sidecar
    - Model-pull skip-if-cached pattern (ollama list | grep before pull)
    - Belt-and-suspenders graceful shutdown: preStop sleep(10) + terminationGracePeriodSeconds=30

key_files:
  created:
    - k8s/base/kustomization.yaml
    - k8s/base/deployment.yaml
    - k8s/base/service.yaml
    - k8s/base/configmap.yaml
    - k8s/base/pvc.yaml
  modified: []

key_decisions:
  - "Ollama sidecar as native K8s 1.29+ initContainer (restartPolicy: Always) placed last, guarantees Ollama ready before geo-api main container starts"
  - "db-wait init container uses pg_isready from postgresql-client (Phase 19 Dockerfile) — avoids relying on alembic retry logic"
  - "model-pull uses skip-if-cached guard (ollama list | grep qwen2.5:3b) to avoid 2GB download on restarts when PVC already populated (D-07)"
  - "ConfigMap holds only non-secret env vars; DATABASE_URL and DATABASE_URL_SYNC go in Secret (CHANGEME placeholders, per D-06)"
  - "No StorageClass specified in PVC — defaults to local-path, the only StorageClass in k3s cluster"

requirements:
  - DEPLOY-02
  - DEPLOY-03
  - DEPLOY-04
  - DEPLOY-05
  - RESIL-04
---

# Phase 20 Plan 02: Kustomize Base Manifests Summary

Kustomize base directory for geo-api with Ollama native sidecar (K8s 1.29+), 4 sequential init containers, health probe endpoints, preStop graceful shutdown, and non-secret ConfigMap — all building cleanly via `kubectl kustomize k8s/base/`.

## What Was Built

Created `k8s/base/` with 5 YAML manifests that form the shared Kustomize base for both dev and prod overlays:

**kustomization.yaml** — Kustomize resource list referencing all 4 manifests with `app.kubernetes.io/name: geo-api` and `app.kubernetes.io/part-of: civpulse-geo` common labels applied to all resources.

**configmap.yaml** — Non-secret configuration keys: ENVIRONMENT, LOG_LEVEL, OLLAMA_URL (set to `http://localhost:11434` for sidecar pod-local networking), CASCADE_LLM_ENABLED, CASCADE_ENABLED, MAX_BATCH_SIZE, BATCH_CONCURRENCY_LIMIT, and connection pool settings. DATABASE_URL and DATABASE_URL_SYNC intentionally excluded (go in Secret per D-06).

**service.yaml** — ClusterIP Service exposing port 8000, selecting on `app.kubernetes.io/name: geo-api`.

**pvc.yaml** — 10Gi ReadWriteOnce PersistentVolumeClaim for Ollama model persistence, defaulting to local-path StorageClass.

**deployment.yaml** — Full pod spec with:
- `terminationGracePeriodSeconds: 30` (D-11)
- 5 initContainers in strict order:
  1. `db-wait` — polls `pg_isready` against postgresql.civpulse-infra.svc.cluster.local:5432
  2. `alembic-migrate` — runs `alembic upgrade head`
  3. `spell-rebuild` — runs `geo-import rebuild-dictionary`
  4. `model-pull` — starts Ollama, checks `ollama list | grep qwen2.5:3b`, pulls only if missing, kills Ollama
  5. `ollama` — native sidecar (`restartPolicy: Always`, MUST be last per K8s 1.29+ spec)
- geo-api main container with startup + liveness probes on `/health/live`, readiness on `/health/ready`
- preStop exec `sleep 10` for graceful drain (D-11)
- ollama-data PVC mounted by model-pull and ollama sidecar

## Verification Results

```
kubectl kustomize k8s/base/ > /dev/null  # exit 0
kubectl kustomize k8s/base/ | grep "^kind:"  # 4 kinds: ConfigMap, Service, PVC, Deployment
grep "DATABASE_URL" k8s/base/configmap.yaml  # 0 matches (passwords not in ConfigMap)
grep "restartPolicy: Always" k8s/base/deployment.yaml  # 1 match (ollama sidecar)
grep "terminationGracePeriodSeconds: 30" k8s/base/deployment.yaml  # 1 match
grep '"/bin/sleep", "10"' k8s/base/deployment.yaml  # 1 match (preStop)
```

All acceptance criteria confirmed.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | e2cf960 | feat(20-02): add Kustomize base kustomization, configmap, service, and pvc |
| Task 2 | ce9fcc6 | feat(20-02): add Kustomize base deployment.yaml with init containers, sidecar, probes, and preStop |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all manifests are complete and wired. The `geo-api-secret` Secret referenced in envFrom is a placeholder CHANGEME YAML defined in Plan 03 (overlays). This is intentional per D-06 and does not affect kustomize build validity.

## Self-Check

Files created:
- k8s/base/kustomization.yaml — exists
- k8s/base/deployment.yaml — exists
- k8s/base/service.yaml — exists
- k8s/base/configmap.yaml — exists
- k8s/base/pvc.yaml — exists

Commits:
- e2cf960 — exists
- ce9fcc6 — exists
