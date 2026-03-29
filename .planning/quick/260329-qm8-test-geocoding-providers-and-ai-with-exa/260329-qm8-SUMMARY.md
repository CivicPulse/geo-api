---
phase: quick
plan: 260329-qm8
subsystem: geocoding-cascade
tags: [testing, cascade, geocoding, trace, delta-report, tiger-timeout]
dependency_graph:
  requires: [260329-q2v]
  provides: [cascade-re-run-report]
  affects: []
tech_stack:
  added: []
  patterns: [cascade-trace, provider-consensus, delta-analysis]
key_files:
  created:
    - .planning/quick/260329-qm8-test-geocoding-providers-and-ai-with-exa/GEOCODE-COMPARISON-REPORT.md
  modified: []
decisions:
  - "Tiger timeout (2000ms) in this run replaces prior run's wrong-county results — net positive for consensus accuracy; no code changes needed"
  - "LLM stage still disabled (Ollama not in docker compose ps without --profile llm) — address 4 unresolvable in both runs"
metrics:
  duration: "~10min"
  completed: "2026-03-29"
  tasks: 1
  files: 1
---

# Quick Task 260329-qm8: Test Geocoding Providers and AI — Re-run Summary

**One-liner:** Re-run of cascade trace for all 4 test addresses confirming stable official results; key delta is Tiger timing out (2000ms) instead of returning wrong-county outliers as in run 260329-q2v.

## What Was Done

Re-geocoded all 4 test addresses via `POST /geocode?trace=true` against http://localhost:8042. Captured fresh cascade trace data and generated GEOCODE-COMPARISON-REPORT.md comparing results against prior run 260329-q2v.

## Deviations from Plan

None — plan executed exactly as written. No bugs discovered or fixed.

## Key Findings

1. **Official results for addresses 1-3 identical to prior run (260329-q2v).** Census is official for addresses 1 and 2 (0.80 confidence); OpenAddresses is official for address 3 (0.40 confidence via 3-way cluster).

2. **Tiger provider times out on all 4 requests (2000ms).** In run 260329-q2v, Tiger returned wrong-county results for addresses 1 and 3 (outliers at 112km and 185km from correct location). In this run, Tiger is absent from all responses. The consensus engine's `outlier_providers` list is `[]` for all addresses — no outliers to filter. Official results are unaffected.

3. **Address 4 still unresolvable** without LLM sidecar. Both deterministic stages (exact_match=0 candidates, fuzzy_match=no candidates above threshold) exhaust without correction. Bug fixes from 260329-q2v (state VARCHAR guard, ST_Y geography cast) confirmed stable — no new HTTP 500 crashes.

4. **Spell dictionary empty** — `spell_corrected=true` flag in traces reflects corrector availability, not applied corrections. Applies to all 4 addresses. No change from prior run.

5. **LLM stage disabled** — `CASCADE_LLM_ENABLED=false` by default. Ollama requires `--profile llm` flag. No change from prior run.

## Self-Check: PASSED

- FOUND: .planning/quick/260329-qm8-test-geocoding-providers-and-ai-with-exa/GEOCODE-COMPARISON-REPORT.md
- FOUND: commit 5d67294
