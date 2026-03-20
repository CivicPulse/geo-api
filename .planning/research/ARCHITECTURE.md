# Architecture Research

**Domain:** Local data source provider integration for geocoding/validation API
**Researched:** 2026-03-20
**Confidence:** HIGH (direct codebase inspection + verified PostGIS Tiger docs + data file inspection)

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Router Layer                              │
│   POST /geocode   POST /validate   POST /geocode/batch  ...      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                        Service Layer                              │
│                                                                   │
│  GeocodingService.geocode()         ValidationService.validate() │
│  ┌─────────────────────────────┐   ┌──────────────────────────┐  │
│  │  provider.is_local?         │   │  provider.is_local?      │  │
│  │  YES → call + return direct │   │  YES → call + return     │  │
│  │  NO  → cache-first pipeline │   │  NO  → cache-first       │  │
│  └─────────────────────────────┘   └──────────────────────────┘  │
└──────────────┬────────────────────────────┬──────────────────────┘
               │                            │
 ┌─────────────▼──────────────┐   ┌─────────▼────────────────────┐
 │   Remote Providers          │   │  Local Providers              │
 │  (HTTP + DB cache)          │   │  (no DB writes)               │
 │  ┌──────────────────┐       │   │  ┌───────────────────┐       │
 │  │ CensusGeocoding  │       │   │  │ OpenAddresses     │       │
 │  │ Provider         │       │   │  │ GeocodingProvider │       │
 │  └──────────────────┘       │   │  └───────────────────┘       │
 │  ┌──────────────────┐       │   │  ┌───────────────────┐       │
 │  │ Scourgify        │       │   │  │ NADGeocoding      │       │
 │  │ ValidationProv.  │       │   │  │ Provider          │       │
 │  └──────────────────┘       │   │  └───────────────────┘       │
 └────────────────────────────┘   │  ┌───────────────────┐       │
                                   │  │ TigerGeocoding    │       │
                                   │  │ Provider          │       │
                                   │  └───────────────────┘       │
                                   └──────────────────────────────┘
               │                            │
 ┌─────────────▼──────────────────────────────────────────────────┐
 │                        Data Layer                               │
 │  ┌──────────────────────┐   ┌──────────────────────────────┐   │
 │  │ PostgreSQL/PostGIS    │   │   Local Source Tables         │   │
 │  │ addresses             │   │   openaddresses_points        │   │
 │  │ geocoding_results     │   │   nad_points                  │   │
 │  │ official_geocoding    │   │   tiger.* (built-in schema)   │   │
 │  │ validation_results    │   └──────────────────────────────┘   │
 │  └──────────────────────┘                                        │
 └─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| `GeocodingProvider` ABC | Contract: `geocode()`, `batch_geocode()`, `provider_name` | Existing — minor addition only (`is_local` property) |
| `ValidationProvider` ABC | Contract: `validate()`, `batch_validate()`, `provider_name` | Existing — minor addition only (`is_local` property) |
| `GeocodingService.geocode()` | Dispatch: local providers bypass cache; remote providers use cache-first | **Modify** |
| `ValidationService.validate()` | Dispatch: local providers bypass cache; remote providers use cache-first | **Modify** |
| `load_providers()` / registry | Instantiate providers at startup; ABC enforcement | Existing — no changes |
| `main.py` lifespan | Register new provider instances | **Modify** |
| `OAGeocodingProvider` | Lookup in `openaddresses_points` PostGIS table | **New** |
| `OAValidationProvider` | Normalize from `openaddresses_points` result | **New** |
| `NADGeocodingProvider` | Lookup in `nad_points` PostGIS table | **New** |
| `NADValidationProvider` | Normalize from `nad_points` result | **New** |
| `TigerGeocodingProvider` | Call `tiger.geocode()` SQL function via async session | **New** |
| `TigerValidationProvider` | Call `tiger.standardize_address()` SQL function | **New** |
| CLI data loader commands | Bulk-load OpenAddresses GeoJSON.gz and NAD CSV into PostGIS tables | **New** |
| `openaddresses_points` table | Staging table: geom, street_number, street_name, city, postcode; spatial index | **New (migration)** |
| `nad_points` table | Staging table: geom, street_number, street_name, city, state, zip; spatial index | **New (migration)** |
| `Settings` | `openaddresses_data_dir`, `nad_data_path` config fields | **Modify** |

---

## Recommended Project Structure

```
src/civpulse_geo/
├── providers/
│   ├── base.py              # Existing — add is_local property with default False
│   ├── schemas.py           # Existing — GeocodingResult, ValidationResult dataclasses
│   ├── registry.py          # Existing — load_providers() unchanged
│   ├── census.py            # Existing — CensusGeocodingProvider unchanged
│   ├── scourgify.py         # Existing — ScourgifyValidationProvider unchanged
│   ├── openaddresses.py     # NEW — OAGeocodingProvider + OAValidationProvider
│   ├── nad.py               # NEW — NADGeocodingProvider + NADValidationProvider
│   └── tiger.py             # NEW — TigerGeocodingProvider + TigerValidationProvider
├── services/
│   ├── geocoding.py         # Modify — add local provider bypass path
│   └── validation.py        # Modify — add local provider bypass path
├── models/
│   ├── local_sources.py     # NEW — OpenAddressesPoint, NADPoint ORM models
│   └── ...                  # Existing unchanged
├── cli/
│   ├── parsers.py           # Existing — add load_geojson_lines() for NDJSON
│   └── commands.py          # NEW — load-oa, load-nad, setup-tiger CLI commands
├── config.py                # Modify — add data path settings
├── main.py                  # Modify — register new providers in lifespan
└── ...
```

### Structure Rationale

- **`providers/openaddresses.py`, `nad.py`, `tiger.py`:** Mirrors existing pattern (one file per provider). Each file contains both the geocoding and validation provider for that data source since they share lookup logic and staging table.
- **`models/local_sources.py`:** Separates staging-table ORM models from the application models. These are read-only lookup tables, not part of the geocoding cache schema.
- **`cli/commands.py`:** Data loading is a one-time operational task, not an API concern. Separate from `parsers.py` (which handles file reading, not DB loading).

---

## Architectural Patterns

### Pattern 1: Local Provider Identity Flag

**What:** Providers that skip DB caching implement an `is_local` property returning `True`. The service layer checks this before deciding whether to persist results.

**When to use:** Any provider whose results must not be stored in `geocoding_results` or `validation_results` tables.

**Trade-offs:** Minimal intrusion into existing ABCs. Adding the property to the base ABC with default `False` is backward-compatible — existing providers get `is_local = False` without code changes. An alternative (tagging by registry key prefix like "local_*") is less explicit and harder to test.

**Example:**

```python
# providers/base.py — add to GeocodingProvider and ValidationProvider ABCs
@property
def is_local(self) -> bool:
    """True if provider results must not be persisted to DB. Default False."""
    return False

# providers/openaddresses.py
class OAGeocodingProvider(GeocodingProvider):
    @property
    def is_local(self) -> bool:
        return True
```

### Pattern 2: Service-Layer Local Bypass

**What:** `GeocodingService.geocode()` and `ValidationService.validate()` split provider iteration into two passes: local providers (call + collect, no DB write) and remote providers (existing cache-first pipeline). The response merges results from both.

**When to use:** Required implementation for the "no caching for local providers" constraint.

**Trade-offs:** The service methods grow in complexity, but the split is well-bounded. An alternative — making services unaware of locality and having providers refuse to write to DB — would require providers to receive the DB session, breaking the clean separation.

**Cache hit subtlety:** The current service returns early on cache hit (existing remote results present). With local providers, the service must always call local providers even when remote results are cached. The cache check must be scoped to remote-only providers:

```python
# services/geocoding.py — modified provider iteration in geocode()
local_providers = {k: v for k, v in providers.items()
                   if isinstance(v, GeocodingProvider) and v.is_local}
remote_providers = {k: v for k, v in providers.items()
                    if isinstance(v, GeocodingProvider) and not v.is_local}

# Cache check applies only when there are no local providers in the request
if not force_refresh and address.geocoding_results and not local_providers:
    # Pure-remote request: full cache hit path (unchanged)
    ...
elif not force_refresh and address.geocoding_results and local_providers:
    # Hybrid: return cached remote results; still call local providers
    remote_orm_results = address.geocoding_results
    local_schema_results = [await _call_local(p, normalized, db) for p in local_providers.values()]
    # merge and return
```

**Response shape change:** The router currently builds `GeocodeProviderResult` Pydantic objects from ORM rows. After this change, the service should return a unified `list[GeocodeProviderResult]` (already serialized), not a mixed list of ORM rows and dataclasses. This simplifies the router and removes the ORM-dependency from the response path for local results.

### Pattern 3: Staging Tables with Spatial Indexes

**What:** OpenAddresses and NAD data are bulk-loaded into PostGIS staging tables at import time. Providers query these tables at request time.

**When to use:** Always preferred over file-based lookup for production use.

**Why not file lookup per request:** NAD has ~80M records at 38 GB uncompressed. Sequential file scan per request is non-viable at any meaningful concurrency. Even OpenAddresses files for a single state are millions of records.

**Lookup strategy (text-first, no initial coordinates):**

```sql
-- OpenAddresses: match by parsed components
SELECT street_number, street_name, city, postcode,
       ST_X(geom::geometry) AS lng, ST_Y(geom::geometry) AS lat
FROM openaddresses_points
WHERE postcode = $1
  AND street_name ILIKE $2
  AND street_number = $3
LIMIT 1;

-- NAD: similar, filtered by state for performance
SELECT street_number, street_name, city, state, zip_code,
       ST_X(geom::geometry) AS lng, ST_Y(geom::geometry) AS lat
FROM nad_points
WHERE state = $1
  AND zip_code = $2
  AND street_name ILIKE $3
  AND street_number = $4
LIMIT 1;
```

For addresses with no ZIP code, fall back to city + state filter. Index on `(state, street_name text_pattern_ops)` supports ILIKE prefix matching.

### Pattern 4: Tiger Provider via SQL Function Call

**What:** `TigerGeocodingProvider` calls the `tiger.geocode()` PostgreSQL function via `db.execute(text(...))`. The provider receives the async session rather than an `http_client`.

**Function signature (verified from PostGIS docs):**

```sql
-- Returns: norm_addy addy, geomout geometry (NAD83), rating integer
SELECT pprint_addy(addy), ST_Y(geomout), ST_X(geomout), rating
FROM tiger.geocode(:addr, 1)
ORDER BY rating LIMIT 1;
```

Rating is 0-100 where 0 = perfect match. A rating > 20 is typically a no-match.

**Session injection approach:** Pass `db` as a kwarg from the service layer to Tiger/OA/NAD providers only. The service is already aware of `is_local` (Pattern 2) and already holds `db`, so no new plumbing is needed. Provider `geocode()` signatures accept `**kwargs` to remain ABC-compatible:

```python
# providers/tiger.py
async def geocode(self, address: str, *, db: AsyncSession = None, **kwargs) -> GeocodingResult:
    ...
```

**Tiger availability check at startup:** Query `pg_extension` at lifespan start. If `postgis_tiger_geocoder` is absent, skip Tiger provider registration (log a warning). Do not crash — Tiger is optional.

```python
# main.py lifespan
async with db_session() as db:
    result = await db.execute(
        text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'postgis_tiger_geocoder'")
    )
    tiger_available = result.scalar() > 0

if tiger_available:
    providers["tiger"] = TigerGeocodingProvider()
else:
    logger.warning("postgis_tiger_geocoder extension not found — Tiger provider disabled")
```

### Pattern 5: Bulk Load via PostgreSQL COPY

**What:** OpenAddresses GeoJSON.gz (NDJSON) and NAD CSV are loaded into staging tables using PostgreSQL `COPY` via psycopg2 `copy_expert()` or asyncpg `copy_records_to_table()`. Row-by-row INSERT is ~100x slower for 10M+ rows.

**When to use:** All data loading CLI commands. Never called from the API.

**Format notes:**
- OpenAddresses `.geojson.gz` files are NDJSON (one GeoJSON Feature per line), NOT a FeatureCollection. The existing `load_geojson()` parser in `parsers.py` handles only FeatureCollections — a new `load_geojson_lines()` streaming variant is needed.
- NAD `NAD_r21.txt` is a CSV with BOM (`utf-8-sig`), 60 columns, ~80M rows. Only 7 columns are needed: `Add_Number`, `StNam_Full`, `Inc_Muni`, `State`, `Zip_Code`, `Longitude`, `Latitude`.

**Memory management:** Stream in chunks (10K-50K rows per COPY batch) to avoid loading the entire file into memory.

```python
# cli/commands.py — NAD load sketch
async def load_nad(conn: asyncpg.Connection, zip_path: Path, chunk_size: int = 50_000):
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("TXT/NAD_r21.txt") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            buffer = []
            for row in reader:
                if not row["Longitude"] or not row["Latitude"]:
                    continue
                buffer.append((
                    row["Add_Number"], row["StNam_Full"], row["Inc_Muni"],
                    row["State"], row["Zip_Code"],
                    float(row["Longitude"]), float(row["Latitude"])
                ))
                if len(buffer) >= chunk_size:
                    await conn.copy_records_to_table(
                        "nad_points",
                        records=buffer,
                        columns=["street_number","street_name","city","state",
                                 "zip_code","longitude","latitude"],
                    )
                    buffer.clear()
            if buffer:
                await conn.copy_records_to_table("nad_points", records=buffer, ...)
```

---

## Data Flow

### Request Flow: Remote Provider (Existing — Unchanged)

```
POST /geocode {address: "..."}
    |
    v
GeocodingService.geocode()
    | normalize + hash
    | find/create Address in DB
    | cache hit? -> return cached ORM rows + official
    | cache miss: call provider.geocode()
    | upsert GeocodingResult ORM row
    | auto-set OfficialGeocoding
    | commit
    v
return {results: [ORM rows], cache_hit: bool, official: ORM row}
```

### Request Flow: Local Provider (New — Bypass Path)

```
POST /geocode {address: "..."}
    |
    v
GeocodingService.geocode()
    | normalize + hash
    | find/create Address in DB  [still needed for address_hash in response]
    | iterate providers:
    |   if provider.is_local:
    |     call provider.geocode(normalized, db=db)  [OA/NAD queries PostGIS table]
    |     collect GeocodingResult dataclass -> NO DB write
    |   else:
    |     existing cache-first upsert path (unchanged)
    | commit only if remote providers ran
    v
return {
    results: [GeocodeProviderResult Pydantic objects (merged local + remote)],
    cache_hit: False  [local results are never cached],
    official: None or existing official from remote cache
}
```

**Key constraint:** The Address record IS still created for all requests (local or remote), because the router uses `address_hash` as the response key. What is skipped for local providers: writing `geocoding_results` rows and setting `official_geocoding`.

### Data Load Flow: OpenAddresses

```
CLI: uv run civpulse-geo load-oa data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz
    |
    For each .geojson.gz file:
        open with gzip, read line by line (NDJSON: one Feature per line)
        parse each line as GeoJSON Feature
        extract: number, street, unit, city, postcode, lon, lat (from geometry.coordinates)
        buffer rows (chunk: 10,000)
        COPY chunk -> openaddresses_points (ON CONFLICT DO NOTHING on source_hash)
```

### Data Load Flow: NAD

```
CLI: uv run civpulse-geo load-nad data/NAD_r21_TXT.zip
    |
    Open ZIP, stream TXT/NAD_r21.txt
        parse CSV header (utf-8-sig BOM)
        extract 7 of 60 columns: Add_Number, StNam_Full, Inc_Muni, State, Zip_Code, Longitude, Latitude
        skip rows missing Longitude or Latitude
        buffer rows (chunk: 50,000)
        COPY chunk -> nad_points
    Total: ~80M records, ~38 GB uncompressed
    Estimated load time: 20-40 min on typical hardware
```

---

## New Components

### New: `openaddresses_points` Table (migration)

```sql
CREATE TABLE openaddresses_points (
    id            BIGSERIAL PRIMARY KEY,
    street_number TEXT,
    street_name   TEXT NOT NULL,
    unit          TEXT,
    city          TEXT,
    postcode      TEXT,
    geom          geography(POINT, 4326) NOT NULL,
    source_hash   TEXT UNIQUE  -- OpenAddresses "hash" field, for dedup on re-load
);
CREATE INDEX idx_oa_geom     ON openaddresses_points USING GIST (geom);
CREATE INDEX idx_oa_postcode ON openaddresses_points (postcode);
CREATE INDEX idx_oa_street   ON openaddresses_points (street_name text_pattern_ops);
```

Note: GiST index must be added manually in Alembic migration — Alembic autogenerate does not emit spatial indexes.

### New: `nad_points` Table (migration)

```sql
CREATE TABLE nad_points (
    id            BIGSERIAL PRIMARY KEY,
    street_number TEXT,
    street_name   TEXT NOT NULL,
    city          TEXT,
    state         CHAR(2),
    zip_code      TEXT,
    geom          geography(POINT, 4326) NOT NULL
    -- No unique constraint: NAD has duplicate addresses from multiple contributors
);
CREATE INDEX idx_nad_geom         ON nad_points USING GIST (geom);
CREATE INDEX idx_nad_zip          ON nad_points (zip_code);
CREATE INDEX idx_nad_state_street ON nad_points (state, street_name text_pattern_ops);
```

### New: `providers/openaddresses.py`

Two classes: `OAGeocodingProvider(GeocodingProvider)` and `OAValidationProvider(ValidationProvider)`. Both receive `db: AsyncSession` as a kwarg. Lookup: text-match on street_number + street_name + postcode against `openaddresses_points`. The OA GeoJSON `hash` property is used for load-time dedup.

### New: `providers/nad.py`

Two classes: `NADGeocodingProvider(GeocodingProvider)` and `NADValidationProvider(ValidationProvider)`. Same DB-injection pattern. The NAD `StNam_Full` column includes direction and type suffix (e.g., "Sand Point Avenue"), so lookup uses ILIKE with `%` or requires parsing the address string into components before querying.

### New: `providers/tiger.py`

Two classes: `TigerGeocodingProvider(GeocodingProvider)` and `TigerValidationProvider(ValidationProvider)`. Calls `tiger.geocode()` and `tiger.standardize_address()` SQL functions via `db.execute(text(...))`. Handles the case where the Tiger extension is not installed (returns NO_MATCH, does not crash).

### New: `cli/commands.py`

Typer commands:
- `load-oa [paths...]` — load OpenAddresses GeoJSON.gz files into `openaddresses_points`
- `load-nad [path]` — load NAD TXT zip into `nad_points`
- `setup-tiger` — print or execute Tiger data loader setup instructions

### Modified: `cli/parsers.py`

Add `load_geojson_lines(path: Path) -> Iterator[dict]` for NDJSON streaming. The existing `load_geojson()` reads a full FeatureCollection and returns a `list` — not suitable for NDJSON files or memory-efficient streaming.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| PostGIS Tiger schema | `db.execute(text("SELECT ... FROM tiger.geocode(...)"))` | Requires `postgis_tiger_geocoder`, `fuzzystrmatch`, `address_standardizer` extensions AND Tiger/Line data loaded. Check `pg_extension` at startup; fail gracefully if absent. |
| OpenAddresses `.geojson.gz` | NDJSON streaming at load time; PostGIS table query at request time | One GeoJSON Feature per line (NOT a FeatureCollection). Existing `load_geojson()` does not handle NDJSON — new streaming parser needed. |
| NAD `NAD_r21_TXT.zip` | CSV streaming at load time; PostGIS table query at request time | BOM (utf-8-sig), 60 columns, ~80M rows / 38 GB uncompressed. Only 7 columns needed. No unique key — duplicate addresses exist across contributor datasets. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Service layer -> local providers | `provider.geocode(address, db=db)` | Session passed as kwarg. ABC `geocode(address)` signature technically honored; implementations accept `**kwargs`. |
| Service layer -> router | Returns `list[GeocodeProviderResult]` (Pydantic, pre-serialized) for local results | Currently the router builds `GeocodeProviderResult` from ORM rows. With mixed local+remote, the service should emit pre-built Pydantic objects so the router does not need to branch on ORM vs dataclass. |
| CLI loaders -> database | Synchronous psycopg2 `copy_expert()` OR async asyncpg `copy_records_to_table()` | COPY requires direct connection, not SQLAlchemy ORM. Consistent with existing Alembic pattern (sync psycopg2). |
| New migrations -> Alembic | `alembic revision --autogenerate` detects `openaddresses_points` and `nad_points` | GiST (spatial) indexes must be written manually in the migration file — Alembic does not autogenerate them. |
| Tiger provider -> `main.py` | Conditional registration based on `pg_extension` check at startup | Tiger is optional; the app must start and serve requests even when Tiger is not configured. |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single region (county/city) | Load only relevant state OpenAddresses files + filter NAD by state at load time. Tables will be O(100K-1M) rows — all queries fast. |
| National (all 50 states) | `openaddresses_points` ~200M rows, `nad_points` ~80M rows. Partition tables by state (PostgreSQL range partition on `state` column) to keep index sizes manageable per partition. |
| High request volume | Local providers hit PostGIS on every request (no response cache). Add asyncpg connection pooling. Tiger `geocode()` is CPU-intensive PL/pgSQL — consider a Tiger-dedicated DB connection pool or rate limiting. |

---

## Anti-Patterns

### Anti-Pattern 1: File Lookup Per Request

**What people do:** Hold a reference to the open `.geojson.gz` or CSV and scan it on every geocode call.

**Why it's wrong:** NAD has ~80M records at 38 GB uncompressed. Sequential scan per request at any meaningful concurrency is seconds per call. Even a 100K-row county file cannot be scanned concurrently without memory pressure.

**Do this instead:** Load into PostGIS tables at import time. GIST spatial indexes reduce per-request lookups to milliseconds.

### Anti-Pattern 2: Writing Local Provider Results to DB

**What people do:** Pass local providers through the same `_upsert_geocoding_result()` path as remote providers.

**Why it's wrong:** Violates the key design constraint. Caching local results consumes space for data already available on disk, and creates staleness when source data is re-loaded.

**Do this instead:** The `is_local` flag (Pattern 1) ensures the service layer never writes local results to `geocoding_results` or `validation_results`.

### Anti-Pattern 3: Setting OfficialGeocoding from Local Results

**What people do:** Treat the first successful local provider result as the `official_geocoding` record for an address.

**Why it's wrong:** `OfficialGeocoding` is a persistent record with admin override semantics. Local providers may return different results when source data changes (re-loaded). Persisting this as "official" creates inconsistency between response and stored state.

**Do this instead:** Local provider results appear in the `results` array but are never written to `official_geocoding`. The `official` field in the response is always derived from cached remote results or an explicit admin override.

### Anti-Pattern 4: Crashing at Startup When Tiger Is Absent

**What people do:** Register `TigerGeocodingProvider` unconditionally; the first request fails with `ProgrammingError: relation "tiger.geocode" does not exist`.

**Why it's wrong:** Tiger setup is complex (requires TIGER/Line data download, several hundred MB to multiple GB per state, and a multi-step loader process). Most dev environments will not have it.

**Do this instead:** Check `pg_extension` at startup. If `postgis_tiger_geocoder` is absent, skip Tiger provider registration and log a warning. The API starts and serves requests normally without Tiger.

### Anti-Pattern 5: Running NAD Load Inside the API Process

**What people do:** Expose a `POST /admin/load-nad` endpoint that streams the NAD ZIP into the DB.

**Why it's wrong:** NAD load is a 20-40 minute operation. It must not run inside a web request or the lifespan context — it would block the event loop or hold a long-lived connection inappropriately.

**Do this instead:** NAD and OA load are CLI-only operations implemented as Typer commands using synchronous psycopg2 `COPY`, entirely separate from the FastAPI application process.

---

## Build Order

Based on component dependencies, the recommended implementation order is:

1. **Alembic migrations** — `openaddresses_points` and `nad_points` tables with spatial indexes. All other components depend on these tables existing.
2. **`parsers.py` — add `load_geojson_lines()`** — NDJSON streaming variant. Needed by the OA loader CLI command.
3. **CLI data loaders** — `load-oa` (OpenAddresses) first, then `load-nad`. OpenAddresses is smaller (county-level files are fast) and provides early feedback on the table design and lookup queries.
4. **`base.py` modification** — add `is_local` property with default `False`. Non-breaking; existing providers inherit the default.
5. **`providers/openaddresses.py`** — simplest local providers: text lookup against the table populated in step 3. Validates the service-layer bypass pattern before touching the service layer.
6. **Service layer modification** — add `is_local` bypass in `geocoding.py` and `validation.py`. Can be developed and tested immediately after step 5.
7. **`providers/nad.py`** — same pattern as OA with different table schema.
8. **`providers/tiger.py`** — most complex: optional extension, PL/pgSQL function call, rating-to-confidence mapping. Implement last; graceful fallback when Tiger is absent.
9. **`main.py` registration** — register all new providers in lifespan with Tiger availability check.
10. **Tiger setup documentation/scripts** — optional; documents the Tiger data loading process separately from the provider code.

---

## Sources

- PostGIS Tiger geocoder function reference: [postgis.net/docs/Geocode.html](https://postgis.net/docs/Geocode.html) — HIGH confidence (official docs)
- Tiger geocoder setup: [blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup](https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup) — MEDIUM confidence (third-party, current)
- PostGIS extras documentation: [postgis.net/docs/Extras.html](https://postgis.net/docs/Extras.html) — HIGH confidence (official docs)
- NAD size and record count: [transportation.gov/gis/national-address-database](https://www.transportation.gov/gis/national-address-database) — HIGH confidence (official DOT source; confirmed by local file inspection: 38.5 GB uncompressed)
- OpenAddresses NDJSON format: [stevage.github.io/ndgeojson](https://stevage.github.io/ndgeojson/) — HIGH confidence (confirmed by local file inspection of `US_GA_Bibb_Addresses_2026-03-20.geojson.gz`)
- Direct codebase inspection: `providers/base.py`, `services/geocoding.py`, `services/validation.py`, `providers/census.py`, `providers/scourgify.py`, `main.py`, `cli/parsers.py`, `data/NAD_r21_TXT.zip` (60 columns confirmed), `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` (NDJSON format confirmed) — HIGH confidence (live code and data)

---

*Architecture research for: CivPulse Geo API — v1.1 Local Data Sources milestone*
*Researched: 2026-03-20*
