# Feature Research

**Domain:** Local geocoding data source providers (OpenAddresses, NAD, PostGIS Tiger geocoder)
**Researched:** 2026-03-20
**Confidence:** HIGH (data schemas verified directly from actual data files; PostGIS functions confirmed via official documentation)

---

## Context: What This Milestone Adds

This research covers the v1.1 milestone: adding three local data source providers to the existing geo-api plugin architecture. All three implement the existing `GeocodingProvider` and `ValidationProvider` ABCs. The key behavioral difference from external providers: **no DB caching** — local providers return results directly without writing to `provider_results` table.

The previous FEATURES.md covered v1.0 (multi-provider cache pipeline, admin override, USPS validation). This file supersedes it for the v1.1 milestone.

---

## Data Source Schemas (Verified from Actual Files)

### OpenAddresses (data/*.geojson.gz, collection-us-south.zip)

**Format:** Newline-delimited GeoJSON (one JSON feature per line, gzip-compressed).
Confirmed from `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz`.

**Feature schema per line:**
```json
{
  "type": "Feature",
  "properties": {
    "hash": "bed3195d7ea1ba2b",
    "number": "489",
    "street": "NORTHMINISTER DR",
    "unit": "",
    "city": "MACON",
    "district": "BIBB",
    "region": "",
    "postcode": "31204",
    "id": "",
    "accuracy": ""
  },
  "geometry": {
    "type": "Point",
    "coordinates": [-83.687444, 32.8720832]
  }
}
```

**Field semantics (from openaddresses/openaddresses schema):**
- `number`: House/building number (string, may include alpha suffix like "100A")
- `street`: Street name including type, USPS-style ("NORTHMINISTER DR")
- `unit`: Suite/apt/unit designator, often empty string
- `city`: City/locality name, uppercase
- `district`: County name (not always populated)
- `region`: State/province — often empty; state is inferred from file path (`us/ga/bibb-addresses-county.geojson`)
- `postcode`: ZIP or ZIP+4
- `id`: Source-system identifier (often empty)
- `accuracy`: Point precision — values: `""`, `"rooftop"`, `"parcel"`, `"interpolated"`, `"centroid"`
- `hash`: OpenAddresses internal dedup hash (16-char hex)
- `geometry.coordinates`: [longitude, latitude] in WGS84

**Collection zip layout** (`collection-us-south.zip`, 3,054 files):
```
us/fl/washington-addresses-county.geojson
us/fl/washington-addresses-county.geojson.meta
us/ga/bibb-addresses-county.geojson
us/ga/bibb-addresses-county.geojson.meta
...
```
Path pattern: `us/{state_abbr}/{county_slug}-addresses-county.geojson`
Also contains `-parcels-county.geojson` files (not needed for address geocoding).
Each `.geojson.meta` file is a JSON object with run metadata (source, layer, status).

**Geocoding query pattern:**
Parse input address into components (number, street, city, state, ZIP), then exact-match
after normalization against `number` + `street` + `city`/`postcode` fields.
Coordinates come directly from `geometry.coordinates` — these are address points
(rooftop or parcel centroid), so location_type maps to "ROOFTOP" or "GEOMETRIC_CENTER".

**Validation pattern:**
A found record confirms the address exists in the dataset. Use matched record's
`number + street + unit + city + postcode` fields to populate `ValidationResult`.
`delivery_point_verified = False` (OA is not a USPS DPV source).

---

### National Address Database / NAD (data/NAD_r21_TXT.zip)

**Format:** Single large CSV: `TXT/NAD_r21.txt`, UTF-8 BOM, comma-delimited.
**Size:** 35.8 GB uncompressed, ~7.8 GB compressed. Officially ~80M addresses.

**Key columns for geocoding/matching (60 total, comma-delimited per schema.ini):**

| Column | Index | Type | Notes |
|--------|-------|------|-------|
| `Add_Number` | 2 | Long | House number (integer) |
| `AddNo_Full` | 4 | Text | Full address number string (includes alpha suffix if any) |
| `St_PreDir` | 6 | Text | Predirectional (N, S, E, W) |
| `St_Name` | 9 | Text | Street name |
| `St_PosTyp` | 10 | Text | Street type (Road, Avenue, Street...) |
| `St_PosDir` | 11 | Text | Postdirectional |
| `Unit` | 16 | Text | Unit/apartment |
| `Post_City` | 24 | Text | Postal city name (may be "Not stated") |
| `State` | 33 | Text | Two-letter state abbreviation |
| `Zip_Code` | 34 | Text | ZIP code (may be empty) |
| `Plus_4` | 35 | Text | ZIP+4 extension |
| `Longitude` | 39 | Double | WGS84 longitude |
| `Latitude` | 40 | Double | WGS84 latitude |
| `Placement` | 43 | Text | Point type (see mapping below) |
| `Lifecycle` | 50 | Text | Address status (see below) |
| `Addr_Type` | 56 | Text | Address classification |
| `DeliverTyp` | 57 | Text | Delivery type (unreliable in this dataset) |

**Placement domain values (from 500k-row sample):**
- `"Structure - Rooftop"` or `"Structure - Entrance"` → maps to ROOFTOP
- `"Parcel - Centroid"` or `"Parcel - Other"` → maps to GEOMETRIC_CENTER
- `"Linear Geocode"` or `"Property Access"` → maps to RANGE_INTERPOLATED
- `"Site"` → maps to GEOMETRIC_CENTER
- `"Unknown"` or `""` → maps to APPROXIMATE (~91% of rows in sample)

**Lifecycle domain values (from 500k-row sample):**
- `"ACTIVE"` — explicitly flagged active (~9% of sample rows, from higher-quality sources)
- `""` — not stated (majority; treat as geocodable — most rows are valid address points)
- Malformed values exist in a small fraction of rows (data quality issue from some contributors)

**Key data quality finding:**
The vast majority of rows have `Lifecycle=""` and `Placement="Unknown"`. This is normal — most contributing agencies do not populate these optional fields. Both empty-Lifecycle and ACTIVE rows are valid geocoding candidates. Filtering to ACTIVE-only would eliminate most of the dataset.

**DeliverTyp is not reliable:** Mostly empty in r21 TXT export. Not usable for DPV confirmation.

**Geocoding query pattern:**
Parse input → match on `Add_Number` + `St_Name` + `St_PosTyp` + `State` + `Zip_Code`.
Coordinate columns `Latitude` and `Longitude` are already WGS84 decimal degrees.
Location type mapped from `Placement` field per table above.

**Validation pattern:**
Same as OpenAddresses — found record confirms address exists; reconstruct
`ValidationResult` from matched row. `delivery_point_verified = False`.

**Scale challenge:** 35.8 GB uncompressed — cannot be loaded into memory or streamed per query.
Must be pre-indexed into a PostGIS table or equivalent for query-time lookup.
This is the single most significant implementation complexity in this milestone.

---

### PostGIS Tiger/LINE Geocoder (PostgreSQL extension)

**Setup:** Requires `postgis_tiger_geocoder` extension plus TIGER/LINE shapefiles
loaded into `tiger` and `tiger_data` schemas via generated loader scripts.

**Extensions required:**
```sql
CREATE EXTENSION postgis;
CREATE EXTENSION fuzzystrmatch;
CREATE EXTENSION postgis_tiger_geocoder;
CREATE EXTENSION address_standardizer;  -- optional, improves normalization accuracy
```

**Geocode function signature (from official PostGIS docs):**
```sql
setof record geocode(
  varchar address,
  integer max_results=10,
  geometry restrict_region=NULL,
  norm_addy OUT addy,
  geometry OUT geomout,
  integer OUT rating
)
```

**Return schema:**
- `geomout`: Point geometry in NAD83 long/lat (compatible with WGS84 for practical US geocoding)
- `rating`: Match quality — 0 = exact match, higher = lower confidence; sorted ascending (lower is better)
- `addy`: `norm_addy` composite type with fields: `address` (street number), `predirAbbrev`, `streetName`,
  `streetTypeAbbrev`, `postdirAbbrev`, `internal` (unit), `location` (city), `stateAbbrev`, `zip`,
  `parsed` (bool), `zip4`, `address_alphanumeric`

**Standard geocoding SQL (Python via SQLAlchemy text()):**
```sql
SELECT
  g.rating,
  ST_X(g.geomout)       AS lon,
  ST_Y(g.geomout)       AS lat,
  pprint_addy(g.addy)   AS normalized_address,
  (g.addy).address      AS street_number,
  (g.addy).streetname   AS street_name,
  (g.addy).location     AS city,
  (g.addy).stateabbrev  AS state,
  (g.addy).zip          AS zip
FROM geocode(:address, 1) AS g;
```

**Address normalization/validation SQL (works without TIGER data loaded):**
```sql
SELECT pprint_addy(normalize_address(:address)) AS normalized;
```
`normalize_address()` uses only bundled lookup tables (directions, states, street type suffixes) —
does not require TIGER shapefile data. The `parsed` field on `norm_addy` indicates success.

**Confidence mapping from rating:**
`confidence = max(0.0, 1.0 - rating / 100.0)` with a floor of 0.0.

**Python async integration:**
Tiger geocoder runs as a PostgreSQL function — called via `await db.execute(text(...), {"address": addr})`
using the existing SQLAlchemy async session. No additional Python libraries needed.
Geometry extracted with `ST_X(geomout)` / `ST_Y(geomout)` in the SQL to avoid WKB parsing.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the milestone must deliver. Missing any of these = milestone incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| OpenAddresses geocoding provider | Core milestone requirement; data files present | MEDIUM | Newline-delimited GeoJSON scan; needs fast lookup — in-memory dict for dev (county files), PostGIS import for production |
| OpenAddresses validation provider | Expected alongside geocoding; same data source | LOW | Geocode first, map matched record fields to ValidationResult; delivery_point_verified=False |
| NAD geocoding provider | Core milestone requirement; data files present | HIGH | 35.8 GB uncompressed requires pre-import to PostGIS with indexed columns; cannot stream at query time |
| NAD validation provider | Expected alongside geocoding; same PostGIS table | LOW after NAD import | Reuses NAD table query; maps matched row to ValidationResult |
| PostGIS Tiger geocoder provider | Core milestone requirement; PostGIS 3.5 installed | MEDIUM | SQL call via existing async session; graceful failure when TIGER data not loaded |
| PostGIS Tiger validation provider | normalize_address() works without TIGER data | LOW | Uses bundled lookup tables — always available when extension is installed |
| Direct-return pipeline (no DB caching) | Explicitly required in PROJECT.md Active requirements | MEDIUM | GeocodingService must branch: local providers bypass cache write and Address row creation |
| location_type mapping per provider | GeocodingResult.location_type must use LocationType enum | LOW | OA: from accuracy field; NAD: from Placement field; Tiger: from rating heuristic |
| NAD import CLI command | Required for NAD provider to function | MEDIUM | Typer CLI consistent with existing GIS import CLI; reads TXT.zip, streams into PostGIS table |
| No-match result (GeocodingResult with confidence=0.0) | All providers must handle address not found | LOW | Follow existing census provider pattern: lat=0.0, lng=0.0, confidence=0.0 |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| NAD pre-import to PostGIS with spatial+text index | Converts unusable 35.8 GB flat file into a fast queryable source | HIGH | One-time CLI import; ~80M rows; needs B-tree index on (state, zip_code, add_number, st_name) minimum |
| OpenAddresses in-memory dict for county files | County-scoped files fit in RAM for dev use | LOW | Bibb county file is tiny; appropriate for dev/testing; same provider ABC works |
| Tiger normalize_address() as always-available validation | Works without TIGER shapefile data | LOW | Validation provider functional even when geocode() has no data; decouples the two |
| Optional Tiger setup scripts | Lowers barrier to enabling Tiger geocoder in Docker Compose | MEDIUM | Generates and runs Census TIGER/LINE loader scripts; works-without flag avoids hard dependency |
| Graceful provider-unavailable handling | Clear error when extension/data not loaded; no crash | LOW | Check extension presence at startup via SQL; configure as optional provider |
| scourgify pre-normalization before local lookup | Normalizes "Road" → "RD", "Georgia" → "GA" before matching | LOW | Existing scourgify provider already handles this; compose, don't duplicate |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Streaming NAD lookup (scan 35.8 GB per query) | Avoids separate import step; simpler code | 35.8 GB sequential scan per geocode request is unusable at any scale (minutes per query) | Pre-import to PostGIS with indexed columns; one-time cost unlocks millisecond queries |
| delivery_point_verified=True for local providers | Caller wants mail-deliverable confirmation | None of the three sources have USPS DPV data — OA/NAD are address point datasets, not USPS databases | Keep delivery_point_verified=False; document limitation; recommend USPS v3 API for DPV |
| Caching local provider results to DB | Seems consistent with external provider pattern | Local providers exist to avoid DB round-trips; caching negates purpose and adds write overhead for fast-path queries | Skip cache writes entirely via pipeline branch; consistent with PROJECT.md Active requirement |
| Fuzzy/phonetic matching in OA and NAD providers | Handles misspellings and abbreviation variants | Adds significant complexity; scourgify normalization + exact match handles most real cases; Tiger already uses soundex internally | Normalize input with scourgify first, then exact match; Tiger handles fuzziness natively |
| Loading full national NAD into memory | Simplest Python code path | ~80M rows × ~350 bytes = ~28 GB RAM requirement; not deployable | PostGIS import with indexed table; SQL queries run in milliseconds |
| Loading all OA collection files at startup | Maximum coverage from a single provider | collection-us-south.zip alone has 1,527 geojson files; full US would be much larger | Support per-file or PostGIS import; county-level for dev, state-level import for production |
| Lifecycle=ACTIVE-only filter for NAD | Seems like it would return only valid addresses | ~91% of rows have empty Lifecycle; filtering to ACTIVE would eliminate most of the dataset | Include both ACTIVE and empty-Lifecycle rows; filter on Longitude/Latitude IS NOT NULL instead |

---

## Feature Dependencies

```
[NAD geocode + validate providers]
    └──requires──> [NAD PostGIS import CLI]
                       └──requires──> [data/NAD_r21_TXT.zip present]
                       └──requires──> [PostgreSQL with PostGIS for target table]

[OpenAddresses geocode + validate providers]
    └──requires──> [data/*.geojson.gz present]
    └──option A (dev)──> [in-memory dict at startup for small county files]
    └──option B (prod)──> [OA PostGIS import CLI for full coverage]

[PostGIS Tiger geocoder provider (geocode)]
    └──requires──> [postgis_tiger_geocoder extension installed]
    └──requires──> [TIGER/LINE data loaded into tiger_data schema]
    └──optional──> [Tiger setup scripts to load TIGER data]

[PostGIS Tiger validation provider]
    └──requires──> [postgis_tiger_geocoder extension installed]
    └──note──> does NOT require TIGER data — normalize_address() uses bundled tables

[Direct-return pipeline]
    └──requires──> [all three provider pairs above]
    └──requires──> [GeocodingService pipeline branch distinguishing local from remote]

[scourgify normalization (existing, already built)]
    └──enhances──> [all three local providers]
    └──rationale──> normalize "Road"→"RD", "Georgia"→"GA" before matching

[Tiger setup scripts]
    └──enhances──> [PostGIS Tiger geocoder provider]
    └──note──> optional — Tiger validation works without them
```

### Dependency Notes

- **NAD provider requires NAD PostGIS import:** The 35.8 GB flat file cannot be queried at runtime. A CLI import step pre-loads ~80M rows into a PostGIS table with indexes. This is a one-time setup cost, not per-request.
- **OpenAddresses in-memory vs PostGIS are two valid strategies:** In-memory dict works for county-level `.geojson.gz` files during development. Production deployments with multi-state coverage need PostGIS import. Both strategies use the same provider ABC — the strategy is a constructor argument.
- **Tiger validation does not require Tiger geocoding data:** `normalize_address()` uses only lookup tables bundled with the `postgis_tiger_geocoder` extension. The validation provider can always be available while the geocoding provider is optional (gated on TIGER/LINE data being loaded).
- **Direct-return pipeline requires service-layer changes:** The existing `GeocodingService` unconditionally writes to `provider_results`. A routing decision must be added to distinguish local providers (direct return, no DB writes) from remote providers (cache-write path). No `Address` row created, no `OfficialGeocoding` set for local results.
- **scourgify pre-normalization should compose with local providers:** Run input through scourgify normalization before passing to OA/NAD/Tiger lookup. The existing `ScourgifyValidationProvider` is pure Python with no I/O — safe to call synchronously from within async provider methods. This maximizes match rate without adding fuzzy matching complexity.

---

## MVP Definition

### Launch With (v1.1 milestone — all required)

- [ ] OpenAddresses geocoding provider — data files present; enables local lookup with no external API
- [ ] OpenAddresses validation provider — reuses same data; minimal additional work over geocoding
- [ ] NAD import CLI command — required for NAD provider to function; Typer CLI consistent with existing GIS import
- [ ] NAD geocoding provider — PostGIS table + index from import CLI; fast address lookup
- [ ] NAD validation provider — reuses NAD PostGIS query; minimal additional work
- [ ] PostGIS Tiger geocoder provider — leverages existing PostGIS 3.5 infrastructure
- [ ] PostGIS Tiger validation provider — normalize_address() always available; low effort
- [ ] Direct-return pipeline (no DB caching for local providers) — required per PROJECT.md Active requirements
- [ ] Optional Tiger setup scripts — lowers barrier for Tiger geocoder; graceful when absent

### Add After Validation (v1.x)

- [ ] OpenAddresses PostGIS import CLI — for full-state or national coverage; trigger: production deployment need
- [ ] Per-state TIGER/LINE data loading — reduces storage vs loading all states; trigger: storage constraints
- [ ] NAD table partitioning by state — improves query performance; trigger: query latency above acceptable threshold

### Future Consideration (v2+)

- [ ] OpenAddresses incremental data refresh CLI — OA data is updated periodically; trigger: data staleness operational issue
- [ ] NAD Lifecycle=ACTIVE-only mode toggle — needs measurement first; filtering may reduce match rate unacceptably
- [ ] Reverse geocoding via Tiger Reverse_Geocode() — explicitly marked Out of Scope in PROJECT.md v1

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Direct-return pipeline | HIGH | MEDIUM | P1 |
| OpenAddresses provider (geocode + validate) | HIGH | MEDIUM | P1 |
| NAD import CLI | HIGH | MEDIUM | P1 |
| NAD provider (geocode + validate) | HIGH | LOW after import CLI | P1 |
| Tiger geocoder provider | HIGH | MEDIUM | P1 |
| Tiger validation provider | MEDIUM | LOW | P1 |
| Tiger setup scripts | MEDIUM | MEDIUM | P2 |
| OpenAddresses PostGIS import CLI | MEDIUM | MEDIUM | P2 |
| NAD table partitioning | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Required for v1.1 milestone
- P2: Enhances production readiness; add post-milestone
- P3: Future consideration; defer until need is demonstrated

---

## Provider Behavior Reference

### location_type Mapping

| Provider | Source Field | Value | location_type |
|----------|-------------|-------|---------------|
| OpenAddresses | `accuracy` | `"rooftop"` | `ROOFTOP` |
| OpenAddresses | `accuracy` | `"parcel"` | `GEOMETRIC_CENTER` |
| OpenAddresses | `accuracy` | `"interpolated"` | `RANGE_INTERPOLATED` |
| OpenAddresses | `accuracy` | `""` or `"centroid"` | `GEOMETRIC_CENTER` |
| NAD | `Placement` | `"Structure - Rooftop"` or `"Structure - Entrance"` | `ROOFTOP` |
| NAD | `Placement` | `"Parcel - Centroid"` or `"Parcel - Other"` | `GEOMETRIC_CENTER` |
| NAD | `Placement` | `"Linear Geocode"` or `"Property Access"` | `RANGE_INTERPOLATED` |
| NAD | `Placement` | `"Unknown"` or `""` | `APPROXIMATE` |
| Tiger | `rating` | `0` | `ROOFTOP` |
| Tiger | `rating` | `1–30` | `RANGE_INTERPOLATED` |
| Tiger | `rating` | `>30` | `APPROXIMATE` |

### confidence Mapping

| Provider | Condition | confidence |
|----------|-----------|------------|
| OpenAddresses | Found, accuracy = "rooftop" | 0.95 |
| OpenAddresses | Found, accuracy other | 0.85 |
| OpenAddresses | Not found | 0.0 |
| NAD | Found, Placement = Structure | 0.95 |
| NAD | Found, Placement = Parcel | 0.85 |
| NAD | Found, Placement = Unknown/empty | 0.75 |
| NAD | Not found | 0.0 |
| Tiger | Found | `max(0.0, 1.0 - rating / 100.0)` |
| Tiger | Not found | 0.0 |

### delivery_point_verified

All three local providers: **always False**.
- OpenAddresses: community-collected address points; no USPS DPV
- NAD: E911/transportation authority address points; no USPS DPV
- Tiger: TIGER/LINE street range interpolation; no USPS DPV

For USPS DPV confirmation, the USPS Address Information API or a provider like SmartyStreets is required. That is a v2+ concern per PROJECT.md.

### No-Cache Pipeline

Local providers bypass the standard GeocodingService write path:
1. Input normalized via scourgify
2. Provider queried directly (OA dict/file, NAD PostGIS table, Tiger SQL function)
3. GeocodingResult returned to caller
4. No `Address` row created or looked up
5. No `provider_results` write
6. No `OfficialGeocoding` set

This satisfies the "direct-return pipeline" requirement in PROJECT.md Active requirements.

---

## Sources

- OpenAddresses schema: [openaddresses/openaddresses schema/layers/address_conform.json](https://github.com/openaddresses/openaddresses/blob/master/schema/layers/address_conform.json)
- PostGIS Geocode function: [postgis.net/docs/Geocode.html](https://postgis.net/docs/Geocode.html)
- PostGIS Normalize_Address: [postgis.net/docs/Normalize_Address.html](https://postgis.net/docs/Normalize_Address.html)
- PostGIS Extras (Tiger geocoder overview): [postgis.net/docs/Extras.html](https://postgis.net/docs/Extras.html)
- NAD schema documentation: [transportation.gov — NAD Schema April 2023](https://www.transportation.gov/sites/dot.gov/files/2023-07/NAD_Schema_202304.pdf)
- RustProof Labs Tiger setup guide: [blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup](https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup)
- Data schema verified directly from on-disk files:
  - `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` (OpenAddresses newline-delimited GeoJSON)
  - `data/NAD_r21_TXT.zip` → `TXT/NAD_r21.txt` and `TXT/schema.ini` (60 columns, field types, sample rows)
  - `data/collection-us-south.zip` (3,054 files; path/naming pattern; meta format)
  - NAD field domain values sampled from first 500,000 rows of NAD_r21.txt

---

*Feature research for: local geocoding data source providers (OpenAddresses, NAD, PostGIS Tiger/LINE)*
*Researched: 2026-03-20*
