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

<!-- Current scope — v1.3 Production Readiness & Deployment -->

- [ ] Resolve all known tech debt and errors
- [ ] Thorough code review (security, stability, performance, logic, exceptions)
- [ ] Structured logging and distributed tracing for AI-assisted debugging
- [ ] K8s deployment to civpulse-dev and civpulse-prod (internal ClusterIP only)
- [ ] Ollama LLM sidecar in both environments
- [ ] Database provisioning (dev + prod)
- [x] CI/CD pipeline (GitHub Actions → GHCR → ArgoCD)
- [ ] E2E testing of all 5 providers in deployed prod
- [ ] Performance/load baselines and scaling validation
- [ ] Monitoring/logging validation under load
- [ ] Iterative bug-fix phases until clean final pass

## Current Milestone: v1.3 Production Readiness & Deployment

**Goal:** Harden, deploy, test, and validate the geo-api across dev and prod K8s environments with full observability, ensuring all providers work correctly at scale.

**Target features:**
- Resolve all known tech debt and errors (Tiger timeout, cache_hit hardcode, empty spell dictionary, CLI test failures)
- Thorough code review for security, stability, performance, logic errors, uncaught exceptions
- Structured logging and distributed tracing (Grafana Alloy → Loki, OTLP → Tempo) for AI-assisted debugging
- Multi-stage Dockerfile, K8s manifests (Deployment + ClusterIP Service), ArgoCD apps, CI/CD pipeline
- Ollama LLM sidecar deployed alongside geo-api in both environments
- Database provisioning on shared PostgreSQL instance (dev + prod)
- Internal ClusterIP service only — no Ingress/IngressRoute
- Debugging/testing access via kubectl port-forward and/or NodePort
- Extensive E2E testing: all 5 providers, performance baselines (P50/P95/P99), load/scaling
- Monitoring/logging validation under load
- Iterative bug-fix phases: blockers resolved in-phase, non-blockers logged for subsequent phases
- Final top-to-bottom validation pass repeating all checks until clean

### Validated (v1.2)

- ✓ Cascading resolution pipeline that auto-sets official geocode from best available result — v1.2, Phase 14
- ✓ Tiger county disambiguation via PostGIS spatial boundary post-filter — v1.2, Phase 12
- ✓ Zip prefix fallback matching for truncated/mistyped zip codes in local providers — v1.2, Phase 12
- ✓ Fuzzy/phonetic street matching (pg_trgm, Double Metaphone) as exact-match fallback — v1.2, Phase 13/16
- ✓ Spell correction layer for address input before provider dispatch — v1.2, Phase 13
- ✓ Local LLM sidecar for address correction/completion when deterministic methods fail — v1.2, Phase 15
- ✓ Cross-provider consensus scoring to flag outliers and weight agreement — v1.2, Phase 14
- ✓ Validation confidence semantics fix (structural parse ≠ address-verified) — v1.2, Phase 12
- ✓ Street name normalization mismatch fix for multi-word street names with USPS suffixes — v1.2, Phase 12

### Validated (v1.3)

- ✓ Security audit — no hardcoded credentials, input validation on all external inputs, provider allowlist — v1.3, Phase 18
- ✓ Stability audit — global exception handler, per-provider error isolation in legacy path — v1.3, Phase 18
- ✓ Performance audit — explicit connection pool sizing, corrected provider weight mapping — v1.3, Phase 18
- ✓ Multi-stage production Dockerfile with non-root appuser, pushed to GHCR — v1.3, Phase 19
- ✓ Database provisioned on shared PostgreSQL instance (dev + prod) with Alembic migrations — v1.3, Phase 19
- ✓ Health probes (/health/live liveness, /health/ready readiness with DB + provider threshold) — v1.3, Phase 20
- ✓ Graceful shutdown with engine disposal, SIGTERM handler, preStop hook — v1.3, Phase 20
- ✓ K8s Kustomize base + overlays (dev/prod) with native Ollama sidecar, init containers, ArgoCD CRs — v1.3, Phase 20
- ✓ CI/CD pipeline: GitHub Actions CI gate (ruff + pytest), CD (Docker build → Trivy scan → GHCR push → ArgoCD dev deploy), production promotion via git tag — v1.3, Phase 21

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
- Tailscale controller for internal user access — future milestone
- Public Ingress/IngressRoute — geo-api is internal-only, accessed by in-cluster services

## Context

Shipped v1.2 with ~8,153 LOC Python, 504 tests (11 pre-existing failures in CLI fixture tests).
Tech stack: FastAPI, SQLAlchemy 2.0, GeoAlchemy2, asyncpg, httpx, Alembic, Pydantic, scourgify, symspellpy, fiona, Typer, Rich.
Database: PostgreSQL 17 + PostGIS 3.5 + pg_trgm + fuzzystrmatch extensions.
Dev environment: Docker Compose (API + PostGIS + optional Ollama LLM sidecar via `--profile llm`).

Active providers: Census Geocoder (external, cached), OpenAddresses (local), Tiger (local, PostGIS SQL), NAD (local, bulk COPY), Macon-Bibb GIS (local, county-specific).
Cascade pipeline: normalize → spell-correct → exact match (parallel, 5 providers) → fuzzy match (pg_trgm + dmetaphone) → LLM correction (Ollama qwen2.5:3b) → consensus scoring → auto-set official.

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
| symspellpy for spell correction | Offline, fast, no external dependency | ✓ Good — sub-ms correction with dictionary from staging tables |
| pg_trgm + dmetaphone for fuzzy matching | Built-in PostgreSQL extensions, no app-level indexing | ✓ Good — leverages GIN indexes, phonetic tiebreaker resolves ambiguity |
| CascadeOrchestrator as staged pipeline | 6-stage progressive refinement with early-exit optimization | ✓ Good — P95 < 3s, transparent to callers |
| 100m cluster radius, 1km outlier threshold | Calibrated against Issue #1 test corpus (4 Macon addresses) | ✓ Good — stable across multiple test runs |
| Ollama qwen2.5:3b for LLM sidecar | Local-only, 3B params, structured JSON output | ✓ Good — no data leaves network, fast enough for single-address correction |
| Docker Compose profiles for Ollama | `--profile llm` avoids 2GB model download for devs not using LLM | ✓ Good — opt-in activation |
| Direct httpx for Ollama client | Reuses existing AsyncClient, no new dependency | ✓ Good — full timeout control, simple integration |

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
*Last updated: 2026-03-30 after Phase 21 complete*
