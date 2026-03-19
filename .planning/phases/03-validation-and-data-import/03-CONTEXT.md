# Phase 3: Validation and Data Import - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

USPS address validation API endpoints and a Bibb County GIS CLI import tool. Callers can validate/standardize US addresses and receive USPS-normalized candidates with confidence scores. The CLI imports county GIS data files (GeoJSON, KML, SHP) as a first-class provider whose results serve as the default official geocode when no admin override exists. Batch endpoints ship in Phase 4.

Requirements covered: VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, DATA-01, DATA-02, DATA-03, DATA-04

</domain>

<decisions>
## Implementation Decisions

### Validation Provider Strategy
- Scourgify-only for v1 — no external USPS v3 API dependency; avoids the known OAuth2 breaking-change risk flagged in STATE.md
- USPS v3 adapter deferred to a future phase as a second validation provider
- ZIP+4 delivery point validation (VAL-06) returns `delivery_point_verified: false` in scourgify-only mode — callers know the address is standardized but not delivery-confirmed; future USPS provider upgrades this to `true`
- Unparseable addresses return HTTP 422 error — invalid input is an error, not a low-confidence result; cleaner API contract
- Validation endpoint is independent from geocoding — no coupling, no optional geocode flag; callers geocode separately if needed

### Validation Response Design
- Structured field input (VAL-03) is concatenated to a freeform string and run through the same scourgify pipeline as freeform input (VAL-02) — one code path, structured input is a caller convenience
- Full structured response per candidate: `normalized_address` (full string) + all parsed components (`street_number`, `street_name`, `street_suffix`, `unit_type`, `unit_number`, `city`, `state`, `zip_code`, `zip_plus4`) + `confidence` + `delivery_point_verified` + `provider_name`
- Validation results cached in a `validation_results` table — same pattern as `geocoding_results`, prepares for future USPS API caching
- Single candidate from scourgify for v1 — the response schema supports a `candidates[]` array for future multi-candidate providers, but scourgify produces one normalized form

### GIS Import CLI Workflow
- CLI tool lives in `src/civpulse_geo/cli/` module — proper package location, importable, testable; Phase 1 context already planned this subdirectory
- Single `import` command auto-detects file format from extension (.geojson, .kml, .shp) — one command, multiple formats
- Uses appropriate parser per format: `json` for GeoJSON, `fiona`/`geopandas` for KML and SHP
- Summary output with counts after import: total records, inserted, updated (upserted), skipped (unparseable), errors — progress counter during import, Loguru for logging
- Hardcoded Bibb County field mapping: `FULLADDR`, `ADDNUM`, `STNAME`, `STTYPE`, `MUNICIPALITY`, `STATE`, `ZIPCODE` → address components; future counties get their own mapping
- Creates new Address records for GIS entries not already in the database — pre-populates the address cache so later queries hit immediately

### County Data as Default Official
- Auto-set `OfficialGeocoding` at import time: for each imported address, if no `OfficialGeocoding` row exists AND no `AdminOverride` exists, create an `OfficialGeocoding` row pointing to the `bibb_county_gis` geocoding result
- Never overwrite admin overrides on re-import — admin decisions are final; upsert updates the `bibb_county_gis` geocoding result but does not touch `OfficialGeocoding` or `AdminOverride` if they exist
- Priority chain preserved: `AdminOverride` > admin-set `OfficialGeocoding` > bibb_county_gis auto-set `OfficialGeocoding` > other provider results

### Claude's Discretion
- Exact `ValidationResult` dataclass field design for the provider contract
- Alembic migration structure for validation_results table
- Fiona/geopandas dependency choice for KML/SHP parsing
- Test fixture organization for validation and import tests
- CLI argument naming and help text
- Confidence score assignment for scourgify results

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Core value proposition, constraints, tech stack, key decisions table
- `.planning/REQUIREMENTS.md` — Full v1 requirement list; Phase 3 covers VAL-01–VAL-06 and DATA-01–DATA-04
- `.planning/ROADMAP.md` — Phase goals, success criteria, dependency graph

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` — Canonical key strategy, schema design decisions, plugin contract shape, project scaffolding decisions

### Data files
- `data/SAMPLE_Address_Points.geojson` — Sample Bibb County GIS data; field names define the hardcoded mapping (FULLADDR, ADDNUM, STNAME, etc.)
- `data/SAMPLE_Address_Points.shp.zip` — Sample SHP format for testing import
- `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml` — Sample KML format for testing import

### Code references
- `src/civpulse_geo/providers/base.py` — ValidationProvider ABC (async validate/batch_validate); the contract to implement
- `src/civpulse_geo/providers/census.py` — CensusGeocodingProvider; template for building the scourgify validation provider
- `src/civpulse_geo/services/geocoding.py` — GeocodingService; pattern for building ValidationService (cache-first, ORM upsert, provider loop)
- `src/civpulse_geo/normalization.py` — canonical_key() and parse_address_components(); reuse for validation input processing
- `src/civpulse_geo/models/geocoding.py` — GeocodingResult, OfficialGeocoding, AdminOverride models; pattern for validation_results table
- `src/civpulse_geo/api/geocoding.py` — Geocoding router; pattern for validation router (dependency injection, Pydantic transform)
- `scripts/seed.py` — Existing Typer + sync psycopg2 GIS import; template for the CLI import tool's upsert pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ValidationProvider` ABC in `providers/base.py` — async `validate()` and `batch_validate()` methods already defined; implement with scourgify
- `canonical_key()` and `parse_address_components()` in `normalization.py` — validation can reuse directly for input normalization and component extraction
- `Address` model with parsed components — structured validation input maps directly to existing fields
- `ProviderError` exception hierarchy — same exceptions apply to validation providers
- `load_providers()` registry — extend to load validation providers alongside geocoding providers
- `seed.py` GeoJSON loader — Bibb County GIS import can reuse the address parsing and PostGIS WKT construction patterns

### Established Patterns
- Cache-first service layer: normalize → find/create address → check cache → call provider → upsert result → commit
- Stateless services instantiated per-request with injected dependencies (db, providers, http_client)
- PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` for idempotent upserts
- PostGIS geography: `SRID=4326;POINT(longitude latitude)` — longitude first
- Unique constraint per provider per address: `(address_id, provider_name)` on results tables
- Sync psycopg2 for CLI tools, async asyncpg for API
- Typer for CLI entry points, Loguru for logging

### Integration Points
- `main.py` lifespan: register validation providers in `app.state` alongside geocoding providers
- `main.py` router: include validation router alongside geocoding router
- `OfficialGeocoding` table: CLI import tool creates rows pointing to bibb_county_gis results
- `GeocodingResult` table: CLI import inserts bibb_county_gis results using existing schema
- `Address` table: both validation and import create/find address records via canonical_key()

</code_context>

<specifics>
## Specific Ideas

- Validation endpoint mirrors geocoding pattern: POST /validate accepts address, returns structured candidates — familiar API shape for CivPulse service consumers
- CLI import tool should feel like a database migration: idempotent, safe to re-run, clear summary of what changed
- When scourgify normalizes an address, the validation response includes both the original input and the corrected output so callers can show "did you mean?" UI if needed
- The priority chain (admin > auto-official > providers) is the same query logic whether the official was set by an admin or auto-set during GIS import — no special-case code paths

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-validation-and-data-import*
*Context gathered: 2026-03-19*
