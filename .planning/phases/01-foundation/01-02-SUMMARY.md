---
phase: 01-foundation
plan: 02
subsystem: infra
tags: [python, scourgify, usaddress, abc, normalization, geocoding, sha256, pytest]

# Dependency graph
requires:
  - phase: 01-foundation/01-01
    provides: pyproject.toml with dependencies, src/civpulse_geo package skeleton

provides:
  - canonical_key() function with USPS Pub 28 normalization and SHA-256 hashing
  - parse_address_components() for structured address extraction
  - GeocodingProvider and ValidationProvider ABCs with async interface
  - GeocodingResult dataclass as canonical provider output type
  - ProviderError exception hierarchy (Network, Auth, RateLimit subtypes)
  - load_providers() registry with eager instantiation (surfaces errors at startup)
  - 52 tests covering INFRA-01 and INFRA-02 requirements

affects:
  - 01-foundation/01-03 (FastAPI app, health endpoint — imports providers package)
  - Phase 2 (Census Geocoder adapter implements GeocodingProvider ABC)
  - Phase 3 (USPS validation adapter implements ValidationProvider ABC)

# Tech tracking
tech-stack:
  added:
    - usaddress-scourgify (USPS Pub 28 address normalization, wraps usaddress)
    - loguru (structured logging in registry)
  patterns:
    - TDD with RED/GREEN commits per task
    - Two-tier canonical key: base address (no unit) for geocoding cache, ZIP5 only
    - Eager provider instantiation at startup for ABC enforcement at load time
    - Broad exception catch in normalization fallback to prevent user-facing errors

key-files:
  created:
    - src/civpulse_geo/normalization.py
    - src/civpulse_geo/providers/__init__.py
    - src/civpulse_geo/providers/base.py
    - src/civpulse_geo/providers/exceptions.py
    - src/civpulse_geo/providers/schemas.py
    - src/civpulse_geo/providers/registry.py
    - tests/__init__.py
    - tests/test_normalization.py
    - tests/test_providers.py
  modified: []

key-decisions:
  - "scourgify exception class is AddressNormalizationError not AddressNormalizeError — plan spec had wrong name, fixed inline"
  - "Fallback normalization catches all exceptions (not just scourgify-specific) to guarantee canonical_key never raises for any input"
  - "Unit stripping handles both comma-separated ('123 Main St, Apt 4B') and inline ('123 Main St Apt 4B') formats"
  - "load_providers accepts dict[str, type] not settings object — keeps registry pure and independently testable"

patterns-established:
  - "Pattern: canonical_key returns (normalized_str, sha256_hex) tuple — callers store normalized_str for debugging, hash for DB lookups"
  - "Pattern: ABC enforcement at startup via eager instantiation in load_providers() — not deferred to first call"
  - "Pattern: Unit designator stripping via _UNIT_KEYWORDS frozenset — matches all USPS Pub 28 Table C2 designators"

requirements-completed: [INFRA-01, INFRA-02]

# Metrics
duration: 4min
completed: 2026-03-19
---

# Phase 1 Plan 02: Normalization and Provider Contract Summary

**USPS Pub 28 canonical address normalization with SHA-256 hashing, GeocodingProvider/ValidationProvider ABCs, and eager-instantiation provider registry — 52 tests all passing**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-19T04:10:16Z
- **Completed:** 2026-03-19T04:14:52Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- canonical_key() normalizes suffixes, directionals, state names, ZIP+4, unit designators, and case — identical hash for semantically equivalent addresses
- GeocodingProvider and ValidationProvider ABCs enforce interface contract at instantiation (TypeError for any missing abstract method)
- load_providers() eagerly instantiates all configured providers at startup, surfacing missing-method errors before any HTTP request is served
- ProviderError hierarchy with typed subtypes (ProviderNetworkError, ProviderAuthError, ProviderRateLimitError) enables typed retry and fallback logic
- 52 tests across 2 test files covering every behavior specified in INFRA-01 and INFRA-02

## Task Commits

Each task was committed atomically:

1. **Task 1: Canonical address normalization** - `ed2fbca` (feat)
2. **Task 2: Provider plugin contract and registry** - `5a47e88` (feat)

_Note: TDD tasks — tests written first (RED), then implementation (GREEN), committed together._

## Files Created/Modified

- `src/civpulse_geo/normalization.py` - canonical_key() and parse_address_components() with scourgify and fallback
- `src/civpulse_geo/providers/__init__.py` - package exports for full provider contract surface
- `src/civpulse_geo/providers/base.py` - GeocodingProvider and ValidationProvider ABCs
- `src/civpulse_geo/providers/exceptions.py` - ProviderError base and Network/Auth/RateLimit subtypes
- `src/civpulse_geo/providers/schemas.py` - GeocodingResult dataclass
- `src/civpulse_geo/providers/registry.py` - load_providers() with eager instantiation
- `tests/__init__.py` - test package marker
- `tests/test_normalization.py` - 23 tests for INFRA-01
- `tests/test_providers.py` - 29 tests for INFRA-02

## Decisions Made

- scourgify's exception is `AddressNormalizationError`, not `AddressNormalizeError` as documented in the plan spec — fixed inline (Rule 1: bug fix)
- Fallback normalization catches `Exception` broadly (not just scourgify-specific errors) so `canonical_key()` is guaranteed never to raise for any input
- Unit stripping handles both comma-separated and inline formats to cover real-world address data variation
- `load_providers` takes `dict[str, type]` directly (not a settings object) — keeps the registry independently testable and free of app config coupling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wrong scourgify exception class name**
- **Found during:** Task 1 (normalization implementation — import error on test run)
- **Issue:** Plan spec referenced `AddressNormalizeError` from `scourgify.exceptions` — this class does not exist. The actual class is `AddressNormalizationError`.
- **Fix:** Updated import and all except clauses to use `AddressNormalizationError`. Also added `UnParseableAddressError` and `IncompleteAddressError` to the catch list for complete coverage.
- **Files modified:** `src/civpulse_geo/normalization.py`
- **Verification:** `uv run pytest tests/test_normalization.py -x` exits 0 (23 tests pass)
- **Committed in:** `ed2fbca` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in plan spec)
**Impact on plan:** Fix was necessary for the module to import. No scope creep.

## Issues Encountered

None beyond the scourgify exception name bug documented above.

## User Setup Required

None - no external service configuration required. All functionality is pure Python with no external API calls.

## Next Phase Readiness

- INFRA-01 canonical key is ready for use in the geocoding cache lookup in Phase 2
- INFRA-02 provider contract is the extension point for CensusGeocodingProvider (Phase 2) and USPSValidationProvider (Phase 3)
- Test infrastructure (tests/ directory, pytest config) is established for Phase 1 Plan 03 health endpoint tests
- No blockers

---
*Phase: 01-foundation*
*Completed: 2026-03-19*
