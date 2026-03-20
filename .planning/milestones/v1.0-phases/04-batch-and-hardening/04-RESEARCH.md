# Phase 4: Batch and Hardening - Research

**Researched:** 2026-03-19
**Domain:** FastAPI batch endpoints, asyncio concurrency, Pydantic schemas, per-item error isolation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Batch Response Format**
- Each result item includes BOTH a positional `index` AND `original_input` echo — maximum debuggability for internal callers
- Response includes top-level summary counts: `total`, `succeeded`, `failed`
- Results array is ordered to match input array by position

**Batch Input Shape**
- Batch geocode: `{"addresses": ["123 Main St, Macon GA", ...]}` — array of freeform strings
- Batch validate: same format — array of freeform strings only, no structured field input in batch (callers pre-concatenate if needed)
- Uniform input shape across both batch endpoints

**Routing**
- Separate routes: `POST /geocode/batch` and `POST /validate/batch`
- Single-address endpoints (`POST /geocode`, `POST /validate`) remain unchanged
- Clean OpenAPI docs with no union-type ambiguity

**Per-Item Error Design**
- Each result item has both `status_code` (int, HTTP-style: 200/422/500) AND `status` (string enum: "success"/"invalid_input"/"provider_error")
- Failed items include `error` object with `message` string; successful items have `error: null`
- Successful items include `data` object with the same shape as the single-address response; failed items have `data: null`

**Outer HTTP Status**
- 200 for any batch with at least one success (including all-success)
- 422 when ALL items in the batch fail — signals total input failure to callers
- 422 also for request-level validation errors (empty addresses field, exceeded batch size)

**Batch Size Limits**
- Maximum 100 addresses per batch request
- Exceeding the limit rejects the entire request with 422: "Batch size N exceeds maximum of 100 addresses"
- Empty batches (0 addresses) return 200 with total=0, succeeded=0, failed=0, results=[]
- Limit discoverable from error messages and API documentation only — no /limits endpoint
- Both `max_batch_size` and `batch_concurrency_limit` configurable via environment variables (Pydantic Settings in config.py), defaults: 100 and 10

**Concurrency Within Batch**
- Addresses processed concurrently via asyncio.gather with asyncio.Semaphore
- Default concurrency limit: 10 simultaneous provider calls
- Cache hits resolve instantly (DB lookup only); only cache misses consume semaphore slots for external provider calls
- Full isolation: each address has independent error handling; a timeout/crash on one item does not cancel or affect others (asyncio.gather with return_exceptions=True)

### Claude's Discretion
- Exact Pydantic schema class names for batch request/response
- Whether batch service methods live in existing GeocodingService/ValidationService or a separate BatchService
- Test fixture design for batch error scenarios
- Error message wording for specific failure modes
- Whether to add a per-item `processing_time_ms` field

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-03 | API supports batch geocoding (multiple addresses in one request) with per-item results and error handling | `POST /geocode/batch` route calling `GeocodingService.geocode()` per item with asyncio.gather + Semaphore; BatchGeocodeRequest/BatchGeocodeResponse schemas |
| INFRA-04 | API supports batch address validation (multiple addresses in one request) with per-item results and error handling | `POST /validate/batch` route calling `ValidationService.validate()` per item with asyncio.gather + Semaphore; BatchValidateRequest/BatchValidateResponse schemas |
| INFRA-06 | Batch responses include per-item status codes and error messages for partial failures | Each `BatchResultItem` carries `index`, `original_input`, `status_code` (int), `status` (str enum), `data` (or null), `error` (or null); outer 422 only when ALL items fail |
</phase_requirements>

---

## Summary

Phase 4 adds two batch endpoints — `POST /geocode/batch` and `POST /validate/batch` — onto an already-working service layer. Both endpoints call the existing single-address service methods (`GeocodingService.geocode()` and `ValidationService.validate()`) per item inside an `asyncio.gather` with `return_exceptions=True`, so no single item failure can cancel another. A `asyncio.Semaphore` caps simultaneous external provider calls at a configurable limit (default 10), while cache hits bypass the semaphore entirely and return immediately from the DB.

The full design is locked in CONTEXT.md. The research task is to confirm the exact Python/FastAPI/Pydantic patterns that make this work cleanly — specifically: how `asyncio.gather(return_exceptions=True)` behaves with mixed success/exception results, how Pydantic v2 models best represent the nullable `data`/`error` union, how to wire a request-level Pydantic validator for the 100-item limit before processing begins, and how to surface the outer 422-vs-200 decision after collecting all item results.

The entire implementation is additive: no existing routes, services, or schemas are modified. New files are `schemas/batch.py` (or additions to `geocoding.py`/`validation.py`), service methods on existing service classes (or a thin `BatchService`), and two new route handlers appended to the existing routers.

**Primary recommendation:** Add `batch_geocode()` and `batch_validate()` methods directly to the existing service classes rather than creating a separate BatchService. This avoids an extra indirection layer; the batch method is simply a thin orchestrator that calls the already-tested single-address method per item.

---

## Standard Stack

### Core (already installed — no new dependencies needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.135.1 | Route handlers, HTTPException, response_model | Already in project |
| pydantic v2 | (via fastapi) | Request/response schemas, validators | Already in project |
| pydantic-settings | >=2.13.1 | Settings with env-var override | Already in project |
| asyncio | stdlib | `gather`, `Semaphore` for concurrency | stdlib, zero install cost |
| sqlalchemy asyncio | >=2.0.48 | Single DB session shared across batch items | Already in project |

### No new dependencies
All batch functionality is achievable with the current dependency set. `asyncio.gather` and `asyncio.Semaphore` are stdlib. Pydantic v2 `model_validator` handles limit enforcement. No queue library, no Celery, no Redis needed for synchronous batch.

**Version verification:** Confirmed via pyproject.toml — all packages already present.

---

## Architecture Patterns

### Recommended Project Structure

No new directories. New and modified files:

```
src/civpulse_geo/
├── config.py                      # Add max_batch_size, batch_concurrency_limit
├── schemas/
│   └── batch.py                   # New: BatchGeocodeRequest/Response, BatchValidateRequest/Response, BatchResultItem
├── services/
│   ├── geocoding.py               # Add batch_geocode() method
│   └── validation.py              # Add batch_validate() method
├── api/
│   ├── geocoding.py               # Add POST /geocode/batch route
│   └── validation.py              # Add POST /validate/batch route
tests/
├── test_batch_geocoding_api.py    # New: batch geocode endpoint tests
└── test_batch_validation_api.py   # New: batch validate endpoint tests
```

### Pattern 1: asyncio.gather with return_exceptions=True for full isolation

**What:** Run all per-item coroutines concurrently. Exceptions are returned as result values, not raised. The caller inspects each result and builds the per-item response.

**When to use:** Any batch where partial failure must not cancel other items.

```python
# Source: Python stdlib asyncio docs
import asyncio

async def _process_one(address: str, semaphore: asyncio.Semaphore, ...) -> dict | Exception:
    """Acquire semaphore only for cache-miss paths that call external providers."""
    # Cache hit check first — no semaphore needed
    # If cache miss: async with semaphore: await service.geocode(...)
    ...

results = await asyncio.gather(
    *[_process_one(addr, semaphore, ...) for addr in addresses],
    return_exceptions=True,
)
# results is a list where each element is either a dict (success) or an Exception instance
```

**Critical detail:** `return_exceptions=True` means the list always has exactly `len(addresses)` elements — one per input, in order. Exceptions are NOT raised; they appear as `Exception` objects in the results list. This is what enables positional `index` to be computed reliably.

### Pattern 2: asyncio.Semaphore to cap concurrency

**What:** A semaphore limits how many coroutines enter the "call external provider" block simultaneously. Cache hits skip the semaphore entirely.

**When to use:** Any scenario where external API calls must be rate-controlled.

```python
# Source: Python stdlib asyncio docs
semaphore = asyncio.Semaphore(settings.batch_concurrency_limit)

async def _geocode_one(freeform: str, semaphore: asyncio.Semaphore, db, providers, http_client):
    # 1. Normalize and do the DB cache check first — no semaphore
    # 2. If cache hit: return immediately without acquiring semaphore
    # 3. If cache miss:
    async with semaphore:
        return await geocoding_service.geocode(freeform, db=db, providers=providers, http_client=http_client)
```

**Important:** The existing `GeocodingService.geocode()` already performs cache check internally. For the semaphore to only wrap provider calls (not DB lookups), the batch handler calls the full service method and the semaphore is a blunt instrument that still works correctly — it just means DB-only requests also briefly hold a semaphore slot. Given cache hits complete in microseconds, this is acceptable and simpler than splitting the cache-check and provider-call phases.

### Pattern 3: Pydantic v2 request-level validator for batch size

**What:** `@model_validator(mode="after")` runs after field parsing. Use it to enforce the 100-item limit before the endpoint handler runs.

**When to use:** Request-level constraints that should return 422 before any processing begins.

```python
# Source: Pydantic v2 docs — model validators
from pydantic import BaseModel, model_validator
from fastapi import HTTPException

class BatchGeocodeRequest(BaseModel):
    addresses: list[str]

    @model_validator(mode="after")
    def check_batch_size(self) -> "BatchGeocodeRequest":
        from civpulse_geo.config import settings
        if len(self.addresses) > settings.max_batch_size:
            raise ValueError(
                f"Batch size {len(self.addresses)} exceeds maximum of {settings.max_batch_size} addresses"
            )
        return self
```

FastAPI converts `ValueError` raised inside a `model_validator` into a 422 response automatically, with the message in `detail[].msg`.

### Pattern 4: Outer HTTP status decision after gathering results

**What:** After `asyncio.gather`, count successes and failures, then decide the outer response status code.

**When to use:** Batch endpoints with the "422 only when ALL fail" rule.

```python
# Source: Established in CONTEXT.md; pattern is standard FastAPI
from fastapi import Response

@router.post("/batch")
async def batch_geocode(body: BatchGeocodeRequest, response: Response, ...):
    items = await _run_batch(body.addresses, ...)
    succeeded = sum(1 for i in items if i.status_code == 200)
    failed = len(items) - succeeded

    if succeeded == 0 and failed > 0:
        response.status_code = 422

    return BatchGeocodeResponse(
        total=len(items),
        succeeded=succeeded,
        failed=failed,
        results=items,
    )
```

**Why `Response` injection:** FastAPI lets you inject the `Response` object and mutate `status_code` before the router serializes it. This is the correct pattern for conditional status codes when `response_model` is used. Alternatively, raise `HTTPException(status_code=422, detail=batch_response)` — but the `Response` injection approach keeps the response body typed via `response_model`.

**Recommendation:** Use `JSONResponse` directly when all-fail to avoid dual-path schema complexity. Raise `HTTPException(status_code=422, detail=response_dict)` when all items fail, and return the `BatchResponse` Pydantic model normally for mixed/all-success cases. This avoids the `Response` injection complexity and keeps the success path typed.

### Pattern 5: Per-item result schema with nullable data/error

**What:** Each item in the results array is always present (positional guarantee), with fields set based on success or failure.

```python
# Source: CONTEXT.md decisions
from pydantic import BaseModel
from typing import Any

class BatchItemError(BaseModel):
    message: str

class BatchGeocodeResultItem(BaseModel):
    index: int
    original_input: str
    status_code: int          # 200, 422, or 500
    status: str               # "success", "invalid_input", "provider_error"
    data: GeocodeResponse | None = None
    error: BatchItemError | None = None

class BatchGeocodeResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[BatchGeocodeResultItem]
```

### Pattern 6: Exception-to-status mapping for per-item results

**What:** After `asyncio.gather(return_exceptions=True)`, each exception type maps to a specific per-item `status_code` and `status`.

```python
# Source: CONTEXT.md per-item error design + existing ProviderError hierarchy
from civpulse_geo.providers.exceptions import ProviderError

def _classify_exception(exc: Exception) -> tuple[int, str, str]:
    """Returns (status_code, status, message)."""
    if isinstance(exc, ProviderError):
        # ProviderError maps to 422 for unparseable addresses (Phase 3 decision)
        # ProviderNetworkError/ProviderRateLimitError map to 500 (provider_error)
        from civpulse_geo.providers.exceptions import ProviderNetworkError, ProviderRateLimitError, ProviderAuthError
        if isinstance(exc, (ProviderNetworkError, ProviderRateLimitError, ProviderAuthError)):
            return 500, "provider_error", str(exc)
        return 422, "invalid_input", str(exc)
    # Unexpected exception — treat as provider_error
    return 500, "provider_error", f"Unexpected error: {type(exc).__name__}"
```

### Anti-Patterns to Avoid

- **Nested asyncio.gather without return_exceptions=True:** The default behavior raises the first exception and cancels remaining tasks. Always use `return_exceptions=True` for batch isolation.
- **Creating a new DB session per batch item:** Each batch request uses a single shared `AsyncSession`. Per-item DB operations within the batch do NOT commit individually — commit once after all items complete (or handle per-item commits carefully to avoid partial state). Given the existing service methods each call `db.commit()`, understand that within `asyncio.gather` these may interleave. See Pitfall 2 below.
- **Raising HTTPException from inside per-item processing:** HTTPException raised inside a `gather` coroutine becomes an unhandled exception result. Per-item errors must be caught and converted to result objects, never re-raised as HTTPException.
- **Using `asyncio.wait` instead of `asyncio.gather`:** `gather` preserves order matching the input list, which is required for the positional `index` guarantee. `wait` returns sets, not ordered lists.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-item error isolation | Custom try/except wrapper tasks | `asyncio.gather(return_exceptions=True)` | Stdlib handles cancellation, ordering, and exception capture correctly |
| Concurrency limiting | Manual task counting or semaphore reimplementation | `asyncio.Semaphore` | Stdlib; correct behavior with async context manager |
| Request-level validation (batch size) | Manual check in endpoint handler | Pydantic `model_validator` | FastAPI automatically converts ValueError to 422 before handler runs |
| Env-configurable limits | Hardcoded constants | `pydantic_settings.BaseSettings` fields | Already in project; Settings already loaded at startup |
| Response schema | Custom dict building | Pydantic `BaseModel` with `response_model=` | FastAPI serialization, OpenAPI docs, type safety |

**Key insight:** The entire batch implementation is assembling existing stdlib and Pydantic primitives. The project already has every tool needed.

---

## Common Pitfalls

### Pitfall 1: DB session commit interleaving with asyncio.gather

**What goes wrong:** The existing `GeocodingService.geocode()` and `ValidationService.validate()` each call `await db.commit()` internally. When N items share the same DB session and run concurrently via `asyncio.gather`, each item commits mid-batch. Under asyncio (single-threaded cooperative multitasking), only one coroutine runs at a time at each `await`, so there is no true race condition — but commits interleave. If one item fails after others have committed, the failed item's partial state (Address record created in Step 2) will be committed by a prior item's commit if they share the same address hash, or left uncommitted if the session rolls back.

**Why it happens:** The services were designed for single-request use with their own commit semantics.

**How to avoid:** Accept that Address records may be written even for items that later fail in the provider call. This is safe — the address row is idempotent (upsert-on-conflict pattern). Failed items produce no GeocodingResult/ValidationResult rows. The batch response correctly reflects the failure. No data corruption occurs.

**Warning signs:** Test failures showing "address exists" or unexpected cache hits when running batch tests with repeated addresses.

### Pitfall 2: asyncio.gather ordering guarantee

**What goes wrong:** Assuming the result order from `asyncio.gather` might differ from input order.

**Why it happens:** Misreading asyncio docs or confusing with `asyncio.wait`.

**How to avoid:** `asyncio.gather` always returns results in the same order as the awaitables passed. Use `enumerate(addresses)` to assign `index` values when building the input coroutine list, and rely on result position for `index`. HIGH confidence: this is a stdlib guarantee documented in the Python asyncio reference.

### Pitfall 3: Semaphore created outside async context

**What goes wrong:** `asyncio.Semaphore(N)` created at module level (outside an event loop) may raise `RuntimeError: no running event loop` in Python 3.10+.

**Why it happens:** Python 3.10 deprecated implicit event loop creation. Creating asyncio primitives at module/class level hits this.

**How to avoid:** Create the `Semaphore` inside the endpoint handler function (per-request), or inside the batch service method. Since a batch request lasts the duration of one gather call, per-request semaphore creation is correct and cheap.

```python
@router.post("/batch")
async def batch_geocode(body: BatchGeocodeRequest, ...):
    semaphore = asyncio.Semaphore(settings.batch_concurrency_limit)
    ...
```

### Pitfall 4: Empty batch returning wrong HTTP status

**What goes wrong:** An empty `addresses: []` triggers the "all failed" check if succeeded == 0 and failed == 0. The condition `succeeded == 0 and failed > 0` must not fire for an empty batch.

**Why it happens:** Off-by-one in the condition check.

**How to avoid:** Condition for outer 422 is: `len(addresses) > 0 and succeeded == 0`. An empty batch returns 200 with counts all zero per the CONTEXT.md decision.

### Pitfall 5: model_validator import cycle for Settings reference

**What goes wrong:** Importing `settings` inside a Pydantic `model_validator` using a top-level import causes circular import if `schemas/batch.py` imports from `config.py` which imports from somewhere that imports schemas.

**Why it happens:** The project's `config.py` is currently standalone (no imports from the project), so this is LOW risk. But the validator needs the settings value.

**How to avoid:** Import `settings` at the top of `schemas/batch.py` — `config.py` has no project imports, so no cycle. Alternatively, pass the limit as a class variable with a default and override in tests.

### Pitfall 6: response_model and 422 all-fail path

**What goes wrong:** If using `response_model=BatchGeocodeResponse` on the route decorator, and the all-fail path returns a dict (from `HTTPException.detail`), FastAPI will not validate it against the schema — the 422 exception bypasses the response model.

**Why it happens:** `HTTPException` is handled by FastAPI's exception handler, not the response model serializer.

**How to avoid:** For the all-fail path, raise `HTTPException(status_code=422, detail=batch_response.model_dump())`. The `detail` field will contain the full batch response body. Callers receive a valid JSON body at 422. Alternatively, use `JSONResponse(status_code=422, content=batch_response.model_dump())` returned from the endpoint — this bypasses the response model and sets the status code explicitly.

**Recommended approach:** Use `JSONResponse` directly:
```python
from fastapi.responses import JSONResponse

if succeeded == 0 and len(body.addresses) > 0:
    return JSONResponse(status_code=422, content=response.model_dump())
return response
```

---

## Code Examples

Verified patterns from the existing codebase and stdlib:

### Config additions to config.py

```python
# Source: Existing config.py pattern + CONTEXT.md decisions
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://..."
    database_url_sync: str = "postgresql+psycopg2://..."
    log_level: str = "INFO"
    environment: str = "development"
    max_batch_size: int = 100
    batch_concurrency_limit: int = 10
```

### Batch request schema with size validator

```python
# Source: Pydantic v2 docs + CONTEXT.md
from pydantic import BaseModel, model_validator
from civpulse_geo.config import settings

class BatchGeocodeRequest(BaseModel):
    addresses: list[str]

    @model_validator(mode="after")
    def check_batch_size(self) -> "BatchGeocodeRequest":
        if len(self.addresses) > settings.max_batch_size:
            raise ValueError(
                f"Batch size {len(self.addresses)} exceeds maximum of {settings.max_batch_size} addresses"
            )
        return self
```

### Core asyncio.gather pattern with Semaphore

```python
# Source: Python 3.12 asyncio stdlib docs
import asyncio
from civpulse_geo.providers.exceptions import ProviderError, ProviderNetworkError, ProviderRateLimitError, ProviderAuthError

async def _geocode_one_with_semaphore(
    index: int,
    freeform: str,
    semaphore: asyncio.Semaphore,
    service: GeocodingService,
    db: AsyncSession,
    providers: dict,
    http_client: httpx.AsyncClient,
) -> BatchGeocodeResultItem:
    try:
        async with semaphore:
            result = await service.geocode(
                freeform=freeform, db=db, providers=providers, http_client=http_client
            )
        # Build success item from result dict
        data = GeocodeResponse(
            address_hash=result["address_hash"],
            normalized_address=result["normalized_address"],
            cache_hit=result["cache_hit"],
            results=[...],  # transform ORM rows to Pydantic
            official=...,
        )
        return BatchGeocodeResultItem(
            index=index,
            original_input=freeform,
            status_code=200,
            status="success",
            data=data,
            error=None,
        )
    except Exception as exc:
        status_code, status, message = _classify_exception(exc)
        return BatchGeocodeResultItem(
            index=index,
            original_input=freeform,
            status_code=status_code,
            status=status,
            data=None,
            error=BatchItemError(message=message),
        )


async def batch_geocode_items(addresses, settings, service, db, providers, http_client):
    semaphore = asyncio.Semaphore(settings.batch_concurrency_limit)
    tasks = [
        _geocode_one_with_semaphore(i, addr, semaphore, service, db, providers, http_client)
        for i, addr in enumerate(addresses)
    ]
    return await asyncio.gather(*tasks, return_exceptions=False)
    # Note: return_exceptions=False is correct here because per-item exceptions
    # are caught INSIDE each task coroutine. The gather itself never sees exceptions.
```

### Endpoint handler with conditional status

```python
# Source: FastAPI docs + CONTEXT.md outer status logic
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from civpulse_geo.database import get_db
from civpulse_geo.services.geocoding import GeocodingService
from civpulse_geo.schemas.batch import BatchGeocodeRequest, BatchGeocodeResponse

@router.post("/batch")
async def batch_geocode(
    body: BatchGeocodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not body.addresses:
        return BatchGeocodeResponse(total=0, succeeded=0, failed=0, results=[])

    service = GeocodingService()
    items = await batch_geocode_items(
        body.addresses, settings, service, db,
        request.app.state.providers, request.app.state.http_client
    )

    succeeded = sum(1 for item in items if item.status_code == 200)
    failed = len(items) - succeeded
    response_body = BatchGeocodeResponse(
        total=len(items),
        succeeded=succeeded,
        failed=failed,
        results=items,
    )

    if succeeded == 0 and failed > 0:
        return JSONResponse(status_code=422, content=response_body.model_dump())
    return response_body
```

### Test pattern for batch — mocking the service method

```python
# Source: Existing test_geocoding_api.py patterns in this project
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from civpulse_geo.main import app

@pytest.mark.asyncio
async def test_batch_geocode_partial_failure(patched_app_state):
    """Batch with one success and one failure returns 200 with mixed results."""
    from civpulse_geo.providers.exceptions import ProviderError
    from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM
    from unittest.mock import MagicMock

    success_row = MagicMock(spec=GeocodingResultORM)
    success_row.provider_name = "census"
    success_row.latitude = 38.845
    success_row.longitude = -76.928
    success_row.location_type = None
    success_row.confidence = 0.8

    call_count = 0

    async def mock_geocode_side_effect(freeform, db, providers, http_client, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "address_hash": "a" * 64,
                "normalized_address": freeform.upper(),
                "cache_hit": False,
                "results": [success_row],
                "official": None,
            }
        raise ProviderError("Address unparseable")

    with patch(
        "civpulse_geo.services.geocoding.GeocodingService.geocode",
        new_callable=AsyncMock,
        side_effect=mock_geocode_side_effect,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/geocode/batch",
                json={"addresses": ["123 Main St Macon GA", "garbage input"]},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "success"
    assert data["results"][1]["status"] == "invalid_input"
    assert data["results"][1]["data"] is None
    assert data["results"][1]["error"]["message"] is not None
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sequential for-loop over addresses | `asyncio.gather` with concurrent coroutines | Python 3.4+ asyncio | Batch of 100 addresses with cache hits completes in ~1 provider call's latency, not 100x |
| Global event loop (Python < 3.10) | Per-request semaphore creation inside async function | Python 3.10 | Semaphore must be created inside running event loop |
| Pydantic v1 `@validator` | Pydantic v2 `@model_validator(mode="after")` | Pydantic v2 (2023) | `mode="after"` receives the model instance, not field values; `mode="before"` for raw dict access |

**Deprecated/outdated:**
- `asyncio.coroutine` decorator: use `async def` only (deprecated Python 3.8, removed 3.11)
- `loop.run_until_complete()`: not needed inside FastAPI async handlers
- Pydantic v1 `@validator`: this project uses Pydantic v2; use `@model_validator` or `@field_validator`

---

## Open Questions

1. **Semaphore scope: per-request vs per-batch-method**
   - What we know: Per-request semaphore creation (inside endpoint handler) is idiomatic and correct.
   - What's unclear: Whether there's a need for a global rate-limit across concurrent batch requests (e.g., two simultaneous batch-100 requests = 200 concurrent provider calls).
   - Recommendation: Start with per-request semaphore. This is sufficient for current single-internal-caller use case. Cross-request rate limiting is out of scope per REQUIREMENTS.md.

2. **DB session and concurrent asyncio.gather with shared session**
   - What we know: SQLAlchemy async sessions are NOT thread-safe but ARE safe for asyncio cooperative multitasking (only one coroutine runs at each await point). Tests confirm single-address service methods work correctly.
   - What's unclear: Whether multiple concurrent `await db.execute()` calls within `asyncio.gather` can interleave in unexpected ways given SQLAlchemy's async session internal buffering.
   - Recommendation: This is MEDIUM confidence. The SQLAlchemy asyncio docs explicitly state the session is designed for asyncio cooperative use. Since only one coroutine runs per `await`, ordering is deterministic. Proceed with shared session. Flag in code comments.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | pyproject.toml — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-03 | POST /geocode/batch with N addresses returns N results | unit | `uv run pytest tests/test_batch_geocoding_api.py -x` | ❌ Wave 0 |
| INFRA-03 | One failing address does not prevent other results | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_partial_failure -x` | ❌ Wave 0 |
| INFRA-03 | Exceeding 100 addresses returns 422 before processing | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_exceeds_limit -x` | ❌ Wave 0 |
| INFRA-03 | Empty addresses array returns 200 with zero counts | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_empty -x` | ❌ Wave 0 |
| INFRA-04 | POST /validate/batch with N addresses returns N results | unit | `uv run pytest tests/test_batch_validation_api.py -x` | ❌ Wave 0 |
| INFRA-04 | One failing validation does not prevent other results | unit | `uv run pytest tests/test_batch_validation_api.py::test_batch_validate_partial_failure -x` | ❌ Wave 0 |
| INFRA-06 | Each item has status_code, status, data/error fields | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_response_structure -x` | ❌ Wave 0 |
| INFRA-06 | All-fail batch returns outer 422 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_all_fail_returns_422 -x` | ❌ Wave 0 |
| INFRA-06 | Mixed batch returns outer 200 | unit | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_partial_failure -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_batch_geocoding_api.py` — covers INFRA-03 and INFRA-06 (geocode path)
- [ ] `tests/test_batch_validation_api.py` — covers INFRA-04 and INFRA-06 (validate path)

*(conftest.py and all fixtures already exist — no framework install needed)*

---

## Sources

### Primary (HIGH confidence)
- Python 3.12 asyncio stdlib — `asyncio.gather`, `asyncio.Semaphore`, `return_exceptions` behavior
- Pydantic v2 docs — `model_validator(mode="after")`, ValueError → 422 conversion
- Existing project source files — `services/geocoding.py`, `services/validation.py`, `api/geocoding.py`, `api/validation.py`, `config.py`, `tests/conftest.py`
- `pyproject.toml` — confirmed dependency versions and pytest configuration

### Secondary (MEDIUM confidence)
- FastAPI docs (response_model, JSONResponse, Request injection patterns) — consistent with existing codebase usage
- SQLAlchemy asyncio docs — session cooperative multitasking safety claim

### Tertiary (LOW confidence)
- SQLAlchemy asyncio session behavior with multiple concurrent gather tasks sharing one session — not directly tested in prior phases; marked in Open Questions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already in pyproject.toml, no new installs
- Architecture: HIGH — locked decisions in CONTEXT.md, patterns verified against existing codebase
- Pitfalls: HIGH (Pitfalls 1-4) / MEDIUM (Pitfall 5-6) — based on stdlib docs and existing code inspection
- Test patterns: HIGH — conftest.py and test patterns already established in tests/

**Research date:** 2026-03-19
**Valid until:** 2026-05-01 (stable stdlib and FastAPI patterns; Pydantic v2 API stable)
