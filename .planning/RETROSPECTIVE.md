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

## Milestone: v1.1 — Local Data Sources

**Shipped:** 2026-03-29
**Phases:** 5 | **Plans:** 9 | **Timeline:** 9 days (2026-03-20 → 2026-03-29)

### What Was Built
- Direct-return pipeline bypass — local providers skip DB caching entirely via `is_local` property on provider ABCs
- OpenAddresses geocoding/validation from `.geojson.gz` files with accuracy-mapped confidence scores
- PostGIS Tiger geocoder via SQL functions (geocode/normalize_address) with graceful degradation
- NAD geocoding/validation with COPY-based bulk import handling 80M+ rows via temp table
- Batch endpoint local provider serialization fix (GAP-INT-01 closure)
- Bonus quick tasks: Macon-Bibb GIS provider, OA parcel boundaries, debugpy, README, Postman collection

### What Worked
- **Provider ABC extensibility** — is_local as a concrete property meant zero changes to existing providers; the plugin architecture from v1.0 paid off immediately
- **Build order (Pipeline → OA → Tiger → NAD)** — increasing complexity order meant each provider was faster to build than the last; patterns established in OA were reused in Tiger and NAD
- **Reusable address parsing** — `_parse_input_address` from OA module reused in NAD provider, avoiding duplication
- **Milestone audit before completion** — caught GAP-INT-01 (batch serialization) and TIGR-05 documentation gap before shipping
- **Quick task workflow** — 7 quick tasks shipped alongside milestone phases without disrupting the main roadmap

### What Was Inefficient
- **Tiger extension check used wrong system catalog** — `pg_available_extensions` (what could be installed) instead of `pg_extension` (what is installed); caught by milestone audit and fixed in quick task 260324-lqg
- **09-02 SUMMARY had empty one-liner** — summary-extract returned "One-liner:" with no content, requiring manual cleanup in MILESTONES.md
- **Phase 8 VERIFICATION.md became stale** — said OA registration was unconditional, but Phase 7 UAT gap-5 fix had added conditional check; verification doc wasn't re-run

### Patterns Established
- `_data_available()` conditional registration pattern — check staging table row count at startup, log warning if empty
- `bare except` in availability checks — ensure API starts cleanly regardless of which data is loaded
- COPY via temp table pattern — COPY into TEXT temp table, then upsert with spatial conversion
- Provider-specific `**kwargs` in geocode() — absorbs extra arguments from service layer without TypeError

### Key Lessons
1. **Verify your verification** — Phase 8's VERIFICATION.md became stale after a Phase 7 post-UAT fix. Verification docs should be re-validated if upstream phases change.
2. **System catalog queries need precision** — `pg_available_extensions` vs `pg_extension` is a subtle but critical distinction. Always test with the extension both installed and not installed.
3. **Quick tasks are high-value** — Macon-Bibb provider, debugpy, Postman collection, and README shipped as quick tasks alongside the main roadmap. The lightweight workflow keeps momentum.

### Cost Observations
- Model mix: ~65% sonnet (execution), ~35% opus (planning/auditing/milestone)
- Sessions: ~8 (phases + audit + quick tasks + completion)
- Notable: 5 providers fully operational in 9 calendar days; quick tasks added significant value without roadmap overhead

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~6 | 6 | Established TDD, cache-first service, and provider plugin patterns |
| v1.1 | ~8 | 5 | Proved provider ABC extensibility; established conditional registration and COPY-via-temp patterns |

### Cumulative Quality

| Milestone | Tests | LOC | Gap Closure Phases |
|-----------|-------|-----|-------------------|
| v1.0 | 179 | 7,488 | 2 (Phases 5-6) |
| v1.1 | 379 | ~10,000 | 1 (Phase 11) |

### Top Lessons (Verified Across Milestones)

1. Cross-phase integration gaps are invisible to within-phase verification — milestone audits catch them (v1.0 admin_overrides, v1.1 batch serialization)
2. Verification docs become stale when upstream phases change — re-validate after cross-phase fixes
3. Quick task workflow adds significant value without disrupting roadmap execution
