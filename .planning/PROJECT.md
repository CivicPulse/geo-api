# CivPulse Geo API

## What This Is

An internal REST API providing GIS/geospatial services to other CivPulse systems (run-api, vote-api, etc.). It acts as a smart caching layer over multiple external geocoding and address validation services, storing results locally to reduce expensive third-party API calls. System admins can override the "official" geocoded location for any address when services disagree.

## Core Value

Provide a single, reliable source of geocoded and validated address data across all CivPulse systems, minimizing cost by caching external service results and giving admins authority over the "official" answer.

## Requirements

### Validated

- [x] PostgreSQL + PostGIS data storage — Validated in Phase 1: Foundation
- [x] Plugin-style architecture for geocoding/validation service providers — Validated in Phase 1: Foundation

### Active

- [x] Geocoding with multi-service caching and admin-overridable official records — Validated in Phase 2: Geocoding
- [x] Address validation/verification with USPS-standard normalization — Validated in Phase 3: Validation and Data Import
- [x] GIS data import with upsert and OfficialGeocoding auto-set — Validated in Phase 3: Validation and Data Import
- [x] Batch support for both geocoding and validation endpoints — Validated in Phase 4: Batch and Hardening
- [x] Admin override coordinates persist to admin_overrides table (upsert) — Validated in Phase 5: Fix Admin Override & Import Order
- [x] GIS-first import ordering constraint documented in CLI — Validated in Phase 5: Fix Admin Override & Import Order

### Out of Scope

- International addresses — US only for v1
- Admin UI — this API serves data; admin interface is a separate system
- Authentication — internal service, network-level security only
- Audit trail for admin overrides — deferred, not a v1 concern

## Context

- Part of the CivPulse ecosystem alongside run-api and vote-api
- Uses the same tech stack: Python, FastAPI, Loguru, Typer
- Internal API consumed by other CivPulse services, not directly by end users
- Known target services: Google Geocoding API, USPS, US Census Geocoder, Amazon Location Service, Geoapify — more welcome
- Addresses often get different geocode results from different services; admins need to pick the correct one or set a custom location
- Address validation must handle partial/invalid input and return USPS-standardized suggestions (e.g., "road" → "RD", "Georga" → "GA", proper casing)
- Validation accepts both freeform string input and structured field-based input
- Cached results do not expire — once stored, treated as permanent unless manually refreshed
- When multiple corrected addresses are possible, return all suggestions ranked with confidence scores

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
| No cache expiration | Addresses/locations rarely change; manual refresh available | — Pending |
| No auth layer | Internal service behind network security | — Pending |
| Multiple service results stored separately | Enables comparison and admin override workflow | — Pending |
| PostGIS for geo storage | Native spatial indexing and queries for geo points | — Pending |

---
*Last updated: 2026-03-19 after Phase 5: Fix Admin Override & Import Order complete — gap closure for admin_overrides write and DATA-03 documentation*
