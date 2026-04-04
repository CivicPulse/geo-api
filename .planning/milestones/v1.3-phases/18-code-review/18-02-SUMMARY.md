---
phase: 18-code-review
plan: "02"
subsystem: api
tags: [fastapi, starlette, exception-handling, stability, testing]

# Dependency graph
requires:
  - phase: 18-01-PLAN
    provides: security blocker fixes; this plan follows with stability fixes
provides:
  - Global FastAPI exception handler returning structured 500 JSON for unhandled exceptions (STAB-01, STAB-02)
  - Per-provider try/except in legacy geocoding provider loops preventing single-provider crash from failing entire request (STAB-04)
  - Removal of unused CascadeResult import (ruff F401 fix)
  - 3 regression tests verifying exception handler behavior
affects: [18-code-review, api-stability, geocoding-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Global FastAPI exception_handler(Exception) in main.py after app= definition, before app.include_router"
    - "Per-provider try/except wrapping entire loop body (not just .geocode() call) so DB upsert errors also degrade gracefully"
    - "TestClient(raise_server_exceptions=False) for testing generic exception handlers in Starlette 0.52+"

key-files:
  created:
    - tests/test_exception_handling.py
  modified:
    - src/civpulse_geo/main.py
    - src/civpulse_geo/services/geocoding.py

key-decisions:
  - "TestClient(raise_server_exceptions=False) required instead of AsyncClient+ASGITransport for testing generic exception handlers — Starlette 0.52 ServerErrorMiddleware re-raises exceptions in ASGITransport test mode"
  - "try/except wraps entire remote provider loop body including DB upsert — ensures any error during result handling also degrades gracefully per STAB-04 scope"

patterns-established:
  - "Exception handler pattern: @app.exception_handler(Exception) placed immediately after app=FastAPI() and before include_router calls"
  - "Test exception handler pattern: TestClient(app, raise_server_exceptions=False) — standard Starlette 0.52+ approach"

requirements-completed: [REVIEW-02]

# Metrics
duration: 3min
completed: 2026-03-30
---

# Phase 18 Plan 02: Stability Blockers Summary

**Global FastAPI exception handler (STAB-01/02) and per-provider loop guards (STAB-04) resolving all three stability blockers with 3 regression tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-30T00:19:21Z
- **Completed:** 2026-03-30T00:23:01Z
- **Tasks:** 2
- **Files modified:** 3 (main.py, services/geocoding.py, tests/test_exception_handling.py)

## Accomplishments

- Added `@app.exception_handler(Exception)` catch-all handler in `main.py` — any unhandled exception from geocode/validate/health endpoints now returns `{"detail": "Internal server error"}` with status 500 instead of raw traceback (resolves STAB-01 and STAB-02)
- Wrapped both local provider loop and remote provider loop bodies in per-provider `try/except Exception` in `_legacy_geocode` — a single provider failure logs a warning and continues to the next provider without crashing the entire request (resolves STAB-04)
- Removed unused `CascadeResult` import from `services/geocoding.py` (ruff F401 fix)
- Created `tests/test_exception_handling.py` with 3 targeted regression tests confirming global exception handler returns structured 500 JSON for RuntimeError, SQLAlchemy-style errors, and validate-path errors

## Task Commits

1. **Task 1: Add global exception handler and guard legacy provider loops** - `319ed4a` (fix)
2. **Task 2: Write targeted stability regression tests** - `0c0a18a` (fix/test)

**Plan metadata:** (included in final docs commit)

## Files Created/Modified

- `src/civpulse_geo/main.py` — Added `Request` and `JSONResponse` imports; added `@app.exception_handler(Exception)` handler block
- `src/civpulse_geo/services/geocoding.py` — Removed unused `CascadeResult` import; wrapped local provider loop body in try/except; wrapped remote provider loop body in try/except
- `tests/test_exception_handling.py` — New file: 3 stability regression tests

## Decisions Made

- **TestClient instead of AsyncClient for exception handler tests:** Starlette 0.52's `ServerErrorMiddleware` re-raises exceptions in `ASGITransport` test mode before they reach the exception handler. `TestClient(app, raise_server_exceptions=False)` is the correct and standard pattern for testing generic exception handlers. The sync client approach is equivalent in correctness for these tests.
- **try/except wraps entire loop iteration body:** Per STAB-04 scope, the entire iteration body (including DB upsert for remote providers) is wrapped — not just the `provider.geocode()` call — to ensure any exception during result handling also degrades gracefully.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AsyncClient+ASGITransport test pattern fails for Exception handler testing in Starlette 0.52**
- **Found during:** Task 2 (Write targeted stability regression tests)
- **Issue:** The plan specified tests using `AsyncClient(transport=ASGITransport(app=app))`. In Starlette 0.52+, `ServerErrorMiddleware` re-raises generic Python exceptions in ASGI test mode, preventing the `@app.exception_handler(Exception)` handler from sending a response — tests raised `RuntimeError` instead of receiving 500 JSON.
- **Fix:** Replaced `AsyncClient+ASGITransport` with `TestClient(app, raise_server_exceptions=False)` — the standard Starlette pattern for testing exception handlers. Tests changed from `@pytest.mark.asyncio async def test_...` to sync `def test_...` (no pytest-asyncio needed, simpler).
- **Files modified:** `tests/test_exception_handling.py`
- **Verification:** `uv run pytest tests/test_exception_handling.py -v` → 3 passed. Full suite: 507 passed, 11 pre-existing CLI fixture failures unchanged.
- **Committed in:** `0c0a18a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was necessary for tests to pass. No scope creep. Exception handler behavior verified identically — `TestClient(raise_server_exceptions=False)` is the correct test approach for this FastAPI/Starlette version.

## Issues Encountered

None beyond the test framework behavior deviation documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Stability blockers STAB-01, STAB-02, STAB-04 resolved and regression-tested
- Full test suite: 507 passing (504 pre-existing + 3 new), 11 pre-existing CLI fixture failures unchanged
- ruff check on all modified files: clean
- Ready for Plan 03 (performance blockers)

---

*Phase: 18-code-review*
*Completed: 2026-03-30*
