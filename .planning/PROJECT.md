# CivPulse Geo API

## What This Is

An internal REST API providing GIS/geospatial services to other CivPulse systems (run-api, vote-api, etc.). It acts as a smart caching layer over multiple external geocoding and address validation services, storing results locally to reduce expensive third-party API calls. Local data source providers (OpenAddresses, NAD, Tiger, Macon-Bibb GIS) query PostGIS staging tables directly for zero-cost geocoding and validation. System admins can override the "official" geocoded location for any address when services disagree.

## Core Value

Provide a single, reliable source of geocoded and validated address data across all CivPulse systems, minimizing cost by caching external service results, querying local data sources directly, and giving admins authority over the "official" answer.

## Requirements

### Validated

- ✓ PostgreSQL + PostGIS data storage — v1.0
- ✓ Plugin-style architecture for geocoding/validation service providers — v1.0
- ✓ Geocoding with multi-service caching and admin-overridable official records — v1.0
- ✓ Address validation/verification with USPS-standard normalization — v1.0
- ✓ GIS data import with upsert and OfficialGeocoding auto-set — v1.0
- ✓ Batch support for both geocoding and validation endpoints — v1.0
- ✓ Admin override coordinates persist to admin_overrides table (upsert) — v1.0
- ✓ GIS-first import ordering constraint documented in CLI — v1.0
- ✓ Documentation traceability: all SUMMARY frontmatter and ROADMAP checkboxes consistent — v1.0
- ✓ Local data source providers (OpenAddresses, NAD, PostGIS Tiger) — v1.1
- ✓ Both geocoding and validation interfaces for each local provider — v1.1
- ✓ Direct-return pipeline (no DB caching for local providers) — v1.1
- ✓ PostGIS Tiger geocoder with optional setup scripts — v1.1
- ✓ National Address Database provider with COPY-based bulk import — v1.1
- ✓ Batch endpoints serialize local_results/local_candidates per item — v1.1

### Active

- [ ] Cascading resolution pipeline that auto-sets official geocode from best available result
- [ ] Tiger county disambiguation via PostGIS spatial boundary post-filter
- [ ] Zip prefix fallback matching for truncated/mistyped zip codes in local providers
- [ ] Fuzzy/phonetic street matching (pg_trgm, Soundex/Metaphone) as exact-match fallback
- [ ] Spell correction layer for address input before provider dispatch
- [ ] Local LLM sidecar for address correction/completion when deterministic methods fail
- [ ] Cross-provider consensus scoring to flag outliers and weight agreement
- [ ] Validation confidence semantics fix (structural parse ≠ address-verified)
- [ ] Street name normalization mismatch fix for multi-word street names with USPS suffixes

## Current Milestone: v1.2 Cascading Address Resolution

**Goal:** Transform the multi-provider lookup into an auto-resolving cascading pipeline that progressively refines degraded address input into an accurate official geocode — transparent to end users.

**Target features:**
- Fix 5 known provider defects from E2E testing (Issue #1)
- Fuzzy/phonetic street matching via pg_trgm and Soundex/Metaphone
- Spell correction layer (offline library) before provider dispatch
- Local LLM sidecar for address correction/completion
- Cross-provider consensus scoring
- Cascading resolution pipeline: normalize → spell-correct → exact match → fuzzy match → AI correction → re-match → score consensus → auto-set official

### Out of Scope

- International addresses — US only for v1
- Admin UI — this API serves data; admin interface is a separate system
- Authentication — internal service, network-level security only
- Audit trail for admin overrides — deferred, not a v1 concern
- Reverse geocoding (lat/lng → address) — v2 candidate
- Cache expiration / TTL — addresses rarely change; manual refresh available
- Routing / directions / distance matrix — different problem domain
- Autocomplete / typeahead — interactive UX feature; this is a batch/point-lookup API
- Google Geocoding API — ToS prohibits caching results; incompatible with geo-api's core caching model
- Local provider result caching — local data is already local, no need to cache
- Collection ZIP multi-state import — single county files sufficient for now
- NAD FGDB import — TXT format preferred for bulk loading
- Real-time Tiger data updates — census-cycle data; manual refresh sufficient

## Context

Shipped v1.1 with ~10,000 LOC Python, 379 tests.
Tech stack: FastAPI, SQLAlchemy 2.0, GeoAlchemy2, asyncpg, httpx, Alembic, Pydantic, scourgify, fiona, Typer, Rich.
Database: PostgreSQL 17 + PostGIS 3.5.
Dev environment: Docker Compose (API + PostGIS with seed data and Tiger extensions).

Active providers: Census Geocoder (external, cached), OpenAddresses (local), Tiger (local, PostGIS SQL), NAD (local, bulk COPY), Macon-Bibb GIS (local, county-specific).

Part of the CivPulse ecosystem alongside run-api and vote-api. Internal API consumed by other CivPulse services, not directly by end users.

Known future provider candidates: USPS (for real DPV), Amazon Location Service, Geoapify.

## Constraints

- **Tech stack**: Python, FastAPI, Loguru, Typer — consistent with other CivPulse APIs
- **Package management**: `uv` for all Python environment and package management
- **Dev environment**: Docker Compose for local development (PostgreSQL/PostGIS + API)
- **Database**: PostgreSQL with PostGIS extension
- **Scope**: US addresses only
- **Network**: Internal API, no public exposure
- **Verification/UAT**: All testing and verification must be automated using Playwright MCP or Chrome DevTools MCP — no interactive/manual checkpoint prompts

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| No cache expiration | Addresses/locations rarely change; manual refresh available | ✓ Good — manual refresh endpoint covers the use case |
| No auth layer | Internal service behind network security | ✓ Good — simplifies API surface |
| Multiple service results stored separately | Enables comparison and admin override workflow | ✓ Good — core differentiator |
| PostGIS for geo storage | Native spatial indexing and queries for geo points | ✓ Good — Geography(POINT,4326) provides distance-in-meters semantics |
| SHA-256 canonical address hash | O(1) cache lookups, deterministic key from normalized address | ✓ Good — handles all suffix/directional/ZIP variants |
| Two database URLs (asyncpg + psycopg2) | Alembic requires synchronous driver | ✓ Good — clean separation of async app vs sync migrations |
| Census Geocoder as first provider | Free, no API key, no ToS risk | ✓ Good — unblocked development |
| scourgify for offline validation | No external API dependency for basic USPS normalization | ⚠️ Revisit — delivery_point_verified always False; real DPV needs paid USPS API |
| ON CONFLICT DO NOTHING for OfficialGeocoding | First-writer-wins preserves existing official records | ⚠️ Revisit — requires GIS import before API geocoding; documented as operational constraint |
| is_local property on provider ABCs | Concrete property (default False) — existing providers need zero changes | ✓ Good — clean pipeline split without breaking existing providers |
| Local providers bypass DB cache | Local data is already local — no value in caching | ✓ Good — eliminates unnecessary writes and simplifies pipeline |
| OA hash as source_hash | Trust OA deduplication, avoid SHA-256 overhead on 60k+ rows | ✓ Good — pragmatic trade-off |
| Tiger via PostGIS SQL functions | No staging table needed — geocode()/normalize_address() called directly | ✓ Good — leverages existing PostGIS extension infrastructure |
| NAD bulk COPY via temp table | COPY to nad_temp (TEXT), then upsert with ST_GeogFromText — avoids geography type in COPY stream | ✓ Good — handles 80M rows efficiently |
| Conditional provider registration | _oa_data_available / _nad_data_available / _tiger_extension_available checks at startup | ✓ Good — API starts cleanly regardless of which data is loaded |
| Google Geocoding API excluded | ToS Section 3.2.3(a) prohibits caching geocoding results | ✓ Good — removes legal risk; local providers cover the use case |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-29 — Phase 12 complete (Correctness Fixes and DB Prerequisites: 5-tuple parse expansion, Tiger county filter, confidence semantics, GIN trigram indexes)*
