# Phase 13: Spell Correction and Fuzzy/Phonetic Matching - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Recover addresses with typoed or phonetically misspelled street names before they reach the cascade orchestrator (Phase 14). This phase delivers two components: (1) an offline spell correction layer using symspellpy that corrects street name tokens before scourgify normalization, and (2) a FuzzyMatcher service using pg_trgm word_similarity() with Double Metaphone tiebreaking as a fallback when all exact-match providers return NO_MATCH.

</domain>

<decisions>
## Implementation Decisions

### Spell Correction Behavior (SPELL-01)
- **D-01:** symspellpy with max_edit_distance=2 — catches single and double typos (e.g., "Mrccer"→"Mercer")
- **D-02:** Multi-word street names corrected per-word independently — split on spaces, correct each token, rejoin (handles "Maartin Lther King"→"Martin Luther King")
- **D-03:** When multiple candidates have similar scores, use top candidate only — if it fails exact match, fuzzy matching (FUZZ-02) catches the rest
- **D-04:** Skip spell correction for street names < 4 characters — short names ("Oak", "Elm") have too many edit-distance neighbors; pass through uncorrected, let fuzzy matching handle if needed

### FuzzyMatcher Architecture (FUZZ-02, FUZZ-03)
- **D-05:** New service class at `services/fuzzy.py` with FuzzyMatcher — called explicitly by Phase 14 orchestrator after exact match fails. Follows existing services/ pattern (geocoding.py, validation.py)
- **D-06:** FuzzyMatcher queries ALL local provider staging tables (OA, NAD, and Macon-Bibb) — Macon-Bibb will need a GIN trigram index added (OA and NAD indexes exist from Phase 12)
- **D-07:** Fuzzy match confidence scales with word_similarity() score — map similarity range (0.65–1.0) to confidence range (e.g., 0.50–0.75). Slots between scourgify (0.3) and exact matches (0.8+) for Phase 14 consensus scoring

### Dictionary Lifecycle (SPELL-02, SPELL-03)
- **D-08:** Dictionary stored in a PostgreSQL table (spell_dictionary) — centralized source of truth populated by CLI commands
- **D-09:** Each API worker loads the dictionary table into an in-memory SymSpell object at startup — one query, then in-memory for all requests. Workers pick up new dictionaries on restart
- **D-10:** Auto-rebuild: `load-oa`, `load-nad`, and `gis import` CLI commands call a shared `rebuild_dictionary()` function at the end, which queries all staging tables for distinct street names and populates the spell_dictionary table
- **D-11:** Manual rebuild also available via standalone `rebuild-dictionary` CLI command for ad-hoc rebuilds

### Fuzzy/Phonetic Fallback Strategy (FUZZ-02, FUZZ-03, FUZZ-04)
- **D-12:** Trigram first, Double Metaphone tiebreaker — word_similarity() runs first; if top candidate is clearly best (gap > 0.05 from runner-up), use it; if ambiguous (multiple within 0.05), dmetaphone() picks the phonetically closest
- **D-13:** word_similarity() threshold starts at 0.65 minimum — per FUZZ-02 range of 0.65–0.70; can tighten during calibration
- **D-14:** Return best match only from fuzzy — single best candidate (highest similarity, Metaphone tiebroken) for simpler Phase 14 orchestrator integration
- **D-15:** FUZZ-04 calibration via automated test suite with 30 addresses — Issue #1's 4 known addresses plus 26 generated addresses (mix of real, fake, varying error levels). Thresholds asserted in CI; regression catches calibration drift

### Claude's Discretion
- Alembic migration strategy for Macon-Bibb GIN index (new migration vs extending existing)
- `fuzzystrmatch` extension enablement approach (may already be present for Tiger)
- Internal SymSpell loading pattern (app startup hook vs lazy initialization)
- spell_dictionary table schema design (columns, indexes)
- Exact confidence mapping formula for similarity→confidence conversion
- Test address generation strategy for the 26 calibration addresses (geographic distribution, error types)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider Implementation
- `src/civpulse_geo/providers/openaddresses.py` — Shared `_parse_input_address()` (5-tuple), existing `_find_oa_fuzzy_match()` (address-number fuzzy, different from street-name fuzzy), street matching patterns
- `src/civpulse_geo/providers/nad.py` — NAD provider with same parse/match patterns as OA
- `src/civpulse_geo/providers/macon_bibb.py` — Macon-Bibb provider; needs GIN trigram index for D-06
- `src/civpulse_geo/providers/schemas.py` — GeocodingResult/ValidationResult with confidence field

### Services
- `src/civpulse_geo/services/geocoding.py` — Existing service pattern; FuzzyMatcher follows this
- `src/civpulse_geo/services/validation.py` — Existing service pattern

### Database and Migrations
- `alembic/versions/f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py` — Phase 12 migration: pg_trgm extension + GIN indexes on OA and NAD street columns
- `src/civpulse_geo/models/openaddresses.py` — OA staging table definition
- `src/civpulse_geo/models/nad.py` — NAD staging table definition

### CLI Commands
- `src/civpulse_geo/cli/__init__.py` — `load-oa` (line 611), `load-nad` (line 758), `gis import` commands where dictionary rebuild hooks attach (SPELL-03/D-10)

### Requirements
- `.planning/REQUIREMENTS.md` — SPELL-01 through SPELL-03, FUZZ-02 through FUZZ-04 requirements with acceptance criteria

### Prior Phase Context
- `.planning/phases/12-correctness-fixes-and-db-prerequisites/12-CONTEXT.md` — Phase 12 decisions: 5-tuple parse (D-08), confidence values scourgify=0.3/Tiger=0.4 (D-09/D-10)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_parse_input_address()` in `openaddresses.py` — returns 5-tuple (street_number, street_name, zip, street_suffix, street_directional); spell correction targets the street_name token (index 1)
- GIN trigram indexes on `openaddresses_points.street_name` and `nad_points.street_name` — already exist from Phase 12; word_similarity() queries will use these
- `pg_trgm` extension — already enabled in Phase 12 migration
- Mock session factory pattern in tests — reusable for FuzzyMatcher test cases

### Established Patterns
- Service classes in `services/` with async methods accepting DB sessions
- Local providers use `is_local=True` and bypass DB cache
- Alembic migrations use `op.execute()` for extension and index creation
- CLI commands use Typer with Rich progress displays

### Integration Points
- SpellCorrector inserts before scourgify normalization in the geocoding pipeline (SPELL-01)
- FuzzyMatcher is a new service called by Phase 14 orchestrator — not a provider in the registry
- Dictionary rebuild hooks attach to existing CLI command functions (`load-oa`, `load-nad`, `gis import`)
- New Alembic migration needed for: spell_dictionary table, Macon-Bibb GIN trigram index, fuzzystrmatch extension (if not present)

</code_context>

<specifics>
## Specific Ideas

- Calibration test suite should include 30 addresses total (4 from Issue #1 + 26 generated) with a mix of real addresses, fake addresses, and varying levels of mistakes — this is a significant expansion beyond FUZZ-04's original 4-address requirement
- Confidence values for fuzzy results must slot between scourgify (0.3) and exact matches (0.8+) to work correctly with Phase 14 consensus scoring
- Macon-Bibb largely duplicates OA data but user explicitly wants it included in FuzzyMatcher coverage

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 13-spell-correction-and-fuzzy-phonetic-matching*
*Context gathered: 2026-03-29*
