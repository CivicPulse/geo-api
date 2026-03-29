# Feature Research

**Domain:** Cascading address resolution pipeline (v1.2)
**Researched:** 2026-03-29
**Confidence:** MEDIUM-HIGH (pg_trgm/fuzzystrmatch verified via official PostgreSQL docs; Ollama structured output verified via official docs; consensus scoring patterns from published geocoding research; LLM prompting patterns from current community practice)

---

## Context: What This Milestone Adds

This research covers the v1.2 milestone: transforming the multi-provider lookup into an auto-resolving cascading pipeline. The existing pipeline (v1.1) already handles: USPS normalization via scourgify, exact lookup across 5 providers (Census, OA, Tiger, NAD, Macon-Bibb), and admin override. What it does NOT do: handle degraded input, weight provider results, or auto-set an official geocode.

**The v1.2 pipeline goal:**
```
normalize → spell-correct → exact match → fuzzy match → AI correction → re-match → score consensus → auto-set official
```

The previous FEATURES.md covered v1.1 (local data source providers). This file supersedes it for the v1.2 milestone.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features a "cascading resolution" system must deliver. Missing these = the cascade doesn't cascade.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Input normalization before dispatch | Every pipeline needs a clean starting point | LOW | Already partially done via scourgify; v1.2 adds USPS suffix expansion (Road→RD) and state abbreviation canonicalization before provider dispatch — not a new library, just consistent pre-processing |
| Zip prefix fallback for truncated/mistyped ZIPs | Callers submit 4-digit or transposed ZIPs; pipeline must not fail | LOW | Detect zip len < 5 or >5; try 5-digit prefix match against `zip_code LIKE :prefix%` in OA/NAD PostGIS tables; SQL-level, no new library |
| pg_trgm fuzzy street name matching | Exact match fails on "Northminstr Dr" → "Northminster Dr" | MEDIUM | `CREATE EXTENSION pg_trgm;` (already available in PostGIS images); `similarity(input_street, street) > 0.7` threshold; GIN index on street column mandatory for acceptable performance at NAD/OA scale; 0.7 is a well-supported practical threshold for street names — lower causes too many false positives on short names |
| Soundex/Metaphone phonetic fallback | Handles homophones and OCR-style substitutions ("Mane" → "Main") | LOW | `SELECT dmetaphone(street_input) = dmetaphone(street_col)` via `fuzzystrmatch` extension (already in PostGIS image); use as a secondary filter when trigram similarity alone is ambiguous; Double Metaphone preferred over plain Soundex for accuracy |
| Tiger county disambiguation via spatial boundary | Tiger geocoder returns results 50 miles off because it has no county restriction — it matches the nearest street in any loaded county | MEDIUM | Pass `restrict_region` geometry to Tiger's `geocode()` function — it accepts a `geometry` parameter; get county polygon from PostGIS `tiger.county` table by FIPS or name; this is the documented mitigation and verified against PostGIS Tiger function signature |
| Confidence semantics fix (validation) | scourgify returning structural parse ≠ delivery point verified; callers are treating `is_valid=True` as authoritative | LOW | Rename/clarify `is_valid` to indicate parse success only; add `address_exists` boolean populated only when a provider confirms the address exists in a dataset; this is a correctness fix, not new behavior |
| Street name normalization for multi-word streets with USPS suffixes | "Oak Hill Road" fails because scourgify returns "Oak Hill Rd" and the stored value is "OAK HILL RD" — case and full/abbrev mismatch | LOW | Uppercase both sides before compare; maintain a USPS suffix expansion/contraction table (St↔Street, Dr↔Drive, Rd↔Road, Blvd↔Boulevard — ~60 common types); apply both directions in matching |

### Differentiators (Competitive Advantage)

Features that make this pipeline substantially better than a simple ordered fallback.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Spell correction layer (symspellpy) | Fixes common typos before any provider is called — "Nrothminster" → "Northminster" before any DB query; reduces fuzzy match load | MEDIUM | symspellpy supports custom dictionaries; load a frequency dictionary built from the imported NAD/OA street names corpus so domain corrections outrank general English suggestions; max edit distance 2 covers most real typos; do NOT use general English spell checkers (pyspellchecker, TextBlob) for street names — they will incorrectly "correct" proper nouns and place names |
| Local LLM sidecar for address correction (Ollama) | Handles pathologically broken input that deterministic methods cannot fix — transposed components, wrong city/state, incomplete addresses | HIGH | Ollama supports structured output via JSON schema (verified, v0.5+); use temperature=0 for determinism; Pydantic model as the schema; prompt with: (1) system context about address format, (2) few-shot examples of bad→corrected addresses, (3) explicit instruction to return null fields it cannot determine; only invoke after all deterministic stages fail; set timeout budget (2–5 seconds); model selection: qwen2.5:7b or mistral:7b balances size vs accuracy for structured extraction |
| Cross-provider consensus scoring | When multiple providers return results, weight them by agreement — providers that cluster together are more likely correct than an outlier (the Tiger-50-miles-off case) | MEDIUM | Score = (number of providers within N meters of this result) × (provider_weight); use 100m as clustering radius for "agreement"; Tiger weighted lower (0.6) when it disagrees with 2+ other providers; Census/OA/NAD weighted higher (0.9) when they agree; outlier = result > 1km from cluster centroid of other providers; this mirrors published multi-provider geocoding optimization approaches |
| Auto-resolution pipeline: auto-set official geocode | When pipeline produces a high-confidence result, write it as the OfficialGeocoding without requiring admin action | MEDIUM | Only auto-set when: (a) at least 2 providers agree within 100m, OR (b) single provider returns confidence ≥ 0.90; never auto-set from Tiger-only result unless restrict_region filter applied; use the existing `OfficialGeocoding` upsert mechanism — the auto-resolver is just another writer |
| Pipeline stage telemetry | Which stage resolved the address? "spell_correction", "fuzzy_pg_trgm", "llm_correction", "consensus_score" — critical for debugging and tuning thresholds | LOW | Add `resolution_stage` field to `GeocodingResult` or a parallel metadata object; log at INFO level with address hash, stage name, elapsed ms; no new infrastructure |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| General English spell checker for addresses | Obvious first choice for "fixing typos" | General dictionaries actively harm address correction — "Main" gets corrected to "Maine", "Peach" to "Peace", "Bibb" (a county) has no English context; edit distance alone without domain frequency data produces wrong corrections | Use symspellpy with a custom frequency dictionary built from the actual address corpus (NAD/OA street names) |
| Running LLM on every address | Seems like it would maximize accuracy | LLM latency (500ms–2s per call) makes it unusable in the hot path; cost for self-hosted models is GPU/CPU time per request; most addresses resolve correctly at the normalization or exact-match stage | LLM is a last-resort fallback only — after normalization, spell correction, exact match, and fuzzy match all fail |
| Parallel LLM + provider dispatch | Seems like it saves time | Wastes GPU/CPU resources on addresses that would resolve deterministically; burns the LLM budget on addresses that don't need it; muddies which result to trust | Sequential pipeline with early-exit; LLM only invoked when earlier stages fail |
| Fuzzy matching at similarity threshold < 0.5 | More permissive = more matches | At < 0.6, trigram similarity on short strings (3–5 char street names) produces too many false positive matches; "Oak" has similarity 0.5 with "Oak" but also with other 3-gram clusters; creates wrong geocodes that are harder to detect than no result | Keep threshold at 0.65–0.75; prefer "no match" over "wrong match" for geocoding |
| Consensus scoring that averages all provider coordinates | Seems like a middle ground | Averaging a correct result (32.87°N, -83.69°W) with an outlier (33.42°N, -83.51°W — 55 miles off) produces a result that is wrong for everyone; the averaged point corresponds to no real address | Detect and exclude outliers before averaging; use cluster-based approach (majority vote within radius) not arithmetic mean |
| Auto-set official from any single-provider result | Simplest auto-resolution | Single provider can be wrong — especially Tiger on streets near county boundaries; auto-setting a wrong OfficialGeocoding is worse than leaving it unset because it poisons downstream callers | Require multi-provider agreement OR a high-confidence single result (≥ 0.90, from a rooftop-accuracy source) before auto-setting |
| Spell-correcting city and state fields | Seems consistent with street correction | City and state corrections require geographic validation (is "Macoon, GA" → "Macon, GA" correct? only if zip confirms it) — general spell correction gets these wrong; city names are proper nouns with low general frequency | Limit spell correction to street name token only; validate city/state against zip-code centroid data if needed |

---

## Feature Dependencies

```
[Cascading Resolution Pipeline]
    └──requires──> [Input Normalization (USPS suffix expansion)]
                       └──uses──> [scourgify (already built)]
    └──requires──> [Zip Prefix Fallback]
                       └──uses──> [OA + NAD PostGIS tables (v1.1)]
    └──requires──> [Exact Match across all providers (v1.0 + v1.1)]
    └──requires──> [Fuzzy Street Matching (pg_trgm + Soundex)]
                       └──requires──> [pg_trgm extension (in PostGIS image)]
                       └──requires──> [fuzzystrmatch extension (in PostGIS image)]
                       └──requires──> [GIN index on OA/NAD street columns]
    └──requires──> [Spell Correction Layer (symspellpy)]
                       └──requires──> [Street name corpus dictionary (from NAD/OA data)]
    └──optional──> [LLM Address Correction (Ollama sidecar)]
                       └──requires──> [Ollama service running with a suitable model]
                       └──requires──> [Structured output schema (Pydantic)]
    └──requires──> [Cross-Provider Consensus Scoring]
                       └──requires──> [Results from 2+ providers]
                       └──requires──> [ST_Distance (PostGIS — already available)]
    └──requires──> [Auto-Set Official Geocode]
                       └──requires──> [OfficialGeocoding upsert (already built, v1.0)]
                       └──requires──> [Consensus score above threshold]

[Tiger County Disambiguation]
    └──requires──> [Tiger geocoder provider (v1.1)]
    └──requires──> [tiger.county table with polygon geometry (loaded with TIGER/LINE data)]
    └──uses──> [restrict_region parameter on geocode() SQL function]

[Validation Confidence Semantics Fix]
    └──requires──> [Understanding of current scourgify provider behavior]
    └──enhances──> [All existing validation providers]

[Street Name Normalization Fix]
    └──requires──> [USPS suffix lookup table (St↔Street, Dr↔Drive, etc.)]
    └──enhances──> [OA, NAD, Tiger providers]
    └──conflicts──> [Current scourgify pre-normalization if suffix expansion not bidirectional]

[Pipeline Stage Telemetry]
    └──enhances──> [All pipeline stages above]
    └──uses──> [Loguru (already in stack)]
```

### Dependency Notes

- **Fuzzy matching requires GIN indexes before use in production:** Trigram similarity without an index performs a full sequential scan of the OA/NAD PostGIS tables. At 60k+ (OA) and 80M+ (NAD) rows, this is unusable. `CREATE INDEX idx_oa_street_trgm ON openaddresses USING GIN (street gin_trgm_ops);` is a prerequisite step, not a runtime dependency.

- **Spell correction dictionary must be built from the address corpus:** The symspellpy dictionary should be generated from the street names in the loaded NAD/OA data — not from a general English corpus. This means the CLI that imports NAD/OA data should optionally produce the frequency dictionary, or a separate build step generates it. The dictionary file is an artifact of the import, not a static resource.

- **LLM sidecar is optional infrastructure:** The Ollama service is an optional component. If it is not running, the pipeline skips the LLM stage and proceeds to consensus scoring with whatever results the deterministic stages produced. The pipeline must not fail when Ollama is unavailable — treat as a graceful no-op.

- **Consensus scoring requires 2+ provider results to be meaningful:** If only one provider returns a result, scoring is trivially 1.0. Consensus is only meaningful when multiple providers have results — the scoring logic must handle the single-result case by passing it through unchanged.

- **Tiger county disambiguation is an improvement to the existing Tiger provider:** It is not a new provider. It adds a `restrict_region` geometry argument to the Tiger SQL call. Requires that the `tiger.county` table is populated (loaded with TIGER/LINE data). If TIGER/LINE data is not loaded, the Tiger provider is already unavailable — this is a non-issue.

- **Auto-set official geocode reuses the v1.0 OfficialGeocoding upsert:** The existing `ON CONFLICT DO UPDATE` logic in the OfficialGeocoding upsert must be changed from `DO NOTHING` to `DO UPDATE` for auto-resolution to work — or a separate "cascade auto-resolve" write path that only fires under the confidence threshold condition. This interacts with the v1.0 "first-writer-wins" decision; the v1.2 pipeline needs to explicitly supersede it.

---

## MVP Definition

### Launch With (v1.2 milestone — all required)

- [ ] Input normalization fix (USPS suffix expansion both directions, uppercase normalize) — prerequisite for everything else; fixes known provider defects from E2E testing
- [ ] Validation confidence semantics fix — correctness fix; scourgify `is_valid=True` currently misleads callers
- [ ] Street name normalization mismatch fix — correctness fix; multi-word streets with USPS suffixes fail
- [ ] Zip prefix fallback matching — low complexity; recovers truncated/mistyped ZIPs without new libraries
- [ ] Tiger county disambiguation via `restrict_region` — directly fixes the Tiger-50-miles-off defect identified in E2E testing; uses existing PostGIS infrastructure
- [ ] pg_trgm fuzzy street matching (threshold 0.65–0.70) — core fuzzy capability; needs GIN index creation
- [ ] Soundex/Double Metaphone phonetic fallback — complements trigrams for phonetic variants; same `fuzzystrmatch` extension
- [ ] Spell correction layer (symspellpy + domain dictionary) — improves input quality before any DB query; offline, no service dependency
- [ ] Cross-provider consensus scoring (cluster-based, 100m radius) — enables outlier exclusion; prerequisite for trustworthy auto-resolution
- [ ] Auto-set official geocode from consensus — closes the pipeline loop; only fires at high confidence threshold
- [ ] Pipeline stage telemetry — needed for threshold tuning after deployment

### Add After Validation (v1.x)

- [ ] Local LLM sidecar (Ollama) for pathological cases — trigger: measurement shows what percentage of addresses fail all deterministic stages; only worth adding if failure rate is > 1–2%
- [ ] Per-provider confidence weight tuning — trigger: telemetry shows which providers are systematically biased; adjust weights based on observed error patterns
- [ ] Spell correction dictionary refresh from updated NAD/OA imports — trigger: operational issue with stale dictionary after data refresh

### Future Consideration (v2+)

- [ ] ML-based address confidence scoring — replaces heuristic weights with a trained model; trigger: enough labeled data to train; high effort
- [ ] Real-time address validation via USPS API — provides actual DPV; trigger: a downstream service needs mail-deliverable confirmation; has cost implications

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Validation confidence semantics fix | HIGH | LOW | P1 |
| Street name normalization mismatch fix | HIGH | LOW | P1 |
| Input normalization (USPS suffix expansion) | HIGH | LOW | P1 |
| Zip prefix fallback | HIGH | LOW | P1 |
| Tiger county disambiguation (restrict_region) | HIGH | LOW | P1 |
| pg_trgm fuzzy street matching + GIN index | HIGH | MEDIUM | P1 |
| Soundex/Double Metaphone phonetic fallback | MEDIUM | LOW | P1 |
| Cross-provider consensus scoring | HIGH | MEDIUM | P1 |
| Auto-set official geocode from consensus | HIGH | MEDIUM | P1 |
| Spell correction (symspellpy + domain dict) | HIGH | MEDIUM | P1 |
| Pipeline stage telemetry | MEDIUM | LOW | P1 |
| Local LLM sidecar (Ollama) | MEDIUM | HIGH | P2 |
| Per-provider weight tuning | LOW | LOW | P2 |
| ML-based confidence scoring | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Required for v1.2 milestone
- P2: Add after validation once failure-rate data available
- P3: Future consideration; defer until need demonstrated

---

## Capability Deep Dives

### Fuzzy Address Matching: What "Good" Looks Like

**What works at the DB layer:**

pg_trgm similarity threshold of **0.65–0.70** is the right range for US street names. The default (0.3) is too permissive and will match unrelated streets. 0.80+ is too strict and misses real typos. The sweet spot for multi-word street names (where trigrams accumulate quickly) is 0.70. For short single-token names (Oak, Elm), drop to 0.65.

**Combine trigram + phonetic:** Use trigram similarity as primary filter (`similarity(street, :input) > 0.65`), then rank results using Double Metaphone agreement as a tiebreaker. This handles both character-level typos ("Northminstr") and phonetic substitutions ("Mane St" → "Main St").

**GIN vs GiST index:** Use GIN for static data (OA, NAD — loaded once, rarely updated). GIN is faster for read-heavy workloads. GiST is better for frequently updated tables and smaller index size. At NAD scale (80M rows), GIN build time is significant (30–60 min) but query performance is milliseconds.

**Threshold tuning approach:** Run the pipeline against known-bad inputs from the E2E test cases; adjust threshold per provider if needed. Lower threshold is acceptable for NAD (80M rows, high coverage) than for OA (county-level file, lower coverage). Emit `resolution_stage=fuzzy_trgm` and `similarity_score` in telemetry to measure.

**What "good" looks like:** Fuzzy matching resolves "Northminstr Dr" → "Northminster Dr" with a score of ~0.76. It does NOT resolve "Oak St" → "Elm St" (score ~0.14 — correctly rejected). It does NOT resolve street numbers — number matching remains exact; only the street name token is fuzzy-matched.

---

### Spell Correction: What "Good" Looks Like

**Why general spell checkers fail for addresses:**

pyspellchecker and TextBlob use general English word frequency. Street names like "Northminster", "Napier", "Shurling", "Zebulon" are rare in English corpora and will be "corrected" to random common words. This produces wrong results that are harder to detect than no result.

**The right approach — symspellpy with domain dictionary:**

1. Extract all unique street name tokens from the loaded OA and NAD PostGIS tables (post-import).
2. Build a frequency dictionary: term → count (use actual occurrence count from the dataset).
3. Load this dictionary into symspellpy instead of the default English dictionary.
4. Max edit distance = 2 (covers single transpositions and common typos; distance 3 produces too many false positives).
5. Only apply spell correction to the **street name token**, not the full address string. House numbers, unit designators, ZIP codes, and state abbreviations must not be spell-corrected.

**What "good" looks like:** "Northminstr Dr" → spell correction unchanged (trigrams handle this better than edit distance); "Rosevelt Ave" → "Roosevelt Ave" (edit distance 2, present in corpus). "123 Mane St Macon GA 31204" → spell corrects "Mane" to "Main" (if Main St exists in corpus) but does not touch "123", "Macon", "GA", or "31204".

**What "good" does NOT look like:** Correcting city names, correcting state abbreviations, correcting cardinal directions (N/S/E/W), correcting house numbers with alpha suffixes ("123A" stays "123A").

---

### LLM Address Correction: What "Good" Looks Like

**When to invoke:**

LLM is a last-resort fallback. Only invoke after: (1) input normalization, (2) spell correction, (3) exact match across all providers, and (4) fuzzy match — all fail to produce a result with confidence ≥ 0.40. In practice, this is pathological input like transposed components ("Macon GA 1234 Northminster Dr") or incomplete addresses ("1234 Northminster, 31204").

**Prompting pattern (verified working with Ollama structured output):**

```
System: You are an address parser for US postal addresses in Macon-Bibb County, Georgia.
        Extract the components from malformed or incomplete address input.
        Return only what you can determine with confidence; use null for fields you cannot determine.

User: Parse this address: "{raw_input}"

Schema: {
  "house_number": "string or null",
  "street_name": "string or null",
  "street_suffix": "string or null",
  "unit": "string or null",
  "city": "string or null",
  "state": "string or null",
  "zip_code": "string or null"
}
```

Few-shot examples in system prompt improve accuracy significantly. Include 2–3 examples of bad input → correct structured output.

**What "good" looks like:** Given "1234 Northminster, Bibb County GA 31204", the LLM returns `{"house_number": "1234", "street_name": "Northminster", "street_suffix": null, "city": "Macon", "state": "GA", "zip_code": "31204"}`. The returned partial address is then fed back into the pipeline for a new exact/fuzzy match pass.

**What "good" does NOT look like:** The LLM inventing a street that doesn't exist in the corpus ("Northminster Drive" when the correct address is "Northminster Boulevard"), or returning coordinates directly (LLMs are unreliable for this). The LLM's job is **address component extraction and completion**, not geocoding.

**Infrastructure note:** Ollama structured output requires `format` parameter set to the JSON schema. Pydantic `model_json_schema()` produces a compatible schema. Use `temperature=0` for determinism. Implement a 3-second timeout; treat timeout as LLM-unavailable and skip stage.

---

### Consensus Scoring: What "Good" Looks Like

**The Tiger-50-miles-off problem:**

Tiger geocodes without a county restriction can return a result in an adjacent county or state that happens to have a street with the same name. The result is geometrically far from the expected location (often 30–80 miles). Cross-provider consensus scoring should detect and down-weight this.

**Cluster-based approach (not averaging):**

1. Collect all provider results with confidence > 0.0.
2. Group results by spatial cluster: results within 100m of each other form a cluster.
3. The winning cluster is the one with the highest aggregate weight (sum of per-provider weights).
4. Results outside the winning cluster are flagged as outliers.
5. The consensus result is the centroid of the winning cluster (not the arithmetic mean of all results).

**Provider weights (starting values — tune with telemetry):**

| Provider | Weight | Rationale |
|----------|--------|-----------|
| Macon-Bibb GIS | 1.0 | Authoritative local source; highest trust |
| OpenAddresses | 0.9 | Community-collected rooftop points; high accuracy |
| NAD | 0.85 | E911 source data; reliable but placement varies |
| Census Geocoder | 0.80 | Interpolated; accurate but not rooftop |
| Tiger (restricted) | 0.75 | PostGIS Tiger with restrict_region applied |
| Tiger (unrestricted) | 0.40 | Unrestricted Tiger; outlier candidate |

**Confidence output:**

```
consensus_confidence = (winning_cluster_weight_sum / total_weight_sum) × max_cluster_confidence
```

If winning cluster has weight 2.65 (OA + NAD + Census) out of total 3.25 (all providers), consensus confidence = 0.815 × 0.95 (OA confidence) ≈ 0.77.

**What "good" looks like:** Three providers agree within 100m → high consensus confidence → auto-set OfficialGeocoding. Tiger returns a point 55 miles away → outlier flagged → Tiger excluded from consensus → pipeline warns in logs but still produces a good result from the agreeing providers.

**What "good" does NOT look like:** A single provider result with confidence=0.95 being treated as consensus. Single-provider results must be marked as `consensus_method=single_provider` and only auto-set official if confidence ≥ 0.90 and provider is a rooftop-accuracy source.

---

### Cascading Pipeline: What Ordering Matters

**The correct ordering:**

```
Stage 1: Input normalization
  - Lowercase, strip punctuation, expand USPS suffix abbreviations
  - Canonicalize state to 2-letter; zero-pad zip to 5 digits
  - EXIT if address is structurally unparseable (return validation error)

Stage 2: Zip prefix recovery
  - If zip < 5 digits, try prefix match
  - Mutate the parsed address zip before further stages

Stage 3: Spell correction (symspellpy, domain dictionary)
  - Only on street name token
  - Store original; record correction applied
  - CONTINUE with corrected form; keep original as fallback

Stage 4: Exact match across all providers
  - Dispatch in priority order: Macon-Bibb → OA → NAD → Census → Tiger(restricted)
  - Collect ALL results that return confidence > 0.0
  - If 2+ providers agree within 100m → run consensus scoring → EXIT with result
  - If 1 provider returns confidence ≥ 0.90 (rooftop source) → EXIT with result

Stage 5: Fuzzy match (pg_trgm similarity on street name)
  - Run against OA and NAD PostGIS tables (they support SQL-level fuzzy)
  - threshold = 0.70 for multi-word streets, 0.65 for single-word
  - Collect candidates; re-run consensus scoring
  - If consensus passes threshold → EXIT with result

Stage 6: Phonetic fallback (Double Metaphone)
  - Combine with trigram: dmetaphone agreement breaks ties between trigram candidates
  - Run against OA and NAD PostGIS tables
  - Collect candidates; re-run consensus scoring
  - If consensus passes threshold → EXIT with result

Stage 7: LLM address correction (optional, if Ollama available)
  - Only if stages 1–6 produced no result with confidence ≥ 0.40
  - LLM returns corrected address components
  - Feed corrected components back into stages 4–6
  - Record resolution_stage = "llm_correction"

Stage 8: Final scoring and auto-set
  - Best available result from highest-confidence stage
  - If confidence ≥ threshold AND meets provider agreement rule → auto-set OfficialGeocoding
  - Otherwise → return result without auto-setting (admin action required)
  - Always return best available result; never return empty when a partial result exists
```

**Why this order:**

- Normalization first eliminates the largest class of mismatches (suffix mismatch, case) before any DB query.
- Spell correction before DB dispatch means the DB sees a cleaner string; avoids needing fuzzy indexes on all providers.
- Exact match before fuzzy: exact is fast (indexed B-tree); fuzzy scan is more expensive even with GIN index. Try cheap paths first.
- Tiger restricted comes before Tiger unrestricted — always; the unrestricted call is purely a fallback.
- LLM last: highest latency, highest infrastructure dependency; only justified when all deterministic methods fail.
- Consensus scoring at each exit point, not just the end: early consensus detection enables early exit, which is critical for batch throughput.

---

## Sources

- PostgreSQL pg_trgm official docs: [postgresql.org/docs/current/pgtrgm.html](https://www.postgresql.org/docs/current/pgtrgm.html)
- PostgreSQL fuzzystrmatch (Soundex/Metaphone): [postgresql.org/docs/current/fuzzystrmatch.html](https://www.postgresql.org/docs/current/fuzzystrmatch.html)
- Neon pg_trgm extension guide: [neon.com/docs/extensions/pg_trgm](https://neon.com/docs/extensions/pg_trgm)
- symspellpy (Python SymSpell port): [pypi.org/project/symspellpy](https://pypi.org/project/symspellpy/)
- libpostal address normalization reference: [github.com/openvenues/libpostal](https://github.com/openvenues/libpostal)
- Ollama structured outputs (v0.5+): [docs.ollama.com/capabilities/structured-outputs](https://docs.ollama.com/capabilities/structured-outputs)
- Ollama structured outputs blog: [ollama.com/blog/structured-outputs](https://ollama.com/blog/structured-outputs)
- Multi-provider geocoding optimization (POI-constrained): [tandfonline.com/doi/full/10.1080/17538947.2025.2578735](https://www.tandfonline.com/doi/full/10.1080/17538947.2025.2578735)
- EarthDaily Geocoding Consensus Algorithm: [earthdaily.com/blog/geocoding-consensus-algorithm](https://earthdaily.com/blog/geocoding-consensus-algorithm-a-foundation-for-accurate-risk-assessment)
- Geocoding systematic review (2025): [arxiv.org/pdf/2503.18888](https://arxiv.org/pdf/2503.18888)
- PostGIS geocode() function (restrict_region): [postgis.net/docs/Geocode.html](https://postgis.net/docs/Geocode.html)
- Crunchydata address matching with libpostal: [crunchydata.com/blog/quick-and-dirty-address-matching-with-libpostal](https://www.crunchydata.com/blog/quick-and-dirty-address-matching-with-libpostal)
- Incognia messy address pipeline: [medium.com/incognia-tech/handling-messy-address-data](https://medium.com/incognia-tech/handling-messy-address-data-4d51bbb7e8e3)
- Cascading geocoding success rates: [coordable.co — Geocoding Orchestrator](https://coordable.co/)
- Address normalization state of the field: [medium.com/@albamus/the-state-of-address-normalisation](https://medium.com/@albamus/the-state-of-address-normalisation-9c41a20a638a)

---

*Feature research for: cascading address resolution pipeline (v1.2)*
*Researched: 2026-03-29*
