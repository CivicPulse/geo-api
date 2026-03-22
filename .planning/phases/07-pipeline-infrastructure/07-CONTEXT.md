# Phase 7: Pipeline Infrastructure - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Direct-return pipeline bypass for local providers, provider ABC extension with `is_local` property, Alembic migrations for OpenAddresses and NAD staging tables, and CLI import command stubs (load-oa, load-nad). No actual provider implementations — those come in Phases 8-10.

</domain>

<decisions>
## Implementation Decisions

### Pipeline bypass behavior
- Per-provider routing: each provider is routed independently — remote providers go through cache, local providers bypass cache. Mixed requests return results from both paths together
- Local provider results ARE eligible for OfficialGeocoding auto-set, same as remote
- Local providers still create/find an Address record (upsert to addresses table) — only geocoding_results/validation_results writes are skipped
- Only return results from explicitly requested providers — no auto-including cached remote results

### Staging table design
- Claude's discretion on provider-specific vs shared columns (choose based on source data formats)
- PostGIS Geography(POINT, 4326) column for spatial data — consistent with existing geocoding_results pattern
- GiST spatial index + composite B-tree index on (state, zip_code, street_name) for address-matching queries
- Source-specific hash column for deduplication: OA uses its built-in hash field, NAD uses composite hash from address components. Enables upsert-on-conflict for idempotent reloads

### CLI import commands
- Upsert (ON CONFLICT UPDATE) when reloading data — safe for incremental loads and re-runs
- Progress reporting via `rich` progress bar (override of "no new dependencies" constraint — user decision)
- load-oa accepts a single .geojson.gz file path (users loop in shell for multiple files)
- load-nad accepts a single NAD TXT file path
- CLI commands use synchronous engine (psycopg2) following existing import pattern

### Provider ABC contract
- `is_local` added as a concrete property with default `False` on both GeocodingProvider and ValidationProvider ABCs — existing providers need zero changes
- Local providers receive async_sessionmaker at construction time for querying staging tables — ABC method signatures unchanged
- Async sessions (asyncpg) for local providers, matching the async service layer
- Phase 7 only modifies ABCs and service layer — no skeleton provider classes

### Claude's Discretion
- Exact staging table column choices (provider-specific vs normalized)
- Alembic migration implementation details
- Service layer refactoring approach for the bypass path
- Test fixtures and factory patterns

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pipeline and provider architecture
- `src/civpulse_geo/providers/base.py` — Provider ABCs (GeocodingProvider, ValidationProvider) to be extended with is_local
- `src/civpulse_geo/providers/registry.py` — load_providers() function, provider discovery pattern
- `src/civpulse_geo/services/geocoding.py` — Geocoding service with cache-first pipeline (bypass target)
- `src/civpulse_geo/services/validation.py` — Validation service with cache-first pipeline (bypass target)

### Existing provider implementations (reference patterns)
- `src/civpulse_geo/providers/census.py` — Remote geocoding provider example
- `src/civpulse_geo/providers/scourgify.py` — Offline validation provider example
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult and ValidationResult dataclasses

### Database and migrations
- `src/civpulse_geo/models/geocoding.py` — GeocodingResult model with Geography column pattern
- `src/civpulse_geo/models/validation.py` — ValidationResult model
- `src/civpulse_geo/models/address.py` — Address model with address_hash pattern
- `alembic/versions/` — Existing migrations (initial schema + validation_results)

### CLI
- `src/civpulse_geo/cli/__init__.py` — Existing CLI app with import command (sync engine + raw SQL pattern)

### Requirements
- `.planning/REQUIREMENTS.md` — PIPE-01 through PIPE-06 requirements for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `providers/base.py` GeocodingProvider and ValidationProvider ABCs: extend with is_local property
- `providers/registry.py` load_providers(): reuse for registering local providers
- `providers/schemas.py` GeocodingResult/ValidationResult dataclasses: local providers will return these same types
- `models/address.py` Address model + address_hash: local providers reuse address normalization path
- `cli/__init__.py` Typer app + sync engine pattern: mirror for load-oa and load-nad commands

### Established Patterns
- PostGIS Geography(POINT, 4326) with GiST index — used in geocoding_results and admin_overrides
- SHA-256 canonical address hash for O(1) lookups
- ON CONFLICT upsert for idempotent writes
- Synchronous engine (psycopg2) for CLI bulk operations
- Async engine (asyncpg) for API request path
- Provider instantiation in FastAPI lifespan context manager

### Integration Points
- `main.py` lifespan: where local providers would be registered alongside existing providers
- Service layer geocode/validate methods: where is_local check routes to bypass path
- Alembic env.py: configured for both async and sync database URLs

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose `rich` for CLI progress bars despite earlier "no new dependencies" research decision — this is an override
- OA hash field comes built-in from the OpenAddresses data format; NAD needs a computed hash

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-pipeline-infrastructure*
*Context gathered: 2026-03-22*
