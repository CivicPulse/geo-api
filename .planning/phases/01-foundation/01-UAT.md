---
status: complete
phase: 01-foundation
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md]
started: 2026-03-19T12:00:00Z
updated: 2026-03-19T12:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running containers. Run `docker compose up --build -d`. Wait for services to be healthy. Server boots without errors, migrations complete, seed data loads, and `curl http://localhost:8000/health` returns a 200 response with live data.
result: pass
notes: Required two fixes — psycopg2-binary moved from dev to main deps, and retry loop added to docker-entrypoint.sh. After fixes, cold start completes successfully.

### 2. Health Endpoint (Healthy)
expected: `GET /health` returns HTTP 200 with JSON body confirming DB connectivity.
result: pass
notes: Verified via Playwright. Returns `{"name":"civpulse-geo","version":"0.1.0","status":"ok","database":"connected"}` with full project metadata.

### 3. Database Tables Created
expected: After migrations, the PostGIS database contains 4 application tables: `addresses`, `admin_overrides`, `geocoding_results`, `official_geocoding` — plus a `locationtype` enum.
result: pass
notes: All 4 tables confirmed via `\dt public.*`. Also present: alembic_version and spatial_ref_sys (PostGIS system table).

### 4. Seed Data Loaded
expected: `SELECT count(*) FROM addresses;` returns a non-zero count (Bibb County GeoJSON samples + 5 synthetic edge-case addresses).
result: pass
notes: 22 rows total (17 GeoJSON + 5 synthetic).

### 5. Unit Tests Pass
expected: `uv run pytest` runs all tests (54+) and exits with code 0 — no failures or errors.
result: pass
notes: 54 passed in 0.41s.

### 6. Address Normalization
expected: Running `canonical_key('123 main street, macon, georgia 31201')` produces a tuple of (normalized_address_string, sha256_hex_hash).
result: pass
notes: Returns `('123 MAIN ST MACON GA 31201', '52b82f07b8900a8f47156e756eb6886b96f29dc6e60ef4600bc809bbd3177547')`. Suffix normalization (street→ST), state expansion (georgia→GA), and case normalization all working.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none — two issues found and fixed during testing]

## Fixes Applied During UAT

1. **psycopg2-binary moved from dev to main dependencies** — Alembic and seed script require psycopg2 at runtime, but Dockerfile builds with `--no-dev`.
2. **Retry loop added to docker-entrypoint.sh** — PostGIS `pg_isready` healthcheck passes before full connection readiness; entrypoint now retries psycopg2 connection up to 30 times before running migrations.
