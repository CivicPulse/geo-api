---
phase: 20-health-resilience-and-k8s-manifests
plan: "01"
subsystem: infra
tags: [fastapi, health-check, k8s, liveness, readiness, graceful-shutdown, asyncpg, sigterm]

# Dependency graph
requires:
  - phase: 19-dockerfile-and-database-provisioning
    provides: Docker/K8s infrastructure prerequisites
provides:
  - /health/live liveness probe endpoint (no DB dependency)
  - /health/ready readiness probe endpoint (DB + provider threshold check)
  - Graceful lifespan shutdown with async engine disposal
  - SIGTERM safety-net handler
  - 9 health/shutdown tests (7 health + 2 shutdown)
affects: [21-ci-cd, 22-observability, 23-e2e-validation, k8s-manifests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Split liveness/readiness probes: /health/live never touches DB, /health/ready requires DB + providers"
    - "Lifespan shutdown sequence: http_client.aclose() → engine.dispose()"
    - "SIGTERM handler as belt-and-suspenders: asyncio signal handler creates cleanup task"
    - "TDD with lifespan context manager for shutdown tests (ASGITransport does not trigger lifespan)"

key-files:
  created:
    - tests/test_shutdown.py
  modified:
    - src/civpulse_geo/api/health.py
    - src/civpulse_geo/main.py
    - tests/test_health.py

key-decisions:
  - "/health/live has NO parameters and NO Depends -- returns 200 if process is alive (RESIL-01)"
  - "/health/ready uses Depends(get_db) and request.app.state to check providers threshold (RESIL-02)"
  - "Provider threshold is >= 2 geocoding AND >= 2 validation providers"
  - "Shutdown order: http_client.aclose() first, then engine.dispose() -- engine last because http_client may need DB during close"
  - "SIGTERM handler installed via asyncio.get_event_loop().add_signal_handler() with NotImplementedError guard for Windows (D-10)"
  - "Shutdown test uses lifespan(app) context manager directly -- ASGITransport does not trigger ASGI lifespan events"

patterns-established:
  - "Liveness probes must NEVER depend on external services to avoid restart loops in K8s"
  - "Readiness probes check both infrastructure (DB) and application state (providers) before accepting traffic"
  - "Engine disposal must happen last in shutdown sequence -- after all in-flight requests and HTTP connections close"

requirements-completed: [RESIL-01, RESIL-02, RESIL-03]

# Metrics
duration: 4min
completed: 2026-03-30
---

# Phase 20 Plan 01: Health Probes and Graceful Shutdown Summary

**Split K8s health probes with /health/live (process-only) and /health/ready (DB + provider threshold), plus lifespan engine disposal and SIGTERM safety-net handler**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-30T04:01:24Z
- **Completed:** 2026-03-30T04:05:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `/health/live` liveness probe that returns 200 immediately with zero external dependencies -- prevents K8s restart loops during DB outages
- Added `/health/ready` readiness probe that returns 503 when DB is unreachable or fewer than 2 geocoding/validation providers are registered -- prevents routing traffic before the app is fully initialized
- Wired graceful shutdown into the lifespan function: http_client.aclose() → engine.dispose() sequence with informational logging
- Added SIGTERM handler as belt-and-suspenders for cases where lifespan cleanup is bypassed
- 9 passing tests (7 health + 2 shutdown), 0 lint errors

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing health tests** - `b27e147` (test)
2. **Task 1 GREEN: /health/live and /health/ready endpoints** - `0722e6a` (feat)
3. **Task 2 RED: Failing shutdown test** - `74e3e9a` (test)
4. **Task 2 GREEN: Graceful shutdown with engine disposal** - `2301cbe` (feat)

_Note: TDD tasks have separate RED (test) and GREEN (implementation) commits_

## Files Created/Modified

- `src/civpulse_geo/api/health.py` - Added `/health/live` (no deps) and `/health/ready` (DB + provider check) endpoints; added `Request` and `HTTPException` to imports
- `src/civpulse_geo/main.py` - Added `_install_sigterm_handler()` and `_sigterm_cleanup()` module-level helpers; wired shutdown sequence in lifespan (http_client.aclose + engine.dispose); added `import asyncio, signal` at module level
- `tests/test_health.py` - Added 5 new test functions: test_health_live, test_health_live_db_down, test_health_ready_ok, test_health_ready_db_down, test_health_ready_insufficient_providers
- `tests/test_shutdown.py` - New file with test_shutdown_disposes_engine and test_shutdown_closes_http_client using lifespan context manager

## Decisions Made

- **ASGITransport does not trigger ASGI lifespan events**: Shutdown tests use `async with lifespan(app)` context manager directly instead of ASGITransport-wrapped AsyncClient to actually trigger startup/shutdown hooks
- **Provider threshold**: >= 2 geocoding AND >= 2 validation providers for readiness -- K8s should not route traffic with only the Census provider (local data sources needed for resilience)
- **Shutdown order**: `http_client.aclose()` before `engine.dispose()` -- matches plan specification; http client connections terminate first, then the DB pool closes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Shutdown test approach changed from ASGITransport to lifespan context manager**
- **Found during:** Task 2 (shutdown test implementation)
- **Issue:** The plan's suggested test pattern uses ASGITransport + AsyncClient to trigger lifespan, but `httpx.ASGITransport` does not send ASGI lifespan events -- the shutdown block never ran
- **Fix:** Used `async with lifespan(app):` directly in tests instead of wrapping in AsyncClient. This reliably triggers both startup and shutdown phases
- **Files modified:** tests/test_shutdown.py
- **Verification:** `mock_engine.dispose.assert_awaited_once()` passes; lifespan startup/shutdown verified
- **Committed in:** 2301cbe (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug in test approach)
**Impact on plan:** Test strategy adjustment only -- implementation is unchanged from plan specification.

## Issues Encountered

- Pre-existing test failures in `tests/test_import_cli.py` (missing `data/SAMPLE_Address_Points.geojson` in worktree) and `tests/test_load_oa_cli.py` (accuracy parcel regression). These are out of scope for this plan and were present before any changes. Documented in deferred-items.md.

## Known Stubs

None - all endpoints are fully wired with real logic.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- K8s liveness and readiness probe endpoints are ready for use in Deployment manifests (Phase 20 Plan 02)
- Graceful shutdown hooks in place for SIGTERM-based pod termination
- `/health/live` → `livenessProbe.httpGet.path: /health/live`
- `/health/ready` → `readinessProbe.httpGet.path: /health/ready`

---
*Phase: 20-health-resilience-and-k8s-manifests*
*Completed: 2026-03-30*
