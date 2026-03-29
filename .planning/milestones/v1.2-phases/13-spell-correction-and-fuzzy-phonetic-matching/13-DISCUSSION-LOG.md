# Phase 13: Spell Correction and Fuzzy/Phonetic Matching - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 13-spell-correction-and-fuzzy-phonetic-matching
**Areas discussed:** Spell correction behavior, FuzzyMatcher architecture, Dictionary lifecycle, Fuzzy/phonetic fallback strategy

---

## Spell Correction Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Max distance 2 | Catches single and double typos. Industry standard for address correction. Low false-positive risk for street names >= 4 chars. | ✓ |
| Max distance 1 | Conservative — only single-character typos. Misses 'Mrccer' (2 errors). | |
| You decide | Claude picks based on calibration. | |

**User's choice:** Max distance 2
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Correct each word independently | Split on spaces, correct each token, rejoin. Handles 'Maartin Lther King'→'Martin Luther King'. | ✓ |
| Correct as whole phrase | Treat entire street name as one lookup. Requires compound entries. | |
| You decide | Claude picks based on dictionary structure. | |

**User's choice:** Correct each word independently
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Top candidate only | Use best-scoring correction and proceed. If it fails, fuzzy matching catches the rest. | ✓ |
| Try top 2-3 candidates | Run exact match against top candidates in parallel. Higher hit rate but more complexity. | |
| You decide | Claude picks based on performance trade-offs. | |

**User's choice:** Top candidate only
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Skip correction for < 4 chars | Short names have too many edit-distance neighbors. Pass through uncorrected. | ✓ |
| Correct all lengths | Correct everything, rely on dictionary frequency. Risk: more false corrections. | |
| You decide | Claude picks based on dictionary analysis. | |

**User's choice:** Skip correction for < 4 chars
**Notes:** None

---

## FuzzyMatcher Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| New service class | services/fuzzy.py with FuzzyMatcher class. Called by Phase 14 orchestrator after exact match fails. | ✓ |
| Extension of existing providers | Add fuzzy_geocode() methods to OA and NAD providers. Keeps data access co-located. | |
| You decide | Claude picks based on cleanest integration. | |

**User's choice:** New service class
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| OA + NAD only | These have GIN trigram indexes from Phase 12. Macon-Bibb is subset of OA. | |
| All local tables | Include Macon-Bibb staging table too. More coverage. | ✓ |
| You decide | Claude decides based on data overlap analysis. | |

**User's choice:** All local tables
**Notes:** Macon-Bibb will need its own GIN trigram index added

| Option | Description | Selected |
|--------|-------------|----------|
| Scale with similarity score | Map word_similarity() (0.65–1.0) to confidence (0.50–0.75). Slots between scourgify (0.3) and exact matches (0.8+). | ✓ |
| Fixed confidence (e.g., 0.5) | All fuzzy matches get same confidence. Simpler but less informative. | |
| You decide | Claude picks for Phase 14 consensus scoring. | |

**User's choice:** Scale with similarity score
**Notes:** None

---

## Dictionary Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| On-disk file, loaded at startup | CLI writes dictionary.txt. Workers load at startup. Simple. | |
| Database table | Store in PostgreSQL table. Workers query at startup. Centralized. | ✓ |
| You decide | Claude picks based on simplicity and performance. | |

**User's choice:** Database table
**Notes:** Clarified in follow-up: workers load DB table into in-memory SymSpell object at startup (one query, then in-memory for all requests)

| Option | Description | Selected |
|--------|-------------|----------|
| CLI rebuilds after each import | Shared rebuild_dictionary() at the end of CLI commands. | |
| Separate CLI command | New 'rebuild-dictionary' command. | |
| Both — auto + manual | Auto-rebuild after imports AND standalone command. | ✓ |

**User's choice:** Both — auto + manual
**Notes:** None

---

## Fuzzy/Phonetic Fallback Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Trigram first, Metaphone tiebreaker | word_similarity() first. If top candidate clearly best, use it. If ambiguous, dmetaphone() picks closest. | ✓ |
| Both in parallel, combine scores | Run both simultaneously, weight-combine. More robust but more complex. | |
| You decide | Claude picks based on calibration results. | |

**User's choice:** Trigram first, Metaphone tiebreaker
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| 0.65 minimum | Per FUZZ-02 range. Starting at 0.65 catches more candidates. | ✓ |
| 0.70 minimum | More conservative — fewer false positives. | |
| You decide | Claude sets based on calibration. | |

**User's choice:** 0.65 minimum
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Best match only | Single best candidate. Simpler for Phase 14 orchestrator. | ✓ |
| Top 3 candidates | Up to 3 ranked candidates. Higher hit rate but more complexity. | |
| You decide | Claude picks based on orchestrator needs. | |

**User's choice:** Best match only
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Automated test suite | pytest tests against Issue #1's 4 addresses + generated addresses. Thresholds asserted in CI. | ✓ |
| One-time analysis, hardcode results | Analyze manually, set thresholds, document rationale. | |
| You decide | Claude picks based on project testing patterns. | |

**User's choice:** Automated test suite with 30 addresses
**Notes:** User wants Issue #1's 4 known addresses plus 26 generated addresses — mix of real addresses, fake addresses, and varying levels of mistakes. Significant expansion beyond original FUZZ-04's 4-address corpus.

---

## Claude's Discretion

- Alembic migration strategy for Macon-Bibb GIN index
- fuzzystrmatch extension enablement approach
- SymSpell loading pattern (startup hook vs lazy init)
- spell_dictionary table schema
- Confidence mapping formula
- Test address generation (geographic distribution, error types)

## Deferred Ideas

None — discussion stayed within phase scope
