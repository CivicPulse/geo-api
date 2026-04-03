#!/usr/bin/env python3
"""Verify geo-api metrics in VictoriaMetrics.

Required port-forward:
  kubectl port-forward -n civpulse-infra pod/victoria-metrics-victoria-metrics-single-server-0 8428:8428

Success output:
  PASS: All 3 core metric families verified - http_requests_total, http_request_duration_seconds, geo_provider_requests_total
"""

import os
import sys

import httpx


VM_URL = os.environ.get("VICTORIAMETRICS_URL", "http://localhost:8428")


def query_vm(promql: str) -> dict:
    response = httpx.get(
        f"{VM_URL}/api/v1/query",
        params={"query": promql},
        timeout=30.0,
    )
    if response.status_code != 200:
        print(
            f"FAIL: VictoriaMetrics query returned HTTP {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    return response.json()


def assert_metric_exists(name: str, promql: str) -> list[dict]:
    data = query_vm(promql)
    result = data.get("data", {}).get("result", [])
    if not result:
        print(
            f"FAIL: Metric '{name}' returned no results for query: {promql}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result


def verify_victoriametrics() -> None:
    http_series = assert_metric_exists("http_requests_total", "http_requests_total")
    histogram_series = assert_metric_exists(
        "http_request_duration_seconds_bucket",
        "http_request_duration_seconds_bucket",
    )
    provider_series = assert_metric_exists(
        "geo_provider_requests_total",
        "geo_provider_requests_total",
    )

    p95_data = query_vm(
        "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
    ).get("data", {}).get("result", [])
    if p95_data:
        print(f"INFO: P95 latency sample = {p95_data[0].get('value')}")

    errors = query_vm('http_requests_total{status_code=~"5.."}').get("data", {}).get("result", [])
    print(f"INFO: 5xx series count = {len(errors)}")
    provider_names = sorted({
        series.get("metric", {}).get("provider", "")
        for series in provider_series
        if series.get("metric", {}).get("provider")
    })
    print(f"INFO: http_requests_total series = {len(http_series)}")
    print(f"INFO: http_request_duration_seconds_bucket series = {len(histogram_series)}")
    print(f"INFO: geo_provider_requests_total providers = {provider_names}")
    print(
        "PASS: All 3 core metric families verified - "
        "http_requests_total, http_request_duration_seconds, geo_provider_requests_total"
    )


if __name__ == "__main__":
    verify_victoriametrics()
