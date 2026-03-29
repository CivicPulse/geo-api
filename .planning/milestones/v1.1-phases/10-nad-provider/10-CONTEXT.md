# Phase 10: NAD Provider - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement NAD geocoding and validation providers that query the `nad_points` staging table, plus wire the `load-nad` CLI command to bulk-import the NAD r21 CSV dataset via PostgreSQL COPY. Providers implement existing GeocodingProvider/ValidationProvider ABCs with `is_local=True`. Provider registration is conditional on nad_points containing data at startup.

</domain>

<decisions>
## Implementation Decisions

### Placement-to-confidence mapping
- Mirror OA confidence tiers for consistency across providers
- Mapping:
  - "Structure - Rooftop" → ROOFTOP / 1.0
  - "Structure - Entrance" → ROOFTOP / 1.0
  - "Site" → APPROXIMATE / 0.8
  - "Property Access" → APPROXIMATE / 0.8
  - "Parcel - Other" → APPROXIMATE / 0.6
  - "Linear Geocode" → RANGE_INTERPOLATED / 0.5
  - "Parcel - Centroid" → GEOMETRIC_CENTER / 0.4
  - "Unknown" / empty / garbage / "Other" / "0" → APPROXIMATE / 0.1
- Garbage values (NatGrid coordinates leaked into Placement field) treated as Unknown — import them, don't skip
- location_type for Unknown is APPROXIMATE (not a new UNKNOWN type) — consistency with existing consumer handling

### Data format
- NAD r21 data is **CSV-delimited** (not pipe-delimited as previously documented) — confirmed by schema.ini `Format=CSVDelimited`
- File has UTF-8 BOM that must be stripped during parsing
- 60 columns in source, reduced to 10 staging table columns during import
- Fix existing docstrings and references that say "pipe-delimited"

### Import interface (load-nad CLI)
- Accepts ZIP file directly — CLI extracts TXT from ZIP transparently, avoids 35.8 GB extracted file on disk
- **State filter is required** — user must specify at least one `--state` argument to prevent accidental full-dataset (88M row) loads
- COPY strategy: COPY to temp table, then INSERT...ON CONFLICT (source_hash) DO UPDATE from temp → nad_points. Supports idempotent reload
- source_hash = NAD UUID field with braces stripped (36-char string, fits String(64) column). Trusts source record IDs like OA
- Rich progress bar during import (consistent with load-oa)
- Column mapping during pre-processing in Python (not SQL transform after COPY):
  - UUID → source_hash (strip `{}` braces)
  - Add_Number → street_number
  - St_Name → street_name
  - St_PosTyp → street_suffix
  - Unit → unit
  - city → fallback chain: Post_City first, then Inc_Muni, then County (use first non-empty/non-"Not stated" value)
  - State → state (2-letter abbreviation)
  - Zip_Code → zip_code
  - Longitude + Latitude → location (WKT POINT for ST_GeogFromText)
  - Placement → placement

### Provider registration
- Conditional on data presence at startup: `SELECT EXISTS(SELECT 1 FROM nad_points LIMIT 1)`
- If no data: log warning (like Tiger pattern), provider not registered
- Restart required after loading data (consistent with all local providers)

### Provider naming
- `provider_name` = "national_address_database" for both geocoding and validation providers

### Address matching strategy (carried from Phase 8)
- Same pattern as OA: scourgify + usaddress parse input, exact component match against staging table
- WHERE street_number = X AND UPPER(street_name) = Y AND zip_code = Z
- On match: return with Placement-mapped confidence/location_type
- On no match: return NO_MATCH with confidence=0.0

### Validation approach (carried from Phase 8)
- Same as OA: match against staging table, re-normalize through scourgify
- Binary confidence: match = 1.0, no-match = 0.0
- delivery_point_verified = False

### Claude's Discretion
- Exact COPY FROM STDIN syntax and batch/chunk sizing for the temp table approach
- Progress bar implementation for streaming from ZIP
- Whether to create a shared base class for NAD geocoding+validation or keep them separate (like OA)
- Test fixture design — mock async session pattern from OA tests
- Exact error handling for malformed CSV rows during import
- Whether batch_geocode/batch_validate use serial loops or optimized batch queries
- How to handle rows with missing/invalid coordinates during import (skip and count, like OA)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider architecture (follow OA pattern)
- `src/civpulse_geo/providers/openaddresses.py` — Local provider reference implementation (is_local=True, async_sessionmaker injection, **kwargs in geocode(), _parse_input_address, _find_oa_match query pattern)
- `src/civpulse_geo/providers/base.py` — GeocodingProvider and ValidationProvider ABCs with is_local property
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult and ValidationResult dataclasses (target return types)
- `src/civpulse_geo/providers/exceptions.py` — ProviderError hierarchy for error handling

### Service layer integration
- `src/civpulse_geo/services/geocoding.py` — is_local bypass logic (local_providers dict, no DB write path)
- `src/civpulse_geo/services/validation.py` — Validation service bypass path
- `src/civpulse_geo/main.py` — FastAPI lifespan: provider registration (NAD added conditionally alongside OA and Tiger)

### Staging table and models
- `src/civpulse_geo/models/nad.py` — NADPoint ORM model (column names, source_hash unique constraint, Geography column)
- `src/civpulse_geo/models/openaddresses.py` — OpenAddressesPoint model (reference for column patterns)

### CLI
- `src/civpulse_geo/cli/__init__.py` — load-nad stub (lines 549-563), load-oa implementation (COPY reference pattern), setup-tiger (state resolution pattern)

### NAD source data
- `data/NAD_r21_TXT.zip` — NAD r21 dataset (CSV format, ~88M rows, 60 columns per schema.ini)
- `data/NAD_r21_TXT.zip!/TXT/schema.ini` — Column definitions confirming CSVDelimited format

### Testing
- `tests/test_oa_provider.py` — Mock async_sessionmaker pattern (_make_session_factory helper) — reuse for NAD tests

### Prior phase context
- `.planning/phases/07-pipeline-infrastructure/07-CONTEXT.md` — Pipeline bypass decisions, staging table design, CLI patterns
- `.planning/phases/08-openaddresses-provider/08-CONTEXT.md` — Local provider implementation pattern, address matching, confidence tiers
- `.planning/phases/09-tiger-provider/09-CONTEXT.md` — Conditional registration pattern, Tiger provider reference

### Requirements
- `.planning/REQUIREMENTS.md` — NAD-01 through NAD-04 requirements for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `providers/openaddresses.py` OAGeocodingProvider/OAValidationProvider: Reference pattern for local provider with async_sessionmaker injection, is_local=True, **kwargs in geocode()
- `providers/openaddresses.py` _parse_input_address(): Reusable for NAD — same scourgify+usaddress parsing
- `providers/openaddresses.py` _find_oa_match(): Query pattern to adapt for nad_points (ST_Y/ST_X extraction, LIMIT 1 ORDER BY id)
- `providers/schemas.py` GeocodingResult/ValidationResult: Return types for both providers
- `providers/exceptions.py` ProviderError: Wrap SQL/DB errors for clean propagation
- `models/nad.py` NADPoint: ORM model already created in Phase 7 with all needed columns
- `cli/__init__.py` load-oa: Import pattern reference (Rich progress, batch processing, stats tracking)
- `cli/__init__.py` _resolve_state(): State FIPS/abbreviation resolution already implemented for Tiger — reuse for NAD --state filter
- `rich.progress.Progress`: Already installed, use for load-nad progress bar
- `tests/test_oa_provider.py` _make_session_factory(): Mock async session pattern reusable for NAD tests

### Established Patterns
- PostGIS Geography(POINT, 4326) with GiST index — query with ST_MakePoint(lng, lat)
- Synchronous engine (psycopg2) for CLI COPY operations, async engine (asyncpg) for API path
- ON CONFLICT upsert for idempotent data loading (via temp table for COPY)
- Provider constructor takes async_sessionmaker for local providers
- is_local=True → service layer skips DB cache writes
- Provider returns NO_MATCH with confidence=0.0 on miss (not exception)
- Conditional registration with warning log (Tiger pattern)

### Integration Points
- `main.py` lifespan: Add NAD conditional registration after data presence check (alongside OA and Tiger blocks)
- `cli/__init__.py`: Replace load-nad stub with actual COPY-based import logic
- Service layer: No changes needed — is_local bypass already handles local providers

</code_context>

<specifics>
## Specific Ideas

- NAD UUID field has braces: `{0EDDC2DD-6521-4EC7-B87B-AE4697521050}` — strip before storing as source_hash
- City fallback chain: Post_City → Inc_Muni → County. Post_City is often "Not stated" in sample data, Inc_Muni has "City of" prefix that may need stripping
- 90.7% of NAD records have Placement="Unknown" — the confidence mapping (0.1) makes these clearly low-trust
- NAD data starts with Alaska, sorted by state — state filter can short-circuit early for single-state loads
- The _parse_input_address function from OA provider should be extracted to a shared module or imported directly from openaddresses.py to avoid duplication

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-nad-provider*
*Context gathered: 2026-03-24*
