# Technology Stack

**Project:** CivPulse Geo API — v1.1 Local Data Source Providers
**Researched:** 2026-03-20
**Confidence:** HIGH — all findings verified against actual data files in `data/` and installed packages in the project virtualenv. Previous entries below the divider are preserved from v1.0 research.

---

## v1.1 Milestone: Stack Additions for Local Providers

### Executive Finding

**No new Python libraries are required.** The full implementation of all three local providers (OpenAddresses, NAD, PostGIS Tiger) fits entirely within the existing dependency footprint. The critical insight is that each data source maps to capabilities already present:

| Provider | Data Format | Reading Method | Status |
|----------|-------------|----------------|--------|
| OpenAddresses | `.geojson.gz` (GeoJSONL) | stdlib `gzip` + `json` | In stdlib |
| NAD r21 TXT | CSV with BOM in zip | stdlib `csv.DictReader` + `zipfile` | In stdlib |
| NAD r21 FGDB | Esri File GDB | `fiona` OpenFileGDB driver | Already installed |
| PostGIS Tiger | PostgreSQL extension | `sqlalchemy.text()` + `asyncpg` | Already installed |
| Address parsing for lookup | Freeform → components | `usaddress` | Already in `uv.lock` (transitive dep) |

---

### Format Verification (Against Actual Files)

#### OpenAddresses `.geojson.gz` — GeoJSONL, not GeoJSON

Files are **newline-delimited GeoJSONL**, one Feature per line. `json.load(f)` raises `JSONDecodeError: Extra data` — do not use it. Confirmed from `US_GA_Bibb_Addresses_2026-03-20.geojson.gz`:

```
{"type":"Feature","properties":{"hash":"bed3195d","number":"489","street":"NORTHMINISTER DR",
 "unit":"","city":"MACON","district":"","region":"","postcode":"31204","id":"","accuracy":""},
 "geometry":{"type":"Point","coordinates":[-83.687444,32.872083]}}
```

Fields: `number` (house number), `street` (full street), `unit`, `city`, `postcode`. No state field — state is encoded in the filename (`US_GA_Bibb_*`). Coordinates are `[lng, lat]`.

Correct reading pattern:
```python
import gzip, json

with gzip.open(path, 'rt', encoding='utf-8') as f:
    for line in f:
        feature = json.loads(line)           # NOT json.load(f)
        props = feature['properties']
        lng, lat = feature['geometry']['coordinates']
```

#### NAD r21 TXT — CSV with BOM, 60 fields

Standard CSV, `utf-8-sig` encoding (byte-order mark). 7.3 GB zip containing `TXT/NAD_r21.txt`. Key address fields:

| Field | Content | Example |
|-------|---------|---------|
| `Add_Number` | House number integer | `1000` |
| `StNam_Full` | Full street name with type | `Sand Point Avenue` |
| `Post_City` | Mailing city | `Not stated` |
| `State` | 2-letter state code | `AK` |
| `Zip_Code` | ZIP (may have spaces) | `99661` |
| `Latitude` | Decimal degrees | `55.335591` |
| `Longitude` | Decimal degrees | `-160.502740` |

Streaming pattern (do NOT load full 7.3 GB into memory):
```python
import csv, zipfile, io

with zipfile.ZipFile('NAD_r21_TXT.zip') as z:
    with z.open('TXT/NAD_r21.txt') as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))
        for row in reader:
            lat = float(row['Latitude']) if row['Latitude'] else None
            lon = float(row['Longitude']) if row['Longitude'] else None
```

#### NAD r21 FGDB — Esri File GDB, readable with existing fiona

`fiona` 1.10.1 (already installed) supports the `OpenFileGDB` driver — no ESRI license required. Verified: `'OpenFileGDB'` is in `fiona.supported_drivers` in the project virtualenv.

The `.gdb` directory must be extracted from the zip before fiona can read it. Same schema as TXT.

**Decision: prefer TXT over FGDB for the runtime provider.** TXT is streamable from inside the zip without extraction. FGDB support belongs in the CLI import command only, not the live provider.

#### PostGIS Tiger Geocoder — SQL extensions, no Python library

The `postgis/postgis:17-3.5` Docker image includes Tiger geocoder binaries. One-time SQL to enable:

```sql
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS address_standardizer;
```

The `geocode()` function signature (unchanged since PostGIS 2.1):
```sql
geocode(address varchar, max_results int DEFAULT 10)
  RETURNS SETOF RECORD (addy norm_addy, geomout geometry, rating integer)
```

Calling from existing async session:
```python
from sqlalchemy import text

result = await session.execute(
    text("SELECT geomout, rating FROM geocode(:address, 1)"),
    {"address": normalized_address}
)
row = result.first()
# row.rating: integer, lower = better match; 0 is exact
# row.geomout: WKB geometry in NAD83 lon/lat
```

The Tiger schema must be on `search_path`. Add `tiger,tiger_data` to the DB `search_path` or use fully-qualified `tiger.geocode(...)`.

**Tiger data is not included in the Docker image** — it must be loaded separately via Census Bureau download scripts. The provider must check for Tiger availability at startup and surface a structured "not configured" response rather than raising an unhandled error.

#### Address Parsing for Local Lookups — `usaddress` already in lock file

`usaddress` 0.5.16 (released August 2025) is already locked in `uv.lock` as a transitive dependency of `usaddress-scourgify`. Use it directly without adding to `pyproject.toml`.

```python
import usaddress

tags, address_type = usaddress.tag("489 Northminister Dr, Macon GA 31204")
# tags: OrderedDict([('AddressNumber', '489'), ('StreetName', 'Northminister'),
#        ('StreetNamePostType', 'Dr'), ('PlaceName', 'Macon'), ('StateName', 'GA'),
#        ('ZipCode', '31204')])
```

Use this to decompose freeform input before field-matching against NAD or OA data. Do not add `usaddress` to `pyproject.toml` — it is already available.

---

### What NOT to Add

| Do Not Add | Why | Use Instead |
|------------|-----|-------------|
| `pyogrio` | Faster than fiona for bulk DataFrame reads, but adds geopandas dependency chain (~200 MB). Providers stream single records — fiona overhead is negligible | `fiona` (already installed) |
| `geopandas` | Heavy: numpy + pandas + shapely + pyogrio. Providers are stream-and-filter, not bulk DataFrame operations | stdlib + fiona |
| `shapely` (explicit) | No geometric operations needed in providers. Coordinates are simple floats; distance checks belong in PostGIS | Not needed |
| `rtree` / `libspatialindex` | In-memory nearest-neighbor for millions of points is only needed if loading all data into application memory — don't do this. Import to PostGIS and use GIST indexes | PostGIS GIST indexes |
| `pandas` | NAD TXT is 7.3 GB; chunked pandas adds complexity with no benefit over `csv.DictReader` streaming | stdlib `csv.DictReader` |
| `usaddress` in pyproject.toml | Already a transitive dep — adding explicitly creates version conflict risk | `import usaddress` directly |
| `geocoder` (PyPI) | In `uv.lock` as a transitive dep but is a separate geocoding library. Do not use in providers | Custom provider ABCs |

---

### Direct-Return Pipeline: No New Libraries Required

The requirement for a "direct-return pipeline that bypasses DB caching for local providers" is a service-layer concern, not a library concern. The existing `GeocodingProvider` and `ValidationProvider` ABCs support this — local providers implement the same ABCs but the calling service skips the cache write step. No new infrastructure needed.

---

### Tiger Setup Script: Not a Migration

Tiger extension creation and data loading are operational setup, not schema migrations. Do not add to Alembic. Implement as `scripts/setup_tiger.sql` or `scripts/load_tiger.sh` that:
1. Creates three SQL extensions
2. Updates `tiger.loader_variables` with TIGER data year and staging dir
3. Calls `Loader_Generate_Nation_Script()` / `Loader_Generate_Script()` for required states
4. Documents that data download is a one-time manual step per deployment

---

### Spatial Indexing for Imported OA/NAD Data

If OA and NAD data are imported into PostGIS via the existing CLI (recommended), spatial indexing is free — the existing GIST index pattern already applies. Implement providers against PostGIS tables, not against raw files streamed at query time.

If file-based lookup is required (no import step), stream and filter by pre-indexing in Python dicts keyed by state+zip. No spatial index library needed for exact address matching; spatial indexing only matters for nearest-neighbor / bounding-box queries, which are not in scope.

---

## Version Compatibility

| Package | Locked Version | Notes |
|---------|---------------|-------|
| `fiona` | 1.10.1 | OpenFileGDB driver confirmed present in venv |
| `usaddress` | 0.5.16 (transitive) | Released Aug 2025, locked in uv.lock |
| PostGIS | 3.5 | `geocode()` signature unchanged since PostGIS 2.1 |
| `sqlalchemy` | 2.0.x | `text()` + `await session.execute()` confirmed working |
| `asyncpg` | 0.31.0 | No changes needed for Tiger calls |

---

## Sources

- File inspection: `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` — confirmed GeoJSONL line-delimited format, field schema (HIGH confidence)
- File inspection: `data/NAD_r21_TXT.zip/TXT/schema.ini` + `NAD_r21.txt` — confirmed 60-field CSV schema, BOM encoding (HIGH confidence)
- `fiona.supported_drivers` in project venv — confirmed `OpenFileGDB` driver available in fiona 1.10.1 (HIGH confidence)
- `uv.lock` — confirmed `usaddress==0.5.16` already locked (HIGH confidence)
- [PostGIS geocode() function docs](https://postgis.net/docs/Geocode.html) — function signature, return type (HIGH confidence)
- [PostGIS Tiger setup — RustProof Labs](https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup) — extension creation steps (MEDIUM confidence)
- [GDAL OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html) — no ESRI license required for read (HIGH confidence)
- [pyogrio about](https://pyogrio.readthedocs.io/en/latest/about.html) — why it's not needed here (HIGH confidence)
- [postgis/docker-postgis](https://github.com/postgis/docker-postgis) — Tiger extension included in official image (MEDIUM confidence)

---

## v1.0 Stack (Pre-existing, Validated — No Changes)

The entries below document the validated v1.0 stack. No changes are required for v1.1.

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12+ | Runtime | Matches other CivPulse APIs; 3.12 has significant perf improvements over 3.11 |
| FastAPI | 0.135+ | HTTP API framework | Pre-decided; async-native, Pydantic v2 integration, OpenAPI autodoc |
| Pydantic | v2 (2.x) | Request/response models, validation | Ships with FastAPI; v2 significantly faster than v1 |
| Loguru | 0.7+ | Structured logging | Pre-decided; simpler than stdlib logging |
| Typer | 0.24+ | CLI commands | Pre-decided; pairs with FastAPI for management commands |

### Database Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 17 | Primary datastore | Pre-decided; required for PostGIS |
| PostGIS | 3.5 | Spatial types and queries | Pre-decided; Geography(POINT,4326) provides distance-in-meters semantics |
| GeoAlchemy2 | 0.18.4 | SQLAlchemy spatial type integration | Standard bridge; handles WKB serialization and Alembic migration types |
| SQLAlchemy | 2.0+ | ORM / query builder | Async support via asyncpg; required by GeoAlchemy2 |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async Postgres driver; required for SQLAlchemy async engine |
| psycopg2-binary | 2.9.11 | Synchronous Postgres driver for Alembic | Alembic requires synchronous driver; asyncpg cannot be used for migrations |
| Alembic | 1.18.4 | Schema migrations | Standard SQLAlchemy migration tool |

### Address Parsing and HTTP

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| usaddress-scourgify | 0.6.0 | USPS-standard address normalization | Offline normalization for cache key generation; no external API needed |
| httpx | 0.28.1 | Async HTTP client for external providers | Async-native; used for Census Geocoder provider |
| fiona | 1.10.1 | Spatial file I/O (SHP, GDB, KML) | Used in GIS import CLI; OpenFileGDB driver for NAD FGDB |

---
*Stack research for: CivPulse Geo API v1.1 Local Data Source Providers*
*Researched: 2026-03-20*
