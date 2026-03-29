# Technology Stack

**Project:** CivPulse Geo API — v1.1 Local Data Source Providers
**Researched:** 2026-03-20
**Confidence:** HIGH — all findings verified against actual data files in `data/` and installed packages in the project virtualenv. Previous entries below the divider are preserved from v1.0 research.

---

## v1.2 Milestone: Stack Additions for Cascading Address Resolution

**Research date:** 2026-03-29
**Confidence:** HIGH (PostgreSQL extensions — official docs), HIGH (symspellpy — PyPI + official docs), MEDIUM (Ollama/LLM — community benchmarks), MEDIUM (consensus scoring — no standard library exists)

### Executive Finding

**Only one new Python library is required: `symspellpy`.** The Ollama Docker sidecar is infrastructure, not a Python dependency (called via existing `httpx`). PostgreSQL fuzzy/phonetic extensions are already bundled in the `postgis/postgis:17-3.5` Docker image. Consensus scoring is implemented with existing PostGIS spatial functions and Python stdlib.

---

### PostgreSQL Extensions (Fuzzy/Phonetic Matching)

Both extensions are bundled with the `postgis/postgis:17-3.5` Docker image as PostgreSQL contrib modules. No new Docker images, no apt installs, no version management.

| Extension | Setup | Purpose |
|-----------|-------|---------|
| `pg_trgm` | `CREATE EXTENSION IF NOT EXISTS pg_trgm;` | Trigram-based fuzzy string similarity for street name matching |
| `fuzzystrmatch` | `CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;` | Phonetic matching (Soundex, Metaphone, Double Metaphone, Levenshtein) |

**Note:** `fuzzystrmatch` is already created by the Tiger geocoder setup (v1.1). The `CREATE EXTENSION IF NOT EXISTS` form is idempotent — safe to call again in v1.2 migrations.

**Key functions by use case:**

| Use Case | Function / Operator | Notes |
|----------|---------------------|-------|
| "Does this street name approximately match?" | `word_similarity(query, street_name) > 0.5` with `<%` operator | Use `<%` operator, not `%`, to get index support |
| Ordered fuzzy results | `ORDER BY street_name <<-> query ASC` | Requires GiST index (not GIN) |
| Full address similarity | `similarity(a, b)` | Only for comparing two strings of equal length/scope |
| Phonetic match (English US street names) | `dmetaphone(s) = dmetaphone(q) OR dmetaphone_alt(s) = dmetaphone_alt(q)` | Covers alternate pronunciations ("Fischer" / "Fisher") |
| Edit distance ceiling | `levenshtein_less_equal(a, b, 3)` | Returns -1 if distance > max_d; cheaper than full `levenshtein()` |

**Why `word_similarity()` not `similarity()` for street matching:**
`similarity('elm', 'elm street macon ga 31201')` scores poorly because the query string is a tiny fraction of the target. `word_similarity('elm', 'elm street macon ga 31201')` finds the best matching continuous substring, returning a high score. This is the right function for matching a short street name query against a full address string.

**Why `dmetaphone()` not `soundex()` for phonetic matching:**
Soundex 4-char code space has extreme collisions for US street names — "Main" and "Macon" produce the same Soundex code. `dmetaphone()` returns longer codes with primary and alternate forms, dramatically reducing false positives.

**Index strategy:**
```sql
-- GIN for fast similarity threshold queries (WHERE word_similarity(...) > 0.5)
CREATE INDEX idx_street_gin ON addresses USING GIN (street_name gin_trgm_ops);

-- GiST when ORDER BY similarity score is needed
CREATE INDEX idx_street_gist ON addresses USING GIST (street_name gist_trgm_ops);

-- Functional index for phonetic matching
CREATE INDEX idx_street_dmetaphone ON addresses (dmetaphone(street_name));
```

**Threshold tuning guidance:**
- `pg_trgm.similarity_threshold` default: 0.3 — too loose for street names; raise to 0.5
- `pg_trgm.word_similarity_threshold` default: 0.6 — reasonable starting point
- Set per-session: `SET pg_trgm.word_similarity_threshold = 0.5;`

**Important encoding caveat:** `soundex`, `metaphone`, `dmetaphone`, and `dmetaphone_alt` do not work correctly with UTF-8 multibyte characters. US street names are ASCII-safe in practice — not a concern for this project, but document for future international work. `levenshtein` and `daitch_mokotoff` are safe with UTF-8.

---

### Python Spell Correction (Offline, Pre-Dispatch Layer)

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `symspellpy` | 6.9.0 | Address typo correction before provider dispatch | 1M+ words/second via Symmetric Delete algorithm. Supports `lookup_compound()` for multi-word correction of full address strings. Custom dictionary via `load_dictionary()` and `create_dictionary_entry()` — critical for loading US street names as high-frequency terms. Supports bigram dictionaries via `load_bigram_dictionary()` for multi-word street names ("Peachtree Battle" etc.). MIT license. Python 3.9–3.13. |

**Why not `pyspellchecker`:** Generates all Levenshtein permutations at lookup time — much slower. No compound/multi-word correction. Cannot bootstrap from a domain-specific address dictionary efficiently.

**Why not textblob / spaCy / nltk:** General-purpose NLP with heavy dependency chains. No custom domain dictionary appropriate for address correction. Overkill for this task.

**Integration pattern:**
```python
from symspellpy import SymSpell, Verbosity

sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
# Load general English frequency dictionary (bundled with symspellpy)
sym_spell.load_dictionary("frequency_dictionary_en_82_765.txt", term_index=0, count_index=1)
# Bootstrap with street names from local address data at startup
# High frequency count = symspellpy prefers these over general English words
sym_spell.create_dictionary_entry("peachtree", 50000)
sym_spell.create_dictionary_entry("forsyth", 50000)

# Multi-word correction for full address string
suggestions = sym_spell.lookup_compound("123 Peechtre St", max_edit_distance=2)
corrected = suggestions[0].term  # "123 peachtree st"
```

**Dictionary bootstrap at startup:** Query distinct street names from local address tables and inject as high-frequency entries. This primes symspellpy to prefer local street names over phonetically similar English words.

---

### LLM Sidecar (Last-Resort Address Correction)

This is the final fallback in the cascade — invoked only when deterministic methods (spell correction, fuzzy matching) cannot resolve an address.

| Technology | Version / Tag | Purpose | Why Recommended |
|------------|--------------|---------|-----------------|
| `ollama/ollama` (Docker image) | `latest` (pin digest in prod) | Serve small LLM as Docker Compose sidecar | Official image; sets `OLLAMA_HOST=0.0.0.0:11434` for inter-container access. Manages model storage, CPU/GPU detection automatically. REST API maps directly to existing httpx patterns. |
| `qwen2.5:3b` (model) | Q4_K_M quantized (~1.9 GB on disk, ~2.5 GB RAM) | Address correction and completion via structured JSON | Best instruction-following at 3B scale. Qwen2.5 was explicitly designed for structured JSON output as a primary goal. CPU-only inference: ~8–12 tok/s; first call after container start: 6–40s (model load); subsequent: 2–5s for short address strings. Acceptable for a tail-of-cascade fallback. |
| `ollama` (Python package) | 0.6.1 | Async client for Ollama; wraps `httpx.AsyncClient` | Matches existing httpx dependency; `AsyncClient` provides `await client.chat()`. Use only if raw httpx is insufficient (streaming, retry logic). For simple one-shot calls, raw httpx is preferred to avoid an extra dependency. |

**Why not `phi-3-mini:3.8b`:** Documented JSON schema compliance failures at 3.8B with strict schemas (empty results in outlines/guidance). Qwen2.5 was designed with JSON as an explicit target. phi-3-mini is also slightly larger.

**Why not `qwen2.5:7b`:** Requires ~4.5 GB RAM — 2x the 3B model for marginal gains on short address strings. Model upgrade is trivial (change one string); start with 3B.

**Why not `llama.cpp` directly:** Manual C++ build, GGUF file management, no model library. Ollama wraps all of this with an identical REST API.

**Why not `transformers` in-process:** Adds 2–3 GB to API process memory; inference blocks the async event loop without an explicit process pool; complex integration.

**Structured output via raw httpx (no additional dependency):**
```python
# Uses existing httpx.AsyncClient — zero new dependencies
response = await http_client.post(
    "http://ollama:11434/api/chat",
    json={
        "model": "qwen2.5:3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": AddressCorrectionResult.model_json_schema(),
    },
    timeout=30.0,
)
result = AddressCorrectionResult.model_validate_json(response.json()["message"]["content"])
```

**Docker Compose service:**
```yaml
ollama:
  image: ollama/ollama:latest
  volumes:
    - ollama_models:/root/.ollama
  environment:
    - OLLAMA_HOST=0.0.0.0:11434
  # No GPU required — CPU inference acceptable for fallback path

volumes:
  ollama_models:
```

**K8s / ArgoCD production consideration:** Use a PVC backed by the ZFS/NFS fileserver for model storage — `emptyDir` causes model re-download on every pod restart. Consider a dedicated Ollama Deployment + ClusterIP Service if multiple API pod replicas share the same model.

---

### Cross-Provider Consensus Scoring

No general-purpose Python library matches this domain. (VoteM8, CoVIRA, etc. are for molecular docking and bioinformatics.) Implement with existing dependencies — no new libraries needed.

**Approach: Weighted Spatial Agreement Score**

| Capability | Implementation | Existing Dependency |
|------------|---------------|---------------------|
| Coordinate distance between provider results | `ST_Distance(Geography, Geography)` returns meters | PostGIS / GeoAlchemy2 (present) |
| Spatial clustering of provider results | `ST_ClusterDBSCAN` or Python distance matrix | PostGIS 3.5 (present) |
| Provider weight config | Dict of `{provider_name: weight}` | Python stdlib |
| Outlier detection | Results > N meters from cluster centroid | `ST_Centroid` + `ST_Distance` (PostGIS) |
| Score aggregation | Weighted mean of agreement ratios | Python `statistics.mean` |

**Algorithm sketch (no new libraries):**
```python
from statistics import mean

PROVIDER_WEIGHTS = {
    "census": 0.8,
    "tiger": 0.9,
    "openaddresses": 0.95,
    "nad": 0.85,
    "macon_bibb": 1.0,
}

def compute_consensus(results: list[ProviderCoordinate], agreement_radius_m: float = 100.0) -> ConsensusScore:
    # 1. For each pair, compute distance via haversine or PostGIS
    # 2. Build adjacency: providers within agreement_radius_m of each other "agree"
    # 3. Largest agreement cluster = winning group
    # 4. score = (agreeing_providers / total_providers) * mean(weighted_confidences)
    # 5. Outliers = providers outside the winning cluster — flag, do not use for official
    ...
```

**PostGIS distance query (already available):**
```sql
SELECT
    p1.provider, p2.provider,
    ST_Distance(
        Geography(ST_MakePoint(p1.lon, p1.lat)),
        Geography(ST_MakePoint(p2.lon, p2.lat))
    ) AS distance_meters
FROM provider_results p1, provider_results p2
WHERE p1.address_id = p2.address_id AND p1.provider != p2.provider
```

---

### New Packages Summary

| Package | Version | Install Command | Notes |
|---------|---------|----------------|-------|
| `symspellpy` | 6.9.0 | `uv add symspellpy` | Only new Python dep for v1.2 |
| `ollama` | 0.6.1 | `uv add ollama` (optional) | Only if raw httpx insufficient |

**PostgreSQL extensions** — no install needed, activated via SQL migration:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- bundled in postgis/postgis:17-3.5
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch; -- already present from v1.1 Tiger setup
```

**Docker infrastructure** — add `ollama` service to `docker-compose.yml` (see above).

---

### What NOT to Add

| Do Not Add | Why | Use Instead |
|------------|-----|-------------|
| `pyspellchecker` | Slow Levenshtein permutation approach; no compound correction; no custom dictionary bootstrapping | `symspellpy` |
| `textblob` / `spaCy` / `nltk` | General NLP — heavy dependencies, not designed for address domain dictionaries | `symspellpy` with custom dictionary |
| `soundex()` for street phonetics | 4-char Soundex codes collide aggressively — "Main" and "Macon" share a code | `dmetaphone()` + `dmetaphone_alt()` |
| `similarity()` for street-name-vs-full-address | Scores poorly when query is tiny fraction of target string | `word_similarity()` or `strict_word_similarity()` |
| GIN index for ORDER BY similarity | GIN supports threshold `WHERE` but not distance `ORDER BY` | GiST index for ordered results |
| `phi-3-mini:3.8b` | Documented JSON schema compliance issues; slightly larger than qwen2.5:3b | `qwen2.5:3b` |
| `qwen2.5:7b` or larger | 2x memory for marginal gain on short address strings; model upgrade is trivial if needed | `qwen2.5:3b` |
| `transformers` in-process | Adds 2–3 GB to API process; blocks async event loop without process pool | Ollama sidecar via HTTP |
| `llama.cpp` directly | Manual binary build and GGUF management; no model library | Ollama |
| `scipy` / `sklearn` for DBSCAN | Heavy import for a single use case; PostGIS ST_ClusterDBSCAN already available | `ST_ClusterDBSCAN` via asyncpg |
| `VoteM8` / `CoVIRA` | Designed for molecular docking / bioinformatics — wrong domain | Custom weighted scoring with PostGIS |

---

### Version Compatibility (v1.2 Additions)

| Package / Extension | Compatible With | Notes |
|--------------------|----------------|-------|
| `symspellpy==6.9.0` | Python 3.9–3.13, `editdistpy` (auto-installed) | No conflict with existing stack |
| `ollama==0.6.1` | Python >=3.8, `httpx` (already present) | Requires httpx >=0.26.0 — verify `httpx==0.28.1` in lock file is compatible |
| `pg_trgm` | PostgreSQL 17 (contrib, bundled) | Idempotent `CREATE EXTENSION IF NOT EXISTS` |
| `fuzzystrmatch` | PostgreSQL 17 (contrib, already present from Tiger) | Already active; `CREATE EXTENSION IF NOT EXISTS` is safe no-op |
| `ollama/ollama:latest` | CPU + GPU; `OLLAMA_HOST=0.0.0.0:11434` default in container | Pin to version tag (e.g., `0.6.x`) in production |

---

### Sources (v1.2)

- [PostgreSQL 17 fuzzystrmatch official docs](https://www.postgresql.org/docs/17/fuzzystrmatch.html) — HIGH confidence; all function signatures verified directly
- [PostgreSQL pg_trgm official docs (current)](https://www.postgresql.org/docs/current/pgtrgm.html) — HIGH confidence; all operators, functions, index types verified directly
- [symspellpy PyPI](https://pypi.org/project/symspellpy/) — HIGH confidence; version 6.9.0 released 2025-03-09, Python 3.9–3.13
- [symspellpy GitHub](https://github.com/mammothb/symspellpy) — HIGH confidence; `load_dictionary()`, `load_bigram_dictionary()`, `create_dictionary_entry()`, `lookup_compound()` API verified
- [ollama PyPI](https://pypi.org/project/ollama/) — HIGH confidence; version 0.6.1, Python >=3.8, httpx-backed `AsyncClient`
- [Ollama structured outputs official docs](https://docs.ollama.com/capabilities/structured-outputs) — HIGH confidence; raw HTTP `format` parameter schema verified
- [ollama/ollama Docker Hub](https://hub.docker.com/r/ollama/ollama) — MEDIUM confidence; `OLLAMA_HOST=0.0.0.0:11434` default in container image
- [Qwen2.5 model on Ollama library](https://ollama.com/library/qwen2.5) — MEDIUM confidence; quantization sizes and memory requirements
- [Qwen2.5-3B hardware specs](https://apxml.com/models/qwen2-5-3b) — MEDIUM confidence; ~1.9 GB Q4_K_M, ~2.5 GB RAM, CPU inference 8–12 tok/s
- [spell-checkers-comparison repo](https://github.com/diffitask/spell-checkers-comparison) — MEDIUM confidence; symspellpy outperforms pyspellchecker on speed and accuracy benchmarks
- [EarthDaily geocoding consensus algorithm](https://earthdaily.com/blog/geocoding-consensus-algorithm-a-foundation-for-accurate-risk-assessment) — MEDIUM confidence; spatial clustering approach validated for multi-provider consensus

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

### What NOT to Add (v1.1)

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

## Sources (v1.1)

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
*Stack research for: CivPulse Geo API v1.2 Cascading Address Resolution — new capabilities*
*Researched: 2026-03-29*
