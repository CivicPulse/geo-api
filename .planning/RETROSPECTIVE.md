# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-19
**Phases:** 6 | **Plans:** 12 | **Commits:** 82

### What Was Built
- PostGIS schema with canonical address normalization (SHA-256 cache keys) and provider plugin contract
- Multi-provider geocoding with cache-first pipeline, admin override workflow, and cache refresh
- USPS address validation via scourgify with freeform + structured input support
- Multi-format GIS CLI import (GeoJSON/KML/SHP) with CRS reprojection and upsert
- Batch geocoding and validation endpoints with asyncio.gather and per-item error isolation
- Docker Compose dev environment with PostGIS, Alembic migrations, and seed data

### What Worked
- **TDD pattern** — RED/GREEN commit discipline caught integration issues early (especially in Phase 3 and 4)
- **Cache-first service pattern** — GeocodingService and ValidationService follow identical normalize→hash→cache-check→provider-call→upsert pipeline; second service was fast to implement
- **Provider plugin ABC** — Clean separation of concerns; Census adapter was straightforward to build against the contract
- **Gap-closure phases** — Milestone audit found 4 partial requirements; Phases 5-6 closed them cleanly rather than shipping with known gaps
- **Parallel plan execution** — Independent plans within phases ran concurrently, reducing wall-clock time

### What Was Inefficient
- **Milestone audit found gaps that required 2 extra phases** — admin_overrides table was created but never written to by the API; this cross-phase integration gap wasn't caught during individual phase verification
- **SUMMARY frontmatter inconsistencies** — Several SUMMARY files had empty or incorrect requirements-completed arrays; required a dedicated cleanup phase
- **ROADMAP checkbox maintenance** — Plan checkboxes fell out of sync with execution status; manual bookkeeping is error-prone
- **VAL-06 ambiguity** — "ZIP+4 delivery point validation" requirement was satisfied by scourgify's offline normalization, but real DPV requires a paid USPS API; requirement text was ambiguous about which was needed

### Patterns Established
- `ON CONFLICT DO UPDATE` for geocoding_results upsert (not DO NOTHING) — ensures re-import refreshes coordinates
- `ON CONFLICT DO NOTHING` for official_geocoding — first-writer-wins, preserving existing official records
- Provider plugin ABC with typed error hierarchy (ProviderError, ProviderNetworkError, ProviderAuthError, ProviderRateLimitError)
- Two-URL database pattern: asyncpg for app, psycopg2 for Alembic
- Module-level `_geocode_one()` / `_validate_one()` helpers for batch orchestration in router layer

### Key Lessons
1. **Cross-phase integration testing is essential** — Individual phase verification passed for all 4 original phases, but the admin_overrides table gap only surfaced during milestone audit. Future milestones should run integration checks after each phase that depends on prior phases.
2. **Documentation traceability needs automation** — Manually maintaining SUMMARY frontmatter and ROADMAP checkboxes doesn't scale. Consider tooling to auto-update these fields from git commits.
3. **Requirement ambiguity surfaces late** — VAL-06's "delivery point validation" was interpretable two ways. Future requirement definitions should include explicit acceptance criteria distinguishing offline normalization from live API verification.

### Cost Observations
- Model mix: ~70% sonnet (execution), ~30% opus (planning/auditing)
- Sessions: ~6 (one per phase, plus audit and cleanup)
- Notable: Entire v1.0 shipped in 2 calendar days across 82 commits

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~6 | 6 | Established TDD, cache-first service, and provider plugin patterns |

### Cumulative Quality

| Milestone | Tests | LOC | Gap Closure Phases |
|-----------|-------|-----|-------------------|
| v1.0 | 179 | 7,488 | 2 (Phases 5-6) |

### Top Lessons (Verified Across Milestones)

1. Cross-phase integration gaps are invisible to within-phase verification — milestone audits catch them
