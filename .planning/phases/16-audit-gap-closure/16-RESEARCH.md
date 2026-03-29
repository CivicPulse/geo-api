# Phase 16: Audit Gap Closure - Research

**Researched:** 2026-03-29
**Domain:** FastAPI app startup wiring, Python tuple unpacking, documentation, verification artifacts
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FUZZ-02 | FuzzyMatcher service uses `word_similarity()` with threshold 0.65–0.70 as fallback after all exact providers return NO_MATCH | Code exists in `services/fuzzy.py`; gap is `app.state.fuzzy_matcher` is never assigned in `main.py` lifespan — cascade stage 3 is unreachable at runtime |
| FUZZ-03 | Double Metaphone used as secondary phonetic fallback when trigram similarity is ambiguous | Code exists in `services/fuzzy.py`; same startup wiring gap blocks it from firing |
| FUZZ-04 | Fuzzy match thresholds calibrated against Issue #1 E2E test corpus | `tests/test_fuzzy_calibration.py` exists and passes (50 tests); gap is Phase 13 VERIFICATION.md does not yet exist to formally confirm this |
| FIX-01 | Tiger geocode results filtered by county boundary | Already satisfied; re-confirmation via VERIFICATION.md |
| FIX-02 | Local providers use zip prefix fallback for short zips | Already satisfied; re-confirmation via VERIFICATION.md |
| FIX-03 | Street name matching includes `street_suffix` | Already satisfied; re-confirmation via VERIFICATION.md |
| FIX-04 | Confidence values: scourgify=0.3, Tiger=0.4 | Code confirmed correct (`SCOURGIFY_CONFIDENCE=0.3`, `TIGER_VALIDATION_CONFIDENCE=0.4`); REQUIREMENTS.md text already states correct values — this is a documentation verification, not a code change |
| FUZZ-01 | pg_trgm GIN indexes on OA and NAD tables | Already satisfied; re-confirmation via VERIFICATION.md |
| SPELL-01 | Street name spell-corrected via symspellpy before scourgify | Already satisfied; re-confirmation via VERIFICATION.md |
| SPELL-02 | Spell correction dictionary built from NAD/OA/Macon-Bibb staging tables | Already satisfied; re-confirmation via VERIFICATION.md |
| SPELL-03 | Dictionary auto-rebuilds on CLI load commands | Already satisfied; re-confirmation via VERIFICATION.md |
</phase_requirements>

---

## Summary

Phase 16 is a targeted gap-closure phase. All v1.2 code was written during Phases 12-15, but a post-completion audit on 2026-03-29 identified four concrete gaps that prevent FUZZ-02/03/04 from being formally satisfied and cause a runtime `ValueError` in the legacy path.

The most critical defect is in `src/civpulse_geo/main.py`: the FastAPI `lifespan` startup hook creates `app.state.spell_corrector` and `app.state.llm_corrector` but never creates `app.state.fuzzy_matcher`. The `FuzzyMatcher` class is fully implemented at `services/fuzzy.py` and has 50 passing tests, but it is completely unreachable at runtime because `app.state.fuzzy_matcher` is always `None`. When `GeocodingService.geocode()` passes `fuzzy_matcher=getattr(request.app.state, "fuzzy_matcher", None)` to `CascadeOrchestrator.run()`, it always passes `None`, so cascade stage 3 never fires.

The second defect is a Python `ValueError` lurking in `_legacy_geocode()` (line 214 of `services/geocoding.py`): `_parse_input_address()` was expanded to return a 5-tuple in Phase 12, but the log warning at line 214 still unpacks it as a 3-tuple (`street_number, street_name, postal_code = _parse_input_address(normalized)`). This raises `ValueError: too many values to unpack` whenever `CASCADE_ENABLED=false` and all local providers return NO_MATCH.

The third gap is documentation: Phase 13 has no `VERIFICATION.md` confirming SPELL-01/02/03 and FUZZ-02/03/04 are implemented and tested.

The fourth item (FIX-04 REQUIREMENTS.md text) is a documentation verification. The REQUIREMENTS.md already shows `scourgify=0.3; Tiger=0.4` and the code already uses those exact constants. This task is a confirm-and-document step only.

**Primary recommendation:** Three code/doc changes in a single plan: (1) add `FuzzyMatcher` startup wiring in `main.py`, (2) fix 3-tuple unpack to 5-tuple in `_legacy_geocode()`, (3) create `.planning/phases/13-spell-correction-and-fuzzy-phonetic-matching/13-VERIFICATION.md`. No new libraries needed.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.x (installed) | App startup lifespan hook — `app.state` assignments | Already used in `main.py` for `spell_corrector` and `llm_corrector` wiring |
| SQLAlchemy async_sessionmaker | 2.0.x (installed) | FuzzyMatcher session factory — same pattern as other providers | `AsyncSessionLocal` already used for all conditional provider registrations |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 (installed) | Test new startup wiring and 5-tuple fix | Unit tests for both fixes |
| pytest-asyncio | 1.3.0 (installed) | Async test support | All new tests use async service layer |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Unconditional FuzzyMatcher init | Conditional init (check if staging data exists) | Unconditional is correct — FuzzyMatcher queries at call time, not at startup; it does not need staging data to be registered |

**No new package installs required.** All dependencies already in pyproject.toml.

---

## Architecture Patterns

### Recommended Project Structure
No new files needed except `13-VERIFICATION.md`. All fixes are edits to existing files.

```
src/civpulse_geo/
├── main.py                  # ADD: app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)
├── services/
│   └── geocoding.py         # FIX: line 214 — 3-tuple → 5-tuple unpack
.planning/phases/
└── 13-spell-correction-and-fuzzy-phonetic-matching/
    └── 13-VERIFICATION.md   # NEW: formal verification of SPELL-01/02/03, FUZZ-02/03/04
```

### Pattern 1: FuzzyMatcher Startup Wiring

**What:** Add `app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)` to the `lifespan` function in `main.py`, following the exact same pattern as `spell_corrector` and `llm_corrector`.

**When to use:** Always unconditional — FuzzyMatcher itself handles empty staging tables gracefully (returns None when no candidates found), so no conditional data-availability check is needed.

**Where to add it:** After the spell_corrector block, before the LLM corrector block. Add the import at the top of `main.py`.

**Example:**
```python
# Source: src/civpulse_geo/main.py (existing pattern — spell_corrector block)

# Import to add at top of main.py:
from civpulse_geo.services.fuzzy import FuzzyMatcher

# Add in lifespan(), after spell_corrector block:
app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)
logger.info("FuzzyMatcher registered")
```

No try/except needed — `FuzzyMatcher.__init__` only stores the session factory, it does not connect to the database.

### Pattern 2: 5-Tuple Unpack Fix

**What:** Change the 3-tuple unpack on line 214 of `services/geocoding.py` to a 5-tuple unpack, matching what `_parse_input_address()` actually returns since Phase 12.

**Root cause:** `_parse_input_address()` signature is:
```python
def _parse_input_address(
    address: str,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Returns (street_number, street_name, postal_code, street_suffix, street_directional)"""
```

It returns 5 values. The logger at line 214 only uses 3 of them, so the fix is to unpack all 5 (discarding the last two with underscores):

```python
# BEFORE (line 214 — raises ValueError):
street_number, street_name, postal_code = _parse_input_address(normalized)

# AFTER:
street_number, street_name, postal_code, _, _ = _parse_input_address(normalized)
```

The logger call on lines 215-220 only references `street_number`, `street_name`, and `postal_code`, so the discard variables `_` are correct — no behavior change, just correct unpacking.

### Pattern 3: VERIFICATION.md Format

**What:** Create `13-VERIFICATION.md` following the project's existing verification artifact format. Confirmed by checking Phase 12's verification structure.

**Content requirements (per Phase 16 success criterion 3):**
- Confirm SPELL-01, SPELL-02, SPELL-03 are implemented and tested
- Confirm FUZZ-02, FUZZ-03, FUZZ-04 are implemented and tested
- Reference the specific test files and passing counts
- Confirm test suite passage

### Anti-Patterns to Avoid

- **Conditional FuzzyMatcher init:** Do NOT wrap `FuzzyMatcher` registration in an `if await _some_data_available()` check — FuzzyMatcher does not fail on empty staging tables, and adding a conditional would make it unregistered in empty-DB test environments.
- **Unused variable warning suppression:** Use `_, _` for the discarded 5-tuple values, not a named variable — naming them implies they are used.
- **Amending existing PLAN files:** Do not modify Phase 13 plan files or summaries to backfill the VERIFICATION.md — write it fresh as a standalone artifact.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Checking if FuzzyMatcher can connect to DB at startup | Custom DB connectivity probe | No probe needed | `FuzzyMatcher.__init__` is stateless; DB errors are handled at query time via SQLAlchemy exceptions |
| Logging FuzzyMatcher startup | Custom health check endpoint | Log in `lifespan` like `spell_corrector` does | One-line logger.info is sufficient; pattern already established |

**Key insight:** This phase is almost entirely a wiring/documentation fix. The hard work (FuzzyMatcher, spell correction, 5-tuple expansion) was done in Phases 12-13. Phase 16 closes the integration gap between finished components.

---

## Common Pitfalls

### Pitfall 1: Test Mock Does Not Reproduce the ValueError

**What goes wrong:** Tests for `_legacy_geocode` mock `_parse_input_address` to return a 3-tuple or a specific value, so the unpack bug never raises in the test suite even before the fix.

**Why it happens:** The existing `TestLocalProviderBypass` tests use addresses where all local providers return `confidence > 0.0`, so the `if local_results and all(r.confidence == 0.0 ...)` branch (line 213) is never entered.

**How to avoid:** Write a test that uses a local provider returning `confidence=0.0` with `CASCADE_ENABLED=false`. This exercises line 214 directly. Add this test before fixing the bug (proves the bug), then confirm it passes after the fix.

**Warning signs:** If `uv run pytest tests/test_geocoding_service.py` passes before the 5-tuple fix is applied, the test is not covering the bug path.

### Pitfall 2: FuzzyMatcher Import Cycle

**What goes wrong:** Adding `from civpulse_geo.services.fuzzy import FuzzyMatcher` to `main.py` triggers a circular import if `fuzzy.py` transitively imports from `main.py`.

**Why it happens:** Circular import risk if any module in the import chain imports from `main.py`.

**How to avoid:** Check `services/fuzzy.py` imports — it only imports from `models/`, `loguru`, and `sqlalchemy`. No circular risk. The import is safe.

**Confirmed:** `services/fuzzy.py` imports:
- `civpulse_geo.models.macon_bibb`
- `civpulse_geo.models.nad`
- `civpulse_geo.models.openaddresses`
- `loguru`, `sqlalchemy`

None of these import from `main.py`.

### Pitfall 3: FuzzyMatcher Already Imported in geocoding.py

**What goes wrong:** Planner adds a redundant import to `main.py` without checking that `FuzzyMatcher` is already imported in the services layer.

**Why it's not a problem:** `main.py` does NOT yet import `FuzzyMatcher`. The import must be added to `main.py`. `services/geocoding.py` does have `from civpulse_geo.services.fuzzy import FuzzyMatcher` (line 41) but that is a different file.

### Pitfall 4: Startup Wiring Inside a Try/Except Silently Fails

**What goes wrong:** Wrapping the FuzzyMatcher assignment in a try/except means a bug in `FuzzyMatcher.__init__` would set `app.state.fuzzy_matcher = None` silently, repeating the original gap.

**How to avoid:** Since `FuzzyMatcher.__init__` is stateless (just stores `session_factory`), no try/except is needed. The assignment is unconditional and cannot fail.

---

## Code Examples

### Complete main.py lifespan change (diff view)

```python
# Source: src/civpulse_geo/main.py

# ADD this import near the top (after other service imports):
from civpulse_geo.services.fuzzy import FuzzyMatcher

# In lifespan(), after the spell_corrector block (before LLM corrector block):
# REPLACE: (nothing — this is a pure addition)
# ADD:
app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)
logger.info("FuzzyMatcher registered")
```

### Complete geocoding.py fix

```python
# Source: src/civpulse_geo/services/geocoding.py, line 214

# BEFORE:
street_number, street_name, postal_code = _parse_input_address(normalized)

# AFTER:
street_number, street_name, postal_code, _, _ = _parse_input_address(normalized)
```

### Test for the legacy path ValueError (to write before fixing)

```python
# Demonstrates the bug: local provider returns NO_MATCH + CASCADE_ENABLED=false
@pytest.mark.asyncio
async def test_legacy_geocode_no_match_does_not_raise_value_error():
    """_legacy_geocode logs a warning (not ValueError) when all local providers return NO_MATCH."""
    service = GeocodingService()
    local_provider = _make_local_geocoding_provider(confidence=0.0)  # NO_MATCH
    http_client = AsyncMock()
    db, address = _make_db_for_local_provider()

    with patch("civpulse_geo.services.geocoding.settings") as mock_settings:
        mock_settings.cascade_enabled = False
        # Should not raise ValueError: too many values to unpack
        result = await service.geocode(
            freeform="123 XYZZY ST MACON GA 31201",
            db=db,
            providers={"test-local": local_provider},
            http_client=http_client,
        )
    assert result["local_results"][0].confidence == 0.0
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_parse_input_address` returns 3-tuple | Returns 5-tuple (adds `street_suffix`, `street_directional`) | Phase 12 | Legacy path warning logger still uses 3-tuple unpack — `ValueError` on NO_MATCH |
| FuzzyMatcher fully implemented | FuzzyMatcher startup-wired to `app.state` | Phase 13 (code) → Phase 16 (wiring) | FUZZ-02/03/04 cannot be satisfied until wiring is done |

---

## Open Questions

1. **Is the FIX-04 documentation task a no-op?**
   - What we know: REQUIREMENTS.md line 15 already reads "Scourgify validation confidence reduced from 1.0 to 0.3; Tiger validation confidence reduced from 1.0 to 0.4". The actual code constants (`SCOURGIFY_CONFIDENCE=0.3`, `TIGER_VALIDATION_CONFIDENCE=0.4`) match.
   - What's unclear: The audit said FIX-04 text needs updating, but the text already appears correct. Possibly the original requirement text said "reduced to 0.5" and was already patched, or the audit was noting a documentation-code alignment check rather than an actual change.
   - Recommendation: Read REQUIREMENTS.md carefully during plan execution. If the text already matches, document the verification and move on. No code change needed.

2. **Should Phase 13 VERIFICATION.md also mention Phase 12 requirements (FIX-01/02/03/04, FUZZ-01)?**
   - What we know: Phase 16 success criterion 3 says "Phase 13 has a VERIFICATION.md confirming SPELL-01/02/03 and FUZZ-02/03/04". FIX-01/02/03/04 and FUZZ-01 belong to Phase 12.
   - Recommendation: Write Phase 13 VERIFICATION.md scoped to Phase 13 requirements only (SPELL-01/02/03, FUZZ-02/03/04). A separate Phase 12 VERIFICATION.md is out of scope for Phase 16.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv / Python | Test execution | Yes | Python 3.12.3, uv 0.10.9 | — |
| pytest + pytest-asyncio | All tests | Yes | pytest 9.0.2, pytest-asyncio 1.3.0 | — |
| FuzzyMatcher service | Startup wiring | Yes (code exists) | N/A | — |

**No missing dependencies.** All changes are code edits and documentation writes.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_geocoding_service.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FUZZ-02 | FuzzyMatcher assigned to `app.state.fuzzy_matcher` at startup | unit | `uv run pytest tests/test_startup_wiring.py -x -q` | No — Wave 0 |
| FUZZ-02 | Cascade stage 3 fires (fuzzy_matcher is not None in orchestrator) | unit | `uv run pytest tests/test_geocoding_service.py -x -q` | Partial — needs new test |
| FUZZ-03 | dmetaphone tiebreaker resolves ambiguous candidates | unit | `uv run pytest tests/test_fuzzy_matcher.py -x -q` | Yes |
| FUZZ-04 | 30-address calibration corpus passes | integration | `uv run pytest tests/test_fuzzy_calibration.py -x -q` | Yes |
| FIX-01 | Tiger county filter verified | existing | `uv run pytest tests/test_tiger_provider.py -x -q` | Yes |
| Legacy path | `_legacy_geocode` no-match path does not raise ValueError | unit | `uv run pytest tests/test_geocoding_service.py -x -q` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_geocoding_service.py tests/test_fuzzy_matcher.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite with no new failures before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] Test for `_legacy_geocode` NO_MATCH path exercising line 214 (proves the 5-tuple bug, then confirms the fix)
- [ ] Test for `app.state.fuzzy_matcher` assignment in startup wiring (may be integration-style or use `TestClient`)

Alternatively: the startup wiring is straightforward enough that the planner may opt to verify via a smoke test (import + instantiate) rather than a full `TestClient` lifespan test. If the planner uses that approach, document the rationale.

---

## Pre-Existing Test Failures (Do Not Regress)

The full test suite currently has **11 pre-existing failures** unrelated to Phase 16:

- `tests/test_import_cli.py` — 10 failures due to missing fixture file: `data/SAMPLE_Address_Points.geojson`
- `tests/test_load_oa_cli.py` — 1 failure for same reason

Phase 16 success criterion 5 ("full test suite passes with no new failures") means the post-fix run must show the same 11 failures and no new ones. The planner should confirm this explicitly in the verification step.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `src/civpulse_geo/main.py` — confirmed FuzzyMatcher is absent from lifespan
- Direct code inspection of `src/civpulse_geo/services/geocoding.py` line 214 — confirmed 3-tuple unpack bug
- Direct code inspection of `src/civpulse_geo/providers/openaddresses.py` lines 73-110 — confirmed 5-tuple return signature
- Direct code inspection of `src/civpulse_geo/services/fuzzy.py` — confirmed FuzzyMatcher implementation is complete
- Direct code inspection of `.planning/REQUIREMENTS.md` line 15 — confirmed FIX-04 text already correct
- `uv run pytest --collect-only -q` — confirmed 516 tests collected, 11 pre-existing failures

### Secondary (MEDIUM confidence)
- `.planning/phases/13-spell-correction-and-fuzzy-phonetic-matching/13-02-PLAN.md` — confirmed FuzzyMatcher was fully planned and built but never wired to startup
- `.planning/STATE.md` `## Decisions` section — confirmed D-09 = SpellCorrector uses sync engine at startup, `app.state.spell_corrector = None` on error; FuzzyMatcher pattern is analogous but simpler (no sync engine needed)

### Tertiary (LOW confidence)
None.

---

## Metadata

**Confidence breakdown:**
- Bug identification: HIGH — confirmed by direct code inspection of the exact lines that are broken
- Fix approach: HIGH — pattern is established (spell_corrector wiring in same file; `_apply_spell_correction` already uses 5-tuple correctly)
- Pitfalls: HIGH — confirmed by tracing actual code paths and test suite state
- No-op items: HIGH — FIX-04 doc check verified correct by direct REQUIREMENTS.md read + code constant grep

**Research date:** 2026-03-29
**Valid until:** This research does not age — it is a code snapshot of a specific codebase state. Valid until the codebase changes.
