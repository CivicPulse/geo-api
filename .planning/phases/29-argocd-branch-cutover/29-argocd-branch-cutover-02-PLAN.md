---
phase: 29-argocd-branch-cutover
plan: 02
type: execute
wave: 1
depends_on: []
files_modified: []
autonomous: false
mutation: true
requirements:
  - GIT-01
  - GIT-02
must_haves:
  truths:
    - "Live geo-api-dev Application in argocd namespace has spec.source.targetRevision = main"
    - "Live geo-api-prod Application in argocd namespace has spec.source.targetRevision = main"
    - "Both Applications report Sync Status = Synced and Health Status = Healthy after cutover"
    - "Remote branch phase-23-deploy-fix no longer exists on origin after verified healthy cutover"
  artifacts:
    - path: "k8s/overlays/dev/argocd-app.yaml"
      provides: "Declarative source for geo-api-dev Application (already committed with targetRevision: main)"
    - path: "k8s/overlays/prod/argocd-app.yaml"
      provides: "Declarative source for geo-api-prod Application (already committed with targetRevision: main)"
  key_links:
    - from: "k8s/overlays/dev/argocd-app.yaml"
      to: "live Application geo-api-dev in argocd namespace"
      via: "kubectl apply -f"
      pattern: "targetRevision: main"
    - from: "k8s/overlays/prod/argocd-app.yaml"
      to: "live Application geo-api-prod in argocd namespace"
      via: "kubectl apply -f"
      pattern: "targetRevision: main"
---

<objective>
Reconcile live ArgoCD Application state with already-committed git state: apply argocd-app.yaml for dev, verify sync/health, then apply for prod, verify sync/health. After both are Synced + Healthy, delete the deprecated `phase-23-deploy-fix` remote branch.

**MUTATION PLAN — USER CONFIRMATION REQUIRED BEFORE EACH CLUSTER/REMOTE MUTATION.**

Purpose: Close Success Criteria #1, #2, #3 of Phase 29 (GIT-01, GIT-02). The committed manifests already show `targetRevision: main` — this plan pushes that state into the live cluster (which still has `phase-23-deploy-fix` from a manual Phase 23 edit) and cleans up the obsolete remote branch.

Output: Live cluster state matches git; deprecated remote branch deleted.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/29-argocd-branch-cutover/29-CONTEXT.md
@k8s/overlays/dev/argocd-app.yaml
@k8s/overlays/prod/argocd-app.yaml
</context>

<mutation_warning>
This plan performs LIVE CLUSTER MUTATIONS and a REMOTE BRANCH DELETION. Per standing user preference for v1.5, pause for explicit user confirmation before EACH of the following commands:
  1. `kubectl apply -f k8s/overlays/dev/argocd-app.yaml`
  2. `kubectl apply -f k8s/overlays/prod/argocd-app.yaml`
  3. `git push origin --delete phase-23-deploy-fix`

Do NOT batch confirmations. Do NOT proceed without explicit "yes" / "approved" from user at each checkpoint.
</mutation_warning>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: Confirm pre-cutover live state (dev + prod)</name>
  <what-built>
Baseline snapshot of current live ArgoCD Application targetRevision before mutation.
  </what-built>
  <how-to-verify>
Run these read-only commands and review output together with the user:

```bash
kubectl get application geo-api-dev -n argocd -o jsonpath='{.spec.source.targetRevision}' && echo
kubectl get application geo-api-prod -n argocd -o jsonpath='{.spec.source.targetRevision}' && echo
kubectl get application geo-api-dev -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}' && echo
kubectl get application geo-api-prod -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}' && echo
```

Expected (the drift being reconciled): dev and prod targetRevision likely show `phase-23-deploy-fix`. Document actual values shown.
  </how-to-verify>
  <resume-signal>User types "approved" to proceed with dev cutover, or describes blockers</resume-signal>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Apply dev argocd-app.yaml and verify dev Synced+Healthy</name>
  <what-built>
Live geo-api-dev Application reconciled to targetRevision=main from committed manifest.
  </what-built>
  <how-to-verify>
PAUSE for user confirmation, then run:

```bash
kubectl apply -f k8s/overlays/dev/argocd-app.yaml
```

Then verify (wait up to ~60s for ArgoCD to reconcile):

```bash
# Must return exactly: main
kubectl get application geo-api-dev -n argocd -o jsonpath='{.spec.source.targetRevision}' && echo

# Poll until Synced/Healthy (retry a few times over ~60s)
kubectl get application geo-api-dev -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}' && echo
```

Optional: force a refresh if reconcile hasn't fired:
```bash
kubectl patch application geo-api-dev -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"normal"}}}'
```

Expected final state: targetRevision=main, sync=Synced, health=Healthy.

DO NOT PROCEED to prod until dev is verified Synced + Healthy.
  </how-to-verify>
  <resume-signal>User types "approved" once dev is Synced+Healthy on main, or describes failure</resume-signal>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Apply prod argocd-app.yaml and verify prod Synced+Healthy</name>
  <what-built>
Live geo-api-prod Application reconciled to targetRevision=main from committed manifest.
  </what-built>
  <how-to-verify>
PAUSE for user confirmation (dev must already be Synced+Healthy from Task 2), then run:

```bash
kubectl apply -f k8s/overlays/prod/argocd-app.yaml
```

Then verify (wait up to ~60s for ArgoCD to reconcile):

```bash
# Must return exactly: main
kubectl get application geo-api-prod -n argocd -o jsonpath='{.spec.source.targetRevision}' && echo

# Poll until Synced/Healthy
kubectl get application geo-api-prod -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}' && echo
```

Optional refresh:
```bash
kubectl patch application geo-api-prod -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"normal"}}}'
```

Expected final state: targetRevision=main, sync=Synced, health=Healthy.
  </how-to-verify>
  <resume-signal>User types "approved" once prod is Synced+Healthy on main, or describes failure</resume-signal>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Delete deprecated phase-23-deploy-fix remote branch</name>
  <what-built>
Remote branch phase-23-deploy-fix removed from origin after both Applications are verified healthy on main.
  </what-built>
  <how-to-verify>
PAUSE for user confirmation (BOTH dev and prod must be Synced+Healthy on main from Tasks 2 & 3), then run:

```bash
# Confirm branch currently exists on origin
git ls-remote --heads origin phase-23-deploy-fix

# Delete it
git push origin --delete phase-23-deploy-fix

# Confirm deletion (should return empty)
git ls-remote --heads origin phase-23-deploy-fix
```

Also move the related todo to closed:

```bash
mkdir -p .planning/todos/closed
mv .planning/todos/pending/2026-04-03-reset-argocd-targetrevision-to-main-after-merge.md .planning/todos/closed/ 2>/dev/null || echo "todo file not found - skip"
```

Expected final state: `git ls-remote --heads origin phase-23-deploy-fix` returns empty; related todo closed if it existed.
  </how-to-verify>
  <resume-signal>User types "approved" once branch is deleted and both apps remain Synced+Healthy</resume-signal>
</task>

</tasks>

<verification>
Final state checks (run all four, all must pass):

```bash
# targetRevision checks — must both print "main"
kubectl get application geo-api-dev  -n argocd -o jsonpath='{.spec.source.targetRevision}'
kubectl get application geo-api-prod -n argocd -o jsonpath='{.spec.source.targetRevision}'

# sync/health checks — must both print "Synced/Healthy"
kubectl get application geo-api-dev  -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}'
kubectl get application geo-api-prod -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}'

# remote branch deletion — must return empty
git ls-remote --heads origin phase-23-deploy-fix
```
</verification>

<success_criteria>
- [x] geo-api-dev targetRevision = main (GIT-01)
- [x] geo-api-prod targetRevision = main (GIT-02)
- [x] Both apps Synced + Healthy after cutover
- [x] phase-23-deploy-fix deleted from origin
- [x] Related pending todo closed
- [x] No prod changes made before dev verified
</success_criteria>

<output>
After completion, create `.planning/phases/29-argocd-branch-cutover/29-argocd-branch-cutover-02-SUMMARY.md` capturing: pre-cutover targetRevision values observed, post-cutover verification output, and confirmation of branch deletion.
</output>
