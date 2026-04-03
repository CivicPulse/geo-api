#!/usr/bin/env python3
"""Verify structured geo-api logs in Loki.

Required port-forward:
  kubectl port-forward -n civpulse-infra svc/loki 3100:3100

Success output:
  PASS: <n> log entries verified - all have request_id and trace_id
"""

import json
import os
import sys
import time

import httpx


LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100")
LOOKBACK_MINUTES = int(os.environ.get("VERIFY_LOOKBACK_MINUTES", "30"))


def verify_loki_logs() -> None:
    now = time.time()
    end_ns = int(now * 1e9)
    start_ns = int((now - LOOKBACK_MINUTES * 60) * 1e9)
    query = '{namespace="civpulse-prod"} | json | request_id != ""'

    response = httpx.get(
        f"{LOKI_URL}/loki/api/v1/query_range",
        params={
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": "100",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        print(
            f"FAIL: Loki query returned HTTP {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    results = response.json().get("data", {}).get("result", [])
    if not results:
        print(
            "FAIL: No logs found in Loki for namespace=civpulse-prod with request_id",
            file=sys.stderr,
        )
        sys.exit(1)

    verified = 0
    for stream in results:
        for _, line in stream.get("values", []):
            entry = json.loads(line)
            if "request_id" not in entry:
                print(f"FAIL: request_id missing from log entry: {entry}", file=sys.stderr)
                sys.exit(1)
            if "trace_id" not in entry:
                print(f"FAIL: trace_id missing from log entry: {entry}", file=sys.stderr)
                sys.exit(1)
            verified += 1

    print(f"PASS: {verified} log entries verified - all have request_id and trace_id")


if __name__ == "__main__":
    verify_loki_logs()
