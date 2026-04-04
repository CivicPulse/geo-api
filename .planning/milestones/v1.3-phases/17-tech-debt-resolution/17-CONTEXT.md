# Phase 17: Tech Debt Resolution - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Resolve all 4 known runtime defects (DEBT-01 through DEBT-04) so the codebase is clean for Phase 18 code review. No new features — only fixing broken behavior and making the full test suite pass.

</domain>

<decisions>
## Implementation Decisions

### Tiger Timeout (DEBT-01)
- **D-01:** Add per-provider timeout configuration (env-var driven via Settings class) for ALL providers, not just Tiger. Tiger gets `tiger_timeout_ms=3000`, others default to `2000ms`.
- **D-02:** Optimize Tiger queries with both `restrict_region` parameter AND `LIMIT` clauses to reduce PostGIS geocode() execution time.
- **D-03:** When a provider times out, fail-open: log a warning and return empty results. The cascade continues to the next stage. Consistent with how Tiger already handles missing extension at startup.

### Cache Hit Detection (DEBT-02)
- **D-04:** Add early-exit cache check in `CascadeOrchestrator.run()` before Stage 2 (exact match). If address exists with cached geocoding_results, skip the provider-calling stages. Mirror the legacy path's cache detection pattern.
- **D-05:** On a cache hit, re-run consensus scoring (Stage 5) on the cached results before returning. This ensures provider weight changes take effect retroactively. Local providers still run fresh since they're never cached.
- **D-06:** Return `cache_hit=True` in `CascadeResult` on the early-exit path.

### Spell Dictionary Auto-Population (DEBT-03)
- **D-07:** At startup (in lifespan function), check if `spell_dictionary` table is empty. If empty AND staging tables (openaddresses_points, nad_points, macon_bibb_points) have data, auto-run `rebuild_dictionary()` before loading the spell corrector. If staging tables are also empty, skip silently (no data to build from).
- **D-08:** Only auto-rebuild when empty — if spell_dictionary already has rows, just load it (no TRUNCATE + re-insert on every restart).
- **D-09:** Phase 20 will also add a K8s init container for spell dictionary rebuild as an optimization. Belt and suspenders: app handles it itself, init container pre-warms it.

### CLI Test Fixtures (DEBT-04)
- **D-10:** Sample fixture files (`SAMPLE_Address_Points.geojson`, `SAMPLE_MBIT2017.DBO.AddressPoint.kml`) have been created from dev VM data with 5 features each. These are committed to `data/` directory.
- **D-11:** Fix `_parse_oa_feature()` in `src/civpulse_geo/cli/__init__.py:575` — change the `accuracy` field handling so empty string `""` becomes `None` instead of defaulting to `"parcel"`. Only apply `"parcel"` default when accuracy is truly missing (`None`/absent).

### Claude's Discretion
- Tiger query optimization specifics (exact restrict_region parameters, LIMIT values) — Claude picks based on what the Tiger provider code reveals during implementation.
- Whether per-provider timeout settings use a flat config pattern (`census_timeout_ms`, `tiger_timeout_ms`, etc.) or a nested/dict-based pattern — Claude picks the approach most consistent with the existing `config.py` style.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — DEBT-01 through DEBT-04 acceptance criteria
- `.planning/ROADMAP.md` §Phase 17 — Success criteria (lines 67-75)

### Source Files (primary targets)
- `src/civpulse_geo/config.py` — Settings class with timeout configs (DEBT-01)
- `src/civpulse_geo/services/cascade.py` — CascadeOrchestrator.run() pipeline (DEBT-01, DEBT-02)
- `src/civpulse_geo/services/geocoding.py` — Legacy cache-hit pattern to mirror (DEBT-02)
- `src/civpulse_geo/services/validation.py` — Validation service cache path (reference)
- `src/civpulse_geo/main.py` — Lifespan function, spell corrector loading (DEBT-03)
- `src/civpulse_geo/spell/corrector.py` — rebuild_dictionary() and load_spell_corrector() (DEBT-03)
- `src/civpulse_geo/cli/__init__.py` — _parse_oa_feature() accuracy bug (DEBT-04)
- `src/civpulse_geo/providers/tiger.py` — Tiger provider implementation (DEBT-01 optimization)

### Test Files
- `tests/test_import_cli.py` — CLI import tests (10 previously failing, now passing with fixtures)
- `tests/test_load_oa_cli.py` — OA CLI tests (1 remaining failure: accuracy parser bug)
- `tests/test_cascade.py` — Cascade tests with timeout mocking (DEBT-01, DEBT-02)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GeocodingService._legacy_geocode()` at `geocoding.py:133` — Has correct cache-hit detection pattern (check `address.geocoding_results`, return early with `cache_hit=True`). The cascade path should mirror this logic.
- `rebuild_dictionary()` at `spell/corrector.py` — Already exists as a standalone function. Can be called from lifespan with a sync connection.
- `load_spell_corrector()` at `spell/corrector.py:141` — Already used at startup. Just needs the rebuild-if-empty check before it.

### Established Patterns
- **Config pattern**: All settings are flat fields on `Settings(BaseSettings)` class, env-var overridable. Per-provider timeouts should follow same flat pattern.
- **Provider registration**: Conditional registration in lifespan with `_*_available()` guards. Spell dictionary auto-rebuild should follow similar try/except + warning pattern.
- **Cascade stages**: Each stage is a numbered block with timing, trace logging, and clear entry/exit. Cache check should be inserted before Stage 2 as a new early-exit path.

### Integration Points
- Cascade timeout: `asyncio.wait_for()` or `asyncio.timeout()` wrapping provider calls in Stage 2 (exact match parallel dispatch)
- Lifespan: Sync engine already created for spell corrector loading — rebuild_dictionary() needs the same sync connection
- Test fixtures: `data/` directory, referenced via `DATA_DIR = Path(__file__).parent.parent / "data"` in tests

</code_context>

<specifics>
## Specific Ideas

No specific requirements — standard approaches for all 4 defects. User emphasized belt-and-suspenders for spell dictionary (app auto-rebuild + K8s init container in Phase 20).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 17-tech-debt-resolution*
*Context gathered: 2026-03-29*
