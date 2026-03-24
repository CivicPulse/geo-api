# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- 🚧 **v1.1 Local Data Sources** — Phases 7-10 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-6) — SHIPPED 2026-03-19</summary>

- [x] **Phase 1: Foundation** — PostGIS schema, canonical key strategy, plugin contract, and project scaffolding (3/3 plans)
- [x] **Phase 2: Geocoding** — Multi-provider geocoding with cache, official record, and admin override (2/2 plans)
- [x] **Phase 3: Validation and Data Import** — USPS address validation and Bibb County GIS CLI import (3/3 plans)
- [x] **Phase 4: Batch and Hardening** — Batch endpoints, per-item error handling, and HTTP layer completion (2/2 plans)
- [x] **Phase 5: Fix Admin Override & Import Order** — Admin override table write fix and import-order documentation (1/1 plan)
- [x] **Phase 6: Documentation & Traceability Cleanup** — SUMMARY frontmatter and ROADMAP checkbox fixes (1/1 plan)

Full details archived in `milestones/v1.0-ROADMAP.md`.

</details>

### 🚧 v1.1 Local Data Sources (In Progress)

**Milestone Goal:** Add OpenAddresses, NAD, and PostGIS Tiger local provider pairs that implement the existing GeocodingProvider/ValidationProvider ABCs, bypass DB caching, and are loaded via CLI commands.

- [x] **Phase 7: Pipeline Infrastructure** — Direct-return pipeline bypass, provider ABC extension, and staging table migrations (completed 2026-03-22)
- [x] **Phase 8: OpenAddresses Provider** — OA geocoding and validation from .geojson.gz files via PostGIS staging table (completed 2026-03-22)
- [x] **Phase 9: Tiger Provider** — Tiger geocoding and validation via PostGIS geocode() and normalize_address() SQL functions (completed 2026-03-24)
- [x] **Phase 10: NAD Provider** — NAD geocoding and validation from 80M-row staging table with bulk COPY import (completed 2026-03-24)

## Phase Details

### Phase 7: Pipeline Infrastructure
**Goal**: The service layer correctly routes local providers through a bypass path that never writes to the DB cache, and PostGIS staging tables exist for local provider data
**Depends on**: Phase 6 (v1.0 complete)
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06
**Success Criteria** (what must be TRUE):
  1. Calling geocode/validate with a local provider never writes to the geocoding_results or validation_results tables
  2. Provider ABCs expose an is_local property that defaults to False on all existing providers
  3. openaddresses_points table exists in the database with a GiST spatial index
  4. nad_points table exists in the database with a GiST spatial index
  5. CLI load-oa and load-nad commands are registered and display help text (data loading wired up in later phases)
**Plans**: 2 plans

Plans:
- [ ] 07-01-PLAN.md — Provider ABC is_local property and service layer bypass for local providers
- [ ] 07-02-PLAN.md — Staging table migrations, ORM models, and CLI command stubs

### Phase 8: OpenAddresses Provider
**Goal**: Users can geocode and validate addresses against loaded OpenAddresses data, with results returned directly without DB caching
**Depends on**: Phase 7
**Requirements**: OA-01, OA-02, OA-03, OA-04
**Success Criteria** (what must be TRUE):
  1. Running load-oa with a .geojson.gz county file populates openaddresses_points and subsequent geocode calls return results from that data
  2. Geocoding an address against OA data returns a location_type mapped from the OA accuracy field (rooftop/parcel/interpolated/centroid)
  3. Validating an address against OA data returns a normalized result with USPS-standard fields
  4. OA provider is automatically registered in the provider list when the openaddresses_points table contains at least one row, and absent otherwise
**Plans**: 2 plans

Plans:
- [ ] 08-01-PLAN.md — OA geocoding and validation providers with accuracy mapping and lifespan registration
- [ ] 08-02-PLAN.md — load-oa CLI NDJSON import with batch upsert and street suffix parsing

### Phase 9: Tiger Provider
**Goal**: Users can geocode and validate addresses via the PostGIS Tiger geocoder SQL functions, with the provider degrading gracefully when Tiger data is not installed
**Depends on**: Phase 7
**Requirements**: TIGR-01, TIGR-02, TIGR-03, TIGR-04, TIGR-05
**Success Criteria** (what must be TRUE):
  1. Geocoding an address via Tiger returns a confidence value between 0.0 and 1.0 correctly mapped from the Tiger rating (rating 0 = confidence 1.0, rating 100 = confidence 0.0)
  2. Validating an address via Tiger normalize_address() returns parsed USPS-standard components
  3. When Tiger extension is installed but data is not loaded, the provider returns a NO_MATCH result without raising an exception
  4. When Tiger extension is not installed, the Tiger provider is not registered at startup and a clear warning is logged
  5. Running setup-tiger installs the required PostGIS extensions and loads Tiger/LINE data for the specified state(s)
**Plans**: 2 plans

Plans:
- [ ] 09-01-PLAN.md — Tiger geocoding and validation providers with rating-to-confidence mapping and conditional lifespan registration
- [ ] 09-02-PLAN.md — setup-tiger CLI command with FIPS conversion and Docker init script for Tiger extensions

### Phase 10: NAD Provider
**Goal**: Users can geocode and validate addresses against the National Address Database, which is loaded via a bulk COPY import capable of handling the full 80M-row dataset
**Depends on**: Phase 7, Phase 8 (load pattern proven)
**Requirements**: NAD-01, NAD-02, NAD-03, NAD-04
**Success Criteria** (what must be TRUE):
  1. Running load-nad with the NAD_r21_TXT.zip file populates nad_points via PostgreSQL COPY (not row-by-row INSERT) and subsequent geocode calls return results from that data
  2. Geocoding an address against NAD returns location_type and confidence mapped from the NAD Placement field
  3. Validating an address against NAD returns a normalized result with USPS-standard fields
  4. NAD provider is automatically registered in the provider list when the nad_points table contains at least one row, and absent otherwise
**Plans**: 2 plans

Plans:
- [ ] 10-01-PLAN.md — NAD geocoding and validation providers with Placement mapping and conditional lifespan registration
- [ ] 10-02-PLAN.md — load-nad CLI COPY-based bulk import from ZIP with state filtering and city fallback

## Progress

**Execution Order:** Phases execute in numeric order: 7 → 8 → 9 → 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-03-19 |
| 2. Geocoding | v1.0 | 2/2 | Complete | 2026-03-19 |
| 3. Validation and Data Import | v1.0 | 3/3 | Complete | 2026-03-19 |
| 4. Batch and Hardening | v1.0 | 2/2 | Complete | 2026-03-19 |
| 5. Fix Admin Override & Import Order | v1.0 | 1/1 | Complete | 2026-03-19 |
| 6. Documentation & Traceability Cleanup | v1.0 | 1/1 | Complete | 2026-03-19 |
| 7. Pipeline Infrastructure | 2/2 | Complete   | 2026-03-22 | - |
| 8. OpenAddresses Provider | 2/2 | Complete   | 2026-03-22 | - |
| 9. Tiger Provider | 2/2 | Complete   | 2026-03-24 | - |
| 10. NAD Provider | 2/2 | Complete    | 2026-03-24 | - |
