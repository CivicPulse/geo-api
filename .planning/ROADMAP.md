# Roadmap: CivPulse Geo API

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-19)
- ✅ **v1.1 Local Data Sources** — Phases 7-11 (shipped 2026-03-29)
- ✅ **v1.2 Cascading Address Resolution** — Phases 12-16 (shipped 2026-03-29)
- ✅ **v1.3 Production Readiness & Deployment** — Phases 17-23 (shipped 2026-04-03)

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

<details>
<summary>✅ v1.2 Cascading Address Resolution (Phases 12-16) — SHIPPED 2026-03-29</summary>

- [x] **Phase 12: Correctness Fixes and DB Prerequisites** — Fix 4 known provider defects and add GIN trigram indexes (2/2 plans) — completed 2026-03-29
- [x] **Phase 13: Spell Correction and Fuzzy/Phonetic Matching** — Offline spell correction and pg_trgm + Double Metaphone fallback (2/2 plans) — completed 2026-03-29
- [x] **Phase 14: Cascade Orchestrator and Consensus Scoring** — 6-stage cascade pipeline with cross-provider consensus and auto-set official (3/3 plans) — completed 2026-03-29
- [x] **Phase 15: LLM Sidecar** — Local Ollama qwen2.5:3b for address correction when deterministic stages fail (3/3 plans) — completed 2026-03-29
- [x] **Phase 16: Audit Gap Closure** — FuzzyMatcher startup wiring, legacy 5-tuple fix, Phase 13 verification (1/1 plan) — completed 2026-03-29

Full details archived in `milestones/v1.2-ROADMAP.md`.

</details>

<details>
<summary>✅ v1.3 Production Readiness & Deployment (Phases 17-23) — SHIPPED 2026-04-03</summary>

- [x] **Phase 17: Tech Debt Resolution** — Resolve all 4 known runtime defects (2/2 plans) — completed 2026-03-29
- [x] **Phase 18: Code Review** — Parallel security, stability, performance audit (3/3 plans) — completed 2026-03-30
- [x] **Phase 19: Dockerfile and Database Provisioning** — Multi-stage Docker image + DB provisioning (2/2 plans) — completed 2026-03-30
- [x] **Phase 20: Health, Resilience, and K8s Manifests** — Health probes, graceful shutdown, K8s manifests (3/3 plans) — completed 2026-03-30
- [x] **Phase 21: CI/CD Pipeline** — GitHub Actions CI/CD with Trivy scan (2/2 plans) — completed 2026-03-30
- [x] **Phase 22: Observability** — Structured logging, Prometheus metrics, OTel traces (3/3 plans) — completed 2026-03-30
- [x] **Phase 23: E2E Testing, Load Baselines, and Final Validation** — Full E2E + load + observability + validation (9/9 plans) — completed 2026-04-03

Full details archived in `milestones/v1.3-ROADMAP.md`.

</details>

## Phase Details

*No active phases — all milestones shipped. Run `/gsd:new-milestone` to start next.*
