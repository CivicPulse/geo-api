# Phase 7: Pipeline Infrastructure - Research

**Researched:** 2026-03-22
**Domain:** Python ABC extension, SQLAlchemy/GeoAlchemy2 migrations, service-layer routing, Typer CLI with rich progress
**Confidence:** HIGH

## Summary

Phase 7 establishes the plumbing that all local data-source phases (8–10) depend on. It has four independent work streams: (1) add `is_local: bool` as a concrete property defaulting to `False` on both provider ABCs, (2) refactor the geocoding and validation service layers to split remote providers through the existing cache-write path and local providers through a bypass path that never touches `geocoding_results` or `validation_results`, (3) create two Alembic migrations for the `openaddresses_points` and `nad_points` staging tables, and (4) register two new CLI commands (`load-oa`, `load-nad`) as import stubs.

All patterns required already exist in the codebase: the GeoAlchemy2 `Geography(POINT, 4326)` + GiST index pattern appears in `initial_schema.py`, the `op.create_geospatial_table` / `op.create_geospatial_index` pair with `alembic_helpers` in `env.py`, the sync-engine raw-SQL CLI pattern in `cli/__init__.py`, and the ON CONFLICT upsert idiom throughout the service layer. No new third-party dependencies are introduced except `rich` (user-approved for progress bars).

The highest-risk implementation decision is the service-layer refactor: the bypass path must skip only the `geocoding_results` / `validation_results` DB writes while still performing the `addresses` upsert and OfficialGeocoding auto-set. The existing `geocode()` and `validate()` methods are long single functions — the refactor should extract a `_write_to_cache(provider, result)` helper that is conditionally skipped for local providers rather than duplicating pipeline code.

**Primary recommendation:** Use the `provider.is_local` check inside the provider iteration loop (Steps 4–5 of each service) to gate only the upsert statements, keeping address upsert and OfficialGeocoding logic unchanged for all providers.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pipeline bypass behavior**
- Per-provider routing: each provider is routed independently — remote providers go through cache, local providers bypass cache. Mixed requests return results from both paths together
- Local provider results ARE eligible for OfficialGeocoding auto-set, same as remote
- Local providers still create/find an Address record (upsert to addresses table) — only geocoding_results/validation_results writes are skipped
- Only return results from explicitly requested providers — no auto-including cached remote results

**Staging table design**
- Claude's discretion on provider-specific vs shared columns (choose based on source data formats)
- PostGIS Geography(POINT, 4326) column for spatial data — consistent with existing geocoding_results pattern
- GiST spatial index + composite B-tree index on (state, zip_code, street_name) for address-matching queries
- Source-specific hash column for deduplication: OA uses its built-in hash field, NAD uses composite hash from address components. Enables upsert-on-conflict for idempotent reloads

**CLI import commands**
- Upsert (ON CONFLICT UPDATE) when reloading data — safe for incremental loads and re-runs
- Progress reporting via `rich` progress bar (override of "no new dependencies" constraint — user decision)
- load-oa accepts a single .geojson.gz file path (users loop in shell for multiple files)
- load-nad accepts a single NAD TXT file path
- CLI commands use synchronous engine (psycopg2) following existing import pattern

**Provider ABC contract**
- `is_local` added as a concrete property with default `False` on both GeocodingProvider and ValidationProvider ABCs — existing providers need zero changes
- Local providers receive async_sessionmaker at construction time for querying staging tables — ABC method signatures unchanged
- Async sessions (asyncpg) for local providers, matching the async service layer
- Phase 7 only modifies ABCs and service layer — no skeleton provider classes

### Claude's Discretion
- Exact staging table column choices (provider-specific vs normalized)
- Alembic migration implementation details
- Service layer refactoring approach for the bypass path
- Test fixtures and factory patterns

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PIPE-01 | Service layer bypasses DB caching for providers with is_local=True | Service layer analysis: geocoding.py and validation.py provider loops at Step 4-5 are the insertion point. The `is_local` check gates only the pg_insert(GeocodingResultORM) / pg_insert(ValidationResultORM) statements. |
| PIPE-02 | Provider ABCs expose is_local property (default False) | base.py analysis: add `@property def is_local(self) -> bool: return False` as a concrete (non-abstract) method on both GeocodingProvider and ValidationProvider. No existing subclass needs changes. |
| PIPE-03 | Alembic migration creates openaddresses_points staging table with GiST spatial index | GeoAlchemy2 pattern confirmed: use op.create_geospatial_table + op.create_geospatial_index (gist) matching initial_schema.py. The alembic_helpers in env.py are already wired. |
| PIPE-04 | Alembic migration creates nad_points staging table with GiST spatial index | Same migration pattern as PIPE-03; separate migration file with nad_points-specific columns. Can be a single migration file creating both tables. |
| PIPE-05 | CLI command imports OpenAddresses .geojson.gz files into staging table | OA data is GeoJSON compressed with gzip; stdlib gzip + json suffice. load-oa: read .geojson.gz, batch upsert to openaddresses_points. Stub that registers and shows help text is the Phase 7 deliverable. |
| PIPE-06 | CLI command imports NAD r21 TXT CSV into staging table via COPY | NAD TXT is pipe-delimited CSV; psycopg2 cursor.copy_expert() is the bulk-load mechanism. Stub that registers and shows help text is the Phase 7 deliverable. |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| geoalchemy2 | 0.18.4 (already installed) | Geography column type + GiST index in Alembic | Already used in initial_schema.py; provides op.create_geospatial_table / op.create_geospatial_index |
| sqlalchemy | 2.0.48 (already installed) | ORM + core SQL, pg_insert upsert | Already the project ORM; pg_insert from dialects.postgresql used throughout services |
| alembic | 1.18.4 (already installed) | Schema migrations | Already configured with alembic_helpers in env.py |
| typer | 0.24.1 (already installed) | CLI framework | Already used for geo-import command |
| psycopg2-binary | 2.9.11 (already installed) | Synchronous driver for CLI bulk ops | Already the sync engine driver used in CLI |
| rich | NOT YET INSTALLED | Progress bars in load-oa / load-nad | User decision override — required for Phase 7 CLI commands |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| gzip (stdlib) | 3.12 | Decompress .geojson.gz OA files | load-oa command file reading |
| json (stdlib) | 3.12 | Parse GeoJSON features | load-oa command |
| hashlib (stdlib) | 3.12 | SHA-256 composite hash for NAD deduplication | NAD source_hash column |
| csv (stdlib) | 3.12 | Parse NAD pipe-delimited TXT | load-nad validation/preview; psycopg2 COPY handles bulk |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `rich` progress | `tqdm` | tqdm already in ecosystem but not installed; rich is user choice and integrates with typer natively |
| Two separate migration files | Single migration file for both tables | Single file is simpler; either works — separate files give cleaner rollback granularity |

**Installation (only new dependency):**
```bash
uv add rich
```

**Version verification:** `rich` latest stable as of 2026-03-22 is 13.x. Verify:
```bash
uv run python -c "import rich; print(rich.__version__)"
# Or: uv pip show rich
```

---

## Architecture Patterns

### Recommended Project Structure

No new top-level directories needed. Changes touch existing modules:

```
src/civpulse_geo/
├── providers/
│   └── base.py                   # ADD: is_local property to both ABCs
├── services/
│   ├── geocoding.py              # MODIFY: bypass path in geocode() provider loop
│   └── validation.py             # MODIFY: bypass path in validate() provider loop
├── models/
│   ├── openaddresses.py          # NEW: ORM model for openaddresses_points table
│   └── nad.py                    # NEW: ORM model for nad_points table
└── cli/
    └── __init__.py               # ADD: load-oa and load-nad commands

alembic/versions/
└── XXXXXXXX_add_staging_tables.py  # NEW: single migration for both staging tables
```

### Pattern 1: Concrete Non-Abstract Property on ABC

**What:** Add `is_local` as a concrete `@property` on the ABC with `return False`. Python ABCs allow concrete methods alongside abstract ones — subclasses inherit the default.
**When to use:** When you need a default behavior that most implementors share, with the option for subclasses to override.

```python
# Source: base.py (project pattern, extended with is_local)
class GeocodingProvider(abc.ABC):

    @property
    def is_local(self) -> bool:
        """True for providers that query local staging tables (bypass DB cache).

        Local providers (e.g., openaddresses, nad, tiger) return results directly
        without writing to geocoding_results. Defaults to False for all remote
        providers — no subclass changes required.
        """
        return False

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        ...
    # ... existing abstract methods unchanged
```

Same pattern applies to `ValidationProvider`.

### Pattern 2: Per-Provider Bypass Check in Service Layer

**What:** Inside the existing provider loop in `GeocodingService.geocode()` (Step 4–5), check `provider.is_local` to decide whether to write to `geocoding_results`. Address upsert and OfficialGeocoding auto-set run for all providers.
**When to use:** This is the bypass pattern required by PIPE-01.

```python
# Source: services/geocoding.py (project pattern, modified)
# Step 4: Call providers on cache miss
new_results: list[GeocodingResultORM] = []
local_results: list[GeocodingResult] = []  # provider schema type, not ORM

for provider_name, provider in providers.items():
    if not isinstance(provider, GeocodingProvider):
        continue

    provider_result = await provider.geocode(normalized, http_client=http_client)

    if provider.is_local:
        # BYPASS: skip geocoding_results write, collect for return
        local_results.append(provider_result)
    else:
        # REMOTE: upsert into geocoding_results as before (Steps 5–6 unchanged)
        ... # existing upsert code
        new_results.append(orm_row)

# Step 6: OfficialGeocoding auto-set considers both remote ORM rows and local results
```

**Key insight:** The return dict from `geocode()` may need to accommodate local results (which have no ORM row). The caller (API route) accesses `results` as ORM objects — consider returning local results as a separate key `local_results` or converting them to a lightweight dict. The CONTEXT.md says the API response shape is a downstream concern; Phase 7 only ensures the bypass happens.

### Pattern 3: GeoAlchemy2 Staging Table Migration

**What:** Use `op.create_geospatial_table` and `op.create_geospatial_index` from geoalchemy2 (via alembic_helpers) — the same pattern as `initial_schema.py`.
**When to use:** Any table with a PostGIS Geography column must use geospatial variants or autogenerate will break.

```python
# Source: alembic/versions/b98c26825b02_initial_schema.py (existing pattern)
from geoalchemy2 import Geography

def upgrade() -> None:
    op.create_geospatial_table(
        'openaddresses_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_hash', sa.String(length=64), nullable=False),
        sa.Column('street_number', sa.String(length=20), nullable=True),
        sa.Column('street_name', sa.String(length=200), nullable=True),
        sa.Column('street_suffix', sa.String(length=20), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('district', sa.String(length=100), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),  # OA "region" = state
        sa.Column('postcode', sa.String(length=20), nullable=True),
        sa.Column('location', Geography(geometry_type='POINT', srid=4326,
                                         dimension=2, spatial_index=False,
                                         from_text='ST_GeogFromText',
                                         name='geography'), nullable=True),
        sa.Column('accuracy', sa.String(length=50), nullable=True),  # OA accuracy field
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_hash', name='uq_oa_source_hash'),
    )
    op.create_geospatial_index(
        'idx_oa_points_location', 'openaddresses_points', ['location'],
        unique=False, postgresql_using='gist', postgresql_ops={}
    )
    op.create_index(
        'idx_oa_points_lookup', 'openaddresses_points',
        ['region', 'postcode', 'street_name']  # composite B-tree for address matching
    )
```

### Pattern 4: Typer CLI Command Stub with Rich Progress

**What:** Register `load-oa` and `load-nad` as `@app.command()` decorators on the existing Typer `app` in `cli/__init__.py`. Phase 7 deliverable: commands exist, accept their argument, display help text, and contain a `rich` progress placeholder.
**When to use:** CLI stubs that wire the interface without implementing data loading (loading comes in Phases 8/10).

```python
# Source: cli/__init__.py (existing pattern, extended)
from pathlib import Path
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

@app.command("load-oa")
def load_openaddresses(
    file: Path = typer.Argument(..., help="Path to OpenAddresses .geojson.gz file"),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2)."
    ),
) -> None:
    """Import an OpenAddresses .geojson.gz file into the openaddresses_points staging table."""
    # Phase 7: stub — wired up in Phase 8
    typer.echo(f"load-oa: {file} (data loading implemented in Phase 8)")
    raise typer.Exit(0)


@app.command("load-nad")
def load_nad(
    file: Path = typer.Argument(..., help="Path to NAD r21 TXT (pipe-delimited) file"),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2)."
    ),
) -> None:
    """Import a NAD r21 TXT file into the nad_points staging table via PostgreSQL COPY."""
    # Phase 7: stub — wired up in Phase 10
    typer.echo(f"load-nad: {file} (data loading implemented in Phase 10)")
    raise typer.Exit(0)
```

### ORM Models for Staging Tables

**What:** Create SQLAlchemy ORM models for `openaddresses_points` and `nad_points`. These are NOT registered with `Base.metadata` in a way that Alembic autogenerate picks them up — the migration is hand-written. However, providing ORM models ensures later phases (8, 10) can query them via SQLAlchemy ORM.

```python
# src/civpulse_geo/models/openaddresses.py
from geoalchemy2.types import Geography
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from civpulse_geo.models.base import Base, TimestampMixin

class OpenAddressesPoint(Base, TimestampMixin):
    __tablename__ = "openaddresses_points"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_oa_source_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    street_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    street_suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)  # state
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    accuracy: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

### Anti-Patterns to Avoid

- **Abstracting `is_local`:** Do NOT make `is_local` an `@abc.abstractmethod` — that forces every existing provider to add the property explicitly. A concrete default of `False` requires zero changes to existing providers.
- **Duplicating service pipeline code:** Do NOT copy the entire provider loop into two branches. Gate only the DB write statements with `if provider.is_local`. Address upsert and OfficialGeocoding are common to both paths.
- **Using `op.create_table` for geospatial tables:** Always use `op.create_geospatial_table` and `op.create_geospatial_index` when a Geography column is present. Using the plain variant causes GeoAlchemy2 autogenerate to produce broken diff-migrations later.
- **Using asyncpg in CLI:** CLI commands use `create_engine(db_url)` (psycopg2 sync) — the same pattern as `cli/__init__.py`. Never use `create_async_engine` in a CLI command.
- **Staging tables without source_hash unique constraint:** Without a unique constraint on `source_hash`, ON CONFLICT upserts cannot be performed and idempotent reloads are impossible.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PostGIS GiST index in migration | Custom `op.execute("CREATE INDEX ...")` | `op.create_geospatial_index(..., postgresql_using='gist')` | The alembic_helpers writer in env.py emits correct GeoAlchemy2-aware DDL; raw SQL bypasses helpers and can break autogenerate |
| Progress bar in CLI | Manual `print` counter loop | `rich.progress.Progress` | Already chosen by user; provides rate, ETA, spinner out of box |
| SHA-256 hash for NAD deduplication | Rolling your own | `hashlib.sha256(composite_string.encode()).hexdigest()` | Same stdlib pattern as existing `address_hash` in `normalization.py` |
| gzip decompression of OA files | subprocess call to gunzip | `gzip.open(path, 'rt')` | stdlib; already available; no subprocess needed |

**Key insight:** All infrastructure patterns (geospatial migration, sync CLI engine, upsert-on-conflict, SHA-256 hash) are established in the existing codebase. This phase is wiring, not invention.

---

## Common Pitfalls

### Pitfall 1: Alembic `spatial_index=False` is Required

**What goes wrong:** When defining `Geography(...)` inside `op.create_geospatial_table`, omitting `spatial_index=False` causes GeoAlchemy2 to try to create the GiST index inside the table DDL AND again when you call `op.create_geospatial_index`. This results in a duplicate index error or migration failure.
**Why it happens:** The `Geography` column type has a `spatial_index` parameter that defaults to `True` in some contexts — the explicit `spatial_index=False` tells GeoAlchemy2 to defer index creation to the separate `op.create_geospatial_index` call.
**How to avoid:** Copy the exact column definition from `initial_schema.py`:
  ```python
  Geography(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False,
            from_text='ST_GeogFromText', name='geography')
  ```
**Warning signs:** Migration fails with `already exists` or index creation errors.

### Pitfall 2: Cache-Hit Short-Circuit Skips Local Providers

**What goes wrong:** The current `geocoding.py` returns early at Step 3 when `address.geocoding_results` is not empty (`if not force_refresh and address.geocoding_results`). If a remote provider result is cached, any subsequent request including a local provider will hit the cache and never call the local provider at all.
**Why it happens:** The cache-hit check is binary — any cached result for the address causes a full short-circuit. Local provider results are never written to `geocoding_results`, so they never appear in `address.geocoding_results`. But the cache check doesn't know which providers were requested.
**How to avoid:** The bypass refactor must account for this. Options:
  1. When `requested_providers` contains any `is_local` providers, always run those providers even on cache hit, and merge results. (Simplest consistent with CONTEXT.md decision: "only return results from explicitly requested providers.")
  2. The cache check is only applied when ALL requested providers are remote. If any is local, skip cache entirely for that request.
  Decision: Approach 2 is cleaner. Check if any provider in the request dict is local; if so, set `force_refresh=True` implicitly or bypass the cache check gate.
**Warning signs:** `geocode` API calls with a local provider never call the provider; `cache_hit: true` returned when a local provider was requested.

### Pitfall 3: OfficialGeocoding Auto-Set With No ORM Row for Local Results

**What goes wrong:** The OfficialGeocoding auto-set in Step 6 of `geocoding.py` calls `pg_insert(OfficialGeocoding).values(geocoding_result_id=successful[0].id)`. Local provider results have no ORM row (they bypass the geocoding_results insert), so `successful[0].id` does not exist.
**Why it happens:** The existing code gathers `new_results` as `GeocodingResultORM` objects from the DB. Local results are `GeocodingResult` dataclasses from the provider schema — they have no `.id`.
**How to avoid:** OfficialGeocoding auto-set should only consider remote results (those that were written to `geocoding_results`). Local results returned from the bypass path do not create OfficialGeocoding rows — per CONTEXT.md, "local provider results ARE eligible for OfficialGeocoding auto-set" but this requires that a GeocodingResult ORM row exists. Revisit this in Phase 8 when the first local provider is implemented; Phase 7 only establishes the bypass path, and the OfficialGeocoding issue is deferred because there are no local providers yet.
**Warning signs:** `AttributeError: 'GeocodingResult' object has no attribute 'id'` when local provider is in the request.

### Pitfall 4: Alembic Model Registration and Autogenerate

**What goes wrong:** New ORM models (`OpenAddressesPoint`, `NADPoint`) imported into `models/__init__.py` will be picked up by Alembic autogenerate. If a developer runs `alembic revision --autogenerate` after Phase 7, Alembic may try to generate a migration for tables that already exist (created by the hand-written migration).
**Why it happens:** Alembic compares `Base.metadata` against the live DB schema. If the hand-written migration matches what the ORM models define exactly, autogenerate will produce a no-op. But column type mismatches (e.g., `Geography` introspection) can cause spurious diff entries.
**How to avoid:** After writing the ORM models and migration, run `alembic revision --autogenerate -m "check"` and verify the generated migration is empty (no-op). If not, reconcile the model definition with the hand-written migration SQL.
**Warning signs:** `alembic upgrade head` succeeds but subsequent `alembic revision --autogenerate` generates table creation for already-existing tables.

### Pitfall 5: `rich` Not Installed — CLI Stubs Fail at Import

**What goes wrong:** If `from rich.progress import Progress` is at module level in `cli/__init__.py` and `rich` is not installed, the entire CLI app fails to import, breaking all existing `geo-import` functionality.
**Why it happens:** Python fails all imports in the module at load time.
**How to avoid:** Add `rich` as a dependency with `uv add rich` before any code references it. Verify it is in `pyproject.toml` dependencies before writing the CLI stubs.
**Warning signs:** `ModuleNotFoundError: No module named 'rich'` when running any `geo-import` subcommand.

---

## Code Examples

Verified patterns from existing codebase:

### GeoAlchemy2 Migration with GiST Index (from initial_schema.py)
```python
# Source: alembic/versions/b98c26825b02_initial_schema.py
from geoalchemy2 import Geography

op.create_geospatial_table('admin_overrides',
    sa.Column('location', Geography(
        geometry_type='POINT', srid=4326, dimension=2,
        spatial_index=False,           # CRITICAL: defer to create_geospatial_index
        from_text='ST_GeogFromText',
        name='geography', nullable=False
    ), nullable=False),
    ...
)
op.create_geospatial_index(
    'idx_admin_overrides_location', 'admin_overrides', ['location'],
    unique=False, postgresql_using='gist', postgresql_ops={}
)
```

### Composite B-Tree Index (from initial_schema.py)
```python
# Source: alembic/versions/b98c26825b02_initial_schema.py
op.create_index(op.f('ix_addresses_address_hash'), 'addresses', ['address_hash'], unique=True)
# For composite (non-op.f prefix needed — op.f only for single-column standard names):
op.create_index('idx_oa_points_lookup', 'openaddresses_points', ['region', 'postcode', 'street_name'])
```

### Sync CLI Engine Pattern (from cli/__init__.py)
```python
# Source: src/civpulse_geo/cli/__init__.py
from sqlalchemy import create_engine, text
engine = create_engine(db_url)
with engine.connect() as conn:
    conn.execute(text("INSERT INTO ..."), {...})
    conn.commit()
```

### pg_insert Upsert Pattern (from services/geocoding.py)
```python
# Source: src/civpulse_geo/services/geocoding.py
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = (
    pg_insert(SomeModel)
    .values(...)
    .on_conflict_do_update(
        constraint="uq_constraint_name",
        set_={...},
    )
    .returning(SomeModel.id)
)
result = await db.execute(stmt)
```

### OfficialGeocoding ON CONFLICT DO NOTHING (from services/geocoding.py)
```python
# Source: src/civpulse_geo/services/geocoding.py
await db.execute(
    pg_insert(OfficialGeocoding)
    .values(address_id=address.id, geocoding_result_id=successful[0].id)
    .on_conflict_do_nothing(index_elements=["address_id"])
)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Abstract `is_local` forcing all subclasses to implement | Concrete non-abstract `@property` with default `False` | This phase | Existing providers (census, scourgify) need zero changes |
| Single service pipeline for all providers | Per-provider routing: local vs remote | This phase | Enables local providers without DB cache pollution |

**Deprecated/outdated:**
- None applicable — all stack is current project standard.

---

## Open Questions

1. **Return type of `geocode()` when local providers are included**
   - What we know: the current return dict has `results: list[GeocodingResultORM]`. Local provider results have no ORM row.
   - What's unclear: should Phase 7 change the return type to accommodate local results, or leave it for Phase 8 when the first local provider is implemented?
   - Recommendation: Phase 7 only establishes the bypass path plumbing. The service bypass should collect local results as `list[GeocodingResult]` (provider schema type) in a `local_results` key on the return dict. The API route in Phase 8 handles serialization. Do not change the API response contract in Phase 7.

2. **Single vs. dual Alembic migration file for staging tables**
   - What we know: both tables can be created in one migration; existing migrations are one concern per file.
   - What's unclear: user has no stated preference.
   - Recommendation: Create a single migration (`add_local_provider_staging_tables`) creating both `openaddresses_points` and `nad_points` — they have no FK dependencies on each other and deploying them atomically is simpler.

---

## Validation Architecture

nyquist_validation is enabled (not explicitly false in config.json).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 with pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` asyncio_mode = "auto" |
| Quick run command | `uv run pytest tests/test_providers.py tests/test_geocoding_service.py tests/test_validation_service.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | geocode() with is_local=True provider skips geocoding_results write | unit | `uv run pytest tests/test_geocoding_service.py -k "local" -x` | ❌ Wave 0 |
| PIPE-01 | validate() with is_local=True provider skips validation_results write | unit | `uv run pytest tests/test_validation_service.py -k "local" -x` | ❌ Wave 0 |
| PIPE-02 | GeocodingProvider.is_local defaults to False | unit | `uv run pytest tests/test_providers.py -k "is_local" -x` | ❌ Wave 0 |
| PIPE-02 | ValidationProvider.is_local defaults to False | unit | `uv run pytest tests/test_providers.py -k "is_local" -x` | ❌ Wave 0 |
| PIPE-03 | openaddresses_points table exists with GiST index | smoke | manual — `alembic upgrade head` + `\d openaddresses_points` in psql | n/a |
| PIPE-04 | nad_points table exists with GiST index | smoke | manual — `alembic upgrade head` + `\d nad_points` in psql | n/a |
| PIPE-05 | load-oa command is registered and displays help text | unit | `uv run pytest tests/test_load_oa_cli.py -x` | ❌ Wave 0 |
| PIPE-06 | load-nad command is registered and displays help text | unit | `uv run pytest tests/test_load_nad_cli.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_providers.py tests/test_geocoding_service.py tests/test_validation_service.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_providers.py` — extend existing file: add `test_is_local_defaults_false_geocoding` and `test_is_local_defaults_false_validation` — covers PIPE-02
- [ ] `tests/test_geocoding_service.py` — extend existing file: add `test_local_provider_bypasses_geocoding_results_write` — covers PIPE-01 (geocoding path)
- [ ] `tests/test_validation_service.py` — extend existing file: add `test_local_provider_bypasses_validation_results_write` — covers PIPE-01 (validation path)
- [ ] `tests/test_load_oa_cli.py` — new file: CLI help text and command registration test — covers PIPE-05
- [ ] `tests/test_load_nad_cli.py` — new file: CLI help text and command registration test — covers PIPE-06

All tests use existing mock patterns from `conftest.py` (AsyncMock session, mock providers). No new fixtures needed for Phase 7 unit tests.

---

## Sources

### Primary (HIGH confidence)
- Project source code: `src/civpulse_geo/providers/base.py` — ABC structure for is_local extension
- Project source code: `src/civpulse_geo/services/geocoding.py` — pipeline steps 1-7, bypass insertion point
- Project source code: `src/civpulse_geo/services/validation.py` — pipeline steps 1-6, bypass insertion point
- Project source code: `alembic/versions/b98c26825b02_initial_schema.py` — op.create_geospatial_table + op.create_geospatial_index pattern with spatial_index=False
- Project source code: `alembic/env.py` — alembic_helpers wiring (include_object, writer, render_item)
- Project source code: `src/civpulse_geo/cli/__init__.py` — sync engine + typer command pattern
- Project source code: `pyproject.toml` — confirmed dependencies (alembic 1.18.4, geoalchemy2 0.18.4, typer 0.24.1, psycopg2-binary 2.9.11); `rich` not yet in dependencies

### Secondary (MEDIUM confidence)
- GeoAlchemy2 migration documentation pattern (spatial_index=False required) — consistent with observed pattern in existing migration file
- Python ABC documentation — concrete non-abstract properties alongside abstract methods is standard Python behavior (HIGH confidence, foundational language feature)

### Tertiary (LOW confidence)
- None — all findings verified against project source code

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed in project except `rich`; versions verified from pyproject.toml
- Architecture: HIGH — all patterns exist verbatim in project source; no new patterns introduced
- Pitfalls: HIGH — pitfalls derived from reading actual service code and migration files; cache-hit short-circuit is a direct code observation

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable patterns; only risk is if geoalchemy2 or alembic releases a breaking version in the interim)
