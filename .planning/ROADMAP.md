# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- ✅ **v1.1 Local Data Sources** — Phases 7-11 (shipped 2026-03-29)

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

<details>
<summary>✅ v1.1 Local Data Sources (Phases 7-11) — SHIPPED 2026-03-29</summary>

- [x] **Phase 7: Pipeline Infrastructure** — Direct-return pipeline bypass, provider ABC extension, and staging table migrations (2/2 plans) — completed 2026-03-22
- [x] **Phase 8: OpenAddresses Provider** — OA geocoding and validation from .geojson.gz files via PostGIS staging table (2/2 plans) — completed 2026-03-22
- [x] **Phase 9: Tiger Provider** — Tiger geocoding and validation via PostGIS geocode() and normalize_address() SQL functions (2/2 plans) — completed 2026-03-24
- [x] **Phase 10: NAD Provider** — NAD geocoding and validation from 80M-row staging table with bulk COPY import (2/2 plans) — completed 2026-03-24
- [x] **Phase 11: Fix Batch Endpoint Local Provider Serialization** — Batch endpoints include local provider results in every response item (1/1 plan) — completed 2026-03-24

Full details archived in `milestones/v1.1-ROADMAP.md`.

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-03-19 |
| 2. Geocoding | v1.0 | 2/2 | Complete | 2026-03-19 |
| 3. Validation and Data Import | v1.0 | 3/3 | Complete | 2026-03-19 |
| 4. Batch and Hardening | v1.0 | 2/2 | Complete | 2026-03-19 |
| 5. Fix Admin Override & Import Order | v1.0 | 1/1 | Complete | 2026-03-19 |
| 6. Documentation & Traceability Cleanup | v1.0 | 1/1 | Complete | 2026-03-19 |
| 7. Pipeline Infrastructure | v1.1 | 2/2 | Complete | 2026-03-22 |
| 8. OpenAddresses Provider | v1.1 | 2/2 | Complete | 2026-03-22 |
| 9. Tiger Provider | v1.1 | 2/2 | Complete | 2026-03-24 |
| 10. NAD Provider | v1.1 | 2/2 | Complete | 2026-03-24 |
| 11. Fix Batch Local Serialization | v1.1 | 1/1 | Complete | 2026-03-24 |
