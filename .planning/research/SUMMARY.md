# Project Research Summary

**Project:** CivPulse Geo API
**Domain:** Internal geocoding and address validation caching API
**Researched:** 2026-03-19
**Confidence:** MEDIUM (no external tooling available; all findings from training data, knowledge cutoff August 2025)

## Executive Summary

CivPulse Geo API is an internal caching proxy that sits between CivPulse microservices and multiple geocoding / address validation providers. The defining characteristic is that it stores every provider's result as a distinct row, then exposes an "official" record per address that an admin can override. This is not a thin geocoding wrapper — it is a canonical address registry with a multi-provider comparison and override workflow at its core. The de facto approach for this kind of system is: lazy-populate a PostGIS-backed cache keyed on a normalized form of the input address, fan out to providers concurrently on cache miss, persist raw responses for durability, and expose an explicit official-record pointer rather than deriving priority at query time.

The recommended stack is FastAPI + SQLAlchemy 2 async + asyncpg + PostGIS + GeoAlchemy2, with httpx for external provider calls and tenacity for retry. Address normalization uses usaddress + usaddress-scourgify offline, with USPS v3 API as the authoritative validation source. The plugin contract for providers should be defined early — it gates every provider integration and all future extensions. uv, ruff, mypy, and pytest round out the development environment; the test suite must run against a real PostGIS instance (pytest-postgresql) because PostGIS spatial functions cannot be meaningfully mocked.

The highest-risk areas are: (1) cache key design — normalization must happen before the cache lookup, not after; (2) Google Maps ToS — caching results outside a Google Map context may violate the platform agreement and must be reviewed before building the adapter; (3) the PostGIS geometry/geography distinction — distances in meters require the `geography` type or explicit casts, and the schema choice cannot be cheaply changed after data accumulates; and (4) USPS API continuity — the v3 OAuth migration broke many integrations and the library-based scourgify fallback must be planned from the start.

---

## Key Findings

### Recommended Stack

The project stack is largely pre-decided (FastAPI, Python 3.12+, PostgreSQL/PostGIS, Loguru, Typer). The key decisions in the research concern the integration glue: SQLAlchemy 2 async with GeoAlchemy2 is the correct ORM/spatial bridge for this combination — it handles WKB serialization, Alembic migration types, and async session management cleanly. asyncpg is the required driver. For external HTTP calls, httpx with tenacity provides async-native, retry-capable clients; using requests in an async app is an antipattern. The Google Maps official client (`googlemaps`) and boto3 cover two of the five providers; USPS and Geoapify use httpx directly because no maintained Python clients exist for them.

See `.planning/research/STACK.md` for full version table and alternatives considered.

**Core technologies:**
- FastAPI 0.111+ + Uvicorn: HTTP layer — pre-decided, async-native, OpenAPI autodoc
- SQLAlchemy 2.0 async + asyncpg 0.29+: ORM + driver — the only combination with clean GeoAlchemy2 support and async sessions
- GeoAlchemy2 0.14+: PostGIS bridge — handles WKB serialization and Alembic geometry column migrations
- PostGIS 3.4+ with `geography(Point, 4326)`: spatial storage — use `geography` not `geometry` to get distance-in-meters semantics automatically
- httpx 0.27+ + tenacity 8.3+: external HTTP — async-native, unified sync/async API, clean retry with exponential backoff
- usaddress 0.5.10 + usaddress-scourgify 0.4.1: offline address parsing and USPS normalization — offline fallback that generates cache keys without hitting external APIs
- pydantic-settings 2.3+: env-var config — manages the five sets of external API credentials cleanly
- pytest + pytest-asyncio + pytest-postgresql + respx: test stack — real PostGIS instance is required; mock httpx for provider calls

**Version validation needed before pinning:** usaddress, usaddress-scourgify, censusgeocode (all low-activity packages), and the USPS v3 API OAuth endpoint URLs.

---

### Expected Features

The feature set is tightly scoped. The core loop is: normalize input → cache lookup → fan out to providers on miss → store all results → return official record. Everything else is layered on top of this loop.

See `.planning/research/FEATURES.md` for full feature table and dependency graph.

**Must have (table stakes):**
- Single-address forward geocoding with cache hit/miss indicator
- Single-address address validation with USPS standardization and ranked suggestions
- Freeform and structured field input for both operations
- Confidence/accuracy score on geocode results, normalized across providers
- Batch geocoding and batch validation endpoints (stated requirement)
- Per-item status in batch responses — partial failures must not silently drop results
- Health/readiness endpoint with DB connectivity check

**Should have (differentiators):**
- Multi-provider result storage — each provider result is a distinct row, not a merged record
- Admin-overridable "official" geocode record — explicit pointer, not derived priority ranking
- Custom admin coordinate (not from any provider) for known landmark corrections
- Plugin-style provider registration — new providers added by config, not code surgery
- Input normalization before cache lookup — "123 Main Street" and "123 Main St" must hit the same cache entry
- Manual cache refresh endpoint — required because the cache never expires by design
- USPS library-based normalization fallback for when USPS API is unavailable

**Defer to v2+:**
- Reverse geocoding (no stated use case yet)
- Per-provider result retrieval endpoint (admin UI is a separate system)
- ZIP+4 delivery point validation (validate basic USPS normalization first)
- Geographic area / radius search queries
- Audit trail for admin overrides

**Explicit anti-features (do not build):**
- Authentication/API keys — internal service, network-isolated
- Cache TTL/expiration — addresses rarely change; manual refresh is sufficient
- International addresses — US-only for v1
- Rate limiting, webhooks, autocomplete, routing

---

### Architecture Approach

The recommended architecture is a clean four-layer design: FastAPI (transport + input validation) → Service layer (CacheService, GeocodingOrchestrator, ValidationOrchestrator) → Provider layer (ProviderRegistry + concrete adapters) → Persistence layer (repositories + PostgreSQL/PostGIS). The key structural decision is the data model: a separate `addresses` table (canonical identity, cache key), `geocoding_results` table (one row per address/provider pair), `validation_results` table (one row per address/provider pair), and `official_geocoding` table (one row per address with an explicit FK to the chosen result or a custom coordinate). The official record is an explicit pointer — never a runtime priority ranking.

See `.planning/research/ARCHITECTURE.md` for full component table, data model DDL, provider plugin contract, and suggested build order.

**Major components:**
1. **FastAPI layer** — HTTP transport, Pydantic validation, batch splitting, response shaping; never calls DB or providers directly
2. **CacheService** — checks DB before any external call; coordinates cache-miss flow; central to every request path
3. **GeocodingOrchestrator** — calls all enabled providers via asyncio.gather, persists results, triggers official record derivation
4. **ValidationOrchestrator** — normalizes input, calls validation providers, ranks suggestions, persists
5. **ProviderRegistry** — holds registered providers; isolates per-provider failures so one timeout doesn't fail the request
6. **OfficialRecordService + AdminOverrideService** — maintains the single official point per address; accepts admin-supplied coordinates or provider result selection
7. **Repository layer** — pure data access (AddressRepository, GeocodingResultRepository, ValidationResultRepository, OfficialGeocodingRepository); no business logic

**Key patterns:**
- Cache-aside (lazy population) — never pre-warm; hit rate improves naturally as addresses accumulate
- Provider fault isolation — each provider call in try/except; partial results are better than errors
- Idempotent persistence — INSERT ... ON CONFLICT DO NOTHING on (address_id, provider)
- Raw response preservation — store full provider JSON in JSONB alongside extracted fields; provider APIs evolve

---

### Critical Pitfalls

The following five pitfalls are data-model-level or legal — they are expensive or impossible to fix after the fact.

1. **Cache key on raw input string** — "123 Main St" and "123 Main Street" miss each other. Normalize to canonical form (USPS abbreviations, uppercase, stripped punctuation) *before* any cache lookup. Store raw input separately for debugging. Address this in Phase 1 before any caching logic is written.

2. **Lat/lon as FLOAT columns instead of PostGIS geography** — Every future spatial query requires a migration and manual Haversine math. Use `GEOGRAPHY(POINT, 4326)` from day one. Add GiST index immediately. Note: ST_MakePoint takes longitude first, then latitude — this ordering trips up nearly everyone.

3. **Two-table separation of address identity from provider results** — The canonical `addresses` table (one row per unique address, holds the canonical key and parsed fields) must be separate from `geocoding_results` (one row per address/provider pair). A single-table design makes the admin override workflow and cross-provider comparison impossible without schema surgery.

4. **Google Maps Platform ToS on caching** — Google's terms prohibit caching geocoding results for use outside a Google Map display context. This must be reviewed before building the Google adapter. Census Geocoder (free, no caching restrictions) should be the primary provider for initial development; Google treated as optional/fallback after legal review.

5. **USPS API as single point of failure** — The USPS v3 OAuth API has a migration history of breaking changes. The validation pipeline must have a library-based fallback (usaddress-scourgify) that standardizes format without hitting USPS. This fallback does not validate deliverability but is sufficient for cache key generation and format normalization.

See `.planning/research/PITFALLS.md` for the full 15-pitfall catalog including moderate pitfalls (no confidence normalization across providers, batch endpoint HTTP status semantics, "not found" vs "error" caching distinction).

---

## Implications for Roadmap

The build order is constrained by hard dependencies: the data model and canonical key strategy must exist before any caching logic; the provider plugin contract must exist before any provider adapters; single-address flows must work before batch flows. The architecture research provides an explicit 9-step build order that maps directly to phases.

---

### Phase 1: Foundation — Data Model, Schema, and Canonical Key

**Rationale:** Everything depends on the database schema and the canonical key strategy. Getting the data model wrong (FLOAT columns, single-table design, wrong PostGIS type) is the most expensive class of mistake in this domain. Build this before any application code.

**Delivers:** PostgreSQL/PostGIS schema with migrations; canonical address normalization function; AddressRepository; GeocodingResultRepository; ValidationResultRepository; OfficialGeocodingRepository; project scaffolding (FastAPI app shell, pydantic-settings config, Loguru logging, uv/ruff/mypy/pre-commit toolchain).

**Addresses:** Input normalization (table stakes), multi-provider result storage (differentiator), admin official record (differentiator).

**Avoids:** Pitfall 1 (cache key on raw input), Pitfall 2 (FLOAT columns), Pitfall 3 (single-table design), Pitfall 7 (admin override conflated with service results), Pitfall 8 (geometry vs. geography SRID), Pitfall 11 (coordinate precision).

**Research flag:** No deep research needed — PostGIS schema design and GeoAlchemy2 integration are well-documented patterns.

---

### Phase 2: Provider Plugin Contract + First Provider (Census)

**Rationale:** The plugin contract gates all provider work. Validate it with Census (free, no API key, no ToS concerns) before investing in the other four providers. This phase proves the CacheService + GeocodingOrchestrator end-to-end loop.

**Delivers:** GeocodingProvider and ValidationProvider abstract base classes; ProviderRegistry with explicit registration; CensusGeocodingProvider concrete implementation; CacheService (cache-miss flow); GeocodingOrchestrator (single provider, single address); end-to-end test: input → normalize → cache miss → Census → persist → return.

**Addresses:** Plugin-style provider architecture (differentiator), cache hit/miss indicator (table stakes).

**Avoids:** Pitfall 5 (parser failures swallowed silently — build the failure path explicitly here), Pitfall 14 (plugin architecture that requires restart to add providers), Pitfall 15 ("not found" vs "error" cache distinction).

**Research flag:** Verify Census Geocoder current response schema before building the adapter. Documentation URLs may have changed since training data cutoff.

---

### Phase 3: Remaining Geocoding Providers + Confidence Normalization

**Rationale:** Once the plugin contract is proven, remaining providers are parallel work. Confidence normalization must happen at the adapter level — each adapter maps its native score to the internal 0.0–1.0 scale. This is the phase where Google ToS must be resolved.

**Delivers:** GoogleGeocodingProvider (pending ToS review), AmazonLocationProvider (via boto3), GeoapifyProvider (via httpx), confidence normalization to internal scale for all providers; OfficialRecordService (auto-derive official record from highest-confidence provider result after all providers have run).

**Addresses:** Multi-provider result storage (differentiator), confidence/accuracy score (table stakes).

**Avoids:** Pitfall 4 (Google ToS — must be explicitly reviewed and documented before merging Google adapter), Pitfall 10 (confidence scores incomparable — normalize in each adapter).

**Research flag:** Google Maps Platform ToS requires explicit verification before the adapter is built. Amazon Location Service response schema should be verified against current AWS docs.

---

### Phase 4: USPS Validation Provider + Validation Pipeline

**Rationale:** Validation is architecturally parallel to geocoding but USPS v3 OAuth is a complex integration. Build it after geocoding providers are proven to avoid mixing two complex integrations in the same phase.

**Delivers:** USPSValidationProvider with OAuth2 token management; ValidationOrchestrator; ranked suggestion list with confidence scores; USPS library-based fallback (usaddress-scourgify) when API is unavailable; validation result caching.

**Addresses:** USPS standardization (table stakes), ranked suggestions with confidence (differentiator), ZIP+4 (optional for v1 — validate basic flow first).

**Avoids:** Pitfall 9 (USPS as single point of failure — implement library fallback in this phase, not later), Pitfall 13 (PO Box / rural route / APO address edge cases — add explicit test cases at implementation time).

**Research flag:** USPS v3 API OAuth2 endpoint URLs and token flow must be verified against current USPS documentation before implementation. Training data may be stale on the exact auth flow.

---

### Phase 5: Admin Override Endpoints + Official Record Management

**Rationale:** Admin override depends on having geocoding results to override. Build this after providers are wired and producing results. This is the core differentiator of the service.

**Delivers:** AdminOverrideService; PATCH /addresses/{id}/official endpoint (accepts provider_result_id or custom lat/lon); is_admin_override flag and override_note on official_geocoding; manual cache refresh endpoint (force re-query from live providers for a specific address).

**Addresses:** Admin-overridable official record (differentiator), custom admin coordinate (differentiator), manual cache refresh (differentiator).

**Avoids:** Pitfall 7 (admin override conflated with service results — explicit official_geocoding table with is_admin_override flag).

**Research flag:** No deep research needed — this is internal business logic derived directly from PROJECT.md requirements.

---

### Phase 6: Batch Endpoints + HTTP Layer Hardening

**Rationale:** Batch endpoints are fan-out over the single-address path. Build last because they add error-handling complexity that is easier to reason about once the single-address paths are solid.

**Delivers:** POST /geocode/batch and POST /validate/batch; asyncio.gather fan-out with per-item status; HTTP 200 always for batch (per-item status in body, not HTTP error codes); health/readiness endpoint with DB connectivity check; full FastAPI endpoint layer for all single-address operations.

**Addresses:** Batch geocoding and validation (table stakes), health endpoint (table stakes), per-item error details (table stakes).

**Avoids:** Pitfall 6 (no idempotency in batch — cache-first per item makes retries nearly free), Pitfall 12 (all-or-nothing HTTP status for batch — always 200, per-item status in body).

**Research flag:** No deep research needed — batch patterns are well-documented.

---

### Phase Ordering Rationale

- Phase 1 before everything: the data model is the load-bearing foundation. Wrong decisions here (FLOAT columns, single-table) are irreversible at scale.
- Phase 2 before Phase 3: the plugin contract must be proven with one provider before adding four more. Census is the correct first provider because it has no API key requirement and no ToS concerns.
- Phase 3 before Phase 5: admin override requires geocoding results to exist; providers must be running before admin override is meaningful.
- Phase 4 (USPS) is decoupled from Phases 2-3: validation and geocoding share the CacheService and repository patterns but USPS integration is its own complex API. Parallelizing Phases 3 and 4 is feasible if there are separate engineers.
- Phase 6 last: batch is fan-out complexity on top of solid single-address logic. Adding batch complexity before the single-address path is hardened creates debugging difficulty.

---

### Research Flags

Phases needing deeper research or external validation during planning:

- **Phase 2:** Verify Census Geocoder current response schema (field names may have changed; API endpoint may have version-incremented).
- **Phase 3:** Google Maps Platform ToS caching clause requires explicit legal/procurement review before the adapter is built — not just documentation reading. Also verify Amazon Location Service geocoding response schema against current AWS docs.
- **Phase 4:** USPS v3 API OAuth2 flow is the highest-uncertainty external dependency in the project. Verify current token endpoint, grant type, and scopes at https://www.usps.com/business/web-tools-apis/ before starting implementation.

Phases with well-documented standard patterns (deep research not needed):

- **Phase 1:** PostGIS schema design, GeoAlchemy2 Alembic migrations, and SQLAlchemy 2 async session setup are extensively documented.
- **Phase 5:** Admin override logic is internal business logic derived from PROJECT.md; no external research needed.
- **Phase 6:** Batch fan-out with asyncio.gather and per-item response semantics are standard FastAPI patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core framework choices are pre-decided (HIGH). GeoAlchemy2 + asyncpg combination is well-established (HIGH). usaddress and censusgeocode version numbers should be verified on PyPI before pinning — no external tooling available during research. |
| Features | MEDIUM | Table stakes and admin override workflow derived from PROJECT.md (HIGH). Provider-specific features (USPS DPV codes, Census response fields) not verified against current API docs due to tooling restrictions. |
| Architecture | HIGH | Layered architecture, cache-aside, plugin contract, and two-table data model are well-established patterns with broad consensus. Not dependent on live documentation. |
| Pitfalls | MEDIUM | All pitfalls are well-documented failure patterns in geocoding systems and PostGIS usage (MEDIUM-HIGH). Google ToS and USPS API state require live verification — training data may be stale. |

**Overall confidence:** MEDIUM

---

### Gaps to Address

- **Google Maps ToS caching clause:** Training data documents a caching restriction; current ToS must be read and a decision made before building the adapter. Resolution: legal/procurement review in Phase 3 planning.
- **USPS v3 OAuth2 endpoint details:** The 2023-2024 migration introduced a new auth flow. Exact token endpoint, scopes, and rate limits are unknown from training data alone. Resolution: read https://www.usps.com/business/web-tools-apis/ at the start of Phase 4.
- **usaddress Python 3.12 compatibility:** Package has low release activity. Verify installability on Python 3.12 before committing to it in pyproject.toml. Resolution: `uv add usaddress` smoke test in Phase 1.
- **usaddress-scourgify 0.4.1 Python 3.12 compatibility:** Same risk as usaddress. Verify in Phase 1.
- **Census Geocoder response schema:** Field names and endpoint versioning may have changed. Resolution: manual inspection of a live Census API response in Phase 2 before finalizing the adapter model.
- **Confidence normalization thresholds:** The internal 0.0–1.0 mapping (ROOFTOP=1.0, RANGE_INTERPOLATED=0.8, etc.) is a suggested starting point, not a validated standard. Resolution: compare against actual provider outputs during Phase 3 and adjust.

---

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — project requirements, constraints, and out-of-scope decisions; admin override and multi-provider result storage requirements derived directly from this file
- Training data: PostGIS documentation, GeoAlchemy2 documentation, SQLAlchemy 2 async documentation, FastAPI async patterns — well-established and stable patterns

### Secondary (MEDIUM confidence)
- Training data: Google Maps Python client (`googlemaps`), boto3 Amazon Location Service, usaddress library, usaddress-scourgify — versions and behavior as of knowledge cutoff August 2025
- Training data: Cache-aside pattern (Martin Fowler PEAA), provider fault isolation patterns, plugin registry patterns

### Tertiary (LOW confidence — verify before use)
- Google Maps Platform Terms of Service caching clause — verify at https://cloud.google.com/maps-platform/terms before building the Google adapter
- USPS v3 API OAuth2 endpoint and auth flow — verify at https://www.usps.com/business/web-tools-apis/ before Phase 4
- Version numbers for usaddress (0.5.10), usaddress-scourgify (0.4.1), censusgeocode (0.5+), pytest-postgresql (5.0+) — verify on PyPI before pinning

---
*Research completed: 2026-03-19*
*Ready for roadmap: yes*
