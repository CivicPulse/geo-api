# Requirements: CivPulse Geo API

**Defined:** 2026-03-19
**Core Value:** Provide a single, reliable source of geocoded and validated address data across all CivPulse systems, minimizing cost by caching external service results and giving admins authority over the "official" answer.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Geocoding

- [ ] **GEO-01**: API can forward geocode a single address to lat/lng coordinates with location type classification (rooftop, centroid, etc.)
- [ ] **GEO-02**: API stores geocode results from each external provider as separate records linked to the address
- [ ] **GEO-03**: API checks local cache before calling external providers; returns cached result on hit
- [ ] **GEO-04**: API returns confidence/accuracy score on each geocode result
- [ ] **GEO-05**: API response indicates whether result came from cache or live service call
- [ ] **GEO-06**: Admin can set the "official" geocode record for an address to match any provider's result or a custom coordinate
- [ ] **GEO-07**: Admin can set a custom lat/lng coordinate as the official location (not from any provider)
- [ ] **GEO-08**: API provides a manual cache refresh endpoint to re-query all providers for a given address
- [ ] **GEO-09**: API can return geocode results from a specific provider for admin comparison workflows

### Address Validation

- [ ] **VAL-01**: API can validate a single US address and return USPS-standardized corrected address(es)
- [ ] **VAL-02**: API accepts freeform string input for validation (e.g., "123 Main Street Anytown GA 30001")
- [ ] **VAL-03**: API accepts structured field input for validation (street, city, state, zip as separate fields)
- [ ] **VAL-04**: API returns all possible corrected addresses ranked with confidence scores when input is ambiguous
- [ ] **VAL-05**: API normalizes address components to USPS standards (abbreviations, casing, formatting)
- [ ] **VAL-06**: API performs ZIP+4 delivery point validation to verify an address actually receives mail

### Data Import

- [ ] **DATA-01**: CLI tool (Typer) can bulk import local GIS data files (GeoJSON, KML, SHP) as a provider's geocode results
- [ ] **DATA-02**: Imported county GIS data is stored as a provider ("bibb_county_gis") using the same schema as online service results
- [ ] **DATA-03**: When county GIS data exists for an address and no admin override is set, the county data is used as the default official record
- [ ] **DATA-04**: CLI import tool supports re-importing updated data exports without creating duplicate records (upsert behavior)

### Infrastructure

- [x] **INFRA-01**: Input addresses are normalized to a canonical form before cache lookup to maximize hit rate
- [x] **INFRA-02**: External geocoding/validation providers are implemented as plugins with a common interface
- [ ] **INFRA-03**: API supports batch geocoding (multiple addresses in one request) with per-item results and error handling
- [ ] **INFRA-04**: API supports batch address validation (multiple addresses in one request) with per-item results and error handling
- [x] **INFRA-05**: API exposes a health/readiness endpoint that verifies database connectivity
- [ ] **INFRA-06**: Batch responses include per-item status codes and error messages for partial failures
- [x] **INFRA-07**: `docker compose up` provides a fully running local development environment with PostgreSQL/PostGIS and seed data

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Geocoding

- **GEO-10**: API can reverse geocode coordinates (lat/lng → address)

### Validation

- **VAL-07**: API validates international addresses (non-US)

### Observability

- **OBS-01**: API tracks audit trail for admin geocode overrides (who, when, previous value, reason)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Authentication / API keys | Internal service; network-level security only |
| Cache expiration / TTL | Addresses rarely change; manual refresh available |
| International addresses | US only for v1; significant scope expansion |
| Admin UI | Separate system that consumes this API |
| Routing / directions / distance matrix | Different problem domain |
| Autocomplete / typeahead | Interactive UX feature; this is a batch/point-lookup API |
| Rate limiting | Internal service with known callers |
| Webhooks / async callbacks | Synchronous requests adequate |
| Geographic area queries | No current use case |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 — Foundation | Complete |
| INFRA-02 | Phase 1 — Foundation | Complete |
| INFRA-05 | Phase 1 — Foundation | Complete |
| INFRA-07 | Phase 1 — Foundation | Complete |
| GEO-01 | Phase 2 — Geocoding | Pending |
| GEO-02 | Phase 2 — Geocoding | Pending |
| GEO-03 | Phase 2 — Geocoding | Pending |
| GEO-04 | Phase 2 — Geocoding | Pending |
| GEO-05 | Phase 2 — Geocoding | Pending |
| GEO-06 | Phase 2 — Geocoding | Pending |
| GEO-07 | Phase 2 — Geocoding | Pending |
| GEO-08 | Phase 2 — Geocoding | Pending |
| GEO-09 | Phase 2 — Geocoding | Pending |
| VAL-01 | Phase 3 — Validation and Data Import | Pending |
| VAL-02 | Phase 3 — Validation and Data Import | Pending |
| VAL-03 | Phase 3 — Validation and Data Import | Pending |
| VAL-04 | Phase 3 — Validation and Data Import | Pending |
| VAL-05 | Phase 3 — Validation and Data Import | Pending |
| VAL-06 | Phase 3 — Validation and Data Import | Pending |
| DATA-01 | Phase 3 — Validation and Data Import | Pending |
| DATA-02 | Phase 3 — Validation and Data Import | Pending |
| DATA-03 | Phase 3 — Validation and Data Import | Pending |
| DATA-04 | Phase 3 — Validation and Data Import | Pending |
| INFRA-03 | Phase 4 — Batch and Hardening | Pending |
| INFRA-04 | Phase 4 — Batch and Hardening | Pending |
| INFRA-06 | Phase 4 — Batch and Hardening | Pending |

**Coverage:**
- v1 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0

---
*Requirements defined: 2026-03-19*
*Last updated: 2026-03-19 after roadmap creation*
