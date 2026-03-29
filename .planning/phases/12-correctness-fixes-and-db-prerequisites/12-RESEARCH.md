# Phase 12: Correctness Fixes and DB Prerequisites - Research

**Researched:** 2026-03-29
**Domain:** PostGIS Tiger spatial filtering, SQLAlchemy async query patterns, Alembic migrations, usaddress/scourgify parsing
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Tiger County Filtering (FIX-01)**
- D-01: Spatial post-filter using `ST_Contains()` against existing PostGIS Tiger extension tables (`tiger.county`) — no new boundary data import needed
- D-02: County is derived from the input address by default (parse city/state, resolve to county FIPS via `tiger.county`), with an optional `county_fips` parameter for callers who know the county
- D-03: When the Tiger geocode result falls outside the expected county polygon, return `NO_MATCH` — wrong-county results are discarded entirely, never enter the pipeline

**ZIP Prefix Fallback (FIX-02)**
- D-04: All local providers (OA, NAD, Macon-Bibb) get zip prefix fallback — consistent behavior since all share the same matching pattern
- D-05: Progressive prefix matching: try 4-digit prefix first (`LIKE '3120%'`), then fall back to 3-digit prefix (`LIKE '312%'`) if no match
- D-06: When multiple candidates match on prefix, order by numeric distance from input zip prefix (closest zip numerically wins)

**Street Suffix Matching (FIX-03)**
- D-07: Query `street_name` AND `street_suffix` as separate WHERE conditions (leverages existing column split in staging tables); fall back to name-only match if suffix is NULL
- D-08: Also extract `StreetNamePostDirectional` (e.g., 'N', 'S') from usaddress parsing while changing `_parse_input_address()` return signature — prevents directional mismatches (e.g., '5th Ave N' vs '5th Ave S')

**Confidence Semantics (FIX-04)**
- D-09: Scourgify validation confidence reduced from 1.0 to **0.3** — "structurally parsed but not address-verified"
- D-10: Tiger validation confidence reduced from 1.0 to **0.4** — slightly higher than scourgify because `normalize_address()` cross-references Census street data

### Claude's Discretion
- GIN trigram index creation strategy (FUZZ-01): new Alembic migration vs. modifying existing — Claude decides based on migration chain
- `pg_trgm` extension enablement approach (in migration or separate)
- Internal refactoring of `_parse_input_address()` to accommodate the expanded return tuple

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FIX-01 | Tiger geocode results filtered by county boundary via PostGIS `ST_Contains()`, discarding wrong-county matches | tiger.county table verified with 3,235 rows, SRID 4269, ST_Contains confirmed working with SRID transform |
| FIX-02 | Local providers (OA, NAD, Macon-Bibb) fall back to zip prefix matching when input zip is < 5 digits | usaddress extracts ZIP as-is (confirmed "3120" passes through), LIKE pattern syntax verified |
| FIX-03 | Street name matching includes `street_suffix` in query to prevent multi-word street names from failing | Root cause confirmed: scourgify normalizes "Falls" to "FLS", usaddress then extracts only "BEAVER" as StreetName; StreetNamePostType is the token to capture |
| FIX-04 | Scourgify validation confidence = 0.3 (was 1.0); Tiger validation confidence = 0.4 (was 1.0) | SCOURGIFY_CONFIDENCE constant in scourgify.py line 28; TigerValidationProvider.validate() hardcodes 1.0 at line 296 |
| FUZZ-01 | pg_trgm extension enabled via Alembic migration with GIN trigram indexes on openaddresses_points.street_name and nad_points.street_name | pg_trgm available in DB container; GIN index syntax `gin (street_name gin_trgm_ops)` verified; migration chain tail is e5b2a1d3f4c6 |
</phase_requirements>

---

## Summary

Phase 12 is a surgical correctness pass across five known defects. Four are provider-level logic bugs; one is a database prerequisite for Phase 13 fuzzy matching. All changes are isolated to a small, well-understood surface area: four provider files sharing a single parse function, one validation provider constant, and one new Alembic migration.

The Tiger county filter (FIX-01) requires adding a county-resolution step before the geocode call and a spatial containment check on the returned coordinates. The `tiger.county` table is verified present with 3,235 rows in SRID 4269 — requiring an explicit `ST_Transform` to match against WGS84 geocode results. The `_parse_input_address()` refactor (FIX-02/FIX-03/D-08) is the highest-impact change because three providers import and destructure this function's return value — expanding the 3-tuple to a 5-tuple touches OA, NAD, and Macon-Bibb simultaneously.

The GIN trigram migration (FUZZ-01) is straightforward: `pg_trgm` is available in the container image, the syntax `gin (street_name gin_trgm_ops)` is verified, and the migration tail is `e5b2a1d3f4c6`. One new migration appended to the chain handles both the `CREATE EXTENSION` and both index creations.

**Primary recommendation:** Implement in dependency order — (1) `_parse_input_address()` signature expansion first (blocks FIX-02 and FIX-03 callers), (2) Tiger county filter (FIX-01, independent), (3) confidence constants (FIX-04, trivial), (4) Alembic migration (FUZZ-01, independent).

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.x (async) | ORM + raw SQL via `text()` | Already in use; all providers use `async_sessionmaker` |
| PostGIS | 3.5.2 | Spatial operations (`ST_Contains`, `ST_Transform`) | Already installed in DB container |
| tiger.county | (loaded) | County boundary polygons for FIX-01 spatial filter | 3,235 rows confirmed, SRID 4269 |
| usaddress | (installed) | Token-level address parsing for `_parse_input_address()` | Already used for StreetName extraction |
| scourgify | (installed) | USPS normalization step before usaddress parsing | Already used in all local providers |
| Alembic | (installed) | Database migration management | All existing migrations use Alembic |
| pg_trgm | PostgreSQL extension | GIN trigram indexes for fuzzy string matching | Available in container image, not yet enabled |

### Alembic Migration Chain (verified)
```
b98c26825b02 (initial_schema)
  -> a3d62fae3d64 (add_validation_results_table)
     -> c1f84b2e9a07 (add_local_provider_staging_tables)
        -> d4a71c3f8b92 (add_oa_parcels_table)
           -> e5b2a1d3f4c6 (add_macon_bibb_address_points_table)  ← CURRENT HEAD
              -> [NEW] add_pg_trgm_gin_indexes
```

**New migration** must set `down_revision = 'e5b2a1d3f4c6'` and use `op.execute()` for DDL that Alembic cannot express via `op.create_index()` alone (pg_trgm requires the extension before the index).

---

## Architecture Patterns

### FIX-01: Tiger County Spatial Post-Filter

**What:** After `geocode()` returns a lat/lng from the PostGIS Tiger function, check that the point falls within the expected county polygon.

**County resolution flow:**
1. Parse input address city/state via `_parse_input_address()` (already available) to derive state FIPS
2. Query `tiger.county` by `name ILIKE <city>` AND `statefp = <state_fips>` to get `cntyidfp` (default path, D-02)
3. OR accept `county_fips` kwarg directly (override path, D-02)
4. After geocode SQL returns lat/lng, run spatial containment check

**Critical SRID detail:** `tiger.county.the_geom` is SRID 4269 (NAD83). The geocode result is WGS84 (SRID 4326). Must use `ST_Transform(ST_SetSRID(ST_MakePoint(lng, lat), 4326), 4269)` to convert the point before the `ST_Contains` check.

**Verified pattern:**
```sql
-- Resolving county FIPS from name (D-02 default path)
SELECT cntyidfp FROM tiger.county
WHERE name ILIKE :county_name AND statefp = :state_fips
LIMIT 1;

-- Containment check (D-03 filter)
SELECT ST_Contains(the_geom, ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 4269))
FROM tiger.county
WHERE cntyidfp = :county_fips;
```

**Implementation note:** The county name derivation from city is best-effort. For Macon-Bibb the city is "Macon" and county is "Bibb" — these differ. A reliable mapping requires either (a) a city→county lookup table, or (b) spatial containment of the geocode result against ALL counties (simpler but requires geocode first, which defeats early-exit). D-02's intent is clear: attempt to resolve from parsed address components; fall back if ambiguous. The simplest approach is to derive county by running the containment check directly using the geocoded point — if the result's lat/lng is not inside `tiger.county` rows matching the input state, return NO_MATCH. This avoids city→county name matching entirely.

**Revised recommended approach (simpler, avoids city/county name ambiguity):**
1. Parse state from input address
2. Run Tiger geocode SQL (existing)
3. If result found: run ST_Contains check against `tiger.county WHERE statefp = :state_fips AND ST_Contains(the_geom, ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 4269))` — this returns the county the result falls in
4. If `county_fips` kwarg provided: verify returned county matches
5. If no county_fips kwarg: accept result if it falls in any county in the correct state
6. If geocode result falls in wrong county (when county_fips is provided, or in wrong state): return NO_MATCH

**Note for planner:** D-02 says county is derived from input address "by default". The simplest, most reliable approach is to do the spatial containment check on the geocoded point rather than trying to reverse-lookup city→county name. The planner should clarify this interpretation with implementation context.

### FIX-02: ZIP Prefix Fallback

**`_parse_input_address()` already extracts `postal_code` including short ZIPs.** Verified: usaddress passes "3120" through as `ZipCode = '3120'`.

**Pattern — modify `_find_oa_match`, `_find_nad_match`, `_find_macon_bibb_match`:**

The existing exact match queries use `== postal_code`. Prefix fallback is added as a two-pass pattern inside the geocode/validate methods:

```python
# Pass 1: exact match (existing)
row_tuple = await _find_oa_match(session, street_number, street_name, postal_code)

# Pass 2: zip prefix fallback — only when postal_code is < 5 digits
if row_tuple is None and postal_code and len(postal_code) < 5:
    row_tuple = await _find_oa_zip_prefix_match(
        session, street_number, street_name, postal_code
    )
```

**Prefix fallback function signature:**
```python
async def _find_oa_zip_prefix_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    zip_prefix: str,  # e.g. "3120" (4-digit) or "312" (3-digit)
) -> tuple[OpenAddressesPoint, float, float] | None:
```

**D-05 progressive prefix logic:** Try 4-digit prefix first; if no match and prefix is >= 4 digits, try 3-digit prefix. D-06: order by `ABS(CAST(postcode AS INTEGER) - CAST(:zip_prefix AS INTEGER))` when multiple candidates exist.

**SQLAlchemy LIKE syntax:**
```python
OpenAddressesPoint.postcode.like(f"{zip_prefix}%")
```

### FIX-03: Street Suffix Matching

**Root cause (verified):** Scourgify normalizes "Beaver Falls" → "BEAVER FLS". Usaddress then parses `StreetName='BEAVER'` and `StreetNamePostType='FLS'`. The existing `_parse_input_address()` only collects `StreetName` tokens, so the query searches for `street_name = 'BEAVER'` — which fails because the staging table stores the full "BEAVER FALLS" in `street_name`.

**Fix:** Expand `_parse_input_address()` return from 3-tuple to 5-tuple, adding `street_suffix` and `street_directional`:

```python
def _parse_input_address(
    address: str,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Parse freeform address into (street_number, street_name, postal_code, street_suffix, street_directional)."""
    ...
    street_suffix = tokens.get("StreetNamePostType")  # e.g. "FLS", "RD", "ST"
    street_directional = tokens.get("StreetNamePostDirectional")  # e.g. "N", "S"
    return (street_number, street_name, postal_code, street_suffix, street_directional)
```

**All callers must be updated** to destructure 5 values. Callers: `OAGeocodingProvider.geocode()`, `OAValidationProvider.validate()`, `NADGeocodingProvider.geocode()`, `NADValidationProvider.validate()`, `MaconBibbGeocodingProvider.geocode()`, `MaconBibbValidationProvider.validate()`.

**Query update for D-07:**
```python
# In _find_oa_match:
.where(
    OpenAddressesPoint.street_number == street_number,
    func.upper(OpenAddressesPoint.street_name) == street_name.upper(),
    OpenAddressesPoint.postcode == postcode,
    # D-07: include suffix when present
    (OpenAddressesPoint.street_suffix.is_(None)) |
    (func.upper(OpenAddressesPoint.street_suffix) == street_suffix.upper())
    if street_suffix else sa.true(),
)
```

**D-08 directional filtering:** Add similar OR-null condition on `street_suffix` column (note: staging tables don't have a dedicated directional column; directional matching may require either storing it or including it in street_name comparisons). Planner should investigate whether `street_suffix` column actually stores directionals or only type suffixes in the loaded data.

### FIX-04: Confidence Constants

Two trivial constant changes:

**scourgify.py:** Change `SCOURGIFY_CONFIDENCE = 1.0` to `SCOURGIFY_CONFIDENCE = 0.3`

**tiger.py:** Change `confidence=1.0` on line 296 of `TigerValidationProvider.validate()` to `confidence=0.4`. No constant currently exists for this value — add `TIGER_VALIDATION_CONFIDENCE = 0.4` as a module-level constant (mirrors the scourgify pattern).

### FUZZ-01: GIN Trigram Indexes

**Decision (Claude's Discretion):** Create a new Alembic migration appended to the chain head (`e5b2a1d3f4c6`). Do NOT modify existing migrations — immutable chain is the established pattern.

**Migration structure:**
```python
revision = 'f6c3d9e2b5a1'  # generate a fresh ID
down_revision = 'e5b2a1d3f4c6'

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX idx_oa_points_street_trgm "
        "ON openaddresses_points USING gin (street_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_nad_points_street_name_trgm "
        "ON nad_points USING gin (street_name gin_trgm_ops)"
    )

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_nad_points_street_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_oa_points_street_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
```

**Why `op.execute()` not `op.create_index()`:** Alembic's `create_index()` with `postgresql_using='gin'` requires the operator class to be set via `postgresql_ops`, but GIN + pg_trgm operator classes require the extension to be present first. Using `op.execute()` for raw DDL is the established Alembic pattern for extension-dependent indexes.

**Verified:** `CREATE EXTENSION IF NOT EXISTS pg_trgm` followed by `CREATE INDEX ... USING gin (street_name gin_trgm_ops)` executes successfully in the live database container.

### Anti-Patterns to Avoid

- **SRID mismatch in ST_Contains:** `tiger.county.the_geom` is SRID 4269. Comparing directly against WGS84 (4326) points silently returns wrong results. Always `ST_Transform` the point to 4269 before containment check.
- **CONCURRENT index creation inside Alembic:** `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. Alembic wraps DDL in a transaction by default. Use plain `CREATE INDEX` in migrations (verified: non-concurrent works correctly inside transaction).
- **Modifying existing migration files:** The migration chain is immutable once applied. Always add new migrations, never edit existing ones.
- **Destructuring 3 values from expanded `_parse_input_address()`:** After the signature expands to 5-tuple, every caller that unpacks with `a, b, c = _parse_input_address(...)` will raise `ValueError: too many values to unpack`. All six call sites must be updated atomically.
- **LIKE on non-prefix-indexed column:** The zip prefix LIKE queries (`postcode LIKE '3120%'`) will work but use a sequential scan if no index exists. The existing `idx_oa_points_lookup` index on `(region, postcode, street_name)` may partially help but not for prefix-only queries. This is acceptable for Phase 12 since prefix fallback is a rare path — index optimization is Phase 13+.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| County boundary data | Import shapefile, build boundary table | `tiger.county` (already loaded) | 3,235 rows present; PostGIS extension owns this data |
| SRID conversion | Write lat/lng transformation math | `ST_Transform(ST_SetSRID(...), 4269)` | PostGIS handles geodetic precision correctly |
| Address component parsing | Custom regex for street suffix/directional | `usaddress.tag()` with `StreetNamePostType` and `StreetNamePostDirectional` tokens | Already used; tokens are verified correct |
| Trigram index creation | Custom similarity index or application-level fuzzy | `pg_trgm` GIN index | PostgreSQL extension handles edit-distance math; proven < 500ms target |

---

## Common Pitfalls

### Pitfall 1: SRID Mismatch in Tiger County Filter
**What goes wrong:** `ST_Contains(tiger.county.the_geom, ST_MakePoint(lng, lat))` returns `false` even for points inside the county.
**Why it happens:** `tiger.county.the_geom` is SRID 4269 (NAD83). Geocode results are WGS84 (SRID 4326). PostGIS `ST_Contains` on mismatched SRIDs either errors or silently returns wrong results.
**How to avoid:** Always wrap the point: `ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 4269)`
**Warning signs:** ST_Contains returning false for obviously correct points; test with known Bibb County coordinates (32.84, -83.63) which confirmed correct.

### Pitfall 2: Caller Signature Drift After 3-to-5-Tuple Expansion
**What goes wrong:** `ValueError: too many values to unpack (expected 3)` at runtime in providers that were not updated.
**Why it happens:** `_parse_input_address()` is imported by NAD and Macon-Bibb providers from `openaddresses.py`. If any of the six call sites is missed, it silently compiles but crashes at runtime.
**How to avoid:** Update all six call sites atomically in the same commit. Grep for `_parse_input_address` to find all callers.
**Warning signs:** Existing tests for NAD or Macon-Bibb providers failing with `ValueError` immediately after the signature change.

### Pitfall 3: Alembic `CREATE EXTENSION` Inside Default Transaction
**What goes wrong:** `CREATE EXTENSION pg_trgm` succeeds but `CREATE INDEX ... gin_trgm_ops` fails with "operator class does not exist" if the extension is not committed before index creation.
**Why it happens:** In non-autocommit Postgres, DDL like `CREATE EXTENSION` is transactional. Within a single Alembic `op.execute()` migration function, the extension IS visible to subsequent statements in the same transaction — confirmed working.
**How to avoid:** Put both `CREATE EXTENSION` and `CREATE INDEX` in the same migration's `upgrade()` function, ordered extension first. Verified working in the live container.
**Warning signs:** Migration fails only in fresh environments; passes in containers where pg_trgm was previously enabled.

### Pitfall 4: Confidence Test Values Hardcoded in Existing Tests
**What goes wrong:** After FIX-04 changes `SCOURGIFY_CONFIDENCE = 0.3` and Tiger validation to `0.4`, existing tests asserting `confidence == 1.0` will fail.
**Why it happens:** `test_tiger_provider.py` line 288 asserts `result.confidence == pytest.approx(1.0)` for successful validation. `test_scourgify_provider.py` similarly tests `confidence=1.0`.
**How to avoid:** Update test assertions for `TigerValidationProvider.validate()` and `ScourgifyValidationProvider.validate()` in the same PR as the constant changes.
**Warning signs:** Tests that were previously passing now fail with `AssertionError: 1.0 != 0.3`.

### Pitfall 5: D-08 Directional — No Dedicated Column in Staging Tables
**What goes wrong:** Attempting to filter on `street_directional` against a column that doesn't exist in `openaddresses_points`, `nad_points`, or `macon_bibb_points`.
**Why it happens:** The staging table schemas (confirmed by reading model files) have `street_suffix` but no `street_directional` column.
**How to avoid:** D-08's directional extraction from `_parse_input_address()` should be used to augment the street_name comparison or included in the suffix field matching, not as a separate column filter. Alternatively, include the directional as part of `street_name` search. This is a design decision for the planner to clarify.
**Warning signs:** SQLAlchemy `AttributeError: mapped class has no attribute 'street_directional'`.

---

## Code Examples

Verified patterns from live code inspection and DB testing:

### ST_Contains with SRID Transform (FIX-01)
```python
# Source: verified in live DB container
COUNTY_CONTAINS_SQL = text("""
    SELECT cntyidfp
    FROM tiger.county
    WHERE statefp = :state_fips
      AND ST_Contains(
            the_geom,
            ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 4269)
          )
    LIMIT 1
""")
```

### County FIPS Resolution from State Name (D-02 with county_fips kwarg)
```python
# Source: verified in live DB container
COUNTY_FIPS_SQL = text("""
    SELECT cntyidfp
    FROM tiger.county
    WHERE name ILIKE :county_name
      AND statefp = :state_fips
    LIMIT 1
""")
```

### Expanded `_parse_input_address()` Signature (FIX-03/D-08)
```python
# Source: openaddresses.py _parse_input_address() — expansion of existing function
def _parse_input_address(
    address: str,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Parse freeform address into (street_number, street_name, postal_code, street_suffix, street_directional)."""
    try:
        parsed = normalize_address_record(address)
    except Exception:
        return (None, None, None, None, None)

    postal_code = (parsed.get("postal_code") or "").strip() or None
    address_line_1 = (parsed.get("address_line_1") or "").strip()

    if not address_line_1:
        return (None, None, None, None, None)

    try:
        tokens, _ = usaddress.tag(address_line_1)
    except usaddress.RepeatedLabelError:
        return (None, None, None, None, None)

    street_number = tokens.get("AddressNumber")
    street_name_parts = [v for k, v in tokens.items() if k == "StreetName"]
    street_name = " ".join(street_name_parts).strip() or None
    street_suffix = tokens.get("StreetNamePostType")           # e.g. "FLS", "RD"
    street_directional = tokens.get("StreetNamePostDirectional")  # e.g. "N", "S"

    return (street_number, street_name, postal_code, street_suffix, street_directional)
```

### ZIP Prefix Fallback (FIX-02) — SQLAlchemy LIKE
```python
# Source: pattern extension of existing _find_oa_match()
async def _find_oa_zip_prefix_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    zip_prefix: str,
) -> tuple[OpenAddressesPoint, float, float] | None:
    stmt = (
        select(
            OpenAddressesPoint,
            func.ST_Y(OpenAddressesPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(OpenAddressesPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            OpenAddressesPoint.street_number == street_number,
            func.upper(OpenAddressesPoint.street_name) == street_name.upper(),
            OpenAddressesPoint.postcode.like(f"{zip_prefix}%"),
        )
        .order_by(OpenAddressesPoint.postcode)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()
```

### FIX-04 Confidence Constant Changes
```python
# scourgify.py — line 28 change
SCOURGIFY_CONFIDENCE = 0.3  # was 1.0

# tiger.py — add module-level constant
TIGER_VALIDATION_CONFIDENCE = 0.4  # was hardcoded 1.0 at line 296
# ...in TigerValidationProvider.validate():
confidence=TIGER_VALIDATION_CONFIDENCE,  # was confidence=1.0
```

### Alembic Migration for FUZZ-01
```python
# alembic/versions/<new_id>_add_pg_trgm_gin_indexes.py
revision = '<new_id>'
down_revision = 'e5b2a1d3f4c6'

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX idx_oa_points_street_trgm "
        "ON openaddresses_points USING gin (street_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_nad_points_street_name_trgm "
        "ON nad_points USING gin (street_name gin_trgm_ops)"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_nad_points_street_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_oa_points_street_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tiger geocode returns any county result | Tiger geocode post-filtered by county boundary | Phase 12 | Eliminates wrong-county matches corrupting cascade |
| Exact 5-digit zip match only | 5-digit exact, then 4-digit prefix, then 3-digit prefix | Phase 12 | Short-ZIP inputs resolve instead of returning NO_MATCH |
| StreetName-only query (misses suffix tokens) | StreetName + StreetNamePostType (suffix) in query | Phase 12 | Multi-word streets like "Beaver Falls" match correctly |
| confidence=1.0 for parse-only providers | confidence=0.3 (scourgify) / 0.4 (Tiger normalize) | Phase 12 | Phase 14 consensus scorer can distinguish parse from geocode |
| No trigram indexes | GIN trigram indexes on street_name columns | Phase 12 | Phase 13 FuzzyMatcher can run word_similarity() within 500ms |

---

## Open Questions

1. **City-to-county name mapping ambiguity (FIX-01, D-02 default path)**
   - What we know: `tiger.county.name` is "Bibb" not "Macon"; city name from input address is "Macon". Direct name lookup fails.
   - What's unclear: Should D-02 "derive county from input address" use (a) the geocoded point's spatial containment to identify its county (most reliable), or (b) a USPS city→county lookup (complex), or (c) just require `county_fips` kwarg always?
   - Recommendation: Use approach (a) — run ST_Contains against the geocoded point to identify its county FIPS, then verify it matches any allowed county for the input's state. When `county_fips` kwarg is provided, verify that the identified county equals the kwarg value. This avoids city/county name ambiguity entirely.

2. **D-08 directional column: where does it go in the WHERE clause?**
   - What we know: Staging tables have `street_suffix` column but NO `street_directional` column.
   - What's unclear: D-08 says "extract StreetNamePostDirectional... prevents directional mismatches". But there's no column to filter against.
   - Recommendation: Include the directional as part of the street_name string match (append it to the StreetName token list) OR add it to the suffix WHERE condition, OR accept that directional extraction in Phase 12 only prevents the *parsed output* from including it in the name (so "5th Ave N" doesn't match "5th Ave" stored in street_name). The planner should decide the exact filtering semantics given the current schema.

3. **D-06 ZIP ordering — numeric distance logic for short prefixes**
   - What we know: D-06 says "order by numeric distance from input zip prefix". Casting "31201" to INTEGER from a 5-digit string works; casting "3120" (4-digit prefix) also works.
   - What's unclear: Ordering by `ABS(CAST(postcode AS INTEGER) - CAST('3120' AS INTEGER))` compares "3120" (4120 numerically if interpreted as int) against "31201" (31201). The numeric distance semantics are odd for prefix matching.
   - Recommendation: Order by `postcode ASC` (lexicographic) when using LIKE prefix — this naturally groups numerically adjacent ZIPs. Alternatively, use `ABS(CAST(LEFT(postcode, LENGTH(:prefix)) AS INTEGER) - CAST(:prefix AS INTEGER))` to compare same-length prefixes.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL + PostGIS | FIX-01 ST_Contains, all DB queries | Yes | PostGIS 3.5.2 on PG17 | — |
| tiger.county table | FIX-01 county spatial filter | Yes | 3,235 rows loaded | — |
| pg_trgm extension | FUZZ-01 GIN indexes | Yes (available, not yet enabled) | Available in container | — |
| usaddress | FIX-03 token extraction | Yes (installed in container) | — | — |
| scourgify | FIX-04, all providers | Yes (installed in container) | — | — |
| Alembic | FUZZ-01 migration | Yes (installed in container) | — | — |
| Docker containers | Test execution | Yes | geo-api-api-1, geo-api-db-1 running | — |
| pytest (in container) | Test suite | Yes | pytest 9.0.2 | — |

**Missing dependencies with no fallback:** None

**Note:** pytest is NOT available on the host system (`python3 -m pytest` fails). All test execution must run inside `geo-api-api-1` container: `docker exec geo-api-api-1 python -m pytest ...`

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py tests/test_oa_provider.py tests/test_nad_provider.py tests/test_macon_bibb_provider.py tests/test_scourgify_provider.py -q` |
| Full suite command | `docker exec geo-api-api-1 python -m pytest tests/ -q` |

### Baseline (pre-Phase 12)
- 378 tests collected
- 365 passing, 11 failing (pre-existing failures in `test_import_cli.py` and `test_load_oa_cli.py` — unrelated to Phase 12)
- 2 skipped (Tiger data tests)

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FIX-01 | Tiger geocode result in neighboring county returns NO_MATCH | unit | `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py -q` | Partial — needs new county filter tests |
| FIX-01 | Tiger geocode result inside correct county returns match | unit | `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py -q` | Partial — needs new tests |
| FIX-02 | 4-digit zip "3120" resolves via LIKE prefix in OA provider | unit | `docker exec geo-api-api-1 python -m pytest tests/test_oa_provider.py -q` | Partial — needs new zip prefix tests |
| FIX-02 | 4-digit zip "3120" resolves in NAD provider | unit | `docker exec geo-api-api-1 python -m pytest tests/test_nad_provider.py -q` | Partial — needs new tests |
| FIX-02 | 4-digit zip "3120" resolves in Macon-Bibb provider | unit | `docker exec geo-api-api-1 python -m pytest tests/test_macon_bibb_provider.py -q` | Partial — needs new tests |
| FIX-03 | "Beaver Falls" street matches when suffix included in query | unit | `docker exec geo-api-api-1 python -m pytest tests/test_oa_provider.py tests/test_nad_provider.py -q` | Needs new suffix tests |
| FIX-03 | `_parse_input_address()` returns 5-tuple with suffix and directional | unit | `docker exec geo-api-api-1 python -m pytest tests/test_oa_provider.py -q` | Needs new parse tests |
| FIX-04 | Scourgify validation returns confidence=0.3 | unit | `docker exec geo-api-api-1 python -m pytest tests/test_scourgify_provider.py -q` | Needs test update (currently asserts 1.0) |
| FIX-04 | Tiger validation returns confidence=0.4 | unit | `docker exec geo-api-api-1 python -m pytest tests/test_tiger_provider.py -q` | Needs test update (currently asserts 1.0) |
| FUZZ-01 | pg_trgm extension enabled after migration | integration | `docker exec geo-api-api-1 alembic upgrade head` + DB check | New test needed or manual verify |
| FUZZ-01 | GIN trigram indexes exist on openaddresses_points.street_name and nad_points.street_name | integration | DB index check query | Verify via `pg_indexes` query |

### Sampling Rate
- **Per task commit:** Quick run on modified provider test file(s)
- **Per wave merge:** `docker exec geo-api-api-1 python -m pytest tests/ -q` (full suite, expect 365+ passing, 11 pre-existing failures untouched)
- **Phase gate:** Full suite green (no new failures) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New test cases in `tests/test_tiger_provider.py` — covers FIX-01 county filter behavior (wrong-county → NO_MATCH, correct-county → match)
- [ ] New test cases in `tests/test_oa_provider.py` — covers FIX-02 zip prefix fallback, FIX-03 suffix matching, 5-tuple destructuring
- [ ] New test cases in `tests/test_nad_provider.py` — covers FIX-02 zip prefix fallback for NAD
- [ ] New test cases in `tests/test_macon_bibb_provider.py` — covers FIX-02 zip prefix fallback for Macon-Bibb
- [ ] Updated assertions in `tests/test_scourgify_provider.py` — `confidence == 1.0` must change to `== 0.3`
- [ ] Updated assertions in `tests/test_tiger_provider.py` — Tiger validation `confidence == 1.0` must change to `== 0.4`

---

## Sources

### Primary (HIGH confidence)
- Live code inspection: `src/civpulse_geo/providers/tiger.py`, `openaddresses.py`, `nad.py`, `macon_bibb.py`, `scourgify.py`, `schemas.py`
- Live DB query: `tiger.county` table schema, row count, SRID, ST_Contains behavior verified in `geo-api-db-1`
- Live code inspection: `alembic/versions/` — full migration chain mapped from `down_revision` fields
- Live DB test: pg_trgm extension available, GIN index syntax `gin (street_name gin_trgm_ops)` verified working
- Live Python test (in container): usaddress token labels `StreetNamePostType`, `StreetNamePostDirectional` verified
- Live Python test (in container): scourgify "Beaver Falls" → "BEAVER FLS" root cause confirmed

### Secondary (MEDIUM confidence)
- PostGIS documentation pattern for SRID mismatch: ST_Transform required when geometries are different SRIDs

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed in container; migration chain verified from source
- Architecture: HIGH — all patterns verified by live DB queries and code inspection; one open question on city→county name mapping
- Pitfalls: HIGH — SRID mismatch, tuple expansion, pg_trgm ordering all verified empirically

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable domain — PostGIS/SQLAlchemy patterns don't change rapidly)
