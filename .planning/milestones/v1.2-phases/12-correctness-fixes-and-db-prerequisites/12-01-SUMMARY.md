---
phase: 12-correctness-fixes-and-db-prerequisites
plan: "01"
subsystem: local-providers
tags: [fix, suffix-matching, zip-prefix, openaddresses, nad, macon-bibb, tests]
dependency_graph:
  requires: []
  provides: [FIX-02, FIX-03]
  affects: [openaddresses-provider, nad-provider, macon-bibb-provider]
tech_stack:
  added: []
  patterns:
    - "_parse_input_address returns 5-tuple (number, name, postal, suffix, directional)"
    - "suffix-aware WHERE clause using unpacking pattern in SQLAlchemy .where()"
    - "progressive zip prefix fallback (4-digit then 3-digit LIKE match)"
key_files:
  created: []
  modified:
    - src/civpulse_geo/providers/openaddresses.py
    - src/civpulse_geo/providers/nad.py
    - src/civpulse_geo/providers/macon_bibb.py
    - tests/test_oa_provider.py
    - tests/test_nad_provider.py
    - tests/test_macon_bibb_provider.py
decisions:
  - "_parse_input_address 5-tuple: added street_suffix (StreetNamePostType) and street_directional (StreetNamePostDirectional) as positions 4 and 5"
  - "Suffix condition uses tuple unpacking in .where() so it is omitted entirely when suffix is None — no NULL comparison needed"
  - "Zip prefix ordering uses lexicographic .asc() on the zip column — groups adjacent codes naturally without integer math"
metrics:
  duration_seconds: 470
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_modified: 6
---

# Phase 12 Plan 01: Suffix Matching and ZIP Prefix Fallback Summary

**One-liner:** Expanded `_parse_input_address()` to 5-tuple with suffix/directional, added suffix-aware WHERE conditions and progressive ZIP prefix fallback to all three local providers (OA, NAD, Macon-Bibb).

## What Was Built

### Task 1: Expand `_parse_input_address`, add suffix matching and zip prefix fallback

**`_parse_input_address()` expansion** in `openaddresses.py`:
- Return type changed from `tuple[str | None, str | None, str | None]` to `tuple[str | None, str | None, str | None, str | None, str | None]`
- Added `street_suffix = tokens.get("StreetNamePostType")` and `street_directional = tokens.get("StreetNamePostDirectional")`
- All error paths return `(None, None, None, None, None)`

**Suffix matching (FIX-03)** added to all 6 `_find_*_match` functions:
- `_find_oa_match()`, `_find_oa_fuzzy_match()` in `openaddresses.py`
- `_find_nad_match()`, `_find_nad_fuzzy_match()` in `nad.py`
- `_find_macon_bibb_match()`, `_find_macon_bibb_fuzzy_match()` in `macon_bibb.py`

Each function gained `street_suffix: str | None = None` parameter with conditional WHERE via tuple unpacking:
```python
*(
    [func.upper(Model.street_suffix) == street_suffix.upper()]
    if street_suffix
    else []
),
```

**ZIP prefix fallback functions (FIX-02)** added:
- `_find_oa_zip_prefix_match()` using `OpenAddressesPoint.postcode.like(f"{zip_prefix}%")`
- `_find_nad_zip_prefix_match()` using `NADPoint.zip_code.like(f"{zip_prefix}%")`
- `_find_macon_bibb_zip_prefix_match()` using `MaconBibbPoint.zip_code.like(f"{zip_prefix}%")`

Progressive prefix logic (D-05) in all 6 provider methods (geocode + validate for each provider):
- Try exact match → fuzzy match → 4-digit prefix → 3-digit prefix

**All 6 call sites** updated to destructure 5-tuple:
`street_number, street_name, postal_code, street_suffix, street_directional = _parse_input_address(address)`

### Task 2: Tests for suffix matching, zip prefix fallback, and 5-tuple parse

New `TestParseInputAddress` class in `test_oa_provider.py` (5 tests):
- `test_parse_input_address_returns_5_tuple`
- `test_parse_input_address_suffix_beaver_falls`
- `test_parse_input_address_directional`
- `test_parse_input_address_no_suffix`
- `test_parse_input_address_parse_failure_returns_5_none_tuple`
- `test_oa_geocode_zip_prefix_fallback`
- `test_oa_geocode_suffix_match`

New `TestNADZipPrefixFallback.test_nad_geocode_zip_prefix_fallback` in `test_nad_provider.py`.

New `TestMaconBibbZipPrefixFallback.test_macon_bibb_geocode_zip_prefix_fallback` in `test_macon_bibb_provider.py`.

All existing tests updated: 3-tuple mock return values `("num", "name", "zip")` → 5-tuple `("num", "name", "zip", None, None)`.

**Test count:** 91 existing + 9 new = 100 total, all passing.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 564471c | feat(12-01): expand _parse_input_address to 5-tuple, add suffix matching and zip prefix fallback |
| 2 | 832fd52 | test(12-01): update mocks to 5-tuple and add suffix/zip-prefix tests |

## Deviations from Plan

**1. [Rule 1 - Bug] Updated existing test mock return values**
- **Found during:** Task 2
- **Issue:** All existing tests that mocked `_parse_input_address` used 3-tuples. After expanding the function to return 5-tuples, these mocks would cause `ValueError: too many values to unpack` at the call sites.
- **Fix:** Global replace of all 3-tuple mock return values to 5-tuple `(num, name, zip, None, None)` in all 3 test files.
- **Files modified:** `tests/test_oa_provider.py`, `tests/test_nad_provider.py`, `tests/test_macon_bibb_provider.py`
- **Commit:** 832fd52

## Known Stubs

None — all implementations are functional. No placeholder data flows to any output path.

## Self-Check: PASSED

All 6 modified files found on disk. Both task commits verified in git log.
