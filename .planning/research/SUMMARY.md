# Project Research Summary

**Project:** CivPulse Geo API — v1.1 Local Data Source Providers
**Domain:** Local geocoding and address validation provider integration
**Researched:** 2026-03-20
**Confidence:** HIGH — all findings verified against actual data files and live codebase

## Executive Summary

The v1.1 milestone adds three local geocoding data source providers (OpenAddresses, NAD, PostGIS Tiger) to the existing CivPulse Geo API plugin architecture. All three providers implement the existing `GeocodingProvider` and `ValidationProvider` ABCs, and all three share a critical behavioral constraint: results bypass DB caching entirely and are returned directly to callers. This "direct-return pipeline" is not a nice-to-have — it is an explicitly stated requirement in PROJECT.md and the correct architectural response to the fact that local data is already on-disk and caching it would create staleness and write overhead with no benefit.

The core implementation challenge is scale. NAD r21 is 35.8 GB uncompressed (~80M rows) and cannot be scanned at query time under any circumstance. OpenAddresses county files are small enough for in-memory dev use, but production deployments with multi-state coverage require PostGIS import. The PostGIS Tiger geocoder requires both extension installation and a separate TIGER/LINE data loading step — and must degrade gracefully when data is absent. All three providers must be backed by PostGIS staging tables and queried via indexed SQL, not by file I/O at request time.

No new Python libraries are required. The entire implementation fits within the existing dependency footprint: stdlib `gzip` + `json` for OpenAddresses streaming at load time, stdlib `csv` + `zipfile` for NAD streaming at load time, `fiona` (already installed at 1.10.1) for NAD FGDB if needed, `usaddress` (already locked as a transitive dep) for address component parsing, and `sqlalchemy.text()` + `asyncpg` (already in use) for Tiger SQL function calls. The key risks are architectural: accidentally routing local providers through the cached pipeline (causes DB bloat), blocking the async event loop with synchronous file I/O, and not handling Tiger's optional data presence gracefully.

---

## Key Findings

### Recommended Stack

The v1.1 stack is entirely additive within the existing dependency footprint. No new packages are required in `pyproject.toml`. The critical insight from stack research is that each data source maps to capabilities already installed: GeoJSONL streaming to stdlib, CSV streaming to stdlib, Esri FGDB to `fiona`'s OpenFileGDB driver (confirmed present in project venv), and Tiger geocoding to PostGIS via the existing async SQLAlchemy session.

See `.planning/research/STACK.md` for full version table and "What NOT to Add" rationale.

**Core technologies:**
- `gzip` + `json` (stdlib): Stream OpenAddresses `.geojson.gz` NDJSON files line-by-line at load time — `json.load()` raises `JSONDecodeError` on these files; only `json.loads(line)` works
- `csv.DictReader` + `zipfile` (stdlib): Stream NAD `NAD_r21.txt` with `utf-8-sig` encoding directly from inside the zip — do not extract the 35.8 GB file before reading
- `fiona` 1.10.1 (already installed): OpenFileGDB driver confirmed present in project venv — use TXT over FGDB for the runtime provider (TXT is streamable in-zip; FGDB requires extraction)
- `usaddress` 0.5.16 (transitive dep, already in `uv.lock`): Address component decomposition before field-matching — do not add to `pyproject.toml`
- `sqlalchemy.text()` + `asyncpg` (already installed): Tiger geocoder SQL function calls via existing async session — extract coordinates with `ST_X`/`ST_Y` in SQL to avoid WKB parsing
- PostGIS `geography(POINT,4326)` (existing pattern): Storage type for both new staging tables — consistent with existing schema; ST_DWithin distances interpreted as meters automatically

---

### Expected Features

The feature set is tightly scoped to three provider pairs and the service-layer changes needed to support them.

See `.planning/research/FEATURES.md` for full feature table, dependency graph, provider behavior reference, and confidence/location_type mapping tables.

**Must have (v1.1 table stakes):**
- OpenAddresses geocoding + validation provider — data files present; county-level files support dev use immediately
- NAD import CLI command — required before NAD provider can function; streams 80M rows in 50K-row COPY batches
- NAD geocoding + validation provider — PostGIS table query with (state, zip_code, street_name) B-tree index
- PostGIS Tiger geocoder provider — SQL function call via existing async session; graceful failure when Tiger data not loaded
- PostGIS Tiger validation provider — `normalize_address()` uses bundled lookup tables, always available when extension is installed
- Direct-return pipeline (no DB caching for local providers) — `is_local` property on provider ABC; service layer bypass path
- `location_type` + `confidence` mapping per provider — verified against actual data field schemas
- `delivery_point_verified = False` for all three providers — none have USPS DPV data

**Should have (production readiness, P2):**
- Optional Tiger setup scripts — explicit CLI command, never automatic at container startup
- OpenAddresses PostGIS import CLI — for full-state or national coverage beyond dev county files
- Configuration-driven provider file paths — `OPENADDRESSES_GLOB` setting avoids hardcoded filenames and parcel file confusion

**Defer (v2+):**
- OpenAddresses incremental data refresh — trigger only when data staleness becomes an operational issue
- NAD table partitioning by state — defer until query latency exceeds acceptable threshold
- Reverse geocoding via Tiger `Reverse_Geocode()` — explicitly out of scope in PROJECT.md v1
- `delivery_point_verified = True` for any local provider — requires USPS DPV source not present in any of these datasets

---

### Architecture Approach

The architecture is a minimal, backward-compatible extension of the existing plugin system. The `GeocodingProvider` and `ValidationProvider` ABCs gain a single `is_local` property (default `False`) to signal bypass routing. `GeocodingService.geocode()` and `ValidationService.validate()` gain a split: local providers are called and collected without DB writes; remote providers use the existing cache-first pipeline unchanged. The response merges both result sets. Two new PostGIS staging tables (`openaddresses_points`, `nad_points`) are added via Alembic migrations with spatial GIST indexes. Three new provider files mirror the existing one-file-per-provider pattern.

See `.planning/research/ARCHITECTURE.md` for full component table, staging table DDL, data flow diagrams, and the 10-step recommended build order.

**Major components:**
1. `providers/base.py` modification — add `is_local` property with default `False`; backward-compatible; all existing providers inherit `False`
2. `services/geocoding.py` + `services/validation.py` modification — local provider bypass path; cache check scoped to remote-only providers; response merges local + remote result sets
3. `providers/openaddresses.py` (new) — `OAGeocodingProvider` + `OAValidationProvider` querying `openaddresses_points` PostGIS table; `source_hash` dedup on re-load
4. `providers/nad.py` (new) — `NADGeocodingProvider` + `NADValidationProvider` querying `nad_points` PostGIS table; ILIKE street name matching
5. `providers/tiger.py` (new) — `TigerGeocodingProvider` + `TigerValidationProvider` calling Tiger SQL functions; conditional registration at startup based on `pg_extension` check
6. `cli/commands.py` (new) — `load-oa`, `load-nad`, `setup-tiger` Typer commands; data loading is CLI-only, never API-triggered or container-startup-triggered
7. `models/local_sources.py` (new) — `OpenAddressesPoint`, `NADPoint` ORM models for read-only staging tables
8. Alembic migrations — `openaddresses_points` and `nad_points` tables with GIST indexes (spatial indexes must be written manually; Alembic autogenerate does not emit them)

---

### Critical Pitfalls

The following pitfalls are the highest-consequence mistakes for this milestone, verified against the codebase.

See `.planning/research/PITFALLS.md` for the full 25-pitfall catalog with phase mapping and recovery strategies.

1. **Local providers accidentally writing to the provider cache (Pitfalls 6, 18)** — Introduce `is_local` property before implementing any provider. Service layer must check it before calling `_upsert_geocoding_result()`. Integration tests must assert `geocoding_results` is NOT touched by local provider calls. Registering local providers in `app.state.providers` alongside `CensusGeocodingProvider` is the single most likely architectural mistake.

2. **Synchronous file I/O blocking the async event loop (Pitfall 9)** — All file I/O in provider `geocode()` methods must be wrapped in `asyncio.to_thread()`. The ABC is async but `gzip.open()` and `csv.DictReader` are blocking C-level calls. Establish this pattern in the first local provider built; subsequent providers follow automatically.

3. **Loading large datasets into application memory at provider init (Pitfall 8)** — OpenAddresses and NAD data must be loaded into PostGIS staging tables via CLI, not held in application memory. Loading NAD (35.8 GB uncompressed / ~80M rows) into memory is not feasible on any deployment.

4. **Tiger data not loaded even though extension is installed (Pitfall 11)** — Extension installation and data loading are two separate steps. At startup, check `SELECT count(*) FROM tiger_data.county > 0` and log a clear warning if empty. Provider must return `confidence=0.0` / NO_MATCH gracefully, not crash. Tiger data loading must be a separate CLI command, never automatic at container startup.

5. **Tiger rating not converted to confidence float (Pitfall 12)** — Tiger `rating` is 0–100+ where lower is better; `GeocodingResult.confidence` is 0.0–1.0 where higher is better. Apply `max(0.0, 1.0 - rating / 100.0)` in the provider. A raw rating of `20` must not appear as `confidence=20.0`.

---

## Implications for Roadmap

The dependency graph and pitfall-phase mapping from research suggest a 4-phase structure. The ordering is driven by two constraints: the `is_local` service bypass must exist before any local provider is wired up, and PostGIS staging tables must exist before provider query logic is written. All other phases follow naturally from data complexity (smallest to largest) and implementation novelty (PostGIS table queries before SQL function calls, SQL function calls before bulk 80M-row loading).

---

### Phase 1: Provider Pipeline Refactor and Staging Table Infrastructure

**Rationale:** The architectural boundary between local and remote providers must be established before any local provider is implemented. Registering local providers in the cached pipeline is the highest-risk mistake (Pitfalls 6 and 18) and cannot be retrofitted easily once other phases are built on top of it. Alembic migrations for staging tables must also precede all provider query work.

**Delivers:** `is_local` property on provider ABCs (default `False`, backward-compatible), service-layer bypass path in `GeocodingService` and `ValidationService`, `openaddresses_points` and `nad_points` staging tables with GIST + B-tree indexes, Docker GDAL package verification (`'OpenFileGDB' in fiona.supported_drivers`), `load_geojson_lines()` NDJSON streaming parser in `cli/parsers.py`

**Addresses:** Direct-return pipeline requirement

**Avoids:** Pitfalls 6 (accidental cache writes), 18 (wrong registry), 7 (GDAL driver missing in Docker), 2 (FLOAT columns instead of geography — staging tables use `geography(POINT,4326)` from day one)

**Research flag:** Standard patterns — well-understood SQLAlchemy, Alembic, and PostGIS work; no phase research needed

---

### Phase 2: OpenAddresses Provider

**Rationale:** OpenAddresses county files are small (the Bibb county file is tiny) and provide fast end-to-end feedback on the full provider pattern. Build and validate the NDJSON streaming loader, PostGIS COPY load command, and provider query pattern here before tackling NAD's scale. Establishes the `asyncio.to_thread()` file I/O pattern and explicit file glob configuration for all subsequent providers.

**Delivers:** `load-oa` CLI command (NDJSON streaming → 10K-row COPY batches → `openaddresses_points`), `OAGeocodingProvider`, `OAValidationProvider`, `location_type` mapping from `accuracy` field, `confidence` mapping per `accuracy` value, `source_hash` dedup logic

**Addresses:** OpenAddresses geocode + validate (P1 features)

**Avoids:** Pitfalls 8 (in-memory load), 9 (blocking I/O), 13 (null/missing OA field handling — use `.get()` with defaults), 15 (exact-string matching — decompose to components before querying), 25 (parcel file discovery — configure with explicit glob `*_Addresses_*.geojson.gz`)

**Research flag:** Standard patterns — NDJSON streaming and PostgreSQL COPY are well-documented with verified data schemas from on-disk files; no phase research needed

---

### Phase 3: PostGIS Tiger Provider

**Rationale:** Tiger comes before NAD in build order because the Tiger provider is the most architecturally distinct (SQL function call vs table query, conditional registration, multi-extension dependency chain) and the most failure-prone (optional extension + optional data + rating-to-confidence inversion). Tackling Tiger while the codebase is clean reduces risk. The Tiger validation provider also provides useful functionality independently of Tiger data being loaded.

**Delivers:** `TigerGeocodingProvider`, `TigerValidationProvider`, startup extension check + conditional provider registration with warning log, `setup-tiger` CLI command, Tiger extension installation order documented, rating-to-confidence conversion (`max(0.0, 1.0 - rating / 100.0)`)

**Addresses:** Tiger geocode + validate providers (P1 features), optional Tiger setup scripts (P2)

**Avoids:** Pitfalls 10 (missing extensions — install in order: postgis → fuzzystrmatch → postgis_tiger_geocoder → address_standardizer), 11 (data not loaded — startup check + graceful NO_MATCH), 12 (rating mapping), 16 (Tiger data loading breaking Docker startup)

**Research flag:** Verify Tiger extension availability in `postgis/postgis:17-3.5` Docker image at the start of this phase — research was MEDIUM confidence on exact image contents. Run `SELECT name FROM pg_available_extensions WHERE name LIKE 'postgis%' OR name LIKE 'address%' OR name = 'fuzzystrmatch'` before writing provider code.

---

### Phase 4: NAD Provider

**Rationale:** NAD is the most complex data loading task (~80M rows, estimated 20–40 min import, 50K-row COPY batches) but the query pattern mirrors what was already built and proven for OpenAddresses. Coming last means the staging table schema, provider ABC pattern, `asyncio.to_thread()` pattern, and service-layer bypass are all validated before tackling the scale challenge. Build order within this phase: import CLI first, then provider query logic.

**Delivers:** `load-nad` CLI command (streams `NAD_r21.txt` from inside zip → 50K-row COPY batches → `nad_points`), `NADGeocodingProvider`, `NADValidationProvider`, `location_type` mapping from `Placement` field, `confidence` mapping per `Placement` value, TXT format selection documented (prefer over FGDB: streamable in-zip, no extraction required)

**Addresses:** NAD geocode + validate + import CLI (P1 features)

**Avoids:** Pitfalls 8 (in-memory load — physically impossible at 35.8 GB), 14 (FGDB vs TXT format — TXT preferred), 15 (address matching — `StNam_Full` includes direction and type; parse to components before querying), column-index parsing (always use `csv.DictReader` with header names, not positional index)

**Research flag:** Standard patterns — CSV streaming and PostgreSQL COPY are well-documented; same patterns proven in Phase 2; no phase research needed

---

### Phase Ordering Rationale

- Phase 1 before everything: the `is_local` bypass must exist before any local provider touches the service layer. This is not optional — wiring a local provider into the existing pipeline before the bypass exists guarantees the accidental-cache-write failure mode.
- Phase 2 before Phase 4: OpenAddresses county-level files validate the full load-to-query pattern at manageable scale. Once the pattern is proven, NAD is mechanically the same at 100x the row count.
- Phase 3 before Phase 4: Tiger's SQL function call pattern is different enough from table queries to warrant proving it separately. If Phase 3 surfaces architectural changes to the provider ABC, NAD can incorporate them without rework.
- Phase 4 last: NAD's import time (20–40 min) makes iteration slow. Build on a proven foundation to minimize re-runs.

---

### Research Flags

Phases needing deeper research during planning:

- **Phase 3 (Tiger):** Verify Docker image extension contents. Research found MEDIUM confidence that `postgis/postgis:17-3.5` includes all five Tiger extensions — confirm before writing provider code.

Phases with standard patterns (skip research-phase):

- **Phase 1:** Alembic migrations with manual spatial indexes, SQLAlchemy ABC additions — well-established in this codebase
- **Phase 2:** NDJSON streaming, PostgreSQL COPY, PostGIS text queries — well-documented with schemas verified from on-disk files
- **Phase 4:** CSV streaming and PostgreSQL COPY — same patterns as Phase 2; field schema verified from on-disk data

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All findings verified against actual data files and project venv; `fiona` OpenFileGDB driver confirmed; `usaddress` confirmed in `uv.lock`; no new deps needed |
| Features | HIGH | Data schemas verified from on-disk files (`US_GA_Bibb_Addresses_2026-03-20.geojson.gz`, `NAD_r21_TXT.zip`); PostGIS function signatures from official docs; field domain values sampled from 500K-row NAD subset |
| Architecture | HIGH | Direct codebase inspection of `providers/base.py`, `services/geocoding.py`, `services/validation.py`, `providers/census.py`, `providers/scourgify.py`, `main.py`, `cli/parsers.py`; build order follows clear dependency graph |
| Pitfalls | MEDIUM-HIGH | v1.1 pitfalls web-verified and grounded in codebase inspection; v1.0 carry-over pitfalls from training data (MEDIUM). Tiger Docker image extension contents are the single remaining MEDIUM-confidence finding |

**Overall confidence:** HIGH

---

### Gaps to Address

- **Tiger Docker image contents:** Verify with `SELECT name FROM pg_available_extensions WHERE name LIKE 'postgis%' OR name LIKE 'address%' OR name = 'fuzzystrmatch'` in the Tiger phase before writing provider code. Research found MEDIUM confidence that all five extensions are present in `postgis/postgis:17-3.5`.
- **NAD FGDB vs TXT format decision:** Research recommends TXT for the runtime provider (streamable in-zip, no extraction required). Confirm this holds in the Phase 4 plan — if FGDB is ever needed, the Dockerfile must add GDAL system packages and the decision must be explicit.
- **Address match rate thresholds:** Research establishes scourgify pre-normalization + exact component matching as the strategy. Pitfall research flags a match rate below 60% as a warning sign. Measure match rate against a representative sample of known addresses during Phase 2 and revisit before Phase 4 NAD.
- **Tiger/LINE dev data:** National Tiger data is 1–2 GB per state. A dev-friendly pre-seeded single-state subset for Docker Compose local development is deferred to Tiger setup scripts in Phase 3 — an explicit decision on whether to bundle a minimal dataset is needed during Phase 3 planning.

---

## Sources

### Primary (HIGH confidence)
- `data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz` — confirmed GeoJSONL line-delimited format, full field schema
- `data/NAD_r21_TXT.zip/TXT/NAD_r21.txt` + `TXT/schema.ini` — confirmed 60-field CSV schema, `utf-8-sig` BOM encoding, field domain values sampled from 500K rows
- `data/collection-us-south.zip` — 3,054 files; path pattern `us/{state}/{county}-addresses-county.geojson` confirmed
- `fiona.supported_drivers` in project venv — `OpenFileGDB` driver confirmed present in fiona 1.10.1
- `uv.lock` — `usaddress==0.5.16` confirmed locked as transitive dependency
- Direct codebase inspection: `providers/base.py`, `services/geocoding.py`, `services/validation.py`, `providers/census.py`, `providers/scourgify.py`, `main.py`, `cli/parsers.py`
- [PostGIS geocode() function](https://postgis.net/docs/Geocode.html) — function signature, return type, rating scale
- [PostGIS Normalize_Address](https://postgis.net/docs/Normalize_Address.html) — validation without TIGER data
- [PostGIS Extras](https://postgis.net/docs/Extras.html) — Tiger geocoder overview, extension list
- [GDAL OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html) — no ESRI license required for read
- [NAD schema documentation](https://www.transportation.gov/sites/dot.gov/files/2023-07/NAD_Schema_202304.pdf) — 60-column definitions
- [OpenAddresses schema](https://github.com/openaddresses/openaddresses/blob/master/schema/layers/address_conform.json) — field semantics
- [FastAPI async/blocking I/O](https://fastapi.tiangolo.com/async/) — asyncio.to_thread() guidance
- [asyncio.to_thread Python docs](https://docs.python.org/3/library/asyncio-task.html) — official

### Secondary (MEDIUM confidence)
- [RustProof Labs Tiger setup](https://blog.rustprooflabs.com/2023/10/geocode-with-postgis-setup) — extension creation steps, timing data
- [postgis/docker-postgis](https://github.com/postgis/docker-postgis) — Tiger extension availability in official image
- [PostGIS Tiger Geocoder Cheatsheet](https://postgis.net/docs/manual-3.6/tiger_geocoder_cheatsheet-en.html) — function reference
- [ijson PyPI](https://pypi.org/project/ijson/) — streaming JSON; referenced in pitfalls but not required since OA files are NDJSON (not FeatureCollection)

### Tertiary (LOW confidence)
- v1.0 SUMMARY.md research (training data, knowledge cutoff August 2025) — v1.0 pitfall patterns; superseded by v1.1 web-verified research where they overlap

---
*Research completed: 2026-03-20*
*Ready for roadmap: yes*
