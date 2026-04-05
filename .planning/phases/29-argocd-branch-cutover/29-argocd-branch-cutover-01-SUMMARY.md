---
phase: 29-argocd-branch-cutover
plan: 01
status: complete
completed: 2026-04-04
requirements:
  - GIT-03
files_modified:
  - docs/BRANCHING.md
---

# Plan 01 Summary: Author docs/BRANCHING.md

## What was built

A new `docs/BRANCHING.md` (54 lines) codifying:

1. **Trunk-Based Development** — `main` as the single long-lived branch and deployment source of truth.
2. **Phase Branch Convention** — `phase-{NN}-{slug}` naming, deleted after merge.
3. **ArgoCD `targetRevision` Policy** — all committed manifests MUST pin `targetRevision: main`. Phase-branch pinning is permitted only as a temporary live-edit during deploy debugging, must be reverted before phase-branch deletion.
4. **PR Workflow** — Conventional Commits, CI-green requirement, delete remote after merge.

## Rationale captured

Documented that the two `geo-api` ArgoCD Applications are not managed by a parent App-of-Apps, so live edits to `targetRevision` do not self-heal. This is the precise drift scenario that Phase 29 was created to reconcile.

## Verification

```
test -f docs/BRANCHING.md && grep -q "targetRevision" docs/BRANCHING.md \
  && grep -q "main" docs/BRANCHING.md && grep -qi "trunk" docs/BRANCHING.md \
  && grep -qi "phase" docs/BRANCHING.md && [ $(wc -l < docs/BRANCHING.md) -ge 30 ]
→ VERIFY PASS — 54 lines
```

## Deferred (out of scope)

- Parent App-of-Apps declarative management of the two geo-api Applications
- CI guard preventing commit of non-`main` `targetRevision`

Both remain candidates for a future v1.6+ hardening item per 29-CONTEXT.md.

## Requirements satisfied

- GIT-03 ✅ Branching strategy documented (trunk-based from main, feature branches, no long-lived deploy branches)
