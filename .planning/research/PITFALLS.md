# Pitfalls Research

**Domain:** Geocoding / Address Validation Caching API — Local Data Source Providers
**Project:** CivPulse Geo API
**Researched:** 2026-03-20 (v1.1 milestone update — local data sources)
**Confidence:** MEDIUM-HIGH — web-verified findings for new sections; training data for v1.0 sections retained

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or systemic reliability failures.

---

### Pitfall 1: Cache Key Does Not Survive Input Normalization

**What goes wrong:** The cache lookup uses the raw input string as the key. "123 Main St" and "123 main st" and "123 Main Street" all miss the cache and trigger fresh API calls, even though they refer to the same address. In production, callers rarely send consistent casing or abbreviation style.

**Why it happens:** It feels natural to hash or key on the input directly. The normalization step gets deferred ("we'll add it later"), and by then the cache has thousands of inconsistently keyed records.

**How to avoid:**
- Normalize the input address to a canonical form *before* the cache lookup, not after.
- Canonical form: uppercase, USPS abbreviations (ST/RD/AVE/BLVD), strip punctuation, collapse whitespace, expand unit designators (APT/STE/UNIT).
- Use `usaddress` (Python library) or a similar parser to decompose and re-serialize to a consistent form before hashing.
- Store both the raw input and the canonical form. Key on canonical form only.

**Warning signs:**
- Cache hit rate below 80% on repeated identical lookups.
- Duplicate rows in the cache table for visually identical addresses.

**Phase to address:** Address normalization must be implemented in Phase 1 / data model design, before any caching logic is built.

---

### Pitfall 2: Storing Coordinates as `FLOAT` or `NUMERIC` Instead of PostGIS `geography`

**What goes wrong:** Lat/lon are stored as two separate `FLOAT` or `NUMERIC` columns. All spatial queries (distance, containment, nearest-neighbor) require manual Haversine math in SQL or application code. Spatial indexes cannot be used. Future spatial feature requests require a schema migration.

**Why it happens:** It seems simpler initially, especially if the first use case is just "give me the coordinates." PostGIS feels like overhead when the schema is being drafted.

**How to avoid:**
- Use `Geography(Point, 4326)` from day one. SRID 4326 is WGS84 — what every geocoding API returns.
- Store with `SRID=4326;POINT(lng lat)` (longitude first — a common reversal mistake).
- Add a GiST index on the geography column.

**Warning signs:**
- Schema has `latitude FLOAT, longitude FLOAT` columns but no geometry/geography column.
- Any query calculating distance without using ST_Distance or ST_DWithin.

**Phase to address:** Data model design (Phase 1). Cannot be retrofitted cheaply.

---

### Pitfall 3: No Canonical Address Key Across Services

**What goes wrong:** Each geocoding service returns the address in its own format. These are stored under different keys, so a cache lookup for one service never benefits from a prior lookup via another. Admin cannot see all service results in one view.

**Why it happens:** Service results are stored verbatim. The design stores per-service results (correct) but doesn't establish a shared canonical address key linking them (wrong omission).

**How to avoid:**
- Separate canonical address identity (parsed, normalized, USPS-standard) from service result.
- Two-table design: `addresses` (canonical form, cache key) + `geocoding_results` (FK to address, service name, raw result, coordinates, confidence).
- Admin override attaches to the `addresses` record, not to a service result.

**Warning signs:**
- Cache table has a `service_name` column but no shared address identity column.
- "Show all results for this address" requires fuzzy string matching across rows.

**Phase to address:** Data model design (Phase 1). Two-table design must be established before building any service adapters.

---

### Pitfall 4: Google Geocoding API Terms of Service Violation — Caching

**What goes wrong:** Google's Geocoding API ToS prohibits caching geocoding results for use outside of displaying them on a Google Map. Storing results in a database and serving to downstream clients violates ToS.

**Why it happens:** Developers assume caching is always acceptable if it reduces cost.

**How to avoid:**
- Read Google Maps Platform Terms of Service before storing results: https://cloud.google.com/maps-platform/terms
- For US addresses: Census Geocoder (free, no caching restrictions) is a safer primary source.

**Warning signs:**
- Google listed as primary geocoding service with no ToS review documented.

**Phase to address:** Architecture / service selection (Phase 1). Must be resolved before building the Google adapter.

---

### Pitfall 5: Address Parser Failure on Freeform Input Causes Silent Cache Miss

**What goes wrong:** The normalization/parsing step fails on unusual but valid input (apartment numbers, rural routes, PO Boxes, hyphenated house numbers). The failure is silently swallowed and the input passed through un-normalized, causing a cache miss.

**Why it happens:** Parsers like `usaddress` return a best-effort parse that can fail or misclassify components. Error handling defaults to "continue with raw input" to avoid returning errors to the caller.

**How to avoid:**
- Treat parser failures as a known, logged event — not an error to silently swallow.
- Log parse failures at WARN level (Loguru) with the raw input.
- On parse failure, fall through to the external service but do NOT cache under a raw key.

**Warning signs:**
- No logging around the normalization step.
- Cache hit rate varies wildly by caller.

**Phase to address:** Address normalization implementation (Phase 1/2). Build the failure path explicitly.

---

### Pitfall 6: Local Providers Accidentally Writing to the Provider Cache

**What goes wrong:** OpenAddresses, NAD, and Tiger providers are added by inheriting from `GeocodingProvider` and registered alongside `CensusGeocodingProvider` in `main.py`. The existing `GeocodingService.geocode()` pipeline unconditionally calls all registered providers and then upserts results into `geocoding_results`. Local providers pollute the cache table with millions of local-data lookups. The `uq_geocoding_address_provider` unique constraint means each address gets at most one row per local provider — but at scale (NAD alone is 10+ GB compressed), the table becomes enormous and every API call triggers a database write.

**Why it happens:** The existing pipeline does not distinguish between "remote API providers that should be cached" and "local data providers that should return directly." It's easy to inherit the ABC and register the class without noticing that the pipeline writes to the DB.

**How to avoid:**
- Introduce a `direct_return` flag on the provider ABC (or a separate `LocalGeocodingProvider` base class) that the pipeline checks.
- In `GeocodingService.geocode()`: if all registered providers are local-only, skip the upsert steps entirely and return results directly without touching `geocoding_results`.
- Alternatively: maintain two separate provider registries (`app.state.providers` for cached providers, `app.state.local_providers` for direct-return). Route requests appropriately.
- Do NOT add local providers to `app.state.providers` (the cached pipeline registry).

**Warning signs:**
- Local provider class is registered in `main.py` in the same `load_providers()` call as `CensusGeocodingProvider`.
- `geocoding_results` table starts growing unexpectedly during local-provider testing.
- Integration tests check that local provider results are NOT in `geocoding_results`.

**Phase to address:** Local provider pipeline design — first phase of v1.1. This architectural boundary must be established before any local provider is implemented.

---

### Pitfall 7: Fiona / GDAL FileGDB Driver Not Available in PyPI Wheel

**What goes wrong:** `fiona` is installed from PyPI (via `uv add fiona`). PyPI wheels are pre-built with a minimal GDAL footprint that omits many optional format drivers, including the FileGDB driver. `fiona.listlayers("NAD_r21.gdb")` raises `DriverError: unsupported driver` silently or with a cryptic GDAL error. The proprietary ESRI FileGDB API SDK is NOT included in any pre-built wheel.

**Why it happens:** The fiona documentation mentions FileGDB support but does not prominently note that the PyPI wheel excludes it. The error messages from GDAL are not beginner-friendly ("Failed to open dataset").

**How to avoid:**
- For Docker-based deployment: install `gdal-bin` and `python3-gdal` (or equivalent) via the system package manager before `uv add fiona`. This gives fiona a system GDAL with the OpenFileGDB driver.
- Alternatively: use `uv pip install --no-binary fiona fiona` to build from source (requires GDAL headers and `libgdal-dev`).
- In `Dockerfile`, add GDAL system packages before the Python dependencies step.
- The OpenFileGDB driver (open source, built into GDAL 3.6+) is sufficient for reading NAD FGDB files — you do NOT need the proprietary ESRI FileGDB API SDK.
- Verify driver availability at startup: `'OpenFileGDB' in fiona.supported_drivers`.

**Warning signs:**
- `fiona.listlayers()` returns an empty list or raises `DriverError` on `.gdb` files.
- CI passes on developer machine (conda-forge install) but fails in Docker (PyPI wheel).
- `fiona.supported_drivers` does not contain `'OpenFileGDB'`.

**Phase to address:** Docker/infrastructure setup phase — before NAD FGDB provider is implemented. The Dockerfile must be updated to include GDAL system packages.

---

### Pitfall 8: Loading Large Local Datasets into Memory on Provider Init

**What goes wrong:** The OpenAddresses or NAD provider loads its entire dataset into memory at startup (e.g., `json.load(gzip.open("data/US_GA_Bibb_Addresses.geojson.gz"))`). A single geojson.gz for a large county can expand to 500MB–2GB in memory. The NAD TXT for a large state can be several GB uncompressed. With multiple providers loading at startup, the container OOM-kills or takes minutes to become available.

**Why it happens:** It's the simplest implementation — load the file, build an index, done. Memory implications are not obvious when testing with a small sample file.

**How to avoid:**
- For geojson.gz files: use `ijson` with `gzip.open()` to stream features one at a time rather than loading the full JSON tree. Pattern: `ijson.items(gzip.open(path, 'rb'), 'features.item')`.
- For large pipe-delimited files: use `csv.reader` or `pandas.read_csv(..., chunksize=10000)` to process in batches rather than `df = pd.read_csv(path)`.
- Build a spatial index (e.g., using `rtree` or PostGIS) at data-loading time rather than scanning the full dataset per request.
- For providers that query a database (Tiger), there is no in-memory loading issue — the data lives in PostgreSQL. Prefer the database-backed approach when datasets are large.

**Warning signs:**
- Provider `__init__` opens and fully reads a compressed file.
- Docker container memory usage exceeds 1GB before serving any requests.
- First request takes >10 seconds (startup I/O blocking the event loop).

**Phase to address:** OpenAddresses and NAD provider implementation phases.

---

### Pitfall 9: Synchronous File I/O Blocking the FastAPI Event Loop

**What goes wrong:** Local providers use Python's synchronous `open()`, `gzip.open()`, or `fiona.open()` in async methods that are called directly from the async event loop. Streaming a large geojson.gz (even with ijson) blocks the single event loop thread for the duration of the I/O, stalling all concurrent requests.

**Why it happens:** The `GeocodingProvider.geocode()` abstract method is `async`, which makes it easy to assume I/O inside it is non-blocking. But `gzip.open()` and standard file reads are synchronous C-level calls that do not yield to the event loop.

**How to avoid:**
- Wrap all file I/O in `asyncio.to_thread()` (Python 3.9+) or `loop.run_in_executor(None, blocking_fn)`.
- Pattern for a local provider: `result = await asyncio.to_thread(self._search_file, normalized_address)` where `_search_file` contains all synchronous file/fiona operations.
- Alternatively: pre-load the dataset into a spatial index at startup (synchronously, before the event loop is running) and serve lookups from the in-memory index during requests.
- For Tiger provider: PostGIS queries are already async via asyncpg — no blocking I/O concern.

**Warning signs:**
- `async def geocode()` contains `gzip.open()` or `fiona.open()` without `asyncio.to_thread()`.
- Request latency spikes to >1s even for simple queries when local providers are active.
- Event loop blocked warnings in uvicorn logs.

**Phase to address:** OpenAddresses and NAD provider implementation phases. Establish the pattern in the first local provider to be built.

---

### Pitfall 10: PostGIS Tiger Geocoder Missing Required Extensions in Docker

**What goes wrong:** The Tiger geocoder requires four extensions installed in a specific order: `postgis`, `fuzzystrmatch`, `postgis_tiger_geocoder`, `address_standardizer`. In the standard `postgis/postgis` Docker image, `postgis_tiger_geocoder` and `address_standardizer` are included as extension SQL files but may not be present in older or minimal image variants. Running `CREATE EXTENSION postgis_tiger_geocoder` fails with "extension not found."

**Why it happens:** The `postgis/postgis` Docker image ships PostGIS extensions, but the Tiger geocoder extension packaging is an optional extra. Different versions and base OS packages include or exclude it. Developers assume "PostGIS installed" means "Tiger geocoder available."

**How to avoid:**
- Use `postgis/postgis:17-3.5` (or current major version) which includes all Tiger extensions.
- Verify the extensions are present: `SELECT name FROM pg_available_extensions WHERE name LIKE 'postgis%' OR name LIKE 'address%' OR name = 'fuzzystrmatch';`
- Required installation order in `docker-entrypoint.sh` or Alembic migration:
  1. `CREATE EXTENSION IF NOT EXISTS postgis;`
  2. `CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;`
  3. `CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;`
  4. `CREATE EXTENSION IF NOT EXISTS address_standardizer;`
  5. `CREATE EXTENSION IF NOT EXISTS address_standardizer_data_us;`
- Make the Tiger provider optional (fails gracefully if the extension is not present) per the project requirement "works with or without pre-installed extension."

**Warning signs:**
- `CREATE EXTENSION postgis_tiger_geocoder` fails or the extension is not listed in `pg_available_extensions`.
- The Geo API starts successfully but Tiger lookups return `ProviderNetworkError` rather than a geocoding result.

**Phase to address:** Tiger provider setup phase — Docker configuration must be updated before the Tiger provider is implemented.

---

### Pitfall 11: Tiger Geocoder Returning No Results Because Tiger Data Is Not Loaded

**What goes wrong:** Extensions are installed successfully. The Tiger provider calls `SELECT * FROM geocode(...)`. It returns 0 rows. The developer debugs the provider code for hours before discovering that while the extension is installed, the actual TIGER/LINE census data (state/county geometry tables) was never loaded into the `tiger_data` schema.

**Why it happens:** The Tiger geocoder extension is separate from the Tiger data. Installing the extension provides the functions but not the reference data. This is poorly communicated in basic PostGIS documentation. Data loading requires running generated shell scripts that download ~1-2 GB per state from Census Bureau servers.

**How to avoid:**
- Document the data loading step explicitly and separately from extension installation.
- Provide a data loading script (Typer CLI command or shell script) that: generates the Tiger loader script via `SELECT Loader_Generate_Nation_Script(...)` and `Loader_Generate_Script(...)`, runs it, then calls `tiger.install_missing_indexes()` and `ANALYZE tiger_data.*`.
- For the Docker dev environment: include a pre-seeded or at-startup Tiger data load for at least one state (e.g., GA) to support local development.
- In the provider implementation: check whether Tiger data is loaded at startup via `SELECT count(*) FROM tiger_data.county` and log a clear warning if it returns 0 rows.

**Warning signs:**
- `SELECT * FROM geocode('123 Main St, Springfield, GA 31329', 1)` returns an empty result set.
- `SELECT count(*) FROM tiger_data.county` returns 0.
- Tiger provider returns NO_MATCH for every address.

**Phase to address:** Tiger provider phase — data loading step must be part of the setup scripts and documented clearly.

---

### Pitfall 12: Tiger Geocoder Rating Score Not Mapped to Confidence Float

**What goes wrong:** The Tiger `geocode()` function returns a `rating` score (lower is better, 0 is perfect, 100+ is poor). The provider maps this directly to the `GeocodingResult.confidence` field (which is a 0.0–1.0 float where higher is better). A rating of 20 becomes `confidence=20.0`, which is nonsensical and breaks any downstream logic that compares confidence across providers.

**Why it happens:** The Tiger rating scale is the inverse of the confidence scale used elsewhere in the system. The mapping is not obvious.

**How to avoid:**
- Convert Tiger rating to 0.0–1.0 confidence in the provider: `confidence = max(0.0, 1.0 - (rating / 100.0))`.
- A rating of 0 → confidence 1.0; rating of 20 → confidence 0.8; rating of 100+ → confidence 0.0 or clamped to a minimum.
- Document the mapping formula in the provider code.
- Treat rating > 20 as effectively NO_MATCH (confidence < 0.8) — the PostGIS documentation notes that ratings <= 20 indicate 97% of results are within 1km of the true location.

**Warning signs:**
- Tiger provider returns `confidence=20.0` or `confidence=5.0` for successful geocodes.
- Admin dashboard shows Tiger results with far higher confidence numbers than Census or other providers.

**Phase to address:** Tiger provider implementation phase.

---

### Pitfall 13: OpenAddresses Data Quality — Null/Missing Fields Not Defensively Handled

**What goes wrong:** OpenAddresses GeoJSON features have `number` and `street` as required fields per the schema, but `city`, `region`, `postcode`, and `unit` are optional and may be entirely absent from the `properties` dict (not null — simply not present). The provider assumes `feature['properties']['city']` exists and raises `KeyError`.

**Why it happens:** OpenAddresses aggregates from hundreds of government sources. Each source uses a different field set. The conform pipeline normalizes what it can but cannot invent missing data. Features from some sources have only `number`, `street`, and coordinates.

**How to avoid:**
- Always use `.get()` with a default for all optional properties: `props.get('city', '')`, `props.get('postcode', '')`.
- Validate that `number` and `street` are present and non-empty before including a feature in any index. A feature with `"number": ""` and `"street": ""` is useless for geocoding.
- Filter out features with no valid geometry (null coordinates, or coordinates outside the bounding box of the US).
- Log a counter of skipped/malformed features at INFO level during data loading.

**Warning signs:**
- `KeyError: 'city'` in provider logs during feature processing.
- Address matching returning results with empty city or state fields.

**Phase to address:** OpenAddresses provider implementation phase.

---

### Pitfall 14: NAD FGDB vs TXT Format — Picking the Wrong One for Production

**What goes wrong:** The project has both `NAD_r21_FGDB.zip` (~9.8GB) and `NAD_r21_TXT.zip` (~7.8GB). The FGDB format requires GDAL's OpenFileGDB driver (see Pitfall 7) but preserves the full geometry (point coordinates). The TXT (pipe-delimited) format contains the same address data with `Latitude` and `Longitude` columns but requires more defensive parsing.

The NAD TXT schema has fields including: `AddNum_Pre`, `Add_Number`, `AddNum_Suf`, `St_PreMod`, `St_PreDir`, `St_PreTyp`, `St_PreSep`, `St_Name`, `St_PosTyp`, `St_PosDir`, `St_PosQuad`, `Unit`, `Floor`, `Building`, `Room`, `Seat`, `Addtl_Loc`, `SubAddress`, `LandmkName`, `County`, `Inc_Muni`, `Post_City`, `State`, `Zip_Code`, `Plus4`, `Latitude`, `Longitude`, `UUID`.

**Why it happens:** Both formats are available; developers pick FGDB assuming it is "more spatial" but encounter GDAL driver issues. Or they pick TXT and misparse the pipe-delimited file by assuming column order rather than using headers.

**How to avoid:**
- For the NAD provider, prefer the TXT format for portability — no GDAL dependency, simpler deployment, coordinates already present as columns.
- Always parse by header name, not column index: `csv.DictReader(f, delimiter='|')`.
- If FGDB is used for richer attribute access, ensure the Docker image has the OpenFileGDB driver verified at startup.
- When using the TXT format, handle `Latitude` and `Longitude` columns as floats. Rows with non-numeric or empty coordinates must be skipped.

**Warning signs:**
- Provider code uses `row[25]` (positional index) instead of `row['Latitude']`.
- FGDB-based provider fails in Docker CI but works in the developer's conda environment.

**Phase to address:** NAD provider implementation phase. Make the format choice explicit in the phase plan.

---

### Pitfall 15: Address Matching Logic Assumes Exact String Equality

**What goes wrong:** The local provider receives a normalized address string (e.g., `"123 MAIN ST, MACON, GA 31201"`) and tries to find it in the OpenAddresses or NAD dataset by exact string comparison against a concatenated field. Real-world data has abbreviation mismatches: the dataset says `"MAIN STREET"` but the input is `"MAIN ST"`. Or the dataset has `"AVE"` but the input says `"AVENUE"`. The provider returns NO_MATCH even though an identical-location record exists.

**Why it happens:** The incoming address is normalized to USPS abbreviations by `scourgify`, but the source data (especially OpenAddresses from raw government sources) may use full spellings, different casing, or local abbreviation conventions.

**How to avoid:**
- Decompose the normalized address into components (`street_number`, `street_name`, `street_type`, `city`, `state`, `zip_code`) before matching rather than comparing full strings.
- Match against individual components with USPS-abbreviation normalization applied to both sides.
- For `street_name`: apply the same normalization to the dataset at load time and to the query at lookup time — both reduce `"MAIN STREET"` to `"MAIN ST"`.
- Do not implement fuzzy string matching at this stage — it adds complexity and the normalized USPS form should handle the common variants. Log failed matches that could benefit from fuzzy matching for future analysis.

**Warning signs:**
- Provider returns NO_MATCH for addresses that are clearly in the dataset (visually identical when printed).
- Match rate in testing is below 60% for a set of well-formed addresses.

**Phase to address:** OpenAddresses and NAD provider implementation phases. Establish matching strategy before implementing the search function.

---

### Pitfall 16: Tiger Data Loading on Docker Startup Breaks the Dev Environment

**What goes wrong:** A `docker-entrypoint.sh` script or similar init mechanism attempts to download and load Tiger data at container startup. Tiger data is 1-2 GB per state. On a slow connection, or with a fresh `docker compose up`, the API container waits indefinitely or times out. Docker health checks fail. Developers cannot run the dev environment without downloading gigabytes.

**Why it happens:** It seems convenient to make data loading automatic. The data volume of Tiger is underestimated.

**How to avoid:**
- Make Tiger data loading a separate, explicit CLI command (`uv run cli load-tiger --state GA`) — not automatic on startup.
- The Tiger provider should check for data presence at startup and degrade gracefully with a clear log message if no Tiger data is loaded: `logger.warning("Tiger geocoder: no census data loaded; provider will return NO_MATCH")`.
- For the Docker dev environment, provide an optional `make load-tiger-ga` or similar target for developers who want Tiger geocoding locally.
- Never download external data (Census FTP) as part of container startup.

**Warning signs:**
- `docker-entrypoint.sh` contains `wget` or `curl` calls to Census Bureau FTP.
- `docker compose up` takes >5 minutes on first run.
- Container startup fails intermittently (network timeouts during data download).

**Phase to address:** Tiger setup scripts phase. Establish the "optional, explicit, CLI-driven" pattern for all large data loading operations.

---

## Moderate Pitfalls

---

### Pitfall 17: No Idempotency in Batch Endpoints

**What goes wrong:** A batch of 500 addresses is submitted. After 300 are processed, the external service rate-limits or returns an error. The batch is retried from the beginning. Services are called again for the 300 already completed.

**How to avoid:**
- Treat batch jobs as a collection of independent lookups, not a monolithic transaction.
- For each address in a batch: check cache first; skip the external call if cached. This makes retries nearly free.
- Use a per-item status in the batch response: `{"status": "cached" | "fetched" | "error", ...}`.

**Phase to address:** Batch endpoint design (Phase 2 / v1.0 — already implemented).

---

### Pitfall 18: Local Provider Registered in the Cached Pipeline Registry

Expanded version of Pitfall 6 for the integration-layer detail.

**What goes wrong:** `main.py` passes all providers to `GeocodingService.geocode()`. The pipeline upserts every provider result to `geocoding_results`. If `"openaddresses"` is in `app.state.providers`, every geocoding request attempts to write an OpenAddresses result row, even for addresses where the local data has no match. At scale this creates millions of rows with `confidence=0.0` (NO_MATCH) in the cache.

**How to avoid:**
- Keep `app.state.providers` exclusively for cacheable (remote API) providers.
- Introduce `app.state.local_providers` (or equivalent) for direct-return local providers.
- The geocoding endpoint routes to the appropriate registry based on request parameters or config.

**Phase to address:** First phase of v1.1 (provider pipeline refactor).

---

### Pitfall 19: Admin Override OfficialGeocoding Pointing at a Local Provider Result

**What goes wrong:** A local provider result (OpenAddresses, NAD) is returned to the API caller. Because local providers bypass the DB cache, the result has no `geocoding_result_id` in the database. If the caller then tries `PUT /geocode/{hash}/official` with the local result ID, the endpoint returns 404 because the result was never written to `geocoding_results`. The admin cannot set an official result based on a local provider hit.

**Why it happens:** Local provider results are ephemeral (returned directly, not stored). The existing `set_official` flow expects a `geocoding_result_id` that references a real database row.

**How to avoid:**
- Document clearly: local provider results cannot be set as official via `geocoding_result_id`. Admins must use the `latitude`/`longitude` path instead to create an admin_override from local data.
- In the API response for local providers, do not include a `geocoding_result_id` field (or explicitly set it null) to signal this limitation.
- Consider whether a "promote local result to DB" endpoint is needed — but defer this to v1.2.

**Phase to address:** v1.1 provider pipeline design.

---

### Pitfall 20: PostGIS SRID Mismatch Between Storage and Queries

**What goes wrong:** Coordinates are stored as SRID 4326 (WGS84), but a spatial query uses ST_DWithin with a distance in meters. ST_DWithin on a 4326 geometry interprets the distance in degrees, not meters. Results are silently wrong.

**How to avoid:**
- Use `Geography(Point, 4326)` (already done in this codebase — see `GeocodingResult.location`).
- Geography columns automatically interpret ST_DWithin distances as meters.
- For local spatial lookups (nearest address in OpenAddresses), use `ST_DWithin(geog_col::geography, query_point::geography, radius_meters)`.

**Phase to address:** Data model design (Phase 1 — already addressed).

---

### Pitfall 21: USPS API Dependency Without a Fallback

**What goes wrong:** USPS address validation is the sole normalization source. USPS's free Addresses API has been periodically sunset, migrated, and rate-limited. When USPS is unavailable, address validation fails entirely.

**How to avoid:**
- USPS should be the preferred validation source, but the plugin architecture should allow fallback to a USPS-format normalization library (`scourgify`, `usaddress-scourgify`) for format standardization without hitting USPS.

**Phase to address:** Service adapter design (Phase 1/2 — already addressed in v1.0).

---

## Minor Pitfalls

---

### Pitfall 22: Batch Endpoint Returns All-or-Nothing HTTP Status

**What goes wrong:** A batch of 50 addresses is submitted. 48 succeed, 2 fail. The endpoint returns HTTP 500 because not all succeeded. The caller retries all 50.

**How to avoid:**
- Batch endpoints always return HTTP 200 with per-item status in the response body.
- HTTP 4xx/5xx reserved for request-level failures (malformed JSON, DB unreachable).

**Phase to address:** Batch endpoint design (v1.0 — already implemented).

---

### Pitfall 23: Treating PO Boxes, Rural Routes, and Military Addresses as Edge Cases

**What goes wrong:** Normalization and validation logic is built for standard street addresses. PO Box, RR (Rural Route), HC (Highway Contract), APO/FPO/DPO (military) addresses are structurally different. Parser misclassifies, normalization produces garbage.

**How to avoid:**
- Add explicit test cases for: `PO BOX 123`, `RR 2 BOX 45`, `HC 1 BOX 12`, `PSC 3 BOX 1234 APO AE 09021`.
- Local providers (OpenAddresses, NAD) typically do not contain PO Boxes — document this as a known gap and fall through to Census or USPS.

**Phase to address:** Address normalization (Phase 1/2 — known from v1.0 research).

---

### Pitfall 24: Plugin Architecture Requires Restart to Add a New Local Provider

**What goes wrong:** Each provider is hardcoded in `main.py`. Adding a new local data file or a new state's OpenAddresses data requires a code change and redeploy.

**How to avoid:**
- Configuration-driven provider loading: read data file paths from `settings` (pydantic-settings). Adding a new file = updating `.env`, not touching `main.py`.
- The OpenAddresses provider should be file-path-configurable rather than hardcoded to a specific filename.

**Phase to address:** Provider architecture — establish during OpenAddresses provider phase.

---

### Pitfall 25: OpenAddresses File Discovery — Handling Multiple .geojson.gz Files

**What goes wrong:** The `data/` directory contains multiple `.geojson.gz` files (Bibb county addresses, Bibb county parcels, a full US-south collection). The OpenAddresses provider naively scans all `.geojson.gz` files in the directory, including parcel files that have a different property schema. Parcel features do not have `number`/`street` fields and the provider silently skips all features with a warning flood.

**Why it happens:** The `data/` directory is used for multiple file types. The provider pattern is "scan directory for matching extension."

**How to avoid:**
- Use a naming convention to distinguish address files from parcel files: `*_Addresses_*.geojson.gz` vs. `*_Parcels_*.geojson.gz`.
- Configure the OpenAddresses provider with explicit file globs (e.g., `OPENADDRESSES_GLOB=data/*_Addresses_*.geojson.gz`) rather than scanning everything.
- At load time, validate that at least one feature in each file has `number` and `street` fields before indexing the full file.

**Warning signs:**
- Provider logs show "skipping feature: missing required field" thousands of times.
- Provider loads in 0.1 seconds and returns NO_MATCH for everything (parsed a parcel file).

**Phase to address:** OpenAddresses provider implementation phase.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Load full geojson.gz into memory | Simple implementation | OOM kills for large files; slow startup | Only for development with small sample files |
| Scan all `.geojson.gz` in `data/` without filtering | Zero config | Parcel/non-address files cause silent mismatches | Never in production |
| Register local providers in the cached pipeline | Reuse existing pipeline | DB bloat with NO_MATCH rows; cache semantics broken | Never |
| Skip `asyncio.to_thread()` for file I/O | Simpler async code | Event loop stalls on large file reads | Never in production |
| Hard-code Tiger data loading in Docker startup | Automatic setup | Docker startup takes 30+ minutes, CI timeouts | Never |
| Use column index instead of header name for NAD TXT | Marginally faster | Breaks silently if column order changes between NAD releases | Never |

---

## Integration Gotchas

Common mistakes when integrating local data sources.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenAddresses geojson.gz | `json.load(gzip.open(path))` — full load | `ijson.items(gzip.open(path, 'rb'), 'features.item')` — streaming |
| NAD TXT (pipe-delimited) | `csv.reader(f)` with positional column index | `csv.DictReader(f, delimiter='|')` with named keys |
| NAD FGDB | `fiona.open(path)` without checking driver availability | Check `'OpenFileGDB' in fiona.supported_drivers` at startup; install GDAL system package in Docker |
| PostGIS Tiger extensions | Install `postgis_tiger_geocoder` without `fuzzystrmatch` first | Install in order: postgis → fuzzystrmatch → postgis_tiger_geocoder → address_standardizer |
| Tiger data | Assume installed extensions = loaded data | Verify `SELECT count(*) FROM tiger_data.county > 0` before serving Tiger requests |
| Tiger rating | Pass raw rating (0-100+) as confidence | Convert: `confidence = max(0.0, 1.0 - rating / 100.0)` |
| Provider pipeline | Register local providers in `app.state.providers` | Use a separate registry for local/direct-return providers |
| All local providers | Call blocking I/O directly in `async def geocode()` | Wrap in `asyncio.to_thread()` or pre-build in-memory index at startup |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full in-memory geojson.gz load | OOM at startup; minutes to first request | Stream with ijson; build spatial index | Files > 200MB |
| Linear scan of in-memory address list per lookup | <1ms per lookup at 1K addresses; >10s at 1M | Build normalized-key dictionary index at load time | Index > ~100K addresses |
| Tiger data loading in container startup | 30+ minute `docker compose up`; CI timeouts | CLI-driven data loading, provider degrades gracefully | Every startup |
| NAD full nationwide TXT file load | 10+ GB uncompressed; swap thrashing | Load only needed states; filter at ingest | Nationwide dataset |
| Local providers in cached pipeline | Millions of NO_MATCH rows in `geocoding_results` | Separate direct-return pipeline | First production deployment |
| Unindexed Tiger geocoder queries | Queries return correct results but take 30+ seconds | Run `tiger.install_missing_indexes()` and `ANALYZE` after data load | After any data load |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **OpenAddresses provider:** Data file loads without error — verify `number` and `street` are non-empty for sampled features and that parcel files are excluded.
- [ ] **NAD provider:** Reads first row correctly — verify all 100K+ rows parse without `KeyError`, empty coordinates are skipped, and headers are used (not column index).
- [ ] **Tiger provider:** `geocode()` returns results — verify Tiger data is actually loaded (`SELECT count(*) FROM tiger_data.county > 0`), rating is converted to confidence float, all required extensions installed.
- [ ] **Local provider pipeline:** Providers registered — verify local providers are NOT in `app.state.providers` and that geocoding requests do NOT write local results to `geocoding_results`.
- [ ] **Fiona FGDB:** `fiona.open()` works locally — verify `'OpenFileGDB' in fiona.supported_drivers` passes in Docker (not just on dev machine).
- [ ] **Tiger extensions:** `CREATE EXTENSION postgis_tiger_geocoder` succeeds — verify with `SELECT postgis_tiger_version()`.
- [ ] **All local providers:** `geocode()` returns correct type — verify `GeocodingResult` confidence is a 0.0–1.0 float (not a raw Tiger rating or some other scale).
- [ ] **Async safety:** Provider passes manual test — verify that a concurrent 10-request batch does not show event loop stall warnings when local providers handle file I/O.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Local provider accidentally wrote to geocoding_results | MEDIUM | `DELETE FROM geocoding_results WHERE provider_name IN ('openaddresses', 'nad', 'tiger');` then `VACUUM ANALYZE geocoding_results;` |
| Fiona driver failure in production Docker | LOW | Add `libgdal-dev` to Dockerfile, rebuild image, redeploy |
| Tiger data not loaded (provider returns all NO_MATCH) | LOW | Run `uv run cli load-tiger --state GA` (or equivalent); no code changes needed |
| In-memory OOM from large geojson.gz load | LOW-MEDIUM | Switch from `json.load` to `ijson` streaming; restart container |
| Event loop blocking from synchronous file I/O | LOW | Wrap I/O in `asyncio.to_thread()`; test under load before re-deploying |
| Tiger rating not converted to confidence | LOW | Fix formula in provider; existing test data is unaffected (no DB writes) |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Local providers writing to cache (P6, P18) | Phase 1: Provider pipeline refactor | Integration test asserts `geocoding_results` not touched by local provider call |
| Fiona GDAL driver missing (P7) | Phase 1: Docker infrastructure update | `docker compose run api python -c "import fiona; assert 'OpenFileGDB' in fiona.supported_drivers"` |
| Large dataset in-memory load (P8) | Phase 2: OpenAddresses provider | Memory profiling shows startup < 500MB |
| Blocking file I/O in async context (P9) | Phase 2: OpenAddresses provider | 10-concurrent-request test shows < 2s p99 latency |
| Tiger extensions missing (P10) | Phase 3: Tiger Docker setup | `SELECT postgis_tiger_version()` returns a version string |
| Tiger data not loaded (P11) | Phase 3: Tiger data loading scripts | `SELECT count(*) FROM tiger_data.county > 0` |
| Tiger rating not mapped (P12) | Phase 3: Tiger provider implementation | Unit test asserts `confidence` for a rating=20 result equals 0.8 |
| OpenAddresses null fields (P13) | Phase 2: OpenAddresses provider | Provider handles features with missing `city`/`postcode`/`unit` without `KeyError` |
| NAD format selection (P14) | Phase 4: NAD provider | Documented in NAD provider phase plan; format choice explicit |
| Address matching exact-string failure (P15) | Phase 2 and 4 | Matching test suite: known addresses in dataset return > 80% match rate |
| Tiger data loading breaking Docker (P16) | Phase 3: Tiger setup scripts | `docker compose up` completes in < 30 seconds; data loading is a separate CLI step |
| OpenAddresses file discovery (P25) | Phase 2: OpenAddresses provider | Provider config uses explicit glob; parcel files excluded from address index |

---

## Sources

- [PostGIS Tiger Geocoder Cheatsheet](https://postgis.net/docs/manual-3.6/tiger_geocoder_cheatsheet-en.html) — MEDIUM confidence; official PostGIS docs
- [Setup Geocoder with PostGIS and Tiger/LINE — RustProof Labs](https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup) — HIGH confidence; hands-on walkthrough with timing data
- [Create Your Own Geocoder with PostGIS/TIGER — DEV Community](https://dev.to/cincybc/create-your-own-geocoder-with-postgistiger-3anc) — MEDIUM confidence
- [PostGIS Extras — Chapter 12](https://postgis.net/docs/Extras.html) — HIGH confidence; official PostGIS docs
- [Processing large JSON files in Python without running out of memory — Python Speed](https://pythonspeed.com/articles/json-memory-streaming/) — HIGH confidence; well-researched article
- [Huge memory usage when opening geojson file — Fiona Issue #624](https://github.com/Toblerity/Fiona/issues/624) — HIGH confidence; upstream issue confirming the problem
- [Reading FileGDB with Fiona — Issue #698](https://github.com/Toblerity/Fiona/issues/698) — HIGH confidence; confirms PyPI wheel FileGDB limitations
- [Fiona installation documentation](https://fiona.readthedocs.io/en/latest/install.html) — HIGH confidence; official docs
- [OpenAddresses address_conform.json schema](https://github.com/openaddresses/openaddresses/blob/master/schema/layers/address_conform.json) — HIGH confidence; upstream schema definition
- [National Address Database — data.gov](https://catalog.data.gov/dataset/national-address-database-nad-text-file) — HIGH confidence; official DOT dataset page
- [FastAPI async/blocking I/O documentation](https://fastapi.tiangolo.com/async/) — HIGH confidence; official FastAPI docs
- [asyncio.to_thread — Python docs](https://docs.python.org/3/library/asyncio-task.html) — HIGH confidence; official Python docs
- [ijson — PyPI](https://pypi.org/project/ijson/) — HIGH confidence; official package page confirming async support
- v1.0 research (training data, knowledge cutoff August 2025) — MEDIUM confidence for v1.0 pitfalls

---
*Pitfalls research for: CivPulse Geo API — local data source providers (OpenAddresses, NAD, PostGIS Tiger)*
*Researched: 2026-03-20 (v1.1 milestone)*
