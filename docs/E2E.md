# End-to-End Verification Checklist

Post-deploy smoke check for the CivPulse Geo API against a live K8s cluster. Runs every endpoint introduced in v1.4 + v1.5 against both `civpulse-dev` and `civpulse-prod`. Scannable — operators should be able to work through this in 5-10 minutes.

**When to run:**

- After a fresh cluster bootstrap (`docs/BOOTSTRAP.md` Step 6)
- After a milestone ship (final validation gate)
- After a ZFS rollback / DR exercise (`docs/DR.md` §5)
- After any `osm-stack` ArgoCD re-sync that touched sidecar images or configs
- Weekly (optional) as drift detection

**Related docs:**
- `docs/BOOTSTRAP.md` — fresh-cluster bring-up
- `docs/DR.md` — disaster recovery
- `k8s/osm/base/jobs/README.md` — Job troubleshooting

---

## 1. Environment Table

| Env | Namespace | Base URL template |
|-----|-----------|-------------------|
| dev  | `civpulse-dev`  | `https://geo-api-dev.example.com`  |
| prod | `civpulse-prod` | `https://geo-api-prod.example.com` |

Replace `example.com` with your actual ingress domain. Set `BASE_URL` before running checks:

```bash
# Dev
BASE_URL=https://geo-api-dev.example.com

# Prod
BASE_URL=https://geo-api-prod.example.com
```

**Run every check in both environments.** Georgia-specific sample coordinates are used throughout (downtown Atlanta, lat=33.7490 lon=-84.3880) since the OSM stack is loaded with `georgia-latest.osm.pbf`.

---

## 2. Checklist

### 2.1 — `GET /health` (liveness)

```bash
curl -s -o /tmp/health.json -w "HTTP %{http_code}\n" $BASE_URL/health && cat /tmp/health.json | jq
```

- **Expected status:** `HTTP 200`
- **Expected payload shape:** `{"status": "ok", ...}` (object with `status: "ok"`; additional fields like `version` / `timestamp` may be present)
- **Failure diagnostic:** if non-200 or connection refused, the geo-api pod itself is down. `kubectl -n civpulse-{dev|prod} get pods -l app=geo-api` and check logs. This is a geo-api outage, not an OSM stack issue.

---

### 2.2 — `GET /health/ready` (readiness + sidecar probes)

```bash
curl -s $BASE_URL/health/ready | jq
```

- **Expected status:** `HTTP 200`
- **Expected payload shape:**
  ```json
  {
    "status": "ready",
    "sidecars": {
      "nominatim": "ready",
      "tile_server": "ready",
      "valhalla": "ready"
    }
  }
  ```
- **Success markers:** all three sidecars report `ready`.
- **Failure diagnostic:**
  - Any sidecar `not_ready` → cross-namespace DNS or the sidecar itself is down. Check `kubectl -n civpulse-gis get deploy` — all three should be `READY=1/1`. See `docs/BOOTSTRAP.md` §Troubleshooting.
  - `HTTP 503` → geo-api deliberately failing readiness because sidecars are down. Fix sidecar, then re-check.

---

### 2.3 — `GET /tiles/10/271/415.png` (tile proxy)

Tile coords `z=10 x=271 y=415` cover Georgia.

```bash
curl -s -o /tmp/tile.png -w "HTTP %{http_code} | content-type: %{content_type} | size: %{size_download}B\n" \
  $BASE_URL/tiles/10/271/415.png
file /tmp/tile.png
```

- **Expected status:** `HTTP 200`
- **Expected content-type:** `image/png`
- **Expected size:** > 1KB (non-empty PNG)
- **`file` output:** `PNG image data, 256 x 256, ...`
- **Failure diagnostic:**
  - `HTTP 404` / `content-type: application/json` → tile not yet rendered (normal for fresh imports; tile-server renders on demand). Retry after a few seconds.
  - `HTTP 502` / `503` → tile-server sidecar unreachable. Check `/health/ready`.
  - `HTTP 500` → tile-server import incomplete. Check `tile-import-job` status: `kubectl -n civpulse-gis get jobs tile-import-job`.

---

### 2.4 — `POST /geocode/reverse` (Nominatim reverse geocode)

Downtown Atlanta coordinate — must return an Atlanta-area address.

```bash
curl -s -X POST $BASE_URL/geocode/reverse \
  -H 'Content-Type: application/json' \
  -d '{"lat": 33.7490, "lon": -84.3880}' | jq
```

- **Expected status:** `HTTP 200`
- **Expected payload shape:**
  ```json
  {
    "address": "<non-empty string, contains 'Atlanta' or 'GA'>",
    "lat": 33.7...,
    "lon": -84.3...,
    ...
  }
  ```
- **Success markers:** `address` field contains `"Atlanta"` or a recognizable Atlanta street. Coordinates round-trip close to input.
- **Failure diagnostic:**
  - `HTTP 503` → Nominatim sidecar unreachable. Check `/health/ready`.
  - `HTTP 200` but `address` empty / null → Nominatim DB not imported or only partially imported. Check `kubectl -n civpulse-gis logs deploy/nominatim` for import completion.
  - Address outside Georgia → wrong PBF imported. Re-verify `pbf-download-job` used the Georgia extract.

---

### 2.5 — `GET /poi/search` (POI search)

```bash
curl -s -G $BASE_URL/poi/search \
  --data-urlencode "q=Georgia State Capitol" \
  --data-urlencode "lat=33.7490" \
  --data-urlencode "lon=-84.3880" | jq
```

- **Expected status:** `HTTP 200`
- **Expected payload shape:**
  ```json
  {
    "results": [
      {"name": "...Georgia State Capitol...", "lat": 33.7..., "lon": -84.3..., ...},
      ...
    ]
  }
  ```
  (or a top-level array, depending on route shape — the key check is it's non-empty)
- **Success markers:** `results` is non-empty; at least one result references the Capitol with coordinates near `33.7490, -84.3880`.
- **Failure diagnostic:**
  - Empty `results` list → Nominatim search index incomplete or wrong region. Confirm import completed and PBF is Georgia.
  - `HTTP 503` → sidecar down; see `/health/ready`.

---

### 2.6 — `POST /route` (Valhalla pedestrian)

Short walking route, Atlanta downtown → Georgia State Capitol (~0.5 mi).

```bash
curl -s -X POST $BASE_URL/route \
  -H 'Content-Type: application/json' \
  -d '{
    "costing": "pedestrian",
    "locations": [
      {"lat": 33.7490, "lon": -84.3880},
      {"lat": 33.7489, "lon": -84.3902}
    ]
  }' | jq '.trip.summary // .summary // .'
```

- **Expected status:** `HTTP 200`
- **Expected payload shape:** JSON with a trip summary containing `length` and `time` fields (Valhalla-standard response). Non-zero positive values.
- **Success markers:** `length` < 2 mi, `time` < 2000s (walking pace over a short distance).
- **Failure diagnostic:**
  - `HTTP 503` → Valhalla sidecar unreachable.
  - `HTTP 400 "No route found"` → Valhalla tiles missing or not built for this region. Check `kubectl -n civpulse-gis get jobs valhalla-build-job`.

---

### 2.7 — `POST /route` (Valhalla driving, Atlanta → Macon)

Longer driving route across Georgia (~85 mi) — exercises the routing graph end-to-end.

```bash
curl -s -X POST $BASE_URL/route \
  -H 'Content-Type: application/json' \
  -d '{
    "costing": "auto",
    "locations": [
      {"lat": 33.7490, "lon": -84.3880},
      {"lat": 32.8407, "lon": -83.6324}
    ]
  }' | jq '.trip.summary // .summary // .'
```

- **Expected status:** `HTTP 200`
- **Expected payload shape:** trip summary with `length` and `time`.
- **Success markers:** `length` ≈ 80-100 mi, `time` ≈ 5000-7000s (1.5-2 hours by car).
- **Failure diagnostic:**
  - `length` wildly off → routing tiles may be partial. Re-check `valhalla-build-job` logs.
  - `HTTP 400 "No route found"` → graph does not span Atlanta→Macon; possible incomplete Valhalla build.

---

## 3. Sample Success Output

All checks passed = bootstrap/DR/ship gate is GREEN. Record in the incident log or SUMMARY:

```
E2E run YYYY-MM-DD — env=prod
  /health                 ✓ 200
  /health/ready           ✓ 200, all 3 sidecars ready
  /tiles/10/271/415.png   ✓ 200, image/png, 12.4KB
  /geocode/reverse        ✓ 200, address contains "Atlanta"
  /poi/search             ✓ 200, 7 results, top=Georgia State Capitol
  /route (pedestrian)     ✓ 200, 0.13 mi, 180s
  /route (auto ATL→Macon) ✓ 200, 83.7 mi, 5220s
```

---

## 4. Troubleshooting Map

| Symptom | Likely cause | Doc |
|---------|--------------|-----|
| `/health` non-200 | geo-api pod down | `kubectl logs -n civpulse-{dev,prod} deploy/geo-api` |
| `/health/ready` sidecar not ready | OSM sidecar down or cross-ns DNS fail | `docs/BOOTSTRAP.md` §Troubleshooting |
| `/tiles` 404 transiently | first-render latency | retry; normal for fresh imports |
| `/tiles` 500/502/503 | tile-server down or import incomplete | `k8s/osm/base/jobs/README.md` §Troubleshooting |
| `/geocode/reverse` empty address | Nominatim DB not imported | `kubectl logs -n civpulse-gis deploy/nominatim` |
| `/poi/search` empty results | wrong region PBF or search index incomplete | confirm Georgia PBF was downloaded |
| `/route` "No route found" | Valhalla tiles missing | `kubectl -n civpulse-gis get jobs valhalla-build-job` |
| Data corruption / need restore | — | `docs/DR.md` |
