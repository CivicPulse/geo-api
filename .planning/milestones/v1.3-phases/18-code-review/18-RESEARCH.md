# Phase 18: Code Review - Research

**Researched:** 2026-03-29
**Domain:** Python codebase audit — security, stability, and performance
**Confidence:** HIGH (all findings derived from direct code inspection of the target codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Severity Classification**
- D-01: Any security finding is a blocker — unvalidated inputs, injection vectors, exposed secrets, regardless of whether exploitation requires internal network access. Conservative stance because other CivPulse services trust geo-api's data.
- D-02: Stability blockers are unhandled exceptions that can bubble to the client as 500 errors. Graceful degradation gaps (e.g., provider down but no fallback message) are non-blockers.
- D-03: Performance blockers are N+1 query patterns, connection pool sizing errors, and logic errors that produce wrong results. Suboptimal-but-correct code is a non-blocker.

**Review Scope**
- D-04: Each of the three teams (security, stability, performance) reviews the full codebase through their lens — all 45 source files. No risk-prioritized shortcuts.
- D-05: Test files (29 files, 504 tests — now 527 after Phase 17) are reviewed for correctness only — verify tests actually test what they claim (no false passes, correct assertions). No style/perf audit of test code.

**Fix Verification**
- D-06: Blocker fixes verified by running the full test suite + ruff lint + targeted new tests for each fix. If existing tests don't cover the fixed code path, write a new test.
- D-07: Fixes committed in batches by team — one commit per team's blocker resolutions (e.g., `fix(security): resolve all security blockers`). Maximum 3 fix commits.

**Non-Blocker Tracking**
- D-08: All non-blockers documented in a detailed `18-FINDINGS.md` report in the phase directory, categorized by team (security/stability/performance).
- D-09: Each non-blocker also added as a GSD todo that references the findings document for full details.
- D-10: Non-blockers prioritized as P1 (fix before prod — next available phase), P2 (fix when convenient), or P3 (nice-to-have / code quality). Todos inherit the priority.

**Claude's Discretion**
- How to partition files across agent teams internally (all teams get all files, but execution order/batching is Claude's call)
- Findings report structure beyond the team/priority framework decided above
- Whether to group related findings or report individually

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REVIEW-01 | Codebase passes security audit (no unvalidated inputs, injection vectors, or exposed secrets) | Security findings pre-identified in §Security Audit Findings below |
| REVIEW-02 | Codebase passes stability audit (no uncaught exceptions, all error paths handled gracefully) | Stability findings pre-identified in §Stability Audit Findings below |
| REVIEW-03 | Codebase passes performance audit (no N+1 queries, pool sizing correct, no logic errors) | Performance findings pre-identified in §Performance Audit Findings below |

</phase_requirements>

---

## Summary

Phase 18 is a structured three-team code audit of the 45-source-file civpulse_geo Python codebase (~8,300 LOC). This research document performs an advance scout pass through the highest-risk code paths to give the planner concrete, pre-identified findings that each team must verify, confirm, and remediate.

The codebase is well-structured. The main security surface is the hardcoded development credentials in `config.py` defaults. The main stability surface is the single-geocode endpoint, which catches `ValueError` (404) but has no catch for unexpected exceptions from `GeocodingService.geocode()` when `cascade_enabled=True` — any unhandled exception from the cascade pipeline propagates to FastAPI as a 500. The main performance surface is that `database.py` does not configure `pool_size`, `max_overflow`, or `pool_pre_ping`, which leaves asyncpg running with SQLAlchemy's default pool (5+10 = 15 connections), unsized for deployment.

There are also 5 known ruff lint issues (unused imports, unused variable) that must be resolved as part of fix verification (D-06).

**Primary recommendation:** Plan three focused team sub-tasks (security read + fix, stability read + fix, performance read + fix) that each read the relevant files, produce their section of `18-FINDINGS.md`, resolve blockers, write targeted tests, run `uv run ruff check src/` and `uv run pytest`, then commit.

---

## Project Constraints (from CLAUDE.md)

Global CLAUDE.md directives that apply to all fixes in this phase:

| Directive | Impact on This Phase |
|-----------|----------------------|
| Always use `uv run` for Python commands | All pytest/ruff invocations must be `uv run pytest` / `uv run ruff check src/` |
| Always use `ruff` to lint; lint before committing | D-06 fix verification pipeline must include `uv run ruff check src/` |
| Never use system Python | No bare `python` or `python3` in shell steps |
| After UI changes, verify with Playwright | Not applicable — no UI in this phase |
| Git commits on branches unless requested to commit to main | Phase fixes committed to main per D-07 (the plan decides branching) |
| Conventional Commits for commit messages | D-07 examples (`fix(security): ...`) already follow this |
| Never push to GitHub unless asked | Do not push after committing fixes |

---

## Codebase Structure (Review Targets)

```
src/civpulse_geo/
├── api/                     # 3 files — geocoding.py, validation.py, health.py
├── cli/                     # 2 files — __init__.py (1,100+ LOC), parsers.py
├── config.py                # Settings(BaseSettings) — secrets, env vars
├── database.py              # SQLAlchemy async engine — pool config
├── main.py                  # FastAPI lifespan — startup, provider registration
├── models/                  # SQLAlchemy ORM models
├── normalization.py         # canonical_key(), parse_address_components()
├── providers/               # 7 files — base, census, openaddresses, tiger, nad, macon_bibb, scourgify
├── schemas/                 # 3 files — geocoding, validation, batch Pydantic schemas
├── services/                # 5 files — cascade.py, geocoding.py, validation.py, fuzzy.py, llm_corrector.py
└── spell/                   # SpellCorrector, rebuild_dictionary
tests/                       # 29 files, 527 tests (525 pass, 2 skipped, 2 warnings)
```

**Recently modified files (Phase 17 — fresh-eyes priority):** `cascade.py`, `config.py`, `main.py`, `corrector.py`, `tiger.py`, `cli/__init__.py`

---

## Security Audit Findings

Pre-identified via direct code inspection. Security team must verify each item then classify as blocker or non-blocker using D-01.

### SEC-01: Hardcoded credentials in config defaults (BLOCKER candidate)

**File:** `src/civpulse_geo/config.py` lines 7-8
**Finding:** `Settings(BaseSettings)` has plain-text default credentials:
```python
database_url: str = "postgresql+asyncpg://civpulse:civpulse@localhost:5432/civpulse_geo"
database_url_sync: str = "postgresql+psycopg2://civpulse:civpulse@localhost:5432/civpulse_geo"
```
The username `civpulse` and password `civpulse` are embedded in source code. While `pydantic_settings` loads from the `.env` file and env vars at runtime, these defaults mean:
1. Any environment where `DATABASE_URL` is not set will connect with the hardcoded password.
2. The credentials are visible in git history.

**Classification trigger:** D-01 (exposed secrets in source = blocker regardless of exploitability).
**Remediation:** Replace the default strings with `None` (or a clearly fake placeholder like `"postgresql+asyncpg://CHANGEME@localhost:5432/civpulse_geo"`) and make the field required with no default, or add a validator that raises on the default value in non-development environments.

### SEC-02: No input length validation on address fields (BLOCKER candidate)

**File:** `src/civpulse_geo/schemas/geocoding.py` line 14, `schemas/validation.py`
**Finding:** `GeocodeRequest` and `ValidateRequest` Pydantic models define `address: str` with no `max_length` constraint. An arbitrarily large address string passes through to:
- `canonical_key()` — calls `scourgify.normalize_address_record()`, usaddress
- All provider geocode calls (Census HTTP, PostGIS SQL parameters)
- The database address storage

No upper bound prevents abuse (e.g., a 10 MB address string triggering OOM in scourgify's regex pipeline, or filling a DB column).

**Classification trigger:** D-01 (unvalidated external input = blocker).
**Remediation:** Add `max_length=500` (or a researched reasonable US address upper bound) to `address: str` on all request schemas.

### SEC-03: `SetOfficialRequest` has no latitude/longitude range validation

**File:** `src/civpulse_geo/schemas/geocoding.py` lines 49-55
**Finding:** `SetOfficialRequest.latitude` and `.longitude` are `float | None` with no range validators. A caller can submit `latitude=9999.0, longitude=-9999.0`, which gets stored verbatim as an EWKT geometry in `geocoding_results`. This produces a corrupt `official` geocode record (out-of-range WGS84 coordinate).

**Classification trigger:** D-01 (unvalidated external input producing logic-corrupting data = blocker).
**Remediation:** Add Pydantic `Field(ge=-90, le=90)` for latitude and `Field(ge=-180, le=180)` for longitude.

### SEC-04: `provider_name` path parameter passed directly to ValueError message

**File:** `src/civpulse_geo/api/geocoding.py` line 225-232
**Finding:** The `provider_name` path parameter from `GET /geocode/{address_hash}/providers/{provider_name}` is passed through `service.get_by_provider()` and any `ValueError` message (which includes the user-supplied `provider_name`) is returned as the HTTP `detail` string. Example: `"No result from provider 'user-injected-text' for this address"`. This is an information-reflection issue.

**Classification trigger:** D-01 (unvalidated input reflected in response — low-severity but conservative stance requires blocker treatment).
**Remediation:** Validate `provider_name` against the set of known provider names before calling the service, or sanitize the error message to not echo user input.

### SEC-05: Raw SQL string in CLI uses unparameterized literals for batch size (non-blocker candidate)

**File:** `src/civpulse_geo/cli/__init__.py` — NAD_COPY_SQL, NAD_UPSERT_SQL
**Finding:** The raw SQL constants for NAD bulk COPY/upsert use string constants (no user input). The NAD batch size (`NAD_BATCH_SIZE = 50_000`) is a module constant. No injection vector exists here. However, the team should verify that no CLI command accepts user-supplied SQL-interpolated values.

**Classification trigger:** D-01 applies if user input is found in any SQL string. If the SQL constants are confirmed as compile-time only, this is a NON-BLOCKER.

---

## Stability Audit Findings

Pre-identified via direct code inspection. Stability team must verify each item then classify as blocker or non-blocker using D-02.

### STAB-01: Single geocode endpoint has no exception catch for cascade failures (BLOCKER candidate)

**File:** `src/civpulse_geo/api/geocoding.py` lines 39-132 (the `geocode` endpoint)
**Finding:** The `geocode()` endpoint catches only `ValueError` for the `set_official`, `refresh`, and `get_provider_result` endpoints. The main `POST /geocode` endpoint does **not** have a try/except:

```python
@router.post("", response_model=GeocodeResponse)
async def geocode(...):
    service = GeocodingService()
    result = await service.geocode(...)  # no try/except here
    # ... build response
```

If `CascadeOrchestrator.run()` raises any non-`ValueError` exception (e.g., a `SQLAlchemyError` on a rare DB condition, or an `AttributeError` from `result.get("outlier_providers", set())`), it propagates to FastAPI as an unhandled 500. The cascade code handles provider exceptions internally (lines ~456-467 in cascade.py), but DB-level errors in the normalize/cache-check stage are not caught at the API layer.

**Classification trigger:** D-02 (unhandled exception that can bubble to client as 500 = blocker).
**Remediation:** Wrap the `geocode()` endpoint body in `try/except Exception as e: raise HTTPException(status_code=500, detail="Internal geocoding error")`. Or add a FastAPI exception handler for `Exception` at the app level.

### STAB-02: Validation endpoint catches only ProviderError, not general exceptions

**File:** `src/civpulse_geo/api/validation.py` lines 33-96
**Finding:** The single `POST /validate` endpoint catches `ProviderError` and raises HTTPException 422. But `ValidationService.validate()` can potentially raise `SQLAlchemyError` or other unhandled exceptions on DB problems. Unlike batch endpoints (which have broad `except Exception`), the single-item path has a narrow catch.

**Classification trigger:** D-02 (potential unhandled exception path reaching client).
**Remediation:** Broaden the try/except or add app-level exception handler.

### STAB-03: `main.py` lifespan swallows SpellCorrector exceptions but sets `app.state.spell_corrector = None`

**File:** `src/civpulse_geo/main.py` lines 86-129
**Finding:** The lifespan wraps spell corrector initialization in `try/except Exception as e: logger.warning(...)` and falls back to `app.state.spell_corrector = None`. This is **correct** graceful degradation per D-02. However, the cascade pipeline and legacy geocoding service access `spell_corrector` via `getattr(request.app.state, "spell_corrector", None)` — if `spell_corrector` is `None`, spell correction silently skips. This is acceptable graceful degradation (non-blocker), not a 500 risk.

**Classification trigger:** NON-BLOCKER (system degrades gracefully without crashing).

### STAB-04: `_legacy_geocode()` loop over providers has no per-provider exception handling

**File:** `src/civpulse_geo/services/geocoding.py` lines 213-230 (local provider loop) and lines 249-310 (remote provider loop)
**Finding:** The legacy path iterates providers in a `for` loop without try/except. If any single provider raises an exception not caught inside the provider itself (e.g., an unexpected error in `_parse_input_address`), the entire geocoding request fails with an unhandled exception.

```python
for provider_name, provider in local_providers.items():
    provider_result = await provider.geocode(normalized, http_client=http_client)  # unguarded
```

The cascade path wraps each provider call in `_call_provider()` with full try/except. The legacy path does not.

**Classification trigger:** D-02 (unhandled exception on legacy path = blocker if `cascade_enabled=False`; non-blocker if `cascade_enabled=True` is the expected deployment config). Security/stability team should determine deployment default.

**Note:** `config.py` default has `cascade_enabled: bool = True`. If production always runs with cascade, this may be a non-blocker (P2). But the code path still exists and can be reached.

### STAB-05: `cascade.py` — N+1 ORM re-query pattern after upsert

**File:** `src/civpulse_geo/services/cascade.py` lines 546-551 and `geocoding.py` lines 304-311
**Finding:** After each remote provider upsert (inside the provider result loop), the code immediately re-queries the same row by ID to get the full ORM object:
```python
upsert_result = await db.execute(stmt)
result_id = upsert_result.scalar_one()
orm_row_result = await db.execute(
    select(GeocodingResultORM).where(GeocodingResultORM.id == result_id)
)
```
This pattern occurs once per remote provider (up to 2 remote providers currently: Census + future). Not a classic N+1 (not triggered per relationship), but it is an extra round-trip per provider. Classified under stability because it adds latency — but it is NOT a logic error (results are correct). This is a performance non-blocker. Listed here as a stability item because the pattern means correctness depends on the re-query matching the upserted row, which it does.

**Classification trigger:** NON-BLOCKER (pattern is correct and latency impact is bounded by provider count, not by data size).

### STAB-06: Test correctness — verify `test_spell_startup.py` assertions match Phase 17 behavior

**File:** `tests/test_spell_startup.py`
**Finding:** Phase 17 changed the spell dictionary startup logic (DEBT-03, D-07/D-08): now auto-rebuilds only when `spell_dictionary` is empty AND staging tables have data. Tests must correctly assert:
1. When `spell_dictionary` is empty and staging tables have data → rebuild triggers
2. When `spell_dictionary` is empty and staging tables are empty → skip with warning
3. When `spell_dictionary` already has data → no rebuild (regardless of staging tables)

The test must NOT use mocks that make `dict_count > 0` pass trivially while the actual check is wrong.

**Classification trigger:** Per D-05, correctness review only. If tests assert the wrong condition (e.g., always mock `dict_count=0` without testing the `staging_count=0` branch), that is a correctness gap.

---

## Performance Audit Findings

Pre-identified via direct code inspection. Performance team must verify each item then classify as blocker or non-blocker using D-03.

### PERF-01: Connection pool uses SQLAlchemy defaults — no explicit sizing (BLOCKER candidate)

**File:** `src/civpulse_geo/database.py` lines 11-17
**Finding:** `create_async_engine` is called with only `echo=False` — no `pool_size`, `max_overflow`, `pool_pre_ping`, or `pool_recycle`:

```python
engine = create_async_engine(settings.database_url, echo=False)
```

SQLAlchemy async engine defaults: `pool_size=5`, `max_overflow=10` → maximum 15 connections. Under K8s with multiple workers (Phase 20 will determine worker count), this may exhaust PostgreSQL's `max_connections` (default 100 on a shared instance). Phase 19 notes that no transaction-mode PgBouncer is assumed — confirmed in STATE.md.

Additionally, without `pool_pre_ping=True`, stale connections from a DB restart are not detected until a query fails, producing transient 500 errors.

**Classification trigger:** D-03 (pool sizing error that may match deployment resource limits = blocker).
**Remediation:** Add configurable `pool_size`, `max_overflow`, and `pool_pre_ping=True` settings to `Settings` and pass them to `create_async_engine`. Document appropriate values for K8s single-replica deployment.

### PERF-02: No N+1 query patterns found in provider code (confirmed safe)

**Finding:** All provider queries are parameterized single-row lookups or SELECT ... LIMIT 1. No relationship traversal that causes N+1. The `selectinload(Address.geocoding_results)` in both `geocoding.py:171` and `cascade.py:296` is correct usage (prevents lazy-load N+1).

**Classification trigger:** CONFIRMED CLEAN — no N+1.

### PERF-03: Re-query after upsert adds one round-trip per remote provider

**File:** `cascade.py` ~546, `geocoding.py` ~304
**Finding:** After each provider upsert (`.returning(GeocodingResultORM.id)`), the code immediately re-queries to load the full ORM row. With 1 remote provider (Census), this is 1 extra SELECT per geocode miss. With future remote providers it scales linearly.

This can be eliminated by using `.returning(*)` to return all columns, or by constructing the ORM object from the INSERT's RETURNING data.

**Classification trigger:** D-03 — suboptimal-but-correct code is a NON-BLOCKER per D-03 definition. The code produces correct results and the overhead is bounded. Mark P2 in FINDINGS.md.

### PERF-04: OA fuzzy match uses `ORDER BY ABS(CAST ... - target_num)` with regex filter

**File:** `src/civpulse_geo/providers/openaddresses.py` lines 174-198
**Finding:** `_find_oa_fuzzy_match` queries with `OpenAddressesPoint.street_number.op("~")(r"^\d+$")` and `ORDER BY ABS(CAST(street_number, Integer) - target_num)`. This requires a sequential scan on all matching `street_name` + `postcode` rows that have numeric street numbers. If the `(street_name, postcode)` index exists (GIN trigram from Phase 12), the regex filter and cast-based order may negate index benefit.

**Classification trigger:** D-03 — this is suboptimal performance with correct results. NON-BLOCKER per D-03. Mark P2. (Performance team should verify that `(street_name, postcode)` index exists and check EXPLAIN output on test data.)

### PERF-05: cascade.py `_legacy_geocode` path re-queries OfficialGeocoding separately

**File:** `src/civpulse_geo/services/geocoding.py` `_get_official()` — called after commit
**Finding:** After committing, `_legacy_geocode()` calls `_get_official()` which performs two SELECT queries: one to find `OfficialGeocoding`, one to load `GeocodingResult` by ID. Could be a single JOIN query. Correct but slightly less efficient.

**Classification trigger:** D-03 NON-BLOCKER (correct, bounded overhead). Mark P3.

### PERF-06: Logic error review — `cascade.py` weight map uses tiger key mismatch

**File:** `src/civpulse_geo/services/cascade.py` lines 63-71
**Finding:** The `get_provider_weight()` function maps `"tiger"` to `settings.weight_tiger_unrestricted`. However, the actual provider name used in `providers` dict is `"postgis_tiger"` (set in `main.py` line 54). This means `get_provider_weight("postgis_tiger")` falls through to the default `0.50` instead of using `weight_tiger_restricted = 0.75`.

```python
weight_map = {
    "census": settings.weight_census,
    "openaddresses": settings.weight_openaddresses,
    "macon_bibb": settings.weight_macon_bibb,
    "tiger": settings.weight_tiger_unrestricted,  # KEY MISMATCH: provider name is "postgis_tiger"
    "nad": settings.weight_nad,
}
```

This is a **logic error that produces wrong results** — Tiger geocoding results receive weight 0.50 instead of 0.40 (unrestricted) or 0.75 (restricted). This affects consensus scoring and auto-set official.

**Classification trigger:** D-03 (logic error producing wrong results = BLOCKER).
**Remediation:** Change `"tiger"` key to `"postgis_tiger"` in the weight map. Also verify whether `weight_tiger_unrestricted` or `weight_tiger_restricted` should be the default (Tiger SQL geocode does not have a "restriction" concept the way HTTP providers do — should be a single weight).

---

## Ruff Lint Issues (Pre-existing, must be resolved per D-06)

Ruff found 5 errors in the source that must be cleaned up as part of fix verification:

| File | Line | Rule | Finding |
|------|------|------|---------|
| `normalization.py` | 15 | F401 | `unicodedata` imported but unused |
| `providers/macon_bibb.py` | 22 | F401 | `usaddress` imported but unused |
| `providers/nad.py` | 23 | F401 | `usaddress` imported but unused |
| `services/fuzzy.py` | 255 | F841 | `candidate_rows` assigned but never used |
| `services/geocoding.py` | 40 | F401 | `CascadeResult` imported but unused |

These are all auto-fixable with `uv run ruff check src/ --fix` (4 of 5) plus manual removal of `candidate_rows`. Include in whichever team's commit is most natural (performance team owns `fuzzy.py`; security/stability owns the others).

---

## Architecture Patterns (for reviewers)

### Provider Pattern
All providers implement `base.GeocodingProvider` or `base.ValidationProvider` ABC. Local providers (`is_local=True`) bypass the DB cache and return results directly. Remote providers write to `geocoding_results` via upsert.

### Cascade Pipeline (6 stages)
```
normalize → spell-correct → exact match (all providers parallel) → fuzzy → LLM → consensus → auto-set official
```
Each stage wraps provider calls in `asyncio.wait_for()` with per-provider timeout. Timeout degrades gracefully (empty result, cascade continues). Exception handling is strong in the cascade path but weaker in the legacy path and at the API layer.

### Settings Pattern
`Settings(BaseSettings)` with `SettingsConfigDict(env_file=".env")`. Env vars override defaults at runtime. The security concern is that defaults are visible in source and have real credentials.

### Error Handling Pattern (current state)
- API batch endpoints: `except Exception` per item → `classify_exception()` → per-item error response
- API single geocode: **no try/except** — unhandled exceptions propagate
- API single validate: `except ProviderError` only — other exceptions propagate
- Cascade providers: `_call_provider()` inner function has broad `except Exception` — excellent
- Legacy providers: bare loop, no per-provider exception handling

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Input length limits | Custom length-check middleware | Pydantic `Field(max_length=...)` | Already used across schemas; consistent pattern |
| Lat/lng range validation | Custom validator function | Pydantic `Field(ge=..., le=...)` | Built into pydantic v2 |
| HTTP error handler | Custom exception middleware | FastAPI `@app.exception_handler(Exception)` | Built-in handler pattern |
| Pool pre-ping | Custom health-check query | `create_async_engine(..., pool_pre_ping=True)` | SQLAlchemy built-in |

---

## Common Pitfalls

### Pitfall 1: Confusing provider name keys with weight map keys
**What goes wrong:** Tiger provider registered as `"postgis_tiger"` but weight map uses `"tiger"`. Weight lookup silently returns default 0.50.
**Why it happens:** Provider name chosen for DB clarity; weight map used a shorter alias.
**How to avoid:** Weight map keys must exactly match provider registration keys in `main.py`.
**Warning signs:** Consensus scoring gives Tiger results unexpected influence (PERF-06 above — already identified as a blocker).

### Pitfall 2: Pydantic defaults look validated but aren't
**What goes wrong:** `address: str` in schemas accepts any length string. Pydantic validates type (is it a string?) but not content constraints unless you add them.
**How to avoid:** Always add `Field(max_length=...)` to free-text input fields.

### Pitfall 3: `except ValueError` in API routes is not a complete safety net
**What goes wrong:** Service layer raises `SQLAlchemyError`, `AttributeError`, etc. that are not `ValueError`. These bypass the 404 handler and surface as 500.
**How to avoid:** Add a generic `except Exception` catch at the API endpoint level, or use a FastAPI global exception handler.

### Pitfall 4: Pool defaults are per-process, not per-pod
**What goes wrong:** With default `pool_size=5, max_overflow=10` and e.g. 4 Uvicorn workers per pod, total connections = 4 × 15 = 60 — already 60% of a shared PostgreSQL default of 100 connections.
**How to avoid:** Size pool explicitly: `pool_size=2, max_overflow=3` per worker for a shared DB, or use `pool_size=1` if a connection pooler (PgBouncer) is added later.

---

## Code Examples

### Correct: exception handler pattern for FastAPI endpoints
```python
# Source: FastAPI official docs — add_exception_handler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: {}", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
```

### Correct: connection pool configuration for asyncpg
```python
# Source: SQLAlchemy async docs
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=settings.db_pool_size,        # add to Settings
    max_overflow=settings.db_max_overflow,  # add to Settings
    pool_pre_ping=True,                     # detect stale connections
    pool_recycle=3600,                      # recycle connections after 1 hour
)
```

### Correct: Pydantic field constraints for API inputs
```python
# Source: Pydantic v2 docs
from pydantic import BaseModel, Field

class GeocodeRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=500)

class SetOfficialRequest(BaseModel):
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
```

---

## Test Infrastructure

Current state:
- **Framework:** pytest with asyncio_mode="auto"
- **Config file:** `pyproject.toml` under `[tool.pytest.ini_options]`
- **Test count:** 527 collected (525 passed, 2 skipped, 2 warnings) on 2026-03-29
- **Quick run:** `uv run pytest tests/ -q`
- **Full suite:** `uv run pytest tests/ -v`

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode="auto") |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Command | Notes |
|--------|----------|-----------|---------|-------|
| REVIEW-01 | No unvalidated inputs / injection vectors / secrets | manual code review + unit | `uv run pytest tests/test_geocoding_api.py tests/test_validation_api.py -v` | Add tests for max_length, lat/lng bounds validation |
| REVIEW-02 | No uncaught exceptions on error paths | unit + manual code review | `uv run pytest tests/test_geocoding_api.py tests/test_geocoding_service.py -v` | Add tests for exception propagation paths |
| REVIEW-03 | No N+1 queries; pool sizing correct; no logic errors | unit + manual review | `uv run pytest tests/test_cascade.py tests/test_providers.py -v` | Add test for `get_provider_weight("postgis_tiger")` returning correct value |

### Sampling Rate
- **Per fix commit:** `uv run ruff check src/ && uv run pytest tests/ -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green + ruff clean before `/gsd:verify-work`

### Wave 0 Gaps (tests needed for blocker fixes)
- [ ] `tests/test_geocoding_api.py` — add test: POST /geocode with oversized address returns 422
- [ ] `tests/test_geocoding_api.py` — add test: POST /geocode with DB error propagates a handled 500 (not raw SQLAlchemy exception)
- [ ] `tests/test_geocoding_api.py` — add test: PUT /geocode/{hash}/official with out-of-range lat/lng returns 422
- [ ] `tests/test_cascade.py` — add test: `get_provider_weight("postgis_tiger")` returns correct weight (not 0.50 default)
- [ ] `tests/test_validation_api.py` — add test: POST /validate with oversized address returns 422

---

## Environment Availability

Step 2.6: Code-review phase is a code-only analysis with no new external tool dependencies. Existing tools confirmed available:

| Dependency | Required By | Available | Version |
|------------|------------|-----------|---------|
| uv | All Python commands | Yes | (installed) |
| ruff | Lint verification (D-06) | Yes | (installed, 5 issues found) |
| pytest | Fix verification (D-06) | Yes | 527 tests collected |
| Python (via uv) | All execution | Yes | managed by uv |

**Missing dependencies with no fallback:** None.

---

## Runtime State Inventory

Step 2.5: Phase 18 is a code review and fix phase, not a rename/refactor/migration phase.

**Not applicable — no runtime state affected by this phase.**

---

## Open Questions

1. **Tiger weight: unrestricted vs. restricted**
   - What we know: `config.py` has two tiger weights: `weight_tiger_unrestricted=0.40` and `weight_tiger_restricted=0.75`. The weight map key `"tiger"` maps only to the unrestricted weight.
   - What's unclear: Does the PostGIS Tiger geocoder ever produce a "restricted" result? The current code has no logic that selects between the two weights — the map has only one entry regardless.
   - Recommendation: Performance team should determine correct weight for `"postgis_tiger"` and whether `weight_tiger_restricted` is used anywhere or is dead configuration.

2. **`pool_pre_ping` interaction with asyncpg**
   - What we know: asyncpg and SQLAlchemy async engine support `pool_pre_ping`. The `pool_pre_ping` sends a `SELECT 1` before returning a connection from the pool.
   - What's unclear: Whether `pool_pre_ping` has measurable latency overhead on the geo-api's high-throughput geocode path.
   - Recommendation: Enable it (correctness > micro-optimization) and document the decision.

3. **`cascade_enabled=False` legacy path deployment status**
   - What we know: Default is `cascade_enabled: bool = True`. Legacy path exists in `_legacy_geocode()`.
   - What's unclear: Is the legacy path expected to remain in production (as a feature flag), or is it dead code to be removed eventually?
   - Recommendation: If production never uses `cascade_enabled=False`, STAB-04 (unguarded legacy provider loop) is a P2 non-blocker. If it remains a valid deployment option, it's a blocker.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all listed source files under `src/civpulse_geo/` — all findings are sourced from the actual codebase
- `src/civpulse_geo/config.py` — settings, defaults, secrets
- `src/civpulse_geo/database.py` — connection pool configuration
- `src/civpulse_geo/api/geocoding.py` — exception handling patterns
- `src/civpulse_geo/services/cascade.py` — pipeline exception handling
- `src/civpulse_geo/services/geocoding.py` — legacy path analysis
- `uv run ruff check src/` output — 5 lint issues confirmed
- `uv run pytest tests/ -q` output — 525 passed, 2 skipped, 527 total

### Secondary (MEDIUM confidence)
- SQLAlchemy async engine docs — pool_size/max_overflow defaults and pool_pre_ping semantics (training data, consistent with code behavior observed)
- Pydantic v2 Field validators — max_length, ge/le constraints (training data, consistent with existing usage in codebase)

---

## Metadata

**Confidence breakdown:**
- Security findings: HIGH — derived from direct code inspection; SEC-01 through SEC-04 are concrete code paths
- Stability findings: HIGH — derived from direct code inspection; STAB-01 confirmed by reading full api/geocoding.py
- Performance findings: HIGH for PERF-01 (pool config confirmed absent), HIGH for PERF-06 (weight map key mismatch confirmed), MEDIUM for PERF-03/04/05 (suboptimal patterns identified, impact not benchmarked)
- Ruff issues: HIGH — verified by running `uv run ruff check src/` directly

**Research date:** 2026-03-29
**Valid until:** This research is derived from the current codebase snapshot. Valid until any source file in `src/civpulse_geo/` is modified. Re-verify after Phase 17 fix commits if any.
