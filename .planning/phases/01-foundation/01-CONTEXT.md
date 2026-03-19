# Phase 1: Foundation - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

PostGIS schema, canonical address normalization function, provider plugin contract (GeocodingProvider and ValidationProvider ABCs), and project scaffolding (FastAPI app, Docker Compose, health endpoint). No geocoding logic, no validation logic, no external provider calls — those ship in Phase 2 and 3.

Requirements covered: INFRA-01, INFRA-02, INFRA-05, INFRA-07

</domain>

<decisions>
## Implementation Decisions

### Canonical Key Strategy
- Full USPS standardization for normalization: suffixes (Street->ST), directionals (North->N), unit designators (Apartment->APT), state names (Georgia->GA), plus lowercasing and whitespace normalization
- Two-tier key with inheritance for unit numbers: base address (no unit) is the geocoding cache key sent to external providers; individual units are stored as separate address records that inherit the geocode from their base address unless specifically overridden by an admin
- Rationale for unit inheritance: large apartment complexes may span zones, so units get their own records that can be moved independently, but default to the building's geocode when no override exists
- ZIP5 only in canonical key — ZIP+4 varies by unit/floor and would split cache entries unnecessarily
- Key format: store both the normalized string (human-readable, debuggable) AND a hash column for fast lookups

### Schema Design
- Separate `official_geocoding` table linking address to its official result — clearer audit boundary, extra join on lookup but clean separation
- Separate `admin_overrides` table for admin-set custom coordinates — distinct from provider results, creates a clear query priority chain: admin_overrides > official_geocoding > provider results
- Addresses table stores parsed components (street, city, state, zip, unit) plus the original freeform input — enables structured queries like "all addresses on Main St" and structured validation input in Phase 3
- Location type as PostgreSQL enum on geocoding_results: ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE — enforced at DB level, maps to GEO-01
- created_at and updated_at timestamps with database defaults on all tables
- PostGIS `geography(Point, 4326)` column type (locked from project setup)
- Addresses and geocoding_results as separate tables (locked from project setup)

### Plugin Contract Shape
- Async methods (`async def geocode(...)`) — FastAPI is async-native, provider calls are I/O-bound HTTP, enables concurrent fan-out to multiple providers in Phase 2
- Custom exception hierarchy for error signaling: ProviderError base with subtypes ProviderNetworkError, ProviderAuthError, ProviderRateLimitError — framework catches and handles each differently (retry vs fail vs degrade)
- Structured result dataclass (GeocodingResult) with typed fields: lat, lng, location_type, confidence, raw_response, provider_name — enforces consistency across all providers
- Explicit provider registry via config (dict/list mapping provider names to classes) — simple, predictable, easy to enable/disable individual providers

### Project Scaffolding
- `src/` layout: `src/civpulse_geo/` with `models/`, `providers/`, `api/`, `cli/` subdirectories — prevents import confusion, standard for modern Python with uv
- Pydantic Settings for configuration with .env file support — type-safe, validates on startup, integrates with FastAPI dependency injection
- Seed data: both real Bibb County GIS samples (from SAMPLE_Address_Points.geojson) and synthetic edge-case addresses (apartments, PO boxes, ambiguous inputs)
- pytest with conftest.py fixtures for database sessions, test client, and provider mocks; optional Docker test DB via environment variable (TEST_DATABASE_URL) for integration tests against real PostGIS

### Claude's Discretion
- Exact Alembic migration structure and naming
- Specific index choices beyond primary/foreign keys
- Health endpoint implementation details
- Docker Compose service naming and networking
- Exact hash algorithm for canonical key hash column
- pytest fixture organization and conftest structure

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Core value proposition, constraints, tech stack decisions, key decisions table
- `.planning/REQUIREMENTS.md` — Full v1 requirement list with traceability matrix; Phase 1 covers INFRA-01, INFRA-02, INFRA-05, INFRA-07
- `.planning/ROADMAP.md` — Phase goals, success criteria, dependency graph

### Data files
- `data/SAMPLE_Address_Points.geojson` — Sample Bibb County GIS data for seed data generation
- `data/SAMPLE_Address_Points.shp.zip` — Sample SHP format for testing import in Phase 3
- `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml` — Sample KML format for testing import in Phase 3

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing code — greenfield project. All code will be created in this phase.

### Established Patterns
- CivPulse ecosystem uses: Python, FastAPI, Loguru, Typer — this API must follow the same stack
- `uv` for all Python environment and package management

### Integration Points
- Other CivPulse services (run-api, vote-api) will consume this API over HTTP
- No authentication layer — internal service behind network security
- Docker Compose must provide PostgreSQL/PostGIS + API for local development

</code_context>

<specifics>
## Specific Ideas

- Unit number handling inspired by real-world apartment complex zoning: units inherit building geocode by default but can be individually overridden when they span different zones
- Query priority chain for official result: admin_overrides (highest) > official_geocoding > provider results (fallback)
- Testing should support both fast mocked-DB fixtures and optional real PostGIS via Docker for integration tests

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-19*
