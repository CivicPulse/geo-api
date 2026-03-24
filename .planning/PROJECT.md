# CivPulse Geo API

## What This Is

An internal REST API providing GIS/geospatial services to other CivPulse systems (run-api, vote-api, etc.). It acts as a smart caching layer over multiple external geocoding and address validation services, storing results locally to reduce expensive third-party API calls. System admins can override the "official" geocoded location for any address when services disagree.

## Core Value

Provide a single, reliable source of geocoded and validated address data across all CivPulse systems, minimizing cost by caching external service results and giving admins authority over the "official" answer.

## Requirements

### Validated

- [x] PostgreSQL + PostGIS data storage — v1.0
- [x] Plugin-style architecture for geocoding/validation service providers — v1.0
- [x] Geocoding with multi-service caching and admin-overridable official records — v1.0
- [x] Address validation/verification with USPS-standard normalization — v1.0
- [x] GIS data import with upsert and OfficialGeocoding auto-set — v1.0
- [x] Batch support for both geocoding and validation endpoints — v1.0
- [x] Admin override coordinates persist to admin_overrides table (upsert) — v1.0
- [x] GIS-first import ordering constraint documented in CLI — v1.0
- [x] Documentation traceability: all SUMMARY frontmatter and ROADMAP checkboxes consistent — v1.0

### Active

- [ ] Local data source providers (OpenAddresses, NAD, PostGIS Tiger/LINE)
- [ ] Both geocoding and validation interfaces for each local provider
- [x] Direct-return pipeline (no DB caching for local providers) — Validated in Phase 7-8
- [x] PostGIS Tiger geocoder with optional setup scripts — Validated in Phase 9

### Out of Scope

- International addresses — US only for v1
- Admin UI — this API serves data; admin interface is a separate system
- Authentication — internal service, network-level security only
- Audit trail for admin overrides — deferred, not a v1 concern
- Reverse geocoding (lat/lng → address) — v2 candidate
- Cache expiration / TTL — addresses rarely change; manual refresh available
- Routing / directions / distance matrix — different problem domain
- Autocomplete / typeahead — interactive UX feature; this is a batch/point-lookup API

## Current Milestone: v1.1 Local Data Sources

**Goal:** Add local data source providers (OpenAddresses, NAD, PostGIS Tiger/LINE geocoder) that implement the existing provider ABCs but query local data directly — no external API calls, no result caching.

**Target features:**
- OpenAddresses provider (geocoding + validation from `data/*.geojson.gz`)
- National Address Database (NAD) provider (geocoding + validation from `NAD_r21` datasets)
- PostGIS Tiger/LINE geocoder provider (geocoding + validation via PostgreSQL extension)
- Direct-return pipeline that bypasses DB caching for local providers
- Optional Tiger geocoder setup scripts (works with or without pre-installed extension)

## Context

Shipped v1.0 with 7,488 LOC Python, 179 tests passing.
Tech stack: FastAPI, SQLAlchemy 2.0, GeoAlchemy2, asyncpg, httpx, Alembic, Pydantic, scourgify, fiona, Typer.
Database: PostgreSQL 17 + PostGIS 3.5.
Dev environment: Docker Compose (API + PostGIS with seed data).

Part of the CivPulse ecosystem alongside run-api and vote-api. Internal API consumed by other CivPulse services, not directly by end users.

Known target providers: US Census Geocoder (implemented), Google Geocoding API (deferred — ToS review), USPS, Amazon Location Service, Geoapify.

## Constraints

- **Tech stack**: Python, FastAPI, Loguru, Typer — consistent with other CivPulse APIs
- **Package management**: `uv` for all Python environment and package management
- **Dev environment**: Docker Compose for local development (PostgreSQL/PostGIS + API)
- **Database**: PostgreSQL with PostGIS extension
- **Scope**: US addresses only
- **Network**: Internal API, no public exposure

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

---
*Last updated: 2026-03-24 after Phase 9 (Tiger Provider) complete*
