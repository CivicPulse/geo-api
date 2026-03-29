---
status: complete
phase: 08-openaddresses-provider
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-03-29T03:15:00Z
updated: 2026-03-29T03:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. OA geocoding provider registered at startup
expected: Server startup logs show "OpenAddresses provider registered". Provider appears in local_results for geocode requests.
result: pass
method: automated — startup logs confirm `OpenAddresses provider registered`; geocode response includes `openaddresses` in local_results

### 2. OA geocoding returns result for loaded data
expected: POST /geocode with address in loaded OA dataset returns openaddresses result with lat/lng, location_type, and accuracy-mapped confidence score.
result: pass
method: automated — `POST /geocode {"address":"478 MULBERRY ST MACON GA 31201"}` returned openaddresses result: lat=32.8369081, lng=-83.6257726, type=APPROXIMATE, confidence=0.4

### 3. OA validation provider registered
expected: OA validation provider registered in startup, appears in local_candidates for validate requests.
result: pass
method: automated — validate response includes `openaddresses` in local_candidates array

### 4. OA provider is_local=True
expected: OA providers have is_local=True, results bypass DB cache writes.
result: pass
method: automated — `pytest tests/test_oa_provider.py::TestOAGeocodingProvider::test_is_local_true` and `TestOAValidationProvider::test_is_local_true` both pass

### 5. load-oa CLI accepts .geojson.gz files
expected: `geo-import load-oa --help` shows FILE argument. CLI validates file existence and .geojson.gz extension.
result: pass
method: automated — help output confirms; `pytest tests/test_load_oa_cli.py::TestLoadOaCli` 4/4 passed

### 6. load-oa imports data with upsert
expected: load-oa streams NDJSON from gzip, parses street components via usaddress, upserts via ON CONFLICT. openaddresses_points table populated.
result: pass
method: automated — `SELECT count(*) FROM openaddresses_points` returns 67,730 rows; `pytest tests/test_load_oa_cli.py::TestLoadOaImport::test_load_oa_with_mock_ndjson` passes

### 7. OA empty-string-to-None normalization
expected: Empty string properties in OA features are converted to None in parsed output.
result: issue
reported: "test_parse_oa_feature_empty_strings_to_none fails: accuracy field returns 'parcel' instead of None when empty string. Code at cli/__init__.py:571 uses `props.get('accuracy') or 'parcel'` — intentional default for OA data, but test expects None."
severity: minor

### 8. All Phase 08 unit tests pass
expected: All OA provider and load-oa CLI tests pass.
result: issue
reported: "40/41 passed, 1 failed: test_parse_oa_feature_empty_strings_to_none (accuracy defaults to 'parcel' not None). Test expectation conflicts with intentional default behavior."
severity: minor

## Summary

total: 8
passed: 6
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "Empty string accuracy in OA features should normalize to None like other fields"
  status: failed
  reason: "test_parse_oa_feature_empty_strings_to_none fails — accuracy field defaults to 'parcel' (line 571: `props.get('accuracy') or 'parcel'`) instead of None. Other fields use `val or None` pattern but accuracy has intentional default."
  severity: minor
  test: 7
  root_cause: "Design mismatch: _parse_oa_feature gives accuracy a fallback default of 'parcel' for DB insert, but test expects the same or-None pattern as other fields. Either update test to expect 'parcel' for empty accuracy, or split accuracy handling to store None and let the provider layer apply the default."
  artifacts:
    - path: "src/civpulse_geo/cli/__init__.py"
      issue: "Line 571: accuracy defaults to 'parcel' on empty/None — test expects None"
    - path: "tests/test_load_oa_cli.py"
      issue: "Line 134: assert row['accuracy'] is None — conflicts with intentional default"
  missing:
    - "Align test expectation with code behavior: either change test line 134 to `assert row['accuracy'] == 'parcel'` or change code to `accuracy: props.get('accuracy') or None` and handle default in provider layer"
  debug_session: ""
