#!/usr/bin/env python3
"""Verify geo-api traces in Tempo.

Required port-forward:
  kubectl port-forward -n civpulse-infra svc/tempo 3200:3200

Success output:
  PASS: <n> traces found, sample trace <trace_id> has <m> spans
"""

import os
import sys
import time

import httpx


TEMPO_URL = os.environ.get("TEMPO_URL", "http://localhost:3200")
LOOKBACK_MINUTES = int(os.environ.get("VERIFY_LOOKBACK_MINUTES", "30"))


def _span_has_attribute(span: dict, key: str) -> bool:
    for attribute in span.get("attributes", []):
        if attribute.get("key") == key:
            return True
    return False


def _collect_spans(trace_payload: dict) -> list[dict]:
    spans: list[dict] = []
    for batch in trace_payload.get("batches", []):
        for scope_spans in batch.get("scopeSpans", []):
            spans.extend(scope_spans.get("spans", []))
    return spans


def _span_count(trace_id: str) -> tuple[int, list[dict]]:
    detail_response = httpx.get(f"{TEMPO_URL}/api/traces/{trace_id}", timeout=30.0)
    if detail_response.status_code != 200:
        print(
            f"FAIL: Tempo trace fetch returned HTTP {detail_response.status_code}: {detail_response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    spans = _collect_spans(detail_response.json())
    return len(spans), spans


def verify_tempo_traces() -> None:
    now = time.time()
    end_s = int(now)
    start_s = int(now - LOOKBACK_MINUTES * 60)

    response = httpx.get(
        f"{TEMPO_URL}/api/search",
        params={
            "tags": "service.name=civpulse-geo",
            "start": str(start_s),
            "end": str(end_s),
            "limit": "20",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        print(
            f"FAIL: Tempo search returned HTTP {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    traces = response.json().get("traces", [])
    if not traces:
        print(
            "FAIL: No traces found in Tempo for service.name=civpulse-geo",
            file=sys.stderr,
        )
        sys.exit(1)

    qualifying_trace_id = None
    qualifying_spans: list[dict] = []
    rejected: list[str] = []

    for trace in traces:
        trace_id = trace.get("traceID")
        if not trace_id:
            continue
        span_count, spans = _span_count(trace_id)
        if span_count >= 2:
            qualifying_trace_id = trace_id
            qualifying_spans = spans
            break
        rejected.append(f"{trace_id}:{trace.get('rootTraceName', '<unknown>')}:{span_count}")

    if qualifying_trace_id is None:
        print(
            "FAIL: No qualifying multi-span trace found in Tempo for service.name=civpulse-geo. "
            f"Checked {len(rejected)} traces: {', '.join(rejected[:5])}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not any(_span_has_attribute(span, "db.system") for span in qualifying_spans):
        print("WARN: No db.system span attribute found - DB auto-instrumentation may not be active")

    print(
        "PASS: "
        f"{len(traces)} traces found, sample trace {qualifying_trace_id} "
        f"has {len(qualifying_spans)} spans"
    )


if __name__ == "__main__":
    verify_tempo_traces()
