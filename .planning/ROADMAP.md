# Roadmap: CivPulse Geo API

## Overview

Build an internal geocoding and address validation caching API in four phases. The foundation establishes the data model and plugin contract — both are load-bearing and wrong choices are irreversible. Geocoding providers and the admin override workflow ship next, delivering the core differentiator. Address validation and county GIS data import follow, completing the canonical address registry. Batch endpoints and HTTP hardening close out v1, layering fan-out complexity on top of proven single-address paths.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Foundation** - PostGIS schema, canonical key strategy, plugin contract, and project scaffolding
- [ ] **Phase 2: Geocoding** - Multi-provider geocoding with cache, official record, and admin override
- [ ] **Phase 3: Validation and Data Import** - USPS address validation and Bibb County GIS CLI import
- [ ] **Phase 4: Batch and Hardening** - Batch endpoints, per-item error handling, and HTTP layer completion

## Phase Details

### Phase 1: Foundation
**Goal**: The data model, canonical address normalization, provider plugin contract, and project scaffolding are in place so that no subsequent phase needs to revisit foundational decisions
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-05, INFRA-07
**Success Criteria** (what must be TRUE):
  1. The database schema exists with PostGIS geography columns, separate addresses / geocoding_results / validation_results / official_geocoding tables, and Alembic migrations that apply cleanly from scratch
  2. A canonical address normalization function exists and is tested: "123 Main Street" and "123 Main St" produce the same cache key
  3. The GeocodingProvider and ValidationProvider abstract base classes exist and are enforced — a concrete class that omits a required method raises an error at load time
  4. The FastAPI application starts, connects to PostgreSQL, and the health endpoint returns a passing response that confirms database connectivity
  5. Running `docker compose up` starts the API and PostgreSQL/PostGIS database with seed data pre-loaded, ready for development
**Plans:** 3/3 plans executed

Plans:
- [x] 01-01-PLAN.md — Project scaffolding, dependencies, ORM models, and Alembic migration infrastructure
- [x] 01-02-PLAN.md — Canonical address normalization and provider plugin contract with tests
- [x] 01-03-PLAN.md — FastAPI app, health endpoint, Docker Compose, seed data, and integration wiring

### Phase 2: Geocoding
**Goal**: Callers can forward geocode any US address through the API, receive results from multiple providers, see which result is the official record, and admins can override or set a custom coordinate
**Depends on**: Phase 1
**Requirements**: GEO-01, GEO-02, GEO-03, GEO-04, GEO-05, GEO-06, GEO-07, GEO-08, GEO-09
**Success Criteria** (what must be TRUE):
  1. A POST to the geocode endpoint returns lat/lng coordinates, location type classification, confidence score, and a cache_hit flag indicating whether the result came from the database or a live provider call
  2. The same address geocoded twice only calls external providers once — the second request returns from cache with cache_hit=true
  3. Each provider's result is stored as a separate record; a caller can request results from a specific provider for comparison
  4. An admin can set the official geocode record for an address to any provider's result or to a custom lat/lng coordinate not from any provider
  5. An admin can force a cache refresh for a specific address, triggering a live re-query from all providers and updating stored results
**Plans**: TBD

### Phase 3: Validation and Data Import
**Goal**: Callers can validate and USPS-standardize US addresses through the API, and the Bibb County GIS dataset is importable as a first-class provider whose results serve as the default official record when no admin override exists
**Depends on**: Phase 1
**Requirements**: VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, DATA-01, DATA-02, DATA-03, DATA-04
**Success Criteria** (what must be TRUE):
  1. A POST to the validation endpoint accepts either a freeform address string or structured fields and returns one or more USPS-standardized address candidates ranked by confidence score
  2. Normalized output applies USPS abbreviation standards: "Road" becomes "RD", "Georgia" becomes "GA", casing is corrected
  3. ZIP+4 delivery point validation runs as part of the response, confirming whether an address actually receives mail
  4. Running the CLI import tool against a GeoJSON, KML, or SHP file loads the data as provider "bibb_county_gis" records using the same schema as online providers, and re-running on the same file performs an upsert without creating duplicate records
  5. For any address where bibb_county_gis data exists and no admin override is set, that county record is returned as the official geocode result
**Plans**: TBD

### Phase 4: Batch and Hardening
**Goal**: Callers can submit multiple addresses in a single geocoding or validation request and receive per-item results with individual status codes, completing the full v1 HTTP surface
**Depends on**: Phase 2, Phase 3
**Requirements**: INFRA-03, INFRA-04, INFRA-06
**Success Criteria** (what must be TRUE):
  1. A POST to the batch geocode endpoint with N addresses returns N result objects; one address failing does not prevent the remaining addresses from being processed and returned
  2. A POST to the batch validation endpoint with N addresses returns N result objects with the same partial-failure isolation
  3. Each item in a batch response includes its own status code and error message so the caller can identify exactly which inputs succeeded and which failed
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4
Note: Phase 3 depends only on Phase 1 (not Phase 2) and could run in parallel with Phase 2 if needed.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete | 2026-03-19 |
| 2. Geocoding | 0/TBD | Not started | - |
| 3. Validation and Data Import | 0/TBD | Not started | - |
| 4. Batch and Hardening | 0/TBD | Not started | - |
