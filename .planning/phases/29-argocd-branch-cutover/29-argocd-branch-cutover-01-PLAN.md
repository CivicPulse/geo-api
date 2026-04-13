---
phase: 29-argocd-branch-cutover
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/BRANCHING.md
autonomous: true
requirements:
  - GIT-03
must_haves:
  truths:
    - "Repository has a written branching policy at docs/BRANCHING.md"
    - "Policy documents main as deployment source of truth"
    - "Policy documents ArgoCD targetRevision pinning to main"
    - "Policy documents phase-branch naming convention"
  artifacts:
    - path: "docs/BRANCHING.md"
      provides: "Trunk-based branching policy and ArgoCD targetRevision guidance"
      min_lines: 30
      contains: "targetRevision"
  key_links:
    - from: "docs/BRANCHING.md"
      to: "k8s/overlays/{dev,prod}/argocd-app.yaml"
      via: "Documentation reference to targetRevision: main policy"
      pattern: "targetRevision"
---

<objective>
Write docs/BRANCHING.md that codifies the project's trunk-based workflow, ArgoCD targetRevision pinning policy, and phase-branch naming convention.

Purpose: Success Criteria #4 of Phase 29 requires a branching strategy document. This plan produces that document and is independent of any live-cluster work, so it can run first with zero risk.

Output: docs/BRANCHING.md committed to main.
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

<interfaces>
<!-- Relevant ArgoCD Application spec fields the doc must reference -->

From k8s/overlays/dev/argocd-app.yaml:
```yaml
spec:
  source:
    repoURL: https://github.com/CivicPulse/geo-api.git
    targetRevision: main
    path: k8s/overlays/dev
```

From k8s/overlays/prod/argocd-app.yaml:
```yaml
spec:
  source:
    repoURL: https://github.com/CivicPulse/geo-api.git
    targetRevision: main
    path: k8s/overlays/prod
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Author docs/BRANCHING.md</name>
  <files>docs/BRANCHING.md</files>
  <action>
Create a new file docs/BRANCHING.md documenting the repository's branching strategy. Keep concise (~40-80 lines). Structure with these H2 sections:

1. "## Trunk-Based Development"
   - `main` is the single long-lived branch and the deployment source of truth.
   - No long-lived develop/release branches.
   - All work happens on short-lived branches that merge back to `main` via PR.

2. "## Phase Branch Convention"
   - Per GSD workflow (per D-01 style trunk model from 29-CONTEXT.md), each phase uses a branch named `phase-{NN}-{slug}` (e.g., `phase-29-argocd-branch-cutover`).
   - Phase branches are deleted after merge to `main`.
   - Before starting a new phase, the previous phase branch must be merged to `main`.

3. "## ArgoCD targetRevision Policy"
   - All committed ArgoCD Application manifests (`k8s/overlays/{env}/argocd-app.yaml`) MUST pin `spec.source.targetRevision: main`.
   - Temporary pinning to a phase branch is permitted ONLY as an in-cluster live-edit during active deploy debugging, and MUST be reverted to `main` before the phase branch is merged/deleted.
   - Rationale: the two Applications are not managed by a parent App-of-Apps, so live edits do not self-heal. Reference Phase 29 for the precedent.

4. "## PR Workflow"
   - Open PR from phase/feature branch to `main`.
   - Use Conventional Commits for PR titles.
   - Squash-or-merge per maintainer preference; delete remote branch after merge.

Do NOT include: parent App-of-Apps design, pre-commit guards, or other deferred ideas from 29-CONTEXT.md deferred section.

Reference GIT-03 requirement wording from .planning/REQUIREMENTS.md to ensure acceptance criteria are met.
  </action>
  <verify>
    <automated>test -f docs/BRANCHING.md && grep -q "targetRevision" docs/BRANCHING.md && grep -q "main" docs/BRANCHING.md && grep -qi "trunk" docs/BRANCHING.md && grep -qi "phase" docs/BRANCHING.md && [ "$(wc -l < docs/BRANCHING.md)" -ge 30 ]</automated>
  </verify>
  <done>
docs/BRANCHING.md exists, is at least 30 lines, and contains sections covering trunk-based development, phase branch convention, ArgoCD targetRevision policy pinned to main, and PR workflow.
  </done>
</task>

</tasks>

<verification>
- File docs/BRANCHING.md exists on disk
- Grep confirms keywords: targetRevision, main, trunk, phase
- Line count >= 30
- Content addresses all four required sections
</verification>

<success_criteria>
- [x] docs/BRANCHING.md created and committed
- [x] Document covers trunk-based development + ArgoCD targetRevision policy + phase branches + PR workflow
- [x] Satisfies GIT-03 acceptance criteria (branching strategy documented)
- [x] No references to deferred items (App-of-Apps, CI guards)
</success_criteria>

<output>
After completion, create `.planning/phases/29-argocd-branch-cutover/29-argocd-branch-cutover-01-SUMMARY.md`
</output>
