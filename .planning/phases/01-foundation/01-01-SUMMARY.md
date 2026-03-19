---
phase: 01-foundation
plan: 01
subsystem: database
tags: [fastapi, sqlalchemy, geoalchemy2, postgis, alembic, pydantic-settings, asyncpg, python, uv]

# Dependency graph
requires: []
provides:
  - Installable civpulse-geo Python package with src layout via uv
  - All ORM models: Address, GeocodingResult, OfficialGeocoding, AdminOverride
  - PostGIS geography(Point, 4326) columns on geocoding_results and admin_overrides
  - LocationType PostgreSQL enum (ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE)
  - Alembic migration infrastructure with GeoAlchemy2 helpers configured
  - Pydantic Settings with async and sync database URLs
  - Async SQLAlchemy engine, session factory, and get_db FastAPI dependency
affects:
  - 01-02: normalization and provider ABCs use the package structure
  - 01-03: FastAPI app, health endpoint, Docker Compose build on this foundation
  - All future plans: ORM models must be imported from civpulse_geo.models

# Tech tracking
tech-stack:
  added:
    - fastapi[standard]==0.135.1
    - sqlalchemy==2.0.48
    - geoalchemy2==0.18.4
    - alembic==1.18.4
    - asyncpg==0.31.0
    - pydantic-settings==2.13.1
    - loguru==0.7.3
    - typer==0.24.1
    - usaddress-scourgify==0.6.0
    - pytest==9.0.2 (dev)
    - pytest-asyncio==1.3.0 (dev)
    - httpx==0.28.1 (dev)
    - psycopg2-binary==2.9.11 (dev)
  patterns:
    - DeclarativeBase from sqlalchemy.orm (not legacy declarative_base())
    - TimestampMixin with server_default=func.now() for created_at/updated_at
    - Geography(geometry_type='POINT', srid=4326) for all coordinate columns (not Geometry)
    - Separate async engine (asyncpg) for app + sync URL (psycopg2) for Alembic
    - GeoAlchemy2 alembic_helpers wired in both offline and online migration modes

key-files:
  created:
    - pyproject.toml
    - .python-version
    - .env.example
    - uv.lock
    - src/civpulse_geo/__init__.py
    - src/civpulse_geo/config.py
    - src/civpulse_geo/database.py
    - src/civpulse_geo/models/__init__.py
    - src/civpulse_geo/models/base.py
    - src/civpulse_geo/models/enums.py
    - src/civpulse_geo/models/address.py
    - src/civpulse_geo/models/geocoding.py
    - alembic.ini
    - alembic/env.py
    - alembic/script.py.mako
    - alembic/versions/.gitkeep
  modified: []

key-decisions:
  - "Use Geography(POINT, 4326) not Geometry for all coordinate columns — distance-in-meters semantics, locked by project"
  - "Two database URLs: asyncpg (DATABASE_URL) for app, psycopg2 (DATABASE_URL_SYNC) for Alembic — Alembic cannot use async engine"
  - "TimestampMixin uses server_default=func.now() so timestamps are set by PostgreSQL, not the application"
  - "address_hash column is SHA-256 of normalized_address — 64-char String for fast index-based cache lookups"
  - "GeocodingResult.uq_geocoding_address_provider unique constraint prevents duplicate provider results per address"
  - "Self-referencing base_address_id FK on Address supports two-tier key: units inherit base address geocode"

patterns-established:
  - "Pattern: DeclarativeBase from sqlalchemy.orm — do not use legacy declarative_base() from sqlalchemy.ext.declarative"
  - "Pattern: Geography(geometry_type='POINT', srid=4326) — always use Geography not Geometry for coordinate columns"
  - "Pattern: Three GeoAlchemy2 alembic helpers in env.py — include_object, writer, render_item — required to prevent broken autogenerate migrations"
  - "Pattern: Async engine for app requests, sync URL for Alembic migrations — never use asyncpg with Alembic"

requirements-completed: []

# Metrics
duration: 4min
completed: 2026-03-19
---

# Phase 1 Plan 01: Scaffold and Data Model Summary

**uv-managed civpulse-geo package with four PostGIS ORM models (Address, GeocodingResult, OfficialGeocoding, AdminOverride) using geography(Point, 4326) columns and Alembic configured with GeoAlchemy2 helpers**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-19T04:09:45Z
- **Completed:** 2026-03-19T04:13:45Z
- **Tasks:** 2
- **Files modified:** 16

## Accomplishments

- Initialized uv project as civpulse-geo with src layout, locked all 13+ dependencies including fastapi, sqlalchemy, geoalchemy2, alembic, asyncpg, and usaddress-scourgify
- Defined four ORM models with correct SQLAlchemy 2.0 DeclarativeBase, geography(Point, 4326) columns, PostgreSQL enum, unique constraints, and self-referencing FK
- Configured Alembic env.py with all three GeoAlchemy2 helpers and psycopg2 sync URL to prevent broken autogenerate migrations

## Task Commits

Each task was committed atomically:

1. **Task 1: Create project structure, dependencies, and configuration** - `099c842` (feat)
2. **Task 2: Define ORM models and Alembic migration infrastructure** - `cf1808b` (feat)

## Files Created/Modified

- `pyproject.toml` - civpulse-geo package metadata, all 13+ locked dependencies, pytest config
- `.python-version` - Pins Python 3.12
- `.env.example` - DATABASE_URL (asyncpg) and DATABASE_URL_SYNC (psycopg2) template
- `uv.lock` - Full dependency lock file
- `src/civpulse_geo/__init__.py` - Package version string
- `src/civpulse_geo/config.py` - Pydantic Settings with database_url and database_url_sync
- `src/civpulse_geo/database.py` - Async engine, AsyncSessionLocal, get_db dependency
- `src/civpulse_geo/models/base.py` - DeclarativeBase + TimestampMixin with server_default
- `src/civpulse_geo/models/enums.py` - LocationType enum (ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE)
- `src/civpulse_geo/models/address.py` - Address model with parsed components, address_hash, base_address_id self-FK
- `src/civpulse_geo/models/geocoding.py` - GeocodingResult, OfficialGeocoding, AdminOverride with Geography columns
- `src/civpulse_geo/models/__init__.py` - Re-exports all models
- `alembic.ini` - Alembic config with empty sqlalchemy.url (overridden in env.py)
- `alembic/env.py` - GeoAlchemy2 helpers + settings.database_url_sync for both offline and online modes
- `alembic/script.py.mako` - Migration file template
- `alembic/versions/.gitkeep` - Tracks empty versions directory in git

## Decisions Made

- Used `Geography(geometry_type='POINT', srid=4326)` exclusively — project locked to distance-in-meters semantics; changing to Geometry post-data would require schema migration
- Two database URLs from the same pydantic-settings Config: asyncpg for the FastAPI async engine, psycopg2 for Alembic synchronous migrations — Alembic raises NotImplementedError with async drivers
- SHA-256 hash (64-char hex) as `address_hash` column with unique index — fast O(1) cache lookups without full normalized string comparison
- `server_default=func.now()` in TimestampMixin — timestamps set by PostgreSQL server clock, not application, ensuring consistency across time zones and app restarts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Package installable via `uv run python -c "from civpulse_geo.models import Base"` — all four ORM models importable
- Alembic migration infrastructure ready; `alembic upgrade head` will work once PostgreSQL/PostGIS is available (Plan 01-03)
- Plan 01-02 (normalization + provider ABCs) can begin immediately — package structure is in place

---
*Phase: 01-foundation*
*Completed: 2026-03-19*

## Self-Check: PASSED

- All key files found on disk
- Task 1 commit 099c842 verified in git log
- Task 2 commit cf1808b verified in git log
- All four ORM tables importable from civpulse_geo.models
