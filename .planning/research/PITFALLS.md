# Pitfalls Research

**Domain:** Cascading Address Resolution — Fuzzy Matching, Spell Correction, LLM Correction, Consensus Scoring
**Project:** CivPulse Geo API
**Researched:** 2026-03-29 (v1.2 milestone — Cascading Address Resolution)
**Confidence:** HIGH for structural pitfalls (drawn from existing codebase + known Issue #1 defects); MEDIUM for LLM-specific claims (web-verified via GDELT research + structured output literature); MEDIUM for threshold recommendations (pg_trgm docs verified, address-specific calibration empirical)

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or systemic reliability failures.

---

### Pitfall 1: Fuzzy Matching Threshold Too Low — Street Name Cross-Match

**What goes wrong:**
The pg_trgm similarity threshold is left at its default (0.3) or set too low for address matching. "MAIN ST" matches "MAIN AVE" at similarity ~0.53. "PINE ST" matches "PINE BLVD" at ~0.57. "OAK DR" matches "OAK CT" at ~0.62. All of these are geographically distinct streets, but all would pass a 0.5 threshold. In a dense grid neighborhood (e.g., Macon downtown with CHERRY ST, CHERRY LN, CHERRY WAY all one block apart), the wrong match is returned with high apparent confidence.

**Why it happens:**
pg_trgm's similarity score measures character overlap, not address semantics. Street names share a large trigram vocabulary. The default threshold of 0.3 was designed for search autocomplete (where false positives are acceptable), not for geocoding (where a false positive means a wrong building on the wrong street). Developers test against a small dataset where no two street names are similar, then deploy into production data where dozens of similar names exist.

**How to avoid:**
- Apply fuzzy matching **per field, not per full address string**. Match `street_name` to `street_name` separately from `street_suffix`.
- For `street_name` field: threshold >= 0.7 (HIGH). Below this, trigram similarity between common street names is too noisy.
- For `street_suffix` field: require exact match or a controlled synonym table (`ST` = `STREET`, `AVE` = `AVENUE`). Never apply trigram similarity to suffix alone — `ST` and `CT` have similarity 0.67 but are completely different suffix types.
- For the full normalized address: threshold >= 0.8 is the floor for considering a result valid. At 0.6–0.8, return as a low-confidence candidate only, never auto-promote to official.
- Never apply a single threshold to the full address string including street number — the house number dominates trigram score and obscures street name divergence.
- Log the raw similarity score on every fuzzy match so threshold tuning has empirical data.

**Warning signs:**
- Fuzzy match returns a result 2+ blocks from the expected location.
- Two different input addresses resolve to the same coordinates via the fuzzy path.
- Test addresses with similar street names (CHERRY ST vs CHERRY LN) return wrong-street results.

**Phase to address:** Fuzzy/phonetic matching phase (Phase 3 or equivalent). Threshold values must be established with a test corpus before any auto-promotion logic is wired up.

---

### Pitfall 2: Fuzzy Matching Threshold Too High — Zero Improvement Over Exact Match

**What goes wrong:**
The threshold is set conservatively at 0.9 or 0.95 to avoid false positives. The fuzzy match stage catches zero additional addresses beyond what exact matching already found. The cascade proceeds to the LLM stage for every typo, which is 100x slower and more expensive. The fuzzy stage adds latency (pg_trgm index scan) with no benefit.

**Why it happens:**
Developers set a high threshold to be "safe," without testing against the actual degraded-input patterns observed in production (truncated zips, one-character typos, missing directionals). A threshold that catches `CHERERY ST` for `CHERRY ST` is around 0.72 — well below the "safe" 0.9 level.

**How to avoid:**
- Test the threshold against the known-bad input set from E2E testing (Issue #1) before wiring up downstream stages. If fuzzy matching with a given threshold catches 0 additional addresses over exact matching on that test set, the threshold is too high.
- For one-character typos in street names (the most common human error): typical similarity is 0.65–0.80 depending on name length. Shorter names require lower thresholds.
- For truncated zip codes (Issue #1 defect): do not use trigram similarity on zip codes. Use prefix matching (`zip_code LIKE '3120%'`) instead — trigram similarity on 5-digit numbers is not meaningful.
- Threshold recommendation: Start at 0.75 for street_name field. Measure false positive and false negative rate against the E2E test suite. Adjust incrementally in 0.05 steps.

**Warning signs:**
- Fuzzy match stage reports 0% improvement over exact match on any test dataset.
- Every degraded-input address falls through to the LLM stage.

**Phase to address:** Fuzzy/phonetic matching phase, immediately after exact-match baseline is established.

---

### Pitfall 3: Spell Correction Library "Corrects" Valid Street Names

**What goes wrong:**
A general-purpose spell correction library (pyspellchecker, TextBlob, symspell with default dictionary) is applied to the full address string. Street names are proper nouns not in the English dictionary. "MERCER" gets corrected to "MERCY". "VINEVILLE" gets corrected to "VINEVILLE" (safe) or "VINE VILLE" (wrong). "PIO NONO AVE" gets corrected to "PIANO NONO AVE". "LANEY WALKER BLVD" gets corrected to "LANEY WALKER BLVD" (safe) or "LANE WALKER BLVD" (wrong — "LANEY" is a person's name on the street sign). Corrections are applied silently with no audit trail.

**Why it happens:**
Spell correction libraries are trained on prose text. Every word in an address is treated as a potential misspelling of an English word. Street names derived from proper nouns, historical figures, geographic features, or local vocabulary are systematically at risk. The library has no concept of "this token is a street name, not a word."

**How to avoid:**
- Apply spell correction **only to the free-text input fields** (the original user input), not to the already-normalized USPS form.
- Apply spell correction **before** address parsing, not after. The correction should produce a more parseable string, not modify already-parsed components.
- Protect proper noun tokens: run spell correction only on tokens that fail both the USPS abbreviation dictionary and a local street name lookup. If a token exists in `tiger_data.featnames` or the OpenAddresses street name index, do not correct it.
- Use symspell or a domain-specific word frequency list, not textblob/pyspellchecker — symspell allows adding proper nouns to the dictionary to prevent correction. Load your local street name index into the custom dictionary at startup.
- After correction, always log `(original: "CHERERY ST") → (corrected: "CHERRY ST")` at DEBUG level. Never apply a correction silently.
- Maintain a correction audit trail: store `original_input` (already done), `spell_corrected_input`, and `canonical_normalized` as separate fields so corrections are traceable.
- Treat corrections as candidates, not authoritative changes: if the corrected form still fails exact match and fuzzy match, abandon the correction and proceed with original input.

**Warning signs:**
- Spell correction changes a token that was already valid (confirmed by looking it up in a street name index).
- Corrected addresses have a lower match rate than uncorrected addresses.
- Street names in the local dataset (e.g., "LANEY WALKER") appear mangled in correction output.

**Phase to address:** Spell correction phase (Phase 2 or equivalent). Must include a street name dictionary built from local data before any correction is applied.

---

### Pitfall 4: LLM Sidecar Hallucinating Plausible-But-Wrong Addresses

**What goes wrong:**
The LLM sidecar is given a degraded address input (`"123 Cherery St, Macin, GA 31201"`) and returns a corrected form (`"123 Cherry St, Macon, GA 31201"`) that looks correct but references a real street that exists in a different city or a different part of the city. The LLM draws on training-data frequency for street name suggestions rather than local address data. In rural counties, the LLM has no training data representation, so it hallucinates coordinates for a plausible-sounding nearby city. Geocodio research documents that LLMs "confidently assert" cities that weren't mentioned and return coordinates with >200km average error on rural addresses.

**Why it happens:**
LLMs are trained on web text, which over-represents urban areas and common street name patterns. The model generates what is statistically likely from training data, not what exists in the local dataset. Temperature > 0 introduces non-determinism — the same bad address can produce different hallucinated corrections on repeated calls. The model has no mechanism to verify that a suggested address actually exists in the PostGIS database.

**How to avoid:**
- **Treat LLM output as a parse suggestion, not a geocoded result.** The LLM's job is to return structured fields (`street_number`, `street_name`, `street_suffix`, `city`, `state`, `zip`), not coordinates.
- **Always re-verify LLM output against the database.** After the LLM returns a corrected form, run that form through the full exact match + fuzzy match pipeline. If it still produces no match, discard the LLM correction. The LLM is not the last word.
- **Use structured output (JSON schema) to constrain the LLM response.** Grammar-constrained generation (via Ollama structured output or similar) prevents the model from returning free-text explanations or fabricating fields. Define a strict Pydantic schema: `AddressCorrectionResult(street_number: str, street_name: str, street_suffix: str, city: str, state: str, zip_code: str, correction_notes: str)`.
- **Set temperature to 0.** Deterministic output is required for a geocoding pipeline. Temperature > 0 makes the same input produce different corrections on repeated calls, which is untestable.
- **Never auto-set OfficialGeocoding from an LLM-suggested correction alone.** LLM corrections require at least one confirming match from a database provider before any official record is written.
- **Log the full prompt and response for every LLM call** at DEBUG level. This is the only way to audit what the model produced vs. what was accepted.
- **Reject LLM corrections that change the state or produce a zip code inconsistent with the state.** These are hard hallucination signals — e.g., returning a GA zip for a correction that suddenly specifies AL.

**Warning signs:**
- LLM-corrected address returns coordinates far from the input address's approximate area (>5 miles for urban, >15 miles for rural).
- The LLM suggests a street name that exists in another city but not in the input address's city.
- LLM correction changes the state code or produces a zip that doesn't match the state.
- Repeated calls to the LLM sidecar with the same input return different corrections.

**Phase to address:** LLM sidecar phase (Phase 4 or equivalent). Must include post-LLM database verification as a hard gate before any result is used.

---

### Pitfall 5: Consensus Scoring Where All Providers Are Wrong the Same Way

**What goes wrong:**
All providers (Census, Tiger, OpenAddresses, NAD) share the same underlying TIGER/LINE reference data at their core. A new subdivision that isn't in the Census Tiger data will be missed by all providers simultaneously. The consensus algorithm sees perfect agreement (all four providers return the same coordinates or all return NO_MATCH for a new address) and interprets agreement as high confidence. The system confidently sets the wrong official record — or fails to set any record for a real address that exists on the ground.

**Why it happens:**
Consensus scoring assumes providers are independent. In practice, local providers all use Census Tiger data as their geographic backbone. OpenAddresses aggregates from local government sources (which themselves may be wrong or stale). When the underlying reference data has a systemic error — a wrong-county centroid (Issue #1 Tiger 50% error rate), a new subdivision not yet in any database, or a renamed street — all providers inherit the same error. Agreement among providers that share data lineage is not the same as independent corroboration.

**How to avoid:**
- **Do not treat provider agreement alone as sufficient for high confidence.** Require spatial plausibility: the consensus coordinates must fall within the county/city boundary implied by the address's zip code and city name. Use `ST_Within(point, county_boundary)` as a hard sanity check on the final consensus result.
- **Weight providers by independence, not just agreement count.** Census Geocoder and Tiger are both Census-sourced — their agreement is 1 vote, not 2. OpenAddresses (local government source) + NAD (DOT-compiled) + Macon-Bibb GIS (county-specific) each represent genuinely independent data lineages when they agree.
- **For the Tiger wrong-county bug (Issue #1):** Tiger's `geocode()` function sometimes returns coordinates that are in the right city but the wrong county polygon. Post-filter all Tiger results with `ST_Within(result_point, expected_county_boundary)` before accepting the result. This is the county disambiguation fix required by the milestone.
- **Flag consensus agreement at confidence 1.0 for addresses where spatial plausibility check fails.** If all providers agree on coordinates that fall outside the expected county, mark that result as `needs_review` rather than auto-promoting to official.
- **Maintain a minimum dissent threshold.** If one provider disagrees by more than 500m from the consensus centroid, do not auto-set official — require admin review. Silent minority dissent often indicates a systemic data problem.

**Warning signs:**
- The consensus result coordinates fall in a different county than the address's stated county.
- All local providers return the same coordinates — verify at least one is from an independent data source.
- Confidence score is 1.0 but ST_Within check against expected county boundary fails.
- New subdivision addresses all return NO_MATCH with consensus confidence 1.0 (unanimous miss).

**Phase to address:** Consensus scoring phase (Phase 5 or equivalent) and Tiger county disambiguation (Phase 1 fix, as it affects all downstream stages).

---

### Pitfall 6: Cascading Pipeline Latency Explosion

**What goes wrong:**
Each stage of the cascade (normalize → spell-correct → exact match → fuzzy match → LLM correction → re-match → consensus score) adds latency sequentially. A pipeline with no timeouts or early-exit conditions runs all stages for every address. The LLM sidecar alone may take 2–10 seconds per address on a CPU-only local model. Combined with pg_trgm index scans, multiple provider calls, and consensus scoring, a single degraded address can take 15–30 seconds to resolve. Batch operations become unusable. The existing API timeout budget is exceeded.

**Why it happens:**
Each stage is developed and tested in isolation where it appears fast enough. Integration testing of the full cascade is deferred until all stages are built. By then, the latency is baked into the architecture.

**How to avoid:**
- **Define a total latency budget before implementing any stage.** Suggested budget: single address 3s P95, batch per-item 5s P95. Every stage must fit within its share.
- **Implement early exit conditions.** If exact match returns confidence >= 0.95, skip fuzzy match, skip LLM, skip re-match. Return immediately. The cascade should be a fallback tree, not a mandatory pipeline.
- **Gate the LLM stage behind a trigger threshold.** Only call the LLM sidecar when: (a) exact match returns confidence 0.0, AND (b) fuzzy match returns confidence < 0.6. An address that fuzzy-matches at 0.75 does not need LLM correction.
- **Per-stage timeouts.** LLM sidecar: 5s timeout, then skip and proceed with best available non-LLM result. pg_trgm query: 500ms timeout via `statement_timeout`. Provider calls: existing httpx timeout budget.
- **Async stage execution where possible.** Multiple local provider lookups (OA, NAD, Tiger) can run concurrently with `asyncio.gather()` rather than serially. This already partially exists in the codebase — ensure the cascade does not serialize what can be parallelized.
- **Measure stage latency in integration tests.** Build a latency regression test that fails if a single-address cascade exceeds 3s P95 on the local Docker environment.

**Warning signs:**
- A single degraded address takes >5s to return from the API.
- Batch of 100 addresses times out at the nginx/uvicorn layer.
- LLM stage is called for addresses that already have a high-confidence fuzzy match.
- Provider calls are serialized (sequential await) when they could be concurrent.

**Phase to address:** Cascade integration phase (the phase that wires all stages together). Latency budget must be defined in that phase's success criteria before any stage is considered complete.

---

### Pitfall 7: Cascade Confidently Auto-Sets Wrong Official Records at Scale

**What goes wrong:**
The pipeline is deployed with auto-set OfficialGeocoding enabled. It processes a batch of 5,000 addresses from a voter registration import. Tiger's 50% error rate (Issue #1 wrong-county bug) means ~2,500 addresses get wrong-county coordinates auto-set as official. These records are used downstream by run-api and vote-api to assign voters to districts. The wrong-county coordinates place some voters in the wrong polling precinct. Undoing the damage requires: identifying which records were auto-set from bad Tiger results, running a corrective batch, and committing the replacements — all while the downstream systems may have already consumed the bad data.

**Why it happens:**
The `ON CONFLICT DO NOTHING` pattern in the existing `GeocodingService` (line 219) means the first auto-set result wins and is never overwritten by the cascade. If the Tiger result is first in the pipeline and it's wrong, it gets locked in. At scale, the audit trail for "which result did the cascade auto-set, and why" is absent — the `official_geocodings` table only records the `geocoding_result_id`, not the cascade metadata (which stage set it, what confidence, what alternatives existed).

**How to avoid:**
- **Do not enable cascade auto-set for the first batch import without a dry-run mode.** Implement a `dry_run=True` flag in the cascade that computes and logs the would-be official result for each address without writing it. Review the dry-run output before enabling auto-set.
- **The Tiger county disambiguation fix (Issue #1) must be completed before any cascade that uses Tiger results is allowed to auto-set official records.** This is a hard gate — not a recommendation.
- **Store cascade metadata on every auto-set decision.** At minimum: `set_by_stage` (which stage provided the winning result), `winning_confidence`, `alternatives_considered` (count and confidence range of other candidates). This audit data enables bulk rollback queries.
- **Implement a minimum confidence threshold for auto-set.** Do not auto-set OfficialGeocoding unless the winning result has confidence >= 0.8 AND passes the spatial plausibility check (ST_Within expected county). Results below this threshold should be written to a `pending_review` queue, not auto-promoted.
- **Implement a bulk rollback capability before the first production cascade run.** SQL: `DELETE FROM official_geocodings WHERE address_id IN (SELECT address_id FROM official_geocodings og JOIN geocoding_results gr ON og.geocoding_result_id = gr.id WHERE gr.provider_name = 'tiger' AND og.set_by_stage = 'cascade_auto')`. This query is impossible without the `set_by_stage` audit field.
- **For the `ON CONFLICT DO NOTHING` behavior**: change to `ON CONFLICT DO UPDATE` in the cascade auto-set path, but only if the new result has higher confidence than the existing official. This prevents the first-result-wins problem.

**Warning signs:**
- Official geocoding records set by cascade have no metadata about which stage produced them.
- Tiger is the first provider in the cascade execution order and auto-set is enabled before the county disambiguation fix is deployed.
- Downstream systems (run-api, vote-api) have already consumed official coordinates before a cascade dry-run was reviewed.
- `official_geocodings` table has no `set_by_stage` or `cascade_confidence` columns.

**Phase to address:** Two phases: (1) Tiger county disambiguation fix must be Phase 1. (2) Cascade auto-set mechanism must include audit metadata and dry-run mode before any production batch is allowed.

---

### Pitfall 8: Validation Confidence Semantic Mismatch — Structural Parse vs. Address-Verified

**What goes wrong:**
`scourgify` and Tiger both return `confidence=1.0` for addresses that parse cleanly into USPS components. This `confidence=1.0` propagates into the consensus scoring algorithm, making those results appear authoritative. But `confidence=1.0` means "this address is structurally valid USPS format," not "this address exists and has been verified against a delivery database." The cascade treats high structural confidence as high factual confidence and auto-sets official records for addresses that are syntactically well-formed but geographically wrong (Issue #1 defect #4).

**Why it happens:**
The existing `GeocodingResult.confidence` field conflates two distinct concepts: (a) parse quality (did the address parse into components?) and (b) geocoding quality (did the geocoder find this address in its reference data?). `scourgify`'s job is (a); Tiger's job is (b). Both currently report via the same confidence float, and downstream logic cannot distinguish them.

**How to avoid:**
- Add a `result_type` or `confidence_basis` field to `GeocodingResult` that distinguishes `STRUCTURAL_PARSE` (scourgify-style) from `GEOCODED_MATCH` (Tiger/OA/NAD-style) from `FUZZY_MATCH` from `LLM_SUGGESTION`.
- In the consensus scoring algorithm, only `GEOCODED_MATCH` and `FUZZY_MATCH` results contribute to the spatial consensus calculation. `STRUCTURAL_PARSE` results contribute only to normalization quality, not to coordinate selection.
- Never auto-set OfficialGeocoding from a `STRUCTURAL_PARSE` result alone, regardless of confidence score.
- This is the validation confidence semantics fix already listed in the milestone requirements — it must be implemented before consensus scoring is built, or the consensus algorithm will be built on a corrupted confidence scale.

**Warning signs:**
- `scourgify` provider returns `confidence=1.0` for an address that has no matching coordinates in any spatial provider.
- Consensus score for an address with no spatial match is high because scourgify and Tiger normalization both report 1.0.
- The `confidence` field does not distinguish between parse quality and geocode quality anywhere in the codebase.

**Phase to address:** Confidence semantics fix — must be Phase 1 (before fuzzy match, LLM, or consensus scoring are built). All downstream stages depend on correctly-typed confidence scores.

---

### Pitfall 9: Street Name Normalization Mismatch With Multi-Word Suffixes

**What goes wrong:**
The existing normalization pipeline (Issue #1 defect #5) fails to correctly normalize multi-word street name suffixes. "LANEY WALKER BLVD" may be stored in the OA dataset as "LANEY WALKER BLVD" but the normalization produces "LANEY WALKER BOULEVARD" or "LANEY WALKER BL". The fuzzy match is then comparing "LANEY WALKER BL" against "LANEY WALKER BLVD" — a similarity of ~0.82, which may pass the threshold, but introduces a match-quality penalty for a known-valid address.

**Why it happens:**
USPS abbreviation tables handle single-word suffixes. "LANEY WALKER" is the street name (a two-token proper noun); "BLVD" is the suffix. But the normalization code may treat "WALKER BLVD" as a compound token and abbreviate "WALKER" incorrectly, or fail to locate the suffix boundary when the street name contains a word that also appears in the suffix table (e.g., "WALKER" is not a suffix, but "COURT" is — a street named "TENNIS COURT DR" requires recognizing that "COURT" is part of the name, not the suffix).

**How to avoid:**
- Apply USPS abbreviation normalization **right-to-left**: find the last token that is a valid suffix abbreviation, treat everything to the left as the street name. Do not apply suffix normalization to any token that is not the terminal suffix.
- For the specific multi-word case: the Tiger `normalize_address()` function can serve as ground truth for how a given street should be decomposed. Compare the local normalization result against Tiger normalization during the suffix mismatch fix phase.
- Build a regression test using the known-failing multi-word suffix cases from Issue #1 before attempting any fix — the test must fail before the fix and pass after.

**Warning signs:**
- Normalized address has a suffix that is a partial abbreviation ("BL" instead of "BLVD").
- Known-valid street names from the local dataset return NO_MATCH after normalization.
- Street names containing a word that is also a USPS suffix keyword (COURT, PARK, GROVE, PLACE) are normalized incorrectly.

**Phase to address:** Normalization mismatch fix — Phase 1, before fuzzy matching is implemented. The fuzzy match quality depends on both sides of the comparison being normalized consistently.

---

### Pitfall 10: Zip Prefix Fallback Matching Wrong City in Same Prefix Zone

**What goes wrong:**
Zip prefix fallback is implemented as `WHERE zip_code LIKE '3120%'` (e.g., for a truncated input of `"3120"`). This matches all zips starting with `3120`: `31201`, `31202`, `31203`, `31204`, `31206`, `31207`, `31210`, `31216`, `31220`. In the Macon-Bibb area, these zips span multiple distinct neighborhoods. A street name that exists only in `31201` might match a record from `31210` under prefix fallback, returning the wrong block-level location. The match appears plausible — same city, same first-four digits — but is off by several miles.

**Why it happens:**
Zip prefix fallback is designed to recover from truncated input. But a 4-digit prefix in a dense metropolitan zip zone covers enough geography that a street name match may be on the wrong side of the city. The fallback treats all prefix-matching records as equally plausible, with no spatial distance weighting.

**How to avoid:**
- Zip prefix fallback should only be attempted when the street + house number match is otherwise unambiguous. If the street name + house number appear in multiple prefix-matching zips, do not auto-select — return all candidates with their distinct zip codes and let consensus scoring (or admin) resolve.
- Weight prefix-fallback candidates by ascending zip-code distance from the truncated input (i.e., `31201` is a better fallback for `3120` than `31220`).
- Limit prefix fallback to the first 4 digits of the input (not 3 or fewer) — a 3-digit prefix covers too wide a geographic area.
- Never auto-set OfficialGeocoding from a zip-prefix-fallback result without at least one confirming provider that returned the full 5-digit match.

**Warning signs:**
- Prefix fallback returns multiple candidates from different neighborhoods.
- The fallback match is more than 2 miles from the expected location.
- Input zip has fewer than 4 digits — fallback should be blocked entirely for input shorter than 4 digits.

**Phase to address:** Zip prefix fallback fix (Phase 1 fix for the truncated zip Issue #1 defect). Must include multi-candidate handling before single-result selection is implemented.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single `confidence` float for all result types | Simple schema | Consensus scoring cannot distinguish parse quality from geocode quality — produces wrong official records | Never for v1.2 — fix before consensus |
| pg_trgm similarity applied to full address string | One query instead of per-field queries | House number dominates the score; street name divergence is masked | Never for address geocoding |
| Default pg_trgm threshold (0.3) | No config required | Returns cross-street false positives in dense street grids | Never — calibrate against test corpus |
| LLM result used directly without database re-verification | Simpler pipeline | LLM hallucinations propagate to official records | Never for auto-set path |
| ON CONFLICT DO NOTHING for cascade auto-set | Existing first result preserved | First-result-wins locks in bad Tiger results; no upgrade path | Only if Tiger county bug is already fixed |
| Cascade auto-set without dry-run mode | Faster to implement | First production run at scale locks in errors that are hard to audit | Never — always ship dry-run first |
| Spell correction applied to already-normalized address | Catch "residual" typos | Corrects valid USPS abbreviations (AVE → "ave" is "safe", but "ST" might be corrected to "SIT") | Never — correct pre-normalization only |
| Serialize all cascade stages sequentially | Simpler code | LLM sidecar + multiple providers adds >15s for degraded addresses | Acceptable in Phase 1 prototype; must parallelize before production batch |

---

## Integration Gotchas

Common mistakes when connecting existing pipeline to new cascade stages.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pg_trgm + existing `canonical_key()` | Apply trigram search against raw input instead of normalized form | Normalize both query and dataset before trigram comparison — index normalized_address in addresses table |
| Tiger county disambiguation | Add ST_Within check inside the Tiger provider | Add as a post-provider filter in the cascade layer, not inside the provider — providers should return raw results; the cascade layer handles filtering |
| LLM sidecar + GeocodingService | Call LLM inside the existing provider ABC | LLM is a pipeline stage, not a provider — it produces a corrected input string, then the corrected input re-enters the existing provider pipeline |
| Consensus scoring + `local_results` | Score local results the same as cached remote results | Local results are ephemeral (no DB row) — consensus logic must handle the case where a result has no `geocoding_result_id` |
| Spell correction + `canonical_key()` | Apply spell correction after `canonical_key()` | Spell correction must happen before `canonical_key()` — the canonical key is derived from the post-correction normalized form |
| Fuzzy match + NAD bulk COPY table | Run trigram search against the full NAD table (80M rows) | pg_trgm index must be created on the staging table before fuzzy queries are enabled; unindexed trigram search on 80M rows is unusably slow |
| Cascade auto-set + existing `ON CONFLICT DO NOTHING` | Reuse existing auto-set logic | Cascade auto-set needs a conditional update path (higher confidence wins), not the existing first-writer-wins logic |
| Zip prefix fallback + exact match cache | Prefix-matched results cache-keyed by truncated zip | Do not cache prefix-fallback results under the truncated zip key — cache under the resolved full zip, or do not cache at all |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Serial cascade for batch operations | Batch of 100 addresses takes >5 min | `asyncio.gather()` for concurrent provider calls; async cascade with per-item early exit | First batch import >50 items |
| pg_trgm on unindexed NAD table | Fuzzy query takes >30s per address | `CREATE INDEX ON nad_addresses USING GIN (normalized_street gin_trgm_ops)` | Any query on NAD without GIN index |
| LLM sidecar called for every address | Throughput collapses to LLM speed (5-10s/address) | Gate LLM on confidence threshold — only call when fuzzy match fails | First production batch load |
| Consensus scoring loads all provider results per address | N+1 query pattern in consensus calculation | Single query joining all results for a batch; not per-address | Batch sizes >200 |
| Spell correction on every address including already-clean inputs | Latency added to all requests | Short-circuit if address parses cleanly on first attempt | Measurable at >50 req/s |
| Tiger county boundary ST_Within check without spatial index | ST_Within over full county polygon set is slow | Ensure county boundary table has GiST index; cache county boundary lookup by zip code | Any production load |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Fuzzy matching:** Returns results — verify threshold is calibrated against the E2E test corpus from Issue #1, not just that it returns any result.
- [ ] **Spell correction:** Corrects "Cherery" to "Cherry" — verify it does NOT change "LANEY WALKER" to "LANE WALKER" or any other valid local street name.
- [ ] **LLM sidecar:** Returns a corrected address — verify that the corrected address is subsequently re-matched against the database (not used as coordinates directly).
- [ ] **LLM sidecar:** Structured output works — verify with a prompt that would cause hallucination (e.g., a nonsense address) and confirm the output is still schema-valid, not free text.
- [ ] **Consensus scoring:** Scores multiple results — verify it correctly handles the case where only one provider returns a match (no false consensus from a single result).
- [ ] **Consensus scoring:** Handles spatial plausibility — verify a result that passes confidence threshold but fails ST_Within expected county is flagged as `needs_review`, not auto-promoted.
- [ ] **Cascade auto-set:** Writes OfficialGeocoding — verify `set_by_stage` metadata is stored, and a dry-run mode exists that computes results without writing.
- [ ] **Tiger county disambiguation:** Post-filter applied — verify with the Issue #1 test addresses that Tiger results are rejected when coordinates fall outside the expected county boundary.
- [ ] **Zip prefix fallback:** Returns a result for truncated zip — verify it returns multiple candidates when the prefix matches multiple zip codes, not just the first hit.
- [ ] **Confidence semantics fix:** `confidence` field updated — verify `GeocodingResult` distinguishes `STRUCTURAL_PARSE` from `GEOCODED_MATCH` and that consensus scoring only uses spatial results.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong official records auto-set from Tiger county bug | HIGH without audit field; MEDIUM with it | `DELETE FROM official_geocodings WHERE address_id IN (SELECT address_id FROM geocoding_results WHERE provider_name='tiger' AND <county_mismatch_condition>)` — then re-run cascade |
| Spell correction mangled valid street names | MEDIUM | Identify via `original_input != spell_corrected_input AND spell_corrected_input != canonical_normalized` audit log query; re-run normalization from original_input |
| LLM hallucinations set as official | MEDIUM with audit trail; HIGH without | Query for official results sourced from LLM stage with no confirming database match; delete and re-run cascade with LLM disabled |
| Fuzzy match false positives in official records | MEDIUM | Spatial audit: find official records where coordinates are >X meters from the centroid of their stated zip code; flag for admin review |
| Cascading pipeline latency exceeded in production | LOW (configuration change) | Raise or enforce per-stage timeouts; disable LLM gate threshold; reduce batch sizes |
| Consensus set from non-independent providers (all Tiger-sourced) | MEDIUM | Re-run consensus scoring with provider independence weights applied; does not require deleting records — update confidence scores |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Confidence semantics mismatch (P8) | Phase 1: Confidence fix + Tiger county disambiguation | `GeocodingResult.confidence_basis` field exists; consensus only scores GEOCODED_MATCH results |
| Tiger wrong-county coordinates (P5 / Issue #1) | Phase 1: Tiger county disambiguation via ST_Within | Issue #1 test addresses all return coordinates within expected county boundary |
| Street name normalization mismatch (P9 / Issue #1) | Phase 1: Normalization mismatch fix | Known multi-word suffix addresses (LANEY WALKER BLVD) normalize correctly; regression tests pass |
| Zip prefix fallback wrong city match (P10 / Issue #1) | Phase 1: Zip prefix fallback fix | Truncated zip inputs return multiple candidates when prefix spans multiple zips; no single auto-selection |
| Fuzzy threshold too low (P1) | Phase 2/3: Fuzzy matching with calibrated threshold | E2E test corpus: zero cross-street false positives at chosen threshold |
| Fuzzy threshold too high (P2) | Phase 2/3: Fuzzy matching with calibrated threshold | E2E test corpus: at least N% of known-degraded inputs recovered by fuzzy stage |
| Spell correction destroys proper nouns (P3) | Phase 2: Spell correction with street name dictionary | "LANEY WALKER", "VINEVILLE", "PIO NONO" all pass through spell correction unchanged |
| LLM hallucination (P4) | Phase 4: LLM sidecar with post-verification gate | LLM output is re-verified against DB before use; hallucinated address is rejected |
| Consensus wrong-same-way (P5) | Phase 5: Consensus scoring with spatial plausibility | ST_Within county boundary check gates auto-promotion |
| Cascade latency explosion (P6) | Phase 5/6: Cascade integration with latency budget | Single address cascade P95 < 3s on local Docker |
| Cascade confident wrong auto-set (P7) | Phase 5/6: Cascade auto-set with dry-run + audit trail | `set_by_stage` field present; dry-run mode works; first production run uses dry-run |

---

## Sources

- [GDELT Project: Why LLM-Based Geocoders Struggle](https://blog.gdeltproject.org/generative-ai-experiments-why-llm-based-geocoders-struggle/) — MEDIUM confidence; empirical research on LLM geocoding failure modes
- [GDELT Project: Surprisingly Poor Performance of LLM-Based Geocoders](https://blog.gdeltproject.org/generative-ai-experiments-the-surprisingly-poor-performance-of-llm-based-geocoders-geographic-bias-why-gpt-3-5-gemini-pro-outperform-gpt-4-0-in-underrepresented-geographies/) — MEDIUM confidence; geographic bias findings
- [PostgreSQL pg_trgm Documentation](https://www.postgresql.org/docs/current/pgtrgm.html) — HIGH confidence; official PostgreSQL docs for threshold parameters
- [EarthDaily: Geocoding Consensus Algorithm](https://earthdaily.com/blog/geocoding-consensus-algorithm-a-foundation-for-accurate-risk-assessment) — MEDIUM confidence; documents consensus approach but gaps in correlated-failure analysis
- [Geocodio: Spelling Correction Guide](https://www.geocod.io/guides/address-spelling-correction/) — MEDIUM confidence; commercial geocoding service's approach to spell correction
- [Markaicode: Structured Output from Local LLMs](https://markaicode.com/ollama-structured-output-pipeline/) — MEDIUM confidence; grammar-constrained generation for local LLM deployments
- [ResearchGate: Pattern and Phonetic Based Street Name Misspelling Correction](https://www.researchgate.net/publication/224245551_Pattern_and_Phonetic_Based_Street_Name_Misspelling_Correction) — MEDIUM confidence; academic treatment of street name misspelling
- [usaddress-scourgify GitHub](https://github.com/GreenBuildingRegistry/usaddress-scourgify) — HIGH confidence; library source confirming it does not perform address validation
- [PostGIS Tiger Geocoder Documentation](https://postgis.net/docs/Extras.html) — HIGH confidence; official PostGIS docs
- Issue #1 E2E test results (known defects, internal) — HIGH confidence; observed in this codebase's test suite
- Existing `GeocodingService.geocode()` source code (services/geocoding.py) — HIGH confidence; direct code inspection of auto-set logic

---
*Pitfalls research for: CivPulse Geo API — cascading address resolution (v1.2 milestone)*
*Researched: 2026-03-29*
