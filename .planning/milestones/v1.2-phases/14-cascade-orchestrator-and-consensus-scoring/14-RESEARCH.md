# Phase 14: Cascade Orchestrator and Consensus Scoring - Research

**Researched:** 2026-03-29
**Domain:** Python asyncio pipeline orchestration, spatial clustering, PostgreSQL upsert patterns, FastAPI query params, Pydantic schema extension, Alembic column migration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Cascade Integration (CASC-01, CASC-02)**
- D-01: CascadeOrchestrator lives in a new `services/cascade.py` file, imported by GeocodingService
- D-02: GeocodingService.geocode() delegates to CascadeOrchestrator.run() when `CASCADE_ENABLED=true`; when false, calls `_legacy_geocode()` which preserves the v1.1 flat pipeline
- D-03: The "replace internals" pattern — current geocode() body moves to _legacy_geocode(), keeping a single entry point for API routes (no route changes needed)
- D-04: Existing tests run parameterized against both CASCADE_ENABLED=true and false via pytest parameterize — both paths tested

**Exact Match Stage (CASC-01)**
- D-05: Single exact-match stage calls ALL providers (local + remote) in parallel. No separate local-then-remote staging. Remote cache check still applies for remote providers. All results feed into consensus scoring regardless of source

**Consensus Clustering (CONS-01, CONS-02)**
- D-06: Greedy single-pass clustering: sort results by trust weight descending, first result seeds cluster 1, each subsequent result joins nearest cluster if within 100m, otherwise starts new cluster
- D-07: Weighted centroid: `centroid_lat = sum(w*lat) / sum(w)` where w = provider trust weight. More trusted providers pull the centroid position
- D-08: Provider trust weights per CONS-02: Census=0.90, OA=0.80, Macon-Bibb=0.80, Tiger=0.40 unrestricted / 0.75 with restrict_region, NAD=0.80
- D-09: Fuzzy results use scaled provider weight: `effective_weight = provider_weight * (fuzzy_confidence / 0.80)`. Naturally discounts fuzzy results without separate config
- D-10: Winning cluster = highest total weight. Winning centroid auto-set as OfficialGeocoding

**Single-Result Handling**
- D-11: When only one provider returns a result: auto-set as official if confidence >= 0.80; below 0.80, return the result but do not write OfficialGeocoding (admin can override manually)

**Early-Exit (CASC-03)**
- D-12: Early-exit triggers when ANY single exact-match provider returns confidence >= 0.80 — skips fuzzy and LLM stages only
- D-13: Consensus scoring ALWAYS runs, even on early-exit — just with fewer results. Ensures consistent outlier flagging and set_by_stage audit trail
- D-14: Stage sequence: (1) normalize + spell-correct → (2) exact match → [early-exit skips 3-4] → (3) fuzzy match → (4) LLM correction → (5) consensus score → (6) auto-set official

**Latency Budgets (CASC-04)**
- D-15: Per-stage configurable timeouts via environment variables: EXACT_MATCH_TIMEOUT_MS=2000, FUZZY_MATCH_TIMEOUT_MS=500, CONSENSUS_TIMEOUT_MS=200, CASCADE_TOTAL_TIMEOUT_MS=3000
- D-16: If a stage times out, cascade continues with whatever results are available from that stage (graceful degradation)

**Dry-Run and Trace (CONS-06)**
- D-17: `?dry_run=true` runs the full cascade but does not write OfficialGeocoding; returns `would_set_official` and full `cascade_trace`
- D-18: `?trace=true` returns `cascade_trace` on normal (non-dry-run) requests too
- D-19: cascade_trace is an array of stage objects: `{stage, input, output, results_count, early_exit, ms, ...}`

**Outlier Flagging (CONS-03)**
- D-20: Per-result `is_outlier: bool` field added to GeocodeProviderResult in the API response. Results > 1km from winning cluster centroid are flagged `is_outlier: true`

**Audit Metadata (CONS-05)**
- D-21: New `set_by_stage` TEXT column on the `official_geocoding` table via Alembic migration. Values: "exact_match_consensus", "fuzzy_consensus", "single_provider", etc.
- D-22: Cascade path uses `ON CONFLICT DO UPDATE` for OfficialGeocoding (replacing v1.1's DO NOTHING) so consensus winner can update a previously auto-set record. Admin overrides are NEVER overwritten (check for admin_override provider before updating)

### Claude's Discretion
- Alembic migration strategy for `set_by_stage` column (new migration vs extending existing)
- Internal CascadeOrchestrator method decomposition (how stages are structured as methods/classes)
- Exact cascade_trace schema fields per stage type
- Haversine vs PostGIS ST_Distance for the 100m/1km clustering thresholds (in-Python vs SQL)
- How CASCADE_ENABLED config integrates with existing `settings` (Pydantic BaseSettings)
- asyncio.gather vs sequential for parallel provider calls within exact-match stage

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CASC-01 | CascadeOrchestrator implements staged resolution: normalize → spell-correct → exact match → fuzzy/phonetic → consensus score → auto-set official | Services/cascade.py new file; geocoding.py _legacy_geocode() refactor pattern documented |
| CASC-02 | Cascade is feature-flagged via `CASCADE_ENABLED` environment variable (default: true for new installs) | Pydantic BaseSettings extension pattern documented; config.py currently minimal |
| CASC-03 | Early-exit optimization: if any exact-match provider returns confidence >= 0.80, skip fuzzy and later stages | asyncio.gather with early-exit pattern documented; confidence thresholds confirmed |
| CASC-04 | Per-stage latency budgets enforced (P95 target: < 3s total cascade for single address) | asyncio.wait_for() timeout pattern; per-stage env var strategy documented |
| CONS-01 | Cross-provider consensus scoring groups results into spatial clusters (within 100m) and selects highest-weighted cluster | Haversine in-Python vs PostGIS analyzed; greedy single-pass algorithm documented |
| CONS-02 | Provider trust weights are configurable (Census: 0.90, OA: 0.80, Macon-Bibb: 0.80, Tiger: 0.40/0.75, NAD: 0.80) | Weight constants and fuzzy weight scaling formula documented |
| CONS-03 | Outlier results (> 1km from winning cluster centroid) are flagged as low-confidence in the response | GeocodeProviderResult schema extension (is_outlier field) documented |
| CONS-04 | Winning cluster centroid is auto-set as OfficialGeocoding when no admin override exists | ON CONFLICT DO UPDATE with admin_override guard pattern documented; OfficialGeocoding ORM structure confirmed |
| CONS-05 | All auto-set official records include `set_by_stage` audit metadata | Alembic op.add_column() migration pattern; OfficialGeocoding model extension documented |
| CONS-06 | Dry-run mode available via query parameter (`?dry_run=true`) — runs full cascade but does not write OfficialGeocoding, returns what would have been set | FastAPI Query() parameter pattern; GeocodeResponse schema extension documented |
</phase_requirements>

---

## Summary

Phase 14 wires together the components from Phases 12 and 13 into a single `CascadeOrchestrator` that replaces the flat geocoding pipeline with a multi-stage resolution loop. The two primary domains are (1) Python async pipeline orchestration with per-stage timeouts and early-exit logic, and (2) in-memory spatial clustering using weighted centroids for consensus scoring.

The existing codebase provides a clear template for all integration points: `GeocodingService` uses the "replace internals" refactor pattern (current `geocode()` body moves to `_legacy_geocode()`), `FuzzyMatcher` is already instantiated with a session factory and can be called as a cascade stage, and `config.py` uses Pydantic `BaseSettings` which trivially accepts additional `CASCADE_*` variables. The Alembic migration chain is established through 7 existing migrations, so adding `set_by_stage` is a straightforward `op.add_column()`.

The key implementation discretion choices (Claude's) are: (a) in-Python haversine for the 100m/1km thresholds rather than PostGIS (no round-trip, pure math), (b) `asyncio.gather()` with `asyncio.wait_for()` wrappers for per-stage timeouts, and (c) a dedicated `CascadeResult` dataclass returned from `CascadeOrchestrator.run()` that carries all fields needed to populate `GeocodeResponse`.

**Primary recommendation:** Use in-Python haversine for clustering (avoids DB round-trip, simpler to unit-test), `asyncio.gather()` for parallel exact-match stage, and `asyncio.wait_for()` for per-stage timeouts. Keep CascadeOrchestrator as a plain class (not a per-request singleton) instantiated in `GeocodingService.__init__` or lazily.

---

## Standard Stack

### Core (all already in pyproject.toml dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy (async) | >=2.0.48 | DB upserts, ORM queries | Already used throughout; `pg_insert().on_conflict_do_update()` pattern established |
| asyncpg | >=0.31.0 | PostgreSQL async driver | Already in deps |
| pydantic-settings | >=2.13.1 | `BaseSettings` for new env vars | Config pattern already established in `config.py` |
| loguru | >=0.7.3 | Stage-level debug logging | Already used in geocoding.py and fuzzy.py |
| asyncio (stdlib) | Python 3.12 | gather + wait_for for parallel stage + timeouts | No new dependency |
| math (stdlib) | Python 3.12 | Haversine distance computation | No new dependency |

### No New Dependencies Required
All required capabilities exist in stdlib or installed packages. The haversine formula uses `math.radians`, `math.sin`, `math.cos`, `math.sqrt`, `math.atan2` — all Python stdlib. This is a deliberate choice over adding `haversine` or `geopy` libraries.

**Installation:**
```bash
# No new packages needed — all dependencies are present
```

---

## Architecture Patterns

### Recommended Project Structure (new files only)
```
src/civpulse_geo/
├── services/
│   ├── geocoding.py    # Modified: geocode() delegates, _legacy_geocode() added
│   └── cascade.py      # NEW: CascadeOrchestrator, CascadeResult, consensus logic
├── schemas/
│   └── geocoding.py    # Modified: is_outlier, cascade_trace, dry_run, would_set_official
├── api/
│   └── geocoding.py    # Modified: dry_run + trace Query params
├── config.py           # Modified: CASCADE_ENABLED, timeout, weight env vars
└── models/
    └── geocoding.py    # Modified: OfficialGeocoding.set_by_stage column
alembic/versions/
└── h8e5f1g4a7b3_add_set_by_stage_to_official_geocoding.py  # NEW
```

### Pattern 1: CascadeOrchestrator Class Decomposition

**What:** A class with a single public `run()` method that encapsulates all stages as private methods. Returns a `CascadeResult` dataclass carrying all state needed by the route handler.

**When to use:** This is the only pattern for Phase 14. The orchestrator does NOT inherit from anything — it is a plain service class following the `GeocodingService` pattern.

```python
# services/cascade.py (pattern sketch — not implementation)
@dataclass
class CascadeResult:
    address_hash: str
    normalized_address: str
    cache_hit: bool
    results: list  # All provider results with is_outlier populated
    official: GeocodingResultORM | None
    would_set_official: GeocodeProviderResult | None  # dry_run only
    cascade_trace: list[dict] | None  # when trace=True or dry_run=True

class CascadeOrchestrator:
    async def run(
        self,
        freeform: str,
        db: AsyncSession,
        providers: dict,
        http_client: httpx.AsyncClient,
        fuzzy_matcher: FuzzyMatcher,
        spell_corrector: SpellCorrector | None,
        dry_run: bool = False,
        trace: bool = False,
    ) -> CascadeResult:
        ...

    async def _stage_normalize(self, ...) -> tuple[str, str]: ...
    async def _stage_exact_match(self, ...) -> list[ProviderResult]: ...
    async def _stage_fuzzy(self, ...) -> FuzzyMatchResult | None: ...
    def _run_consensus(self, results: list) -> ConsensusResult: ...
    async def _auto_set_official(self, ...) -> GeocodingResultORM | None: ...
```

### Pattern 2: GeocodingService Refactor (_legacy_geocode)

**What:** The current `geocode()` body is moved verbatim to `_legacy_geocode()`. The `geocode()` method becomes a two-branch dispatcher.

**When to use:** Always — D-02 / D-03 mandate this pattern.

```python
# services/geocoding.py
async def geocode(self, freeform, db, providers, http_client, ...
                  dry_run=False, trace=False) -> dict:
    if settings.cascade_enabled:
        return await self._cascade_orchestrator.run(...)
    else:
        return await self._legacy_geocode(freeform, db, providers, ...)

async def _legacy_geocode(self, freeform, db, providers, http_client, ...) -> dict:
    # Existing geocode() body moved here verbatim
    ...
```

### Pattern 3: asyncio.gather + asyncio.wait_for for Stage Timeouts

**What:** Each stage call is wrapped in `asyncio.wait_for(coro, timeout=seconds)`. The entire exact-match stage runs all providers concurrently with `asyncio.gather()`. Results from timed-out providers are simply absent from the stage output.

**When to use:** Exact-match stage (all providers in parallel, D-05), fuzzy stage (single call, D-15), consensus stage.

```python
# Parallel provider calls with per-stage timeout (D-05, D-15)
import asyncio

async def _stage_exact_match(self, normalized, providers, http_client, timeout_ms):
    timeout_s = timeout_ms / 1000
    tasks = {
        name: asyncio.wait_for(
            provider.geocode(normalized, http_client=http_client),
            timeout=timeout_s
        )
        for name, provider in providers.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    # Filter out TimeoutError and other exceptions (graceful degradation, D-16)
    good = []
    for name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning("Provider {} timed out or errored: {}", name, result)
        else:
            good.append(result)
    return good
```

### Pattern 4: Greedy Single-Pass Clustering with In-Python Haversine

**What:** Pure Python clustering using the haversine formula from stdlib math. No PostGIS round-trip needed — all provider results carry `lat`/`lng` already.

**When to use:** Consensus scoring (CONS-01, CONS-02).

```python
# Haversine distance in meters — stdlib math only
import math

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# Greedy clustering (D-06, D-07)
def _cluster(results_with_weights):
    # Sort by weight descending
    sorted_results = sorted(results_with_weights, key=lambda r: r.weight, reverse=True)
    clusters = []
    for item in sorted_results:
        placed = False
        for cluster in clusters:
            dist = haversine_m(cluster.centroid_lat, cluster.centroid_lng,
                               item.lat, item.lng)
            if dist <= 100:
                cluster.add(item)
                placed = True
                break
        if not placed:
            clusters.append(Cluster(item))
    # Winning cluster = highest total weight (D-10)
    return max(clusters, key=lambda c: c.total_weight)
```

**Why in-Python over PostGIS:** No additional DB query needed (lat/lng already loaded in provider results), haversine is accurate to <0.1% at sub-km distances, simpler to unit-test without a PostGIS fixture.

### Pattern 5: ON CONFLICT DO UPDATE with Admin Override Guard (D-22)

**What:** The cascade path replaces `ON CONFLICT DO NOTHING` with `ON CONFLICT DO UPDATE`, but first checks whether an `admin_override` provider result is currently set as the official. If the existing official points to `admin_override`, skip the upsert entirely.

**When to use:** Auto-set OfficialGeocoding in cascade path (CONS-04, D-22).

```python
# Check for admin_override before overwriting (D-22)
existing_official = await self._get_official(db, address.id)
if existing_official and existing_official.provider_name == "admin_override":
    # Never overwrite admin override
    return existing_official

# Safe to write consensus winner
await db.execute(
    pg_insert(OfficialGeocoding)
    .values(
        address_id=address.id,
        geocoding_result_id=winner_result_id,
        set_by_stage=stage_name,
    )
    .on_conflict_do_update(
        index_elements=["address_id"],
        set_={
            "geocoding_result_id": winner_result_id,
            "set_by_stage": stage_name,
        },
    )
)
```

### Pattern 6: Alembic Column Addition (add_column)

**What:** New migration file chained from `g7d4e0f3a6b2` using `op.add_column()` to add `set_by_stage TEXT` (nullable) to `official_geocoding`. New migration, not extending existing.

**When to use:** CONS-05 (D-21).

```python
# alembic/versions/h8e5f1g4a7b3_add_set_by_stage_to_official_geocoding.py
revision = "h8e5f1g4a7b3"
down_revision = "g7d4e0f3a6b2"

def upgrade() -> None:
    op.add_column(
        "official_geocoding",
        sa.Column("set_by_stage", sa.Text, nullable=True),
    )

def downgrade() -> None:
    op.drop_column("official_geocoding", "set_by_stage")
```

### Pattern 7: FastAPI Query Parameters for dry_run and trace

**What:** Add `dry_run: bool = Query(False)` and `trace: bool = Query(False)` to the `geocode()` route handler signature. Pass them through to `GeocodingService.geocode()` / `CascadeOrchestrator.run()`.

**When to use:** CONS-06 / D-17, D-18.

```python
# api/geocoding.py
from fastapi import Query

@router.post("", response_model=GeocodeResponse)
async def geocode(
    body: GeocodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    dry_run: bool = Query(False, description="Run cascade without writing OfficialGeocoding"),
    trace: bool = Query(False, description="Include cascade_trace in response"),
):
    ...
```

### Pattern 8: Pydantic BaseSettings Extension (config.py)

**What:** Add new fields to the existing `Settings` class. Pydantic BaseSettings automatically reads `CASCADE_ENABLED`, `EXACT_MATCH_TIMEOUT_MS`, etc. from env / `.env` file.

```python
# config.py
class Settings(BaseSettings):
    # ... existing fields ...

    # Cascade feature flag (CASC-02)
    cascade_enabled: bool = True

    # Per-stage timeout budgets in ms (CASC-04, D-15)
    exact_match_timeout_ms: int = 2000
    fuzzy_match_timeout_ms: int = 500
    consensus_timeout_ms: int = 200
    cascade_total_timeout_ms: int = 3000

    # Provider trust weights (CONS-02, D-08)
    weight_census: float = 0.90
    weight_openaddresses: float = 0.80
    weight_macon_bibb: float = 0.80
    weight_tiger_unrestricted: float = 0.40
    weight_tiger_restricted: float = 0.75
    weight_nad: float = 0.80
```

### Pattern 9: GeocodeResponse Schema Extension (additive)

**What:** Add optional fields to `GeocodeProviderResult` and `GeocodeResponse`. Existing callers unaffected because new fields default to `None`/`False`.

```python
# schemas/geocoding.py
class GeocodeProviderResult(BaseModel):
    provider_name: str
    latitude: float | None = None
    longitude: float | None = None
    location_type: str | None = None
    confidence: float | None = None
    is_outlier: bool = False  # NEW (CONS-03, D-20)

class GeocodeResponse(BaseModel):
    address_hash: str
    normalized_address: str
    cache_hit: bool
    results: list[GeocodeProviderResult]
    local_results: list[GeocodeProviderResult] = []
    official: GeocodeProviderResult | None = None
    cascade_trace: list[dict] | None = None  # NEW (CONS-06, D-19)
    would_set_official: GeocodeProviderResult | None = None  # NEW (dry_run, D-17)
```

### Pattern 10: OfficialGeocoding Model Extension

**What:** Add `set_by_stage: Mapped[str | None]` to the ORM model.

```python
# models/geocoding.py
class OfficialGeocoding(Base, TimestampMixin):
    # ... existing columns ...
    set_by_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### Anti-Patterns to Avoid

- **Calling FuzzyMatcher without zip_code scoping:** FuzzyMatcher accepts `zip_code` to scope results. The cascade must extract zip from the parsed address and pass it — otherwise fuzzy queries are unscoped and return wrong-area results.
- **Using `on_conflict_do_nothing` in cascade path:** The existing geocoding.py auto-set uses `DO NOTHING`. The cascade MUST switch to `DO UPDATE` (D-22), but only after checking for admin_override first.
- **Storing fuzzy result as a cached GeocodingResult row:** FuzzyMatcher returns a `FuzzyMatchResult` dataclass, not an ORM row. The cascade must create a synthetic `GeocodingResult` schema object to participate in consensus scoring, similar to how local_results are handled in the existing pipeline.
- **Assuming `local_results` have ORM ids:** Current pipeline distinguishes local_results (no ORM row) from remote results (ORM rows). The cascade must handle local provider results from exact-match stage and fuzzy results identically — neither has a geocoding_result_id until the cascade decides to persist.
- **Applying fuzzy confidence weight without mapping:** D-09 specifies `effective_weight = provider_weight * (fuzzy_confidence / 0.80)`. The denominator 0.80 is the threshold above which a single result auto-sets official (D-11), providing a natural normalization anchor.
- **Creating a new session for FuzzyMatcher:** FuzzyMatcher opens its own sessions via its `session_factory`. The cascade should not pass a session to FuzzyMatcher or use db.execute for the fuzzy query — FuzzyMatcher handles its own session lifecycle.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parallel provider dispatch | Custom asyncio loop | `asyncio.gather()` + `asyncio.wait_for()` | Handles cancellation, exception isolation, timeouts correctly |
| Distance computation | Custom spherical math | Python `math` stdlib haversine | 6-line formula, well-understood, no deps |
| Env var config | Custom `os.getenv()` calls | Pydantic BaseSettings (already in config.py) | Type coercion, validation, `.env` support built-in |
| DB upsert with conflict handling | Custom SELECT-then-INSERT | `pg_insert().on_conflict_do_update()` (already used) | Atomic, avoids race conditions |
| Fuzzy street matching | New trigram query | Existing `FuzzyMatcher.find_fuzzy_match()` | Already calibrated, tested, and correct |
| Address normalization | Re-implement | Existing `canonical_key()` / `_apply_spell_correction()` | Idempotent, consistent hash behavior |

**Key insight:** Every component needed by the cascade already exists — this phase is integration and orchestration, not net-new algorithms.

---

## Runtime State Inventory

> This is a greenfield service addition phase (new file, additive schema change). Runtime state considerations are minimal.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `official_geocoding` rows lack `set_by_stage` column (NULL after migration) | Alembic migration adds nullable column — existing rows stay NULL (acceptable; only new cascade writes populate it) |
| Live service config | `CASCADE_ENABLED` defaults to `true` — existing deployments without this env var will have cascade active after deploy | Operators should set `CASCADE_ENABLED=false` in staging before upgrade if they want controlled rollout |
| OS-registered state | None | None |
| Secrets/env vars | New env vars (`CASCADE_ENABLED`, `EXACT_MATCH_TIMEOUT_MS`, etc.) have sensible defaults in `Settings` — no hard failure if unset | None required; document defaults in README if desired |
| Build artifacts | None — pure Python, no compiled artifacts | None |

---

## Common Pitfalls

### Pitfall 1: FuzzyMatcher Returns a Dataclass, Not an ORM Row
**What goes wrong:** Consensus scoring expects provider results with `lat`/`lng`/`confidence`/`provider_name`. `FuzzyMatchResult` is a dataclass from `services/fuzzy.py` — it has these fields but is NOT a `GeocodingResultSchema` or ORM row.
**Why it happens:** The existing pipeline only handles two types: `GeocodingResultSchema` (from providers) and `GeocodingResultORM` (from DB). Fuzzy introduces a third type.
**How to avoid:** Define a protocol or use duck-typing in consensus scoring. The orchestrator should normalize all result types into a common `ProviderCandidate` internal dataclass before clustering. Alternatively, map `FuzzyMatchResult` to a `GeocodingResult` schema object (from `providers/schemas.py`) before feeding into consensus.
**Warning signs:** `AttributeError: 'FuzzyMatchResult' object has no attribute 'lat'` — note FuzzyMatchResult uses `lat`/`lng` matching the schema convention, so the field names align.

### Pitfall 2: Local Provider Results Have No geocoding_result_id
**What goes wrong:** `OfficialGeocoding.geocoding_result_id` is a FK to `geocoding_results.id`. Local providers (OA, NAD, Macon-Bibb, Tiger) do NOT write to `geocoding_results` — they return schema objects only. If the consensus winner is a local provider result, there is no `geocoding_result_id` to write.
**Why it happens:** The existing pipeline's Step 6 explicitly notes: "Local results have no ORM row and cannot be referenced by geocoding_result_id".
**How to avoid:** The cascade must persist the winning result as a `GeocodingResult` ORM row before auto-setting `OfficialGeocoding`. For local/fuzzy winners, upsert into `geocoding_results` first (using the same upsert pattern as remote providers), then use the returned `id` for `OfficialGeocoding`.
**Warning signs:** `IntegrityError: null value in column "geocoding_result_id"` at the OfficialGeocoding upsert step.

### Pitfall 3: asyncio.wait_for Cancellation Leaks
**What goes wrong:** When `asyncio.wait_for` times out, it raises `asyncio.TimeoutError` AND cancels the wrapped coroutine. If the coroutine holds DB resources or has side effects (e.g., writing cache), the cancellation may leave the session in an inconsistent state.
**Why it happens:** Remote providers (Census) make HTTP calls via `httpx.AsyncClient`. Cancellation mid-request should be safe (httpx handles it), but providers that write to DB within the call would be problematic.
**How to avoid:** Provider `geocode()` methods in this codebase do NOT write to DB (writing is handled by GeocodingService). The cascade should catch `asyncio.TimeoutError` (or `asyncio.CancelledError`) per-task via `return_exceptions=True` in `asyncio.gather()` — this isolates failures and allows the stage to continue with partial results.
**Warning signs:** Tasks in `asyncio.gather()` showing `CancelledError` propagating beyond the stage boundary.

### Pitfall 4: ON CONFLICT DO UPDATE Overwrites Admin Override
**What goes wrong:** After a human admin sets a custom coordinate, the cascade runs again (e.g., via refresh) and overwrites the admin's choice with the consensus winner.
**Why it happens:** `ON CONFLICT DO UPDATE` always updates — it does not check the current value before overwriting.
**How to avoid:** Query `OfficialGeocoding` and join to `GeocodingResult.provider_name` before the upsert. If `provider_name == "admin_override"`, skip the upsert entirely and return the existing official (D-22).
**Warning signs:** Admin-set coordinates being silently replaced after any geocode refresh.

### Pitfall 5: Cascade Trace Adds Significant Response Payload
**What goes wrong:** `cascade_trace` contains per-stage input/output snapshots. If trace is always on, responses grow large — especially for addresses that traverse all 4 stages.
**Why it happens:** Trace was designed for debugging, not production use.
**How to avoid:** `cascade_trace` defaults to `None` in `GeocodeResponse`. Only populate when `trace=True` or `dry_run=True` (D-17, D-18). The orchestrator conditionally builds trace objects.
**Warning signs:** Response size exceeding expected bounds on normal (non-trace) requests.

### Pitfall 6: pytest.mark.parametrize Across CASCADE_ENABLED Requires Careful DB State
**What goes wrong:** Tests parameterized with `CASCADE_ENABLED=true` and `CASCADE_ENABLED=false` may share DB state between test runs, causing false positives when cascade path accidentally uses legacy state.
**Why it happens:** `settings` is a module-level singleton; patching it mid-test requires `unittest.mock.patch` or a fixture-level override.
**How to avoid:** Use `unittest.mock.patch.object(settings, 'cascade_enabled', ...)` as a context manager or fixture. Alternatively, pass `cascade_enabled` as a parameter to `GeocodingService.geocode()` so tests can inject it without patching the global settings.
**Warning signs:** Tests passing individually but failing in combination due to settings mutation.

---

## Code Examples

Verified patterns from existing codebase:

### Existing Upsert Pattern (geocoding.py — basis for cascade auto-set)
```python
# Source: src/civpulse_geo/services/geocoding.py lines 177-199
stmt = (
    pg_insert(GeocodingResultORM)
    .values(
        address_id=address.id,
        provider_name=provider_name,
        location=ewkt_point,
        latitude=latitude,
        longitude=longitude,
        location_type=location_type_value,
        confidence=provider_result.confidence,
        raw_response=provider_result.raw_response,
    )
    .on_conflict_do_update(
        constraint="uq_geocoding_address_provider",
        set_={
            "location": ewkt_point,
            "latitude": latitude,
            "longitude": longitude,
            "location_type": location_type_value,
            "confidence": provider_result.confidence,
            "raw_response": provider_result.raw_response,
        },
    )
    .returning(GeocodingResultORM.id)
)
upsert_result = await db.execute(stmt)
result_id = upsert_result.scalar_one()
```

### Existing OfficialGeocoding Write (legacy DO NOTHING — cascade changes to DO UPDATE)
```python
# Source: src/civpulse_geo/services/geocoding.py lines 218-225
# v1.1 pattern — cascade REPLACES .on_conflict_do_nothing() with .on_conflict_do_update()
await db.execute(
    pg_insert(OfficialGeocoding)
    .values(
        address_id=address.id,
        geocoding_result_id=successful[0].id,
    )
    .on_conflict_do_nothing(index_elements=["address_id"])
)
```

### FuzzyMatcher Invocation Pattern (cascade stage 3)
```python
# Source: src/civpulse_geo/services/fuzzy.py lines 89-95
# FuzzyMatcher requires session_factory (not a session) — instantiate at app startup
fuzzy_matcher = FuzzyMatcher(session_factory=async_session_factory)
result = await fuzzy_matcher.find_fuzzy_match(
    street_name=parsed_street_name,
    zip_code=parsed_zip_code,
    street_number=parsed_street_number,
)
# Returns FuzzyMatchResult | None
```

### Pydantic BaseSettings Extension Pattern (config.py)
```python
# Source: src/civpulse_geo/config.py — extend existing Settings class
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    # existing fields unchanged
    database_url: str = "..."
    # new cascade fields — all have defaults, so no breakage on existing deployments
    cascade_enabled: bool = True
    exact_match_timeout_ms: int = 2000
    # etc.
```

### Alembic add_column Pattern (most recent migration as template)
```python
# Source: alembic/versions/g7d4e0f3a6b2_add_spell_dictionary_macon_bibb_trgm.py
import sqlalchemy as sa
from alembic import op

revision = "h8e5f1g4a7b3"
down_revision = "g7d4e0f3a6b2"

def upgrade() -> None:
    op.add_column(
        "official_geocoding",
        sa.Column("set_by_stage", sa.Text, nullable=True),
    )

def downgrade() -> None:
    op.drop_column("official_geocoding", "set_by_stage")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `on_conflict_do_nothing` for OfficialGeocoding auto-set | `on_conflict_do_update` with admin guard in cascade path | Phase 14 | Enables cascade to update stale auto-set results; admin overrides still protected |
| Flat provider loop with no early-exit | Staged cascade with early-exit at confidence >= 0.80 | Phase 14 | Eliminates unnecessary fuzzy queries for clean addresses |
| Single-result auto-set (first successful provider wins) | Multi-result weighted consensus with spatial clustering | Phase 14 | More accurate official geocode from multi-provider agreement |

---

## Open Questions

1. **How does FuzzyMatcher get passed to CascadeOrchestrator?**
   - What we know: `FuzzyMatcher` requires `session_factory` at construction. `SpellCorrector` is loaded into `app.state.spell_corrector`. There is no `app.state.fuzzy_matcher` yet.
   - What's unclear: Whether FuzzyMatcher should live in `app.state` (loaded at startup like SpellCorrector) or be instantiated inside CascadeOrchestrator.
   - Recommendation: Store in `app.state.fuzzy_matcher` at startup (same pattern as `spell_corrector`). The orchestrator receives it as a constructor arg or `run()` parameter.

2. **Where does the consensus "centroid" get persisted?**
   - What we know: The weighted centroid (D-07) is a computed lat/lng, not an existing provider result. `OfficialGeocoding.geocoding_result_id` requires a real FK to `geocoding_results.id`.
   - What's unclear: Does the cascade persist a synthetic `GeocodingResult` row with `provider_name="cascade_consensus"` and the centroid coordinates, then point `OfficialGeocoding` at it?
   - Recommendation: Yes — create a synthetic `cascade_consensus` GeocodingResult row with `provider_name="cascade_consensus"` and upsert with `ON CONFLICT (address_id, provider_name)`. This row carries the weighted centroid lat/lng and `set_by_stage` in its `raw_response`. OfficialGeocoding then points at this row.

3. **How does early-exit interact with cache?**
   - What we know: The existing pipeline has a cache-check step that returns early if remote results are already cached (geocoding_results exist). The cascade early-exit (D-12) is a different mechanism — it skips fuzzy/LLM based on confidence, not on cache.
   - What's unclear: Should the cascade still check for cached remote results before calling providers?
   - Recommendation: Yes — the cascade should preserve the existing cache-check behavior (skip provider calls if `address.geocoding_results` is populated and `force_refresh=False`). Cache-hit path still runs consensus on cached results.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL + pg_trgm | FuzzyMatcher (stage 3) | Assumed present (Phase 13 prerequisite) | — | — |
| fuzzystrmatch (dmetaphone) | FuzzyMatcher tiebreak | Assumed present (Phase 13 prerequisite) | — | — |
| Python asyncio | Stage timeouts (asyncio.wait_for) | ✓ | Python 3.12 stdlib | — |
| Python math | Haversine distance | ✓ | Python 3.12 stdlib | — |

No new external dependencies — all required capabilities are in stdlib or already installed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0.2 + pytest-asyncio >= 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/test_cascade_orchestrator.py tests/test_consensus_scoring.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CASC-01 | Cascade stages execute in order; degraded address returns official geocode | unit | `uv run pytest tests/test_cascade_orchestrator.py -x` | ❌ Wave 0 |
| CASC-02 | `CASCADE_ENABLED=false` triggers _legacy_geocode(), existing test suite passes | unit + parameterized | `uv run pytest tests/test_geocoding_service.py -x` | ✅ (needs param extension) |
| CASC-03 | Early-exit when provider confidence >= 0.80 skips fuzzy stage | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_early_exit -x` | ❌ Wave 0 |
| CASC-04 | Provider timeout results in graceful degradation (no crash) | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_timeout_graceful_degradation -x` | ❌ Wave 0 |
| CONS-01 | Results within 100m cluster together; cluster with highest weight wins | unit | `uv run pytest tests/test_consensus_scoring.py::test_clustering -x` | ❌ Wave 0 |
| CONS-02 | Trust weights applied correctly; fuzzy weight scaled by confidence/0.80 | unit | `uv run pytest tests/test_consensus_scoring.py::test_weights -x` | ❌ Wave 0 |
| CONS-03 | Results > 1km from centroid have is_outlier=True in response | unit | `uv run pytest tests/test_consensus_scoring.py::test_outlier_flagging -x` | ❌ Wave 0 |
| CONS-04 | OfficialGeocoding auto-set from consensus winner; admin_override never overwritten | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_admin_override_protected -x` | ❌ Wave 0 |
| CONS-05 | set_by_stage column populated with correct stage name in OfficialGeocoding | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_set_by_stage_audit -x` | ❌ Wave 0 |
| CONS-06 | dry_run=True returns would_set_official without writing DB | unit | `uv run pytest tests/test_cascade_orchestrator.py::test_dry_run -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_cascade_orchestrator.py tests/test_consensus_scoring.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_cascade_orchestrator.py` — covers CASC-01, CASC-03, CASC-04, CONS-04, CONS-05, CONS-06
- [ ] `tests/test_consensus_scoring.py` — covers CONS-01, CONS-02, CONS-03
- [ ] CASC-02 can be handled by extending `tests/test_geocoding_service.py` with `@pytest.mark.parametrize("cascade_enabled", [True, False])` (existing file, needs additions only)

---

## Sources

### Primary (HIGH confidence)
- Direct source code read: `src/civpulse_geo/services/geocoding.py` — full pipeline, upsert patterns, local/remote split
- Direct source code read: `src/civpulse_geo/services/fuzzy.py` — FuzzyMatcher API, FuzzyMatchResult fields
- Direct source code read: `src/civpulse_geo/models/geocoding.py` — OfficialGeocoding ORM schema
- Direct source code read: `src/civpulse_geo/config.py` — Pydantic BaseSettings pattern
- Direct source code read: `src/civpulse_geo/schemas/geocoding.py` — existing response schema
- Direct source code read: `src/civpulse_geo/api/geocoding.py` — route handler patterns
- Direct source code read: `src/civpulse_geo/providers/base.py` — is_local property
- Direct source code read: `alembic/versions/g7d4e0f3a6b2_*` — most recent migration as template
- Direct source read: `.planning/phases/14-cascade-orchestrator-and-consensus-scoring/14-CONTEXT.md` — all locked decisions
- Python 3.12 stdlib documentation: `asyncio.gather`, `asyncio.wait_for`, `math` module — confirmed in training data (stable APIs, no version concerns)

### Secondary (MEDIUM confidence)
- Pydantic BaseSettings env var handling: confirmed against pyproject.toml dependency version (pydantic-settings>=2.13.1) and existing config.py usage pattern

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already installed, no new packages
- Architecture: HIGH — all patterns derived from existing codebase source reads + locked decisions in CONTEXT.md
- Pitfalls: HIGH — derived from direct reading of existing ORM/service code and known async patterns
- Open questions: MEDIUM — recommendations made but final choices are Claude's discretion (D-21 et al.)

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (stable libraries, no fast-moving dependencies)
