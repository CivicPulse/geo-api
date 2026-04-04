# Phase 17: Tech Debt Resolution - Research

**Researched:** 2026-03-29
**Domain:** Python/asyncio bug fixes — timeout configuration, cache detection, startup initialization, CLI parser correctness
**Confidence:** HIGH

## Summary

Phase 17 resolves four known runtime defects carried forward from v1.2. All four bugs are code-level fixes with fully understood root causes. No new architecture is required — the changes are surgical edits to existing files identified in CONTEXT.md.

The test suite currently has 517 collected entries (not 504 as the roadmap estimated). Of those, **1 is failing** (the `accuracy` empty-string bug in `_parse_oa_feature`). The other 516 pass. DEBT-04 is mostly resolved by the fixture files already committed to `data/` — only the single `accuracy` bug fix remains to get to a clean run.

DEBT-01, DEBT-02, and DEBT-03 require new code, but all three patterns to follow are already present in the codebase: per-field `Settings` flat config, legacy cache-hit logic in `_legacy_geocode()`, and sync-engine startup initialization for the spell corrector.

**Primary recommendation:** Fix bugs in the exact order DEBT-04, DEBT-02, DEBT-01, DEBT-03. Start with DEBT-04 since it is one-line, run the test suite to confirm 517/517, then implement the remaining three defects.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Tiger Timeout (DEBT-01)
- **D-01:** Add per-provider timeout configuration (env-var driven via Settings class) for ALL providers, not just Tiger. Tiger gets `tiger_timeout_ms=3000`, others default to `2000ms`.
- **D-02:** Optimize Tiger queries with both `restrict_region` parameter AND `LIMIT` clauses to reduce PostGIS geocode() execution time.
- **D-03:** When a provider times out, fail-open: log a warning and return empty results. The cascade continues to the next stage. Consistent with how Tiger already handles missing extension at startup.

#### Cache Hit Detection (DEBT-02)
- **D-04:** Add early-exit cache check in `CascadeOrchestrator.run()` before Stage 2 (exact match). If address exists with cached geocoding_results, skip the provider-calling stages. Mirror the legacy path's cache detection pattern.
- **D-05:** On a cache hit, re-run consensus scoring (Stage 5) on the cached results before returning. This ensures provider weight changes take effect retroactively. Local providers still run fresh since they're never cached.
- **D-06:** Return `cache_hit=True` in `CascadeResult` on the early-exit path.

#### Spell Dictionary Auto-Population (DEBT-03)
- **D-07:** At startup (in lifespan function), check if `spell_dictionary` table is empty. If empty AND staging tables (openaddresses_points, nad_points, macon_bibb_points) have data, auto-run `rebuild_dictionary()` before loading the spell corrector. If staging tables are also empty, skip silently (no data to build from).
- **D-08:** Only auto-rebuild when empty — if spell_dictionary already has rows, just load it (no TRUNCATE + re-insert on every restart).
- **D-09:** Phase 20 will also add a K8s init container for spell dictionary rebuild as an optimization. Belt and suspenders: app handles it itself, init container pre-warms it.

#### CLI Test Fixtures (DEBT-04)
- **D-10:** Sample fixture files (`SAMPLE_Address_Points.geojson`, `SAMPLE_MBIT2017.DBO.AddressPoint.kml`) have been created from dev VM data with 5 features each. These are committed to `data/` directory.
- **D-11:** Fix `_parse_oa_feature()` in `src/civpulse_geo/cli/__init__.py:575` — change the `accuracy` field handling so empty string `""` becomes `None` instead of defaulting to `"parcel"`. Only apply `"parcel"` default when accuracy is truly missing (`None`/absent).

### Claude's Discretion
- Tiger query optimization specifics (exact restrict_region parameters, LIMIT values) — Claude picks based on what the Tiger provider code reveals during implementation.
- Whether per-provider timeout settings use a flat config pattern (`census_timeout_ms`, `tiger_timeout_ms`, etc.) or a nested/dict-based pattern — Claude picks the approach most consistent with the existing `config.py` style.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEBT-01 | Tiger provider responds consistently under load (2000ms timeout resolved) | Per-provider timeout via flat Settings fields; `asyncio.wait_for()` already used in `_call_provider`; Tiger needs its own `tiger_timeout_ms=3000` field |
| DEBT-02 | Cascade path uses cached results for repeated calls (cache_hit=False hardcode removed) | Legacy cache-hit pattern in `_legacy_geocode()` at geocoding.py:232 mirrors exactly what cascade needs; cascade must load `geocoding_results` eagerly and re-run consensus |
| DEBT-03 | Spell dictionary auto-populates at application startup without manual CLI intervention | `rebuild_dictionary()` exists in spell/corrector.py:59; sync engine already created in lifespan; needs empty-check SQL before `load_spell_corrector()` call |
| DEBT-04 | CLI test failures fixed (test_import_cli.py, test_load_oa_cli.py fixture data resolved) | Fixture files already committed; only 1 test still fails (accuracy empty-string); fix is line 575 `cli/__init__.py` |
</phase_requirements>

## Standard Stack

No new dependencies are required. All fixes use existing project libraries.

### Core (already installed)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| pydantic-settings | current | `Settings` flat config fields for per-provider timeouts | Pattern: add `tiger_timeout_ms: int = 3000`, `census_timeout_ms: int = 2000`, etc. |
| asyncio | stdlib | `asyncio.wait_for()` for per-provider timeout enforcement | Already used in `cascade.py::_call_provider` |
| sqlalchemy (sync) | current | Sync engine for `rebuild_dictionary()` at startup | Sync engine already created in `main.py` lifespan |
| symspellpy | current | `SpellCorrector` loaded after dictionary rebuild | No change needed to `load_spell_corrector()` |
| pytest | 9.0.2 | Test suite; currently 517 collected, 1 failing | Quick run: `uv run pytest -q` |

### Installation
No new packages needed. All dependencies are already present.

## Architecture Patterns

### Established Patterns in This Codebase

#### Flat Settings Fields (config.py)
All existing timeout/flag configs are flat fields on `Settings(BaseSettings)`:
```python
# Existing pattern — follow this exactly for DEBT-01
exact_match_timeout_ms: int = 2000
fuzzy_match_timeout_ms: int = 500
consensus_timeout_ms: int = 200
llm_timeout_ms: int = 5000
```
New per-provider timeout fields must follow the same pattern: `tiger_timeout_ms: int = 3000`.
The existing `exact_match_timeout_ms` becomes the default used by all non-Tiger providers.
Claude's discretion: use flat fields, not a nested dict (consistent with codebase style).

#### Per-Provider Timeout in `_call_provider` (cascade.py)
The existing `_call_provider` inner function at Stage 2 already wraps each provider call in `asyncio.wait_for()`:
```python
# cascade.py:355-365 — existing implementation
async def _call_provider(provider_name, provider):
    try:
        result = await asyncio.wait_for(
            provider.geocode(normalized, http_client=http_client),
            timeout=settings.exact_match_timeout_ms / 1000,
        )
        return provider_name, result
    except asyncio.TimeoutError:
        logger.warning("CascadeOrchestrator: provider {} timed out after {}ms", ...)
        return provider_name, None
```
DEBT-01 changes the hardcoded `settings.exact_match_timeout_ms` to a per-provider lookup: Tiger gets `settings.tiger_timeout_ms`, all others fall back to `settings.exact_match_timeout_ms`.

#### Cache-Hit Early Exit (legacy pattern to mirror, geocoding.py:232-246)
The `_legacy_geocode()` method shows the exact pattern:
```python
# geocoding.py:232-246 — mirror this in CascadeOrchestrator.run()
if not force_refresh and address.geocoding_results:
    cached = address.geocoding_results
    official_result = await self._get_official(db, address.id)
    await db.commit()
    return {
        "address_hash": address_hash,
        "normalized_address": normalized,
        "results": cached,
        "local_results": local_results,
        "cache_hit": True,
        "official": official_result,
    }
```
For DEBT-02, the cascade must:
1. Load `address.geocoding_results` eagerly (use `selectinload`) in Stage 1's address lookup
2. Insert a cache-hit early exit block after finding the Address (before Stage 2 label)
3. On cache hit: still run local providers fresh (they are never cached), re-run `run_consensus()` on the ORM-loaded results, return `cache_hit=True`

**Critical detail:** The current `cascade.py` Stage 1 address lookup does NOT use `selectinload`:
```python
# cascade.py:293-298 — missing selectinload
addr_result = await db.execute(
    select(Address)
    .where(Address.address_hash == address_hash)
)
```
DEBT-02 fix must add `.options(selectinload(Address.geocoding_results))` to this query to make cache detection possible.

#### Spell Dictionary Rebuild on Empty (startup pattern, main.py:83-95)
The existing lifespan spell corrector block to extend for DEBT-03:
```python
# main.py:83-95 — current code
try:
    from sqlalchemy import create_engine as _create_sync_engine
    from civpulse_geo.config import settings as _settings
    _sync_engine = _create_sync_engine(_settings.database_url_sync)
    with _sync_engine.connect() as conn:
        app.state.spell_corrector = load_spell_corrector(conn)
    ...
except Exception as e:
    logger.warning(f"SpellCorrector not loaded (spell_dictionary may be empty): {e}")
    app.state.spell_corrector = None
```
DEBT-03 adds a check BEFORE `load_spell_corrector()`: count rows in `spell_dictionary`; if 0, check whether any staging table has data; if yes, call `rebuild_dictionary(conn)`. Uses the same sync connection already created in the block.

### Recommended Project Structure (No Changes)
```
src/civpulse_geo/
├── config.py              # DEBT-01: add tiger_timeout_ms, census_timeout_ms fields
├── main.py                # DEBT-03: spell dict auto-rebuild in lifespan
├── services/
│   └── cascade.py         # DEBT-01: per-provider timeout; DEBT-02: cache early exit
├── spell/
│   └── corrector.py       # DEBT-03: no changes (rebuild_dictionary() already correct)
└── cli/
    └── __init__.py        # DEBT-04: fix accuracy field line 575
```

### Anti-Patterns to Avoid
- **Nested timeout config dict:** Don't use `provider_timeouts: dict = {"tiger": 3000}` — the codebase uses flat fields on Settings, keep it consistent.
- **Rebuilding dictionary unconditionally at startup:** `rebuild_dictionary()` does a TRUNCATE first. Calling it when the table already has data wastes startup time and is explicitly excluded by D-08.
- **Blocking async lifespan with long sync ops:** `rebuild_dictionary()` can be slow on a full dataset. It must run in the synchronous block already established for spell loading (sync engine), not in the async lifespan directly.
- **Setting `cache_hit=True` without loading cached results:** The ORM relationship `address.geocoding_results` must be loaded eagerly (not lazily) — async sessions cannot lazy-load relationships.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-provider timeouts | A custom timeout decorator or wrapper class | `asyncio.wait_for()` already in `_call_provider` | Already handles timeout exception and fail-open |
| Empty table check | Raw SQL count outside SQLAlchemy | `conn.execute(text("SELECT COUNT(*) FROM spell_dictionary"))` | One-liner; no new abstraction needed |
| ORM eager loading | Manual re-query for `geocoding_results` | `selectinload(Address.geocoding_results)` in the Stage 1 query | Existing pattern in `_legacy_geocode()` |
| Spell dict rebuild trigger | Background task, cron, or separate service | Inline in lifespan sync block | Simplest; matches D-07 spec exactly |

**Key insight:** Every mechanism needed for all 4 fixes already exists in the codebase. The work is wiring, not invention.

## Common Pitfalls

### Pitfall 1: Forgetting `selectinload` on the cascade address query
**What goes wrong:** Cache hit check runs `if address.geocoding_results:` but the relationship returns `[]` because async SQLAlchemy never lazy-loads. Cache always misses.
**Why it happens:** `cascade.py` Stage 1 uses a bare `select(Address)` without `selectinload`. The legacy path uses `selectinload` but cascade doesn't mirror this.
**How to avoid:** Add `.options(selectinload(Address.geocoding_results))` to the Stage 1 address lookup in `cascade.py`.
**Warning signs:** Tests show `cache_hit` always `False` even after second call.

### Pitfall 2: `rebuild_dictionary()` calls `conn.commit()` — don't commit twice
**What goes wrong:** Calling `rebuild_dictionary(conn)` followed by other operations on the same connection that also commit may cause a double-commit error or lose data.
**Why it happens:** `corrector.py:137` has `conn.commit()` at the end of `rebuild_dictionary()`. The lifespan block also calls `conn.commit()` implicitly when the connection context closes (depending on SQLAlchemy version).
**How to avoid:** `rebuild_dictionary()` manages its own commit. After calling it, immediately call `load_spell_corrector(conn)` on the same connection — no extra commit needed.
**Warning signs:** `sqlalchemy.exc.InvalidRequestError: Can't reconnect until invalid transaction is rolled back`.

### Pitfall 3: Tiger timeout defaults — `exact_match_timeout_ms` still applies to ALL other providers
**What goes wrong:** Adding `tiger_timeout_ms=3000` but forgetting to keep `exact_match_timeout_ms=2000` as the default for all other providers. Or using `tiger_timeout_ms` for Tiger but accidentally using `tiger_timeout_ms` for Census too.
**Why it happens:** The `_call_provider` closure captures settings at call time; it's easy to change the wrong variable.
**How to avoid:** The per-provider lookup should be: `timeout = settings.tiger_timeout_ms if provider_name == "postgis_tiger" else settings.exact_match_timeout_ms`. Other named providers (Census, OA, NAD, Macon-Bibb) all get `exact_match_timeout_ms`.
**Warning signs:** Census provider suddenly gets 3 second timeout in tests.

### Pitfall 4: `_parse_oa_feature` accuracy fix breaks the "truly absent" case
**What goes wrong:** Changing line 575 so `""` becomes `None` but also making `None` become `None` — dropping the `"parcel"` default entirely. Features with no `accuracy` key should still default to `"parcel"`.
**Why it happens:** `props.get("accuracy") or "parcel"` collapses both `None` and `""` to `"parcel"`. The fix must distinguish them.
**How to avoid:** Use: `props.get("accuracy") or None` — this makes both `None` and `""` map to `None`. The test `test_parse_oa_feature_valid` confirms that a feature with `"accuracy": "rooftop"` returns `"rooftop"` unchanged. The test `test_parse_oa_feature_empty_strings_to_none` confirms that `""` returns `None`. There is no test requiring the `"parcel"` default — the CONTEXT.md D-11 says to only apply it when "truly missing (None/absent)", but the test file expects `None` for empty string with no fallback default. **Important:** Remove the `"parcel"` default entirely and use `props.get("accuracy") or None`.

### Pitfall 5: Cache-hit path in cascade must still call local providers
**What goes wrong:** Early exit on cache hit skips ALL provider calls including local providers (Tiger, OA, NAD, Macon-Bibb with `is_local=True`). Local providers are always called fresh per design (they're never cached).
**Why it happens:** Early exit short-circuits before Stage 2 where the local/remote split happens.
**How to avoid:** Mirror the legacy path exactly: call local providers FIRST (before the cache check), then check `address.geocoding_results`. This is the order in `_legacy_geocode()`.
**Warning signs:** Local provider results missing from cache-hit responses.

### Pitfall 6: `rebuild_dictionary()` is slow — log duration
**What goes wrong:** Startup hangs for 30-60 seconds with no log output when rebuilding from a large staging table. Operations team panics.
**Why it happens:** `rebuild_dictionary()` does `TRUNCATE` + `INSERT ... SELECT ... UNION ALL` across three large tables.
**How to avoid:** Log `logger.info("spell_dictionary empty — auto-rebuilding from staging tables...")` before calling, and `logger.info("spell_dictionary rebuilt: {} words in {}ms", count, elapsed)` after. Use `time.monotonic()`.
**Warning signs:** No warning, just startup silence for 60 seconds.

## Code Examples

Verified patterns from this codebase's source files.

### DEBT-01: Per-provider timeout lookup in `_call_provider`
```python
# config.py — add these fields alongside existing timeout fields
tiger_timeout_ms: int = 3000        # Tiger PostGIS geocode() runs slower than HTTP providers
census_timeout_ms: int = 2000       # explicit field for Census (same as exact_match_timeout_ms default)

# cascade.py — inside _call_provider, replace hardcoded timeout lookup
_PROVIDER_TIMEOUT_MAP = {
    "postgis_tiger": settings.tiger_timeout_ms,
}
timeout_ms = _PROVIDER_TIMEOUT_MAP.get(provider_name, settings.exact_match_timeout_ms)

result = await asyncio.wait_for(
    provider.geocode(normalized, http_client=http_client),
    timeout=timeout_ms / 1000,
)
```

### DEBT-01: Tiger query optimization (Claude's discretion on exact values)
```python
# tiger.py — add restrict_region and explicit LIMIT to GEOCODE_SQL
GEOCODE_SQL = text("""
    SELECT
        rating,
        ST_Y(geomout) AS lat,
        ST_X(geomout) AS lng,
        ...
    FROM geocode(:address, 1, ARRAY[
        (SELECT the_geom FROM tiger.state WHERE stusps = 'GA')
    ])
    ORDER BY rating ASC
    LIMIT 1
""")
```
Note: The `restrict_region` parameter is the second geometry array argument to `geocode()`. Passing the Georgia state boundary polygon narrows the search significantly. Claude should verify the exact `geocode()` signature against the installed Tiger extension during implementation.

### DEBT-02: Add `selectinload` to Stage 1 address query
```python
# cascade.py Stage 1 — replace bare select with eager load
from sqlalchemy.orm import selectinload

addr_result = await db.execute(
    select(Address)
    .options(selectinload(Address.geocoding_results))
    .where(Address.address_hash == address_hash)
)
address = addr_result.scalars().first()
```

### DEBT-02: Cache early exit block (insert after Stage 1, before Stage 2)
```python
# cascade.py — insert between Stage 1 and Stage 2 blocks
# ----------------------------------------------------------------
# Cache check: if remote results exist, skip provider calls (DEBT-02)
# Local providers always run fresh (they are never cached)
# ----------------------------------------------------------------
local_results_cache: list[GeocodingResultSchema] = []
if address is not None and address.geocoding_results:
    # Run local providers fresh even on cache hit
    for p_name, provider in providers.items():
        if provider.is_local:
            try:
                result = await asyncio.wait_for(
                    provider.geocode(normalized, http_client=http_client),
                    timeout=settings.exact_match_timeout_ms / 1000,
                )
                local_results_cache.append(result)
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("Cache-hit local provider {} failed: {}", p_name, exc)

    # Re-run consensus on cached ORM rows
    cached_candidates = [
        ProviderCandidate(
            provider_name=r.provider_name,
            lat=r.latitude or 0.0,
            lng=r.longitude or 0.0,
            confidence=r.confidence or 0.0,
            weight=get_provider_weight(r.provider_name),
        )
        for r in address.geocoding_results
        if r.latitude and r.longitude and r.confidence
    ]
    winning_cluster, _ = run_consensus(cached_candidates)

    official_result = await self._get_official(db, address.id)
    await db.commit()
    return CascadeResult(
        address_hash=address_hash,
        normalized_address=normalized,
        address=address,
        cache_hit=True,
        results=address.geocoding_results,
        local_results=local_results_cache,
        official=official_result,
    )
```

### DEBT-03: Spell dictionary auto-rebuild in `lifespan`
```python
# main.py — replace the spell corrector loading block
try:
    from sqlalchemy import create_engine as _create_sync_engine
    from civpulse_geo.config import settings as _settings
    from civpulse_geo.spell.corrector import rebuild_dictionary, load_spell_corrector
    import time as _time

    _sync_engine = _create_sync_engine(_settings.database_url_sync)
    with _sync_engine.connect() as conn:
        # Check if spell_dictionary is empty (DEBT-03, D-07, D-08)
        dict_count = conn.execute(
            text("SELECT COUNT(*) FROM spell_dictionary")
        ).scalar()
        if dict_count == 0:
            # Check if any staging table has data before rebuilding
            staging_count = conn.execute(text(
                "SELECT (SELECT COUNT(*) FROM openaddresses_points) "
                "+ (SELECT COUNT(*) FROM nad_points) "
                "+ (SELECT COUNT(*) FROM macon_bibb_points)"
            )).scalar()
            if staging_count and staging_count > 0:
                logger.info("spell_dictionary empty — auto-rebuilding from staging tables...")
                t0 = _time.monotonic()
                word_count = rebuild_dictionary(conn)
                elapsed_ms = round((_time.monotonic() - t0) * 1000)
                logger.info(
                    "spell_dictionary rebuilt: {} words in {}ms",
                    word_count, elapsed_ms,
                )
            else:
                logger.warning(
                    "spell_dictionary empty and staging tables empty — skipping auto-rebuild"
                )

        app.state.spell_corrector = load_spell_corrector(conn)
    loaded_count = len(app.state.spell_corrector._sym_spell.words)
    logger.info(f"SpellCorrector loaded with {loaded_count} dictionary words")
except Exception as e:
    logger.warning(f"SpellCorrector not loaded: {e}")
    app.state.spell_corrector = None
```

### DEBT-04: Fix accuracy field in `_parse_oa_feature`
```python
# cli/__init__.py:575 — change this line
# BEFORE (buggy):
"accuracy": props.get("accuracy") or "parcel",

# AFTER (correct):
"accuracy": props.get("accuracy") or None,
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cache_hit=False` hardcoded in `CascadeResult` return | Early-exit cache check before Stage 2 | Phase 17 (this phase) | Eliminates redundant provider calls on repeated address lookups |
| Single timeout `exact_match_timeout_ms` for all providers | Per-provider timeout (`tiger_timeout_ms=3000`) | Phase 17 (this phase) | Tiger gets 50% more time; other providers unchanged |
| Manual CLI `rebuild-spell-dict` required after data load | Auto-rebuild at startup when empty | Phase 17 (this phase) | Zero-touch deployment; K8s init container in Phase 20 adds belt-and-suspenders |

**Already resolved before this phase:**
- `test_import_cli.py` failures: Fixture files `data/SAMPLE_Address_Points.geojson` and `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml` already committed; all 10 previously-failing import tests now pass.

## Open Questions

1. **Tiger `geocode()` restrict_region signature**
   - What we know: PostGIS Tiger `geocode(address, max_results, restrict_region)` accepts a geometry array as third argument for spatial filtering
   - What's unclear: The exact Tiger extension version installed and whether `restrict_region` is a geometry array or a single geometry — varies between PostGIS Tiger versions
   - Recommendation: Claude should `SELECT * FROM tiger.geocode_settings` or check `\df geocode` in psql during implementation to verify the actual function signature before writing the SQL constant

2. **Cache-hit `selectinload` performance on large `geocoding_results`**
   - What we know: Some addresses may accumulate many `geocoding_results` rows (one per provider per call with upsert). At 5 providers, that's at most 5 rows.
   - What's unclear: Whether `selectinload` vs `joined_load` matters at this row count
   - Recommendation: `selectinload` is the correct choice — it avoids a JOIN on the address query and uses a separate `IN` query, consistent with the legacy path. No optimization needed for 5 rows.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | Test suite | Yes | 9.0.2 | — |
| uv | Python task runner | Yes | in PATH | — |
| ruff | Linting (required before commit per CLAUDE.md) | Yes | in PATH | — |
| PostGIS Tiger extension | DEBT-01 optimization verification | dev DB only | — | DEBT-01 can be coded/tested without Tiger data; Tiger tests are marked skip |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -q` |
| Full suite command | `uv run pytest --tb=short` |
| Asyncio mode | `auto` (set in pyproject.toml) |

### Current Test Suite State
| Status | Count |
|--------|-------|
| Collected | 517 |
| Passing | 516 |
| Failing | 1 (`test_parse_oa_feature_empty_strings_to_none`) |
| Skipped | 2 (Tiger-data-dependent tests) |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| DEBT-04 | `_parse_oa_feature` accuracy="" returns None | unit | `uv run pytest tests/test_load_oa_cli.py::TestLoadOaImport::test_parse_oa_feature_empty_strings_to_none -x` | 1 existing failing test; fix makes it pass |
| DEBT-01 | Tiger provider gets 3000ms timeout, others get 2000ms | unit | `uv run pytest tests/test_cascade.py -x` | New tests needed for per-provider timeout dispatch |
| DEBT-02 | Second geocode call returns `cache_hit=True` | unit | `uv run pytest tests/test_cascade.py -x` | New test needed: make two calls, assert second has `cache_hit=True` |
| DEBT-03 | Startup auto-rebuilds when dict empty + staging tables have data | unit | `uv run pytest tests/test_cascade.py -x` | New tests in lifespan or spell corrector tests |

### Sampling Rate
- **Per task commit:** `uv run pytest -q`
- **Per wave merge:** `uv run pytest --tb=short`
- **Phase gate:** All 517+ tests green before `/gsd:verify-work`

### Wave 0 Gaps (new tests needed)
- [ ] `tests/test_cascade.py` — add `TestCacheHitEarlyExit` class: test that second call on same address returns `cache_hit=True`
- [ ] `tests/test_cascade.py` — add `TestPerProviderTimeout` class: verify Tiger gets `tiger_timeout_ms`, Census gets `exact_match_timeout_ms`
- [ ] `tests/test_cascade.py` — add `TestCacheHitLocalProvidersStillCalled`: verify local providers are called even on cache hit
- [ ] `tests/test_spell_corrector.py` or `tests/test_main.py` — add tests for DEBT-03 startup logic (mock `spell_dictionary` count = 0 with staging tables having data)

*(Existing test infrastructure covers all other phase requirements — only the 4 new test classes above need to be added alongside the implementation changes.)*

## Project Constraints (from CLAUDE.md)

Applicable directives from the global `~/.claude/CLAUDE.md`:

| Directive | Impact on This Phase |
|-----------|---------------------|
| Always use `uv run` for Python commands | All pytest runs: `uv run pytest` |
| Always use `ruff` to lint before git commit | Lint each changed file before committing: `uv run ruff check src/civpulse_geo/config.py src/civpulse_geo/services/cascade.py src/civpulse_geo/main.py src/civpulse_geo/cli/__init__.py` |
| Never use system python | No bare `python` or `python3` commands |
| Git commits on branches unless directed to main | Confirm with user before committing to main |
| Commit after each task/story/phase | Commit after each DEBT fix, not all at once |
| Conventional commits | e.g. `fix(cascade): add per-provider timeout for Tiger (DEBT-01)` |
| Never push unless explicitly requested | Do not push after commit |

No project-specific `CLAUDE.md` exists in `/home/kwhatcher/projects/civicpulse/geo-api/` — only the global user CLAUDE.md applies.

## Sources

### Primary (HIGH confidence)
- Direct source inspection: `src/civpulse_geo/cascade.py`, `src/civpulse_geo/services/geocoding.py`, `src/civpulse_geo/config.py`, `src/civpulse_geo/main.py`, `src/civpulse_geo/spell/corrector.py`, `src/civpulse_geo/providers/tiger.py`, `src/civpulse_geo/cli/__init__.py` — all read in full
- `tests/test_load_oa_cli.py`, `tests/test_import_cli.py`, `tests/test_cascade.py` — all read in full
- Live test run: `uv run pytest --tb=short -q` → confirmed 517 tests, 1 failure, exact line identified

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions D-01 through D-11 — all locked decisions directly inform implementation
- SQLAlchemy async `selectinload` pattern: verified against existing usage in `_legacy_geocode()` at `geocoding.py:169-172`
- asyncio.wait_for pattern: verified against existing usage in `cascade.py:355`

### Tertiary (LOW confidence)
- Tiger `geocode()` restrict_region third argument: training knowledge suggests geometry array; exact signature must be confirmed against installed version during implementation

## Metadata

**Confidence breakdown:**
- DEBT-04 fix: HIGH — root cause confirmed by failing test; one-line fix
- DEBT-02 fix: HIGH — exact pattern to mirror is in the same codebase (`_legacy_geocode`); `selectinload` missing is confirmed by code inspection
- DEBT-01 fix: HIGH — `asyncio.wait_for` already present; only the per-provider dispatch needs addition; Tiger SQL optimization is MEDIUM (restrict_region signature must be verified at implementation time)
- DEBT-03 fix: HIGH — `rebuild_dictionary()` and sync engine are both present; SQL for empty check is trivial

**Research date:** 2026-03-29
**Valid until:** 2026-04-30 (codebase changes would invalidate findings; no external dependencies)
