# Phase 9: Tiger Provider - Research

**Researched:** 2026-03-24
**Domain:** PostGIS Tiger Geocoder SQL functions, FastAPI async provider pattern, Typer CLI
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Graceful degradation**
- When Tiger extensions are installed but no data is loaded for the requested state: return NO_MATCH result (confidence=0.0, location_type=None) — consistent with Census and OA miss behavior
- When Tiger extensions are NOT installed: do not register the provider at all. Log a warning at startup. Provider does not appear in the provider list (per TIGR-04)
- Extension check at startup via `SELECT * FROM pg_available_extensions WHERE name = 'postgis_tiger_geocoder'` — check only the main extension (CASCADE dependencies install automatically)
- Extension check runs during FastAPI lifespan, before provider registration
- Tiger `geocode()` returns SETOF: take best result only (`LIMIT 1 ORDER BY rating ASC`)

**Setup script (setup-tiger)**
- Full automation: CLI command that (1) installs extensions via SQL, (2) calls `Loader_Generate_Script()` for specified state(s), (3) executes the generated script to download and load data
- Takes state FIPS codes as arguments: e.g., `setup-tiger 13` for Georgia, `setup-tiger 13 01` for GA + AL
- Fully idempotent: `CREATE EXTENSION IF NOT EXISTS`, skip already-loaded states, safe to re-run
- Runs inside Docker container (postgis/postgis image has shp2pgsql and wget available) — invoked via `docker compose exec`

**Confidence and result mapping**
- Linear mapping: `confidence = (100 - rating) / 100` where Tiger rating 0 = best match (confidence 1.0), rating 100 = worst match (confidence 0.0). Research phase must verify this against PostGIS docs.
- `location_type` = RANGE_INTERPOLATED for all Tiger geocoding results — Tiger interpolates along street ranges, does not provide rooftop/parcel precision
- Validation via `normalize_address()` returns address components only, no coordinates — consistent with scourgify validation pattern

**Provider naming**
- `provider_name` = "postgis_tiger" for both geocoding and validation providers
- `raw_response` contains full norm_addy fields (address, predirAbbrev, streetName, streetTypeAbbrev, location, stateAbbrev, zip, zip4, parsed) plus rating integer

**Testing strategy**
- Unit tests: mock async session to return fake geocode()/normalize_address() result tuples — same pattern as OA provider tests
- Integration tests: marked with `@pytest.mark.tiger`, skipped unless Tiger data is present
- Unit mocks always run; integration tests are optional

**Docker integration**
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

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TIGR-01 | User can geocode an address via PostGIS Tiger geocode() function | SQL pattern for geocode() + composite type unpacking verified from PostGIS docs |
| TIGR-02 | User can validate/normalize an address via PostGIS normalize_address() | SQL pattern for normalize_address() + norm_addy fields verified from PostGIS docs |
| TIGR-03 | Tiger geocoding maps rating score to confidence (0=best -> 1.0 confidence) | Verified: rating 0 = exact match = confidence 1.0; linear mapping confirmed |
| TIGR-04 | Tiger provider degrades gracefully when extension/data not installed | Extension check via pg_available_extensions verified; NO_MATCH pattern established in OA provider |
| TIGR-05 | Setup scripts install Tiger extensions and load data per state | Loader_Generate_Script API verified; CRITICAL: takes state abbreviations not FIPS codes |
</phase_requirements>

---

## Summary

Phase 9 implements two providers (`TigerGeocodingProvider` and `TigerValidationProvider`) that call PostGIS SQL functions (`geocode()` and `normalize_address()`) rather than querying a staging table. The architecture closely mirrors the OA provider pattern established in Phase 8: both providers are `is_local=True`, inject `async_sessionmaker`, use raw `text()` queries, and return `NO_MATCH` on miss. The key difference is that Tiger calls SQL functions returning composite types (`norm_addy`) rather than querying ORM-mapped table rows.

The `setup-tiger` CLI command orchestrates three steps: install extensions via `CREATE EXTENSION IF NOT EXISTS`, generate a download/load shell script via `Loader_Generate_Script()`, and execute that script inside the running Docker container. The PostGIS Docker image (`postgis/postgis:17-3.5`) already includes all required extensions — confirmed via Dockerfile inspection. A docker-compose init script will install extensions and load Georgia data automatically on first startup.

**Critical finding:** `Loader_Generate_Script()` accepts **2-letter state abbreviations** (e.g., `'GA'`), not FIPS numeric codes (e.g., `13`). The CONTEXT.md describes the CLI accepting FIPS codes as user-facing arguments — the implementation must therefore convert FIPS codes to state abbreviations before calling `Loader_Generate_Script()`.

**Primary recommendation:** Follow the OA provider pattern exactly for class structure and session injection; use `sqlalchemy.text()` with named bind parameters for SQL function calls; build a FIPS-to-abbreviation lookup dict for the CLI conversion; implement the Docker init script as a shell script in `initdb.d/` directory.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlalchemy (async) | 2.0.48 (already installed) | Async DB session, `text()` for raw SQL | Project standard; used by all providers |
| asyncpg | 0.31.0 (already installed) | Async PostgreSQL driver for API path | Project standard; used by existing providers |
| psycopg2-binary | 2.9.11 (already installed) | Sync engine for CLI commands | Project standard; used by load-oa and load-nad |
| typer | 0.24.1 (already installed) | CLI framework for setup-tiger command | Project standard; used by existing CLI |
| loguru | 0.7.3 (already installed) | Structured logging for startup warnings | Project standard |

### No New Python Dependencies Required

The Tiger provider requires zero new Python packages. All necessary libraries are already installed:
- PostGIS SQL functions called via `session.execute(text(...))` — no Python Tiger client exists or is needed
- Shell script generation/execution uses stdlib `subprocess`
- Extension check uses `text()` query against `pg_available_extensions`

**Version verification:** All packages confirmed from existing `pyproject.toml`. No new `pip install` required.

---

## Architecture Patterns

### Recommended Project Structure

```
src/civpulse_geo/
├── providers/
│   ├── tiger.py            # NEW: TigerGeocodingProvider + TigerValidationProvider
│   ├── openaddresses.py    # Reference pattern (existing)
│   ├── base.py             # ABCs (existing)
│   ├── schemas.py          # GeocodingResult, ValidationResult (existing)
│   └── exceptions.py       # ProviderError hierarchy (existing)
├── main.py                 # ADD: conditional Tiger registration in lifespan
└── cli/
    └── __init__.py         # ADD: setup-tiger command

tests/
├── test_tiger_provider.py  # NEW: unit tests (mock pattern)
└── conftest.py             # ADD: @pytest.mark.tiger marker registration
```

### Pattern 1: TigerGeocodingProvider — SQL Function Call

**What:** Calls `geocode()` via raw `text()` query, extracts composite `addy` fields and coordinates in a single SELECT.
**When to use:** All Tiger geocoding. Always `is_local=True`.

```python
# Source: PostGIS docs https://postgis.net/docs/Geocode.html
# Pattern confirmed from dev.to/cincybc article

GEOCODE_SQL = text("""
    SELECT
        rating,
        ST_Y(geomout) AS lat,
        ST_X(geomout) AS lng,
        (addy).address        AS address_number,
        (addy).predirabbrev   AS predir,
        (addy).streetname     AS street_name,
        (addy).streettypeabbrev AS street_type,
        (addy).postdirabbrev  AS postdir,
        (addy).internal       AS internal,
        (addy).location       AS city,
        (addy).stateabbrev    AS state,
        (addy).zip            AS zip,
        (addy).zip4           AS zip4,
        (addy).parsed         AS parsed
    FROM geocode(:address, 1)
    ORDER BY rating ASC
    LIMIT 1
""")

async def geocode(self, address: str, **kwargs: Any) -> GeocodingResult:
    try:
        async with self._session_factory() as session:
            result = await session.execute(GEOCODE_SQL, {"address": address})
            row = result.first()
    except SQLAlchemyError as e:
        raise ProviderError(f"Tiger geocode query failed: {e}") from e

    if row is None:
        return _no_match_result(self.provider_name)

    confidence = (100 - row.rating) / 100
    raw_response = {
        "rating": row.rating,
        "address": row.address_number,
        ...
    }
    return GeocodingResult(
        lat=row.lat,
        lng=row.lng,
        location_type="RANGE_INTERPOLATED",
        confidence=max(0.0, min(1.0, confidence)),
        raw_response=raw_response,
        provider_name=self.provider_name,
    )
```

### Pattern 2: TigerValidationProvider — normalize_address()

**What:** Calls `normalize_address()` via raw `text()` query, returns parsed address components as `ValidationResult`.
**When to use:** All Tiger validation. Returns address components only, no coordinates.

```python
# Source: PostGIS docs https://postgis.net/docs/Normalize_Address.html

NORMALIZE_SQL = text("""
    SELECT
        (na).address          AS address_number,
        (na).predirabbrev     AS predir,
        (na).streetname       AS street_name,
        (na).streettypeabbrev AS street_type,
        (na).postdirabbrev    AS postdir,
        (na).internal         AS internal,
        (na).location         AS city,
        (na).stateabbrev      AS state,
        (na).zip              AS zip,
        (na).zip4             AS zip4,
        (na).parsed           AS parsed
    FROM normalize_address(:address) AS na
""")

async def validate(self, address: str, **kwargs: Any) -> ValidationResult:
    try:
        async with self._session_factory() as session:
            result = await session.execute(NORMALIZE_SQL, {"address": address})
            row = result.first()
    except SQLAlchemyError as e:
        raise ProviderError(f"Tiger normalize_address query failed: {e}") from e

    if row is None or not row.parsed:
        return _no_match_validation(address, self.provider_name)

    address_line_1 = " ".join(filter(None, [
        str(row.address_number) if row.address_number else None,
        row.predir,
        row.street_name,
        row.street_type,
        row.postdir,
    ]))
    # Build ValidationResult from norm_addy fields
    ...
```

### Pattern 3: Conditional Provider Registration in Lifespan

**What:** Check `pg_available_extensions` before instantiating Tiger providers. Log warning if absent, skip registration entirely.
**When to use:** FastAPI startup (lifespan function in main.py).

```python
# Source: CONTEXT.md decision; pg_available_extensions is standard PostgreSQL system catalog

async def _tiger_extension_available(session_factory: async_sessionmaker) -> bool:
    """Return True if postgis_tiger_geocoder is available in this PostgreSQL instance."""
    CHECK_SQL = text("""
        SELECT 1 FROM pg_available_extensions
        WHERE name = 'postgis_tiger_geocoder'
    """)
    try:
        async with session_factory() as session:
            result = await session.execute(CHECK_SQL)
            return result.first() is not None
    except Exception:
        return False

# In lifespan:
if await _tiger_extension_available(AsyncSessionLocal):
    app.state.providers["postgis_tiger"] = TigerGeocodingProvider(AsyncSessionLocal)
    app.state.validation_providers["postgis_tiger"] = TigerValidationProvider(AsyncSessionLocal)
    logger.info("Tiger geocoder provider registered")
else:
    logger.warning(
        "postgis_tiger_geocoder extension not available — Tiger provider not registered"
    )
```

### Pattern 4: setup-tiger CLI Command

**What:** Typer command that installs Tiger extensions and loads state data inside Docker container.
**When to use:** `geo-import setup-tiger GA` (after FIPS-to-abbrev research finding below).

```python
# Source: PostGIS Loader_Generate_Script docs; CONTEXT.md decisions

FIPS_TO_ABBREV = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY",
}

@app.command("setup-tiger")
def setup_tiger(
    states: list[str] = typer.Argument(..., help="State FIPS codes (e.g., 13 for GA)"),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
    ),
) -> None:
    """Install Tiger extensions and load TIGER/Line data for specified state(s)."""
    # 1. Convert FIPS codes to abbreviations
    abbrevs = []
    for fips in states:
        abbrev = FIPS_TO_ABBREV.get(fips.zfill(2))
        if abbrev is None:
            typer.echo(f"Unknown FIPS code: {fips}", err=True)
            raise typer.Exit(1)
        abbrevs.append(abbrev)

    # 2. Install extensions
    engine = create_engine(database_url or settings.database_url_sync)
    with engine.connect() as conn:
        for ext in ["postgis", "fuzzystrmatch", "address_standardizer",
                    "address_standardizer_data_us", "postgis_tiger_geocoder"]:
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        conn.commit()

    # 3. Generate and execute load script per state
    with engine.connect() as conn:
        for abbrev in abbrevs:
            result = conn.execute(
                text("SELECT Loader_Generate_Script(ARRAY[:state], 'sh')"),
                {"state": abbrev}
            )
            script_text = result.scalar()
            # Execute inside Docker container
            subprocess.run(["bash", "-c", script_text], check=True)
```

### Pattern 5: Docker Init Script for Extensions + GA Data

**What:** Shell script placed in `/docker-entrypoint-initdb.d/` that installs extensions and triggers GA Tiger data load on first container startup.
**When to use:** Docker development environment.

```bash
# docker-entrypoint-initdb.d/20_tiger_setup.sh
# Runs automatically on first postgres container startup (initdb.d/ pattern)
#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
    CREATE EXTENSION IF NOT EXISTS address_standardizer;
    CREATE EXTENSION IF NOT EXISTS address_standardizer_data_us;
    CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
EOSQL
# Load GA data (runs the generated loader script inside container)
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -A -t \
  -c "SELECT Loader_Generate_Script(ARRAY['GA'], 'sh')" | bash
```

### Anti-Patterns to Avoid

- **Parsing norm_addy as a string:** The `addy` column in `geocode()` output is a composite type — access fields with `(addy).fieldname` syntax in SQL, NOT by string parsing in Python
- **Using geocode() without LIMIT 1:** `geocode()` returns SETOF up to `max_results` rows; always use `LIMIT 1 ORDER BY rating ASC` to get the best match
- **Passing `max_results=1` without ORDER BY:** The function already sorts by rating internally, but explicit `ORDER BY rating ASC LIMIT 1` is defensive and makes intent clear
- **Registering Tiger provider unconditionally:** The extension check is required — absence of `postgis_tiger_geocoder` in `pg_available_extensions` means the SQL functions don't exist and calling them raises `ProgrammingError`
- **Passing FIPS codes to Loader_Generate_Script:** The function requires 2-letter state abbreviations, not numeric FIPS codes

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Address geocoding | Custom address parser + coordinate lookup | `geocode()` PostGIS SQL function | Tiger handles street range interpolation, fuzzy matching, and rating all internally |
| Address normalization | Custom regex parser | `normalize_address()` PostGIS SQL function | Returns USPS-compliant parsed components from same Tiger database |
| Extension installation | Custom extension existence check | `CREATE EXTENSION IF NOT EXISTS` | Idempotent by design; no need for manual pre-check |
| State data download | Custom census.gov downloader | `Loader_Generate_Script()` | Generates wget-based scripts that handle all Census FTP paths, state structure, and shp2pgsql loading |
| Confidence scoring | Custom match quality algorithm | Linear rating-to-confidence formula | Tiger's `rating` is already a calibrated quality metric (0=best, 100=worst)

**Key insight:** Tiger is a SQL-first geocoder — all the hard work (street range interpolation, fuzzy name matching, ZIP code lookups) happens inside PostGIS. The Python provider is a thin wrapper that calls the SQL function and maps the result to the project's schema types.

---

## Common Pitfalls

### Pitfall 1: Loader_Generate_Script Takes Abbreviations, Not FIPS Codes

**What goes wrong:** Calling `Loader_Generate_Script(ARRAY['13'], 'sh')` with a FIPS code returns an empty result or loads nothing — the function looks up state by abbreviation in its internal `tiger.state_all` table.
**Why it happens:** The CONTEXT.md user decision describes the CLI as accepting "state FIPS codes as arguments" (the external interface) but `Loader_Generate_Script` itself requires abbreviations.
**How to avoid:** Implement a `FIPS_TO_ABBREV` lookup dict in the CLI. Convert before calling `Loader_Generate_Script`. Accept both formats gracefully (2-char strings pass through directly; 2-digit numeric strings are looked up).
**Warning signs:** `Loader_Generate_Script` returns NULL or empty string for a given state.

### Pitfall 2: geocode() Returns Empty SETOF When No Data Loaded

**What goes wrong:** When Tiger extension is installed but no state data has been loaded into `tiger_data.*` tables, `geocode()` returns zero rows (not an error). This is the desired NO_MATCH behavior but must not be confused with a SQL error.
**Why it happens:** `geocode()` returns SETOF — zero rows is a valid empty result set, not an exception.
**How to avoid:** Check `row = result.first()` — if `None`, return `NO_MATCH` with `confidence=0.0`. Do not wrap in a "was extension installed?" guard; let the SQL execute normally.
**Warning signs:** Provider always returns NO_MATCH even for valid addresses (data not loaded for that state).

### Pitfall 3: norm_addy `parsed=False` on Garbage Input

**What goes wrong:** `normalize_address()` never raises an exception — it returns a `norm_addy` record with `parsed=False` when it cannot parse the input. If `parsed=False` is not checked, the provider returns a ValidationResult with all-None components.
**Why it happens:** PostGIS Tiger normalizer is lenient — it attempts to parse everything and signals failure via the `parsed` flag.
**How to avoid:** Check `row.parsed` after the query. If `False` or `None`, return NO_MATCH ValidationResult (confidence=0.0).
**Warning signs:** ValidationResult with `address_line_1=""`, `city=None`, `state=None` for invalid inputs.

### Pitfall 4: Tiger Rating Can Exceed 100

**What goes wrong:** While the linear mapping `confidence = (100 - rating) / 100` works well for ratings 0–100, Tiger can return ratings above 100 for poor matches (e.g., rating 108 seen in official PostGIS docs).
**Why it happens:** Tiger's scoring is not capped at 100 — higher values indicate increasingly poor matches.
**How to avoid:** Clamp the result: `confidence = max(0.0, min(1.0, (100 - rating) / 100))`. Ratings above 100 produce negative confidence which clamps to 0.0.
**Warning signs:** Negative confidence values in raw_response.rating for very poor matches.

### Pitfall 5: asyncpg and PostgreSQL Composite Types

**What goes wrong:** When using raw `text()` queries via asyncpg, accessing composite type columns (like the raw `addy` column from `geocode()`) may return a string representation rather than a structured object. The `(addy).fieldname` SQL expansion avoids this entirely.
**Why it happens:** asyncpg maps PostgreSQL composite types to string representations by default.
**How to avoid:** Always expand composite type fields in SQL using `(addy).fieldname` notation. Never try to Python-parse the composite type string. The SELECT pattern with named scalar columns (rating, lat, lng, street_name, etc.) returns plain scalar values that asyncpg/SQLAlchemy handle natively.
**Warning signs:** Row fields returning values like `(123,N,MAIN,ST,,,,MACON,GA,31201,t,,,)`.

### Pitfall 6: No pytest.mark.tiger Registration

**What goes wrong:** Using `@pytest.mark.tiger` without registering the marker causes pytest to emit `PytestUnknownMarkWarning` for every test.
**Why it happens:** pytest requires all custom markers to be registered in `pyproject.toml` or `pytest.ini`.
**How to avoid:** Add `markers = ["tiger: marks tests that require Tiger/Line data loaded (skipped otherwise)"]` to the `[tool.pytest.ini_options]` section in `pyproject.toml`.
**Warning signs:** `PytestUnknownMarkWarning: Unknown pytest.mark.tiger` in test output.

### Pitfall 7: Docker initdb.d Scripts Only Run on First Startup

**What goes wrong:** Changes to the Tiger init script are not applied when restarting an existing container with a named volume.
**Why it happens:** `docker-entrypoint-initdb.d/` scripts only run when the data directory is initialized (first `docker compose up`).
**How to avoid:** Document this. Users must `docker compose down -v` to destroy the postgres_data volume and force re-initialization. Alternatively, make extensions installable separately via `setup-tiger` CLI.
**Warning signs:** Tiger extension appears missing after modifying the init script without destroying the volume.

---

## Code Examples

Verified patterns from official PostGIS documentation:

### geocode() Query — Scalar Column Expansion

```sql
-- Source: https://postgis.net/docs/Geocode.html
-- Source: https://dev.to/cincybc/create-your-own-geocoder-with-postgistiger-3anc
SELECT
    rating,
    ST_Y(geomout) AS lat,
    ST_X(geomout) AS lng,
    (addy).address        AS address_number,
    (addy).predirabbrev   AS predir,
    (addy).streetname     AS street_name,
    (addy).streettypeabbrev AS street_type,
    (addy).postdirabbrev  AS postdir,
    (addy).internal       AS internal,
    (addy).location       AS city,
    (addy).stateabbrev    AS state,
    (addy).zip            AS zip,
    (addy).zip4           AS zip4,
    (addy).parsed         AS parsed
FROM geocode('45 Rockefeller Plaza, New York, NY 10111', 1) AS g
ORDER BY rating ASC
LIMIT 1;
```

### normalize_address() Query — Scalar Column Expansion

```sql
-- Source: https://postgis.net/docs/Normalize_Address.html
SELECT
    (na).address          AS address_number,
    (na).predirabbrev     AS predir,
    (na).streetname       AS street_name,
    (na).streettypeabbrev AS street_type,
    (na).postdirabbrev    AS postdir,
    (na).internal         AS internal,
    (na).location         AS city,
    (na).stateabbrev      AS state,
    (na).zip              AS zip,
    (na).zip4             AS zip4,
    (na).parsed           AS parsed
FROM normalize_address('1 Devonshire Place, Boston, MA 02109') AS na;
```

### Extension Check Query

```sql
-- Source: CONTEXT.md decision; pg_available_extensions is a standard PostgreSQL system catalog view
SELECT 1 FROM pg_available_extensions
WHERE name = 'postgis_tiger_geocoder';
```

### Loader_Generate_Script Usage

```sql
-- Source: https://postgis.net/docs/Loader_Generate_Script.html
-- Note: Takes STATE ABBREVIATIONS, not FIPS codes
SELECT Loader_Generate_Script(ARRAY['GA'], 'sh');
-- Returns: multi-line shell script text for download + load into tiger_data schema
```

### Confidence Calculation

```python
# Source: CONTEXT.md decision; verified against PostGIS rating semantics
# Tiger rating: 0 = exact match, higher = worse match, can exceed 100
# Clamp to [0.0, 1.0] to handle super-ratings (108+ documented in PostGIS examples)
confidence = max(0.0, min(1.0, (100 - rating) / 100))
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct composite type access from `geocode()` | Scalar column expansion `(addy).fieldname` in SELECT | PostGIS 2.x+ | Avoids asyncpg composite type mapping issues entirely |
| Separate `CREATE EXTENSION` checks before install | `CREATE EXTENSION IF NOT EXISTS` | PostgreSQL 9.3+ | Idempotent; safe to re-run without error checking |
| Custom Tiger data download scripts | `Loader_Generate_Script()` | PostGIS 2.0+ | Generates wget/shp2pgsql scripts aligned with current Census FTP structure |

**Deprecated/outdated:**
- TIGER 2023+ format: PostGIS `shp2pgsql` cannot consume 2023+ format TIGER files as of early 2024. `Loader_Generate_Script` is configured to download 2022 data. This is documented upstream — not a blocker, but affects recency of address data.
- `Loader_Generate_Census_Script`: Separate function for census blocks/tracts; not needed for address geocoding.

---

## Open Questions

1. **FIPS vs abbreviation in CLI interface**
   - What we know: `Loader_Generate_Script` requires 2-letter abbreviations. CONTEXT.md specifies FIPS code user interface.
   - What's unclear: Whether the CLI should also accept abbreviations directly (e.g., `setup-tiger GA`) or strictly FIPS only.
   - Recommendation: Accept both — if input is 2 alpha chars, treat as abbreviation; if 2 numeric chars, look up in FIPS dict. This is Claude's Discretion territory.

2. **Tiger data load time in Docker**
   - What we know: GA Tiger data is ~200MB. Loading in initdb.d on first startup blocks container ready state.
   - What's unclear: Whether the healthcheck timeout is sufficient or if the first `docker compose up` should use a longer wait.
   - Recommendation: Document the long first-startup time; consider making the Docker init script conditional (only loads if data not present) to ensure idempotency.

3. **normalize_address() with no Tiger data loaded**
   - What we know: `normalize_address()` is a pure parsing function that does NOT require loaded Tiger data — it only uses the bundled lookup tables installed with the extension.
   - What's unclear: Does `normalize_address()` work with just the extension installed, before any state data is loaded?
   - Recommendation: Research confirms `normalize_address()` is independent of loaded data — it uses internal rules tables, not `tiger_data.*`. The validation provider does NOT need Tiger data to function; only the geocoding provider does. This is a useful distinction for the planner.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/test_tiger_provider.py -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| TIGR-01 | geocode() returns GeocodingResult with correct lat/lng/location_type/confidence | unit | `uv run pytest tests/test_tiger_provider.py -k "geocode" -x` | Wave 0 |
| TIGR-01 | geocode() returns NO_MATCH when row is None | unit | `uv run pytest tests/test_tiger_provider.py -k "no_match" -x` | Wave 0 |
| TIGR-01 | geocode() accepts **kwargs (http_client=) without TypeError | unit | `uv run pytest tests/test_tiger_provider.py -k "kwargs" -x` | Wave 0 |
| TIGR-02 | normalize_address() returns ValidationResult with parsed components | unit | `uv run pytest tests/test_tiger_provider.py -k "validate" -x` | Wave 0 |
| TIGR-02 | normalize_address() returns NO_MATCH when parsed=False | unit | `uv run pytest tests/test_tiger_provider.py -k "parsed_false" -x` | Wave 0 |
| TIGR-03 | rating 0 -> confidence 1.0; rating 100 -> confidence 0.0 | unit | `uv run pytest tests/test_tiger_provider.py -k "confidence" -x` | Wave 0 |
| TIGR-03 | rating > 100 clamps to confidence 0.0 | unit | `uv run pytest tests/test_tiger_provider.py -k "clamp" -x` | Wave 0 |
| TIGR-04 | Provider not registered when extension absent | unit | `uv run pytest tests/test_tiger_provider.py -k "extension" -x` | Wave 0 |
| TIGR-04 | Startup warning logged when extension absent | unit | `uv run pytest tests/test_tiger_provider.py -k "warning" -x` | Wave 0 |
| TIGR-05 | setup-tiger CLI installs extensions (idempotent) | unit | `uv run pytest tests/test_tiger_cli.py -k "extensions" -x` | Wave 0 |
| TIGR-05 | setup-tiger FIPS->abbrev conversion works | unit | `uv run pytest tests/test_tiger_cli.py -k "fips" -x` | Wave 0 |
| TIGR-01 | geocode() returns real Tiger result for known GA address | integration (`@pytest.mark.tiger`) | `uv run pytest tests/test_tiger_provider.py -m tiger -x` | Wave 0 |
| TIGR-02 | normalize_address() returns real parsed components | integration (`@pytest.mark.tiger`) | `uv run pytest tests/test_tiger_provider.py -m tiger -k "validate" -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_tiger_provider.py tests/test_tiger_cli.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_tiger_provider.py` — unit tests for TigerGeocodingProvider + TigerValidationProvider (mock pattern from test_oa_provider.py)
- [ ] `tests/test_tiger_cli.py` — unit tests for setup-tiger CLI command (FIPS conversion, extension install)
- [ ] `pyproject.toml` markers config — add `markers = ["tiger: marks tests requiring Tiger/Line data"]` to `[tool.pytest.ini_options]`
- [ ] `scripts/20_tiger_setup.sh` or `docker-entrypoint-initdb.d/20_tiger.sh` — Docker init script for Tiger extension + GA data loading

---

## Sources

### Primary (HIGH confidence)

- PostGIS official docs `https://postgis.net/docs/Geocode.html` — geocode() function signature, output columns, rating semantics, norm_addy dot-notation access
- PostGIS official docs `https://postgis.net/docs/Normalize_Address.html` — normalize_address() signature, all 12 norm_addy fields with names and types
- PostGIS official docs `https://postgis.net/docs/Loader_Generate_Script.html` — Loader_Generate_Script signature, state abbreviation format, psql execution pattern
- `postgis/docker-postgis` Dockerfile `https://github.com/postgis/docker-postgis/blob/master/17-3.5/alpine/Dockerfile` — confirms all 8 extensions including `postgis_tiger_geocoder` and `fuzzystrmatch` are present in `postgis/postgis:17-3.5`
- Project codebase — `openaddresses.py`, `base.py`, `schemas.py`, `exceptions.py`, `main.py`, `cli/__init__.py`, `tests/test_oa_provider.py` — all read directly for pattern confirmation

### Secondary (MEDIUM confidence)

- `https://dev.to/cincybc/create-your-own-geocoder-with-postgistiger-3anc` — SQL geocode() query with ST_Y/ST_X and `(addy).fieldname` pattern; verified against PostGIS official docs
- `https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup` — extension installation order and Loader_Generate_Script execution pattern; cross-verified with PostGIS docs
- WebSearch results — confirmed state abbreviation (not FIPS) requirement for Loader_Generate_Script from multiple sources

### Tertiary (LOW confidence)

- TIGER 2023+ format incompatibility note (from WebSearch; single source, not verified against PostGIS official changelog — flagged for awareness only)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already in pyproject.toml; no new dependencies
- Architecture: HIGH — SQL patterns verified from PostGIS official docs; class structure matches proven OA provider pattern
- Pitfalls: HIGH — composite type pitfall confirmed from asyncpg docs; rating clamping verified from PostGIS examples showing rating 108; FIPS/abbrev issue confirmed from multiple sources
- FIPS-to-abbreviation CLI translation: HIGH — Loader_Generate_Script abbreviation requirement confirmed from PostGIS docs and multiple secondary sources

**Research date:** 2026-03-24
**Valid until:** 2026-06-24 (stable — PostGIS Tiger API is stable across versions; check if PostGIS 3.6+ changes Loader_Generate_Script behavior)
