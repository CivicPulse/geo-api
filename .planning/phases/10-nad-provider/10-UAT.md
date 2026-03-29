---
status: testing
phase: 10-nad-provider
source: [10-01-SUMMARY.md, 10-02-SUMMARY.md]
started: 2026-03-24T10:06:00Z
updated: 2026-03-29T00:00:00Z
---

## Current Test

number: 6
name: load-nad loads data from ZIP
expected: |
  Running `geo-import load-nad NAD_r21_TXT.zip --state GA` streams CSV from ZIP, shows Rich progress bar with row count, exits with success. nad_points table is populated.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running server. Start the application from scratch (e.g. `docker compose up`). The server boots without errors, startup logs appear, and a health check or basic API call returns a live response. No crash, no missing-import error.
result: pass

### 2. NAD absent startup warning
expected: With no NAD data loaded (nad_points empty or table absent), the server still boots cleanly. Startup log shows a warning but does NOT crash. Provider count reflects NAD providers as absent.
result: pass

### 3. load-nad --help shows --state as required
expected: Running `geo-import load-nad --help` shows `--state` listed as required. Help text describes FIPS code or abbreviation accepted. No references to "pipe-delimited".
result: pass

### 4. load-nad rejects missing --state
expected: Running `geo-import load-nad some.zip` (without `--state`) exits with a clear error saying --state is required. No traceback.
result: pass

### 5. load-nad rejects invalid state
expected: Running `geo-import load-nad some.zip --state ZZ` exits with a clear error like "unknown state identifier: ZZ". No crash or traceback.
result: pass

### 6. load-nad loads data from ZIP
expected: Running `geo-import load-nad NAD_r21_TXT.zip --state GA` streams CSV from ZIP, shows Rich progress bar with row count, exits with success. nad_points table is populated.
result: [pending]

### 7. NAD providers register after data load
expected: After loading NAD data, restart server. Startup log shows NAD geocoding and validation providers registered.
result: [pending]

### 8. NAD geocoding returns result
expected: POST /geocode with an address in loaded state returns a result from NAD with confidence score and location_type field.
result: [pending]

### 9. NAD validation returns result
expected: POST /validate with an address in loaded state returns normalized address from NAD provider with street, city, state, zip fields.
result: [pending]

## Summary

total: 9
passed: 5
issues: 0
pending: 4
skipped: 0

## Gaps

[none]

<!-- resolved during UAT: cold-start failure caused by seed.py fatal exit on missing GeoJSON was fixed
     (scripts/seed.py now warns and continues; .dockerignore added to exclude data/ from build context) -->

- truth: "Server boots from cold start without errors and responds to API calls (RESOLVED)"
  status: failed
  reason: "User reported: Container exits at seed step. seed.py:219 calls raise typer.Exit(code=1) when data/SAMPLE_Address_Points.geojson is not found. docker-entrypoint.sh has set -e so the whole container exits. Actual Bibb County data file is present under a different name: data/Address_Points(1).geojson"
  severity: blocker
  test: 1
  root_cause: "seed.py treats missing GeoJSON as a fatal error (raise typer.Exit(code=1) at line 219). docker-entrypoint.sh uses set -e so propagates that exit. The DEFAULT_GEOJSON path (data/SAMPLE_Address_Points.geojson) does not exist — actual file is Address_Points(1).geojson. GeoJSON loading should be optional: skip with a warning when file is absent, still load synthetic addresses, let container start."
  artifacts:
    - path: "scripts/seed.py"
      issue: "Line 219 raises Exit(code=1) when GeoJSON missing — should warn and continue without GeoJSON data"
    - path: "scripts/docker-entrypoint.sh"
      issue: "set -e causes container to exit on non-zero seed exit code"
  missing:
    - "Make GeoJSON loading optional in seed.py: print warning and skip geojson block when file not found, only exit if no viable data path exists"
  debug_session: ""
