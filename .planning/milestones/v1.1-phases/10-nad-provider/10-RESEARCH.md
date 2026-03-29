# Phase 10: NAD Provider - Research

**Researched:** 2026-03-24
**Domain:** National Address Database (NAD) geocoding/validation provider + bulk CSV import via PostgreSQL COPY
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Placement-to-confidence mapping** (mirrors OA confidence tiers):
- "Structure - Rooftop" → ROOFTOP / 1.0
- "Structure - Entrance" → ROOFTOP / 1.0
- "Site" → APPROXIMATE / 0.8
- "Property Access" → APPROXIMATE / 0.8
- "Parcel - Other" → APPROXIMATE / 0.6
- "Linear Geocode" → RANGE_INTERPOLATED / 0.5
- "Parcel - Centroid" → GEOMETRIC_CENTER / 0.4
- "Unknown" / empty / garbage / "Other" / "0" → APPROXIMATE / 0.1
- Garbage values (NatGrid coordinates leaked into Placement field) treated as Unknown — import them, don't skip
- location_type for Unknown is APPROXIMATE (not a new UNKNOWN type)

**Data format:**
- NAD r21 data is CSV-delimited (not pipe-delimited as previously documented) — confirmed by schema.ini `Format=CSVDelimited`
- File has UTF-8 BOM that must be stripped during parsing
- 60 columns in source, reduced to 10 staging table columns during import
- Fix existing docstrings and references that say "pipe-delimited"

**Import interface (load-nad CLI):**
- Accepts ZIP file directly — CLI extracts TXT from ZIP transparently
- State filter is required — user must specify at least one `--state` argument to prevent accidental full-dataset (88M row) loads
- COPY strategy: COPY to temp table, then INSERT...ON CONFLICT (source_hash) DO UPDATE from temp → nad_points
- source_hash = NAD UUID field with braces stripped (36-char string, fits String(64) column)
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

**Provider registration:**
- Conditional on data presence at startup: `SELECT EXISTS(SELECT 1 FROM nad_points LIMIT 1)`
- If no data: log warning (like Tiger pattern), provider not registered
- Restart required after loading data (consistent with all local providers)

**Provider naming:**
- `provider_name` = "national_address_database" for both geocoding and validation providers

**Address matching strategy:**
- Same pattern as OA: scourgify + usaddress parse input, exact component match against staging table
- WHERE street_number = X AND UPPER(street_name) = Y AND zip_code = Z
- On match: return with Placement-mapped confidence/location_type
- On no match: return NO_MATCH with confidence=0.0

**Validation approach:**
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

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NAD-01 | User can geocode an address against loaded NAD data | NADGeocodingProvider implementation following OAGeocodingProvider pattern; PLACEMENT_MAP drives location_type/confidence |
| NAD-02 | User can validate an address against NAD records | NADValidationProvider following OAValidationProvider pattern; scourgify re-normalization on match; NAD-specific fields (zip_code vs postcode, state vs region) |
| NAD-03 | NAD import handles 80M+ rows via PostgreSQL COPY (not row-by-row INSERT) | psycopg2 copy_expert + StringIO buffer; COPY to temp table then INSERT...ON CONFLICT upsert; state filter prevents accidental full-dataset loads |
| NAD-04 | NAD provider registered automatically when staging table has data | SELECT EXISTS(SELECT 1 FROM nad_points LIMIT 1) async check at startup; conditional registration in main.py lifespan, same pattern as Tiger |
</phase_requirements>

---

## Summary

Phase 10 is a high-fidelity clone of Phase 8 (OpenAddresses provider) adapted for the NAD data model. The provider implementation (NAD-01, NAD-02, NAD-04) follows the OAGeocodingProvider/OAValidationProvider pattern exactly: async_sessionmaker injection, is_local=True, _parse_input_address reuse, exact-component WHERE query against nad_points, Placement-to-confidence mapping in place of OA's accuracy mapping, and conditional registration in main.py lifespan at startup.

The import command (NAD-03) is where NAD diverges from OA. The 35.8 GB uncompressed source file requires PostgreSQL COPY (not row-by-row INSERT) for performance. The chosen strategy is: stream CSV rows from the ZIP in Python, pre-process each row into 10 columns (city fallback chain, UUID brace stripping, WKT POINT construction), write batches into a StringIO buffer, COPY that buffer into a temp table, then execute a single INSERT...ON CONFLICT upsert from the temp table into nad_points. The mandatory `--state` flag filters rows during streaming to support single-state imports without writing the entire 35.8 GB to disk.

A key data observation: in the sampled NAD r21 data, 100% of rows in the Alaska prefix of the file have Placement="Unknown". The CONTEXT.md decision to map Unknown → APPROXIMATE/0.1 is the correct approach for 90.7% of the NAD dataset. The Inc_Muni field contains "City of X" / "City and Borough of X" prefixes in 100% of the Alaska data tested, which is relevant to the city fallback chain implementation decision.

**Primary recommendation:** Implement in two files — `providers/nad.py` (providers, PLACEMENT_MAP, `_find_nad_match`) and CLI expansion in `cli/__init__.py` (replace stub with full COPY-based load-nad). Register in `main.py` lifespan. Test in `tests/test_nad_provider.py` using the `_make_session_factory` pattern from `test_oa_provider.py`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2-binary | >=2.9.11 (pinned in pyproject.toml) | PostgreSQL COPY via `copy_expert` | Already in project; provides `cursor.copy_expert(sql, file_obj)` for efficient COPY FROM STDIN |
| sqlalchemy | Already installed | ORM queries for provider path + create_engine for CLI | Already in project; async engine for providers, sync engine for CLI |
| geoalchemy2 | Already installed | Geography(POINT) casting for ST_Y/ST_X extraction | Already in project; same as OA provider |
| scourgify | Already installed | Input address normalization + validation result re-normalization | Already in project; same as OA |
| usaddress | Already installed | Token-level street component parsing | Already in project; same as OA |
| rich | Already installed | Progress bar during import | Already in project; matches load-oa UX |
| typer | Already installed | CLI argument/option definition | Already in project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| zipfile (stdlib) | Python 3.x | Open NAD ZIP and stream TXT without extracting to disk | load-nad command |
| io.StringIO (stdlib) | Python 3.x | In-memory buffer for COPY FROM STDIN batches | load-nad COPY pipeline |
| csv (stdlib) | Python 3.x | Parse CSV rows from the UTF-8-BOM-decoded TXT stream | load-nad row parsing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psycopg2 copy_expert | SQLAlchemy bulk_insert_mappings | COPY is 10-50x faster for large loads; bulk_insert_mappings still does row-by-row under the hood |
| StringIO batching | Write temp file to disk | Avoids disk I/O; no temp file cleanup needed |
| Python-side city fallback | SQL COALESCE in upsert | Python fallback is decided in CONTEXT.md; simpler to test |

**Installation:** No new dependencies required — all libraries are already in pyproject.toml.

---

## Architecture Patterns

### Recommended Project Structure

New files to create:
```
src/civpulse_geo/providers/nad.py          # NAD provider (geocoding + validation + PLACEMENT_MAP)
tests/test_nad_provider.py                 # Provider unit tests
```

Files to modify:
```
src/civpulse_geo/cli/__init__.py           # Replace load-nad stub with full implementation
src/civpulse_geo/main.py                   # Add NAD conditional registration in lifespan
src/civpulse_geo/models/nad.py             # Fix "pipe-delimited" docstring to "CSV-delimited"
```

### Pattern 1: PLACEMENT_MAP (mirrors ACCURACY_MAP in openaddresses.py)

**What:** Module-level dict mapping NAD Placement string to (location_type, confidence) tuple.
**When to use:** Applied in `geocode()` after successful `_find_nad_match()`.

```python
# Source: .planning/phases/10-nad-provider/10-CONTEXT.md + openaddresses.py pattern
PLACEMENT_MAP: dict[str, tuple[str, float]] = {
    "Structure - Rooftop":  ("ROOFTOP", 1.0),
    "Structure - Entrance": ("ROOFTOP", 1.0),
    "Site":                 ("APPROXIMATE", 0.8),
    "Property Access":      ("APPROXIMATE", 0.8),
    "Parcel - Other":       ("APPROXIMATE", 0.6),
    "Linear Geocode":       ("RANGE_INTERPOLATED", 0.5),
    "Parcel - Centroid":    ("GEOMETRIC_CENTER", 0.4),
}
DEFAULT_PLACEMENT: tuple[str, float] = ("APPROXIMATE", 0.1)  # Unknown / empty / garbage / "Other" / "0"
```

Usage mirrors `ACCURACY_MAP.get(oa_row.accuracy or "", DEFAULT_ACCURACY)`:
```python
location_type, confidence = PLACEMENT_MAP.get(
    nad_row.placement or "", DEFAULT_PLACEMENT
)
```

### Pattern 2: `_find_nad_match` (adapts `_find_oa_match` for NAD column names)

**What:** Async helper querying nad_points with exact component match.
**Key difference from OA:** Column is `zip_code` (not `postcode`), and `state` (not `region`).

```python
# Source: providers/openaddresses.py _find_oa_match, adapted for NADPoint
from civpulse_geo.models.nad import NADPoint

async def _find_nad_match(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postal_code: str,
) -> tuple[NADPoint, float, float] | None:
    stmt = (
        select(
            NADPoint,
            func.ST_Y(NADPoint.location.cast(Geometry)).label("lat"),
            func.ST_X(NADPoint.location.cast(Geometry)).label("lng"),
        )
        .where(
            NADPoint.street_number == street_number,
            func.upper(NADPoint.street_name) == street_name.upper(),
            NADPoint.zip_code == postal_code,
        )
        .order_by(NADPoint.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()
```

### Pattern 3: NAD data presence check (conditional registration)

**What:** Async function that queries nad_points for at least one row; used in main.py lifespan.
**When to use:** Called once at startup before registering NAD providers.

```python
# Source: providers/tiger.py _tiger_extension_available pattern
async def _nad_data_available(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    try:
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT EXISTS(SELECT 1 FROM nad_points LIMIT 1)")
            )
            return bool(result.scalar())
    except Exception:
        return False
```

### Pattern 4: COPY-to-temp-table import pipeline

**What:** Streams CSV from ZIP, pre-processes rows in Python, batches writes via COPY FROM STDIN into a temp table, then upserts into nad_points.
**When to use:** load-nad CLI command.

```python
# Source: CONTEXT.md decisions + psycopg2 copy_expert docs
# Engine: synchronous psycopg2 (same as load-oa)

NAD_COPY_SQL = """
    COPY nad_temp (
        source_hash, street_number, street_name, street_suffix,
        unit, city, state, zip_code, location, placement
    ) FROM STDIN WITH (FORMAT CSV, NULL '')
"""

NAD_UPSERT_SQL = """
    INSERT INTO nad_points (
        source_hash, street_number, street_name, street_suffix,
        unit, city, state, zip_code, location, placement
    )
    SELECT
        source_hash, street_number, street_name, street_suffix,
        unit, city, state, zip_code,
        ST_GeogFromText(location),
        placement
    FROM nad_temp
    ON CONFLICT ON CONSTRAINT uq_nad_source_hash DO UPDATE
        SET street_number = EXCLUDED.street_number,
            street_name   = EXCLUDED.street_name,
            street_suffix = EXCLUDED.street_suffix,
            unit          = EXCLUDED.unit,
            city          = EXCLUDED.city,
            state         = EXCLUDED.state,
            zip_code      = EXCLUDED.zip_code,
            location      = EXCLUDED.location,
            placement     = EXCLUDED.placement
"""

# The temp table holds raw WKT strings (TEXT) so COPY can handle them;
# ST_GeogFromText is applied in the upsert SELECT.
CREATE_TEMP_TABLE = """
    CREATE TEMP TABLE nad_temp (
        source_hash TEXT,
        street_number TEXT,
        street_name TEXT,
        street_suffix TEXT,
        unit TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT,
        location TEXT,       -- WKT POINT string, e.g. "SRID=4326;POINT(-83.63 32.84)"
        placement TEXT
    ) ON COMMIT DROP
"""
```

**COPY FROM STDIN with psycopg2:**
```python
import io
import csv

buf = io.StringIO()
writer = csv.writer(buf)
# ... write rows to buf ...
buf.seek(0)
with engine.connect() as conn:
    raw_conn = conn.connection  # psycopg2 connection
    with raw_conn.cursor() as cur:
        cur.copy_expert(NAD_COPY_SQL, buf)
    raw_conn.commit()
```

### Pattern 5: City fallback chain

**What:** Resolves city from three NAD fields in order of preference.
**Why:** 100% of Alaska data has Post_City="Not stated"; Inc_Muni contains "City of X" prefix in 100% of sampled data.

```python
def _resolve_city(post_city: str, inc_muni: str, county: str) -> str | None:
    """Apply NAD city fallback chain: Post_City → Inc_Muni → County."""
    NOT_STATED = "not stated"
    for raw in [post_city, inc_muni, county]:
        val = (raw or "").strip()
        if val and val.lower() != NOT_STATED:
            return val
    return None
```

Note: The Inc_Muni prefix stripping ("City of X" → "X") is a discretion item. The data confirms 100% of Alaska Inc_Muni values start with "City of" or "City and Borough of". Whether to strip is a planner/implementer decision.

### Pattern 6: State filtering during streaming

**What:** Filter CSV rows by State column value during streaming, before any processing.
**Why:** Avoids writing 35.8 GB to disk; supports single-state imports.

```python
# Normalize input --state values using existing _resolve_state function
states_upper = {_resolve_state(s).upper() for s in state_args if _resolve_state(s)}

# In streaming loop:
if row["State"].upper() not in states_upper:
    continue  # skip row entirely before any processing
```

### Pattern 7: main.py lifespan registration (NAD alongside Tiger pattern)

```python
# Source: src/civpulse_geo/main.py + CONTEXT.md
from civpulse_geo.providers.nad import (
    NADGeocodingProvider,
    NADValidationProvider,
    _nad_data_available,
)

# In lifespan, after Tiger block:
if await _nad_data_available(AsyncSessionLocal):
    app.state.providers["national_address_database"] = NADGeocodingProvider(AsyncSessionLocal)
    app.state.validation_providers["national_address_database"] = NADValidationProvider(AsyncSessionLocal)
    logger.info("NAD provider registered")
else:
    logger.warning(
        "nad_points table is empty — NAD provider not registered"
    )
```

### Pattern 8: Docstring fix in nad.py model

The existing `models/nad.py` docstring says "pipe-delimited TXT files" — this is incorrect per schema.ini confirmation. Must be fixed to "CSV-delimited (CSVDelimited format per schema.ini)".

### Anti-Patterns to Avoid

- **Using row-by-row INSERT for NAD data:** 88M rows × INSERT latency = hours. Use COPY.
- **COPY directly into nad_points:** Direct COPY cannot call ST_GeogFromText. Use temp table with TEXT location column, then INSERT...SELECT with ST_GeogFromText.
- **Extracting the ZIP to disk:** 35.8 GB uncompressed. Stream directly from the ZIP with `zipfile.open()`.
- **Loading full dataset without --state:** 88M rows takes prohibitive time and disk space for test imports. Require --state.
- **Recomputing source_hash:** NAD UUIDs are already unique per-record. Strip `{}` and use directly, as decided.
- **Creating a new UNKNOWN location_type:** Any garbage/unknown Placement values map to APPROXIMATE/0.1, not a new type.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bulk CSV-to-DB loading | Custom row-by-row INSERT loop | psycopg2 `copy_expert` | COPY is 10-50x faster; handles large datasets without memory pressure |
| Address input normalization | Custom parser | `scourgify` + `usaddress` | Already in project; exact same pattern as OA provider |
| Progress bar | Custom terminal output | `rich.progress.Progress` | Already installed; matches load-oa UX; handles streaming progress |
| State FIPS/abbreviation resolution | New lookup table | `_resolve_state()` from cli/__init__.py | Already implemented for Tiger; exact same table |
| UTF-8 BOM handling | Manual byte stripping | `encoding='utf-8-sig'` in io.TextIOWrapper | Python stdlib handles BOM transparently |

**Key insight:** NAD is intentionally a near-clone of the OA provider. The only novel work is: PLACEMENT_MAP (instead of ACCURACY_MAP), COPY-based import (instead of JSON batch upsert), ZIP streaming, state filtering, and the city fallback chain.

---

## Common Pitfalls

### Pitfall 1: Direct COPY to nad_points fails (Geography column)
**What goes wrong:** `COPY nad_points (..., location, ...) FROM STDIN` fails because PostgreSQL cannot accept a WKT string into a Geography column directly via COPY.
**Why it happens:** COPY expects raw binary or text representations native to the column type. Geography columns require ST_GeogFromText() or ST_GeomFromEWKT() function calls.
**How to avoid:** COPY to a temp table with a TEXT location column, then INSERT...SELECT applying ST_GeogFromText() from the temp table to nad_points. This is the decided COPY strategy.
**Warning signs:** `ERROR: invalid input syntax for type geography` during COPY.

### Pitfall 2: UTF-8 BOM corrupts first column name
**What goes wrong:** The first column header becomes `\ufeffOID_` instead of `OID_`, causing csv.DictReader to produce keys with a BOM prefix. Column lookups for `Add_Number` etc. still work, but if code ever accesses `OID_` directly it will fail silently.
**Why it happens:** NAD r21 TXT file is encoded UTF-8 with BOM (confirmed by schema.ini/data inspection).
**How to avoid:** Open the file with `encoding='utf-8-sig'` via `io.TextIOWrapper(file_obj, encoding='utf-8-sig')`. Python's `utf-8-sig` codec strips the BOM transparently.
**Warning signs:** First dict key has `\ufeff` prefix when decoded without `utf-8-sig`.

### Pitfall 3: Accessing raw psycopg2 connection through SQLAlchemy
**What goes wrong:** `engine.connect()` returns a SQLAlchemy connection, not a raw psycopg2 connection. `copy_expert` is on the psycopg2 cursor, not the SQLAlchemy cursor.
**Why it happens:** SQLAlchemy wraps the DBAPI connection.
**How to avoid:** Access the raw connection via `conn.connection` (SQLAlchemy 2.x: `conn.connection` gives the DBAPI connection; then `.cursor()` gives the psycopg2 cursor). Pattern: `raw_conn = conn.connection; cur = raw_conn.cursor(); cur.copy_expert(...)`.
**Warning signs:** `AttributeError: 'Connection' object has no attribute 'copy_expert'`.

### Pitfall 4: State filter must use the State column, not file ordering
**What goes wrong:** The NAD file is sorted by State alphabetically (starts with Alaska), so you could in principle break early for single-state loads. However, relying on file ordering is fragile. The correct approach filters every row by the State column value.
**Why it happens:** Temptation to optimize by breaking on first non-matching state after seeing target state rows.
**How to avoid:** Filter by `row["State"].upper() in states_upper` for every row. Skip only; never break.

### Pitfall 5: Inc_Muni "City of" prefix in city fallback
**What goes wrong:** City stored as "City of Sand Point" instead of "Sand Point", causing validation results to look wrong and potentially breaking geocode lookups if users query with just the bare city name.
**Why it happens:** 100% of Alaska Inc_Muni values (confirmed by data inspection) contain "City of X", "City and Borough of X", or "Borough of X" prefixes.
**How to avoid:** The city fallback chain first tries Post_City (which is "Not stated" in Alaska but may be populated elsewhere). If stripping Inc_Muni prefixes: implement `_strip_muni_prefix(val)` to remove common patterns. This is a discretion item — the planner should decide whether to strip or store verbatim.
**Warning signs:** City field populated with "City of X" in nad_points after import.

### Pitfall 6: Empty/None zip_code causes false NO_MATCH
**What goes wrong:** Many NAD records have empty Zip_Code fields (confirmed in Alaska sample data). The match query `WHERE zip_code = X` will never match rows with NULL zip_code. Users querying with a valid ZIP will get NO_MATCH for addresses that exist but lack ZIP.
**Why it happens:** NAD data quality varies; Alaska records frequently omit ZIP codes.
**How to avoid:** This is a known data quality limitation. The address matching strategy (from CONTEXT.md) requires zip_code match, consistent with OA. No change needed — document that NAD coverage may be incomplete for addresses without ZIP codes.

### Pitfall 7: Forgot to drop existing temp table between batches
**What goes wrong:** If using `CREATE TEMP TABLE` with `ON COMMIT DROP`, the temp table is dropped at each commit. If batching across multiple commits, you need to recreate the temp table for each batch.
**Why it happens:** Temp table lifecycle is per-transaction when `ON COMMIT DROP` is used.
**How to avoid:** Create the temp table once per CLI invocation (not per batch), or use `ON COMMIT DELETE ROWS` to keep the table structure but clear data after each commit.

---

## Code Examples

Verified patterns from existing source:

### Existing `_make_session_factory` for NAD tests (reuse verbatim)
```python
# Source: tests/test_oa_provider.py lines 34-51
def _make_session_factory(execute_return_value=None, raise_exc=None):
    """Build a mock async_sessionmaker that works with 'async with factory() as session'."""
    mock_session = AsyncMock()
    if raise_exc is not None:
        mock_session.execute.side_effect = raise_exc
    else:
        mock_result = MagicMock()
        mock_result.first.return_value = execute_return_value
        mock_session.execute = AsyncMock(return_value=mock_result)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory
```

### NAD row mock builder for tests
```python
def _make_nad_row(
    street_number="123",
    street_name="MAIN",
    street_suffix="ST",
    unit=None,
    city="MACON",
    state="GA",
    zip_code="31201",
    placement="Unknown",
    source_hash="test-uuid-1234",
):
    """Return a mock NADPoint row."""
    row = MagicMock()
    row.street_number = street_number
    row.street_name = street_name
    row.street_suffix = street_suffix
    row.unit = unit
    row.city = city
    row.state = state
    row.zip_code = zip_code
    row.placement = placement
    row.source_hash = source_hash
    return row
```

### load-nad state option declaration (using existing _resolve_state)
```python
# Source: cli/__init__.py setup-tiger pattern for state argument
@app.command("load-nad")
def load_nad(
    file: Path = typer.Argument(..., help="Path to NAD r21 ZIP file"),
    states: list[str] = typer.Option(
        ..., "--state", "-s",
        help="State abbreviation(s) or FIPS code(s) to import (required). E.g. --state GA --state FL",
    ),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2).",
    ),
) -> None:
```

### NADPoint column names (confirmed from models/nad.py)
```python
# Source: src/civpulse_geo/models/nad.py
# Columns: id, source_hash, street_number, street_name, street_suffix,
#          unit, city, state, zip_code, location (Geography), placement
# Constraint: uq_nad_source_hash on source_hash
# Note: 'state' and 'zip_code' differ from OA's 'region' and 'postcode'
```

### Validation result construction (adapting OA pattern for NAD columns)
```python
# Source: providers/openaddresses.py OAValidationProvider.validate() adapted for NAD
# Key difference: oa_row.region → nad_row.state; oa_row.postcode → nad_row.zip_code
suffix = (nad_row.street_suffix or "").strip()
street_line = f"{nad_row.street_number or ''} {nad_row.street_name or ''} {suffix}".strip()
city_str = nad_row.city or ""
state_str = nad_row.state or ""     # NAD column is 'state', not 'region'
zip_str = nad_row.zip_code or ""    # NAD column is 'zip_code', not 'postcode'
reconstructed = f"{street_line}, {city_str}, {state_str} {zip_str}".strip(", ")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Row-by-row INSERT for bulk data | PostgreSQL COPY via psycopg2 copy_expert | Phase 10 decision | 10-50x faster; essential for 88M row dataset |
| Stub load-nad (exit 0) | Full COPY-based implementation | Phase 10 | NAD-03 requirement satisfied |
| No NAD provider in registry | Conditional NAD registration at startup | Phase 10 | NAD-01, NAD-02, NAD-04 requirements satisfied |

**Deprecated/outdated:**
- `models/nad.py` docstring says "pipe-delimited" — schema.ini confirms CSVDelimited. Fix in Phase 10.
- `cli/__init__.py` load-nad stub docstring says "pipe-delimited TXT file" — fix to "CSV ZIP file".

---

## Open Questions

1. **Inc_Muni prefix stripping**
   - What we know: 100% of Alaska Inc_Muni values start with "City of X" or "City and Borough of X". In Georgia test data, value was "Unincorporated" (not a "City of" prefix case).
   - What's unclear: How widespread is the "City of" prefix in non-Alaska states? Stripping improves city normalization but adds code complexity.
   - Recommendation: Implement `_strip_muni_prefix()` that removes "City of ", "City and Borough of ", "Borough of ", "Township of " prefixes to produce a cleaner city name. Mark as Claude's discretion.

2. **Temp table lifecycle during large imports**
   - What we know: `CREATE TEMP TABLE ... ON COMMIT DROP` drops after each commit. `ON COMMIT DELETE ROWS` clears data but keeps structure.
   - What's unclear: What's the optimal batch size for the COPY buffer before flushing to temp and upserting into nad_points?
   - Recommendation: Create the temp table once with `ON COMMIT DELETE ROWS` (or without `ON COMMIT` clause using explicit DROP). Use batches of ~50,000 rows per COPY+upsert cycle for memory efficiency and incremental durability.

3. **_parse_input_address shared vs imported**
   - What we know: OA provider exports `_parse_input_address` as a module-level function; CONTEXT.md specifies it should be extracted to a shared module or imported from openaddresses.py.
   - What's unclear: Whether to create a new `providers/_address_parsing.py` shared module or import directly from `providers/openaddresses.py`.
   - Recommendation: Import directly from `civpulse_geo.providers.openaddresses` (no new file needed). The planner should decide whether refactoring into a shared module is within scope.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` — asyncio_mode = "auto" |
| Quick run command | `.venv/bin/pytest tests/test_nad_provider.py tests/test_load_nad_cli.py -x` |
| Full suite command | `.venv/bin/pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NAD-01 | NADGeocodingProvider geocodes with Placement mapping | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADGeocodingProvider -x` | ❌ Wave 0 |
| NAD-01 | NO_MATCH returned on parse failure | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADGeocodingProvider::test_geocode_no_match_on_parse_failure -x` | ❌ Wave 0 |
| NAD-01 | All 8 Placement values covered | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestPlacementMapping -x` | ❌ Wave 0 |
| NAD-02 | NADValidationProvider returns ValidationResult with confidence=1.0 on match | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADValidationProvider::test_validate_match -x` | ❌ Wave 0 |
| NAD-02 | Scourgify fallback on re-normalization failure | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNADValidationProvider::test_validate_scourgify_fallback -x` | ❌ Wave 0 |
| NAD-03 | load-nad with valid ZIP + state succeeds (smoke with mock DB) | unit | `.venv/bin/pytest tests/test_load_nad_cli.py -x` | ✅ (partial — existing stub tests pass) |
| NAD-03 | load-nad requires --state argument | unit | `.venv/bin/pytest tests/test_load_nad_cli.py::TestLoadNadCli::test_load_nad_requires_state -x` | ❌ Wave 0 |
| NAD-04 | _nad_data_available returns True/False based on table content | unit | `.venv/bin/pytest tests/test_nad_provider.py::TestNadDataAvailable -x` | ❌ Wave 0 |
| NAD-04 | main.py registers NAD providers when data present | integration | `.venv/bin/pytest tests/test_nad_provider.py::TestNADRegistration -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/test_nad_provider.py tests/test_load_nad_cli.py -x`
- **Per wave merge:** `.venv/bin/pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_nad_provider.py` — covers NAD-01, NAD-02, NAD-04 (unit tests for providers + `_nad_data_available`)
- [ ] Additional test cases in `tests/test_load_nad_cli.py` — extend existing file to cover NAD-03 (--state required, ZIP input, state filtering)

*(Existing `tests/test_load_nad_cli.py` covers stub behavior. New tests for full implementation needed in Wave 0.)*

---

## Sources

### Primary (HIGH confidence)
- `src/civpulse_geo/providers/openaddresses.py` — Reference implementation read directly; all OA patterns confirmed
- `src/civpulse_geo/providers/base.py` — ABC interface confirmed
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult/ValidationResult fields confirmed
- `src/civpulse_geo/models/nad.py` — NADPoint columns and constraint names confirmed
- `src/civpulse_geo/main.py` — Lifespan registration pattern confirmed
- `src/civpulse_geo/cli/__init__.py` — load-nad stub (lines 549-563), load-oa pattern, _resolve_state confirmed
- `tests/test_oa_provider.py` — _make_session_factory pattern confirmed for reuse
- `data/NAD_r21_TXT.zip!/TXT/schema.ini` — CSV format, all 60 column names confirmed
- `data/NAD_r21_TXT.zip!/TXT/NAD_r21.txt` — Sampled first 5M rows; confirmed UTF-8 BOM, UUID with braces, Placement="Unknown" in 100% of sampled data, Inc_Muni "City of" prefix in 100% of Alaska data
- `pyproject.toml` — psycopg2-binary, pytest, pytest-asyncio versions confirmed
- psycopg2 cursor `copy_expert` method — confirmed present via `.venv/bin/python` inspection

### Secondary (MEDIUM confidence)
- `.planning/phases/10-nad-provider/10-CONTEXT.md` — All locked decisions used directly (CONTEXT.md is authoritative)

### Tertiary (LOW confidence)
- Placement values beyond "Unknown": Only 100k rows sampled; all returned "Unknown". The full 88M-row dataset contains the full Placement distribution claimed in CONTEXT.md (90.7% Unknown, remainder having non-Unknown values). Not directly verified but trusted given CONTEXT.md notes confirmed structure.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified present in pyproject.toml and virtual env
- Architecture: HIGH — OA/Tiger patterns read directly; NAD model and stub read directly
- Pitfalls: HIGH for items verified against actual data (UTF-8 BOM, Inc_Muni prefix, Placement="Unknown"); MEDIUM for COPY temp table lifecycle (psycopg2 docs not directly fetched, but copy_expert method confirmed present)
- Data format: HIGH — schema.ini and first rows sampled directly from ZIP

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (stable domain — psycopg2 and SQLAlchemy APIs very stable)
