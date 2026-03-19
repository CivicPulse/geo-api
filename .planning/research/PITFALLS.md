# Domain Pitfalls

**Domain:** Geocoding / Address Validation Caching API
**Project:** CivPulse Geo API
**Researched:** 2026-03-19
**Confidence note:** Web search and WebFetch were unavailable during research. All findings are from training data. Confidence levels reflect that limitation.

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or systemic reliability failures.

---

### Pitfall 1: Cache Key Does Not Survive Input Normalization

**What goes wrong:** The cache lookup uses the raw input string as the key. "123 Main St" and "123 main st" and "123 Main Street" all miss the cache and trigger fresh API calls, even though they refer to the same address. In production, callers rarely send consistent casing or abbreviation style.

**Why it happens:** It feels natural to hash or key on the input directly. The normalization step gets deferred ("we'll add it later"), and by then the cache has thousands of inconsistently keyed records.

**Consequences:** Cache hit rate collapses. Third-party API costs spike. Services like Google or USPS rate-limit the application. The cache table grows without bound.

**Prevention:**
- Normalize the input address to a canonical form *before* the cache lookup, not after.
- Canonical form: uppercase, USPS abbreviations (ST/RD/AVE/BLVD), strip punctuation, collapse whitespace, expand unit designators (APT/STE/UNIT).
- Use `usaddress` (Python library) or a similar parser to decompose and re-serialize to a consistent form before hashing.
- Store both the raw input and the canonical form. Key on canonical form only.

**Warning signs:**
- Cache hit rate below 80% on repeated identical lookups.
- Duplicate rows in the cache table for visually identical addresses.

**Phase:** Address normalization must be implemented in Phase 1 / data model design, before any caching logic is built.

---

### Pitfall 2: Storing Coordinates as `FLOAT` or `NUMERIC` Instead of PostGIS `geometry`

**What goes wrong:** Lat/lon are stored as two separate `FLOAT` or `NUMERIC` columns. All spatial queries (distance, containment, nearest-neighbor) require manual Haversine math in SQL or application code. Spatial indexes cannot be used. Future spatial feature requests require a schema migration.

**Why it happens:** It seems simpler initially, especially if the first use case is just "give me the coordinates." PostGIS feels like overhead when the schema is being drafted.

**Consequences:** Every future spatial query is a rewrite. No GiST index on coordinates. No ability to do ST_DWithin, ST_Contains, or any PostGIS function without a migration. This is the single most common PostGIS regret.

**Prevention:**
- Use `geometry(Point, 4326)` from day one. SRID 4326 is WGS84 — what every geocoding API returns.
- Store with `ST_SetSRID(ST_MakePoint(lon, lat), 4326)`.
- Add a GiST index: `CREATE INDEX ON geocode_results USING GIST (location)`.
- Note: `ST_MakePoint(lon, lat)` — longitude first, latitude second. This ordering trips up nearly everyone.

**Warning signs:**
- Schema has `latitude FLOAT, longitude FLOAT` columns but no `geometry` column.
- Any query that calculates distance without using ST_Distance or ST_DWithin.

**Phase:** Data model design (Phase 1). This cannot be retrofit cheaply.

---

### Pitfall 3: No Canonical Address Key Across Services

**What goes wrong:** Each geocoding service returns the address in its own format. Google returns "123 Main St, Springfield, IL 62701, USA". USPS returns "123 MAIN ST, SPRINGFIELD IL 62701-1234". Census returns something else. These are stored under different keys, so a cache lookup for one service never benefits from a prior lookup via another.

**Why it happens:** Service results are stored verbatim. The design stores per-service results (correct) but doesn't establish a shared canonical address key that links them (wrong omission).

**Consequences:** Admins cannot see all service results for an address in one view. The "pick the official result" workflow breaks because results appear to be for different addresses. Deduplication is impossible.

**Prevention:**
- Separate the *canonical address identity* (parsed, normalized, USPS-standard) from the *service result*. The data model needs: `addresses` table (canonical form, cache key) and `geocode_results` table (foreign key to address, service name, raw result, coordinates, confidence).
- Every lookup normalizes the input to the canonical form, looks up the address record, then checks for existing service results.
- Admin override attaches to the `addresses` record, not to a service result.

**Warning signs:**
- The cache table has a `service_name` column but no shared address identity column.
- "Show all results for this address" requires multiple queries with fuzzy string matching.

**Phase:** Data model design (Phase 1). The two-table design must be established before building any service adapters.

---

### Pitfall 4: Google Geocoding API Terms of Service Violation — Caching

**What goes wrong:** Google's Geocoding API Terms of Service (as of knowledge cutoff) prohibit caching geocoding results for use outside of displaying them on a Google Map. Storing Google geocoding results in a database and serving them to downstream clients that do not render a Google Map may violate ToS.

**Why it happens:** Developers assume caching is always acceptable if it reduces cost. Google's ToS is not read carefully until a billing dispute or legal review.

**Consequences:** Contract violation. Potential API key termination. Legal exposure if used commercially.

**Prevention:**
- Read Google Maps Platform Terms of Service before storing results: https://cloud.google.com/maps-platform/terms
- Consider whether Google is needed at all. For US addresses: Census Geocoder (free, no caching restrictions), Geoapify (permissive ToS), Amazon Location Service (verify terms), USPS (validation, not geocoding).
- If Google is included, flag this in the service adapter with a comment and verify ToS compliance. Consider making Google the fallback-only service, not the primary cached one.

**Warning signs:**
- Google is listed as the primary geocoding service with no ToS review documented.

**Phase:** Architecture / service selection (Phase 1). Must be resolved before building the Google adapter.

---

### Pitfall 5: Address Parser Failure on Freeform Input Causes Silent Cache Miss

**What goes wrong:** The normalization/parsing step fails on unusual but valid input (apartment numbers, rural routes, PO Boxes, hyphenated house numbers, multi-word city names). The failure is silently swallowed, the input is passed through un-normalized, and a cache lookup is done on the raw string — missing any existing cached entry.

**Why it happens:** Parsers like `usaddress` return a best-effort parse that can fail or misclassify components. Error handling defaults to "continue with raw input" to avoid returning errors to the caller.

**Consequences:** Cache thrashing on legitimate addresses. Inconsistent behavior. Hard to debug because results look correct when they do work.

**Prevention:**
- Treat parser failures as a known, logged event — not an error to silently swallow and not a hard failure to return to the caller.
- Log parse failures with the raw input at WARN level (Loguru).
- On parse failure, fall through to the external service but do NOT cache the result under a raw key. Return the service result but flag it as un-normalized in the response.
- Maintain a `parse_failures` log table or counter metric to surface systemic parser problems.

**Warning signs:**
- No logging around the normalization step.
- Cache hit rate varies wildly by caller (one caller formats addresses, another sends freeform).

**Phase:** Address normalization implementation (Phase 1/2). Build the failure path explicitly, not as an afterthought.

---

## Moderate Pitfalls

---

### Pitfall 6: No Idempotency in Batch Endpoints

**What goes wrong:** A batch of 500 addresses is submitted. After 300 are processed, the external service rate-limits or returns an error. The batch is retried from the beginning. Services that charge per-lookup are called again for the 300 already completed.

**Why it happens:** Batch endpoints are built as a simple loop. No intermediate state is persisted.

**Prevention:**
- Treat batch jobs as a collection of independent lookups, not a monolithic transaction.
- For each address in a batch: check cache first, skip the external call if cached. This makes retries nearly free for already-cached items.
- Use a per-item status in the batch response: `{"address": "...", "status": "cached" | "fetched" | "error", ...}`.
- Never retry the entire batch — retry only the failed items.

**Phase:** Batch endpoint design (Phase 2).

---

### Pitfall 7: Admin Override Model Conflated With Service Results

**What goes wrong:** The admin override is stored as just another geocoding result, distinguished only by a `source = "admin"` flag. When the "official" result is determined at query time by priority ranking, the logic to promote the admin override must be replicated everywhere — in the API response, in batch jobs, in any future export.

**Why it happens:** It's the path of least resistance in a single-table design.

**Consequences:** Admin overrides get silently ignored when priority logic has a bug. Adding a new service requires updating the priority ranking in multiple places. Data integrity depends on application-layer logic that's easy to bypass.

**Prevention:**
- Give the admin override a dedicated column or row status on the `addresses` (canonical) table: `official_result_id FK → geocode_results`, or `official_coordinates geometry, official_source TEXT`.
- The "official" result is an explicit pointer, not an implicit ranking. Any query for the official geocode does a single lookup: `WHERE address.official_result_id IS NOT NULL`.
- Admin overrides with custom coordinates (not from any service) are valid and should be supported without shoehorning them into a service result row.

**Phase:** Data model design (Phase 1).

---

### Pitfall 8: PostGIS SRID Mismatch Between Storage and Queries

**What goes wrong:** Coordinates are stored as SRID 4326 (WGS84), but a spatial query uses ST_DWithin with a distance in meters. ST_DWithin on a 4326 geometry interprets the distance in degrees, not meters. Results are silently wrong (or the query returns no results for reasonable distances).

**Why it happens:** The PostGIS function signatures accept both geography and geometry types, and the distinction is easy to miss. Geometry with SRID 4326 does not automatically become a geography type.

**Prevention:**
- Use `geography(Point, 4326)` instead of `geometry(Point, 4326)` if distance-in-meters queries are needed now or likely in the future. Geography columns automatically interpret ST_DWithin distances as meters.
- If using geometry, always cast explicitly: `ST_DWithin(location::geography, ST_MakePoint(lon,lat)::geography, 1000)`.
- Document the SRID and type choice in schema comments.

**Warning signs:**
- ST_DWithin queries with numeric distance values and no explicit geography cast.
- Tests that assert "find addresses within 1 mile" passing trivially or returning empty results unexpectedly.

**Phase:** Data model design (Phase 1).

---

### Pitfall 9: USPS API Dependency Without a Fallback

**What goes wrong:** USPS address validation is the sole normalization source. USPS's free Addresses API has been periodically sunset, migrated, and rate-limited (the OAuth-based API replacing the older web tools API introduced breaking changes in 2024). When USPS is unavailable, address validation fails entirely.

**Why it happens:** USPS is the authoritative source for USPS-standard addresses, so it's treated as the only option.

**Consequences:** Outages in USPS validation block all address ingestion. The API becomes a single point of failure.

**Prevention:**
- USPS should be the preferred validation source, but the plugin architecture should allow fallback to a USPS-formatted normalization library (e.g., `scourgify`, `usaddress-scourgify`) that standardizes without hitting USPS.
- A library-only fallback will not validate deliverability, but it will standardize format — which is sufficient for cache key generation.
- Track the USPS API version. The 2024 USPS Web Tools → OAuth migration broke many integrations silently.

**Phase:** Service adapter design (Phase 1/2).

---

### Pitfall 10: No Confidence Score Normalization Across Services

**What goes wrong:** Each geocoding service returns confidence or accuracy in its own format. Google returns `geometry.location_type` (ROOFTOP, RANGE_INTERPOLATED, GEOMETRIC_CENTER, APPROXIMATE). Census returns match score 0-100. Geoapify returns `rank.confidence` 0-1. Amazon Location returns a numeric relevance score. Stored verbatim, these are incomparable.

**Why it happens:** Service adapters store raw API responses without normalizing confidence to a common scale.

**Consequences:** Admin override UI (or any future UI) cannot sort/compare service results meaningfully. Logic to "auto-select the highest confidence result" is impossible or brittle.

**Prevention:**
- Define an internal confidence enum or 0.0–1.0 float early: ROOFTOP=1.0, RANGE_INTERPOLATED=0.8, GEOMETRIC_CENTER=0.5, APPROXIMATE=0.2, etc.
- Each service adapter is responsible for mapping its native confidence to the internal scale.
- Store both the raw confidence value/type and the normalized internal score.

**Phase:** Service adapter interface design (Phase 1/2).

---

### Pitfall 11: Coordinate Precision Exceeding Source Data Accuracy

**What goes wrong:** Geocoded coordinates are stored and returned with 8+ decimal places of precision (e.g., `-87.62981234`). This implies sub-millimeter accuracy, which no geocoding service provides. Range-interpolated results (the majority for US addresses without dedicated rooftop geocoding) are accurate to maybe 10-50 meters.

**Why it happens:** Database stores full float precision. Nobody truncates.

**Consequences:** Callers make decisions based on false precision. Deduplication logic that compares coordinates fails because two lookups for the same address return slightly different float representations.

**Prevention:**
- Store coordinates at 6 decimal places (approximately 11 cm precision — well within geocoding accuracy).
- Document in the schema what precision is meaningful given source data.
- Do not use coordinate equality (`lat = X AND lon = Y`) for deduplication — always compare via ST_DWithin with a small tolerance (e.g., 10 meters).

**Phase:** Data model design (Phase 1).

---

## Minor Pitfalls

---

### Pitfall 12: Batch Endpoint Returns All-or-Nothing HTTP Status

**What goes wrong:** A batch of 50 addresses is submitted. 48 succeed, 2 fail (one invalid, one service timeout). The endpoint returns HTTP 500 because not all succeeded. The caller retries all 50.

**Prevention:**
- Batch endpoints always return HTTP 200 with per-item status in the response body.
- HTTP 4xx/5xx are reserved for request-level failures (malformed JSON, database unreachable), not item-level failures.

**Phase:** Batch endpoint design (Phase 2).

---

### Pitfall 13: Treating PO Boxes, Rural Routes, and Military Addresses as Edge Cases

**What goes wrong:** The normalization and validation logic is built and tested against standard street addresses. PO Box, RR (Rural Route), HC (Highway Contract), APO/FPO/DPO (military) addresses are structurally different. The parser misclassifies components, normalization produces garbage, and USPS rejects the validation request.

**Prevention:**
- Add explicit test cases for: `PO BOX 123`, `RR 2 BOX 45`, `HC 1 BOX 12`, `PSC 3 BOX 1234 APO AE 09021`.
- `usaddress` handles some of these but not reliably. Document known gaps.
- For cache key generation, these address types need a separate normalization path.

**Phase:** Address normalization (Phase 1/2). Add test cases at the time of implementation.

---

### Pitfall 14: Plugin Architecture That Requires Restart to Add a New Service

**What goes wrong:** The "plugin-style architecture" is implemented by having each service hardcoded in a factory function or config file. Adding a new service requires a code change and redeploy.

**Prevention:**
- Use a registration pattern: each service adapter registers itself. New adapters can be added by dropping in a new file and updating config — not by touching the orchestration layer.
- Consider using Python entry points or a simple class registry pattern.

**Phase:** Service adapter architecture (Phase 1).

---

### Pitfall 15: No Distinction Between "Not Found" and "Error" in Cache

**What goes wrong:** An address is geocoded once. The service returns no results (the address doesn't exist or is too rural). This "not found" response is treated as a transient failure — not cached. Future lookups for the same invalid address hit the external service every time.

**Prevention:**
- Cache negative results explicitly. Store a row with `status = "not_found"` and the service that returned it.
- Distinguish: `not_found` (address doesn't exist per this service — cache it), vs. `error` (service was unavailable — do not cache, retry later).
- Return a clear `"not_found"` status in the API response rather than an empty result or error.

**Phase:** Service adapter and caching logic (Phase 1/2).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Data model design | Lat/lon as FLOAT columns instead of PostGIS geometry | Use `geometry(Point, 4326)` + GiST index from day one |
| Data model design | Single-table design conflating address identity with service results | Two-table: `addresses` (canonical) + `geocode_results` (per-service) |
| Data model design | Admin override as just another service result | Explicit `official_result_id` pointer on `addresses` table |
| Data model design | geometry vs. geography SRID distance queries | Use `geography` type or always cast; document the choice |
| Address normalization | Raw input used as cache key | Normalize to canonical form before any cache lookup |
| Address normalization | Parser failures silently falling through | Log at WARN, do not cache un-normalized results |
| Address normalization | PO Box / RR / APO addresses breaking the parser | Explicit test cases at implementation time |
| Service adapter design | Google ToS violation for caching | Verify ToS before building the Google adapter |
| Service adapter design | USPS API as single point of failure | Library-based normalization fallback for format standardization |
| Service adapter design | Confidence scores incomparable across services | Normalize to internal 0.0–1.0 scale in each adapter |
| Service adapter design | "Not found" treated as transient error | Cache negative results explicitly with status field |
| Batch endpoints | All-or-nothing HTTP status | HTTP 200 always, per-item status in body |
| Batch endpoints | Retry re-calls external services for already-cached items | Cache-first per item makes retry nearly free |

---

## Sources

**Confidence note:** WebSearch, WebFetch, and Context7 were all unavailable during this research session. All findings are drawn from training data (knowledge cutoff August 2025). The pitfalls documented here represent well-established failure patterns in geocoding systems, PostGIS usage, and USPS integration. Confidence is MEDIUM across the board — not LOW, because these are patterns with broad consensus in the domain, but not HIGH, because they were not verified against current official documentation during this session.

- PostGIS geometry vs. geography: well-documented in PostGIS official docs; the SRID/distance confusion is a top FAQ item
- Google Maps Platform ToS caching restriction: documented at https://cloud.google.com/maps-platform/terms (verify current state before building the adapter)
- USPS API migration (OAuth): USPS Web Tools sunset/migration announced 2023-2024; verify current API endpoint and auth model at https://www.usps.com/business/web-tools-apis/
- `usaddress` Python library: https://github.com/datamade/usaddress — US address parsing; known limitations with non-standard address types
- `scourgify` / `usaddress-scourgify`: USPS-format normalization without API calls — useful as fallback
