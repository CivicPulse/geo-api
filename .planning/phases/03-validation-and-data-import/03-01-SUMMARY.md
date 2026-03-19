---
phase: 03-validation-and-data-import
plan: "01"
subsystem: database
tags: [scourgify, usps, validation, alembic, orm, sqlalchemy, tdd]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Base ORM, TimestampMixin, Address model, initial Alembic migration b98c26825b02
  - phase: 02-geocoding-service
    provides: GeocodingResult ORM pattern, providers/schemas.py structure, ValidationProvider ABC

provides:
  - ValidationResult dataclass in providers/schemas.py with 10 fields
  - ValidationResult ORM model (validation_results table, uq_validation_address_provider)
  - Alembic migration a3d62fae3d64 chains from b98c26825b02
  - ScourgifyValidationProvider implementing ValidationProvider ABC
  - 39 new unit tests covering dataclass, ORM, migration, and provider behaviors

affects:
  - 03-02 (ValidationService + router will import ScourgifyValidationProvider and ValidationResultORM)
  - 03-03 (data import will use ValidationResult ORM for storage)

# Tech tracking
tech-stack:
  added: []  # scourgify already in pyproject.toml; no new dependencies
  patterns:
    - TDD red-green cycle for both ORM and provider layers
    - ValidationResult dataclass mirrors GeocodingResult pattern from providers/schemas.py
    - ValidationResult ORM mirrors GeocodingResult ORM (Base+TimestampMixin, UniqueConstraint, FK to addresses)
    - Alembic autogenerate + manual cleanup of PostGIS TIGER DROP statements

key-files:
  created:
    - src/civpulse_geo/providers/scourgify.py
    - src/civpulse_geo/models/validation.py
    - alembic/versions/a3d62fae3d64_add_validation_results_table.py
    - tests/test_scourgify_provider.py
    - tests/test_validation_model.py
  modified:
    - src/civpulse_geo/providers/schemas.py
    - src/civpulse_geo/models/__init__.py

key-decisions:
  - "ValidationResultORM alias in models/__init__.py avoids collision with ValidationResult dataclass in providers/schemas.py"
  - "postal_code is String(10) not String(5) — scourgify preserves ZIP+4 (e.g. '31201-5678') in output"
  - "Alembic autogenerate includes PostGIS TIGER extension table DROPs; manually removed all — only create_table('validation_results') remains"
  - "ScourgifyValidationProvider.validate() is async even though scourgify is synchronous — consistent with ValidationProvider ABC contract; no asyncio.to_thread() needed for CPU-only offline logic"

patterns-established:
  - "ValidationProvider ABC implementations return typed ValidationResult dataclass (not dict)"
  - "Alembic autogenerate requires manual PostGIS TIGER cleanup before commit — documented as recurring step"
  - "TDD: write test file first (confirm ImportError), then implement, confirm all pass"

requirements-completed: [VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06]

# Metrics
duration: 12min
completed: 2026-03-19
---

# Phase 3 Plan 1: ValidationResult data layer and ScourgifyValidationProvider Summary

**ValidationResult dataclass + ORM with Alembic migration, and ScourgifyValidationProvider normalizing US addresses to USPS Pub 28 via offline scourgify library**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-19T14:15:00Z
- **Completed:** 2026-03-19T14:27:00Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 7

## Accomplishments

- ValidationResult dataclass added to providers/schemas.py with all 10 fields (normalized_address, address_line_1, address_line_2, city, state, postal_code, confidence, delivery_point_verified, provider_name, original_input)
- ValidationResult ORM model (validation_results table) with uq_validation_address_provider UniqueConstraint and FK to addresses, postal_code String(10) for ZIP+4 support
- Alembic migration a3d62fae3d64 chains from b98c26825b02, manually cleaned to contain only create_table/drop_table for validation_results
- ScourgifyValidationProvider implements ValidationProvider ABC — normalizes Road->RD, Georgia->GA, extracts APT/unit to address_line_2, preserves ZIP+4, confidence=1.0, delivery_point_verified=False, raises ProviderError for PO Box/unparseable input
- 39 new unit tests via TDD (23 for model layer, 16 for provider) — all 129 tests pass (90 prior + 39 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: ValidationResult dataclass, ORM model, and Alembic migration** - `8e8c92a` (feat)
2. **Task 2: ScourgifyValidationProvider with unit tests** - `2f84459` (feat)

_Note: Both tasks used TDD (red test commit implicit in workflow, green commit is the task commit)_

## Files Created/Modified

- `src/civpulse_geo/providers/schemas.py` - Added ValidationResult dataclass (10 fields) below GeocodingResult
- `src/civpulse_geo/models/validation.py` - New ORM model for validation_results table
- `src/civpulse_geo/models/__init__.py` - Added ValidationResultORM alias import and __all__ entry
- `alembic/versions/a3d62fae3d64_add_validation_results_table.py` - Clean migration, no PostGIS table references
- `src/civpulse_geo/providers/scourgify.py` - ScourgifyValidationProvider implementation
- `tests/test_validation_model.py` - 23 tests for dataclass fields, ORM structure, migration file
- `tests/test_scourgify_provider.py` - 16 tests for provider behaviors per VAL-01 through VAL-06

## Decisions Made

- **ValidationResultORM alias** — import as alias in models/__init__.py to avoid name collision with ValidationResult dataclass in providers/schemas.py. Plan specified this pattern explicitly.
- **postal_code String(10)** — scourgify returns full ZIP+4 string (e.g. "31201-5678") so String(10) not String(5) is required. Plan specified this.
- **Alembic TIGER cleanup** — autogenerate includes DROP statements for PostGIS TIGER extension tables. Manually replaced entire migration body with only the validation_results create/drop. This matches STATE.md decision from Phase 1.
- **async validate() with synchronous scourgify** — kept async per ValidationProvider ABC contract even though normalize_address_record() is sync. No asyncio.to_thread() needed (no I/O).

## Deviations from Plan

None - plan executed exactly as written. Migration cleanup was anticipated and documented in STATE.md decisions.

## Issues Encountered

- Pre-existing test failure in tests/test_import_cli.py (TestImportGISCommand::test_import_geojson_cli_runs) — patches civpulse_geo.cli.create_engine which doesn't exist. Confirmed pre-existing before my changes via git stash check. Out of scope per deviation scope boundary rules. Logged to deferred-items.

## User Setup Required

None - no external service configuration required. scourgify is offline pure-Python.

## Next Phase Readiness

- Plan 03-02 (ValidationService + router) can import ScourgifyValidationProvider and ValidationResultORM directly
- ScourgifyValidationProvider is fully tested and confirmed to handle USPS normalization behaviors
- Migration a3d62fae3d64 ready to apply to production DB when deploying Plan 03-02

---
*Phase: 03-validation-and-data-import*
*Completed: 2026-03-19*
