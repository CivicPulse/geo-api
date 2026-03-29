# Deferred Items — Phase 09 Tiger Provider

## Out-of-Scope Pre-existing Failures

**Discovered during:** 09-02 execution (Task 1 and Task 2 full suite runs)
**File:** `tests/test_import_cli.py` — 10 tests failing
**Root cause:** Missing fixture file `data/SAMPLE_Address_Points.geojson`
**Status:** Pre-existing before 09-02 work (verified by stashing changes and re-running)
**Action required:** Restore or mock the `SAMPLE_Address_Points.geojson` fixture file in a future plan
**Impact:** None on current phase — all Tiger and new CLI tests pass
