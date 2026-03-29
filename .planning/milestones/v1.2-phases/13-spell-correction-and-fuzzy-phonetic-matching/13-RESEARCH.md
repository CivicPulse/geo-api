# Phase 13: Spell Correction and Fuzzy/Phonetic Matching - Research

**Researched:** 2026-03-29
**Domain:** symspellpy spell correction, pg_trgm fuzzy matching, PostgreSQL fuzzystrmatch Double Metaphone
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Spell Correction Behavior (SPELL-01)**
- D-01: symspellpy with max_edit_distance=2 — catches single and double typos (e.g., "Mrccer"→"Mercer")
- D-02: Multi-word street names corrected per-word independently — split on spaces, correct each token, rejoin (handles "Maartin Lther King"→"Martin Luther King")
- D-03: When multiple candidates have similar scores, use top candidate only — if it fails exact match, fuzzy matching (FUZZ-02) catches the rest
- D-04: Skip spell correction for street names < 4 characters — short names ("Oak", "Elm") have too many edit-distance neighbors; pass through uncorrected, let fuzzy matching handle if needed

**FuzzyMatcher Architecture (FUZZ-02, FUZZ-03)**
- D-05: New service class at `services/fuzzy.py` with FuzzyMatcher — called explicitly by Phase 14 orchestrator after exact match fails. Follows existing services/ pattern (geocoding.py, validation.py)
- D-06: FuzzyMatcher queries ALL local provider staging tables (OA, NAD, and Macon-Bibb) — Macon-Bibb will need a GIN trigram index added (OA and NAD indexes exist from Phase 12)
- D-07: Fuzzy match confidence scales with word_similarity() score — map similarity range (0.65–1.0) to confidence range (e.g., 0.50–0.75). Slots between scourgify (0.3) and exact matches (0.8+) for Phase 14 consensus scoring

**Dictionary Lifecycle (SPELL-02, SPELL-03)**
- D-08: Dictionary stored in a PostgreSQL table (spell_dictionary) — centralized source of truth populated by CLI commands
- D-09: Each API worker loads the dictionary table into an in-memory SymSpell object at startup — one query, then in-memory for all requests. Workers pick up new dictionaries on restart
- D-10: Auto-rebuild: `load-oa`, `load-nad`, and `gis import` CLI commands call a shared `rebuild_dictionary()` function at the end, which queries all staging tables for distinct street names and populates the spell_dictionary table
- D-11: Manual rebuild also available via standalone `rebuild-dictionary` CLI command for ad-hoc rebuilds

**Fuzzy/Phonetic Fallback Strategy (FUZZ-02, FUZZ-03, FUZZ-04)**
- D-12: Trigram first, Double Metaphone tiebreaker — word_similarity() runs first; if top candidate is clearly best (gap > 0.05 from runner-up), use it; if ambiguous (multiple within 0.05), dmetaphone() picks the phonetically closest
- D-13: word_similarity() threshold starts at 0.65 minimum — per FUZZ-02 range of 0.65–0.70; can tighten during calibration
- D-14: Return best match only from fuzzy — single best candidate (highest similarity, Metaphone tiebroken) for simpler Phase 14 orchestrator integration
- D-15: FUZZ-04 calibration via automated test suite with 30 addresses — Issue #1's 4 known addresses plus 26 generated addresses (mix of real, fake, varying error levels). Thresholds asserted in CI; regression catches calibration drift

### Claude's Discretion
- Alembic migration strategy for Macon-Bibb GIN index (new migration vs extending existing)
- `fuzzystrmatch` extension enablement approach (may already be present for Tiger)
- Internal SymSpell loading pattern (app startup hook vs lazy initialization)
- spell_dictionary table schema design (columns, indexes)
- Exact confidence mapping formula for similarity→confidence conversion
- Test address generation strategy for the 26 calibration addresses (geographic distribution, error types)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPELL-01 | Address input spell-corrected via symspellpy before scourgify normalization, scoped to street name token only | symspellpy 6.9 `lookup()` with Verbosity.TOP; `_parse_input_address()` 5-tuple provides street_name at index 1 |
| SPELL-02 | Spell correction dictionary built from NAD, OA, and Macon-Bibb staging table street names | `create_dictionary_entry(word, count)` loop over DISTINCT street names from all three tables |
| SPELL-03 | Dictionary auto-rebuilds when `load-oa`, `load-nad`, or `gis import` CLI commands complete | Attach `rebuild_dictionary()` call after commit in each CLI command function (lines 611, 758, and gis import) |
| FUZZ-02 | FuzzyMatcher service uses `word_similarity()` with threshold 0.65–0.70 as fallback after all exact providers return NO_MATCH | pg_trgm `word_similarity()` confirmed available (pg_trgm 1.6 installed); GIN indexes on OA + NAD exist; Macon-Bibb index needs new migration |
| FUZZ-03 | Double Metaphone used as secondary phonetic fallback when trigram similarity is ambiguous | `dmetaphone()` from fuzzystrmatch 1.2 confirmed installed; safe for ASCII US street names |
| FUZZ-04 | Fuzzy match thresholds calibrated against Issue #1 E2E test corpus (30 addresses total) | Pytest test file with parameterized address corpus; thresholds asserted, regression detects drift |
</phase_requirements>

---

## Summary

Phase 13 delivers two components: SpellCorrector (offline pre-normalization typo recovery) and FuzzyMatcher (post-exact-match fallback using PostgreSQL trigrams + Double Metaphone). Both build on infrastructure already in place from Phase 12: the `pg_trgm` and `fuzzystrmatch` extensions are confirmed installed (pg_trgm 1.6, fuzzystrmatch 1.2), GIN indexes exist on OA and NAD street_name columns, and `_parse_input_address()` already extracts the street_name token this phase targets.

SpellCorrector uses symspellpy 6.9 (not yet in pyproject.toml — must be added). The dictionary is populated at startup from a `spell_dictionary` PostgreSQL table, which is rebuilt automatically after every CLI data-load command. `create_dictionary_entry()` is called per-word with frequency count 1 (or actual count if frequency matters) for each distinct street name across all three staging tables.

FuzzyMatcher is a new service class at `services/fuzzy.py`, following the pattern established by `services/geocoding.py`. It executes `word_similarity(input_street, street_name)` across OA, NAD, and Macon-Bibb staging tables (the last needs a new Alembic migration for its GIN index), returns the top candidate above 0.65 threshold, uses `dmetaphone()` as a tiebreaker when multiple candidates score within 0.05 of each other, and maps similarity to confidence in the 0.50–0.75 range.

**Primary recommendation:** Add symspellpy as a project dependency; write a new Alembic migration for the Macon-Bibb GIN index; implement SpellCorrector and FuzzyMatcher as thin Python classes that delegate the heavy lifting to pg_trgm and fuzzystrmatch (both already in the DB).

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| symspellpy | 6.9.0 | Offline spell correction using symmetric delete algorithm | 1M+ word lookup in ~2ms; pure Python port of SymSpell v6.7.2; widely used for address correction |
| PostgreSQL pg_trgm | 1.6 (installed) | `word_similarity()` for fuzzy street name matching | GIN indexes already exist on OA + NAD from Phase 12; no new extension needed |
| PostgreSQL fuzzystrmatch | 1.2 (installed) | `dmetaphone()` phonetic tiebreaker | Already installed as Tiger geocoder dependency; no new extension needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLAlchemy `func.` | 2.0.x (installed) | Call `word_similarity()` and `dmetaphone()` via ORM | Use `func.word_similarity()` and `text()` inside async SQLAlchemy queries |
| pytest-asyncio | 1.3.0 (installed) | Async test support for FuzzyMatcher and SpellCorrector tests | All new test files |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| symspellpy | pyspellchecker, hunspell | symspellpy is 1000x faster for large custom dictionaries; direct control over dictionary |
| pg_trgm word_similarity() | Levenshtein in Python | DB-side is faster for large tables; GIN indexes eliminate sequential scan |
| dmetaphone() in Postgres | Python `double-metaphone` package (v0.6) | Using Postgres keeps tiebreak in the same query; no Python round-trip |

**Installation:**
```bash
uv add symspellpy
```

**Version verification:** symspellpy 6.9.0 confirmed on PyPI as of 2026-03-29. Not yet in pyproject.toml.

---

## Architecture Patterns

### Recommended Project Structure
```
src/civpulse_geo/
├── spell/
│   ├── __init__.py
│   └── corrector.py          # SpellCorrector class (SPELL-01, SPELL-02)
├── services/
│   ├── fuzzy.py              # FuzzyMatcher class (FUZZ-02, FUZZ-03) — new file
│   ├── geocoding.py          # Existing — reference pattern
│   └── validation.py         # Existing — reference pattern
├── models/
│   └── spell_dictionary.py   # spell_dictionary ORM model (D-08)
├── cli/
│   └── __init__.py           # Add rebuild_dictionary() hook to load-oa, load-nad, gis import
alembic/versions/
│   └── XXXX_add_macon_bibb_trgm_spell_dict.py   # New migration
tests/
    ├── test_spell_corrector.py      # Unit tests for SpellCorrector
    ├── test_fuzzy_matcher.py        # Unit tests for FuzzyMatcher
    └── test_fuzzy_calibration.py    # 30-address corpus calibration (FUZZ-04)
```

### Pattern 1: symspellpy In-Memory Dictionary Loading

**What:** At API startup (in `lifespan()`), query `spell_dictionary` table once, load all words into an in-memory SymSpell object, store on `app.state`. All requests use the in-memory object.

**When to use:** App startup hook — same pattern as provider registration in `main.py`

**Example:**
```python
# Source: symspellpy 6.9 API (verified via GitHub source)
from symspellpy import SymSpell, Verbosity

sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
# Load from spell_dictionary table (sync query at startup)
rows = conn.execute("SELECT word, frequency FROM spell_dictionary").fetchall()
for word, freq in rows:
    sym_spell.create_dictionary_entry(word, freq)
# Store on app.state for request use
app.state.sym_spell = sym_spell
```

### Pattern 2: SpellCorrector — Per-Token Street Name Correction

**What:** Accept the raw address string; call `_parse_input_address()` to extract street_name; split on spaces; correct each token >= 4 chars with `lookup(token, Verbosity.TOP, max_edit_distance=2)`; rejoin; reconstruct address with corrected street name.

**When to use:** Before scourgify normalization in the geocoding pipeline (SPELL-01)

**Example:**
```python
# Source: symspellpy 6.9 API
from symspellpy import Verbosity

def correct_street_name(sym_spell, street_name: str) -> str:
    """Correct each word in street_name independently. Skip tokens < 4 chars (D-04)."""
    tokens = street_name.split()
    corrected = []
    for token in tokens:
        if len(token) < 4:
            corrected.append(token)  # D-04: pass short tokens through uncorrected
            continue
        suggestions = sym_spell.lookup(token, Verbosity.TOP, max_edit_distance=2)
        if suggestions:
            corrected.append(suggestions[0].term)  # D-03: top candidate only
        else:
            corrected.append(token)  # no suggestion: keep original
    return " ".join(corrected)
```

**SuggestItem fields:**
- `suggestions[0].term` — the corrected word string
- `suggestions[0].distance` — edit distance from input
- `suggestions[0].count` — frequency in dictionary

### Pattern 3: FuzzyMatcher — word_similarity() with dmetaphone() Tiebreaker

**What:** Query all three staging tables for streets above the 0.65 threshold; collect top N candidates; if best candidate leads by > 0.05 over second-best, return it; otherwise use `dmetaphone()` to pick the phonetically closest match.

**When to use:** After all exact-match providers return NO_MATCH (called by Phase 14 orchestrator)

**Example:**
```python
# Source: pg_trgm official docs + verified fuzzystrmatch 1.2 install
from sqlalchemy import func, select, text

async def find_fuzzy_match(session, street_name: str, zip_code: str):
    # word_similarity(query, stored_value) — first arg is the partial/mistyped input
    stmt = select(
        OpenAddressesPoint.street_name,
        func.word_similarity(street_name, OpenAddressesPoint.street_name).label("score"),
    ).where(
        func.word_similarity(street_name, OpenAddressesPoint.street_name) >= 0.65,
        OpenAddressesPoint.postcode == zip_code,
    ).order_by(
        func.word_similarity(street_name, OpenAddressesPoint.street_name).desc()
    ).limit(5)
    ...
    # dmetaphone tiebreaker when top candidates are within 0.05 of each other
    # SELECT dmetaphone(:input) = dmetaphone(candidate.street_name)
```

**word_similarity() argument order matters:** `word_similarity(needle, haystack)` — first argument is the potentially partial/mistyped input; second is the stored value. This matches the use case of matching a typed street name against stored street names.

### Pattern 4: Alembic Migration for Macon-Bibb GIN Index + spell_dictionary Table

**What:** Single new migration that: (1) creates `spell_dictionary` table, (2) adds GIN trigram index on `macon_bibb_points.street_name`. The fuzzystrmatch extension does NOT need `CREATE EXTENSION IF NOT EXISTS` in the migration — it is already installed via `20_tiger_setup.sh` at DB init time.

**When to use:** New Alembic migration (separate file, extends migration chain from f6c3d9e2b5a1)

**Example:**
```python
# Source: alembic/versions/f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py pattern
def upgrade() -> None:
    # spell_dictionary table
    op.create_table(
        "spell_dictionary",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("word", sa.String(200), nullable=False, unique=True),
        sa.Column("frequency", sa.Integer, nullable=False, default=1),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_spell_dictionary_word", "spell_dictionary", ["word"])
    # Macon-Bibb GIN trigram index (matches OA and NAD pattern)
    op.execute(
        "CREATE INDEX idx_macon_bibb_street_trgm "
        "ON macon_bibb_points USING gin (street_name gin_trgm_ops)"
    )
```

### Pattern 5: rebuild_dictionary() — Shared CLI Hook

**What:** Synchronous function that queries distinct street names from all three staging tables via a psycopg2 connection, truncates the `spell_dictionary` table, and reinserts. Called at the end of `load-oa`, `load-nad`, and `gis import` CLI commands.

**When to use:** After the existing `conn.commit()` in each CLI command (D-10/D-11)

**Example:**
```python
def rebuild_dictionary(conn) -> int:
    """Rebuild spell_dictionary from distinct street names across all local providers.
    Returns count of words inserted."""
    conn.execute(text("TRUNCATE spell_dictionary"))
    result = conn.execute(text("""
        INSERT INTO spell_dictionary (word, frequency)
        SELECT word, COUNT(*) as frequency FROM (
            SELECT upper(street_name) as word FROM openaddresses_points WHERE street_name IS NOT NULL
            UNION ALL
            SELECT upper(street_name) FROM nad_points WHERE street_name IS NOT NULL
            UNION ALL
            SELECT upper(street_name) FROM macon_bibb_points WHERE street_name IS NOT NULL
        ) all_names
        GROUP BY word
        ON CONFLICT (word) DO UPDATE SET frequency = EXCLUDED.frequency
    """))
    conn.commit()
    return result.rowcount
```

**Note:** The `spell_dictionary` table stores individual words (single tokens), not full street names. The SpellCorrector splits multi-word street names and corrects each token separately (D-02). The dictionary is built from individual words extracted from street names — one word per row.

### Anti-Patterns to Avoid

- **Correcting the full address string:** Spell correction must target ONLY the street_name token. House numbers, zip codes, and state abbreviations must be extracted first via `_parse_input_address()`. Never pass the full address to symspellpy.
- **Using `similarity()` instead of `word_similarity()`:** `similarity()` compares entire strings. `word_similarity()` finds the best matching extent within a longer string — critical when the stored street name is a substring or the input is a substring. Use `word_similarity()`.
- **Calling `dmetaphone()` on non-ASCII input:** The fuzzystrmatch docs warn that dmetaphone does not work well with multibyte UTF-8 strings. US street names are predominantly ASCII. Apply `upper()` and strip non-ASCII characters before calling `dmetaphone()` if safety is needed.
- **Loading symspellpy dictionary per-request:** SymSpell builds a delete-based index at load time. Loading per-request is O(N * edit_distance) and will crater performance. Load once at startup, share the object.
- **Rebuilding dictionary inline in the API path:** Dictionary rebuilds are CLI-only operations. Never trigger a rebuild from an API request handler.
- **Testing calibration with mocked DB:** The 30-address FUZZ-04 calibration corpus must test actual word_similarity() against real (or realistic mock) data — mock DB sessions that return hardcoded scores don't validate threshold correctness.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Edit distance spell correction | Custom Levenshtein loop | symspellpy `lookup()` | SymSpell is O(1) lookup via precomputed delete dictionary; Levenshtein is O(n*m) per candidate |
| Street name tokenization | Custom regex | `_parse_input_address()` already in `openaddresses.py` | 5-tuple extraction already handles usaddress edge cases |
| Trigram similarity | Python-side fuzzy comparison | `pg_trgm word_similarity()` in SQL | GIN indexes make DB-side 100-1000x faster than Python set intersection |
| Phonetic encoding | Custom soundalike | `dmetaphone()` from installed fuzzystrmatch | Already installed; handles English phonetic rules correctly |
| Dictionary persistence | In-memory only / file-based | PostgreSQL `spell_dictionary` table | Survives container restarts; updated by CLI without service restart |

**Key insight:** Both major operations (spell correction and fuzzy matching) have production-ready implementations already available in the project's dependencies. The implementation work is wiring, not algorithm building.

---

## Runtime State Inventory

> Greenfield additions — no existing state to migrate. All new tables and indexes.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — `spell_dictionary` table does not exist yet | Code edit — new Alembic migration creates it |
| Live service config | Docker-compose DB is running; fuzzystrmatch and pg_trgm extensions already installed | None — both verified present |
| OS-registered state | None | None |
| Secrets/env vars | None — no new env vars needed | None |
| Build artifacts | symspellpy not yet in pyproject.toml | Add to dependencies: `uv add symspellpy` |

---

## Common Pitfalls

### Pitfall 1: word_similarity() Argument Order
**What goes wrong:** `word_similarity("MERCER", "MRCER RD")` returns a very different value than `word_similarity("MRCER", "MERCER")`. Swapping arguments changes semantics from "how much of needle is in haystack" to the reverse.
**Why it happens:** `word_similarity(a, b)` measures the greatest similarity between trigrams of `a` and any continuous extent of `b`. The first argument is the "needle" (the potentially misspelled query), the second is the "haystack" (the stored street name).
**How to avoid:** Always pass `word_similarity(input_street_name, stored_street_name)` — input first, stored second.
**Warning signs:** Threshold calibration produces inconsistent results; addresses with short query strings match too broadly.

### Pitfall 2: symspellpy Correcting House Numbers and Zip Codes
**What goes wrong:** Passing the full address string to symspellpy results in "3120" being corrected to "3120" (no change) but "31201" being corrected to "32201" (wrong city), or house number "123" becoming "12" or "1234".
**Why it happens:** SymSpell treats all tokens as words to correct. Numeric strings have many close neighbors.
**How to avoid:** Extract street_name token via `_parse_input_address()` before passing any input to symspellpy. Only call `sym_spell.lookup()` on the street_name component.
**Warning signs:** Tests show zip codes or house numbers changed after spell correction.

### Pitfall 3: Short Street Name Over-Correction (D-04 Violation)
**What goes wrong:** "Elm St" becomes "Elf St" because "Elm" (3 chars) has many edit-distance-1 neighbors that appear more frequently in the dictionary than "Elm".
**Why it happens:** Short words have disproportionately many edit-distance neighbors. Frequency counts from NAD/OA data are not a perfect signal for name correctness.
**How to avoid:** Skip correction for tokens with `len(token) < 4` — pass them through unchanged. Let FuzzyMatcher handle short-name mismatches.
**Warning signs:** Common short street names ("Elm", "Oak", "Lee") being changed in tests.

### Pitfall 4: fuzzystrmatch dmetaphone UTF-8 Warning
**What goes wrong:** `dmetaphone('Café Rd')` or other UTF-8 strings may produce garbled or empty results per PostgreSQL docs ("do not work well with multibyte encodings").
**Why it happens:** dmetaphone's C implementation assumes ASCII.
**How to avoid:** Apply `upper()` on street name before `dmetaphone()` call — US street names are almost entirely ASCII after normalization through scourgify/usaddress. If safety is needed, add `regexp_replace(street_name, '[^\x00-\x7F]', '', 'g')` before passing to dmetaphone. In practice, OA/NAD data is ASCII-normalized.
**Warning signs:** `dmetaphone()` returning empty string for any candidate.

### Pitfall 5: spell_dictionary Not Split Into Individual Words
**What goes wrong:** Storing full street names like "MARTIN LUTHER KING" as dictionary entries means symspellpy won't correct individual word typos like "LTHER" — it only suggests "MARTIN LUTHER KING" as a multi-word suggestion via `lookup_compound()`, not the per-token correction D-02 requires.
**Why it happens:** `lookup()` operates on a single word. Multi-word lookup requires `lookup_compound()`.
**How to avoid:** Extract individual words from street names when populating `spell_dictionary`. Either split street names on spaces and insert each unique word, or use `lookup_compound()` for the full street name string. Given D-02's per-word approach, insert individual tokens.
**Warning signs:** Multi-word street names with typos in the middle word are not corrected.

### Pitfall 6: Confidence Mapping Must Slot Between 0.3 and 0.8
**What goes wrong:** If FuzzyMatcher returns confidence >= 0.8, Phase 14's early-exit optimization (CASC-03) triggers and skips consensus scoring.
**Why it happens:** CASC-03 spec says "if any exact-match provider returns confidence >= 0.80, skip fuzzy." If FuzzyMatcher confidences reach 0.8, they can accidentally trigger early exit in Phase 14.
**How to avoid:** Map similarity range 0.65–1.0 to confidence range 0.50–0.75. A linear mapping: `confidence = 0.50 + (similarity - 0.65) / (1.0 - 0.65) * 0.25` yields max 0.75 at similarity=1.0.
**Warning signs:** Phase 14 tests show fuzzy results triggering early exit.

### Pitfall 7: FuzzyMatcher Called Before Exact Match Fails
**What goes wrong:** If FuzzyMatcher is wired into every geocoding request (not just on NO_MATCH), it runs against large staging tables on every call, violating the "real-time fuzzy matching on every request" out-of-scope ruling in REQUIREMENTS.md.
**Why it happens:** Accidental placement in the normal provider path instead of the fallback path.
**How to avoid:** FuzzyMatcher is NOT a provider in the provider registry. It is called only by the Phase 14 orchestrator after all registered providers return NO_MATCH. This phase just builds the service; Phase 14 wires it in.
**Warning signs:** API response times increase significantly on normal (exact-match) addresses after Phase 13.

---

## Code Examples

### SpellCorrector Class Skeleton
```python
# Source: symspellpy 6.9 API + CONTEXT.md D-01 through D-04
from symspellpy import SymSpell, Verbosity

class SpellCorrector:
    """Offline street-name spell corrector using symspellpy.

    Loaded once at startup with words from spell_dictionary table.
    Per-request cost: O(words_in_street_name) * O(1) lookup.
    """

    def __init__(self, sym_spell: SymSpell) -> None:
        self._sym_spell = sym_spell

    def correct_street_name(self, street_name: str) -> str:
        """Correct each token in street_name. Skip tokens < 4 chars (D-04)."""
        if not street_name:
            return street_name
        tokens = street_name.split()
        corrected = []
        for token in tokens:
            if len(token) < 4:
                corrected.append(token)
                continue
            suggestions = self._sym_spell.lookup(
                token.upper(), Verbosity.TOP, max_edit_distance=2
            )
            corrected.append(suggestions[0].term if suggestions else token)
        return " ".join(corrected)
```

### FuzzyMatcher word_similarity() Query Pattern
```python
# Source: pg_trgm official docs + sqlalchemy 2.0 func API
from sqlalchemy import func, select, union_all, literal_column

# Query all three tables, union results, return top candidates
oa_q = (
    select(
        OpenAddressesPoint.street_name,
        func.word_similarity(input_street, OpenAddressesPoint.street_name).label("score"),
        literal_column("'oa'").label("source"),
    )
    .where(
        func.word_similarity(input_street, OpenAddressesPoint.street_name) >= threshold,
        OpenAddressesPoint.postcode == zip_code,
    )
)
# Similar for nad_q and macon_bibb_q
# Union all three, order by score desc, limit to top N for tiebreak evaluation
```

### dmetaphone() Tiebreaker Pattern (SQL)
```sql
-- Source: fuzzystrmatch 1.2 installed, verified in running DB
SELECT
    candidate_street,
    score,
    dmetaphone(upper(candidate_street)) = dmetaphone(upper(:input_street)) AS phonetic_match,
    dmetaphone_alt(upper(candidate_street)) = dmetaphone_alt(upper(:input_street)) AS phonetic_alt_match
FROM top_candidates
ORDER BY phonetic_match DESC, phonetic_alt_match DESC, score DESC
LIMIT 1;
```

### Confidence Mapping Formula
```python
# Maps word_similarity 0.65–1.0 → confidence 0.50–0.75
# Slots between scourgify (0.3) and exact matches (0.8+) — D-07
FUZZY_CONFIDENCE_MIN = 0.50
FUZZY_CONFIDENCE_MAX = 0.75
FUZZY_SIMILARITY_MIN = 0.65

def similarity_to_confidence(similarity: float) -> float:
    normalized = (similarity - FUZZY_SIMILARITY_MIN) / (1.0 - FUZZY_SIMILARITY_MIN)
    return FUZZY_CONFIDENCE_MIN + normalized * (FUZZY_CONFIDENCE_MAX - FUZZY_CONFIDENCE_MIN)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Exact string match only | pg_trgm trigram similarity + SymSpell edit distance | Phase 13 | Recovers typos before providers, catches near-misses after |
| Provider registry handles all geocoding | Orchestrator + FuzzyMatcher as separate fallback tier | Phase 13/14 split | FuzzyMatcher is not a provider; keeps provider interface clean |
| Static dictionary | DB-backed dictionary rebuilt after every data load | Phase 13 | Dictionary stays current without manual intervention |

**Note:** FUZZ-01 (pg_trgm extension + OA/NAD GIN indexes) was delivered in Phase 12. Phase 13 builds on those indexes — they do not need to be recreated.

---

## Open Questions

1. **Word-level vs phrase-level dictionary population**
   - What we know: D-02 requires per-word correction. `lookup()` operates on single words.
   - What's unclear: Should the dictionary contain individual words (tokens) extracted from street names, or full multi-word street name strings?
   - Recommendation: Populate with individual word tokens. Extract words by splitting each distinct street name on spaces. This directly supports D-02's per-token correction loop. Use `lookup_compound()` only if per-word approach misses multi-word typos during calibration.

2. **Macon-Bibb GIN index: new migration vs extending existing**
   - What we know: Phase 12 migration `f6c3d9e2b5a1` only covered OA and NAD. Claude's Discretion.
   - What's unclear: Whether to add a single new migration covering both the GIN index and spell_dictionary table, or two separate migrations.
   - Recommendation: Single new migration covering both Macon-Bibb GIN index and spell_dictionary table creation. Fewer files; both are Phase 13 additions.

3. **Tiger featnames inclusion in spell_dictionary (SPELL-02)**
   - What we know: SPELL-02 says "supplemented with Tiger `featnames` where available."
   - What's unclear: Tiger featnames live in the `tiger.featnames` table, which requires Tiger data to be loaded. The table may or may not be populated.
   - Recommendation: `rebuild_dictionary()` should query Tiger featnames with `IF EXISTS` guard or a try/except. The function should not fail if Tiger data is absent — it should silently skip it. This makes SPELL-02 "best effort" on Tiger.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL pg_trgm | FuzzyMatcher word_similarity() | ✓ | 1.6 | — |
| PostgreSQL fuzzystrmatch | dmetaphone() tiebreaker | ✓ | 1.2 | — |
| symspellpy | SpellCorrector | ✗ (not in pyproject.toml) | — | Wave 0: `uv add symspellpy>=6.9.0` |
| pytest-asyncio | All new async tests | ✓ | 1.3.0 | — |
| Docker DB (geo-api-db-1) | Integration tests | ✓ | PostGIS 17-3.5 | — |

**Missing dependencies with no fallback:**
- symspellpy — must be added to pyproject.toml before any implementation begins

**Missing dependencies with fallback:**
- None

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `uv run pytest tests/test_spell_corrector.py tests/test_fuzzy_matcher.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPELL-01 | Street name token corrected, house number/zip unchanged | unit | `uv run pytest tests/test_spell_corrector.py -x` | ❌ Wave 0 |
| SPELL-01 | Short street names (< 4 chars) pass through uncorrected | unit | `uv run pytest tests/test_spell_corrector.py::test_short_token_passthrough -x` | ❌ Wave 0 |
| SPELL-02 | Dictionary built from OA/NAD/Macon-Bibb street names | unit (mock DB) | `uv run pytest tests/test_spell_corrector.py::test_rebuild_dictionary -x` | ❌ Wave 0 |
| SPELL-03 | rebuild_dictionary() called after load-oa, load-nad, gis import | unit (CLI mock) | `uv run pytest tests/test_spell_corrector.py::test_rebuild_triggered_after_cli -x` | ❌ Wave 0 |
| FUZZ-02 | word_similarity() returns candidate above 0.65 threshold | unit (mock session) | `uv run pytest tests/test_fuzzy_matcher.py::test_fuzzy_above_threshold -x` | ❌ Wave 0 |
| FUZZ-02 | NO_MATCH returned when best similarity < 0.65 | unit (mock session) | `uv run pytest tests/test_fuzzy_matcher.py::test_fuzzy_below_threshold -x` | ❌ Wave 0 |
| FUZZ-03 | dmetaphone tiebreaker selects phonetically closest when scores within 0.05 | unit (mock session) | `uv run pytest tests/test_fuzzy_matcher.py::test_dmetaphone_tiebreaker -x` | ❌ Wave 0 |
| FUZZ-04 | 30-address calibration corpus: all thresholds pass | integration (requires DB) | `uv run pytest tests/test_fuzzy_calibration.py -x -m "not tiger"` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_spell_corrector.py tests/test_fuzzy_matcher.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green (392 + new tests) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_spell_corrector.py` — covers SPELL-01, SPELL-02, SPELL-03
- [ ] `tests/test_fuzzy_matcher.py` — covers FUZZ-02, FUZZ-03
- [ ] `tests/test_fuzzy_calibration.py` — covers FUZZ-04 (30-address corpus)
- [ ] symspellpy install: `uv add symspellpy>=6.9.0` — required before any tests can run

---

## Sources

### Primary (HIGH confidence)
- symspellpy GitHub source `symspellpy/symspellpy.py` — SymSpell constructor, `create_dictionary_entry()`, `lookup()`, `lookup_compound()`, SuggestItem, Verbosity enum
- symspellpy GitHub `docs/examples/dictionary.rst` — `load_dictionary()` and `create_dictionary_entry()` examples
- PostgreSQL 17 official docs `https://www.postgresql.org/docs/17/pgtrgm.html` — `word_similarity()` function signature, GIN index usage, threshold parameter, operator `<%`
- PostgreSQL 17 official docs `https://www.postgresql.org/docs/17/fuzzystrmatch.html` — `dmetaphone()`, `dmetaphone_alt()` signatures, multibyte encoding caveat
- PyPI `https://pypi.org/pypi/symspellpy/json` — version 6.9.0 confirmed as of 2026-03-29
- Codebase inspection — `alembic/versions/f6c3d9e2b5a1_add_pg_trgm_gin_indexes.py`, `providers/openaddresses.py`, `scripts/20_tiger_setup.sh`, `main.py`, `services/geocoding.py`
- Live DB verification — `docker compose exec db psql` confirmed `pg_trgm 1.6` and `fuzzystrmatch 1.2` installed

### Secondary (MEDIUM confidence)
- WebSearch results for symspellpy usage patterns — multiple sources agree on `create_dictionary_entry(word, count)` and `Verbosity.TOP` for single-best-match
- WebSearch results for pg_trgm `word_similarity()` threshold usage — confirmed default threshold 0.6, custom threshold via `pg_trgm.word_similarity_threshold` GUC

### Tertiary (LOW confidence)
- None — all critical claims verified with primary sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — symspellpy version confirmed from PyPI; pg_trgm and fuzzystrmatch verified installed in live DB
- Architecture: HIGH — patterns derived directly from existing codebase (services/geocoding.py, providers/openaddresses.py, alembic migration patterns)
- Pitfalls: HIGH — most pitfalls verified against official docs (word_similarity argument order from pg_trgm docs, dmetaphone UTF-8 caveat from fuzzystrmatch docs, SymSpell D-04 behavior from symspellpy API)

**Research date:** 2026-03-29
**Valid until:** 2026-06-29 (stable libraries; pg_trgm and fuzzystrmatch are PostgreSQL built-ins with no breaking changes expected)
