---
phase: 23-e2e-testing-load-baselines-and-final-validation
created: 2026-04-03T20:12:00Z
status: partial_pass
scope:
  - tempo
  - loki
  - victoriametrics
---

# Phase 23 Observability Report

## Summary

Observability validation is partially complete.

- `Loki` verification passed.
- `Tempo` export path appears active, but the validation script had to be hardened because Tempo search returns mixed one-span traces that are not suitable verification samples.
- `VictoriaMetrics` ingestion is still not working for `geo-api`; the app exposes the expected metrics locally, but the metrics backend is not scraping or storing them.

## Actions Taken

### OTLP endpoint remediation

Patched live `geo-api-config` in both `civpulse-dev` and `civpulse-prod` so tracing exports to:

- `http://tempo.civpulse-infra.svc.cluster.local:4317`

This replaced the broken short-hostname endpoint that was producing `StatusCode.UNAVAILABLE`.

### Live environment verification

Confirmed from fresh pods in both `dev` and `prod`:

- startup logs show `OpenTelemetry tracing initialized -- exporter endpoint: http://tempo.civpulse-infra.svc.cluster.local:4317`
- all 5 geocoding providers and all 5 validation providers load successfully
- `/health/ready` returns `status=ready`

### Tempo verifier hardening

Patched [scripts/verify/verify_tempo.py](/home/kwhatcher/projects/civicpulse/geo-api/scripts/verify/verify_tempo.py):

- before: it fetched the first trace from Tempo search and failed if that one trace had fewer than 2 spans
- after: it iterates through the returned traces, fetches details, and selects the first qualifying multi-span trace
- if no qualifying trace exists, it now reports that explicitly and prints the first few rejected trace ids/root names/span counts

This removes a false-negative caused by Tempo returning one-span client traces first.

## Current Findings

### Loki

`uv run python scripts/verify/verify_loki.py`

Result:

- `PASS: 8 log entries verified - all have request_id and trace_id`

Interpretation:

- structured logs are present in Loki
- request/trace correlation fields are present as expected

### Tempo

`uv run python scripts/verify/verify_tempo.py`

Result after patch:

- `FAIL: No qualifying multi-span trace found in Tempo for service.name=civpulse-geo ...`

Observed Tempo search behavior:

- Tempo search returns traces for `service.name=civpulse-geo`
- many of the returned traces are one-span roots such as:
  - `GET`
  - `connect`
  - `SELECT civpulse_geo_prod`
  - `SELECT civpulse_geo_dev`

One inspected trace payload showed a single `httpx` client span from an older build (`service.version=db536ee`).

Interpretation:

- the verifier logic is now correct
- trace data exists in Tempo
- the current search window/result ordering is dominated by one-span traces, so no qualifying multi-span sample was found during this run
- this is no longer a script-selection bug; it is now a trace-shape / trace-availability issue in live data

### VictoriaMetrics

`uv run python scripts/verify/verify_victoriametrics.py`

Result:

- `FAIL: Metric 'http_requests_total' returned no results for query: http_requests_total`

Direct validation showed:

- `geo-api` `/metrics` exposes:
  - `http_requests_total`
  - `http_request_duration_seconds_bucket`
  - `geo_provider_requests_total`
- querying VictoriaMetrics for `up` only returns infra jobs such as:
  - `cloudflared`
  - `kubernetes-cadvisor`
  - `kubernetes-nodes`
  - `postgres-exporter`
  - `traefik`
  - `zitadel`
- there is no visible `geo-api` scrape target in VictoriaMetrics

Interpretation:

- application metrics instrumentation is working
- VictoriaMetrics is not scraping `geo-api`
- this is a scrape/discovery/config gap, not an app instrumentation gap

## Root Cause Assessment

### Fixed

1. Broken OTLP endpoint in live config
2. False-negative Tempo verifier behavior that assumed the first trace was representative

### Still Open

1. Tempo does not currently present a qualifying multi-span trace sample within the verification search results
2. VictoriaMetrics scrape path for `geo-api` is absent or misconfigured

## Recommended Next Steps

### Tempo

1. Generate fresh traced request traffic that is known to emit nested spans.
2. Re-run the patched verifier against a shorter, more recent lookback window if needed.
3. If only one-span traces continue to appear, inspect instrumentation coverage and sampling/export behavior for request/server spans versus client/DB spans.

### VictoriaMetrics

1. Inspect the live scrape layer configuration (`VMAgent` / scrape config / relabel rules) in the infra stack.
2. Confirm whether `geo-api` pods or services have the annotations/labels expected by that scrape configuration.
3. Add or correct `geo-api` scrape discovery so the target appears in `up`.
4. Re-run `verify_victoriametrics.py` after confirming the target and metric families are present in VictoriaMetrics.

## Useful Evidence

### Metrics present on app endpoint

Direct scrape of `geo-api` `/metrics` showed:

- `http_requests_total{method="POST",path="/geocode",status_code="200"}`
- `http_request_duration_seconds_bucket{...}`
- `geo_provider_requests_total`

### Metrics absent in VictoriaMetrics

VictoriaMetrics `up` query returned only infra jobs and no `geo-api` target.

### Tempo search shape

Tempo `/api/search` for `service.name=civpulse-geo` returned traces rooted at:

- `GET`
- `connect`
- `SELECT civpulse_geo_prod`
- `SELECT civpulse_geo_dev`

Those traces were insufficient for the original verifier and remain insufficient for the hardened verifier because they are single-span results.
