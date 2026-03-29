# Phase 8: OpenAddresses Provider - Research

**Researched:** 2026-03-22
**Domain:** OpenAddresses geocoding/validation provider + CLI data loading
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Phase Boundary**
Implement OpenAddresses geocoding and validation providers that query the `openaddresses_points` staging table, plus wire the `load-oa` CLI command to actually import .geojson.gz data. Providers implement existing GeocodingProvider/ValidationProvider ABCs with `is_local=True`. No new staging tables, no new migrations — Phase 7 built the infrastructure.

**Address matching strategy**
- Parse incoming freeform address using scourgify's `normalize_address_record()` to extract components (number, street, city, state, zip)
- Exact component match against staging table: `WHERE street_number = X AND UPPER(street_name) = Y AND postcode = Z`
- Normalize street suffixes before matching (both input and stored data use USPS abbreviations)
- On multiple matches: `LIMIT 1` ordered by id (first match, deterministic)
- On no match: return GeocodingResult with confidence=0.0, location_type=NO_MATCH

**Accuracy-to-location_type mapping** (confidence tiers fixed)
- rooftop = 1.0
- parcel = 0.8
- interpolation = 0.5
- centroid = 0.4
- empty/unknown = 0.1

**Provider auto-registration**
- Always register the OA provider in the provider list (no startup data check needed)
- If `openaddresses_points` table is empty, provider returns NO_MATCH gracefully (no error)
- Restart required after loading new data (consistent with all providers)
- Provider constructor receives `async_sessionmaker` for querying staging table

**Validation approach**
- Same matching logic as geocoding: scourgify-parse input, exact component match against staging table
- After matching, pipe the OA address components through scourgify for USPS-standard normalization
- Binary confidence: match = 1.0, no-match = 0.0
- `delivery_point_verified` = False (no DPV from OA data)

**CLI data loading (load-oa)**
- 1000-row batches with commit per batch
- Rich progress bar during import, updates per batch
- Convert empty strings to NULL during import (OA uses empty strings for missing data)
- Use OA's built-in `hash` property directly as `source_hash` value
- Upsert: ON CONFLICT (source_hash) DO UPDATE
- Summary after import: total processed, inserted, updated, skipped, elapsed time
- Skip features without valid coordinates (count in skipped total, log hash for debugging)
- Skip malformed GeoJSON features (log warning, count in skipped total)

**Street suffix parsing during import**
- Use `usaddress` library (transitive dep via scourgify) to parse OA `street` field into `street_name` and `street_suffix`
- OA `number` and `street` are always separate properties — no need to extract number from street
- Store parsed suffix in `street_suffix` column for matching queries

**Provider naming**
- `provider_name` = "openaddresses" for both geocoding and validation providers
- `raw_response` contains matched OA row data as dict: source_hash, street_number, street_name, street_suffix, city, region, postcode, accuracy, lat, lng

**Error handling**
- During import: skip and count malformed features, don't halt entire import
- During geocode/validate: raise `ProviderError` on database connection failures (not silent NO_MATCH)
- Wrap SQLAlchemy exceptions in ProviderError for clean error propagation

### Claude's Discretion
- Exact accuracy-to-location_type mapping choices
- Whether to create a shared base class for OA geocoding+validation or keep them separate
- Internal query construction details (text() vs ORM query)
- Test fixture design and factory patterns
- Whether batch_geocode/batch_validate use serial loops or optimized batch queries

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| OA-01 | User can geocode an address against loaded OpenAddresses data | OA geocoding provider with async_sessionmaker, component-match query, GeocodingResult return |
| OA-02 | User can validate an address against OpenAddresses records | OA validation provider reusing same match logic, scourgify normalization of matched row, ValidationResult return |
| OA-03 | OA geocoding returns location_type based on accuracy field (rooftop/parcel/interpolated/centroid) | accuracy→location_type mapping table; Bibb County data has empty accuracy — use empty=0.1 mapping |
| OA-04 | OA provider registered automatically when staging table has data | Always-register pattern confirmed; no startup table check needed per CONTEXT decision; main.py lifespan updated to pass async_sessionmaker |
</phase_requirements>

---

## Summary

Phase 8 wires the `openaddresses_points` staging table (built in Phase 7) to a pair of geocoding and validation providers, and replaces the `load-oa` CLI stub with actual NDJSON import logic. All three implementation pieces are self-contained: the CLI is synchronous (psycopg2), the providers are async (asyncpg via SQLAlchemy async_sessionmaker), and the service layer already handles `is_local=True` providers without modification.

The sample Bibb County dataset confirms the NDJSON format (one JSON Feature object per line, gzip-compressed) and reveals that the `accuracy` field is empty for this county's data — the empty/unknown confidence tier (0.1) will apply to all Bibb County records. The OA `region` field is similarly empty in this dataset, making postcode the reliable geographic discriminator for matching.

Street suffix parsing via `usaddress.parse()` works correctly for the majority of OA street values. Edge cases (highway names like "I-475 NB", landmark-tagged streets like "MANNING MILL") will fail to yield a `StreetNamePostType` tag — the import should store NULL for `street_suffix` in those cases rather than erroring. Matching queries must handle `street_suffix IS NULL` gracefully.

**Primary recommendation:** Build `OAGeocodingProvider` and `OAValidationProvider` as separate classes (no shared base class needed — they share only the match query logic, which is extracted as a private helper method or module-level function). Wire into `main.py` lifespan and register unconditionally.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy (async) | Already installed | Query `openaddresses_points` via ORM `select()` | Project async engine pattern; `async_sessionmaker` already in `database.py` |
| scourgify | Already installed | Parse freeform input into components; normalize matched OA address for validation output | Existing offline validation provider uses this; `normalize_address_record()` proven pattern |
| usaddress | Already installed (transitive dep via scourgify) | Parse OA `street` field into `street_name` + `street_suffix` | `usaddress.parse()` returns labeled token list without raising; safer than `tag()` for non-address street strings |
| gzip (stdlib) | stdlib | Decompress .geojson.gz files | No dep needed; `gzip.open(path, 'rt')` reads NDJSON line by line |
| json (stdlib) | stdlib | Parse NDJSON feature lines | No dep needed |
| rich | Already installed (Phase 7) | Progress bar for CLI import | `rich.progress.Progress` already imported in CLI |
| typer | Already installed | CLI command definition | Existing CLI uses typer |
| sqlalchemy (sync, psycopg2) | Already installed | CLI import uses sync engine | Existing `import` CLI command pattern |

### No New Dependencies

All required libraries are already installed. The `[v1.1 Research]` decision in STATE.md confirms: "No new Python dependencies — gzip/json/csv stdlib + usaddress (transitive) + existing asyncpg/sqlalchemy cover all three providers."

**Installation:** None required.

---

## Architecture Patterns

### Recommended Project Structure

```
src/civpulse_geo/
├── providers/
│   └── openaddresses.py     # OAGeocodingProvider + OAValidationProvider
├── cli/
│   └── __init__.py          # load-oa stub replaced with actual import logic
└── main.py                  # lifespan updated to register OA providers
```

### Pattern 1: Local Provider with async_sessionmaker Constructor

The `async_sessionmaker` is NOT created inside the provider — it is passed in at construction time from `main.py` lifespan. The provider stores it as `self._session_factory` and calls `async with self._session_factory() as session:` per request.

```python
# Source: database.py pattern (AsyncSessionLocal) + CONTEXT.md decision
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

class OAGeocodingProvider(GeocodingProvider):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def is_local(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "openaddresses"

    async def geocode(self, address: str, **kwargs) -> GeocodingResult:
        async with self._session_factory() as session:
            row = await _match_oa_row(session, address)
            if row is None:
                return _no_match_result()
            return _build_geocoding_result(row)
```

**Key note:** The geocoding service calls `provider.geocode(normalized, http_client=http_client)`. The OA provider must accept `**kwargs` or an explicit `http_client=None` keyword argument in its `geocode()` signature to avoid `TypeError` — the ABC only requires `(self, address: str)` but callers pass extra kwargs.

### Pattern 2: load_providers Registry Needs Session Factory

The current `load_providers()` in `registry.py` calls `cls()` with no arguments (line 43). The OA providers require `async_sessionmaker` at construction time. The lifespan in `main.py` must instantiate OA providers directly rather than passing them to `load_providers()`, OR `load_providers()` is called with already-instantiated instances. The cleanest approach: instantiate OA providers inline in `main.py` and add to the existing registry dicts.

```python
# Source: main.py lifespan pattern
from civpulse_geo.database import AsyncSessionLocal
from civpulse_geo.providers.openaddresses import OAGeocodingProvider, OAValidationProvider

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    # Remote providers via load_providers
    app.state.providers = load_providers({"census": CensusGeocodingProvider})
    # Local providers added directly (require session_factory arg)
    app.state.providers["openaddresses"] = OAGeocodingProvider(AsyncSessionLocal)
    app.state.validation_providers = load_providers({"scourgify": ScourgifyValidationProvider})
    app.state.validation_providers["openaddresses"] = OAValidationProvider(AsyncSessionLocal)
    yield
    await app.state.http_client.aclose()
```

### Pattern 3: Component Matching Query

```python
# Source: CONTEXT.md + OpenAddressesPoint ORM model analysis
from sqlalchemy import select, func
from civpulse_geo.models.openaddresses import OpenAddressesPoint

async def _match_oa_row(
    session: AsyncSession,
    street_number: str,
    street_name: str,
    postcode: str,
) -> OpenAddressesPoint | None:
    stmt = (
        select(OpenAddressesPoint)
        .where(
            OpenAddressesPoint.street_number == street_number,
            func.upper(OpenAddressesPoint.street_name) == street_name.upper(),
            OpenAddressesPoint.postcode == postcode,
        )
        .order_by(OpenAddressesPoint.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()
```

**Note on street_suffix in matching:** The matching query per CONTEXT is `street_number + UPPER(street_name) + postcode`. The suffix is NOT used in the match query (it's stored but the match key doesn't include it). This avoids false negatives when suffix parsing is inconsistent between import and query paths.

### Pattern 4: CLI NDJSON Import Loop

```python
# Source: CONTEXT.md + sample data verification
import gzip
import json
import time
from pathlib import Path
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn

BATCH_SIZE = 1000

def _import_oa_ndjson(conn, file: Path, stats: dict) -> None:
    batch = []
    with gzip.open(file, 'rt') as f:
        with Progress(...) as progress:
            task = progress.add_task("Importing...", total=None)
            for line in f:
                try:
                    feat = json.loads(line)
                except json.JSONDecodeError:
                    stats["skipped"] += 1
                    logger.warning(f"Malformed JSON line skipped")
                    continue
                row = _parse_oa_feature(feat, stats)
                if row:
                    batch.append(row)
                if len(batch) >= BATCH_SIZE:
                    _upsert_batch(conn, batch, stats)
                    batch.clear()
                    progress.advance(task, BATCH_SIZE)
            if batch:
                _upsert_batch(conn, batch, stats)
```

### Pattern 5: accuracy → location_type Mapping

The OA specification documents these accuracy values. The Bibb County sample file has ALL empty accuracy fields — but the mapping must handle the documented values for other counties:

| OA accuracy value | location_type string | confidence |
|-------------------|---------------------|-----------|
| `"rooftop"` | `"ROOFTOP"` | 1.0 |
| `"parcel"` | `"APPROXIMATE"` | 0.8 |
| `"interpolation"` | `"RANGE_INTERPOLATED"` | 0.5 |
| `"centroid"` | `"GEOMETRIC_CENTER"` | 0.4 |
| `""` or unknown | `"APPROXIMATE"` | 0.1 |

**Rationale for location_type choices:**
- The `GeocodingResult.location_type` field comment says "matches LocationType enum values: ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE" — these are the four valid string values used in the codebase.
- `"parcel"` maps to `"APPROXIMATE"` because a parcel centroid is geometrically approximate (not a specific point on the structure). Confidence 0.8 distinguishes it from true approximations.
- `"interpolation"` maps to `"RANGE_INTERPOLATED"` — direct OA-to-existing-enum alignment.
- `"centroid"` maps to `"GEOMETRIC_CENTER"` — the closest conceptual match.
- Empty/unknown maps to `"APPROXIMATE"` with lowest confidence.

### Pattern 6: usaddress.parse() for Suffix Extraction

Use `usaddress.parse()` (not `usaddress.tag()`) for street suffix extraction during import. `parse()` returns a list of `(token, label)` tuples and never raises `RepeatedLabelError`:

```python
import usaddress

def _parse_street_components(street: str) -> tuple[str, str | None]:
    """Extract street_name and street_suffix from OA street field.

    Returns (street_name, street_suffix). street_suffix is None when
    usaddress cannot identify a StreetNamePostType tag.
    """
    tokens = usaddress.parse(street)
    name_parts = [tok for tok, lbl in tokens if lbl == "StreetName"]
    suffix_parts = [tok for tok, lbl in tokens if lbl == "StreetNamePostType"]
    street_name = " ".join(name_parts) if name_parts else street
    street_suffix = suffix_parts[0] if suffix_parts else None
    return street_name, street_suffix
```

**Verified behavior (from live testing):**
- `"NORTHMINISTER DR"` → name=`"NORTHMINISTER"`, suffix=`"DR"`
- `"HEATHERS GLENN DR"` → name=`"HEATHERS GLENN"`, suffix=`"DR"`
- `"BEACON HL"` → name=`"BEACON"`, suffix=`"HL"`
- `"LEVEL ACRES DR SW"` → suffix=`"DR"` found (though name parsed partially wrong — acceptable for import storage)
- `"MANNING MILL"` → LandmarkName tags, no suffix → suffix=None, name_parts=[], fallback to full street value
- `"I-475 NB"` → no StreetName tags, suffix=None, fallback to full street value

**Highway/landmark edge cases:** When no StreetName tokens found, fall back to storing the full `street` value as `street_name` with `street_suffix=NULL`.

### Anti-Patterns to Avoid

- **Using `usaddress.tag()` for import:** Raises `RepeatedLabelError` on ambiguous inputs. Use `parse()` which never raises.
- **Storing empty string instead of NULL:** OA data uses `""` for missing fields. Convert to `None`/NULL during import per CONTEXT decision. Empty string `postcode` would match empty string queries.
- **Checking table row count at startup for registration:** CONTEXT locked decision is to always register OA providers. Do not implement a startup SELECT COUNT query.
- **Trying to match against `region` (state) field:** The Bibb County sample data has `region=""` for all records. Postcode is the reliable geographic discriminator.
- **Passing `async_sessionmaker` to `load_providers()`:** That function calls `cls()` with no args. Instantiate OA providers directly in the lifespan function instead.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Address component extraction from freeform input | Custom regex parser | `scourgify.normalize_address_record()` | Handles USPS abbreviations, secondary designators, state name normalization |
| Street suffix extraction from OA street field | Custom split/regex | `usaddress.parse()` with `StreetNamePostType` label | Handles multi-word street names, directionals, edge cases |
| NDJSON decompression | Custom gzip reader | `gzip.open(path, 'rt')` | Built-in stdlib; already used in this pattern |
| Progress reporting in CLI | Custom print loop | `rich.progress.Progress` | Already installed (Phase 7); project pattern |
| USPS normalization of matched address for validation | Custom formatter | `scourgify.normalize_address_record()` again on reconstructed address | Existing ScourgifyValidationProvider does exactly this |

**Key insight:** The OA provider is largely an assembly of existing components: scourgify (input parse + output normalize), usaddress (street split at import time), SQLAlchemy async select (query), and the provider ABC pattern.

---

## Common Pitfalls

### Pitfall 1: geocode() Signature Mismatch

**What goes wrong:** `GeocodingService` calls `provider.geocode(normalized, http_client=http_client)` at line 124. The ABC only declares `(self, address: str)`. An OA geocode method declared as `async def geocode(self, address: str)` will raise `TypeError: geocode() got an unexpected keyword argument 'http_client'`.

**Why it happens:** Remote providers like `CensusGeocodingProvider` accept `http_client` as an optional kwarg. The service passes it unconditionally to all providers in the `local_providers` loop.

**How to avoid:** Declare `async def geocode(self, address: str, **kwargs) -> GeocodingResult:` or `async def geocode(self, address: str, http_client=None, **kwargs) -> GeocodingResult:` on the OA provider.

**Warning signs:** `TypeError` in test or runtime when calling geocode on the OA provider.

### Pitfall 2: Empty String vs NULL in Matching Query

**What goes wrong:** If import stores empty strings (not NULL), then a query with `WHERE postcode = '31204'` works but `WHERE postcode = ''` matches incorrectly stored empty-postcode records. Worse: if input parsing returns `None` for postcode and the query checks `WHERE postcode = None`, PostgreSQL treats that as `WHERE postcode IS NULL` in SQLAlchemy ORM context — but `postcode = ''` records would not match.

**Why it happens:** OA data uses `""` for absent values. If not converted during import, queries using `postcode = ?` with a real ZIP code will fail to match records where postcode was stored as empty string rather than NULL.

**How to avoid:** During import, convert empty string to `None` for all nullable fields: `number or None`, `street or None`, `postcode or None`, etc.

**Warning signs:** Zero match results even after loading data; records in table show empty string for postcode.

### Pitfall 3: Rich Progress with Unknown Total

**What goes wrong:** `Progress.add_task("...", total=X)` where X is the NDJSON line count — reading line count requires scanning the file first. Alternatively, `total=None` renders as indeterminate progress bar, which is valid but less informative.

**Why it happens:** NDJSON files don't have a header with record count. Gzip files don't expose decompressed line count cheaply.

**How to avoid:** Use `total=None` for an indeterminate/spinner style bar, OR do a single fast count pass before the import pass (`sum(1 for _ in gzip.open(file, 'rt'))`). The two-pass approach is reasonable for files up to ~70k rows (Bibb County = 67,730 lines). Decision is Claude's discretion — recommend two-pass for better UX.

**Warning signs:** Progress bar shows no percentage or `?/?` records.

### Pitfall 4: Reconstructing Address for Scourgify Normalization in Validation

**What goes wrong:** After matching an OA row, the validation provider must pipe the matched address through scourgify for USPS normalization. If the reconstructed address string is missing components (e.g., no city because OA `city` is NULL), scourgify may raise `IncompleteAddressError`.

**Why it happens:** Some OA records lack city or postcode. Reconstructing as `f"{street_number} {street_name} {street_suffix}, {city}, {region} {postcode}"` fails if fields are None.

**How to avoid:** Only include non-None components in the reconstructed string. If scourgify fails on the matched OA address, fall back to returning a ValidationResult built directly from the raw OA components without scourgify normalization.

**Warning signs:** `IncompleteAddressError` from scourgify during validation of addresses with sparse OA data.

### Pitfall 5: usaddress Import Edge Case Losing Street Name

**What goes wrong:** For streets like `"MANNING MILL"` that get tagged as `LandmarkName` by usaddress, `name_parts` (tokens with label `StreetName`) will be empty. Without the fallback, `street_name` would be stored as empty string or raise an error.

**Why it happens:** usaddress CRF model assigns `LandmarkName` to ambiguous noun phrases that don't match address patterns.

**How to avoid:** When `name_parts` is empty, fall back to storing the full `street` field as `street_name` with `street_suffix=NULL`. This means matching queries against these streets will only succeed if the input parse also produces the full street string in its name component — which it should via the same scourgify/usaddress path.

---

## Code Examples

### OA Provider Constructor and is_local

```python
# Source: base.py pattern + CONTEXT.md decision + database.py AsyncSessionLocal pattern
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from civpulse_geo.providers.base import GeocodingProvider

class OAGeocodingProvider(GeocodingProvider):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def is_local(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "openaddresses"
```

### No-Match GeocodingResult

```python
# Source: census.py NO_MATCH pattern
GeocodingResult(
    lat=0.0,
    lng=0.0,
    location_type="NO_MATCH",
    confidence=0.0,
    raw_response={},
    provider_name="openaddresses",
)
```

### No-Match ValidationResult (for OA validation provider)

When OA validation finds no match, it must return a ValidationResult with confidence=0.0. However, `ValidationResult` requires `normalized_address` and `address_line_1` as non-optional strings. Return empty strings for those fields on no-match:

```python
# Source: schemas.py ValidationResult analysis
ValidationResult(
    normalized_address="",
    address_line_1="",
    address_line_2=None,
    city=None,
    state=None,
    postal_code=None,
    confidence=0.0,
    delivery_point_verified=False,
    provider_name="openaddresses",
    original_input=address,
)
```

### Batch Geocode/Validate (Serial Loop)

```python
# Source: census.py + scourgify.py pattern — both use serial loops
async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult]:
    results = []
    for addr in addresses:
        result = await self.geocode(addr)
        results.append(result)
    return results
```

### Upsert in CLI Import

```python
# Source: existing CLI _import_feature() pattern adapted for openaddresses_points
conn.execute(
    text("""
        INSERT INTO openaddresses_points (
            source_hash, street_number, street_name, street_suffix,
            unit, city, district, region, postcode, location, accuracy
        ) VALUES (
            :source_hash, :street_number, :street_name, :street_suffix,
            :unit, :city, :district, :region, :postcode,
            ST_GeogFromText(:location), :accuracy
        )
        ON CONFLICT ON CONSTRAINT uq_oa_source_hash DO UPDATE
            SET street_number = EXCLUDED.street_number,
                street_name   = EXCLUDED.street_name,
                street_suffix = EXCLUDED.street_suffix,
                unit          = EXCLUDED.unit,
                city          = EXCLUDED.city,
                district      = EXCLUDED.district,
                region        = EXCLUDED.region,
                postcode      = EXCLUDED.postcode,
                location      = EXCLUDED.location,
                accuracy      = EXCLUDED.accuracy
        RETURNING id, (xmax = 0) AS was_inserted
    """),
    {...},
)
```

The `uq_oa_source_hash` unique constraint name is confirmed from `models/openaddresses.py` line `UniqueConstraint("source_hash", name="uq_oa_source_hash")`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Check table row count at startup for conditional registration | Always register, return NO_MATCH if empty | CONTEXT.md decision | Simpler lifespan; no async startup query needed |
| Hand-roll address component extraction | scourgify.normalize_address_record() | Existing provider pattern | Zero custom parser code |

---

## Open Questions

1. **Rich Progress total count (two-pass vs. indeterminate)**
   - What we know: NDJSON files don't self-report count; Bibb County = 67,730 lines
   - What's unclear: Whether the user prefers a percentage bar (two-pass) vs. spinner (total=None)
   - Recommendation: Two-pass is better UX for files the planner expects to be used interactively; implement two-pass (fast read then import)

2. **Shared helper for match query (single file vs. two providers)**
   - What we know: Both OAGeocodingProvider and OAValidationProvider need identical DB match logic
   - What's unclear: Best encapsulation (module-level function, classmethod, or shared base class)
   - Recommendation: Module-level `async def _find_oa_match(session, street_number, street_name, postcode)` in `openaddresses.py` — both provider classes call it; no base class overhead

3. **Validation no-match behavior**
   - What we know: ValidationResult requires `normalized_address: str` and `address_line_1: str` (no Optional)
   - What's unclear: Whether callers handle empty-string normalized_address for no-match
   - Recommendation: Follow scourgify pattern — raise `ProviderError` on no-match, OR return empty-string ValidationResult with confidence=0.0. CONTEXT says "binary confidence: match=1.0, no-match=0.0" which implies return (not raise). Use empty strings.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `asyncio_mode = "auto"` |
| Quick run command | `pytest tests/test_oa_provider.py tests/test_load_oa_cli.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OA-01 | `OAGeocodingProvider.geocode()` returns GeocodingResult with correct lat/lng on match | unit | `pytest tests/test_oa_provider.py::TestOAGeocodingProvider -x` | ❌ Wave 0 |
| OA-01 | `OAGeocodingProvider.geocode()` returns NO_MATCH on empty table | unit | `pytest tests/test_oa_provider.py::test_geocode_no_match -x` | ❌ Wave 0 |
| OA-01 | `load-oa` imports NDJSON rows into `openaddresses_points` | unit (mock DB) | `pytest tests/test_load_oa_cli.py -x` | ✅ exists (needs expansion) |
| OA-02 | `OAValidationProvider.validate()` returns ValidationResult with USPS-normalized fields on match | unit | `pytest tests/test_oa_provider.py::TestOAValidationProvider -x` | ❌ Wave 0 |
| OA-02 | `OAValidationProvider.validate()` returns no-match result (confidence=0.0) | unit | `pytest tests/test_oa_provider.py::test_validate_no_match -x` | ❌ Wave 0 |
| OA-03 | accuracy "rooftop" → location_type "ROOFTOP", confidence 1.0 | unit | `pytest tests/test_oa_provider.py::test_accuracy_mapping -x` | ❌ Wave 0 |
| OA-03 | accuracy "" → location_type "APPROXIMATE", confidence 0.1 | unit | `pytest tests/test_oa_provider.py::test_accuracy_mapping_empty -x` | ❌ Wave 0 |
| OA-04 | OA providers present in `app.state.providers` after lifespan start | unit | `pytest tests/test_oa_provider.py::test_oa_registered_in_lifespan -x` | ❌ Wave 0 |
| OA-04 | Empty `openaddresses_points` table → geocode returns NO_MATCH (not error) | unit | `pytest tests/test_oa_provider.py::test_empty_table_returns_no_match -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_oa_provider.py tests/test_load_oa_cli.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green (≥201 passing) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_oa_provider.py` — covers OA-01, OA-02, OA-03, OA-04 with mock async session factory
- [ ] `tests/test_load_oa_cli.py` — expand existing stubs to cover actual import behavior (batch upsert, skip malformed, progress reporting)

*(Existing `tests/test_load_oa_cli.py` covers PIPE-05 CLI registration; needs new test classes for Phase 8 import logic.)*

---

## Sources

### Primary (HIGH confidence)
- Direct code reading: `src/civpulse_geo/providers/base.py`, `census.py`, `scourgify.py`, `schemas.py`, `registry.py`, `exceptions.py` — provider patterns, signatures, ABC contract
- Direct code reading: `src/civpulse_geo/services/geocoding.py`, `validation.py` — how local providers are called, `http_client` kwarg passing
- Direct code reading: `src/civpulse_geo/models/openaddresses.py` — column names, constraint name `uq_oa_source_hash`, nullable fields
- Direct code reading: `src/civpulse_geo/cli/__init__.py` — existing `load-oa` stub, CLI patterns with `text()` raw SQL, commit cadence
- Direct code reading: `src/civpulse_geo/database.py` — `AsyncSessionLocal` async_sessionmaker pattern
- Direct code reading: `src/civpulse_geo/main.py` — lifespan pattern for provider registration
- Live data inspection: `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` — 67,730 NDJSON lines, confirmed property structure, all `accuracy=""` in Bibb County
- Live `usaddress.parse()` testing in project venv — confirmed behavior on OA street field values
- Live `scourgify.normalize_address_record()` testing — confirmed input/output for reconstructed OA addresses

### Secondary (MEDIUM confidence)
- `.planning/phases/08-openaddresses-provider/08-CONTEXT.md` — all locked decisions sourced from user discussion
- `.planning/STATE.md` — confirmed no new Python dependencies decision

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified present in venv, no new installs needed
- Architecture patterns: HIGH — all patterns derived from direct code reading of existing providers and services
- Pitfalls: HIGH — geocode signature mismatch and empty-string/NULL pitfalls verified from live code inspection; usaddress edge cases verified from live testing
- accuracy→location_type mapping: MEDIUM — the four string values (ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE) are confirmed from existing codebase; the specific OA accuracy value strings ("rooftop", "parcel", "interpolation", "centroid") are from OA spec documentation knowledge; Bibb County data has empty accuracy for all rows, so production mapping is empirically unverified

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable stack, 30-day window)
