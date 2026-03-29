# Phase 12: Correctness Fixes and DB Prerequisites - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix 4 known provider defects (Tiger county mismatch, ZIP prefix fallback, street suffix matching, validation confidence semantics) and add GIN trigram indexes on staging tables — preparing the database and providers for cascade logic in subsequent phases.

</domain>

<decisions>
## Implementation Decisions

### Tiger County Filtering (FIX-01)
- **D-01:** Spatial post-filter using `ST_Contains()` against existing PostGIS Tiger extension tables (`tiger.county`) — no new boundary data import needed
- **D-02:** County is derived from the input address by default (parse city/state, resolve to county FIPS via `tiger.county`), with an optional `county_fips` parameter for callers who know the county
- **D-03:** When the Tiger geocode result falls outside the expected county polygon, return `NO_MATCH` — wrong-county results are discarded entirely, never enter the pipeline

### ZIP Prefix Fallback (FIX-02)
- **D-04:** All local providers (OA, NAD, Macon-Bibb) get zip prefix fallback — consistent behavior since all share the same matching pattern
- **D-05:** Progressive prefix matching: try 4-digit prefix first (`LIKE '3120%'`), then fall back to 3-digit prefix (`LIKE '312%'`) if no match
- **D-06:** When multiple candidates match on prefix, order by numeric distance from input zip prefix (closest zip numerically wins)

### Street Suffix Matching (FIX-03)
- **D-07:** Query `street_name` AND `street_suffix` as separate WHERE conditions (leverages existing column split in staging tables); fall back to name-only match if suffix is NULL
- **D-08:** Also extract `StreetNamePostDirectional` (e.g., 'N', 'S') from usaddress parsing while changing `_parse_input_address()` return signature — prevents directional mismatches (e.g., '5th Ave N' vs '5th Ave S')

### Confidence Semantics (FIX-04)
- **D-09:** Scourgify validation confidence reduced from 1.0 to **0.3** — "structurally parsed but not address-verified" (deviates from FIX-04's literal 0.5; user chose more conservative separation from real geocode results)
- **D-10:** Tiger validation confidence reduced from 1.0 to **0.4** — slightly higher than scourgify because `normalize_address()` cross-references Census street data, providing more signal than offline regex parsing

### Claude's Discretion
- GIN trigram index creation strategy (FUZZ-01): new Alembic migration vs. modifying existing — Claude decides based on migration chain
- `pg_trgm` extension enablement approach (in migration or separate)
- Internal refactoring of `_parse_input_address()` to accommodate the expanded return tuple

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider Implementation
- `src/civpulse_geo/providers/tiger.py` — Tiger geocoding/validation provider; FIX-01 changes here
- `src/civpulse_geo/providers/openaddresses.py` — OA provider + shared `_parse_input_address()` function; FIX-02, FIX-03 changes here
- `src/civpulse_geo/providers/nad.py` — NAD provider; FIX-02, FIX-03 changes here
- `src/civpulse_geo/providers/macon_bibb.py` — Macon-Bibb provider; FIX-02, FIX-03 changes here
- `src/civpulse_geo/providers/scourgify.py` — Scourgify validation provider; FIX-04 confidence change here
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult/ValidationResult dataclasses

### Database Models and Migrations
- `src/civpulse_geo/models/openaddresses.py` — OpenAddressesPoint table definition (has `street_suffix` column)
- `src/civpulse_geo/models/nad.py` — NADPoint table definition (has `street_suffix` column)
- `alembic/versions/c1f84b2e9a07_add_local_provider_staging_tables.py` — Current indexes on staging tables; FUZZ-01 GIN indexes build on this

### Requirements
- `.planning/REQUIREMENTS.md` — FIX-01 through FIX-04, FUZZ-01 requirements with acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_parse_input_address()` in `openaddresses.py` — shared parser used by OA, NAD, and Macon-Bibb; single change point for FIX-03/D-08
- `tiger.county` PostGIS extension table — already loaded county boundary polygons; enables FIX-01 spatial post-filter without new data import
- Mock session factory pattern in tests (`_make_session_factory()`) — reusable for new test cases

### Established Patterns
- Local providers use `is_local=True` property and bypass DB cache — no cache table changes needed
- All providers accept `**kwargs` in `geocode()` — optional `county_fips` parameter (D-02) fits cleanly
- Alembic migrations use `op.create_index()` with `postgresql_using` kwarg for spatial indexes — same pattern for GIN trigram indexes
- Confidence is a float field on `GeocodingResult`/`ValidationResult` schemas — value changes are constant swaps

### Integration Points
- `_parse_input_address()` return signature change (3-tuple to 5-tuple) affects all callers in OA, NAD, and Macon-Bibb providers
- Tiger provider's `GEOCODE_SQL` constant needs post-query filtering logic added to `geocode()` method
- New Alembic migration for `pg_trgm` extension + GIN indexes on `openaddresses_points.street` and `nad_points.street_name`

</code_context>

<specifics>
## Specific Ideas

- User wants `county_fips` as an optional API parameter for a specific use case — ensure it passes through the provider interface
- Confidence values (0.3 scourgify, 0.4 Tiger) deliberately deviate from FIX-04's literal "0.5" — user chose more conservative values to create clearer separation from geocoded results (0.8-1.0 range) for Phase 14 consensus scoring
- Progressive zip prefix (4-digit then 3-digit) chosen over single-pass — user wants broader fallback coverage at the cost of an extra query round

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-correctness-fixes-and-db-prerequisites*
*Context gathered: 2026-03-29*
