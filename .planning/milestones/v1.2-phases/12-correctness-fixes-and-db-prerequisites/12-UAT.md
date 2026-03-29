---
status: complete
phase: 12-correctness-fixes-and-db-prerequisites
source: [12-01-SUMMARY.md, 12-02-SUMMARY.md]
started: 2026-03-29T17:18:00Z
updated: 2026-03-29T17:18:00Z
---

## Current Test

[testing complete]

## Tests

### 1. _parse_input_address 5-tuple expansion
expected: _parse_input_address returns (number, name, postal, suffix, directional) 5-tuple with suffix/directional extracted from usaddress tokens
result: pass
method: automated — pytest tests/test_oa_provider.py::TestParseInputAddress (5 tests pass)

### 2. Suffix-aware WHERE clauses in providers
expected: OA, NAD, and Macon-Bibb providers apply street suffix filtering when suffix is present in parsed address, omit condition when None
result: pass
method: automated — pytest tests/test_oa_provider.py tests/test_nad_provider.py tests/test_macon_bibb_provider.py (146 tests pass)

### 3. ZIP prefix fallback
expected: When exact ZIP match fails, providers try 4-digit prefix then 3-digit prefix LIKE match before returning NO_MATCH
result: pass
method: automated — pytest provider tests include zip prefix fallback assertions (146 tests pass)

### 4. Tiger county spatial post-filter
expected: Tiger geocode results are validated via ST_Contains against county geometry; points outside expected county are filtered out
result: pass
method: automated — pytest tests/test_tiger_provider.py includes county filter and state FIPS tests

### 5. Confidence constants corrected
expected: SCOURGIFY_CONFIDENCE=0.3, TIGER_VALIDATION_CONFIDENCE=0.4 (not hardcoded 1.0)
result: pass
method: automated — import verification confirms constants; pytest test assertions validate correct values

### 6. GIN trigram index migration
expected: Alembic migration f6c3d9e2b5a1 creates pg_trgm extension and GIN indexes on OA and NAD street_name columns
result: pass
method: automated — file exists, revision chain verified (down_revision=e5b2a1d3f4c6)

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
