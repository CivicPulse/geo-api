# Milestones

## v1.3 Production Readiness & Deployment (Shipped: 2026-04-03)

**Phases completed:** 7 phases, 24 plans, 34 tasks

**Key accomplishments:**

- OA accuracy parser fixed (None not 'parcel'), Tiger gets dedicated 3s timeout via per-provider map, and cascade cache-hit early exit wired with consensus re-run populating would_set_official retroactively
- Startup auto-rebuilds spell_dictionary when empty and staging tables have data, eliminating manual CLI step after data loads
- 4 security blockers resolved via Pydantic field constraints and provider allowlist: hardcoded DB credentials removed (CHANGEME placeholders), all address inputs capped at 500 chars, lat/lng range validated, unknown provider names rejected before service dispatch
- Global FastAPI exception handler (STAB-01/02) and per-provider loop guards (STAB-04) resolving all three stability blockers with 3 regression tests
- One-liner:
- Docker image pushed to ghcr.io/civicpulse/geo-api:sha-42d5282 (public), both dev/prod databases provisioned on host PG with PostGIS/pg_trgm/fuzzystrmatch, Alembic migrations applied (12 tables), and connectivity verified from K8s pods in both namespaces
- Split K8s health probes with /health/live (process-only) and /health/ready (DB + provider threshold), plus lifespan engine disposal and SIGTERM safety-net handler
- Kustomize dev and prod overlays with env-specific ConfigMap patches, ArgoCD Application CRs for GitOps sync, and obsolete standalone Ollama manifests removed
- GitHub Actions CI workflow (ruff lint + pytest) with SHA-pinned actions, minimal read permissions, and .trivyignore skeleton for CVE suppression
- Loguru JSON structured logging, Prometheus metric definitions (3 tiers), RequestIDMiddleware with UUID4 propagation, and GET /metrics endpoint installed as standalone importable modules
- OpenTelemetry TracerProvider with OTLP gRPC exporter, Loguru trace_id/span_id patcher via lazy get_current_span(), and fully wired main.py lifespan (configure_logging -> setup_tracing -> providers -> teardown_tracing -> engine.dispose)
- geo-api deployed to civpulse-prod and civpulse-dev with all 5 providers registered, ArgoCD Synced/Healthy, and /health/ready returning 200 — prerequisite for E2E, load, and observability plans
- Loaded OpenAddresses (67,731), NAD (206,699), and Macon-Bibb (67,730) address datasets into prod PostgreSQL, triggering spell_dictionary rebuild (4,456 words) and enabling all 5 providers to register at pod startup — /health/ready now reports geocoding_providers:5, validation_providers:5
- Tempo OTLP connectivity and Tiger provider registration both confirmed operational in dev and prod - all 5 providers register at startup with no OTLP errors
- 12/12 E2E tests pass for all 5 providers; Locust baselines captured (cold/warm, 30 users); Loki + Tempo + VictoriaMetrics all verified passing after adding geo-api scrape targets to VictoriaMetrics
- 23-VALIDATION-CHECKLIST.md populated with run 1 results across all 7 categories — VAL-03 clean pass achieved with 35 PASS items, 2 DEFERRED non-blockers (load test P95 thresholds due to port-forward infra constraints), and no open blockers

---

## v1.2 Cascading Address Resolution (Shipped: 2026-03-29)

**Phases:** 5 | **Plans:** 11 | **Commits:** 94 | **Files:** 107 | **LOC:** 8,153 Python
**Timeline:** 2026-03-29 (single day)
**Git range:** v1.1..78754b0
**Requirements:** 25/25 complete

**Key accomplishments:**

1. Fixed 4 provider defects (Tiger wrong-county, truncated ZIP, suffix matching, confidence semantics) and added GIN trigram indexes for fuzzy matching
2. Spell correction layer (symspellpy) with auto-rebuilding dictionary from OA/NAD/Macon-Bibb/Tiger street names
3. FuzzyMatcher service with pg_trgm word_similarity() + Double Metaphone tiebreaker across all local staging tables
4. CascadeOrchestrator with 6-stage pipeline: normalize → spell-correct → exact match → fuzzy → LLM → consensus scoring with auto-set official geocode
5. Local Ollama LLM sidecar (qwen2.5:3b) for address correction when deterministic stages fail, with zip/state guardrails and Docker/K8s deployment
6. Audit gap closure: FuzzyMatcher startup wiring, legacy 5-tuple unpack fix, Phase 13 formal verification

**Delivered:** Auto-resolving cascading geocode pipeline that progressively refines degraded address input (typos, truncated ZIPs, misspellings) into an accurate official geocode — transparent to callers, with cross-provider consensus scoring and outlier detection.

**Known tech debt:**

- Tiger provider times out at 2000ms under load (wrong-county outlier fix works when Tiger responds)
- Cascade path hardcodes cache_hit=False (repeated calls re-dispatch all providers)
- No geo-api K8s Deployment manifest (Ollama K8s manifests exist but geo-api needs env var injection)
- Pre-existing CLI test failures: test_import_cli.py, test_load_oa_cli.py (missing fixture data)
- spell_dictionary starts empty until rebuild-spell-dictionary CLI is run

---

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
