---
id: SEED-002
status: dormant
planted: 2026-04-13
planted_during: v1.5 Prod/Dev Bootstrap & K8s Jobs (first-run bootstrap on thor)
trigger_when: next touch of k8s/osm/base/tile-server.yaml or k8s/osm/base/jobs/tile-import-job.yaml
scope: small
---

# SEED-002: Tile-server Deployment must wait for tile-import-job completion

## Why This Matters

During v1.5 first-run bootstrap on 2026-04-13, the `tile-server` Deployment had been running (crash-looping) for 8 days while its PVC was empty. The moment the ZFS dataset became writable (after the `hatch1/geo` rename + `chmod 777`), the tile-server container's entrypoint succeeded in initializing an **empty** PostgreSQL schema, writing `/data/database/postgres/PG_VERSION` before inevitably crashing on the missing OSM data.

Then when `tile-import-job` ran, its idempotency guard `[ -f /data/database/postgres/PG_VERSION ]` saw the file and logged `"tile-server data already imported (postgres dir present), skipping"` — a complete lie. The Job exited 0 in 63 seconds without importing a single byte.

Recovery required a full manual dance:
1. Scale `tile-server` Deployment to 0
2. Run a one-shot busybox pod to `rm -rf /data/database/*` on the PVC
3. Delete the failed `tile-import-job`
4. Re-apply `tile-import-job` with the empty directory
5. Scale `tile-server` back to 1 after import completed

Proper fix: the Deployment must not run before the Job is complete. Options:
- **Option A — Init container.** Add an initContainer to the tile-server Deployment that blocks until a stronger "import really done" marker exists — e.g., `/data/database/planet-import-complete` (the file tile-import-job touches on successful exit) or a specific row count in the osm_point table.
- **Option B — Readiness probe.** Add a readiness probe that checks for `planet-import-complete` existence before reporting Ready; combined with `maxUnavailable: 0`, the Deployment never takes traffic until imports land.
- **Option C — Strengthen the Job's idempotency guard.** Check for the `planet-import-complete` marker instead of just `PG_VERSION`. This protects the Job but doesn't stop the Deployment from running prematurely — it just stops the Deployment's half-initialized state from defeating the Job. Worth combining with A or B.

Also consider: the tile-import-job's postgres dir initialization is destructive — it assumes a fresh directory. If the Deployment keeps writing partial state, we'll see this bug again on any cluster rebuild.

## When to Surface

**Trigger:** Any touch of `k8s/osm/base/tile-server.yaml`, `k8s/osm/base/jobs/tile-import-job.yaml`, or any milestone doing OSM refresh / tile regeneration work.

This seed should be presented during `/gsd-new-milestone` when the milestone scope matches any of:
- OSM stack refactors or refreshes
- Tile-server feature work or caching changes
- Operator-UX improvements around bootstrap
- Cluster rebuild automation / disaster recovery procedures

## Scope Estimate

**Small** — a few hours. One initContainer addition OR one readiness probe OR one guard change. Testing scope is modest: spin up from empty dataset, verify correct sequencing.

## Breadcrumbs

- `k8s/osm/base/tile-server.yaml` — the Deployment that wrote the premature PG_VERSION
- `k8s/osm/base/jobs/tile-import-job.yaml` — the Job with weak idempotency guard
- `k8s/osm/base/jobs/README.md` — idempotency table, §"Re-running After Data Corruption"
- The overv/openstreetmap-tile-server:2.3.0 image touches `/data/database/planet-import-complete` on successful import exit — that's the marker to check for

## Notes

Related to SEED-001 (valhalla build vs deploy race). Consider a unified "Deployment-waits-for-Job" pattern across all three OSM workloads: tile-server, nominatim (which has its own in-container import lifecycle), and valhalla.

Observed recovery time: ~5 min once the problem was diagnosed. Debugging time before diagnosis was significant because the spurious "skipping" log line misled the operator.
