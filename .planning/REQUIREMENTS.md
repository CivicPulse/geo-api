# Requirements: CivPulse Geo API

**Defined:** 2026-03-22
**Core Value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching and giving admins authority over the official answer

## v1.1 Requirements

Requirements for local data source providers. Each maps to roadmap phases.

### Pipeline Infrastructure

- [ ] **PIPE-01**: Service layer bypasses DB caching for providers with is_local=True
- [ ] **PIPE-02**: Provider ABCs expose is_local property (default False)
- [ ] **PIPE-03**: Alembic migration creates openaddresses_points staging table with GiST spatial index
- [ ] **PIPE-04**: Alembic migration creates nad_points staging table with GiST spatial index
- [ ] **PIPE-05**: CLI command imports OpenAddresses .geojson.gz files into staging table
- [ ] **PIPE-06**: CLI command imports NAD r21 TXT CSV into staging table via COPY

### OpenAddresses

- [ ] **OA-01**: User can geocode an address against loaded OpenAddresses data
- [ ] **OA-02**: User can validate an address against OpenAddresses records
- [ ] **OA-03**: OA geocoding returns location_type based on accuracy field (rooftop/parcel/interpolated/centroid)
- [ ] **OA-04**: OA provider registered automatically when staging table has data

### NAD

- [ ] **NAD-01**: User can geocode an address against loaded NAD data
- [ ] **NAD-02**: User can validate an address against NAD records
- [ ] **NAD-03**: NAD import handles 80M+ rows via PostgreSQL COPY (not row-by-row INSERT)
- [ ] **NAD-04**: NAD provider registered automatically when staging table has data

### Tiger

- [ ] **TIGR-01**: User can geocode an address via PostGIS Tiger geocode() function
- [ ] **TIGR-02**: User can validate/normalize an address via PostGIS normalize_address()
- [ ] **TIGR-03**: Tiger geocoding maps rating score to confidence (0=best -> 1.0 confidence)
- [ ] **TIGR-04**: Tiger provider degrades gracefully when extension/data not installed
- [ ] **TIGR-05**: Setup scripts install Tiger extensions and load data per state

## Future Requirements

### Additional Data Sources

- **COLL-01**: Import from OpenAddresses collection ZIP (multi-state, 3000+ files)
- **NAD-FGDB-01**: NAD FGDB format import as alternative to TXT
- **BATCH-LOCAL-01**: Batch geocoding/validation endpoints for local providers

### Enhanced Matching

- **MATCH-01**: Fuzzy address matching for local providers (Levenshtein/soundex)
- **MATCH-02**: Configurable match confidence thresholds per provider

## Out of Scope

| Feature | Reason |
|---------|--------|
| Local provider result caching | User decision — local data is already local, no need to cache |
| Collection ZIP multi-state import | Deferred — single county files sufficient for v1.1 |
| NAD FGDB import | TXT format preferred for bulk loading; FGDB is a future alternative |
| Real-time Tiger data updates | Tiger data is census-cycle; manual refresh sufficient |
| Reverse geocoding from local sources | v2 candidate — forward geocoding first |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 7 | Pending |
| PIPE-02 | Phase 7 | Pending |
| PIPE-03 | Phase 7 | Pending |
| PIPE-04 | Phase 7 | Pending |
| PIPE-05 | Phase 7 | Pending |
| PIPE-06 | Phase 7 | Pending |
| OA-01 | Phase 8 | Pending |
| OA-02 | Phase 8 | Pending |
| OA-03 | Phase 8 | Pending |
| OA-04 | Phase 8 | Pending |
| NAD-01 | Phase 10 | Pending |
| NAD-02 | Phase 10 | Pending |
| NAD-03 | Phase 10 | Pending |
| NAD-04 | Phase 10 | Pending |
| TIGR-01 | Phase 9 | Pending |
| TIGR-02 | Phase 9 | Pending |
| TIGR-03 | Phase 9 | Pending |
| TIGR-04 | Phase 9 | Pending |
| TIGR-05 | Phase 9 | Pending |

**Coverage:**
- v1.1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-03-22*
*Last updated: 2026-03-22 after roadmap creation*
