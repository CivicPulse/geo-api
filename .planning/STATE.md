---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Local Data Sources
status: unknown
stopped_at: Completed 11-01-PLAN.md
last_updated: "2026-03-24T14:45:03.427Z"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 9
  completed_plans: 9
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-20)

**Core value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching and giving admins authority over the official answer
**Current focus:** v1.1 milestone complete — all phases delivered

## Current Position

Phase: 11 (Fix Batch Local Serialization) — COMPLETE
Plan: 1 of 1 (complete)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.1 Roadmap]: Local providers bypass DB cache entirely via is_local property on provider ABCs — establish this before any provider is implemented
- [v1.1 Roadmap]: Build order is Pipeline → OA → Tiger → NAD (complexity and scale increasing; Tiger before NAD to isolate SQL function pattern from table-query pattern)
- [v1.1 Research]: No new Python dependencies — gzip/json/csv stdlib + usaddress (transitive) + existing asyncpg/sqlalchemy cover all three providers
- [07-01]: is_local is a concrete property (not abstract) so existing providers need zero changes
- [07-01]: OfficialGeocoding auto-set skipped for local-only requests — no ORM row to reference
- [07-01]: AsyncMock(spec=GeocodingProvider) returns truthy mock for is_local — test helpers must explicitly set is_local=False
- [07-02]: Staging table source_hash is String(64) for SHA-256 hex digests supporting upsert deduplication
- [07-02]: load-oa validates .geojson.gz extension; load-nad validates file existence only (Phase 10 validates TXT format)
- [07-02]: CLI stubs use raise typer.Exit(0) pattern for clean exit with Typer CliRunner
- [08-02]: OA hash used directly as source_hash (not recomputed) — trusts OA deduplication, avoids SHA-256 overhead on 60k+ rows
- [08-02]: engine.connect() used over engine.begin() so _upsert_oa_batch can call conn.commit() per batch for incremental durability
- [08-02]: Two-pass .geojson.gz approach (count then import) accepted for clean Rich progress bar despite reading file twice
- [Phase 08]: geocode() accepts **kwargs to avoid TypeError from service layer http_client= call
- [Phase 08]: OA providers registered directly in lifespan (not via load_providers) because they require async_sessionmaker
- [Phase 08]: ST_Y/ST_X lat/lng extracted in same SELECT as row fetch to avoid second DB round-trip
- [09-01]: Tiger calls PostGIS SQL functions directly (geocode/normalize_address) rather than staging table — no data import step needed
- [09-01]: Confidence = max(0.0, min(1.0, (100 - rating) / 100)) — clamped to never be negative for ratings > 100
- [09-01]: _tiger_extension_available uses bare except to ensure startup never crashes when Tiger is absent
- [09-01]: Provider count log lines moved after Tiger registration block to report final inclusive count
- [Phase 09]: setup-tiger installs extensions only in Docker init script — data download deferred to manual CLI invocation
- [10-01]: _parse_input_address reused from openaddresses module — no address parsing duplication across OA and NAD providers
- [10-01]: PLACEMENT_MAP has exactly 7 keys covering all known NAD Placement values; DEFAULT_PLACEMENT ('APPROXIMATE', 0.1) handles None/empty/unknown/garbage
- [10-01]: NAD providers use nad_row.state (not .region) and nad_row.zip_code (not .postcode) — column names differ from OA
- [10-01]: _nad_data_available uses bare except to ensure startup never crashes even if nad_points table doesn't exist yet
- [Phase 10-nad-provider]: load-nad: COPY targets nad_temp (TEXT) then ST_GeogFromText in upsert SQL — avoids geography type complications in psycopg2 COPY streams
- [Phase 10-nad-provider]: load-nad city fallback is case-insensitive 'not stated' check — handles both 'Not stated' and 'Not Stated' variants in NAD source data
- [Phase 11]: GAP-INT-01 closed — batch endpoints now serialize local_results/local_candidates identically to single-address endpoints (fix applied in f6f904d)

### Pending Todos

None.

### Blockers/Concerns (Carry Forward)

- [Phase 9 Tiger]: MEDIUM confidence that all five Tiger extensions are present in postgis/postgis:17-3.5 — verify with pg_available_extensions query before writing provider code
- Google Maps Platform ToS caching clause must be reviewed before building the Google adapter
- VAL-06 delivery_point_verified is always False with scourgify — real DPV needs a paid USPS API adapter

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260324-lqg | fix Tiger extension check predicate | 2026-03-24 | 86ef71b | [260324-lqg-fix-tiger-extension-check-predicate](./quick/260324-lqg-fix-tiger-extension-check-predicate/) |

## Session Continuity

Last activity: 2026-03-24 - Completed quick task 260324-lqg: fix Tiger extension check predicate
Stopped at: Completed quick task 260324-lqg
Resume file: None
