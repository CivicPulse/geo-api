# E2E Provider Test Report

**Date:** 2026-03-29
**Environment:** Local Docker Compose (geo-api-api + geo-api-db)
**API:** http://localhost:8042
**Providers tested:** Census, OpenAddresses, PostGIS Tiger, NAD, Macon-Bibb, Scourgify

## Test Design

Four addresses with progressively degraded input quality to stress-test normalization, matching, and error handling across all providers:

| # | Address | Input Defects |
|---|---------|---------------|
| 1 | `548 Moss Hl, MacOn GA, 31204` | Abbreviated street suffix ("Hl"), mixed case ("MacOn") |
| 2 | `700 poplar st, Macon, ga, 31201` | All lowercase, extra comma |
| 3 | `659 Arlington place, Macon, ga 3120` | Truncated zip (4 digits), unabbreviated suffix |
| 4 | `669 Arlngton lace, Macon Georgia` | Misspelled street ("Arlngton"), misspelled suffix ("lace" for "Place"), no zip, state spelled out |

---

## Provider Data Coverage

Before interpreting results, note each provider's geographic coverage in this environment:

| Provider | Coverage | Rows | Zip Prefixes |
|----------|----------|------|--------------|
| Census | National (external API) | n/a | All |
| OpenAddresses | Bibb County GA | 67,730 | 310xx, 312xx |
| PostGIS Tiger | GA statewide (address interpolation) | 1.7M addr, 1.9M edges | All GA |
| NAD | Atlanta metro GA | 206,698 | 303xx only |
| Macon-Bibb | Bibb County GA | 67,730 | 312xx |
| Scourgify | n/a (validation only, pure normalization) | n/a | All |

**NAD has no Macon-area data** (312xx zips) so all NAD NO_MATCH results for these addresses are expected and not defects.

---

## Address 1: `548 Moss Hl, MacOn GA, 31204`

**Defects:** Abbreviated suffix, mixed case

### Geocode Results

| Provider | Confidence | Location Type | Latitude | Longitude | Verdict |
|----------|-----------|---------------|----------|-----------|---------|
| Census | 0.80 | RANGE_INTERPOLATED | 32.866817 | -83.675862 | PASS |
| OpenAddresses | 0.80 | APPROXIMATE | 32.867320 | -83.676507 | PASS |
| PostGIS Tiger | 0.80 | RANGE_INTERPOLATED | **32.515201** | **-84.985742** | **FAIL** |
| NAD | 0.00 | NO_MATCH | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.80 | APPROXIMATE | 32.867320 | -83.676508 | PASS |

### Validation Results

| Provider | Confidence | Normalized Address | DPV | Verdict |
|----------|-----------|-------------------|-----|---------|
| Scourgify | 1.00 | 548 MOSS HL MACON GA 31204 | No | PASS |
| OpenAddresses | 1.00 | 548 MOSS HL MACON GA 31204 | No | PASS |
| PostGIS Tiger | 1.00 | 548 Moss Hl MacOn GA 31204 | No | PASS (parsed ok) |
| NAD | 0.00 | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 1.00 | 548 MOSS HILL MACON GA 31204 | No | PASS (expanded abbreviation) |

### Analysis

- **Census, OA, and Macon-Bibb agree** on coordinates (~32.867, -83.676), confirming 548 Moss Hill is a real Bibb County address.
- **PostGIS Tiger returned wrong coordinates** (32.515, -84.986) — approximately 50 miles southwest in Muscogee County. Tiger matched a "Moss Hill" street in a different GA county because the abbreviated suffix "Hl" and lack of city-level disambiguation caused it to pick the wrong candidate. This is a **Tiger address disambiguation defect**.
- **Macon-Bibb expanded "HL" to "HILL"** in validation — it stores the full suffix in its source data and returned the canonical form. Scourgify preserved the abbreviation as-is.

---

## Address 2: `700 poplar st, Macon, ga, 31201`

**Defects:** All lowercase, extra comma after city

### Geocode Results

| Provider | Confidence | Location Type | Latitude | Longitude | Verdict |
|----------|-----------|---------------|----------|-----------|---------|
| Census | 0.80 | RANGE_INTERPOLATED | 32.836028 | -83.631827 | PASS |
| OpenAddresses | 0.00 | NO_MATCH | - | - | **MISS** (data gap) |
| PostGIS Tiger | 0.88 | RANGE_INTERPOLATED | 32.835963 | -83.631802 | PASS |
| NAD | 0.00 | NO_MATCH | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.00 | NO_MATCH | - | - | **MISS** (data gap) |

### Validation Results

| Provider | Confidence | Normalized Address | DPV | Verdict |
|----------|-----------|-------------------|-----|---------|
| Scourgify | 1.00 | 700 POPLAR ST MACON GA 31201 | No | PASS |
| OpenAddresses | 0.00 | - | - | MISS (data gap) |
| PostGIS Tiger | 1.00 | 700 poplar St Macon GA 31201 | No | PASS |
| NAD | 0.00 | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.00 | - | - | MISS (data gap) |

### Analysis

- **Census and Tiger agree** on coordinates (~32.836, -83.632), confirming this is a valid address in downtown Macon.
- **Tiger had the highest confidence** (0.88) of any result in the entire test suite — the Poplar St address range matched cleanly.
- **OA and Macon-Bibb both missed** this address. This is a **data coverage gap**, not a matching defect — 700 Poplar St simply isn't in either point dataset. Point-based datasets only contain addresses that were explicitly surveyed or imported from local GIS systems.
- Lowercase input and extra comma were handled correctly by all providers via scourgify normalization.
- **Note:** This result was returned from cache (`cache_hit: true`) — the geocode endpoint was called for this address in a prior test session.

---

## Address 3: `659 Arlington place, Macon, ga 3120`

**Defects:** Truncated zip (4 digits instead of 5), unabbreviated suffix ("place" instead of "PL")

### Geocode Results

| Provider | Confidence | Location Type | Latitude | Longitude | Verdict |
|----------|-----------|---------------|----------|-----------|---------|
| Census | 0.80 | RANGE_INTERPOLATED | 32.837504 | -83.641804 | PASS |
| OpenAddresses | 0.00 | NO_MATCH | - | - | **FAIL** (zip mismatch) |
| PostGIS Tiger | 0.80 | RANGE_INTERPOLATED | **32.059796** | **-84.182321** | **FAIL** |
| NAD | 0.00 | NO_MATCH | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.00 | NO_MATCH | - | - | **FAIL** (zip mismatch) |

### Validation Results

| Provider | Confidence | Normalized Address | DPV | Verdict |
|----------|-----------|-------------------|-----|---------|
| Scourgify | 1.00 | 659 ARLINGTON PL MACON GA 3120 | No | PASS (normalized suffix) |
| OpenAddresses | 0.00 | - | - | FAIL (zip mismatch) |
| PostGIS Tiger | 1.00 | 659 Arlington Pl Macon GA 3120 | No | PASS (parsed ok) |
| NAD | 0.00 | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.00 | - | - | FAIL (zip mismatch) |

### Analysis

- **Census handled the truncated zip gracefully** and returned correct Macon coordinates (32.838, -83.642).
- **PostGIS Tiger returned wrong coordinates again** (32.060, -84.182) — approximately 60 miles south in Dooly County. Same disambiguation defect as Address 1: an "Arlington Pl" exists in another GA county and Tiger picked the wrong one because the truncated zip didn't provide enough disambiguation.
- **OA and Macon-Bibb both failed due to exact zip matching.** These providers query with `WHERE zip_code = :postal_code`, so "3120" != "31201" or "31206". This is a **truncated zip handling defect** — the matching logic should either:
  - Prefix-match truncated zips (WHERE zip_code LIKE '3120%')
  - Ignore zip in matching when it's clearly truncated (< 5 digits)
  - Fall back to city+state matching when zip doesn't match
- Scourgify correctly normalized "place" to "PL" but **preserved the truncated zip as-is** — it doesn't validate zip code length or correctness.

---

## Address 4: `669 Arlngton lace, Macon Georgia`

**Defects:** Misspelled street name ("Arlngton" missing 'i'), misspelled suffix ("lace" for "Place"), no zip code, state spelled out

### Geocode Results

| Provider | Confidence | Location Type | Latitude | Longitude | Verdict |
|----------|-----------|---------------|----------|-----------|---------|
| Census | 0.00 | NO_MATCH | - | - | FAIL (no fuzzy match) |
| OpenAddresses | 0.00 | NO_MATCH | - | - | FAIL (no fuzzy match) |
| PostGIS Tiger | 0.00 | NO_MATCH | - | - | FAIL (no fuzzy match) |
| NAD | 0.00 | NO_MATCH | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.00 | NO_MATCH | - | - | FAIL (no fuzzy match) |

### Validation Results

| Provider | Confidence | Normalized Address | DPV | Verdict |
|----------|-----------|-------------------|-----|---------|
| Scourgify | 1.00 | 669 ARLNGTON LACE MACON GA | No | **FALSE POSITIVE** |
| OpenAddresses | 0.00 | - | - | FAIL (no fuzzy match) |
| PostGIS Tiger | 1.00 | 669 Arlngton lace Macon GA | No | **FALSE POSITIVE** |
| NAD | 0.00 | - | - | EXPECTED (no coverage) |
| Macon-Bibb | 0.00 | - | - | FAIL (no fuzzy match) |

### Analysis

- **Total geocode failure across all 5 providers.** No provider has fuzzy/phonetic matching capability. The misspelled "Arlngton" doesn't match any street name in any dataset.
- **Scourgify and Tiger both returned confidence 1.00 for validation despite obvious typos.** This is a **false positive** — both tools parse address structure (number + street + city + state) but do not verify that the street name is real. A confidence of 1.00 implies the address is valid when it clearly isn't.
- Scourgify correctly expanded "Georgia" to "GA" but did not flag the misspelled street or suffix.
- The **missing zip code** is an additional challenge — OA and Macon-Bibb require zip for matching, and without it they'd fail even with correct spelling.

---

## Cross-Cutting Issues

### Issue 1: Tiger County Disambiguation (CRITICAL)

**Severity:** Critical
**Affected:** Addresses 1, 3

PostGIS Tiger's `geocode()` function returned coordinates in the wrong county for 2 of 4 addresses (50% wrong-county rate). When a street name exists in multiple GA counties, Tiger fails to use zip code or city name to disambiguate correctly. The abbreviated suffix ("Hl") and truncated zip ("3120") worsen the problem.

**Root cause:** Tiger's address interpolation relies on the `normalize_address()` parser to identify city/zip, then uses spatial joins against `tiger.place` and `tiger.county` to constrain the search. When the zip is truncated or the suffix is non-standard, the constraint weakens and it falls back to the first matching street range statewide.

**Impact:** Any address with a common street name ("Main", "Oak", "Arlington") in a statewide Tiger dataset risks returning coordinates in the wrong county.

### Issue 2: Exact Zip Matching in Local Providers (HIGH)

**Severity:** High
**Affected:** Address 3

OpenAddresses and Macon-Bibb both use `WHERE zip_code = :postal_code` for exact matching. A truncated zip ("3120") or mistyped zip ("31021" for "31201") produces NO_MATCH even though the address exists in the dataset and would match on street+city+state alone.

**Impact:** Any typo or truncation in the zip code field causes a complete match failure for OA and Macon-Bibb, even when the rest of the address is correct.

### Issue 3: No Fuzzy/Phonetic Matching (MEDIUM)

**Severity:** Medium
**Affected:** Address 4

No provider performs fuzzy string matching, Soundex, Metaphone, or Levenshtein distance matching on street names. "Arlngton" (edit distance 1 from "Arlington") produces zero hits across all 5 providers.

**Impact:** Real-world address input from forms, OCR, or voice transcription frequently contains minor misspellings. The current system has zero tolerance for these errors.

### Issue 4: Scourgify False Positive Validation (MEDIUM)

**Severity:** Medium
**Affected:** Address 4

Scourgify returns confidence 1.00 for any parseable address structure regardless of whether the address exists. "669 ARLNGTON LACE" is confidently validated even though "Arlngton" is not a real street and "Lace" is not a real suffix. Scourgify is a structural parser, not an address verifier.

**Impact:** Users relying on validation confidence to determine address quality will get false positives for structurally well-formed but factually wrong addresses.

### Issue 5: Street Name Normalization Mismatch (LOW)

**Severity:** Low
**Affected:** Observed in prior testing (not directly in these 4 addresses)

Scourgify normalizes street suffixes per USPS Pub 28 ("Falls" -> "FLS", "Place" -> "PL"), but NAD and OA store original source data with full suffix names. The matching query uses `street_name` only (not `street_suffix`), so when scourgify moves the suffix out of the street name, the remaining `street_name` ("BEAVER" instead of "BEAVER FALLS") doesn't match the source data.

**Impact:** Multi-word street names where the last word is a valid USPS suffix may fail to match in NAD and OA even when the address exists in the dataset.

---

## Provider Scorecard

Scoring: PASS = correct result, MISS = data gap (expected), FAIL = incorrect behavior, FALSE POS = misleading positive

### Geocode

| Provider | Addr 1 | Addr 2 | Addr 3 | Addr 4 | Score |
|----------|--------|--------|--------|--------|-------|
| Census | PASS | PASS | PASS | FAIL | 3/4 |
| OpenAddresses | PASS | MISS | FAIL | FAIL | 1/3* |
| PostGIS Tiger | **FAIL** | PASS | **FAIL** | FAIL | 1/4 |
| NAD | MISS | MISS | MISS | MISS | n/a |
| Macon-Bibb | PASS | MISS | FAIL | FAIL | 1/3* |

*Scored against addresses in coverage area only

### Validate

| Provider | Addr 1 | Addr 2 | Addr 3 | Addr 4 | Score |
|----------|--------|--------|--------|--------|-------|
| Scourgify | PASS | PASS | PASS | FALSE POS | 3/4 |
| OpenAddresses | PASS | MISS | FAIL | FAIL | 1/3* |
| PostGIS Tiger | PASS | PASS | PASS | FALSE POS | 3/4 |
| NAD | MISS | MISS | MISS | MISS | n/a |
| Macon-Bibb | PASS | MISS | FAIL | FAIL | 1/3* |

### Provider Reliability Ranking (for clean Macon addresses)

1. **Census** — Most reliable across all input qualities. Handles abbreviations, truncated zips, and case variations. Only fails on misspellings.
2. **Macon-Bibb** — Reliable for addresses in its dataset. Good normalization (expands abbreviations). Fails on zip issues and data gaps.
3. **OpenAddresses** — Same reliability as Macon-Bibb for addresses in its dataset. Slightly different coverage.
4. **PostGIS Tiger** — **Least reliable for Macon addresses.** Wrong-county results are worse than NO_MATCH because they appear valid (confidence 0.80) but are factually wrong.
5. **NAD** — No Macon coverage in current dataset. Cannot be evaluated for this area.

---

## Recommendations

1. **Tiger result filtering:** Post-filter Tiger geocode results by checking if the returned coordinates fall within the expected city/county boundaries (using a PostGIS spatial query against `tiger.place` or `tiger.county`). Discard results outside the expected area.

2. **Zip prefix matching fallback:** When a zip code is < 5 digits, use `LIKE` prefix matching (`WHERE zip_code LIKE '3120%'`) instead of exact equality. This handles truncation and OCR errors.

3. **Fuzzy street matching:** Add Soundex or pg_trgm fuzzy matching as a fallback when exact street_name match returns 0 rows. PostgreSQL's `pg_trgm` extension supports `similarity()` and `%` operators with GiST indexes.

4. **Validation confidence semantics:** Consider reducing Scourgify confidence to < 1.0 (e.g., 0.5) to indicate "structurally valid but not address-verified." Reserve 1.0 confidence for providers that confirm the address exists in a real dataset.

5. **Cross-provider consensus scoring:** When multiple providers return results, compute a consensus score. If Tiger returns coordinates 50+ miles from Census and Macon-Bibb, flag it as low-confidence rather than reporting all three as equally valid.
