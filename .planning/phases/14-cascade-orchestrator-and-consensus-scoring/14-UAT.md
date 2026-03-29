---
status: complete
phase: 14-cascade-orchestrator-and-consensus-scoring
source: [14-01-SUMMARY.md, 14-02-SUMMARY.md, 14-03-SUMMARY.md]
started: 2026-03-29T17:18:00Z
updated: 2026-03-29T17:18:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cascade config settings
expected: Settings includes cascade_enabled (default True), 4 timeout budget fields, 6 provider weight fields — all env-var readable
result: pass
method: automated — config import verification confirms cascade_enabled=True, all weight fields present

### 2. set_by_stage migration
expected: Alembic migration h8e5f1g4a7b3 adds nullable set_by_stage column to official_geocoding table
result: pass
method: automated — file exists, down_revision=g7d4e0f3a6b2 chains correctly

### 3. CascadeTraceStage and schema extensions
expected: GeocodeResponse has cascade_trace and would_set_official fields; GeocodeProviderResult has is_outlier field
result: pass
method: automated — import verification of CascadeTraceStage, GeocodeResponse, GeocodeProviderResult successful

### 4. CascadeOrchestrator 6-stage pipeline
expected: CascadeOrchestrator.run() executes normalize, exact match (parallel), fuzzy, consensus, auto-set, commit stages
result: pass
method: automated — pytest tests/test_cascade.py (all cascade tests pass)

### 5. Haversine distance and consensus clustering
expected: haversine_m() computes great-circle distance; run_consensus() clusters within 100m, flags outliers at 1km
result: pass
method: automated — pytest tests/test_cascade.py includes haversine and clustering tests

### 6. Provider weight lookup
expected: get_provider_weight() maps provider names to config weights with 0.50 fallback
result: pass
method: automated — pytest tests/test_cascade.py includes weight lookup tests

### 7. GeocodingService cascade dispatcher
expected: geocode() delegates to CascadeOrchestrator when cascade_enabled=True, falls back to _legacy_geocode when False
result: pass
method: automated — pytest tests/test_geocoding_service.py (cascade dispatch tests pass)

### 8. API dry_run and trace params
expected: POST /geocode accepts ?dry_run=true and ?trace=true query params; returns cascade_trace and would_set_official fields
result: pass
method: automated — pytest tests/test_geocoding_api.py (dry_run and trace param tests pass)

### 9. is_outlier in API response
expected: GeocodeProviderResult includes is_outlier=True for providers flagged by consensus as >1km from winning cluster
result: pass
method: automated — pytest tests/test_geocoding_api.py includes outlier tests

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
