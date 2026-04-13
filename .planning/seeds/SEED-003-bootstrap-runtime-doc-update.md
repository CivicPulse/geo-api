---
id: SEED-003
status: dormant
planted: 2026-04-13
planted_during: v1.5 Prod/Dev Bootstrap & K8s Jobs (first-run bootstrap on thor)
trigger_when: next docs pass or any change to docs/BOOTSTRAP.md / docs/DR.md / docs/ZFS-STORAGE.md
scope: small
---

# SEED-003: Correct docs/BOOTSTRAP.md runtime estimates based on real first-run data

## Why This Matters

`docs/BOOTSTRAP.md` quotes **"Total wall-clock time (first bootstrap, serial): ~3.5 hours"** and per-job runtimes of nominatim ~90min, tile-import ~90min, valhalla ~30min.

Actual first-run on thor (2026-04-13) for the Georgia region:

| Workload | Estimated | Actual |
|---|---|---|
| pbf-download-job | ~5 min | **23 seconds** |
| tile-import-job | ~90 min | **25 minutes** |
| valhalla-build-job | ~30 min | **~16 minutes** |
| nominatim auto-import | ~90 min | **~55 minutes** |
| **total wall clock** | **~3.5h** | **~76 minutes** (concurrent) |

The 3.5h estimate is 2.75× the actual duration, which materially changes operator planning. An operator who thinks they need 3.5h of babysitting may defer the bootstrap to a weekend; the real 76-min number fits a single meeting-free afternoon slot.

Also: the tile-import-job `activeDeadlineSeconds` was bumped to 10800 (3h) in commit e165eb5 for safety headroom. With actual runtime at 25 min, that's 7.2× headroom — significantly overcommitted. Worth tightening to something like 5400 (90 min) once we have a few more runs to confirm.

## When to Surface

**Trigger:** Next docs pass, next bootstrap run by a different operator, or any change to `docs/BOOTSTRAP.md` / `docs/DR.md` / `docs/ZFS-STORAGE.md`.

This seed should be presented during `/gsd-new-milestone` when the milestone scope matches any of:
- Documentation / operator-UX work
- Another bootstrap run (different region, cluster rebuild, DR exercise)
- Any change that re-validates the runtime table

## Scope Estimate

**Small** — a few minutes of doc edits, one commit. The numbers are already known and documented in this seed.

## Breadcrumbs

- `docs/BOOTSTRAP.md` — runtime table in §"Step 5: Wait for imports" (currently "Serial total: ~3.5h. Concurrent total: ~1h40m")
- `docs/ZFS-STORAGE.md` — no runtime claims, OK
- `docs/DR.md` — "Expected cost: pbf ~5 min, nominatim ~90 min, tile-server ~90 min, valhalla ~30 min" in §6; same numbers to correct
- `k8s/osm/base/jobs/README.md` — "Expected Runtimes" table; same update
- `k8s/osm/base/jobs/tile-import-job.yaml` — `activeDeadlineSeconds: 10800` (tighten candidate)
- Commit `e165eb5` bumped the tile-import deadline pessimistically; commit log from 2026-04-13 bootstrap has real timings

## Notes

Caveat: these numbers are from **one region** (Georgia) on **one machine** (thor). A much larger region (California, Texas, nationwide) would push tile-import back into the 90+ minute range. The doc should either:
(a) Quote region-specific numbers ("Georgia: ~25 min, full US: ~X hours") or
(b) Use a per-PBF-MB rate as a scaling heuristic and let operators estimate from their region's file size.

The Georgia PBF was ~334 MB. Rates observed:
- tile-import: ~13 MB/min osm2pgsql ingest
- valhalla: ~21 MB/min graph build
- nominatim: ~6 MB/min import+index
