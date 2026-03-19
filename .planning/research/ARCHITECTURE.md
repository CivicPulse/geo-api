# Architecture Patterns

**Domain:** Geocoding / Address Validation Caching API
**Researched:** 2026-03-19
**Confidence:** HIGH (well-established patterns; training data + direct domain knowledge)

---

## Recommended Architecture

### System Overview

```
Callers (run-api, vote-api, ...)
        |
        v
  [FastAPI Layer]
   - REST endpoints
   - Input parsing / normalization
   - Batch fan-out
        |
        v
  [Service Layer]
   - CacheService (check DB first)
   - GeocodingOrchestrator
   - ValidationOrchestrator
        |           |
        v           v
  [Provider Layer]  [Admin Layer]
   - ProviderRegistry  - OfficialRecordService
   - GoogleProvider    - AdminOverrideService
   - USPSProvider
   - CensusProvider
   - AmazonProvider
   - GeoapifyProvider
        |
        v
  [Persistence Layer]
   - PostgreSQL + PostGIS
   - AddressRepository
   - GeocodingResultRepository
   - ValidationResultRepository
   - OfficialGeocodingRepository
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **FastAPI Layer** | HTTP transport, request validation (Pydantic), routing, batch splitting, response shaping | Service Layer only — never calls providers or DB directly |
| **CacheService** | Check DB before calling any external service; coordinate cache-miss flow | AddressRepository, Orchestrators |
| **GeocodingOrchestrator** | Decide which providers to call, collect results, persist, return | ProviderRegistry, GeocodingResultRepository, OfficialGeocodingRepository |
| **ValidationOrchestrator** | Normalize raw input, call validation providers, rank suggestions, persist | ProviderRegistry, ValidationResultRepository |
| **ProviderRegistry** | Enumerate registered providers; route calls; handle per-provider errors without failing the whole request | Individual Providers |
| **Provider (abstract base)** | Define contract: `geocode(address)`, `validate(address)` | External HTTP services only |
| **Concrete Providers** | Implement provider contract for one external service | ProviderRegistry (called by), External APIs |
| **OfficialRecordService** | Maintain the single "official" geocoded point per address; apply or clear admin overrides | OfficialGeocodingRepository |
| **AdminOverrideService** | Accept admin-supplied lat/lon or selection of an existing provider result; write to official record | OfficialRecordService |
| **AddressRepository** | CRUD for canonical address records; normalize input to a lookup key | PostgreSQL |
| **GeocodingResultRepository** | Store/fetch one row per (address, provider) geocoding result | PostgreSQL + PostGIS |
| **ValidationResultRepository** | Store/fetch one row per (address, provider) validation result + suggestion list | PostgreSQL |
| **OfficialGeocodingRepository** | Store the single official point (or null) per address; track whether it is admin-set or system-derived | PostgreSQL + PostGIS |

---

## Data Flow

### Geocoding Request (single address)

```
1. FastAPI receives POST /geocode {address_input}
2. Normalize input → canonical address key (lowercase, stripped)
3. CacheService: lookup address by canonical key
   a. MISS → insert address record, proceed to step 4
   b. HIT  → check if geocoding results exist for address
      - Results exist → return cached results + official record
      - No results    → proceed to step 4
4. GeocodingOrchestrator: call all enabled providers via ProviderRegistry
   - Each provider call is independent; failures logged, not fatal
   - Results persisted to geocoding_results (one row per provider)
5. OfficialRecordService: if no official record exists, derive one
   (e.g., first successful provider result, or highest-confidence result)
6. Return: { address_id, canonical, provider_results[], official_result }
```

### Address Validation Request (single address)

```
1. FastAPI receives POST /validate {raw_input} (freeform or structured)
2. Parse to structured fields (street, city, state, zip) where possible
3. CacheService: lookup address
   - HIT with validation results → return cached suggestions
   - MISS → proceed
4. ValidationOrchestrator: call USPS + configured validation providers
5. Collect suggestions (each provider may return multiple ranked results)
6. Persist suggestions to validation_results; store best-match as canonical
7. Return: { suggestions: [{standardized, confidence, source}, ...] }
```

### Batch Flow

```
POST /geocode/batch [{address_input}, ...]
1. FastAPI splits into individual address inputs
2. For each: run cache check (synchronous DB lookup is fast)
3. Cache misses collected → fan out to providers (asyncio.gather)
4. Results assembled in original input order
5. Return array matching input order
```

### Admin Override Flow

```
PATCH /addresses/{address_id}/official
1. Admin supplies { lat, lon } OR { provider_result_id }
2. AdminOverrideService validates input
3. OfficialRecordService: upsert official_geocoding row
   - Sets is_admin_override = true
   - Stores override source and value
4. Return updated official record
```

---

## Data Model

### Core Tables

```sql
-- Canonical address identity
addresses (
  id              UUID PRIMARY KEY,
  raw_input       TEXT NOT NULL,          -- original string or serialized struct
  canonical_key   TEXT NOT NULL UNIQUE,   -- normalized lookup key
  line1           TEXT,
  line2           TEXT,
  city            TEXT,
  state           CHAR(2),
  zip             TEXT,
  zip4            TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)

-- One row per (address, provider) geocoding attempt
geocoding_results (
  id              UUID PRIMARY KEY,
  address_id      UUID NOT NULL REFERENCES addresses(id),
  provider        TEXT NOT NULL,          -- 'google', 'census', 'amazon', etc.
  lat             NUMERIC(10,7),
  lon             NUMERIC(10,7),
  geom            GEOGRAPHY(POINT, 4326), -- PostGIS column; derived from lat/lon
  accuracy        TEXT,                   -- provider-specific accuracy tier
  match_type      TEXT,                   -- provider-specific (ROOFTOP, RANGE, etc.)
  raw_response    JSONB,                  -- full provider payload preserved
  fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(address_id, provider)
)

-- The "official" single point per address
official_geocoding (
  id                UUID PRIMARY KEY,
  address_id        UUID NOT NULL UNIQUE REFERENCES addresses(id),
  geocoding_result_id UUID REFERENCES geocoding_results(id), -- null if admin-custom
  lat               NUMERIC(10,7) NOT NULL,
  lon               NUMERIC(10,7) NOT NULL,
  geom              GEOGRAPHY(POINT, 4326),
  is_admin_override BOOLEAN NOT NULL DEFAULT false,
  override_note     TEXT,                 -- optional admin comment
  set_at            TIMESTAMPTZ NOT NULL DEFAULT now()
)

-- One row per (address, provider) validation attempt
validation_results (
  id              UUID PRIMARY KEY,
  address_id      UUID NOT NULL REFERENCES addresses(id),
  provider        TEXT NOT NULL,
  suggestions     JSONB NOT NULL,         -- [{standardized, confidence, dpv_match, ...}]
  fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(address_id, provider)
)
```

### Key Indexes

```sql
-- Fast canonical lookup (primary cache hit path)
CREATE INDEX idx_addresses_canonical_key ON addresses(canonical_key);

-- Spatial index for proximity queries
CREATE INDEX idx_geocoding_results_geom ON geocoding_results USING GIST(geom);
CREATE INDEX idx_official_geocoding_geom ON official_geocoding USING GIST(geom);

-- Provider result lookups
CREATE INDEX idx_geocoding_results_address_id ON geocoding_results(address_id);
CREATE INDEX idx_validation_results_address_id ON validation_results(address_id);
```

### Canonical Key Strategy

The canonical key is the normalized form used for cache lookups before any external call. A simple but effective approach:

```python
def canonical_key(raw: str) -> str:
    # lowercase, collapse whitespace, strip punctuation except hyphens
    import re
    s = raw.lower().strip()
    s = re.sub(r"[^\w\s\-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s
```

For structured input, serialize fields in a deterministic order before hashing.

---

## Provider Plugin Contract

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class GeocodingResult:
    provider: str
    lat: Optional[float]
    lon: Optional[float]
    accuracy: Optional[str]
    match_type: Optional[str]
    raw_response: dict

@dataclass
class ValidationSuggestion:
    standardized: str
    confidence: float          # 0.0–1.0
    dpv_match: Optional[str]   # USPS DPV match codes where applicable
    components: dict

class GeocodingProvider(ABC):
    name: str                  # unique registry key, e.g. "google"

    @abstractmethod
    async def geocode(self, address: str) -> GeocodingResult: ...

class ValidationProvider(ABC):
    name: str

    @abstractmethod
    async def validate(self, address: str) -> list[ValidationSuggestion]: ...
```

ProviderRegistry holds a dict keyed by `provider.name`. Registration is explicit (no auto-discovery magic), keeping the system predictable:

```python
registry = ProviderRegistry()
registry.register(GoogleGeocodingProvider(api_key=...))
registry.register(CensusGeocodingProvider())
registry.register(USPSValidationProvider(user_id=...))
```

---

## Patterns to Follow

### Pattern 1: Cache-Aside (Lazy Population)

**What:** Check DB on every request. On miss, call providers and populate. Never pre-warm.
**When:** All geocoding and validation requests.
**Why:** Addresses are long-tail; pre-warming is wasteful. Lazy population is natural for this domain.

### Pattern 2: Independent Provider Results with Separate Official Record

**What:** Each provider's result is a first-class row with its own identity. A separate table holds the "official" point.
**When:** Always — this is the core data model.
**Why:** Enables comparison, admin override selection, and adding new providers retroactively without schema changes.

### Pattern 3: Provider Fault Isolation

**What:** Each provider call is wrapped in try/except. Failure of one provider does not fail the request.
**When:** All orchestrator calls to the provider layer.
**Why:** External services are unreliable. A partial result (from 3 of 4 providers) is more valuable than an error.

### Pattern 4: Idempotent Persistence

**What:** INSERT ... ON CONFLICT DO NOTHING (or DO UPDATE) on `(address_id, provider)`.
**When:** All result persistence — especially critical for batch and concurrent requests.
**Why:** Prevents duplicate rows from concurrent requests for the same address.

### Pattern 5: Raw Response Preservation

**What:** Store the full provider JSON response in a JSONB column alongside extracted fields.
**When:** Every geocoding and validation result row.
**Why:** Provider APIs evolve; raw storage lets you extract new fields later without re-calling the API.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking Provider Calls in Sequence

**What:** Calling provider 1, waiting, then calling provider 2, etc.
**Why bad:** 5 providers × 200ms each = 1s minimum latency on every cache miss.
**Instead:** Use `asyncio.gather()` to fan out all provider calls concurrently.

### Anti-Pattern 2: Normalizing Away the Raw Input

**What:** Discarding the original input string after parsing.
**Why bad:** Debugging and admin review require seeing exactly what was submitted.
**Instead:** Store `raw_input` on the address record alongside parsed fields.

### Anti-Pattern 3: Single "geocode" Column on Address Table

**What:** Putting lat/lon directly on the addresses table.
**Why bad:** Can't store multiple provider results; makes admin override a schema problem.
**Instead:** Separate `geocoding_results` (one per provider) + `official_geocoding` (one per address).

### Anti-Pattern 4: Synchronous HTTP Clients in an Async Framework

**What:** Using `requests` library in FastAPI route handlers.
**Why bad:** Blocks the event loop; kills concurrency under load.
**Instead:** Use `httpx.AsyncClient` throughout. Each provider gets its own client instance configured with appropriate timeouts.

### Anti-Pattern 5: Fat Repository Layer

**What:** Putting business logic (which provider wins, how to derive official record) inside repository classes.
**Why bad:** Repositories should map Python objects to SQL — nothing more.
**Instead:** Business logic lives in Orchestrators and OfficialRecordService; repositories are pure data access.

---

## Suggested Build Order

Dependencies flow downward — build lower layers before the layers that depend on them.

```
1. Database schema + migrations
   (everything else depends on the data model)

2. Repository layer (AddressRepo, GeocodingResultRepo, etc.)
   (Service layer needs working DB access)

3. Provider abstract base + one concrete provider (Census — free, no key)
   (Validates the plugin contract before investing in all providers)

4. CacheService + GeocodingOrchestrator (single-address, single provider)
   (Core cache-aside loop; verifiable end-to-end before adding more providers)

5. Remaining concrete providers (Google, USPS, Amazon, Geoapify)
   (Parallel work once the contract is proven)

6. ValidationOrchestrator + validation providers
   (Parallel to step 5; shares CacheService and repository patterns)

7. OfficialRecordService + AdminOverrideService
   (Needs geocoding results to exist before it makes sense)

8. FastAPI endpoint layer (single-address endpoints)
   (Wire the service layer to HTTP; all logic already tested)

9. Batch endpoints
   (Fan-out over single-address logic; build last because it adds complexity)
```

---

## Component Dependency Graph

```
FastAPI ──────────────────────────────────────────────
  │                                                   │
  ▼                                                   ▼
CacheService                               AdminOverrideService
  │                                                   │
  ├──▶ AddressRepository                              ▼
  │                                        OfficialRecordService
  ├──▶ GeocodingOrchestrator ──▶ ProviderRegistry ──▶ Providers
  │         │                                         │
  │         ▼                                         │ (external HTTP)
  │    GeocodingResultRepository                      │
  │    OfficialGeocodingRepository ◀──────────────────┘
  │
  └──▶ ValidationOrchestrator ──▶ ProviderRegistry ──▶ Providers
            │
            ▼
       ValidationResultRepository
```

---

## Scalability Considerations

| Concern | At current scale (internal) | If volume grows |
|---------|----------------------------|-----------------|
| Provider fan-out latency | asyncio.gather handles it well | Add per-provider timeout caps (e.g., 2s); drop slow providers |
| DB write contention on batch | ON CONFLICT DO NOTHING prevents duplicates | Batch-insert with executemany; add connection pooling (asyncpg + SQLAlchemy async) |
| Cache hit ratio | Improves naturally as addresses accumulate | No expiry means ratio only goes up over time |
| PostGIS spatial queries | GIST index handles thousands of points | Partition by state CHAR(2) if millions of rows |
| Provider API rate limits | Per-provider clients should track request counts | Add token-bucket rate limiter per provider in ProviderRegistry |

---

## Sources

- Domain knowledge: geocoding SaaS architectures (Pelias, Nominatim, SmartyStreets internals)
- FastAPI async patterns: official FastAPI docs on async/await and background tasks
- PostGIS geography type and GIST indexing: PostGIS documentation (geography vs geometry tradeoffs)
- Cache-aside pattern: Martin Fowler's Patterns of Enterprise Application Architecture
- Confidence: HIGH — these are well-established patterns with no significant variation across sources
