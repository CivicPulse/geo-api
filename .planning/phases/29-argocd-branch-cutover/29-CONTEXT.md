# Phase 29: ArgoCD Branch Cutover - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Switch `geo-api-dev` and `geo-api-prod` ArgoCD Applications from `phase-23-deploy-fix` to `main`, and document the project's branching strategy. Delete the deprecated branch after cutover.

**Important discovery during scout:** The committed `k8s/overlays/{dev,prod}/argocd-app.yaml` manifests already show `targetRevision: main`. The drift is in the *live* cluster — the ArgoCD Applications themselves are NOT managed by a parent App-of-Apps, so manual live edits (done during Phase 23 deploy fixes) do not self-heal from git. This phase reconciles live state with already-committed git state.

</domain>

<decisions>
## Implementation Decisions

### Apply Strategy
- Apply method: `kubectl apply -f k8s/overlays/{dev,prod}/argocd-app.yaml` — declarative GitOps-style reconciliation
- Verify via `kubectl get application geo-api-{dev,prod} -n argocd -o jsonpath='{.spec.source.targetRevision}'` → should return `main`
- After apply, wait for ArgoCD Sync Status = Synced and Health Status = Healthy

### Branch Lifecycle
- Delete `phase-23-deploy-fix` remote branch after cutover is verified healthy (both dev + prod synced, not just dev)
- Rationale: throwaway branch from v1.3 deployment-fix work; v1.4 already shipped on main, nothing to preserve

### Branching Model
- Document trunk-based development with short-lived feature branches off `main`
- Matches the GSD phase workflow (phase branches merge to main before next phase starts)
- Matches current repo behavior (no long-lived develop/release branches exist)

### Documentation
- Create new `docs/BRANCHING.md` (explicit success criteria suggests this path)
- Cover: main = deployment source of truth, ArgoCD targetRevision policy, phase branch convention, PR workflow

### Claude's Discretion
- Exact wording/length of BRANCHING.md — keep concise, reference ArgoCD pinning policy
- Order of operations (update prod first or dev first) — dev-first is safer and conventional
- Whether to add a small note to README.md pointing at BRANCHING.md

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `k8s/overlays/dev/argocd-app.yaml` and `k8s/overlays/prod/argocd-app.yaml` — already committed with `targetRevision: main`, just need live reconciliation
- Both apps use `selfHeal: true` + `prune: true` — once live target matches git, selfHeal keeps them aligned
- `destination.namespace` already `civpulse-dev` / `civpulse-prod` respectively

### Established Patterns
- ArgoCD Applications live in `k8s/overlays/{env}/argocd-app.yaml` alongside overlay kustomization
- Each Application targets its own namespace (`civpulse-dev`, `civpulse-prod`)
- `CreateNamespace=false` syncOption — namespaces must pre-exist (bootstrap responsibility)

### Integration Points
- Live cluster ArgoCD in `argocd` namespace (node `thor` — v1.5 milestone context)
- No parent App-of-Apps manages these two Applications — they're installed directly into argocd namespace
- `docs/` directory exists with `geocoding-data-research.md`, `OBSERVABILITY-REPORT.md` — add BRANCHING.md alongside

</code_context>

<specifics>
## Specific Ideas

- There is already a pending todo: "Reset ArgoCD targetRevision to main after merge" (.planning/todos/pending/2026-04-03-...) — this phase closes that todo
- Dev-first cutover order for safety: apply dev, verify healthy, then apply prod

</specifics>

<deferred>
## Deferred Ideas

- Parent App-of-Apps to manage the two ArgoCD Applications themselves declaratively — would prevent future manual-edit drift. Not in scope for v1.5; could be a v1.6+ hardening item.
- Automated guard (pre-commit or CI) that rejects non-`main` `targetRevision` in committed manifests — also out of scope.

</deferred>
