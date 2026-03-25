---
phase: quick
plan: 260325-0pw
subsystem: data-layer
tags: [parcels, openaddresses, cli, alembic, orm]
dependency_graph:
  requires: [openaddresses-point-staging]
  provides: [openaddresses-parcel-staging, load-oa-parcels-cli]
  affects: [cli, models, migrations]
tech_stack:
  added: []
  patterns: [pure-python-geojson-to-ewkt, upsert-on-conflict, batched-bulk-load]
key_files:
  created:
    - src/civpulse_geo/models/parcels.py
    - alembic/versions/d4a71c3f8b92_add_oa_parcels_table.py
  modified:
    - src/civpulse_geo/models/__init__.py
    - src/civpulse_geo/cli/__init__.py
decisions:
  - "Pure Python _polygon_geojson_to_ewkt helper replaces shapely — no new dependencies per project constraint"
  - "Shapely was removed from CLI imports and replaced with inline coordinate-to-WKT conversion"
metrics:
  duration: 15m
  completed: "2026-03-25"
  tasks_completed: 2
  files_modified: 4
---

# Quick Task 260325-0pw: Add OpenAddresses Parcel Boundary Staging Summary

**One-liner:** ORM model, Alembic migration, and CLI bulk-load command for OpenAddresses parcel boundary polygons with pure-Python GeoJSON-to-EWKT conversion (no new dependencies).

## Tasks Completed

| # | Name | Status | Commit |
|---|------|--------|--------|
| 1 | Verify implementation completeness | Complete | fcc0de9 |
| 2 | Run existing test suite for regression check | Complete | fcc0de9 |

## What Was Delivered

- **`src/civpulse_geo/models/parcels.py`** — `OpenAddressesParcel` ORM model backed by `openaddresses_parcels` table. Columns: `id`, `source_hash` (String 64, unique), `pid`, `county`, `state`, `boundary` (Geography POLYGON SRID=4326), `address_id` (FK → addresses.id, nullable), plus `created_at`/`updated_at` via `TimestampMixin`.

- **`src/civpulse_geo/models/__init__.py`** — Updated to import and export `OpenAddressesParcel` in `__all__`.

- **`alembic/versions/d4a71c3f8b92_add_oa_parcels_table.py`** — Migration creating `openaddresses_parcels` with GiST spatial index on `boundary` and lookup indexes on `pid`, `(state, county)`, and `address_id`. Down revision: `c1f84b2e9a07`.

- **`src/civpulse_geo/cli/__init__.py`** — Added `_polygon_geojson_to_ewkt()`, `_parse_oa_parcel_feature()`, `_upsert_oa_parcel_batch()`, and `load-oa-parcels` Typer command. Accepts `--file` (`.geojson.gz`), `--state`, `--county`, `--database-url`. Upserts on `uq_oa_parcel_source_hash` in batches of 1000 with Rich progress bar.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed shapely dependency — not installed and not in pyproject.toml**
- **Found during:** Task 1 verification
- **Issue:** `from shapely.geometry import shape as shapely_shape` was added to CLI `__init__.py` but `shapely` is not installed in the venv and is not declared in `pyproject.toml`. Project has an explicit constraint: no new Python dependencies (stdlib + usaddress + asyncpg/sqlalchemy only).
- **Fix:** Removed the `shapely` import and replaced its usage in `_parse_oa_parcel_feature` with a new pure-Python helper `_polygon_geojson_to_ewkt()` that converts GeoJSON Polygon coordinate arrays directly to EWKT format (e.g., `SRID=4326;POLYGON ((lon lat, ...))`). Functionally equivalent for well-formed Polygon geometries.
- **Files modified:** `src/civpulse_geo/cli/__init__.py`
- **Commit:** fcc0de9

### Pre-existing Test Failures (out of scope)

Two test failures exist on `main` before this task's changes:
1. `tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features` — missing fixture file `data/SAMPLE_Address_Points.geojson`
2. `tests/test_load_oa_cli.py::TestLoadOaImport::test_parse_oa_feature_empty_strings_to_none` — `accuracy` field returns `'parcel'` instead of `None`

Both confirmed pre-existing via `git stash` isolation. Our changes introduced zero regressions (322 other tests pass).

## Self-Check: PASSED

- `src/civpulse_geo/models/parcels.py` — FOUND
- `src/civpulse_geo/models/__init__.py` — updated, OpenAddressesParcel in __all__
- `alembic/versions/d4a71c3f8b92_add_oa_parcels_table.py` — FOUND
- `src/civpulse_geo/cli/__init__.py` — load-oa-parcels command verified via `geo-import --help`
- Commit fcc0de9 — FOUND
