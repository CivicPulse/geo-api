---
phase: 23-e2e-testing-load-baselines-and-final-validation
plan: "02"
subsystem: load-testing
tags: [locust, loadtests, baselines, performance]
completed: 2026-04-03
---

# Phase 23 Plan 02 Summary

Implemented the load-test scaffolding for cold-cache and warm-cache baseline capture.

## Delivered

- Added [`loadtests/geo_api_locustfile.py`](/home/kwhatcher/projects/civicpulse/geo-api/loadtests/geo_api_locustfile.py) with weighted geocode, validate, and cascade tasks.
- Added [`loadtests/addresses/cold_cache_addresses.txt`](/home/kwhatcher/projects/civicpulse/geo-api/loadtests/addresses/cold_cache_addresses.txt) with 30 seed addresses.
- Added [`loadtests/addresses/warm_cache_addresses.txt`](/home/kwhatcher/projects/civicpulse/geo-api/loadtests/addresses/warm_cache_addresses.txt) with 10 repeated addresses.
- Added [`loadtests/reports/.gitkeep`](/home/kwhatcher/projects/civicpulse/geo-api/loadtests/reports/.gitkeep).
- Added `locust` to dev dependencies in [`pyproject.toml`](/home/kwhatcher/projects/civicpulse/geo-api/pyproject.toml) and report ignores in [`.gitignore`](/home/kwhatcher/projects/civicpulse/geo-api/.gitignore).

## Verification

- `uv run python -m py_compile loadtests/geo_api_locustfile.py`
- `uv run python -c "import locust; print(locust.__version__)"`
- `wc -l loadtests/addresses/cold_cache_addresses.txt loadtests/addresses/warm_cache_addresses.txt`

## Outcome

The load-test assets are ready. Live baseline capture remains blocked on the deployed environments missing local provider data and failing Tempo exports.
