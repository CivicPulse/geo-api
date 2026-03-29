---
phase: 15-llm-sidecar
plan: 03
subsystem: infra
tags: [ollama, docker-compose, kubernetes, k8s, llm, qwen2.5, argocd]

# Dependency graph
requires:
  - phase: 15-llm-sidecar/15-02
    provides: LLMAddressCorrector and cascade stage 4 integration
provides:
  - Ollama Docker Compose service with auto-pull entrypoint and profile-based opt-in
  - K8s Deployment, PVC, and Service manifests for Ollama on bare-metal K8s (thor)
  - scripts/ollama-entrypoint.sh for idempotent model pre-pull
affects:
  - docker-compose.yml consumers (local dev setup)
  - K8s deployment pipeline (ArgoCD/thor)

# Tech tracking
tech-stack:
  added:
    - ollama/ollama:latest Docker image
    - qwen2.5:3b LLM model (pulled at container start)
  patterns:
    - Docker Compose profiles for optional service activation (profiles: [llm])
    - initContainer pattern for K8s model pre-pull before main container starts
    - Entrypoint script pattern: start server in background, wait for readiness, pull models, wait for PID

key-files:
  created:
    - scripts/ollama-entrypoint.sh
    - k8s/ollama-deployment.yaml
    - k8s/ollama-pvc.yaml
    - k8s/ollama-service.yaml
  modified:
    - docker-compose.yml

key-decisions:
  - "Docker Compose profiles (profiles: [llm]) so ollama only starts when explicitly requested — devs who don't need LLM don't download the 2GB model"
  - "K8s initContainer pulls qwen2.5:3b before main container starts — model is warm on first request"
  - "No CPU limit in K8s or Docker per D-11 — LLM workloads are CPU-bursty, limits cause starvation"
  - "10Gi PVC for model storage — qwen2.5:3b Q4_K_M is ~1.9GB, headroom for future model updates"
  - "mem_limit: 4g in Docker Compose — qwen2.5:3b uses ~2-3GB RAM, provides overhead"

patterns-established:
  - "Ollama Docker entrypoint: start server background, poll /api/tags until ready, pull models from OLLAMA_MODELS env var"
  - "K8s ArgoCD-compatible: plain YAML manifests in k8s/ directory, no Kustomize overlay required"

requirements-completed: [LLM-01, LLM-04]

# Metrics
duration: 8min
completed: 2026-03-29
---

# Phase 15 Plan 03: LLM Sidecar Infrastructure Summary

**Ollama Docker Compose service with profile-gated auto-pull entrypoint and ArgoCD-compatible K8s Deployment/PVC/Service manifests for qwen2.5:3b on bare-metal K8s**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-29T00:00:00Z
- **Completed:** 2026-03-29T00:08:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added ollama service to docker-compose.yml behind `llm` profile — opt-in only, no model download for devs not using LLM
- Created `scripts/ollama-entrypoint.sh` that starts Ollama server, waits for readiness, then idempotently pulls models from `OLLAMA_MODELS` env var
- Created 3 K8s manifests: Deployment with initContainer model pre-pull, 10Gi PVC, ClusterIP Service

## Task Commits

Each task was committed atomically:

1. **Task 1: Docker Compose Ollama service and entrypoint script** - `24fbb69` (feat)
2. **Task 2: K8s manifests for Ollama deployment** - `213ce5d` (feat)

## Files Created/Modified

- `docker-compose.yml` - Added ollama service (profile: llm, mem_limit: 4g, 120s health check), ollama_data volume, CASCADE_LLM_ENABLED and OLLAMA_URL to api env
- `scripts/ollama-entrypoint.sh` - Auto-pull entrypoint: start Ollama in background, wait for /api/tags readiness, pull OLLAMA_MODELS, wait on PID
- `k8s/ollama-deployment.yaml` - Deployment with initContainer pulling qwen2.5:3b, memory limits 4Gi, no CPU limit, readiness/liveness probes
- `k8s/ollama-pvc.yaml` - 10Gi ReadWriteOnce PVC for model storage
- `k8s/ollama-service.yaml` - ClusterIP Service on port 11434

## Decisions Made

- Used Docker Compose `profiles: [llm]` so Ollama only starts when `docker compose --profile llm up` is used — devs without LLM use case avoid the 2GB model download
- K8s uses initContainer pattern to pull qwen2.5:3b before the main Ollama container starts — model is warm when the Deployment becomes Ready
- No CPU limits in either Docker or K8s (D-11) — LLM inference is CPU-bursty; limits cause severe starvation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Minor: Files were initially written to the main repo instead of the git worktree — corrected by writing to the worktree path. No code changes needed.

## Known Stubs

None — all infrastructure manifests are complete and functional.

## Next Phase Readiness

- All infrastructure artifacts in place for LLM sidecar deployment
- Local dev: `docker compose --profile llm up` starts Ollama and pulls qwen2.5:3b on first run
- Production: Apply `k8s/ollama-*.yaml` manifests via ArgoCD to deploy on thor
- Requires: LLM-02 (LLMAddressCorrector) and LLM-03 (cascade stage 4) from plans 15-01 and 15-02

## Self-Check: PASSED

- FOUND: docker-compose.yml (worktree)
- FOUND: scripts/ollama-entrypoint.sh (worktree)
- FOUND: k8s/ollama-deployment.yaml (worktree)
- FOUND: k8s/ollama-pvc.yaml (worktree)
- FOUND: k8s/ollama-service.yaml (worktree)
- FOUND: commits 24fbb69 and 213ce5d in worktree git log

---
*Phase: 15-llm-sidecar*
*Completed: 2026-03-29*
