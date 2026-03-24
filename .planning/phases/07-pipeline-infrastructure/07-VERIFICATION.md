---
phase: 07-pipeline-infrastructure
verified: 2026-03-22T16:00:00Z
re_verified: 2026-03-24T13:30:00Z
status: passed
score: 16/16 must-haves verified
re_verification: true
gaps_found_during_uat:
  - id: gap-1
    truth: "POST /geocode succeeds on first call for a new address"
    status: fixed
    root_cause: "db.flush() after new Address creation expires the geocoding_results relationship; accessing it triggers synchronous lazy-load which fails on asyncpg. Fix: await db.refresh(address, attribute_names=['geocoding_results']) after flush."
    fix_commit: pending
  - id: gap-2
    truth: "local_results from Tiger/OA/NAD providers appear in POST /geocode response"
    status: fixed
    root_cause: "api/geocoding.py only serialized result['results'] (ORM remote); result['local_results'] (Pydantic schema dataclasses) were computed but discarded. Fix: added local_provider_results serialization loop and local_results field to GeocodeResponse."
    fix_commit: pending
  - id: gap-3
    truth: "Remote provider cache is still used when local providers are registered"
    status: fixed
    root_cause: "Cache check condition 'not local_providers' was False whenever Tiger was registered, causing Census to be re-called on every request even when cached. Fix: moved local provider calls before cache check; cache check now only gates remote providers."
    fix_commit: pending
  - id: gap-4
    truth: "local_candidates from Tiger/OA/NAD providers appear in POST /validate response"
    status: fixed
    root_cause: "api/validation.py only serialized result['candidates'] (ORM remote); result['local_candidates'] (Pydantic schema dataclasses) were computed but discarded. Fix: added local_candidates serialization loop and local_candidates field to ValidateResponse."
    fix_commit: pending
  - id: gap-5
    truth: "OpenAddresses providers are not registered when openaddresses_points table is empty"
    status: fixed
    root_cause: "main.py unconditionally registered OAGeocodingProvider and OAValidationProvider regardless of table contents. Phase 8 requirement OA-04 states conditional registration. Fix: added _oa_data_available() check (same pattern as _nad_data_available) and conditional registration with warning log."
    fix_commit: pending
---

# Phase 7: Pipeline Infrastructure Verification Report

**Phase Goal:** The service layer correctly routes local providers through a bypass path that never writes to the DB cache, and PostGIS staging tables exist for local provider data
**Initial Verification:** 2026-03-22T16:00:00Z
**Re-verification (UAT):** 2026-03-24T13:30:00Z
**Status:** passed (after UAT gap fixes)

---

## Goal Achievement

### Observable Truths (Plan 01 — PIPE-01, PIPE-02)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GeocodingProvider.is_local defaults to False without existing providers needing changes | VERIFIED | `base.py` line 32-39: concrete `@property def is_local(self) -> bool: return False` — not abstract |
| 2 | ValidationProvider.is_local defaults to False without existing providers needing changes | VERIFIED | `base.py` line 97-105: identical concrete property on ValidationProvider |
| 3 | Calling geocode() with a local provider never writes to geocoding_results table | VERIFIED | `geocoding.py`: local providers handled in separate loop with no `pg_insert` call |
| 4 | Calling validate() with a local provider never writes to validation_results table | VERIFIED | `validation.py`: local providers handled in separate loop with no `pg_insert` call |
| 5 | Local providers still trigger Address upsert (addresses table write is NOT skipped) | VERIFIED | Address find-or-create runs before the local/remote split |
| 6 | Local provider results are returned in response even on remote cache hit | VERIFIED (FIXED) | Restructured service to call local providers before cache check; local_results included in cache-hit return dict |
| 7 | POST /geocode succeeds for new addresses (no MissingGreenlet) | VERIFIED (FIXED) | db.refresh(address, attribute_names=["geocoding_results"]) after flush prevents lazy-load |
| 8 | local_results in geocode response | VERIFIED (FIXED) | api/geocoding.py builds local_provider_results from result["local_results"] and includes in GeocodeResponse |
| 9 | local_candidates in validate response | VERIFIED (FIXED) | api/validation.py builds local_candidates from result["local_candidates"] and includes in ValidateResponse |
| 10 | OA providers not registered when openaddresses_points is empty | VERIFIED (FIXED) | _oa_data_available() check added; conditional registration with warning log |

---

## UAT Re-Verification Results (2026-03-24)

Automated tests via live API against running Docker stack:

| Test | Description | Result |
|------|-------------|--------|
| T1 | Health check | PASS |
| T2 | Startup warnings: OA absent, NAD absent, Tiger registered | PASS |
| T3 | POST /geocode cache miss — census+tiger results returned | PASS |
| T4 | POST /geocode cache hit — tiger still in local_results | PASS |
| T5 | POST /validate cache miss — scourgify+tiger results returned | PASS |
| T6 | POST /validate cache hit — tiger still in local_candidates | PASS |
| T7 | Tiger geocode confidence in [0.0, 1.0] | PASS |
| T8 | Tiger validate returns USPS-normalized address | PASS |
| T9 | Local bypass: 1st call cache_hit=False, 2nd call cache_hit=True, local always fresh | PASS |
| T10 | Remote cache: Census not re-called after first geocode | PASS |

**10/10 PASS**

---

## Files Modified by UAT Fixes

| File | Change |
|------|--------|
| `src/civpulse_geo/services/geocoding.py` | Moved local provider calls before cache check; added db.refresh() after flush |
| `src/civpulse_geo/services/validation.py` | Moved local provider calls before cache check |
| `src/civpulse_geo/schemas/geocoding.py` | Added `local_results: list[GeocodeProviderResult] = []` to GeocodeResponse |
| `src/civpulse_geo/schemas/validation.py` | Added `local_candidates: list[ValidationCandidate] = []` to ValidateResponse |
| `src/civpulse_geo/api/geocoding.py` | Serialize local_results from service into GeocodeResponse |
| `src/civpulse_geo/api/validation.py` | Serialize local_candidates from service into ValidateResponse |
| `src/civpulse_geo/providers/openaddresses.py` | Added `_oa_data_available()` function |
| `src/civpulse_geo/main.py` | Changed OA registration to conditional (same pattern as NAD/Tiger) |

---

_Initial Verification: 2026-03-22T16:00:00Z by Claude (gsd-verifier)_
_Re-verification: 2026-03-24T13:30:00Z by Claude (automated UAT)_
