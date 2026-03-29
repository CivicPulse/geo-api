# Phase 9: Tiger Provider - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement PostGIS Tiger geocoding and validation providers that call the Tiger geocoder SQL functions (`geocode()` and `normalize_address()`), plus a `setup-tiger` CLI command that installs Tiger extensions and loads TIGER/Line data per state. Providers implement existing GeocodingProvider/ValidationProvider ABCs with `is_local=True`. Provider registration is conditional on Tiger extension availability at startup.

</domain>

<decisions>
## Implementation Decisions

### Graceful degradation
- When Tiger extensions are installed but no data is loaded for the requested state: return NO_MATCH result (confidence=0.0, location_type=None) — consistent with Census and OA miss behavior
- When Tiger extensions are NOT installed: do not register the provider at all. Log a warning at startup. Provider does not appear in the provider list (per TIGR-04)
- Extension check at startup via `SELECT * FROM pg_available_extensions WHERE name = 'postgis_tiger_geocoder'` — check only the main extension (CASCADE dependencies install automatically)
- Extension check runs during FastAPI lifespan, before provider registration
- Tiger `geocode()` returns SETOF: take best result only (`LIMIT 1 ORDER BY rating ASC`)

### Setup script (setup-tiger)
- Full automation: CLI command that (1) installs extensions via SQL, (2) calls `Loader_Generate_Script()` for specified state(s), (3) executes the generated script to download and load data
- Takes state FIPS codes as arguments: e.g., `setup-tiger 13` for Georgia, `setup-tiger 13 01` for GA + AL
- Fully idempotent: `CREATE EXTENSION IF NOT EXISTS`, skip already-loaded states, safe to re-run
- Runs inside Docker container (postgis/postgis image has shp2pgsql and wget available) — invoked via `docker compose exec`

### Confidence and result mapping
- Linear mapping: `confidence = (100 - rating) / 100` where Tiger rating 0 = best match (confidence 1.0), rating 100 = worst match (confidence 0.0). Research phase must verify this against PostGIS docs.
- `location_type` = RANGE_INTERPOLATED for all Tiger geocoding results — Tiger interpolates along street ranges, does not provide rooftop/parcel precision
- Validation via `normalize_address()` returns address components only, no coordinates — consistent with scourgify validation pattern

### Provider naming
- `provider_name` = "postgis_tiger" for both geocoding and validation providers
- `raw_response` contains full norm_addy fields (address, predirAbbrev, streetName, streetTypeAbbrev, location, stateAbbrev, zip, zip4, parsed) plus rating integer

### Testing strategy
- Unit tests: mock async session to return fake geocode()/normalize_address() result tuples — same pattern as OA provider tests
- Integration tests: marked with `@pytest.mark.tiger`, skipped unless Tiger data is present
- Unit mocks always run; integration tests are optional

### Docker integration
- docker-compose.yml updated to auto-install Tiger extensions AND load Georgia (FIPS 13) data on first startup
- GA chosen for consistency with existing Bibb County seed data and OA test data
- Tiger data for GA is ~200MB download — first startup will be slower

### Claude's Discretion
- Exact SQL query construction for geocode() and normalize_address() calls
- Whether to create a shared base class for Tiger geocoding+validation or keep them separate
- norm_addy field extraction approach (composite type unpacking vs string parsing)
- Setup script internal implementation (subprocess vs psycopg2 for shell script execution)
- Docker init script implementation details
- Exact test fixture design

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider architecture (follow OA pattern)
- `src/civpulse_geo/providers/openaddresses.py` — Local provider reference implementation (is_local=True, async_sessionmaker injection, **kwargs in geocode())
- `src/civpulse_geo/providers/base.py` — GeocodingProvider and ValidationProvider ABCs with is_local property
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult and ValidationResult dataclasses (target return types)
- `src/civpulse_geo/providers/exceptions.py` — ProviderError hierarchy for error handling

### Service layer integration
- `src/civpulse_geo/services/geocoding.py` — is_local bypass logic (local_providers dict, no DB write path)
- `src/civpulse_geo/services/validation.py` — Validation service bypass path
- `src/civpulse_geo/main.py` — FastAPI lifespan: provider registration (Tiger added conditionally alongside OA)

### CLI
- `src/civpulse_geo/cli/__init__.py` — Existing CLI app with load-oa command pattern (sync engine + Typer)

### Testing
- `tests/test_oa_provider.py` — Mock async_sessionmaker pattern (_make_session_factory helper)

### Docker
- `docker-compose.yml` — Uses postgis/postgis:17-3.5 image

### Prior phase context
- `.planning/phases/07-pipeline-infrastructure/07-CONTEXT.md` — Pipeline bypass decisions, is_local pattern
- `.planning/phases/08-openaddresses-provider/08-CONTEXT.md` — Local provider implementation pattern, session_factory injection

### Requirements
- `.planning/REQUIREMENTS.md` — TIGR-01 through TIGR-05 requirements for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `providers/openaddresses.py` OAGeocodingProvider/OAValidationProvider: Reference pattern for local provider with async_sessionmaker injection, is_local=True, **kwargs in geocode()
- `providers/schemas.py` GeocodingResult/ValidationResult: Return types for both providers
- `providers/exceptions.py` ProviderError: Wrap SQL errors for clean propagation
- `tests/test_oa_provider.py` _make_session_factory(): Mock async session pattern reusable for Tiger tests
- `database.py` AsyncSessionLocal: async_sessionmaker instance passed to local providers

### Established Patterns
- Local providers registered directly in lifespan (not via load_providers) because they require async_sessionmaker
- ST_Y/ST_X for lat/lng extraction from geography columns (used in OA provider)
- Provider returns NO_MATCH with confidence=0.0 on miss (not exception)
- Synchronous engine (psycopg2) for CLI operations (setup-tiger script)
- Async engine (asyncpg) for API path (provider queries)

### Integration Points
- `main.py` lifespan: Conditional Tiger registration after pg_available_extensions check
- `cli/__init__.py`: Add setup-tiger command alongside existing load-oa and load-nad
- `docker-compose.yml`: Add init script for Tiger extension installation and GA data loading

</code_context>

<specifics>
## Specific Ideas

- Tiger provider is fundamentally different from OA/NAD: it calls SQL functions, not queries against a staging table
- The postgis/postgis:17-3.5 Docker image availability of Tiger extensions must be verified during research (STATE.md blocker)
- setup-tiger runs inside the Docker container to leverage built-in shp2pgsql and wget
- Georgia (FIPS 13) auto-loaded in Docker for consistency with Bibb County test addresses

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-tiger-provider*
*Context gathered: 2026-03-24*
