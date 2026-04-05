---
status: gaps_found
phase: 29-argocd-branch-cutover
verified: 2026-04-05
must_haves_verified: 1/4
blocker: scope_collision_with_phase_28_29_31_boundaries
---

# Phase 29 Verification — BLOCKED, scope rework required

## Summary

Phase 29's scope (branch cutover from `phase-23-deploy-fix` to `main`) cannot achieve success criterion #3 (Sync=Synced **AND** Health=Healthy) under its current definition. Dev cutover was attempted, failed to reach Healthy, and has been reverted.

## What was verified

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `geo-api-dev` targetRevision = main | ⚠ Achievable but reverted |
| 2 | `geo-api-prod` targetRevision = main | Not attempted (dev blocker first) |
| 3 | Both apps Synced AND Healthy after cutover | ❌ Cannot achieve under current scope |
| 4 | Branching strategy documented in docs/BRANCHING.md | ✅ Complete (Plan 01) |

## Root cause

When dev's `targetRevision` was patched to `main` and origin/main was pushed (211-commit catch-up, user-approved), ArgoCD reconciled and began deploying v1.4's OSM sidecars (`nominatim`, `tile-server`, `valhalla`) that Phase 28 added to `k8s/base/`. These sidecars immediately entered `CrashLoopBackOff` because:

- `nominatim` auto-imports at startup and requires the Georgia PBF file, which is absent — Phase 32's bootstrap Jobs are supposed to stage it.
- `valhalla` needs pre-built routing tiles, also absent.
- These sidecars belong in the `civpulse-gis` namespace per Phase 31's goal, not in `civpulse-dev`.

The `geo-api` pod itself remained `Running 2/2` throughout — the blocker is strictly the new sidecars in `k8s/base/`.

## Actions taken

1. **Pushed local main → origin/main** (211 commits: all of v1.3 and v1.4). This was a user-approved deviation from standing "don't push" instruction. `origin/main` now at `7246745`.
2. **Applied `k8s/overlays/dev/argocd-app.yaml`** to live cluster — targetRevision became `main`, ArgoCD synced manifests, sidecars crashed.
3. **Reverted** — patched live dev Application back to `targetRevision: phase-23-deploy-fix`, forced refresh. Dev is now back to `Synced/Healthy` with sidecars pruned. No lasting cluster damage; `geo-api` pod untouched throughout.
4. **Prod not touched** — dev blocker caught first.

## Current cluster state

- `geo-api-dev`: targetRevision=phase-23-deploy-fix, Synced/Healthy ✅ (same as pre-Phase-29)
- `geo-api-prod`: targetRevision=phase-23-deploy-fix, Synced/Healthy ✅ (untouched)
- `origin/main`: now current with local main (211 commits pushed)
- `origin/phase-23-deploy-fix`: still exists (not deleted)
- `docs/BRANCHING.md`: committed to main ✅

## Scope rework options

The ROADMAP ordering (29: cutover → 30: ZFS → 31: move to civpulse-gis → 32: bootstrap) has a latent dependency: **Phase 29 assumes `main`'s `k8s/base/` is deployable, but Phase 28 put un-bootstrappable sidecars there.** Options to resolve:

**Option A — Reorder phases:** Execute 31 before 29. Phase 31 moves OSM sidecars out of `k8s/base/` into `k8s/osm/base/` + `civpulse-gis` namespace + new `osm-stack` ArgoCD Application. Once `k8s/base/` no longer contains broken sidecars, Phase 29's cutover becomes a clean no-op-then-branch-flip. **Cleanest from a narrative standpoint.** Renumber to 29→31, 30→29, 31→30 OR just execute out-of-order and note the deviation.

**Option B — Expand Phase 29's scope:** Pull the "remove sidecars from k8s/base/" step forward into Phase 29. Phase 29 becomes: (a) remove OSM sidecars from k8s/base/kustomization.yaml + delete their YAML files + remove OSM PVCs, (b) cutover live apps to main, (c) docs, (d) delete deprecated branch. Phase 31 then only adds the NEW location (`k8s/osm/base/`, civpulse-gis namespace, new ArgoCD Application). **Keeps phase numbers stable, expands Phase 29.**

**Option C — Skip cutover step in Phase 29 entirely:** Reduce Phase 29 to just Plan 01 (docs). Defer the actual cutover to a new phase 31.5 or 34.5 after Phase 31 ships. **Simplest, but leaves branch drift unresolved longest.**

## Recommendation

**Option A (reorder)** — execute Phase 31 first, then Phase 29. Phase 31's goal already includes moving sidecars out of `k8s/base/`, so it naturally resolves the blocker. Renumber is not required; just execute in logical order and note in ROADMAP.

Phase 30 (ZFS storage) also belongs before Phase 31 since Phase 31's PVCs will want to bind to ZFS PVs. Revised execution order:

1. **Phase 30** — ZFS-Backed Storage Infrastructure (storage foundation)
2. **Phase 31** — OSM Stack in civpulse-gis Namespace (moves sidecars out of `k8s/base/`, creates new ArgoCD Application)
3. **Phase 29** — ArgoCD Branch Cutover (now clean — `k8s/base/` has only geo-api, main is safe to sync)
4. **Phase 32** — Bootstrap Jobs
5. **Phase 33** — Cross-Namespace wiring
6. **Phase 34** — Runbook + DR + E2E

## Next action

Awaiting user decision on scope rework. `/gsd:autonomous` paused after Plan 01 success and Plan 02 revert.

## Requirements status

- GIT-01: **deferred** (dev targetRevision cannot stay on main until Phase 31 completes)
- GIT-02: **deferred** (branch deletion blocked until live apps cut over cleanly)
- GIT-03: **complete** ✅ (docs/BRANCHING.md authored & committed)
