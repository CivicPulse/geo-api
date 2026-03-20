# Phase 4: Batch and Hardening - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Batch geocoding and batch validation endpoints with per-item error handling, completing the v1 HTTP surface. Callers can submit multiple addresses in a single request and receive per-item results with individual status codes. Single-address endpoints remain unchanged. No new providers, no new data models beyond batch-specific schemas.

Requirements covered: INFRA-03, INFRA-04, INFRA-06

</domain>

<decisions>
## Implementation Decisions

### Batch Response Format
- Each result item includes BOTH a positional `index` AND `original_input` echo — maximum debuggability for internal callers
- Response includes top-level summary counts: `total`, `succeeded`, `failed`
- Results array is ordered to match input array by position

### Batch Input Shape
- Batch geocode: `{"addresses": ["123 Main St, Macon GA", ...]}` — array of freeform strings
- Batch validate: same format — array of freeform strings only, no structured field input in batch (callers pre-concatenate if needed)
- Uniform input shape across both batch endpoints

### Routing
- Separate routes: `POST /geocode/batch` and `POST /validate/batch`
- Single-address endpoints (`POST /geocode`, `POST /validate`) remain unchanged
- Clean OpenAPI docs with no union-type ambiguity

### Per-Item Error Design
- Each result item has both `status_code` (int, HTTP-style: 200/422/500) AND `status` (string enum: "success"/"invalid_input"/"provider_error")
- Failed items include `error` object with `message` string; successful items have `error: null`
- Successful items include `data` object with the same shape as the single-address response; failed items have `data: null`

### Outer HTTP Status
- 200 for any batch with at least one success (including all-success)
- 422 when ALL items in the batch fail — signals total input failure to callers
- 422 also for request-level validation errors (empty addresses field, exceeded batch size)

### Batch Size Limits
- Maximum 100 addresses per batch request
- Exceeding the limit rejects the entire request with 422: "Batch size N exceeds maximum of 100 addresses"
- Empty batches (0 addresses) return 200 with total=0, succeeded=0, failed=0, results=[]
- Limit discoverable from error messages and API documentation only — no /limits endpoint
- Both `max_batch_size` and `batch_concurrency_limit` configurable via environment variables (Pydantic Settings in config.py), defaults: 100 and 10

### Concurrency Within Batch
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Core value proposition, constraints, tech stack, key decisions table
- `.planning/REQUIREMENTS.md` — Full v1 requirement list; Phase 4 covers INFRA-03, INFRA-04, INFRA-06
- `.planning/ROADMAP.md` — Phase goals, success criteria, dependency graph

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` — Canonical key strategy, schema design, plugin contract, project scaffolding
- `.planning/phases/03-validation-and-data-import/03-CONTEXT.md` — Validation provider strategy, response design, service patterns

### Code references
- `src/civpulse_geo/api/geocoding.py` — Geocoding router; pattern for batch geocode endpoint (dependency injection, Pydantic transform)
- `src/civpulse_geo/api/validation.py` — Validation router; pattern for batch validate endpoint
- `src/civpulse_geo/services/geocoding.py` — GeocodingService.geocode(); single-address method that batch will call per-item
- `src/civpulse_geo/services/validation.py` — ValidationService.validate(); single-address method that batch will call per-item
- `src/civpulse_geo/schemas/geocoding.py` — GeocodeRequest/GeocodeResponse; batch schemas will wrap these
- `src/civpulse_geo/schemas/validation.py` — ValidateRequest/ValidateResponse; batch schemas will wrap these
- `src/civpulse_geo/config.py` — Pydantic Settings; add batch_concurrency_limit and max_batch_size here

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GeocodingService.geocode()` — fully implemented single-address pipeline; batch calls this per-item
- `ValidationService.validate()` — fully implemented single-address pipeline; batch calls this per-item
- `ProviderError` exception hierarchy — batch catches these per-item to populate error fields
- `canonical_key()` / `parse_address_components()` — reused by single-address services, no batch changes needed
- Pydantic `GeocodeResponse` / `ValidateResponse` — batch `data` field mirrors these shapes

### Established Patterns
- Stateless services instantiated per-request with injected dependencies (db, providers, http_client)
- Cache-first pipeline: normalize → find/create address → check cache → call provider → upsert
- `ProviderError` → 422 for unparseable addresses (Phase 3 decision)
- Async endpoint handlers with `Depends(get_db)` for session management
- `INSERT ... ON CONFLICT DO UPDATE` for idempotent upserts

### Integration Points
- `main.py` router: include batch routes in existing geocoding and validation routers (or as new routers)
- `config.py` Settings: add `max_batch_size: int = 100` and `batch_concurrency_limit: int = 10`
- Each batch item reuses the same DB session — single transaction per batch request

</code_context>

<specifics>
## Specific Ideas

- Batch response is self-describing: callers can log `succeeded`/`failed` counts without iterating, then drill into individual `results[]` items for details
- The "422 when all fail" rule gives monitoring/alerting a quick signal for bad-input batches without parsing the response body
- Concurrency semaphore means a batch of mostly-cached addresses returns almost as fast as a single request — only cache misses slow it down

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-batch-and-hardening*
*Context gathered: 2026-03-19*
