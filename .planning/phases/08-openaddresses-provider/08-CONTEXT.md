# Phase 8: OpenAddresses Provider - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement OpenAddresses geocoding and validation providers that query the `openaddresses_points` staging table, plus wire the `load-oa` CLI command to actually import .geojson.gz data. Providers implement existing GeocodingProvider/ValidationProvider ABCs with `is_local=True`. No new staging tables, no new migrations — Phase 7 built the infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Address matching strategy
- Parse incoming freeform address using scourgify's `normalize_address_record()` to extract components (number, street, city, state, zip)
- Exact component match against staging table: `WHERE street_number = X AND UPPER(street_name) = Y AND postcode = Z`
- Normalize street suffixes before matching (both input and stored data use USPS abbreviations)
- On multiple matches: `LIMIT 1` ordered by id (first match, deterministic)
- On no match: return GeocodingResult with confidence=0.0, location_type=NO_MATCH

### Accuracy-to-location_type mapping
- Claude's discretion on exact mapping from OA accuracy values to GeocodingResult location_type
- May update existing location_type values in codebase if better mappings exist
- Confidence tiers are fixed by user decision:
  - rooftop = 1.0
  - parcel = 0.8
  - interpolation = 0.5
  - centroid = 0.4
  - empty/unknown = 0.1

### Provider auto-registration
- Always register the OA provider in the provider list (no startup data check needed)
- If `openaddresses_points` table is empty, provider returns NO_MATCH gracefully (no error)
- Restart required after loading new data (consistent with all providers)
- Provider constructor receives `async_sessionmaker` for querying staging table

### Validation approach
- Same matching logic as geocoding: scourgify-parse input, exact component match against staging table
- After matching, pipe the OA address components through scourgify for USPS-standard normalization
- Binary confidence: match = 1.0, no-match = 0.0
- `delivery_point_verified` = False (no DPV from OA data)

### CLI data loading (load-oa)
- 1000-row batches with commit per batch
- Rich progress bar during import, updates per batch
- Convert empty strings to NULL during import (OA uses empty strings for missing data)
- Use OA's built-in `hash` property directly as `source_hash` value
- Upsert: ON CONFLICT (source_hash) DO UPDATE
- Summary after import: total processed, inserted, updated, skipped, elapsed time
- Skip features without valid coordinates (count in skipped total, log hash for debugging)
- Skip malformed GeoJSON features (log warning, count in skipped total)

### Street suffix parsing during import
- Use `usaddress` library (transitive dep via scourgify) to parse OA `street` field into `street_name` and `street_suffix`
- OA `number` and `street` are always separate properties — no need to extract number from street
- Store parsed suffix in `street_suffix` column for matching queries

### Provider naming
- `provider_name` = "openaddresses" for both geocoding and validation providers
- `raw_response` contains matched OA row data as dict: source_hash, street_number, street_name, street_suffix, city, region, postcode, accuracy, lat, lng

### Error handling
- During import: skip and count malformed features, don't halt entire import
- During geocode/validate: raise `ProviderError` on database connection failures (not silent NO_MATCH)
- Wrap SQLAlchemy exceptions in ProviderError for clean error propagation

### Claude's Discretion
- Exact accuracy-to-location_type mapping choices
- Whether to create a shared base class for OA geocoding+validation or keep them separate
- Internal query construction details (text() vs ORM query)
- Test fixture design and factory patterns
- Whether batch_geocode/batch_validate use serial loops or optimized batch queries

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider architecture
- `src/civpulse_geo/providers/base.py` — GeocodingProvider and ValidationProvider ABCs with is_local property
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult and ValidationResult dataclasses (target return types)
- `src/civpulse_geo/providers/registry.py` — load_providers() eager instantiation pattern
- `src/civpulse_geo/providers/exceptions.py` — ProviderError hierarchy for error handling

### Reference implementations (follow these patterns)
- `src/civpulse_geo/providers/census.py` — Remote geocoding provider (GeocodingResult construction, error handling)
- `src/civpulse_geo/providers/scourgify.py` — Offline validation provider (ValidationResult construction, scourgify usage)

### Service layer integration
- `src/civpulse_geo/services/geocoding.py` — is_local bypass logic (local_providers dict, no DB write path)
- `src/civpulse_geo/services/validation.py` — Validation service bypass path

### Staging table and models
- `src/civpulse_geo/models/openaddresses.py` — OpenAddressesPoint ORM model (column names and types)
- `src/civpulse_geo/models/base.py` — TimestampMixin pattern

### CLI
- `src/civpulse_geo/cli/__init__.py` — load-oa stub (lines ~270-287), existing import command patterns (sync engine + raw SQL)

### Sample data
- `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` — Bibb County OA data (NDJSON format, ~property structure reference)

### Prior phase context
- `.planning/phases/07-pipeline-infrastructure/07-CONTEXT.md` — Pipeline bypass decisions, staging table design, CLI patterns

### Requirements
- `.planning/REQUIREMENTS.md` — OA-01 through OA-04 requirements for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scourgify.normalize_address_record()`: Parse freeform addresses into USPS components — used for both input parsing and output normalization
- `usaddress` (transitive dep): Tag-based address parsing for splitting OA street field into name+suffix
- `providers/schemas.py` GeocodingResult/ValidationResult: Return types for both providers
- `providers/exceptions.py` ProviderError: Wrap DB errors for clean propagation
- `rich.progress.Progress`: Already installed (Phase 7), use for load-oa progress bar
- `models/openaddresses.py` OpenAddressesPoint: ORM model for staging table queries

### Established Patterns
- PostGIS Geography(POINT, 4326) with GiST index — query with ST_MakePoint(lng, lat)
- Synchronous engine (psycopg2) for CLI operations, async engine (asyncpg) for API path
- ON CONFLICT upsert for idempotent data loading
- Provider constructor takes no args for remote, async_sessionmaker for local
- is_local=True on provider class → service layer skips DB cache writes

### Integration Points
- `main.py` lifespan: Register OA providers alongside existing providers (pass async_sessionmaker)
- `cli/__init__.py`: Replace load-oa stub with actual import logic
- `providers/registry.py`: May need update to pass session_factory to local provider constructors
- Service layer: No changes needed — is_local bypass already handles local providers

</code_context>

<specifics>
## Specific Ideas

- OA's `hash` property is used directly as source_hash (not recomputed) — per Phase 7 context decision
- OA `region` field maps to state, but sample Bibb County data has it empty — postcode-based matching may be more reliable than state-based
- Sample data is NDJSON (newline-delimited JSON) inside .geojson.gz, not standard GeoJSON FeatureCollection
- Confidence tiers are user-specified exact values, not ranges: rooftop=1.0, parcel=0.8, interpolation=0.5, centroid=0.4, empty=0.1

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-openaddresses-provider*
*Context gathered: 2026-03-22*
