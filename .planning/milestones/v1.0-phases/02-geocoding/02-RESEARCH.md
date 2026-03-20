# Phase 2: Geocoding - Research

**Researched:** 2026-03-19
**Domain:** Geocoding API — Census Geocoder provider, async HTTP, cache-first service layer, admin override workflow
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GEO-01 | API can forward geocode a single address to lat/lng with location type classification | Census Geocoder adapter returning GeocodingResult; POST /geocode endpoint with Pydantic response model |
| GEO-02 | API stores geocode results from each external provider as separate records linked to address | `geocoding_results` table with (address_id, provider_name) unique constraint already in schema |
| GEO-03 | API checks local cache before calling external providers; returns cached result on hit | SHA-256 `address_hash` index on `addresses` table; check geocoding_results before calling provider |
| GEO-04 | API returns confidence/accuracy score on each geocode result | `confidence` Float column on geocoding_results; Census returns match percentage mapped to 0.0–1.0 |
| GEO-05 | API response indicates whether result came from cache or live service call | `cache_hit: bool` field in Pydantic response model; set by service layer |
| GEO-06 | Admin can set the "official" geocode record to match any provider's result | PUT /geocode/{address_hash}/official endpoint; updates `official_geocoding` table FK |
| GEO-07 | Admin can set a custom lat/lng as official (not from any provider) | POST custom coordinate to create synthetic GeocodingResult + set as official; OR use `admin_overrides` table directly |
| GEO-08 | API provides a manual cache refresh endpoint to re-query all providers | POST /geocode/{address_hash}/refresh; deletes existing geocoding_results, re-queries all providers |
| GEO-09 | API can return geocode results from a specific provider for admin comparison | GET /geocode/{address_hash}/providers/{provider_name} endpoint |
</phase_requirements>

---

## Summary

Phase 2 builds the live geocoding workflow on top of the Phase 1 foundation. The data model, plugin contract, canonical key strategy, and database schema are already in place — the phase is exclusively about implementing behavior: the Census Geocoder provider adapter, the cache-first service layer, and the admin override/refresh endpoints.

The Census Geocoder API (geocoding.geo.census.gov) is free, requires no API key, and is already designated as the first provider per the pre-phase decision. Its JSON response schema is confirmed via live API calls: coordinates are under `result.addressMatches[0].coordinates` with `x` = longitude and `y` = latitude. The API uses range interpolation (TIGER/Line address ranges), so all successful matches map to `LocationType.RANGE_INTERPOLATED` — the `ROOFTOP` level of precision does not exist in this API. An empty `addressMatches` array means no match.

The service layer pattern is straightforward: normalize the incoming address with the existing `canonical_key()` function, look up the `address_hash` in the database, return cached results if they exist (with `cache_hit=True`), or call all registered providers, persist results, and return (with `cache_hit=False`). Admin override and cache-refresh endpoints sit on top of the same address lookup plumbing. All database access uses the existing async SQLAlchemy 2.0 / asyncpg pattern already established in Phase 1.

**Primary recommendation:** Implement a `GeocodingService` class that encapsulates the cache-first lookup logic, inject it via FastAPI `Depends`, and build a `CensusGeocodingProvider` as the single concrete provider for this phase. Keep the httpx `AsyncClient` as a lifespan-managed singleton stored on `app.state`.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version (installed) | Purpose | Why Standard |
|---------|-------------------|---------|--------------|
| httpx | 0.28.1 | Async HTTP calls to Census Geocoder | Already a dev dependency; async-native; connection pooling via lifespan pattern |
| sqlalchemy | 2.0.48 | Async ORM for cache lookups and writes | Already in use; `postgresql+asyncpg` engine established in Phase 1 |
| fastapi | 0.135.1 | API framework and dependency injection | Already in use; established in Phase 1 |
| pydantic | 2.12.5 | Request/response schema validation | Already in use via FastAPI; Pydantic v2 |
| geoalchemy2 | 0.18.4 | PostGIS Geography column inserts | Already in models; needed for writing `location` column |

### No New Dependencies Needed

Phase 2 requires no new packages. httpx is already a dev dependency but needs to be moved to runtime dependencies since the provider will use it in production. All other libraries are present.

**One dependency change required:**
```bash
# Move httpx from dev to runtime (it's used by the Census provider at runtime)
uv add httpx
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx.AsyncClient | aiohttp | httpx is already installed; both fine for this use case |
| Census Geocoder (free, no key) | Google Maps Platform | Google ToS caching clause flagged as blocker in STATE.md — defer |
| Inline service logic in router | Repository + Service classes | Service class makes unit testing easier; recommended for this codebase |

---

## Architecture Patterns

### Recommended Project Structure

```
src/civpulse_geo/
├── api/
│   ├── health.py            # existing
│   └── geocoding.py         # NEW: geocoding router (POST /geocode, admin endpoints)
├── providers/
│   ├── base.py              # existing: ABC contracts
│   ├── schemas.py           # existing: GeocodingResult dataclass
│   ├── registry.py          # existing: load_providers()
│   ├── exceptions.py        # existing: ProviderError hierarchy
│   ├── __init__.py          # existing
│   └── census.py            # NEW: CensusGeocodingProvider
├── services/
│   └── geocoding.py         # NEW: GeocodingService (cache-first logic)
├── schemas/
│   └── geocoding.py         # NEW: Pydantic request/response models for API
├── models/                  # existing: ORM models
├── config.py                # existing (add CENSUS_GEOCODER_TIMEOUT if desired)
├── database.py              # existing
├── main.py                  # update: add census provider to load_providers, init httpx client
└── normalization.py         # existing
```

### Pattern 1: Lifespan-Managed httpx.AsyncClient

The Census provider needs a shared async HTTP client. Store it on `app.state` using the existing lifespan pattern.

**What:** Single `httpx.AsyncClient` instance shared across all requests.
**When to use:** Any provider making outbound HTTP calls. Never create `AsyncClient` inside a request handler or inside a loop.

```python
# src/civpulse_geo/main.py — updated lifespan
# Source: https://www.python-httpx.org/async/
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from civpulse_geo.providers.census import CensusGeocodingProvider
from civpulse_geo.providers.registry import load_providers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Single shared client — never instantiate inside a request
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    app.state.providers = load_providers({"census": CensusGeocodingProvider})
    yield
    await app.state.http_client.aclose()
```

### Pattern 2: CensusGeocodingProvider Concrete Implementation

**Census Geocoder API confirmed details (live API verified 2026-03-19):**

- **Endpoint:** `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`
- **Parameters:** `address=<freeform>`, `benchmark=Public_AR_Current`, `format=json`
- **No API key required**
- **Benchmarks available:** Public_AR_Current (id=4, default), Public_AR_ACS2025 (id=8), Public_AR_Census2020 (id=2020)
- **Response on match:** `result.addressMatches[0].coordinates.x` = longitude, `.y` = latitude
- **Response on no match:** `result.addressMatches` is an empty list `[]`
- **Location type:** Always `RANGE_INTERPOLATED` — Census uses TIGER/Line range interpolation; it does NOT return rooftop precision
- **Confidence:** The API does not return a numeric confidence score directly. Use 0.8 as a fixed confidence for any successful match (range-interpolated is moderately reliable). Use 0.0 for no-match.
- **Rate limit:** Not formally documented. Free public service. Observed to be reliable for reasonable request rates; can be slow under heavy load. Timeout of 10 seconds is appropriate.

```python
# src/civpulse_geo/providers/census.py
import httpx
from civpulse_geo.providers.base import GeocodingProvider
from civpulse_geo.providers.schemas import GeocodingResult
from civpulse_geo.providers.exceptions import ProviderNetworkError
from civpulse_geo.models.enums import LocationType

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CENSUS_BENCHMARK = "Public_AR_Current"
# Census uses range interpolation — never rooftop
CENSUS_LOCATION_TYPE = LocationType.RANGE_INTERPOLATED.value
CENSUS_CONFIDENCE = 0.8  # fixed: range-interpolated is moderately confident

class CensusGeocodingProvider(GeocodingProvider):
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        # Optional injection for testing; production uses app.state.http_client
        self._client = http_client

    @property
    def provider_name(self) -> str:
        return "census"

    async def geocode(self, address: str, http_client: httpx.AsyncClient | None = None) -> GeocodingResult:
        client = http_client or self._client
        try:
            resp = await client.get(
                CENSUS_GEOCODER_URL,
                params={"address": address, "benchmark": CENSUS_BENCHMARK, "format": "json"},
            )
            resp.raise_for_status()
        except httpx.RequestError as exc:
            raise ProviderNetworkError(f"Census geocoder unreachable: {exc}") from exc

        data = resp.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            # No match — return result with null coordinates
            return GeocodingResult(
                lat=0.0, lng=0.0,
                location_type="NO_MATCH",
                confidence=0.0,
                raw_response=data,
                provider_name=self.provider_name,
            )
        match = matches[0]
        coords = match["coordinates"]
        return GeocodingResult(
            lat=coords["y"],   # y = latitude
            lng=coords["x"],   # x = longitude
            location_type=CENSUS_LOCATION_TYPE,
            confidence=CENSUS_CONFIDENCE,
            raw_response=data,
            provider_name=self.provider_name,
        )

    async def batch_geocode(self, addresses: list[str], http_client: httpx.AsyncClient | None = None) -> list[GeocodingResult]:
        # Serial fallback — Census batch API requires file upload (multipart), not worth the complexity for v1
        return [await self.geocode(a, http_client=http_client) for a in addresses]
```

### Pattern 3: Cache-First Service Layer

**What:** `GeocodingService` encapsulates the lookup-or-fetch logic. Router delegates to it.
**When to use:** Any time a geocode request arrives.

```python
# src/civpulse_geo/services/geocoding.py (structure only)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from civpulse_geo.normalization import canonical_key
from civpulse_geo.models.address import Address
from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

class GeocodingService:
    async def geocode(
        self,
        freeform: str,
        db: AsyncSession,
        providers: dict,
        http_client,
        force_refresh: bool = False,
    ) -> dict:
        # 1. Normalize and hash
        normalized, address_hash = canonical_key(freeform)

        # 2. Look up address record (create if missing)
        stmt = select(Address).where(Address.address_hash == address_hash)
        address = (await db.execute(stmt)).scalar_one_or_none()
        if address is None:
            address = Address(original_input=freeform, normalized_address=normalized, address_hash=address_hash, ...)
            db.add(address)
            await db.flush()  # get address.id without committing

        # 3. Cache check (unless force_refresh)
        if not force_refresh:
            stmt = select(GeocodingResultORM).where(GeocodingResultORM.address_id == address.id)
            cached = (await db.execute(stmt)).scalars().all()
            if cached:
                await db.commit()
                return {"results": cached, "cache_hit": True}

        # 4. Call providers
        results = []
        for name, provider in providers.items():
            if hasattr(provider, "geocode"):
                geo_result = await provider.geocode(normalized, http_client=http_client)
                # Upsert into geocoding_results
                ...
                results.append(orm_result)

        await db.commit()
        return {"results": results, "cache_hit": False}
```

### Pattern 4: Database Upsert for Provider Results

Use PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` to handle the cache-refresh case atomically.

```python
# Source: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

# Build WKT for PostGIS geography column
point_wkt = f"SRID=4326;POINT({geo_result.lng} {geo_result.lat})"

stmt = pg_insert(GeocodingResultORM).values(
    address_id=address.id,
    provider_name=geo_result.provider_name,
    location=point_wkt,
    latitude=geo_result.lat,
    longitude=geo_result.lng,
    location_type=geo_result.location_type,
    confidence=geo_result.confidence,
    raw_response=geo_result.raw_response,
)
stmt = stmt.on_conflict_do_update(
    constraint="uq_geocoding_address_provider",
    set_={
        "latitude": stmt.excluded.latitude,
        "longitude": stmt.excluded.longitude,
        "location_type": stmt.excluded.location_type,
        "confidence": stmt.excluded.confidence,
        "raw_response": stmt.excluded.raw_response,
        "location": stmt.excluded.location,
    }
)
await db.execute(stmt)
```

### Pattern 5: Pydantic Response Schema

The geocode endpoint response must include `lat`, `lng`, `location_type`, `confidence`, `cache_hit`, and `provider_name`.

```python
# src/civpulse_geo/schemas/geocoding.py
from pydantic import BaseModel

class GeocodeRequest(BaseModel):
    address: str

class GeocodeProviderResult(BaseModel):
    provider_name: str
    latitude: float | None
    longitude: float | None
    location_type: str | None
    confidence: float | None

class GeocodeResponse(BaseModel):
    address_hash: str
    normalized_address: str
    cache_hit: bool
    results: list[GeocodeProviderResult]
    official: GeocodeProviderResult | None = None
```

### Pattern 6: Admin Override — Two Paths

GEO-06 and GEO-07 cover setting the official geocode record. Two distinct paths:

- **GEO-06 (point to existing provider result):** Update `official_geocoding.geocoding_result_id` to an existing `geocoding_results.id` for that address.
- **GEO-07 (custom coordinate):** Insert a new `geocoding_results` row with `provider_name="custom"` (or `"admin_override"`), then set `official_geocoding` to point at it. This reuses the existing schema cleanly rather than requiring a separate `admin_overrides` table record.

**Note:** The `admin_overrides` table exists in the schema (with its own `location` column) but GEO-07 can be satisfied more simply by creating a synthetic provider result. The `admin_overrides` table design is for a direct-coordinate override that bypasses `geocoding_results` entirely. Either approach works — choose based on whether admin overrides need their own audit trail separate from provider results.

### Anti-Patterns to Avoid

- **Creating httpx.AsyncClient per request:** Destroys connection pool benefits; always use the lifespan singleton.
- **Lazy-loading SQLAlchemy relationships in async context:** Will raise `MissingGreenlet`. Use `selectinload()` or `joinedload()` in the select statement.
- **Calling `await db.refresh(obj)` after commit with `expire_on_commit=True`:** The existing `AsyncSessionLocal` already has `expire_on_commit=False` — attributes are accessible after commit without a reload.
- **Using `db.add()` + `db.commit()` when you need upsert:** Use `pg_insert().on_conflict_do_update()` for cache refresh to avoid duplicate key errors.
- **Calling external provider with original un-normalized input:** Always pass the `normalized_address` to providers for consistent cache keys and cleaner provider responses.
- **Creating a new `Address` record without parsing components:** Use `parse_address_components()` from `normalization.py` to populate street/city/state/zip fields on the `Address` ORM row.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Address normalization | Custom regex parser | `canonical_key()` in normalization.py | Already built and tested in Phase 1 |
| Async HTTP to Census | `urllib.request` or `requests` in threadpool | `httpx.AsyncClient` (already installed) | Non-blocking; connection pooling |
| PostgreSQL upsert | SELECT + INSERT in two queries | `pg_insert().on_conflict_do_update()` | Race-condition-safe; atomic; single round-trip |
| PostGIS point insert | WKB binary construction | `"SRID=4326;POINT(lng lat)"` EWKT string | GeoAlchemy2 accepts EWKT strings directly; no Shapely needed |
| Async ORM lazy load | `obj.relationship` access after session close | `selectinload()` in the query | Lazy load raises `MissingGreenlet` in async context |
| Provider ABC | Duck typing / manual inspection | `GeocodingProvider` ABC from providers/base.py | Already enforces contract at startup; reuse it |

**Key insight:** Phase 1 built all the plumbing specifically to make Phase 2 straightforward. The normalization, hashing, ORM models, plugin registry, and database session are all proven and tested. Phase 2 is exclusively about wiring behavior through that infrastructure.

---

## Common Pitfalls

### Pitfall 1: Census Geocoder Returns x=longitude, y=latitude (not the other way)

**What goes wrong:** Coordinates are stored swapped — addresses map to the ocean or wrong continent.
**Why it happens:** TIGER/Line convention uses `x` for the easting (longitude) and `y` for the northing (latitude), which is the mathematical Cartesian convention — opposite of the colloquial "lat/lng" order.
**How to avoid:** `lat = coords["y"]`, `lng = coords["x"]` — always check the axis names from the raw response.
**Warning signs:** Coordinates with `lat` near ±90 but unexpectedly large magnitude, or coordinates that plot to wrong hemisphere.

### Pitfall 2: Census "No Match" Returns Empty addressMatches, Not an Error

**What goes wrong:** Code raises `KeyError` or `IndexError` trying to access `addressMatches[0]`.
**Why it happens:** An unsuccessful geocode returns HTTP 200 with `"addressMatches": []` — not a 4xx error.
**How to avoid:** Always check `if not matches` before accessing `matches[0]`.
**Warning signs:** `IndexError: list index out of range` in provider code.

### Pitfall 3: Async SQLAlchemy Lazy Loading (MissingGreenlet)

**What goes wrong:** `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called` when accessing a relationship attribute after the `await`.
**Why it happens:** SQLAlchemy async sessions do not support implicit I/O. Accessing `address.geocoding_results` without eager loading triggers a lazy load that has no greenlet context.
**How to avoid:** Use `selectinload()` in every query where you need related objects: `select(Address).options(selectinload(Address.geocoding_results)).where(...)`.
**Warning signs:** The error message mentions `greenlet_spawn`; it only appears at runtime, not during static analysis.

### Pitfall 4: httpx AsyncClient Created Inside Request Handler

**What goes wrong:** Memory leak and performance degradation — each request creates a new TCP connection pool.
**Why it happens:** Developers follow synchronous patterns (`with httpx.Client() as c:`) without realizing the scoping cost in async.
**How to avoid:** Create `AsyncClient` once in the lifespan context manager, attach to `app.state`, pass it into the service.
**Warning signs:** Connection count grows over time; "too many open files" errors under load.

### Pitfall 5: Writing PostGIS Geography Without SRID Prefix

**What goes wrong:** `ProgrammingError: Geometry SRID (0) does not match column SRID (4326)`.
**Why it happens:** Inserting a WKT string without the `SRID=4326;` prefix creates a geometry with SRID=0, which PostGIS rejects for the geography column.
**How to avoid:** Always use EWKT format: `f"SRID=4326;POINT({lng} {lat})"` — note **lng first, then lat** in WKT/PostGIS convention.
**Warning signs:** `SRID` mismatch error from PostgreSQL; coordinates in wrong column.

### Pitfall 6: Cache Refresh Race Condition Without Upsert

**What goes wrong:** Two simultaneous refresh requests both succeed, creating duplicate `geocoding_results` rows and violating the `uq_geocoding_address_provider` unique constraint.
**Why it happens:** A naive delete-then-insert pattern has a window between the delete and insert where another request can observe the absence and also begin inserting.
**How to avoid:** Use `ON CONFLICT DO UPDATE` for inserts so concurrent refreshes are idempotent. Alternatively, use `SELECT FOR UPDATE` on the address row to serialize concurrent refreshes for the same address.
**Warning signs:** `IntegrityError: UniqueViolation` on the `uq_geocoding_address_provider` constraint under concurrent load.

### Pitfall 7: Passing Original Input to Provider Instead of Normalized Form

**What goes wrong:** Cache miss on semantically identical addresses ("123 Main St" vs "123 Main Street") because the raw input was passed to the provider, causing mismatched stored keys.
**Why it happens:** Developers forget to use `canonical_key()` output when calling the provider.
**How to avoid:** Always geocode the `normalized_address` string, not the `original_input`. The `canonical_key()` function returns `(normalized, hash)` — use the `normalized` string for all provider calls.

---

## Code Examples

### Census Geocoder — Live API Response (verified 2026-03-19)

```json
// GET https://geocoding.geo.census.gov/geocoder/locations/onelineaddress
//     ?address=4600+Silver+Hill+Rd+Washington+DC+20233
//     &benchmark=Public_AR_Current&format=json
{
  "result": {
    "input": { "address": {"address": "4600 Silver Hill Rd Washington DC 20233"}, ... },
    "addressMatches": [
      {
        "tigerLine": {"side": "L", "tigerLineId": "657091557"},
        "coordinates": {"x": -76.928365658124, "y": 38.845053106269},
        "addressComponents": {
          "zip": "20233", "streetName": "SILVER HILL", "preType": "",
          "city": "WASHINGTON", "preDirection": "", "suffixDirection": "",
          "fromAddress": "4600", "state": "DC", "suffixType": "RD",
          "toAddress": "4700", "suffixQualifier": "", "preQualifier": ""
        },
        "matchedAddress": "4600 SILVER HILL RD, WASHINGTON, DC, 20233"
      }
    ]
  }
}
// No match: "addressMatches": []
```

### SQLAlchemy Async: Address Cache Lookup

```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy import select
from sqlalchemy.orm import selectinload

async def get_address_by_hash(db: AsyncSession, address_hash: str) -> Address | None:
    stmt = (
        select(Address)
        .options(selectinload(Address.geocoding_results))
        .where(Address.address_hash == address_hash)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
```

### SQLAlchemy Async: Upsert Geocoding Result

```python
# Source: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def upsert_geocoding_result(db: AsyncSession, address_id: int, result: GeocodingResult):
    point_ewkt = f"SRID=4326;POINT({result.lng} {result.lat})"  # lng first!
    stmt = pg_insert(GeocodingResultORM).values(
        address_id=address_id,
        provider_name=result.provider_name,
        location=point_ewkt,
        latitude=result.lat,
        longitude=result.lng,
        location_type=result.location_type,
        confidence=result.confidence,
        raw_response=result.raw_response,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_geocoding_address_provider",
        set_={k: stmt.excluded[k] for k in
              ["latitude", "longitude", "location_type", "confidence", "raw_response", "location"]},
    )
    await db.execute(stmt)
```

### FastAPI Router Pattern (consistent with existing health.py)

```python
# src/civpulse_geo/api/geocoding.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from civpulse_geo.database import get_db
from civpulse_geo.schemas.geocoding import GeocodeRequest, GeocodeResponse

router = APIRouter(prefix="/geocode", tags=["geocoding"])

@router.post("", response_model=GeocodeResponse)
async def geocode(
    body: GeocodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = GeocodingService()
    return await service.geocode(
        freeform=body.address,
        db=db,
        providers=request.app.state.providers,
        http_client=request.app.state.http_client,
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `asynccontextmanager lifespan` | FastAPI 0.93+ | Phase 1 already uses lifespan; continue this pattern |
| Pydantic v1 `.schema()` | Pydantic v2 `.model_json_schema()` | Pydantic v2 | Project already on Pydantic 2.12.5; use v2 syntax |
| `session.query()` style | `select()` + `session.execute()` | SQLAlchemy 2.0 | Phase 1 already on SA 2.0 style |
| pytest-asyncio `@pytest.mark.asyncio` | `asyncio_mode = "auto"` in config | pytest-asyncio 0.21+ | Already configured in pyproject.toml |

**Deprecated/outdated in this project's context:**
- Google Maps Platform: Flagged in STATE.md as blocked pending ToS/legal review — do not implement in Phase 2.
- `admin_overrides` table direct use for GEO-07: Consider whether a synthetic provider result (`provider_name="custom"`) is cleaner. The `admin_overrides` table exists but introduces a second query path.

---

## Open Questions

1. **GEO-07: admin_overrides table vs synthetic provider result**
   - What we know: Both `admin_overrides` table (with its own `location` column, `reason` text) and a synthetic `GeocodingResult` row with `provider_name="custom"` would satisfy the requirement.
   - What's unclear: Does the admin override need its own audit trail independent of provider results? The `admin_overrides` table has a `reason` field; a synthetic provider result does not.
   - Recommendation: Use synthetic provider result (`provider_name="admin_override"`) inserted into `geocoding_results` for simplicity, and set it as official via `official_geocoding`. This keeps the single-path query logic. The `admin_overrides` table can be preserved for potential future audit use. Flag this as a planner decision.

2. **Census Geocoder reliability in production**
   - What we know: Free, no API key, no documented rate limit. Can be slow or unavailable during Census Bureau maintenance windows. Reliability issues are known (multiple third-party articles reference it going down).
   - What's unclear: Whether a timeout-and-retry strategy is needed for Phase 2 vs. Phase 4 hardening.
   - Recommendation: Add a 10-second timeout on the httpx client. Do not add retry logic in Phase 2 — if the provider fails, return a 503 with a clear error message. Retry/circuit-breaker is Phase 4 hardening scope.

3. **OfficialGeocoding row creation: auto vs. explicit**
   - What we know: `official_geocoding` table has a unique constraint on `address_id`. There's no row created automatically on first geocode.
   - What's unclear: Should the geocode endpoint automatically set the first successful result as the official record, or leave it unset until an admin explicitly sets it?
   - Recommendation: Auto-set the first non-empty result as the official record on initial geocode (INSERT OR IGNORE pattern). This satisfies GEO-01 returning the "official" result on the first call without requiring a separate admin action. GEO-06/GEO-07 then override it.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `uv run python -m pytest tests/ -x -q` |
| Full suite command | `uv run python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEO-01 | POST /geocode returns lat/lng, location_type, confidence, cache_hit | integration (mock provider) | `uv run python -m pytest tests/test_geocoding_api.py -x` | ❌ Wave 0 |
| GEO-02 | Provider results stored as separate records per provider | unit (service) | `uv run python -m pytest tests/test_geocoding_service.py::test_stores_provider_results -x` | ❌ Wave 0 |
| GEO-03 | Cache hit on second geocode request | unit (service) | `uv run python -m pytest tests/test_geocoding_service.py::test_cache_hit -x` | ❌ Wave 0 |
| GEO-04 | Confidence score present on each result | unit (provider) | `uv run python -m pytest tests/test_census_provider.py::test_confidence -x` | ❌ Wave 0 |
| GEO-05 | cache_hit flag correct in response | unit (service) | `uv run python -m pytest tests/test_geocoding_service.py::test_cache_hit_flag -x` | ❌ Wave 0 |
| GEO-06 | Admin set official to provider result | integration (mock db) | `uv run python -m pytest tests/test_geocoding_api.py::test_set_official -x` | ❌ Wave 0 |
| GEO-07 | Admin set custom coordinate as official | integration (mock db) | `uv run python -m pytest tests/test_geocoding_api.py::test_set_custom_coordinate -x` | ❌ Wave 0 |
| GEO-08 | Cache refresh re-queries providers | unit (service) | `uv run python -m pytest tests/test_geocoding_service.py::test_force_refresh -x` | ❌ Wave 0 |
| GEO-09 | Get results for specific provider | integration (mock db) | `uv run python -m pytest tests/test_geocoding_api.py::test_get_by_provider -x` | ❌ Wave 0 |
| Census adapter | Census JSON parsed correctly, x=lng y=lat | unit | `uv run python -m pytest tests/test_census_provider.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run python -m pytest tests/ -x -q`
- **Per wave merge:** `uv run python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_census_provider.py` — covers GEO-01, GEO-04; Census adapter unit tests with httpx mock
- [ ] `tests/test_geocoding_service.py` — covers GEO-02, GEO-03, GEO-05, GEO-08; service layer with mock DB
- [ ] `tests/test_geocoding_api.py` — covers GEO-01, GEO-06, GEO-07, GEO-09; FastAPI endpoint integration tests with mock providers and mock DB
- [ ] `src/civpulse_geo/schemas/` directory — does not exist, needed before test imports can resolve

---

## Sources

### Primary (HIGH confidence)

- Live Census Geocoder API call — `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=4600+Silver+Hill+Rd+Washington+DC+20233&benchmark=Public_AR_Current&format=json` — response schema confirmed (x=lng, y=lat, addressMatches structure)
- Live Census Benchmarks API — `https://geocoding.geo.census.gov/geocoder/benchmarks` — confirmed Public_AR_Current is id=4 and default
- SQLAlchemy 2.0 asyncio docs — `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html` — scalar_one_or_none, selectinload patterns
- SQLAlchemy PostgreSQL insert docs — `https://docs.sqlalchemy.org/en/20/dialects/postgresql.html` — ON CONFLICT DO UPDATE pattern
- httpx async docs — `https://www.python-httpx.org/async/` — lifespan-managed AsyncClient pattern
- Project source code — Phase 1 ORM models, normalization.py, providers/base.py, conftest.py — all examined directly

### Secondary (MEDIUM confidence)

- Census Geocoder API PDF — `https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.pdf` — benchmark/parameter structure; rate limit not documented (confirmed absence)
- WebSearch: Census Geocoder reliability — multiple sources indicate Census API can experience downtime; no formal SLA published

### Tertiary (LOW confidence)

- Fixed confidence value of 0.8 for Census successful match — based on Census documentation describing range interpolation as moderate precision; no official confidence scoring exists in the Census API response

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified from installed versions; no new dependencies
- Architecture: HIGH — patterns verified against SQLAlchemy async docs, httpx docs, existing Phase 1 code
- Census API schema: HIGH — live API calls made and response structure confirmed
- Census confidence score: LOW — API does not return one; 0.8 is a reasonable constant but is a judgment call
- Pitfalls: HIGH — most derived from SQLAlchemy async documentation and verified by examining existing code patterns

**Research date:** 2026-03-19
**Valid until:** 2026-06-19 (stable stack — SQLAlchemy, httpx, Census API are low-churn; Census API schema is stable)
