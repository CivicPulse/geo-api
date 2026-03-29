# Milestones

## v1.1 Local Data Sources (Shipped: 2026-03-29)

**Phases completed:** 5 phases, 9 plans, 16 tasks

**Key accomplishments:**

- is_local property on provider ABCs with geocoding/validation service bypass path — local providers skip geocoding_results/validation_results DB writes while still upserting Address records
- openaddresses_points and nad_points staging tables with GiST spatial indexes, ORM models, and load-oa/load-nad Typer command stubs with rich installed
- OAGeocodingProvider and OAValidationProvider querying openaddresses_points via ST_Y/ST_X, registered in FastAPI lifespan, with accuracy-mapped confidence scores and scourgify USPS re-normalization
- Functional load-oa CLI command with gzip NDJSON streaming, usaddress suffix parsing, empty-to-NULL normalization, and ON CONFLICT upsert into openaddresses_points
- TigerGeocodingProvider and TigerValidationProvider using PostGIS geocode()/normalize_address() SQL functions, with rating-to-confidence mapping and conditional startup registration
- NAD geocoding and validation providers with 7-value PLACEMENT_MAP, conditional startup registration via _nad_data_available, and 34-test TDD suite
- Full COPY-based load-nad CLI replacing stub — streams CSV from ZIP, filters by state, upserts into nad_points via psycopg2 copy_expert through a temp table
- Verified GAP-INT-01 closure: batch endpoints now include local_results/local_candidates via fix applied in commit f6f904d before planning began — 16/16 batch tests pass including 2 regression tests

---

## v1.0 MVP (Shipped: 2026-03-19)

**Phases:** 6 | **Plans:** 12 | **Commits:** 82 | **Files:** 116 | **LOC:** 7,488 Python
**Timeline:** 2026-03-18 → 2026-03-19 (2 days)
**Git range:** acd51a9..866d7c7
**Requirements:** 26/26 complete

**Key accomplishments:**

1. PostGIS schema with canonical address normalization (SHA-256 cache keys) and provider plugin contract (GeocodingProvider/ValidationProvider ABCs)
2. Multi-provider geocoding with cache-first pipeline, admin override workflow (set to provider result or custom coordinate), and cache refresh endpoint
3. USPS address validation with scourgify (freeform + structured input, USPS abbreviation normalization, ZIP+4)
4. Multi-format GIS CLI import (GeoJSON/KML/SHP) with CRS reprojection, upsert, and OfficialGeocoding auto-set
5. Batch geocoding and validation endpoints with asyncio.gather, per-item error isolation, and configurable concurrency
6. Admin override table write fix and GIS-first import-order constraint documentation (gap closure from milestone audit)

**Delivered:** Internal geocoding and address validation caching API with multi-provider support, admin overrides, GIS import, and batch endpoints — 179 tests passing.

**Known tech debt:**

- VAL-06 delivery_point_verified always False (scourgify offline-only; real DPV needs paid USPS API)
- NO_MATCH location_type not in LocationType enum (guarded by confidence check)
- SHP file tests conditionally skip when sample data absent
- Address ORM model missing validation_results relationship

---
