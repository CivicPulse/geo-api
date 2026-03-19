# Phase 1: Foundation - Research

**Researched:** 2026-03-19
**Domain:** FastAPI + SQLAlchemy 2.0 + GeoAlchemy2 + PostGIS + Alembic + Python ABCs
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Canonical Key Strategy**
- Full USPS standardization for normalization: suffixes (Street->ST), directionals (North->N), unit designators (Apartment->APT), state names (Georgia->GA), plus lowercasing and whitespace normalization
- Two-tier key with inheritance for unit numbers: base address (no unit) is the geocoding cache key; individual units stored as separate address records that inherit the base address geocode unless specifically overridden by an admin
- ZIP5 only in canonical key — ZIP+4 would split cache entries unnecessarily
- Key format: store both the normalized string (human-readable, debuggable) AND a hash column for fast lookups

**Schema Design**
- Separate `official_geocoding` table linking address to its official result
- Separate `admin_overrides` table for admin-set custom coordinates — distinct from provider results
- Query priority chain: `admin_overrides` > `official_geocoding` > provider results
- Addresses table stores parsed components (street, city, state, zip, unit) plus the original freeform input
- Location type as PostgreSQL enum on geocoding_results: ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE
- `created_at` and `updated_at` timestamps with database defaults on all tables
- PostGIS `geography(Point, 4326)` column type — locked
- Addresses and geocoding_results as separate tables — locked

**Plugin Contract Shape**
- Async methods (`async def geocode(...)`)
- Custom exception hierarchy: ProviderError base with subtypes ProviderNetworkError, ProviderAuthError, ProviderRateLimitError
- Structured result dataclass GeocodingResult with typed fields: lat, lng, location_type, confidence, raw_response, provider_name
- Explicit provider registry via config (dict/list mapping provider names to classes)

**Project Scaffolding**
- `src/` layout: `src/civpulse_geo/` with `models/`, `providers/`, `api/`, `cli/` subdirectories
- Pydantic Settings for configuration with .env file support
- Seed data: both real Bibb County GIS samples (from SAMPLE_Address_Points.geojson) and synthetic edge-case addresses
- pytest with conftest.py fixtures for database sessions, test client, and provider mocks; optional Docker test DB via environment variable (TEST_DATABASE_URL)

**Tech Stack (CivPulse ecosystem — non-negotiable)**
- Python, FastAPI, Loguru, Typer
- `uv` for all Python environment and package management
- Docker Compose for local development (PostgreSQL/PostGIS + API)

### Claude's Discretion
- Exact Alembic migration structure and naming
- Specific index choices beyond primary/foreign keys
- Health endpoint implementation details
- Docker Compose service naming and networking
- Exact hash algorithm for canonical key hash column
- pytest fixture organization and conftest structure

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Input addresses are normalized to a canonical form before cache lookup to maximize hit rate | usaddress-scourgify for USPS normalization; SHA-256 hash column for fast lookup |
| INFRA-02 | External geocoding/validation providers are implemented as plugins with a common interface | Python `abc.ABC` + `abstractmethod` enforces interface at instantiation; async method signature documented |
| INFRA-05 | API exposes a health/readiness endpoint that verifies database connectivity | FastAPI lifespan + `SELECT 1` via AsyncSession; returns 200 on success, 503 on DB failure |
| INFRA-07 | `docker compose up` provides a fully running local development environment with PostgreSQL/PostGIS and seed data | postgis/postgis:17-3.5 image; `/docker-entrypoint-initdb.d/` for seed SQL; pg_isready healthcheck |
</phase_requirements>

---

## Summary

This phase establishes the entire foundation: database schema, address normalization, provider plugin contract, and project scaffolding. Every subsequent phase consumes these artifacts — schema changes after Phase 1 have cascading cost, so getting the data model right matters more here than anywhere else.

The primary technical surface is SQLAlchemy 2.0 ORM with GeoAlchemy2 for PostGIS geography columns, Alembic for migrations (with GeoAlchemy2 helpers to prevent autogenerate pitfalls), Python ABCs for the provider contract, and Docker Compose with the official `postgis/postgis` image. The canonical address normalization function uses `usaddress-scourgify` to apply USPS Pub 28 abbreviation standards, then computes a SHA-256 hash for fast database lookups.

A critical finding: Python ABCs enforce abstract method implementation at **instantiation time**, not import/load time. The success criterion says "raises an error at load time" — this is achievable by eagerly instantiating each registered provider class at application startup (inside the provider registry initialization), converting the enforcement point from "whenever someone calls the class" to "when the app starts." This satisfies the intent of the requirement.

**Primary recommendation:** Use `from geoalchemy2.types import Geography` with `Geography(geometry_type='POINT', srid=4326)` for geography columns; configure Alembic env.py with all three GeoAlchemy2 helpers (`include_object`, `writer`, `render_item`) to prevent broken autogenerate migrations; and register providers eagerly at startup to surface missing-method errors before any request is served.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi[standard] | 0.135.1 | HTTP framework, routing, dependency injection | CivPulse ecosystem; async-native; OpenAPI generation included |
| sqlalchemy | 2.0.48 | ORM and core SQL layer | Industry standard; full async support in 2.0; typed mapped columns |
| geoalchemy2 | 0.18.4 | PostGIS geography/geometry column types for SQLAlchemy | Only maintained SQLAlchemy extension for PostGIS; official docs reference |
| alembic | 1.18.4 | Database migration management | Official SQLAlchemy migration tool; Alembic 1.x supports SQLAlchemy 2.0 |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Required for SQLAlchemy async engine with PostgreSQL; fastest PG async driver |
| pydantic-settings | 2.13.1 | Type-safe configuration from env/dotenv | Validated at startup; FastAPI-native; CivPulse pattern |
| loguru | 0.7.3 | Structured logging | CivPulse ecosystem constraint |
| typer | 0.24.1 | CLI for seed data tooling | CivPulse ecosystem constraint |
| usaddress-scourgify | 0.6.0 | USPS Pub 28 address normalization | Handles suffix, directional, unit abbreviations; returns structured components |

### Supporting (dev/test)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 | Test runner | All tests |
| pytest-asyncio | 1.3.0 | Async test support | Tests hitting async SQLAlchemy sessions and async FastAPI routes |
| httpx | 0.28.1 | Async HTTP test client | FastAPI TestClient for async tests |
| psycopg2-binary | 2.9.11 | Sync PG driver for Alembic | Alembic migration commands run synchronously; asyncpg is for the app |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncpg | psycopg3 (async) | psycopg3 is newer but asyncpg is more battle-tested with SQLAlchemy 2.0 async |
| usaddress-scourgify | usaddress alone | usaddress parses; scourgify normalizes to USPS Pub 28 standards — both are needed and scourgify wraps usaddress |
| SHA-256 (hash algo) | SHA-1 | SHA-1 has known collision weaknesses; SHA-256 is the standard recommendation for any new application |

**Installation:**

```bash
uv add fastapi[standard] sqlalchemy geoalchemy2 alembic asyncpg pydantic-settings loguru typer usaddress-scourgify
uv add --dev pytest pytest-asyncio httpx psycopg2-binary
```

**Version verification (confirmed 2026-03-19 against PyPI):**

| Package | Verified Version |
|---------|-----------------|
| geoalchemy2 | 0.18.4 |
| alembic | 1.18.4 |
| sqlalchemy | 2.0.48 |
| fastapi | 0.135.1 |
| pydantic-settings | 2.13.1 |
| asyncpg | 0.31.0 |
| loguru | 0.7.3 |
| typer | 0.24.1 |
| usaddress-scourgify | 0.6.0 |
| pytest | 9.0.2 |
| pytest-asyncio | 1.3.0 |
| httpx | 0.28.1 |
| psycopg2-binary | 2.9.11 |

## Architecture Patterns

### Recommended Project Structure

```
geo-api/
├── pyproject.toml          # uv project; all dependencies here
├── uv.lock                 # locked dependency graph
├── .env.example            # template for local env vars
├── docker-compose.yml      # PostGIS + API services
├── Dockerfile              # API image; uv-based multi-stage build
├── alembic.ini             # Alembic config
├── alembic/
│   ├── env.py              # GeoAlchemy2 helpers configured here
│   └── versions/           # migration scripts
├── scripts/
│   └── seed.py             # standalone seed data script
├── src/
│   └── civpulse_geo/
│       ├── __init__.py
│       ├── main.py         # FastAPI app + lifespan
│       ├── config.py       # pydantic-settings Settings class
│       ├── database.py     # engine, sessionmaker, get_db dependency
│       ├── models/
│       │   ├── __init__.py
│       │   ├── base.py     # DeclarativeBase + TimestampMixin
│       │   ├── address.py  # Address ORM model
│       │   ├── geocoding.py # GeocodingResult, OfficialGeocoding ORM models
│       │   └── enums.py    # LocationType PostgreSQL enum
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py     # GeocodingProvider, ValidationProvider ABCs
│       │   ├── exceptions.py # ProviderError hierarchy
│       │   ├── registry.py # provider registry + eager instantiation
│       │   └── schemas.py  # GeocodingResult dataclass
│       └── api/
│           ├── __init__.py
│           └── health.py   # /health endpoint
└── tests/
    ├── conftest.py         # engine, session, test_client fixtures
    ├── test_normalization.py
    ├── test_providers.py   # ABC enforcement tests
    ├── test_health.py
    └── test_migrations.py  # schema smoke test
```

### Pattern 1: Geography Column Definition

**What:** Use `geoalchemy2.types.Geography` (not `Geometry`) for distance-in-meters semantics locked by the project.

**When to use:** All lat/lng coordinate columns in this project.

**Example:**

```python
# Source: geoalchemy-2.readthedocs.io/en/latest/types.html
from sqlalchemy import Column
from geoalchemy2.types import Geography

class GeocodingResult(Base):
    __tablename__ = "geocoding_results"
    # ...
    location = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
```

### Pattern 2: SQLAlchemy 2.0 DeclarativeBase with Timestamp Mixin

**What:** Use the new `DeclarativeBase` from `sqlalchemy.orm` (not the legacy `declarative_base()` from `sqlalchemy.ext.declarative`).

**Example:**

```python
# Source: SQLAlchemy 2.0 docs — sqlalchemy.org/en/20/orm/declarative_styles.html
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column
from sqlalchemy import DateTime, func
import datetime

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: MappedColumn[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: MappedColumn[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

### Pattern 3: Alembic env.py with GeoAlchemy2 Helpers

**What:** Three helpers from `geoalchemy2.alembic_helpers` must all be wired in to prevent broken autogenerate migrations.

**Example:**

```python
# Source: geoalchemy-2.readthedocs.io/en/latest/alembic.html
from geoalchemy2 import alembic_helpers

# In both run_migrations_offline() and run_migrations_online():
context.configure(
    ...
    include_object=alembic_helpers.include_object,
    process_revision_directives=alembic_helpers.writer,
    render_item=alembic_helpers.render_item,
)
```

### Pattern 4: Provider ABC with Eager Enforcement

**What:** ABCs enforce missing methods at instantiation (not import). Register providers eagerly at startup to surface errors before any request is served.

**Example:**

```python
# src/civpulse_geo/providers/base.py
import abc

class GeocodingProvider(abc.ABC):
    @abc.abstractmethod
    async def geocode(self, address: str) -> "GeocodingResult": ...

    @abc.abstractmethod
    async def batch_geocode(self, addresses: list[str]) -> list["GeocodingResult"]: ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

# src/civpulse_geo/providers/registry.py
from civpulse_geo.config import settings

def load_providers() -> dict[str, GeocodingProvider]:
    """Eagerly instantiate all configured providers.

    TypeError is raised here at startup if any provider class omits a required method.
    """
    registry = {}
    for name, cls in settings.provider_classes.items():
        registry[name] = cls()   # ABC enforcement fires here
    return registry
```

### Pattern 5: FastAPI Lifespan with DB and Provider Initialization

**What:** Use the `@asynccontextmanager` lifespan pattern (FastAPI >= 0.95) instead of deprecated `@app.on_event`.

**Example:**

```python
# src/civpulse_geo/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from civpulse_geo.database import create_engine_and_session
from civpulse_geo.providers.registry import load_providers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.state.providers = load_providers()   # surfaces ABC violations at startup
    yield
    # shutdown

app = FastAPI(lifespan=lifespan)
```

### Pattern 6: Health Endpoint with DB Connectivity Check

**What:** Execute `SELECT 1` via an AsyncSession to confirm the database is reachable.

**Example:**

```python
# src/civpulse_geo/api/health.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from civpulse_geo.database import get_db

router = APIRouter()

@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
```

### Pattern 7: Canonical Address Normalization

**What:** Use usaddress-scourgify to normalize to USPS Pub 28 standards; SHA-256 hash the result for the fast-lookup column.

**Example:**

```python
# src/civpulse_geo/normalization.py
import hashlib
from scourgify import normalize_address_record
from scourgify.exceptions import AmbiguousAddressError, AddressNormalizeError

def canonical_key(freeform: str) -> tuple[str, str]:
    """Return (normalized_string, sha256_hex) for a freeform address.

    Uses ZIP5 only — never ZIP+4 — to prevent cache splits by unit/floor.
    Strips unit component from the base geocoding key (see two-tier key design).
    """
    try:
        parsed = normalize_address_record(freeform)
    except (AmbiguousAddressError, AddressNormalizeError):
        # Fall back to simple whitespace/case normalization when scourgify fails
        parsed = _fallback_normalize(freeform)

    # Build canonical string from components
    parts = [
        parsed.get("address_line_1", ""),
        parsed.get("city", ""),
        parsed.get("state", ""),
        (parsed.get("postal_code") or "")[:5],  # ZIP5 only
    ]
    normalized = " ".join(p.strip().upper() for p in parts if p)
    hash_value = hashlib.sha256(normalized.encode()).hexdigest()
    return normalized, hash_value
```

### Anti-Patterns to Avoid

- **Using `Geometry` instead of `Geography`:** The project decision is locked to `geography(Point, 4326)` — `Geography` uses spherical math giving distance-in-meters semantics. `Geometry` uses planar math. These are not interchangeable.
- **Skipping GeoAlchemy2 Alembic helpers:** Without all three helpers, autogenerate creates duplicate spatial indexes and missing imports in migration files, breaking `alembic upgrade head`.
- **Using `@app.on_event("startup")`:** Deprecated since FastAPI 0.95. Use the lifespan context manager.
- **Using `declarative_base()` from `sqlalchemy.ext.declarative`:** Legacy API. Use `DeclarativeBase` from `sqlalchemy.orm` for SQLAlchemy 2.0.
- **Relying on ZIP+4 in the canonical key:** ZIP+4 varies by unit/floor and would cause cache misses for the same building.
- **Assuming ABCs enforce at import time:** They do not. Only `TypeError` at instantiation time. Eager instantiation at startup is the pattern that satisfies the "at load time" requirement.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| USPS address normalization | Custom regex for suffix/directional abbrev. | usaddress-scourgify | 300+ USPS suffix variants, directional/unit abbreviation tables; years of edge cases baked in |
| PostGIS column types | Raw `VARCHAR` for WKT storage | GeoAlchemy2 Geography type | Spatial index, `ST_*` function integration, reflection support — not achievable with raw text |
| Database migrations | Manual `ALTER TABLE` scripts | Alembic | History, revision graph, up/down, autogenerate |
| Env/config validation | `os.getenv()` with manual type casts | pydantic-settings | Type coercion, validation errors at startup, `.env` file support, IDE completion |
| PostgreSQL enum enforcement | Application-level string validation | PostgreSQL native ENUM type | DB-level rejection of invalid values; enforced even if someone writes directly to the table |

**Key insight:** The address normalization problem looks simple (just abbreviate "Street" to "St") but USPS Pub 28 has 300+ street suffix abbreviations, multiple directional forms, and ~50 unit designator variants. Any hand-rolled solution will have gaps that split the cache.

## Common Pitfalls

### Pitfall 1: GeoAlchemy2 Alembic autogenerate creates broken migrations

**What goes wrong:** Running `alembic revision --autogenerate` without the three GeoAlchemy2 helpers produces migration files that (a) are missing `from geoalchemy2 import ...` imports, (b) create spatial indexes twice (once implicitly during `CREATE TABLE`, once explicitly), causing `alembic upgrade head` to fail.

**Why it happens:** Alembic's default autogenerate doesn't know about PostGIS spatial extensions. GeoAlchemy2 provides helpers specifically to patch this.

**How to avoid:** Wire all three helpers into `alembic/env.py` before writing any migrations:
```python
from geoalchemy2 import alembic_helpers
context.configure(
    include_object=alembic_helpers.include_object,
    process_revision_directives=alembic_helpers.writer,
    render_item=alembic_helpers.render_item,
)
```

**Warning signs:** Migration script contains `op.create_index` on a geography column AND the `CREATE TABLE` also includes that column — duplicate index.

### Pitfall 2: Alembic cannot use the async engine directly

**What goes wrong:** Alembic migration commands (`alembic upgrade head`) are synchronous. If the SQLAlchemy engine is an `AsyncEngine`, Alembic will raise an error.

**Why it happens:** Alembic uses its own synchronous connection management. The async engine is only for application request handling.

**How to avoid:** Configure two connection strings — `DATABASE_URL` for the async app (`postgresql+asyncpg://...`) and a separate synchronous URL for Alembic (`postgresql+psycopg2://...`). In `alembic/env.py`:

```python
# alembic/env.py — use sync driver for migrations
from civpulse_geo.config import settings
config.set_main_option("sqlalchemy.url", settings.database_url_sync)
```

**Warning signs:** `alembic upgrade head` raises `NotImplementedError: The asyncio extension requires an async driver...`

### Pitfall 3: PostgreSQL ENUM + Alembic autogenerate

**What goes wrong:** Alembic's autogenerate does not correctly handle PostgreSQL ENUM type additions/removals. It may skip creating the enum entirely, or attempt to drop and recreate it (which fails if the column is in use).

**Why it happens:** Known Alembic limitation, tracked since 2015.

**How to avoid:** For the `LocationType` enum: let autogenerate create the initial migration, then manually review it to confirm the `CREATE TYPE` statement is present. Add `alembic-postgresql-enum` (v1.10.0) to dev dependencies if enum values need to change after initial creation.

**Warning signs:** `alembic upgrade head` raises `ProgrammingError: type "locationtype" does not exist`.

### Pitfall 4: ABC enforcement is not at import time

**What goes wrong:** The success criterion says providers "raise an error at load time." Python ABCs raise `TypeError` only when you try to instantiate the class, not when the module is imported.

**Why it happens:** ABCMeta defers enforcement to instantiation by design.

**How to avoid:** Eagerly instantiate every registered provider class inside `load_providers()` which is called from the FastAPI lifespan startup. This means any class with a missing abstract method raises `TypeError` before the first HTTP request is served — effectively "at application load time."

**Warning signs:** A malformed provider class passes import without error, but fails only when first called.

### Pitfall 5: usaddress-scourgify raises on unparseable input

**What goes wrong:** `normalize_address_record()` raises `AmbiguousAddressError` or `AddressNormalizeError` for inputs it cannot parse (PO boxes, partial addresses, international formats).

**Why it happens:** The library is strict — it does not silently return partial results.

**How to avoid:** Wrap all calls in try/except and implement a fallback that does simple uppercase + whitespace normalization. The fallback still produces a consistent key even if it is less precise.

**Warning signs:** Unit tests with PO Box or partial address inputs throw unhandled exceptions.

### Pitfall 6: Docker Compose API starts before PostGIS is ready

**What goes wrong:** The API container starts, tries to connect to PostgreSQL, fails (PostGIS is still initializing), and crashes before any request is served.

**Why it happens:** Docker Compose `depends_on` by default only waits for the container to start, not for PostgreSQL to be ready to accept connections.

**How to avoid:** Add a healthcheck to the `db` service and use `depends_on: condition: service_healthy` in the `api` service:

```yaml
services:
  db:
    image: postgis/postgis:17-3.5
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5
  api:
    depends_on:
      db:
        condition: service_healthy
```

**Warning signs:** `docker compose up` shows the API repeatedly crashing with a connection refused error on the first startup.

## Code Examples

### Geography Column in ORM Model

```python
# Source: geoalchemy-2.readthedocs.io/en/latest/types.html (verified 2026-03-19)
from sqlalchemy import Column, String, Enum as PgEnum
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column
from geoalchemy2.types import Geography
from civpulse_geo.models.enums import LocationType

class GeocodingResult(Base):
    __tablename__ = "geocoding_results"
    id: MappedColumn[int] = mapped_column(primary_key=True)
    location: MappedColumn = mapped_column(
        Geography(geometry_type='POINT', srid=4326), nullable=True
    )
    location_type: MappedColumn = mapped_column(
        PgEnum(LocationType, name="locationtype", create_type=True), nullable=True
    )
```

### Async Engine and Session Setup

```python
# Source: SQLAlchemy 2.0 async docs + FastAPI patterns
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from civpulse_geo.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

### Alembic env.py Async + GeoAlchemy2

```python
# alembic/env.py — key sections
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from geoalchemy2 import alembic_helpers
from civpulse_geo.config import settings
from civpulse_geo.models.base import Base

target_metadata = Base.metadata

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    # Use sync URL for Alembic
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()
```

### Provider ABC Definition

```python
# Source: Python docs — docs.python.org/3/library/abc.html
import abc
from dataclasses import dataclass
from typing import Any

@dataclass
class GeocodingResult:
    lat: float
    lng: float
    location_type: str      # matches LocationType enum values
    confidence: float       # 0.0–1.0
    raw_response: dict[str, Any]
    provider_name: str

class GeocodingProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

    @abc.abstractmethod
    async def geocode(self, address: str) -> GeocodingResult: ...
```

### Seed Data Loading from GeoJSON

```python
# scripts/seed.py — reading SAMPLE_Address_Points.geojson
import json
from pathlib import Path

GEOJSON_PATH = Path(__file__).parent.parent / "data" / "SAMPLE_Address_Points.geojson"

def load_bibb_county_seeds() -> list[dict]:
    with GEOJSON_PATH.open() as f:
        data = json.load(f)
    return [feature["properties"] for feature in data["features"]]
```

### Docker Compose Structure

```yaml
# docker-compose.yml skeleton
services:
  db:
    image: postgis/postgis:17-3.5
    environment:
      POSTGRES_DB: civpulse_geo
      POSTGRES_USER: civpulse
      POSTGRES_PASSWORD: civpulse
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/seed.sql:/docker-entrypoint-initdb.d/01_seed.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U civpulse -d civpulse_geo"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    environment:
      DATABASE_URL: postgresql+asyncpg://civpulse:civpulse@db:5432/civpulse_geo
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

### Dockerfile for uv + src Layout

```dockerfile
# Source: docs.astral.sh/uv/guides/integration/docker/ (verified 2026-03-19)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer — only rebuilds when lock file changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy source and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "civpulse_geo.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `declarative_base()` from `sqlalchemy.ext.declarative` | `DeclarativeBase` from `sqlalchemy.orm` | SQLAlchemy 2.0 (2023) | Typed mapped columns, better IDE support |
| `@app.on_event("startup")` | `@asynccontextmanager` lifespan | FastAPI 0.95 (2023) | Cleaner resource management, no deprecation warning |
| `pip` / `poetry` | `uv` | 2024 | 10-100x faster installs; lock file included; CivPulse standard |
| Geometry type for lat/lng | Geography type for lat/lng | PostGIS 2.x+ | Distance-in-meters semantics without manual SRID casting |

**Deprecated/outdated patterns to avoid:**
- `from sqlalchemy.ext.declarative import declarative_base` — legacy, still works but not recommended
- `@app.on_event` decorator — deprecated, use lifespan
- `alembic_postgresql_enum` is needed only if enum values change post-creation; not required for initial schema

## Open Questions

1. **Alembic async vs sync connection in env.py**
   - What we know: Alembic requires a synchronous connection; the app uses `asyncpg` async
   - What's unclear: Whether `alembic.ini` should reference the sync URL directly or load it from pydantic-settings
   - Recommendation: Load settings in `env.py` and construct both async and sync URLs from a single base config; expose `settings.database_url_sync` returning `postgresql+psycopg2://...`

2. **Seed data mechanism: SQL file vs Python script**
   - What we know: `/docker-entrypoint-initdb.d/` runs `.sql` and `.sh` scripts on first container start
   - What's unclear: Whether to generate seed SQL from GeoJSON at build time (static file) or run a Python seed script at startup
   - Recommendation: Generate `seed.sql` from `SAMPLE_Address_Points.geojson` via a Python script run once at project setup; mount the resulting `.sql` into `initdb.d/` to keep Docker Compose self-contained without requiring Python in the DB container

3. **pytest PostGIS in CI**
   - What we know: Integration tests against real PostGIS require a running DB; unit tests can mock
   - What's unclear: Whether the project expects PostGIS available in CI or mocked
   - Recommendation: Structure tests with two tiers — fast unit tests with mocked DB (no Docker required) gated on `TEST_DATABASE_URL` env variable for integration tests; CI can opt in or skip

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` section (Wave 0) |
| Quick run command | `uv run pytest tests/ -x -q --ignore=tests/integration` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `canonical_key("123 Main Street")` == `canonical_key("123 Main St")` | unit | `uv run pytest tests/test_normalization.py -x` | Wave 0 |
| INFRA-01 | ZIP+4 stripped to ZIP5 in canonical key | unit | `uv run pytest tests/test_normalization.py::test_zip5_only -x` | Wave 0 |
| INFRA-01 | Unit number excluded from base geocoding key | unit | `uv run pytest tests/test_normalization.py::test_unit_excluded -x` | Wave 0 |
| INFRA-02 | Concrete class omitting `geocode()` raises TypeError on instantiation | unit | `uv run pytest tests/test_providers.py::test_missing_method_raises -x` | Wave 0 |
| INFRA-02 | `load_providers()` raises at startup if a provider is malformed | unit | `uv run pytest tests/test_providers.py::test_registry_enforces -x` | Wave 0 |
| INFRA-05 | `GET /health` returns 200 and `"database": "connected"` | integration | `uv run pytest tests/test_health.py -x` | Wave 0 |
| INFRA-05 | `GET /health` returns 503 when DB is unreachable | unit (mocked) | `uv run pytest tests/test_health.py::test_health_db_down -x` | Wave 0 |
| INFRA-07 | `docker compose up` starts without error and API /health returns 200 | smoke (manual) | `docker compose up -d && curl localhost:8000/health` | manual |
| INFRA-07 | Alembic migrations apply cleanly from scratch | integration | `uv run pytest tests/test_migrations.py -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q --ignore=tests/integration`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

All test files must be created; no existing test infrastructure exists (greenfield project).

- [ ] `tests/conftest.py` — async engine, test session, TestClient fixtures; `TEST_DATABASE_URL` env variable gating for integration tests
- [ ] `tests/test_normalization.py` — covers INFRA-01
- [ ] `tests/test_providers.py` — covers INFRA-02 (ABC enforcement, registry eager load)
- [ ] `tests/test_health.py` — covers INFRA-05 (happy path + mocked DB failure)
- [ ] `tests/test_migrations.py` — covers schema existence smoke test (INFRA-07 partial)
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"` required for pytest-asyncio 1.x

## Sources

### Primary (HIGH confidence)

- geoalchemy-2.readthedocs.io/en/latest/ — Geography type definition, column parameters, Alembic helper configuration
- docs.astral.sh/uv/guides/integration/docker/ — Dockerfile pattern, layer caching, ENV variables
- docs.astral.sh/uv/guides/integration/fastapi/ — uv + FastAPI pyproject.toml setup
- PyPI registry (2026-03-19) — all package versions verified via `curl pypi.org/pypi/{pkg}/json`
- docs.python.org/3/library/abc.html — ABC enforcement timing (instantiation, not import)

### Secondary (MEDIUM confidence)

- geoalchemy-2.readthedocs.io/en/latest/alembic.html — Three helper functions confirmed by WebFetch
- pypi.org/project/usaddress-scourgify/ — USPS Pub 28 normalization scope and limitations
- pypi.org/project/alembic-postgresql-enum/ — PostgreSQL enum autogenerate limitation and fix

### Tertiary (LOW confidence)

- WebSearch: pytest-asyncio `asyncio_mode = "auto"` in pyproject.toml — pattern found in multiple sources, not verified against official pytest-asyncio 1.3.0 docs directly
- WebSearch: `depends_on: condition: service_healthy` Docker Compose pattern — widely documented, not verified against Docker Compose spec version used

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all versions verified against PyPI registry on 2026-03-19
- Architecture: HIGH — patterns verified against GeoAlchemy2 docs, uv docs, SQLAlchemy 2.0 docs, Python ABC docs
- Pitfalls: HIGH (GeoAlchemy2/Alembic pitfalls confirmed by official GeoAlchemy2 docs); MEDIUM (ABC timing, Docker healthcheck)

**Research date:** 2026-03-19
**Valid until:** 2026-04-18 (stable ecosystem — these libraries version slowly; FastAPI and SQLAlchemy are most likely to patch)
