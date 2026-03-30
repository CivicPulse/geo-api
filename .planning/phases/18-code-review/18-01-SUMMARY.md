---
phase: 18-code-review
plan: "01"
subsystem: api
tags: [security, pydantic, fastapi, input-validation, ruff]

# Dependency graph
requires:
  - phase: 17-tech-debt-resolution
    provides: Stable codebase baseline with tech debt resolved
provides:
  - Hardcoded credential placeholders in config.py (SEC-01)
  - Input length constraints on all address fields in all schemas (SEC-02)
  - Coordinate range validation on SetOfficialRequest (SEC-03)
  - Provider name allowlist on GET /geocode/{hash}/providers/{name} (SEC-04)
  - 9 targeted security regression tests
  - 3 ruff F401 unused import fixes in security-owned files
affects: [19-dockerfile-db, 20-health-k8s, 21-cicd, 23-e2e-validation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic Field constraints for input validation (min_length, max_length, ge, le)"
    - "Module-level frozenset allowlist for path parameter validation before service layer"
    - "CHANGEME placeholder pattern for required env-var credentials"

key-files:
  created: []
  modified:
    - src/civpulse_geo/config.py
    - src/civpulse_geo/schemas/geocoding.py
    - src/civpulse_geo/schemas/validation.py
    - src/civpulse_geo/schemas/batch.py
    - src/civpulse_geo/api/geocoding.py
    - src/civpulse_geo/normalization.py
    - src/civpulse_geo/providers/macon_bibb.py
    - src/civpulse_geo/providers/nad.py
    - tests/test_geocoding_api.py
    - tests/test_validation_api.py

key-decisions:
  - "CHANGEME placeholders in config.py defaults — allows Settings() instantiation without .env while making required env vars obvious; using Field(required=...) would break pytest"
  - "KNOWN_PROVIDERS as module-level frozenset — allowlist evaluated before service layer, sanitized error message prevents input reflection in 404 detail"
  - "Per-item Annotated[str, Field(...)] in batch list fields — Pydantic v2 pattern for per-item constraints in list types"

patterns-established:
  - "SEC pattern: Pydantic Field constraints are the first line of defense; schema validation fires before endpoint body runs"
  - "SEC pattern: Path parameters with known enumeration must be validated against allowlist before service dispatch"
  - "SEC pattern: Error messages must not reflect user-supplied values back in responses"

requirements-completed: [REVIEW-01]

# Metrics
duration: 3min
completed: 2026-03-30
---

# Phase 18 Plan 01: Security Audit and Fix Summary

**4 security blockers resolved via Pydantic field constraints and provider allowlist: hardcoded DB credentials removed (CHANGEME placeholders), all address inputs capped at 500 chars, lat/lng range validated, unknown provider names rejected before service dispatch**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-30T00:19:21Z
- **Completed:** 2026-03-30T00:22:45Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- SEC-01: Replaced `civpulse:civpulse` hardcoded credentials in config.py with `CHANGEME:CHANGEME` placeholders — no real credentials in code
- SEC-02: Added `max_length=500` to all address string inputs across geocoding, validation, and batch schemas; `min_length=1` on required fields; per-item Annotated constraints in batch list types
- SEC-03: Added `ge=-90.0, le=90.0` / `ge=-180.0, le=180.0` to SetOfficialRequest latitude/longitude fields — out-of-range coordinates rejected at 422 before service layer
- SEC-04: Added `KNOWN_PROVIDERS` frozenset allowlist in api/geocoding.py; unknown provider returns 404 with "Unknown provider" (input not reflected); existing ValueError changed to sanitized message
- Ruff: Removed 3 unused imports (unicodedata from normalization.py, usaddress from macon_bibb.py and nad.py)
- 9 targeted security regression tests added; all 534 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix all security blockers (SEC-01 through SEC-04) and clean ruff lint** - `57decf2` (fix)
2. **Task 2: Write targeted security regression tests and verify full suite** - `1520fbf` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/civpulse_geo/config.py` - CHANGEME placeholders for database_url and database_url_sync defaults
- `src/civpulse_geo/schemas/geocoding.py` - Field constraints: address min/max_length, latitude/longitude ge/le bounds
- `src/civpulse_geo/schemas/validation.py` - Field constraints on all ValidateRequest fields
- `src/civpulse_geo/schemas/batch.py` - Annotated per-item constraints on batch address lists; typing.Annotated import added
- `src/civpulse_geo/api/geocoding.py` - KNOWN_PROVIDERS frozenset; allowlist check before service dispatch; sanitized error message
- `src/civpulse_geo/normalization.py` - Removed unused `import unicodedata`
- `src/civpulse_geo/providers/macon_bibb.py` - Removed unused `import usaddress`
- `src/civpulse_geo/providers/nad.py` - Removed unused `import usaddress`
- `tests/test_geocoding_api.py` - 7 security regression tests + pre-existing ruff lint fixes (F401, E402)
- `tests/test_validation_api.py` - 2 security regression tests + pre-existing ruff lint fixes (F401)

## Decisions Made

- CHANGEME placeholders instead of required fields — `Field(...)` with no default would cause `Settings()` instantiation failure in tests that don't load `.env`. CHANGEME is clearly non-functional but allows import-time instantiation.
- `KNOWN_PROVIDERS` as module-level frozenset not request-time — providers are statically defined at startup; frozenset lookup is O(1) and avoids app.state access at validation time.
- Sanitized ValueError catch — changed `detail=str(e)` to a fixed string to prevent service error messages (which may contain user input) from being reflected in HTTP responses.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Fixed pre-existing ruff lint issues in test files**
- **Found during:** Task 2 (test file ruff check required by verification spec)
- **Issue:** Pre-existing F401 unused imports and E402 mid-file import in test_geocoding_api.py and test_validation_api.py caused `uv run ruff check` to fail — which is a plan acceptance criterion
- **Fix:** Removed unused imports (get_db, GeocodeResponse, settings, CascadeResult, Address from geocoding test; AsyncClient, ASGITransport, get_db, ValidationResultSchema from validation test). Moved mid-file `from unittest.mock import patch as _api_patch` to top-level alias `_api_patch = patch`.
- **Files modified:** tests/test_geocoding_api.py, tests/test_validation_api.py
- **Verification:** `uv run ruff check tests/test_geocoding_api.py tests/test_validation_api.py` exits 0
- **Committed in:** 1520fbf (Task 2 commit)

**2. [Rule 1 - Bug] Fixed tests for boundary values and known provider (service layer mock missing)**
- **Found during:** Task 2 (test run)
- **Issue:** `test_set_official_accepts_boundary_values` and `test_get_provider_allows_known_provider` reached the real service layer via mock db session, causing internal Pydantic validation errors from MagicMock values. Tests expected 404/200 but got 500.
- **Fix:** Added `patch("...GeocodingService.set_official", side_effect=ValueError(...))` and `patch("...GeocodingService.get_by_provider", side_effect=ValueError(...))` to simulate realistic not-found behavior.
- **Files modified:** tests/test_geocoding_api.py
- **Verification:** Both tests pass; behavior matches plan intent (404 != 422)
- **Committed in:** 1520fbf (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both auto-fixes were necessary to meet the plan's verification requirements. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Known Stubs

None — all security fixes are fully wired. No placeholder values flow to any output.

## Next Phase Readiness

- SEC-01 through SEC-04 resolved — API input surface is hardened against oversized input, out-of-range coordinates, and unknown path parameters
- Ruff clean on all security-owned files
- Full test suite green (534 passed, 2 skipped)
- Ready for Phase 18 Plans 02 and 03 (stability and performance review)

---
*Phase: 18-code-review*
*Completed: 2026-03-30*
