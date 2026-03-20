---
phase: 01-foundation
plan: 03
subsystem: api
tags: [fastapi, docker, postgis, alembic, sqlalchemy, geoalchemy2, typer, httpx, pytest]

requires:
  - phase: 01-01
    provides: ORM models (Address, GeocodingResult, OfficialGeocoding, AdminOverride), database.py, config.py, normalization.py
  - phase: 01-02
    provides: Provider registry (load_providers), provider ABCs, provider schemas

provides:
  - FastAPI app with asynccontextmanager lifespan pattern, provider registry initialized at startup
  - GET /health endpoint returning 200 with DB connectivity check or 503 on failure
  - Docker Compose environment: PostGIS 17-3.5 + API with healthcheck-gated startup
  - Dockerfile using uv multi-stage build with venv PATH injection and docker-entrypoint.sh
  - Alembic initial migration creating all 4 application tables with PostGIS geography columns
  - Seed script loading Bibb County GeoJSON samples + 5 synthetic edge-case addresses
  - Test infrastructure: async test client, mock DB session, override_db fixtures in conftest.py

affects:
  - phase-02 (geocoding providers will add to provider registry, use health endpoint pattern)
  - phase-03 (admin UI will use the running Docker stack and health endpoint)
  - phase-04 (all API endpoints follow the router.include pattern established here)

tech-stack:
  added:
    - httpx (ASGITransport for async FastAPI test client)
    - pytest-asyncio (asyncio_mode=auto for async test fixtures)
    - loguru (FastAPI lifespan logging)
  patterns:
    - asynccontextmanager lifespan for FastAPI startup/shutdown (not deprecated @app.on_event)
    - app.dependency_overrides for mocking get_db in tests without real PostGIS
    - ON CONFLICT DO NOTHING for idempotent seed data insertion
    - GeoAlchemy2 helpers (include_object, writer, render_item) in both offline/online Alembic context

key-files:
  created:
    - src/civpulse_geo/api/__init__.py
    - src/civpulse_geo/api/health.py
    - src/civpulse_geo/main.py
    - tests/conftest.py
    - tests/test_health.py
    - Dockerfile
    - docker-compose.yml
    - scripts/seed.py
    - scripts/docker-entrypoint.sh
    - alembic/versions/b98c26825b02_initial_schema.py
  modified: []

key-decisions:
  - "asynccontextmanager lifespan used throughout — not deprecated @app.on_event — future API additions must follow same pattern"
  - "app.dependency_overrides pattern for test DB mocking — no TestClient wrapper, uses httpx.AsyncClient with ASGITransport"
  - "Alembic autogenerate includes PostGIS TIGER extension tables in DROP statements; manually removed all TIGER/topology drops from migration to scope only application tables"
  - "Seed script uses synchronous psycopg2 (DATABASE_URL_SYNC) not asyncpg — consistent with Alembic pattern, no event loop needed for CLI"
  - "docker-entrypoint.sh runs alembic then seed then uvicorn — migrations and seed are idempotent so re-runs are safe"

patterns-established:
  - "FastAPI lifespan: @asynccontextmanager, load_providers({}) at startup, yield, log shutdown"
  - "Health endpoint: Depends(get_db), await db.execute(text('SELECT 1')), 503 on exception"
  - "Test DB mock: AsyncMock session, app.dependency_overrides[get_db] = _override, clear after test"
  - "Alembic migration: remove PostGIS extension table references from autogenerate output before committing"

requirements-completed: [INFRA-05, INFRA-07]

duration: 5min
completed: 2026-03-19
---

# Phase 1 Plan 03: Wire Up FastAPI, Docker, and Seed Data Summary

**FastAPI app with asynccontextmanager lifespan, GET /health with PostGIS connectivity check, Docker Compose (PostGIS 17-3.5 + uv API image), and Alembic initial migration for all 4 tables with Bibb County GeoJSON seed data**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-19T04:17:58Z
- **Completed:** 2026-03-19T04:22:51Z
- **Tasks:** 3 (2 auto + 1 checkpoint auto-approved)
- **Files modified:** 10

## Accomplishments

- FastAPI app wired with asynccontextmanager lifespan, provider registry (empty for Phase 1), and health router — all 54 unit tests pass without running DB
- Docker Compose brings up PostGIS 17-3.5 with healthcheck and API with `condition: service_healthy` — entrypoint runs migrations, seeds, then starts uvicorn
- Alembic initial migration creates all 4 tables (addresses, admin_overrides, geocoding_results, official_geocoding) with Geography(POINT, 4326) columns and locationtype enum — verified round-trip upgrade/downgrade

## Task Commits

Each task was committed atomically:

1. **Task 1: FastAPI app, health endpoint, and test infrastructure** - `5dc1fba` (feat)
2. **Task 2: Docker Compose, Dockerfile, seed data, and Alembic initial migration** - `37add65` (feat)
3. **Task 3: Verify Docker Compose** - auto-approved checkpoint (no commit)

## Files Created/Modified

- `src/civpulse_geo/main.py` - FastAPI app with lifespan, provider registry init, health router
- `src/civpulse_geo/api/__init__.py` - Empty package init for api module
- `src/civpulse_geo/api/health.py` - GET /health with Depends(get_db) and SELECT 1 check
- `tests/conftest.py` - test_client (httpx.AsyncClient/ASGITransport), mock_db_session, override_db fixtures
- `tests/test_health.py` - test_health_ok and test_health_db_down (both pass with mocked DB)
- `Dockerfile` - python:3.12-slim + uv binary, dep install cache, venv PATH, entrypoint script
- `docker-compose.yml` - PostGIS 17-3.5 with pg_isready healthcheck, API with service_healthy condition
- `scripts/docker-entrypoint.sh` - Runs alembic upgrade head, seed.py, then uvicorn
- `scripts/seed.py` - Typer CLI: loads SAMPLE_Address_Points.geojson + 5 synthetic addresses via psycopg2
- `alembic/versions/b98c26825b02_initial_schema.py` - Initial schema migration for all 4 application tables

## Decisions Made

- Used `app.dependency_overrides` for mocking `get_db` in tests — cleaner than subclassing TestClient, allows async mocking without real PostGIS
- Seed script uses psycopg2 synchronous engine (`DATABASE_URL_SYNC`) consistent with Alembic pattern — no async event loop complexity in CLI
- `docker-entrypoint.sh` runs both migrations and seed at container start — both are idempotent (ON CONFLICT DO NOTHING) so safe for restarts

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed PostGIS TIGER table DROP statements from Alembic migration**
- **Found during:** Task 2 (Alembic initial migration generation)
- **Issue:** `alembic revision --autogenerate` compared our ORM metadata against the full PostGIS database (which includes TIGER geocoder tables in the `tiger` schema). Autogenerate produced DROP statements for ~30 TIGER/topology tables in the upgrade() function. Running this migration would have dropped PostGIS extension tables needed for spatial operations.
- **Fix:** Manually edited the generated migration to remove all TIGER/topology DROP operations from upgrade() and the corresponding CREATE operations from downgrade(). Kept only the 4 CivPulse application tables (addresses, admin_overrides, geocoding_results, official_geocoding) plus their indexes and the locationtype enum.
- **Files modified:** alembic/versions/b98c26825b02_initial_schema.py
- **Verification:** `alembic upgrade head` then `alembic downgrade base` then `alembic upgrade head` all complete without errors; `\dt` confirms 4 application tables created, TIGER tables intact
- **Committed in:** 37add65 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug in autogenerated migration)
**Impact on plan:** Auto-fix necessary for correctness — the autogenerated migration would have corrupted the PostGIS extension. No scope creep.

## Issues Encountered

- Alembic autogenerate connected to PostGIS 17-3.5 which includes the TIGER geocoder schema in the same database. Alembic has no way to distinguish application tables from extension tables without schema-level filtering — requires manual migration cleanup. Future practice: use Alembic `include_schemas` or add `exclude_tables` list to env.py to exclude tiger/topology schemas from autogenerate.

## User Setup Required

To run the full stack:
```bash
docker compose up --build -d
sleep 15
curl http://localhost:8000/health
# Expected: {"status":"ok","database":"connected"}
```

## Next Phase Readiness

- All foundation infrastructure is in place: app, health endpoint, Docker stack, migrations, seed data
- Phase 2 can add geocoding provider adapters (Census, USPS) by registering them in `load_providers({})` call in main.py
- Phase 2 provider tests can use the same `override_db` fixture pattern from conftest.py
- Blocker: Google Maps Platform ToS caching clause must be reviewed before building Google adapter (existing concern from Phase 01)

---
*Phase: 01-foundation*
*Completed: 2026-03-19*

## Self-Check: PASSED

Files verified:
- FOUND: src/civpulse_geo/main.py
- FOUND: src/civpulse_geo/api/__init__.py
- FOUND: src/civpulse_geo/api/health.py
- FOUND: tests/conftest.py
- FOUND: tests/test_health.py
- FOUND: Dockerfile
- FOUND: docker-compose.yml
- FOUND: scripts/seed.py
- FOUND: scripts/docker-entrypoint.sh
- FOUND: alembic/versions/b98c26825b02_initial_schema.py

Commits verified:
- FOUND: 5dc1fba (Task 1)
- FOUND: 37add65 (Task 2)
