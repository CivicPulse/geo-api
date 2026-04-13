# Disaster Recovery — ZFS Snapshot & Rollback

Operator runbook for recovering the OSM stack data from ZFS snapshots on node `thor` after corruption, failed import, or accidental wipe.

**Storage layer reference:** `docs/ZFS-STORAGE.md` — dataset layout, PV/PVC binding model, Retain semantics.
**Bootstrap reference:** `docs/BOOTSTRAP.md` — for re-bringing up a dataset from scratch when no snapshot is available.

> ## ⚠ HONEST NOTE — Procedure Not Yet Exercised
>
> **As of milestone v1.5 close (2026-04-04), this rollback procedure has NOT been exercised against a live ZFS dataset.**
>
> Milestone v1.5 success criterion **DOC-02** required that the rollback procedure "be run through at least once on a non-critical dataset." That exercise is **DEFERRED** to milestone v1.6 or to the first production incident that forces it.
>
> This document records the **intended procedure** based on ZFS semantics and the storage layer documented in `docs/ZFS-STORAGE.md`. First real-world exercise is an **accepted known gap** and should be treated as such: expect to encounter edge cases on first execution.
>
> **Action item for v1.6:** take a snapshot on the `pbf` dataset (lowest-risk — source data is re-downloadable), execute a rollback against a scratch file change, remove this note, and log the exercise outcome in a SUMMARY doc.

---

## 1. Snapshot Strategy

ZFS snapshots are copy-on-write and effectively free to take. Cadence is calibrated to rebuild cost:

| Dataset | Cadence | Rationale |
|---------|---------|-----------|
| `hatch1/geo/nominatim` | **daily** | Heavy writes during imports; ~90 min rebuild cost |
| `hatch1/geo/tile-server` | **weekly** | Moderate change; ~90 min rebuild cost |
| `hatch1/geo/valhalla` | **weekly** | Moderate change; ~30 min rebuild cost |
| `hatch1/geo/pbf` | **none** | Re-downloadable from Geofabrik (~5 min) |

Cadence is the same as `docs/ZFS-STORAGE.md` §4. Automate via cron on `thor` when ops capacity allows.

## 2. Take a Snapshot

Name snapshots with ISO dates so `zfs list -t snapshot` output is sortable.

```bash
# Single dataset
zfs snapshot hatch1/geo/<dataset>@$(date +%Y-%m-%d)

# All four, same timestamp
TS=$(date +%Y-%m-%d)
for ds in pbf nominatim tile-server valhalla; do
  zfs snapshot hatch1/geo/$ds@$TS
done
```

## 3. List Snapshots

```bash
zfs list -t snapshot -r hatch1/geo
```

Expected output: sorted list of `<dataset>@<date>` entries with USED / REFER columns. Identify the target snapshot to roll back to.

## 4. Rollback Procedure

**`zfs rollback` is destructive.** It discards every change made to the dataset since the target snapshot, and destroys any snapshots taken *after* the target. There is no undo.

### Step 4a — Scale consumer(s) to 0

The PV mount must not be in use during rollback. Identify which Deployment(s) consume the dataset (see table below) and scale to 0.

| Dataset | Consumer Deployment |
|---------|---------------------|
| `hatch1/geo/pbf` | `nominatim` (mounts PBF at `/nominatim/pbf/`); also mounted by `pbf-download-job`, `tile-import-job`, `valhalla-build-job` when running |
| `hatch1/geo/nominatim` | `nominatim` |
| `hatch1/geo/tile-server` | `tile-server` |
| `hatch1/geo/valhalla` | `valhalla` |

```bash
# Example: rolling back the nominatim dataset
kubectl -n civpulse-gis scale deployment nominatim --replicas=0

# Confirm pod terminated
kubectl -n civpulse-gis get pods -l app=nominatim
# Expected: no pods, or pods in Terminating
```

### Step 4b — Roll back the dataset

Run as `root` on `thor`:

```bash
zfs rollback hatch1/geo/<dataset>@<snapshot-name>
```

**If ZFS refuses with "more recent snapshots exist":** later snapshots block the rollback. Either `zfs destroy` them explicitly, or add `-r` to acknowledge their destruction:

```bash
zfs rollback -r hatch1/geo/<dataset>@<snapshot-name>
```

### Step 4c — Scale consumer(s) back to 1

```bash
kubectl -n civpulse-gis scale deployment nominatim --replicas=1

# Confirm pod comes Ready
kubectl -n civpulse-gis rollout status deploy/nominatim --timeout=5m
```

---

## 5. Validation Checklist After Rollback

Post-rollback, confirm the restored data is intact and functional:

- [ ] **Consumer pod is Ready:**
  ```bash
  kubectl -n civpulse-gis get deploy <name>
  # Expected: READY=1/1
  ```
- [ ] **Pod logs show clean startup (no schema/data errors):**
  ```bash
  kubectl -n civpulse-gis logs deploy/<name> --tail=50
  ```
- [ ] **No `CrashLoopBackOff` or `Error` states:**
  ```bash
  kubectl -n civpulse-gis get pods
  ```
- [ ] **`/health/ready` on geo-api reports the rolled-back sidecar as `ready`:**
  ```bash
  curl -s https://geo-api-prod.example.com/health/ready | jq .sidecars
  # Expected: sidecar in question shows "ready"
  ```
- [ ] **Relevant E2E endpoint(s) succeed** — run the matching check(s) from `docs/E2E.md`:
  - nominatim rollback → `/geocode/reverse`, `/poi/search`
  - tile-server rollback → `/tiles/{z}/{x}/{y}.png`
  - valhalla rollback → `/route`
- [ ] **Document the rollback** — record snapshot name, affected dataset, and reason in the incident log / SUMMARY.

---

## 6. Recovery When No Snapshot Exists

If no usable snapshot exists for a corrupted dataset, recovery = **re-bootstrap that dataset from scratch**:

1. Scale consumer(s) to 0 (Step 4a).
2. On `thor` as root: `zfs destroy -r hatch1/geo/<dataset>` then `zfs create hatch1/geo/<dataset>`.
3. Re-apply the corresponding bootstrap Job per `docs/BOOTSTRAP.md` Step 4 and `k8s/osm/base/jobs/README.md` §Re-running After Data Corruption.
4. Scale consumer(s) back to 1 after the Job completes.

Expected cost: pbf ~5 min, nominatim ~90 min, tile-server ~90 min, valhalla ~30 min.

---

## 7. Related

- `docs/ZFS-STORAGE.md` — storage layer reference (dataset layout, snapshot mechanics §4-5, Retain semantics §6)
- `docs/BOOTSTRAP.md` — fresh-cluster bring-up
- `docs/E2E.md` — post-rollback verification
- `k8s/osm/base/jobs/README.md` §Re-running After Data Corruption
