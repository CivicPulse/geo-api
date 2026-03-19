# Feature Landscape

**Domain:** Internal geocoding and address validation caching API
**Researched:** 2026-03-19
**Confidence note:** External research tools were unavailable during this session. All findings are based on training-data knowledge of geocoding/address validation APIs (Google Maps Geocoding, USPS APIs, Census Geocoder, SmartyStreets, Geoapify). Confidence is MEDIUM overall — well-established domain with stable patterns, but not verified against current API documentation.

---

## Table Stakes

Features consumers expect from any geocoding/address validation API. Missing these makes the API feel incomplete or unreliable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single-address geocoding (address → lat/lng) | Core purpose of the API | Low | Returns coordinates + location type (rooftop, centroid, etc.) |
| Single-address reverse geocoding (lat/lng → address) | Standard complement to forward geocoding | Low | Useful for confirming or labeling coordinates |
| Address validation with USPS standardization | CivPulse explicitly requires this; USPS is the authoritative US source | Medium | Normalizes abbreviations, fixes capitalization, expands postal codes to ZIP+4 |
| Freeform string input for both geocoding and validation | Users/services have addresses as strings | Low | Parse "123 Main St Anytown GA 30001" as a single field |
| Structured field input for both operations | Some callers have pre-parsed address fields | Low | street, city, state, zip as separate fields — both forms must work |
| Confidence/accuracy score on geocode results | Callers need to know how trustworthy a result is | Low | Maps to provider accuracy types: rooftop, range-interpolated, geometric-center |
| Location type classification | Distinguishes precise from approximate results | Low | e.g., rooftop vs road centerline vs ZIP centroid |
| Batch geocoding (multiple addresses in one request) | Required per PROJECT.md; reduces HTTP overhead for bulk imports | Medium | Return results in same order as input; include per-item error handling |
| Batch address validation | Required per PROJECT.md; same rationale | Medium | Same ordering and per-item error semantics as batch geocoding |
| Cache hit/miss indication in response | Callers benefit from knowing if result came from cache or live service | Low | Simple boolean or enum field on response |
| Error details per address | Partial batch failures must not silently drop results | Low | Per-item status code and message in batch responses |
| Health/readiness endpoint | Required for any internal service in a microservice ecosystem | Low | /health or /readiness; checks DB connectivity at minimum |

---

## Differentiators

Features that go beyond table stakes and reflect the specific design goals of this API.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Multi-service result storage | Store all provider results separately rather than picking one; enables admin comparison and override | Medium | Core architectural decision from PROJECT.md — each provider result is a distinct record |
| Admin-overridable "official" geocode record | When providers disagree, a human can mark one result (or a custom coordinate) as canonical | Medium | Official record is the one downstream services use; must be queryable by address |
| Custom admin coordinate (not from any provider) | Admin can pin a lat/lng that no provider returned — corrects provider errors for known landmarks | Medium | Needs a clear "source: admin_override" signal in the response |
| Plugin-style geocoding provider architecture | New providers can be added without touching core logic | High | Defined interface per provider; swapping or adding services is configuration, not code surgery |
| USPS ZIP+4 delivery point validation | Validates that a specific address actually receives mail, not just that the street exists | Medium | USPS API returns DPV confirmation codes; highly valuable for voter/resident data |
| Ranked suggestions with confidence on validation | When input is ambiguous/partial, return ordered list of candidates | Low | Required per PROJECT.md ("return all suggestions ranked with confidence scores") |
| Manual cache refresh endpoint | Force re-query of a cached address from live providers | Medium | Needed because cache is permanent otherwise; admin or service-triggered |
| Per-provider result retrieval | Allow callers to request results from a specific provider, not just the "official" answer | Low | Enables provider comparison in admin workflows |
| Consistent address normalization on input | Normalize input before cache lookup to maximize hit rate (lowercase, expand abbreviations) | Medium | "123 Main Street" and "123 Main St" should hit the same cache entry |

---

## Anti-Features

Features to explicitly NOT build in v1. These are deliberate omissions, not oversights.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Authentication / API keys | Internal service behind network security; adding auth creates operational overhead with no security benefit given network isolation | Rely on network-level security per PROJECT.md decision |
| Cache expiration / TTL | Addresses and locations rarely change; automatic expiration would trigger unnecessary re-queries and potentially flip admin-set official records | Use manual cache refresh endpoint when a record is known stale |
| International addresses | Significant scope expansion (different address formats, different providers, different validation standards) | Constrain to US for v1; provider interface supports future extension |
| Admin UI | Out of scope per PROJECT.md; this API is a data service | Build admin interface as a separate system that consumes this API |
| Audit trail for admin overrides | Deferred per PROJECT.md | Can add a simple event log table in a future milestone if compliance needs arise |
| Routing / directions / distance matrix | Different problem domain; adds provider dependencies with no current use case | Use dedicated routing service if CivPulse needs it |
| Autocomplete / typeahead | Interactive UX feature; this is an internal batch/point-lookup API, not a search box backend | If needed, consumer services can build autocomplete using their own lookup patterns |
| Rate limiting | Internal service with known callers; rate limiting adds latency and operational complexity without benefit | Address this if abuse patterns emerge on internal network |
| Webhooks / async callbacks | Adds message broker dependency for a use case that synchronous requests handle adequately | Batch endpoint with synchronous response covers the async-like use case |
| Geographic area queries (bounding box, radius search) | PostGIS supports this, but no stated use case yet | Enable if a consuming service identifies the need |

---

## Feature Dependencies

```
Freeform string input → Input normalization → Cache lookup
Structured field input → Input normalization → Cache lookup

Cache lookup (MISS) → Multi-provider geocoding → Store all provider results → Return official result
Cache lookup (HIT)  → Return cached official result

Multi-provider geocoding → Admin-overridable official record
  (must store all results before admin can pick one)

Admin override → Manual cache refresh
  (refresh replaces provider results but admin override should survive or be re-applied)

USPS validation → Ranked suggestions with confidence
  (USPS returns multiple candidates; ranking requires confidence scoring)

Batch geocoding → Single-address geocoding
  (batch is a loop with unified error handling over the single-address path)

Batch validation → Single-address validation
  (same relationship)

Plugin provider architecture → Multi-provider geocoding
  (plugins are the mechanism by which multi-provider results are collected)

Health endpoint → DB connectivity check
  (meaningful health check requires testing the PostGIS connection)
```

---

## MVP Recommendation

For an internal v1 that serves CivPulse immediately and validates core assumptions:

**Prioritize (must be in v1):**
1. Single-address geocoding with cache (forward only; reverse can follow)
2. Single-address USPS validation with standardization and ranked suggestions
3. Multi-provider result storage (even if only one or two providers are wired initially)
4. Admin official record override (the core differentiator of this service)
5. Batch endpoints for both operations (stated requirement)
6. Plugin provider interface (gates all future provider additions)
7. Manual cache refresh endpoint (required because cache never expires)
8. Input normalization before cache lookup (correctness multiplier)
9. Health endpoint (operational necessity)

**Defer (not needed for v1 validation):**
- Reverse geocoding: No stated use case yet; add when a consumer requests it
- Per-provider result retrieval endpoint: Admin UI (separate system) can be built with official record + override workflow first
- ZIP+4 delivery point validation: Valuable but adds USPS API integration complexity; validate basic USPS normalization first
- Geographic area queries: No current use case

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Table stakes features | MEDIUM | Standard geocoding API patterns are stable and well-known; not verified against current Google/USPS/Census docs due to tool restrictions |
| USPS standardization specifics | MEDIUM | ZIP+4, DPV codes, USPS abbreviation tables are well-documented in training data but not verified against current USPS API docs |
| Admin override workflow | HIGH | Derived directly from PROJECT.md requirements — this is the system's design intent, not inferred from external research |
| Differentiator features | HIGH | Derived from PROJECT.md requirements and architectural decisions |
| Anti-features | HIGH | Directly mapped from PROJECT.md out-of-scope decisions plus standard internal-API reasoning |
| Feature dependencies | MEDIUM | Logical dependencies; not verified against any reference implementation |

---

## Sources

- PROJECT.md (primary): /home/kwhatcher/projects/civpulse/geo-api/.planning/PROJECT.md
- Training data: Google Maps Geocoding API, USPS Address Information API, US Census Geocoder, SmartyStreets/Smarty, Geoapify — patterns as of knowledge cutoff August 2025
- Note: WebSearch, WebFetch, and Brave Search were unavailable during this research session. Verification against current API documentation is recommended before finalizing provider-specific claims (e.g., USPS DPV codes, Census Geocoder response schema).
