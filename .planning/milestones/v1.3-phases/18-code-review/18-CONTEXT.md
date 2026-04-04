# Phase 18: Code Review - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Thorough three-team audit (security, stability, performance) of the entire geo-api Python codebase (~8,300 LOC, 45 source files, 29 test files). All blocking findings resolved in-phase with targeted tests. Non-blockers documented and tracked as todos for subsequent phases.

</domain>

<decisions>
## Implementation Decisions

### Severity Classification
- **D-01:** Any security finding is a blocker — unvalidated inputs, injection vectors, exposed secrets, regardless of whether exploitation requires internal network access. Conservative stance because other CivPulse services trust geo-api's data.
- **D-02:** Stability blockers are unhandled exceptions that can bubble to the client as 500 errors. Graceful degradation gaps (e.g., provider down but no fallback message) are non-blockers.
- **D-03:** Performance blockers are N+1 query patterns, connection pool sizing errors, and logic errors that produce wrong results. Suboptimal-but-correct code is a non-blocker.

### Review Scope
- **D-04:** Each of the three teams (security, stability, performance) reviews the full codebase through their lens — all 45 source files. No risk-prioritized shortcuts.
- **D-05:** Test files (29 files, 504 tests) are reviewed for correctness only — verify tests actually test what they claim (no false passes, correct assertions). No style/perf audit of test code.

### Fix Verification
- **D-06:** Blocker fixes verified by running the full test suite + ruff lint + targeted new tests for each fix. If existing tests don't cover the fixed code path, write a new test.
- **D-07:** Fixes committed in batches by team — one commit per team's blocker resolutions (e.g., `fix(security): resolve all security blockers`). Maximum 3 fix commits.

### Non-Blocker Tracking
- **D-08:** All non-blockers documented in a detailed `18-FINDINGS.md` report in the phase directory, categorized by team (security/stability/performance).
- **D-09:** Each non-blocker also added as a GSD todo that references the findings document for full details.
- **D-10:** Non-blockers prioritized as P1 (fix before prod — next available phase), P2 (fix when convenient), or P3 (nice-to-have / code quality). Todos inherit the priority.

### Claude's Discretion
- How to partition files across agent teams internally (all teams get all files, but execution order/batching is Claude's call)
- Findings report structure beyond the team/priority framework decided above
- Whether to group related findings or report individually

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — REVIEW-01, REVIEW-02, REVIEW-03 acceptance criteria
- `.planning/ROADMAP.md` §Phase 18 — Success criteria (lines 85-89)

### Prior Phase Context
- `.planning/phases/17-tech-debt-resolution/17-CONTEXT.md` — Phase 17 decisions and code changes (files recently modified that need fresh review eyes)

### Source Files (review targets — all 45 .py files under src/civpulse_geo/)
- `src/civpulse_geo/providers/` — 7 provider files (external API calls, SQL queries — high-risk for security + performance)
- `src/civpulse_geo/services/` — 5 service files (cascade pipeline, fuzzy matching, LLM corrector — high-risk for stability + performance)
- `src/civpulse_geo/api/` — 3 API route files (user-facing endpoints — high-risk for security + stability)
- `src/civpulse_geo/config.py` — Settings class (secrets, env vars — security review)
- `src/civpulse_geo/database.py` — Connection pool config (performance review)
- `src/civpulse_geo/main.py` — Lifespan, startup logic (stability review)
- `src/civpulse_geo/cli/` — CLI commands (input validation — security review)
- `src/civpulse_geo/models/` — SQLAlchemy models (query patterns — performance review)
- `src/civpulse_geo/schemas/` — Pydantic schemas (input validation — security review)
- `src/civpulse_geo/spell/` — Spell corrector (stability review)
- `src/civpulse_geo/normalization.py` — Address normalization (stability review)

### Test Files (correctness review only)
- `tests/` — 29 test files, 504 tests

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing test suite (504 tests) serves as regression baseline for fix verification
- ruff already configured for linting — use as part of fix verification pipeline

### Established Patterns
- **Config pattern**: `Settings(BaseSettings)` with env-var overrides — security review should verify no secrets in defaults
- **Provider pattern**: ABC base class with concrete providers — each provider is an independent review unit
- **Cascade pipeline**: 6-stage orchestrator — stability review should trace every exception path through all stages
- **Pydantic schemas**: Request/response validation — security review should verify all external inputs flow through Pydantic

### Integration Points
- Phase 17 recently modified: `cascade.py`, `config.py`, `main.py`, `corrector.py`, `tiger.py`, `cli/__init__.py` — these files have fresh changes that warrant careful review
- Database connection pool in `database.py` — performance team must check pool sizing against deployment resource limits (Phase 20 will set K8s resource limits)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — standard three-team parallel audit with the severity thresholds and tracking mechanisms decided above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 18-code-review*
*Context gathered: 2026-03-29*
