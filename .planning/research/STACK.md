# Technology Stack

**Project:** CivPulse Geo API
**Researched:** 2026-03-19
**Confidence note:** External network tools (WebSearch, WebFetch, Context7) were unavailable during this research session. All findings are from training data (knowledge cutoff August 2025). Version numbers should be validated against PyPI before pinning in pyproject.toml.

---

## Recommended Stack

### Core Framework (Pre-decided)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12+ | Runtime | Matches other CivPulse APIs; 3.12 has significant perf improvements over 3.11 |
| FastAPI | 0.111+ | HTTP API framework | Pre-decided; async-native, Pydantic v2 integration, OpenAPI autodoc |
| Pydantic | v2 (2.7+) | Request/response models, validation | Ships with FastAPI; v2 is significantly faster than v1 |
| Uvicorn | 0.29+ | ASGI server | Standard pairing with FastAPI; use `uvicorn[standard]` for watchfiles/httptools |
| Loguru | 0.7+ | Structured logging | Pre-decided; simpler than stdlib logging, good JSON sink support |
| Typer | 0.12+ | CLI commands (admin/maintenance) | Pre-decided; pairs with FastAPI apps for management commands |

**Confidence:** HIGH — these are project constraints, not decisions to make.

---

### Database Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16+ | Primary datastore | Pre-decided; mature, reliable, required for PostGIS |
| PostGIS | 3.4+ | Spatial types and queries | Pre-decided; industry standard for geo in Postgres; native `GEOMETRY(Point, 4326)` columns, spatial indexing with GIST, `ST_Distance`, `ST_DWithin` |
| GeoAlchemy2 | 0.14+ | SQLAlchemy spatial type integration | The standard bridge between SQLAlchemy and PostGIS; defines `Geometry` column types, compiles spatial functions to SQL, works with Alembic migrations |
| SQLAlchemy | 2.0+ | ORM / query builder | Async support via `asyncpg`; GeoAlchemy2 requires SQLAlchemy 2.x |
| asyncpg | 0.29+ | Async PostgreSQL driver | Fastest async Postgres driver for Python; required when using SQLAlchemy async engine |
| Alembic | 1.13+ | Schema migrations | Standard SQLAlchemy migration tool; GeoAlchemy2 spatial types serialize correctly in migration scripts |

**Confidence:** HIGH for SQLAlchemy 2 + GeoAlchemy2 + asyncpg combination — this is the de facto standard for async FastAPI + PostGIS. MEDIUM for specific minor versions.

**Why GeoAlchemy2 over raw SQL:** Spatial column types in Pydantic models, migration-safe geometry column definitions, and WKB/WKT serialization handled automatically. Avoids hand-rolling `ST_GeomFromText` in every insert.

**Why SQLAlchemy 2 async over sync:** FastAPI is async-native; using sync SQLAlchemy in async endpoints requires `run_in_executor` workarounds that defeat the purpose of async. The 2.0 async API with `AsyncSession` is clean and production-proven.

---

### Address Parsing and Normalization

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| usaddress | 0.5.10 | US address field tagging (parse freeform to components) | The most-cited pure-Python US address parser; uses probabilistic CRF model; extracts street number, street name, city, state, zip from freeform input |
| usaddress-scourgify | 0.4.1 | USPS-standard normalization on top of usaddress | Wraps usaddress output and normalizes to USPS abbreviations ("Road" → "RD", "Georgia" → "GA"); purpose-built for exactly what this project needs |

**Confidence:** MEDIUM — usaddress is well-established but unmaintained (last release ~2022). scourgify similarly mature but slow-moving. Both are still the correct choice for offline US address parsing; no compelling 2025 replacement has emerged. FLAG: Verify both packages are still installable and functional before committing.

**Why not libpostal:** libpostal (via pypostal) is the gold standard for international address parsing and is more accurate globally, but it requires a C library build (~3GB data files) and is overkill for US-only. The operational overhead is not justified.

**Why not spaCy address extraction:** Too generic; requires custom NER training for reliable US address component extraction. Not worth it when usaddress exists.

**Alternative if usaddress proves abandoned:** `addressparser` (PyPI) or fall back to regex-based normalization + USPS API validation as the source of truth. Given that USPS validation is one of the target services, the risk of usaddress gaps is low — USPS API results provide standardized components.

---

### Geocoding Client Libraries

This project wraps multiple external geocoding services. For each service:

| Service | Python Client | Version | Notes |
|---------|--------------|---------|-------|
| Google Geocoding API | `googlemaps` | 4.10+ | Official Google Maps Python client; covers Geocoding, Reverse Geocoding, Address Validation API |
| US Census Geocoder | `censusgeocode` | 0.5+ | Thin wrapper around Census Bureau REST API; no API key required; good for US addresses |
| Amazon Location Service | `boto3` | 1.34+ | AWS SDK; Amazon Location Service is in `boto3.client('location')`; no dedicated geocoding client needed |
| Geoapify | `httpx` (direct) | — | No official Python client; use `httpx` directly with their REST API |
| USPS Address Validation | `httpx` (direct) | — | USPS has a REST API (v3 as of 2024); no maintained Python client — use `httpx` directly |

**Confidence:** HIGH for googlemaps and boto3 (official clients). MEDIUM for censusgeocode (widely used, community maintained). MEDIUM for USPS REST approach — USPS released a new OAuth2-based v3 API; the old XML-based API is being deprecated. FLAG: Verify USPS API v3 endpoints and auth flow before implementation.

**Why `httpx` for direct calls (Geoapify, USPS):** httpx is async-native, has a clean interface, supports retry via `httpx-retries` or `tenacity`, and is already likely in the dependency tree for testing. Using `requests` in an async FastAPI app is an antipattern.

**geopy consideration:** geopy provides a unified interface over many geocoding backends (Google, Bing, Nominatim, etc.) and is the most popular geocoding library in Python. However, this project benefits from calling services individually and storing each result separately (for admin comparison/override workflow). A unified abstraction obscures per-service results. Use the native clients instead of geopy for this reason.

---

### HTTP Client (for external API calls)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx | 0.27+ | Async HTTP client for external service calls | Async-native, sync-compatible, clean API; replaces requests in async contexts |
| tenacity | 8.3+ | Retry logic for external API calls | Declarative retry with exponential backoff; geocoding services have transient failures |

**Confidence:** HIGH — httpx + tenacity is the standard 2024-2025 pattern for resilient async HTTP in Python.

---

### Data Validation and Serialization

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Pydantic | v2 (2.7+) | Request/response models, internal data contracts | Already in FastAPI; define address input models (freeform string vs structured fields), geocoding result models, confidence score models |
| pydantic-settings | 2.3+ | Environment-based configuration | Standard for FastAPI apps; reads from `.env` and environment variables for API keys (Google, AWS, Geoapify, USPS) |

**Confidence:** HIGH.

---

### Spatial Utilities

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Shapely | 2.0+ | In-memory geometric operations | When geometry manipulation is needed outside the database (e.g., bounding box checks, coordinate validation before insert); Shapely 2.0 rewrote internals with GEOS C bindings for 10x speedup |
| pyproj | 3.6+ | Coordinate reference system transformations | If any CRS conversion is needed; mostly used when input coordinates are not WGS84; likely optional for v1 but low-cost to include |

**Confidence:** MEDIUM — Shapely 2 is essential if doing any server-side geometry work. pyproj is optional for a US-only geocoding API that only deals with WGS84 lat/lng. Include Shapely, hold on pyproj until a use case emerges.

---

### Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | 8.2+ | Test runner | Standard; async support via pytest-asyncio |
| pytest-asyncio | 0.23+ | Async test support | Required for testing async FastAPI endpoints and async SQLAlchemy sessions |
| httpx | 0.27+ | Test client for FastAPI | FastAPI's `TestClient` uses httpx under the hood; use `AsyncClient` for async tests |
| factory-boy | 3.3+ | Test fixture factories | Reduces boilerplate for creating test address/geocoding records |
| pytest-postgresql | 5.0+ | Ephemeral PostgreSQL for tests | Spins up a real Postgres instance for tests; necessary for PostGIS spatial query testing; cannot mock PostGIS functions meaningfully |
| respx | 0.21+ | Mock httpx calls | Intercept external API calls in tests; prevents real calls to Google/USPS/Census during CI |

**Confidence:** HIGH for pytest stack. MEDIUM for pytest-postgresql version. The critical test infrastructure insight: PostGIS spatial queries must be tested against a real PostGIS instance — mocking SQLAlchemy at the ORM level will miss spatial index behavior and ST_* function correctness.

---

### Development Tooling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | 0.4+ | Package management and virtualenv | Fast; modern pip replacement; lock file support; consistent with 2025 Python packaging norms |
| ruff | 0.5+ | Linting and formatting | Replaces flake8 + isort + black in one tool; extremely fast |
| mypy | 1.10+ | Static type checking | SQLAlchemy 2 and Pydantic v2 have complete type stubs; mypy catches model mismatches early |
| pre-commit | 3.7+ | Git hooks | Run ruff and mypy before commits |

**Confidence:** HIGH for ruff and uv as 2024-2025 Python standards.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| ORM | SQLAlchemy 2 async | Tortoise ORM, SQLModel | SQLAlchemy 2 has best GeoAlchemy2 support; SQLModel is thin wrapper over SQLAlchemy 2 anyway |
| Geo ORM bridge | GeoAlchemy2 | Raw SQL geometry | GeoAlchemy2 handles WKB serialization, Alembic migration types, and column definition cleanly |
| Address parser | usaddress | libpostal | libpostal requires 3GB C library; overkill for US-only |
| Address parser | usaddress | regex/USPS only | USPS API must be called first to normalize; usaddress enables offline pre-normalization for cache key generation |
| HTTP client | httpx | aiohttp | httpx has cleaner API, sync/async unified, native httpx.AsyncClient for tests |
| Geocoding abstraction | Per-service clients | geopy unified | Project needs per-service results stored separately for admin override; unified abstraction defeats this |
| Retry | tenacity | stamina | tenacity is more established; stamina is newer with similar API but less ecosystem adoption |
| Package manager | uv | poetry | uv is faster, simpler, increasingly standard in 2025 |

---

## Installation

```bash
# Core dependencies
uv add fastapi uvicorn[standard] loguru typer pydantic pydantic-settings

# Database
uv add sqlalchemy[asyncio] geoalchemy2 asyncpg alembic

# Geocoding clients
uv add googlemaps boto3 censusgeocode httpx tenacity

# Address parsing
uv add usaddress usaddress-scourgify

# Spatial utilities
uv add shapely

# Dev dependencies
uv add --dev pytest pytest-asyncio pytest-postgresql factory-boy respx ruff mypy pre-commit
```

---

## Configuration Structure

All external API keys and service URLs should be injected via environment variables using `pydantic-settings`:

```python
# Required env vars
GOOGLE_MAPS_API_KEY=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
GEOAPIFY_API_KEY=...
USPS_CLIENT_ID=...        # USPS v3 OAuth2
USPS_CLIENT_SECRET=...    # USPS v3 OAuth2
DATABASE_URL=postgresql+asyncpg://...
```

---

## Versions to Validate Before Pinning

The following should be verified against PyPI before setting exact pins in `pyproject.toml`, as training data may be stale:

| Package | Claimed Version | Risk |
|---------|----------------|------|
| usaddress | 0.5.10 | Low activity — may be unmaintained |
| usaddress-scourgify | 0.4.1 | Low activity — check Python 3.12 compatibility |
| censusgeocode | 0.5+ | Community maintained — verify current release |
| USPS API v3 | — | New OAuth2 flow; verify endpoint URLs and auth in docs |
| pytest-postgresql | 5.0+ | Verify PostGIS extension support in ephemeral instance setup |

---

## Sources

- Training data, knowledge cutoff August 2025
- No external sources were accessible during this research session (WebSearch, WebFetch, Context7 all unavailable)
- All version claims are MEDIUM confidence at best; verify with `pip index versions <package>` or PyPI before pinning
