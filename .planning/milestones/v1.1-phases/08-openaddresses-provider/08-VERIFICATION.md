---
phase: 08-openaddresses-provider
verified: 2026-03-22T20:30:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 8: OpenAddresses Provider Verification Report

**Phase Goal:** Users can geocode and validate addresses against loaded OpenAddresses data, with results returned directly without DB caching
**Verified:** 2026-03-22T20:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | OAGeocodingProvider.geocode() returns GeocodingResult with lat/lng from matched OA row | VERIFIED | Lines 200-207 in openaddresses.py; ST_Y/ST_X in SELECT at lines 97-98; 3 rooftop/parcel/centroid/interpolation tests pass |
| 2 | OAGeocodingProvider.geocode() returns NO_MATCH with confidence=0.0 when no rows match | VERIFIED | Lines 172-180 in openaddresses.py; test_geocode_no_match and test_geocode_no_match_on_parse_failure pass |
| 3 | OAValidationProvider.validate() returns ValidationResult with USPS-normalized fields from matched OA row | VERIFIED | Lines 309-342 in openaddresses.py; scourgify re-normalization on matched row; test_validate_match_returns_confidence_1 passes |
| 4 | OAValidationProvider.validate() returns confidence=0.0 with empty strings on no match | VERIFIED | Lines 274-288 in openaddresses.py; test_validate_no_match passes |
| 5 | Accuracy mapping: rooftop=1.0, parcel=0.8, interpolation=0.5, centroid=0.4, empty=0.1 | VERIFIED | ACCURACY_MAP lines 36-41, DEFAULT_ACCURACY line 42; TestAccuracyMapping: 5/5 assertions pass |
| 6 | OA providers registered in app.state.providers and app.state.validation_providers at startup | VERIFIED | main.py lines 21 and 24; import verified at line 12; uv run python -c "from civpulse_geo.main import app" exits 0 |
| 7 | load-oa with .geojson.gz populates openaddresses_points in 1000-row batches | VERIFIED | OA_BATCH_SIZE=1000 at cli line 25; _upsert_oa_batch with ON CONFLICT uq_oa_source_hash; test_load_oa_with_mock_ndjson passes |
| 8 | Malformed features / missing coordinates are skipped and counted, not halted | VERIFIED | _parse_oa_feature lines 296-313; test_parse_oa_feature_missing_coordinates and test_parse_oa_feature_no_hash pass |
| 9 | Empty strings in OA data converted to NULL during import | VERIFIED | `val or None` pattern in _parse_oa_feature lines 320-329; test_parse_oa_feature_empty_strings_to_none passes |
| 10 | Street suffix parsed from OA street field using usaddress StreetNamePostType | VERIFIED | _parse_street_components lines 275-284; test_parse_street_components_with_suffix passes |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/civpulse_geo/providers/openaddresses.py` | OAGeocodingProvider and OAValidationProvider classes | VERIFIED | 361 lines; both classes fully implemented, non-stub |
| `tests/test_oa_provider.py` | Unit tests for both OA providers | VERIFIED | 433 lines, 28 tests, all pass (28 passed in 0.13s) |
| `src/civpulse_geo/main.py` | OA providers registered in lifespan | VERIFIED | 40 lines; imports on line 12, registrations on lines 21+24 |
| `src/civpulse_geo/cli/__init__.py` | load-oa functional NDJSON import logic | VERIFIED | 454 lines; stub text "data loading implemented in Phase 8" is absent; full import logic present |
| `tests/test_load_oa_cli.py` | Tests for actual import behavior | VERIFIED | 238 lines, 13 tests, all pass (13 passed in 0.24s) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/civpulse_geo/providers/openaddresses.py` | `openaddresses_points` table | `select(OpenAddressesPoint)` with ST_Y/ST_X | VERIFIED | Lines 94-109 in openaddresses.py; stmt selects OpenAddressesPoint + func.ST_Y + func.ST_X |
| `src/civpulse_geo/main.py` | `src/civpulse_geo/providers/openaddresses.py` | import + instantiation in lifespan | VERIFIED | Line 12: `from civpulse_geo.providers.openaddresses import OAGeocodingProvider, OAValidationProvider`; lines 21+24: `OAGeocodingProvider(AsyncSessionLocal)`, `OAValidationProvider(AsyncSessionLocal)` |
| `src/civpulse_geo/cli/__init__.py` | `openaddresses_points` table | raw SQL INSERT with ON CONFLICT uq_oa_source_hash | VERIFIED | Lines 337-366; SQL contains `ON CONFLICT ON CONSTRAINT uq_oa_source_hash DO UPDATE` and `RETURNING (xmax = 0) AS was_inserted` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| OA-01 | 08-01-PLAN, 08-02-PLAN | User can geocode an address against loaded OpenAddresses data | SATISFIED | OAGeocodingProvider queries openaddresses_points; load-oa populates table; full end-to-end path implemented |
| OA-02 | 08-01-PLAN | User can validate an address against OpenAddresses records | SATISFIED | OAValidationProvider with scourgify re-normalization on matched row; returns ValidationResult |
| OA-03 | 08-01-PLAN | OA geocoding returns location_type based on accuracy field (rooftop/parcel/interpolated/centroid) | SATISFIED | ACCURACY_MAP with all 4 keys; DEFAULT_ACCURACY=("APPROXIMATE", 0.1) for empty/unknown; all 5 cases covered by tests |
| OA-04 | 08-01-PLAN | OA provider registered automatically when staging table has data | SATISFIED | Providers registered unconditionally in lifespan (design decision: return NO_MATCH when table empty rather than conditional registration); plan explicitly notes "no table row count check" |

No orphaned requirements found. All Phase 8 requirement IDs (OA-01 through OA-04) are claimed by plan frontmatter and verified in the codebase.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/civpulse_geo/cli/__init__.py` | 451 | `# Phase 10 implements data loading; this stub confirms wiring` (in load-nad) | Info | load-nad is intentionally stubbed for Phase 10; no impact on Phase 8 goal |

No blockers or warnings found in Phase 8 files. The load-nad stub is a planned Phase 10 artifact, not a Phase 8 issue.

---

### Human Verification Required

None. All observable truths are verifiable programmatically through:
- Source code structure and content
- Test suite execution (28 + 13 = 41 tests passing)
- Import verification (main.py imports cleanly)

---

### Gaps Summary

No gaps. All must-haves from both plan frontmatters are verified against the actual codebase.

**Test execution summary:**
- `tests/test_oa_provider.py`: 28 passed in 0.13s
- `tests/test_load_oa_cli.py`: 13 passed in 0.24s
- Full suite (excluding pre-existing failure in test_import_cli.py): 226 passed in 1.49s
- Pre-existing failure (`tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features`) is unrelated to Phase 8 — references a missing sample file at `data/SAMPLE_Address_Points.geojson` that predates this phase

**OA-04 design note:** The requirement says "registered automatically when staging table has data." The implemented design registers providers unconditionally — they return NO_MATCH when the table is empty rather than guarding on row count. This was an explicit locked decision in the plan (`success_criteria` line: "Providers registered in main.py lifespan unconditionally (no table row count check)"). The requirement is satisfied at the behavior level: once `load-oa` populates the table, geocoding results come from OA data.

---

_Verified: 2026-03-22T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
