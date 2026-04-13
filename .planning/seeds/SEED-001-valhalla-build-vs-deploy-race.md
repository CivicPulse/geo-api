---
id: SEED-001
status: dormant
planted: 2026-04-13
planted_during: v1.5 Prod/Dev Bootstrap & K8s Jobs (first-run bootstrap on thor)
trigger_when: next touch of k8s/osm/base/valhalla.yaml or k8s/osm/base/jobs/, or next milestone shipping OSM stack changes
scope: medium
---

# SEED-001: Disentangle valhalla build-job from valhalla Deployment

## Why This Matters

During v1.5 first-run bootstrap on 2026-04-13, both the `valhalla-build-job` and the `valhalla` Deployment tried to build the graph tiles from PBF. This caused two concrete problems:

1. **Spurious idempotency-check skips on valhalla-build-job.** The Job's guard was `[ -d /custom_files/valhalla_tiles ] && [ -n "$(ls -A …)" ]`. Crash-looping Deployment pods (from the old wrong-image era) had created the directory without populating it; the Job saw a non-empty path and skipped every run. Had to strengthen to `[ -f /custom_files/valhalla_tiles.tar ]` in commit 1e580b0.
2. **Wasted cycles from the self-builder race.** When the Job spuriously skipped, the Deployment's gis-ops entrypoint (`use_tiles_ignore_pbf=True` but no usable tiles) did its own 40-thread build in-pod, hitting OOM risk because the Deployment's memory limits were set for serving, not building (had to bump to 16Gi in commit b99b534).

Net effect: a confusing operator experience where a "Job complete (2m)" log line was a lie, and the Deployment ended up doing the real work under tighter resource limits than the dedicated Job.

Proper fix: one actor, one role. Either:
- **Option A — Delete valhalla-build-job entirely.** Let the Deployment be the single actor with `build_tiles` CMD and `serve_tiles=True`. Simpler manifest surface, but the Deployment must always carry build-scale memory limits (16Gi) even during steady-state serving.
- **Option B — Keep the Job, gate the Deployment.** Add a readiness probe to the Deployment that only passes once `/custom_files/valhalla_tiles.tar` exists and is non-empty. Alternatively, use an init container that blocks until the tar is present. Cleaner separation but more moving parts.

Option B is the better long-term story because it lets the Deployment run with right-sized serving limits (2–4 Gi memory) after the Job completes the heavy build.

## When to Surface

**Trigger:** Any touch of `k8s/osm/base/valhalla.yaml` or `k8s/osm/base/jobs/valhalla-build-job.yaml`, or any milestone whose scope includes OSM stack changes, routing feature work, or graph refresh automation.

This seed should be presented during `/gsd-new-milestone` when the milestone scope matches any of:
- OSM stack refactors or upgrades
- Routing / Valhalla feature work
- Operator-UX improvements around the bootstrap runbook
- Any graph rebuild automation (scheduled refresh from newer PBFs)

## Scope Estimate

**Medium** — a phase or two. Manifest changes are small but need coordinated testing: build-then-serve ordering, readiness probe behavior, verification that a cluster rebuild still converges cleanly from empty PVCs.

## Breadcrumbs

- `k8s/osm/base/valhalla.yaml` — Deployment with `serve_tiles=True`, `use_tiles_ignore_pbf=True`, `server_threads=8`, memory req 4Gi/lim 16Gi
- `k8s/osm/base/jobs/valhalla-build-job.yaml` — Job with `build_tiles` CMD, idempotency guard on `valhalla_tiles.tar`, `force_rebuild=False`
- `k8s/osm/base/jobs/README.md` — idempotency table (already documents the weakness)
- Commits: `1e580b0` (idempotency guard fix), `b99b534` (deploy memory bump), `e131461` (server_threads cap)

## Notes

Observed runtime for Georgia graph build: ~16 min wall clock with 40 threads (the build-job run), ~16 min estimated for the Deployment's self-build before it was preempted.

Related: the tile-server Deployment has a similar class of issue (see SEED-002). Worth considering a unified design pattern for "Deployment that depends on a one-shot import/build Job completing first" across the OSM stack.
