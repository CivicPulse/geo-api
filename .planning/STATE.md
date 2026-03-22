---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Local Data Sources
status: unknown
stopped_at: Completed 08-01-PLAN.md
last_updated: "2026-03-22T20:07:21.329Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-20)

**Core value:** Single, reliable source of geocoded and validated address data across CivPulse systems — minimizing cost through caching and giving admins authority over the official answer
**Current focus:** Phase 08 — openaddresses-provider

## Current Position

Phase: 08 (openaddresses-provider) — EXECUTING
Plan: 2 of 2 (complete)

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

### Pending Todos

None.

### Blockers/Concerns (Carry Forward)

- [Phase 9 Tiger]: MEDIUM confidence that all five Tiger extensions are present in postgis/postgis:17-3.5 — verify with pg_available_extensions query before writing provider code
- Google Maps Platform ToS caching clause must be reviewed before building the Google adapter
- VAL-06 delivery_point_verified is always False with scourgify — real DPV needs a paid USPS API adapter

## Session Continuity

Last session: 2026-03-22T20:03:39.110Z
Stopped at: Completed 08-01-PLAN.md
Resume file: None
