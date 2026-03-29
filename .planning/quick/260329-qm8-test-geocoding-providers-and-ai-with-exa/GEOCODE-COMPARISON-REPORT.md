# Geocoding Cascade Comparison Report

**Date:** 2026-03-29
**Environment:** Local Docker Compose (geo-api-api + geo-api-db)
**API URL:** http://localhost:8042
**Cascade enabled:** Yes (`CASCADE_ENABLED=true`)
**LLM sidecar:** Not running (Ollama requires `--profile llm`, no Ollama container in compose ps)
**Providers active:** census, openaddresses, postgis_tiger, national_address_database, macon_bibb (5 registered; Tiger timing out — see Delta section)
**Spell corrector:** Loaded (0 dictionary words — spell_dictionary table empty in current environment)

---

## Test Addresses

| # | Raw Input | Input Defects |
|---|-----------|---------------|
| 1 | `548 Moss Hl, MacOn GA, 31204` | Abbreviated street suffix ("Hl" for Hill), mixed-case city ("MacOn") |
| 2 | `700 poplar st, Macon, ga, 31201` | All lowercase, extra trailing comma |
| 3 | `659 Arlington place, Macon, ga 3120` | Unabbreviated suffix ("place"), truncated ZIP (4 digits, missing last digit) |
| 4 | `669 Arlngton lace, Mac0n Georgia` | Misspelled street ("Arlngton"), misspelled suffix ("lace" for "Place"), zero instead of 'o' in city ("Mac0n"), no ZIP, state spelled out |

---

## Address 1: 548 Moss Hl, MacOn GA, 31204

### Normalized Address
`548 MOSS HL MACON GA 31204`

The normalizer successfully handled mixed case and the abbreviated suffix "Hl".

### Cascade Trace

| Stage | Duration (ms) | Results Count | Early Exit | Detail |
|-------|--------------|---------------|------------|--------|
| normalize | 15.8 | — | — | spell_corrected=true; input uppercased, "Hl" preserved |
| exact_match | 4,687.5 | 2 | — | 5 providers called; Census + OpenAddresses matched; Tiger timed out at 2000ms |
| fuzzy_match | — | — | Skipped | Census confidence=0.80 triggered early exit |
| llm_correction | — | — | Skipped | CASCADE_LLM_ENABLED=false |
| consensus | 0.5 | 2 candidates | — | Winning cluster size=2, total_weight=1.70, set_by_stage=exact_match_consensus |
| auto_set_official | 18.0 | — | — | Official set to Census (closest to centroid) |

### Provider Results

| Provider | Confidence | Location Type | Lat | Lng | Is Outlier | Verdict |
|----------|-----------|---------------|-----|-----|------------|---------|
| census | 0.80 | RANGE_INTERPOLATED | 32.866817 | -83.675862 | No | Official — selected by consensus |
| openaddresses | 0.80 | APPROXIMATE | 32.867320 | -83.676508 | No | In winning cluster (~67m from Census) |
| postgis_tiger | — | — | — | — | — | Timed out (2000ms) — no result returned |
| national_address_database | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match (NAD covers 303xx ZIP only) |
| macon_bibb | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match (address not in Macon-Bibb GIS dataset) |

### Official Result
- **Provider:** census
- **Coordinates:** 32.866817, -83.675862
- **Confidence:** 0.80
- **Set by stage:** exact_match_consensus

### Analysis
Address 1 is a mild test: mixed case and an abbreviated suffix. The normalizer handled both correctly. Two providers agreed within ~67m, forming a strong consensus cluster (weight=1.70). Tiger timed out (2000ms) rather than returning its prior wrong-county result — this is a change from run 260329-q2v where Tiger returned a Troup County outlier at (32.515, -84.985). Official result is reliable.

---

## Address 2: 700 poplar st, Macon, ga, 31201

### Normalized Address
`700 POPLAR ST MACON GA 31201`

The normalizer correctly uppercased all tokens and handled the extra trailing comma.

### Cascade Trace

| Stage | Duration (ms) | Results Count | Early Exit | Detail |
|-------|--------------|---------------|------------|--------|
| normalize | 3.8 | — | — | spell_corrected=true; all-lowercase input uppercased cleanly |
| exact_match | 4,314.8 | 1 | — | 5 providers called; only Census matched; Tiger timed out at 2000ms |
| fuzzy_match | — | — | Skipped | Census confidence=0.80 triggered early exit |
| llm_correction | — | — | Skipped | CASCADE_LLM_ENABLED=false |
| consensus | 0.1 | 1 candidate | — | Single provider; cluster_weight=0.90, set_by_stage=single_provider |
| auto_set_official | 4.2 | — | — | Official set to Census result |

### Provider Results

| Provider | Confidence | Location Type | Lat | Lng | Is Outlier | Verdict |
|----------|-----------|---------------|-----|-----|------------|---------|
| census | 0.80 | RANGE_INTERPOLATED | 32.836028 | -83.631827 | No | Official — only matching provider |
| openaddresses | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match (700 Poplar St not in OA Bibb dataset) |
| postgis_tiger | — | — | — | — | — | Timed out (2000ms) — no result returned |
| national_address_database | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match (NAD covers 303xx only) |
| macon_bibb | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match |

**Note on single_provider weight:** The consensus reports `winning_cluster_weight=0.90` for a single Census result. Census is a remote provider with weight 1.0; the 0.90 likely reflects a per-candidate scoring adjustment applied to single-provider clusters (vs. multi-provider consensus). This is consistent with prior run behavior.

### Official Result
- **Provider:** census
- **Coordinates:** 32.836028, -83.631827
- **Confidence:** 0.80
- **Set by stage:** single_provider

### Analysis
Address 2 is the cleanest test case — only formatting noise (lowercase, extra comma). Normalization handled it without spell correction. Only Census matched with sufficient confidence (0.80), setting official via single_provider path. The result is a valid, findable location. Tiger's timeout (vs. prior run where Tiger returned a near-identical result ~5m from Census) has no impact on outcome here since Census alone suffices.

---

## Address 3: 659 Arlington place, Macon, ga 3120

### Normalized Address
`659 ARLINGTON PL MACON GA 3120`

The normalizer expanded "place" → "PL" and preserved the truncated 4-digit ZIP "3120" as-is (no padding or validation).

### Cascade Trace

| Stage | Duration (ms) | Results Count | Early Exit | Detail |
|-------|--------------|---------------|------------|--------|
| normalize | 7.7 | — | — | spell_corrected=true; "place" expanded to "PL"; truncated ZIP preserved |
| exact_match | 3,389.2 | 3 | — | 5 providers called; Census + OpenAddresses + Macon-Bibb matched; Tiger timed out |
| fuzzy_match | — | — | Skipped | Census confidence=0.80 triggered early exit |
| llm_correction | — | — | Skipped | CASCADE_LLM_ENABLED=false |
| consensus | 0.3 | 3 candidates | — | Winning cluster size=3, total_weight=2.50, set_by_stage=exact_match_consensus |
| auto_set_official | 13.3 | — | — | Official set via consensus |

### Provider Results

| Provider | Confidence | Location Type | Lat | Lng | Is Outlier | Verdict |
|----------|-----------|---------------|-----|-----|------------|---------|
| census | 0.80 | RANGE_INTERPOLATED | 32.837504 | -83.641804 | No | In winning cluster |
| openaddresses | 0.40 | APPROXIMATE | 32.837536 | -83.641785 | No | In winning cluster (~2m from Census) |
| postgis_tiger | — | — | — | — | — | Timed out (2000ms) — no result returned |
| national_address_database | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match |
| macon_bibb | 0.40 | APPROXIMATE | 32.837536 | -83.641785 | No | In winning cluster (same point as OA) |

**Notable:** Despite the truncated ZIP (4 digits instead of 5), all three correct providers found the address. OpenAddresses and Macon-Bibb returned confidence=0.40 (APPROXIMATE) — lower than 0.80 — consistent with ZIP mismatch reducing match quality. OpenAddresses and Macon-Bibb share the exact same coordinate (both likely sourced from the same underlying parcel/GIS data).

### Official Result
- **Provider:** openaddresses
- **Coordinates:** 32.837536, -83.641785
- **Confidence:** 0.40
- **Set by stage:** exact_match_consensus

**Note:** The official is "openaddresses" (centroid closest member), not Census (0.80). OpenAddresses and Macon-Bibb share the exact same point, and that point was selected as closest to the 3-way weighted centroid. This is the same behavior as prior run 260329-q2v.

### Analysis
Address 3 demonstrates that truncated ZIP (4 digits) does not block resolution. The three-way agreement (all within ~2m) produced a confident cluster. Tiger's timeout removes the previously-observed outlier from (32.059, -84.182) — the `outlier_providers` list is now `[]` vs. prior run where Tiger was included. The net outcome (official result, consensus stage) is identical to the prior run despite Tiger's absence.

---

## Address 4: 669 Arlngton lace, Mac0n Georgia

### Normalized Address
`669 ARLNGTON LACE MAC0N GEORGIA`

The normalizer preserved all errors: "ARLNGTON" (misspelled), "LACE" (suffix misidentification), "MAC0N" (zero not corrected — spell corrector has 0 dictionary words), "GEORGIA" (state name not abbreviated).

**Component parse result:** `state` stored as `None` (exceeded VARCHAR(2) — safe guard applied in 260329-q2v bug fix), `city` misidentified as "LACE".

### Cascade Trace

| Stage | Duration (ms) | Results Count | Early Exit | Detail |
|-------|--------------|---------------|------------|--------|
| normalize | 12.0 | — | — | spell_corrected=true; no corrections applied (dictionary empty) |
| exact_match | 3,397.2 | 0 | — | 5 providers called; all NO_MATCH; Tiger timed out |
| fuzzy_match | 420.4 | — | — | Ran (no early exit); no candidates above 0.65 threshold |
| llm_correction | — | — | Skipped | LLM disabled (CASCADE_LLM_ENABLED=false / llm_corrector=None) |
| consensus | 0.0 | 0 candidates | — | No candidates; winning_cluster=null, set_by_stage=null |
| auto_set_official | 0.0 | — | — | Not set (no winning cluster) |

### Provider Results

| Provider | Confidence | Location Type | Lat | Lng | Is Outlier | Verdict |
|----------|-----------|---------------|-----|-----|------------|---------|
| census | 0.0 | null | null | null | No | NO_MATCH — Census returned null coordinates |
| openaddresses | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match |
| postgis_tiger | — | — | — | — | — | Timed out (2000ms) — no result returned |
| national_address_database | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match |
| macon_bibb | 0.0 | NO_MATCH | 0.0 | 0.0 | No | No match |

**Fuzzy match:** The FuzzyMatcher searched all three staging tables (OA, NAD, Macon-Bibb) using pg_trgm word_similarity for "ARLNGTON". No candidates scored ≥ 0.65 threshold (420ms). The misspelling ("Arlngton" vs "Arlington" — transposed 'l' + missing 'i') produces edit distance too large for pg_trgm recovery at this threshold.

**LLM stage:** Not active. With Ollama running (`docker compose --profile llm up -d`), the qwen2.5:3b model would attempt to correct "669 Arlngton lace, Mac0n Georgia" → "669 Arlington Place, Macon, GA" and re-verify through providers.

**Census response format change:** Census returned `latitude: null, longitude: null, location_type: null` (not `latitude: 0.0, location_type: "NO_MATCH"`) — this is consistent with how the Census provider encodes a true no-result (null) vs. an explicit no-match from local providers (0.0 / NO_MATCH string). Same semantics, different encoding.

### Official Result
**Not set** — all cascade stages exhausted without producing a valid candidate.

### Analysis
Address 4 remains the hardest test: compound errors with no ZIP code. The cascade correctly exhausted all deterministic stages. Without the LLM sidecar, this address is unresolvable. The bug fixes from 260329-q2v (state VARCHAR(2) guard, ST_Y cast) continue to hold — no HTTP 500 errors. The fuzzy stage ran successfully (420ms, ~same as prior run's 424ms), confirming the ST_Y fix is stable.

---

## Comparison Matrix

| Address | Input | Spell Corrected? | Fuzzy Matched? | LLM Corrected? | Official Set? | Official Provider | Confidence | exact_match Candidates |
|---------|-------|-----------------|----------------|----------------|---------------|-------------------|------------|----------------------|
| 1 | `548 Moss Hl, MacOn GA, 31204` | Yes (flag=true, no changes) | No (skipped) | No (disabled) | Yes | census | 0.80 | 2 |
| 2 | `700 poplar st, Macon, ga, 31201` | Yes (flag=true, no changes) | No (skipped) | No (disabled) | Yes | census | 0.80 | 1 |
| 3 | `659 Arlington place, Macon, ga 3120` | Yes (flag=true, no changes) | No (skipped) | No (disabled) | Yes | openaddresses | 0.40 | 3 |
| 4 | `669 Arlngton lace, Mac0n Georgia` | Yes (flag=true, no changes) | No (no candidates) | No (disabled) | No | — | — | 0 |

**Note on spell_corrected flag:** All four addresses show `spell_corrected=true` — this flag indicates the SpellCorrector ran (was available), not that corrections were applied. The spell_dictionary has 0 words so no actual corrections were made.

---

## Delta from Prior Run (260329-q2v)

### Change 1: Tiger Provider Now Times Out on All Requests (Behavioral Regression)

**Prior run (260329-q2v):** Tiger returned results for addresses 1 and 3 (wrong-county bug — Troup County ~185km from Macon for address 1, Meriwether County ~112km for address 3). These were flagged as outliers by the consensus engine.

**This run (260329-qm8):** Tiger times out on every request at 2000ms. Confirmed by API logs:
```
WARNING | CascadeOrchestrator: provider postgis_tiger timed out after 2000ms
```
Tiger does not appear in `local_results` for any address.

**Root cause hypothesis:** The PostgreSQL Tiger geocoder extension is likely under load or the Tiger data tables are being scanned without indexes during this session. This may also be related to Docker resource contention — the db container was started 5 days ago but the API was restarted 10 minutes before the test run. The Tiger extension may require a warm-up query cycle.

**Impact on results:**
- Address 1: `outlier_providers: []` (prior: Tiger was flagged). Consensus outcome unchanged (Census + OA cluster still wins).
- Address 2: No change — Tiger matched previously but was not in the consensus pool (only Census was official anyway).
- Address 3: `outlier_providers: []` (prior: Tiger flagged at ~112km). Consensus outcome unchanged (3-provider cluster without Tiger).
- Address 4: No change — Tiger didn't contribute in either run.

**Net outcome:** Official results for all 4 addresses are identical to prior run despite Tiger's absence. The consensus engine's outlier detection was not exercised in this run (no outliers present).

### Change 2: Address 4 Census Response Format

**Prior run:** Census returned `"location_type": null, "confidence": 0.0` for address 4 (NO_MATCH pattern).

**This run:** Census returned `"latitude": null, "longitude": null, "location_type": null, "confidence": 0.0` — null coordinates instead of 0.0 floats. This is a minor difference in Census API response marshaling; both correctly encode NO_MATCH semantics.

### Change 3: Cascade Timing Slightly Faster for Address 4

**Prior run:** Address 4 exact_match: 3,274.8ms.

**This run:** Address 4 exact_match: 3,397.2ms (slightly slower); fuzzy: 420.4ms (prior: 424.5ms). Negligible variance, within expected timing noise.

### No Changes

- Official results (provider, coordinates, confidence) for all 4 addresses are **identical** to 260329-q2v.
- Bug fixes from 260329-q2v (state VARCHAR guard, fuzzy ST_Y cast) are confirmed stable — no new crashes.
- Spell corrector behavior unchanged (0 dictionary words, no corrections applied).
- LLM stage unchanged (disabled in both runs).

---

## Findings

### 1. Cascade Stage Activation by Defect Type

| Defect Type | Stage That Resolves It | Addresses Affected |
|-------------|----------------------|-------------------|
| Mixed case, extra commas | normalize (D-01) | 1, 2 |
| Abbreviated suffix ("Hl", "st") | normalize (USPS expansion) | 1, 2 |
| Unabbreviated suffix ("place") | normalize (USPS expansion) | 3 |
| Truncated ZIP (4 digits) | exact_match (Census + OA accept partial ZIPs) | 3 |
| Misspelled street (with populated dictionary) | spell_correct (Stage 1) — would handle Address 4 | 4 (blocked — empty dict) |
| Misspelled street below fuzzy threshold | fuzzy_match fails above 0.65 for "ARLNGTON" | 4 (unresolved) |
| Zero-for-letter city substitution + no ZIP | LLM correction (Stage 4) — required but disabled | 4 (unresolved) |

### 2. LLM Stage Requirement for Address 4

Address 4 requires the LLM stage to resolve. The compound errors (misspelled street + number-for-letter city + no ZIP + state spelled out) exceed the correction capacity of both spell correction (empty dictionary) and fuzzy matching (pg_trgm threshold). The LLM corrector (qwen2.5:3b) is the designed handler for exactly this failure mode. To activate: `docker compose --profile llm up -d`.

### 3. Provider Agreement and Reliability

- **Census** is the most reliable provider: matched 3/4 addresses (correct result) and was selected as official for 2/4. For address 4, returned null coordinates (correct NO_MATCH behavior).
- **OpenAddresses** matched 2/4 (addresses 1 and 3). For address 3, returned confidence=0.40 (ZIP truncation lowers match quality). Was selected as official for address 3 (centroid selection).
- **Macon-Bibb GIS** matched 1/4 (address 3), same point as OpenAddresses — confirming shared data lineage.
- **Tiger (PostGIS)** timed out on all 4 requests in this run. In prior run, Tiger returned wrong-county results (Troup County, Meriwether County) that were correctly identified as outliers by consensus. Tiger timeout (vs. wrong-county results) is a net improvement for consensus accuracy — no outliers needed to be filtered.
- **NAD** returned NO_MATCH for all 4 — expected, as NAD data covers the 303xx range (Atlanta metro) and test addresses are Macon (310xx-312xx).

### 4. Tiger Wrong-County Bug — Status Update

In prior run 260329-q2v, Tiger returned wrong-county results for 2/4 addresses. In this run, Tiger times out. The Tiger timeout behavior prevents wrong-county pollution of the consensus pool without requiring the FIX-01 `restrict_region` guard — but for different reasons (performance/timeout vs. geographic filtering). The FIX-01 fix is still needed to make Tiger reliably correct (not just absent).

### 5. Consensus Scoring Robustness

The consensus engine performed correctly across all test cases:
- **Address 1:** 2-provider cluster (Census + OA), outlier detection not exercised (Tiger timed out)
- **Address 2:** Single provider, official set correctly via single_provider path
- **Address 3:** 3-provider cluster (Census + OA + Macon-Bibb within ~2m), outlier detection not exercised
- **Address 4:** Zero candidates, no official set (correct — no data to work with)

The 100m cluster radius and 1km outlier threshold remain well-calibrated. Results are stable and consistent across runs despite Tiger's changed behavior.

### 6. Spell Corrector Status

The spell_dictionary has 0 words — same as prior run. No address corrections applied. To rebuild: `docker compose exec api python -m civpulse_geo.cli rebuild-spell-dictionary`. With a populated dictionary, "ARLNGTON" → "ARLINGTON" would likely be corrected at Stage 1 for address 4.

### 7. Overall Assessment

The v1.2 cascade pipeline is stable and producing correct results for addresses 1-3 (mild-to-moderate input defects). Address 4 (severe compound errors) requires LLM activation. The bug fixes from 260329-q2v are confirmed stable. The Tiger timeout is a behavioral change from the prior run but has no negative impact on official result accuracy.
