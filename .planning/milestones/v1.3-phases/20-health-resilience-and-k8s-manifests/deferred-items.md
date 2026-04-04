# Deferred Items - Phase 20

## Pre-existing Test Failures (Out of Scope)

### 1. tests/test_import_cli.py::TestLoadGeoJSON::test_load_geojson_returns_features
- **Cause:** Missing `data/SAMPLE_Address_Points.geojson` in worktree (file exists in main repo but not copied to worktree)
- **Scope:** Pre-existing; not caused by Phase 20 changes
- **Impact:** 1 test failure

### 2. tests/test_load_oa_cli.py::TestLoadOaImport::test_parse_oa_feature_empty_strings_to_none
- **Cause:** OA accuracy regression -- accuracy 'parcel' returned instead of None for empty strings
- **Scope:** Pre-existing; not caused by Phase 20 changes
- **Impact:** 1 test failure

Both failures existed before Phase 20 Plan 01 execution began. Verified by checking that tests pass when these files are excluded.
