# Deferred Items — Phase 07 Pipeline Infrastructure

## Pre-existing Test Data Failures

**File:** tests/test_import_cli.py
**Tests affected:** TestLoadGeoJSON (4 tests), TestLoadKML (3 tests), TestImportGISCommand (3 tests, partially)

**Issue:** These tests require sample data files that were never committed to the repository:
- `data/SAMPLE_Address_Points.geojson`
- `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml`

The `data/` directory is gitignored and the SAMPLE_ files don't exist on this machine.

**Impact:** 10 tests fail when the full test suite is run. The CLI logic itself works correctly
(verified by TestImportGISCommand::test_import_unsupported_format passing).

**Resolution needed:** Either:
1. Create minimal sample test fixtures in the tests/ directory (not data/)
2. Add pytest.skip() guards when sample files don't exist
3. Mock the file loading in CLI tests

**Discovered by:** Plan 07-02 task 2 (full test suite verification)
**Priority:** Medium (pre-existing, not caused by current work)
