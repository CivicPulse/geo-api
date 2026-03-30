"""Prometheus HTTP metrics middleware (Tier 1, D-02).

Records http_requests_total, http_request_duration_seconds, and
http_requests_in_progress for every non-health request.

Excludes /health/live, /health/ready, and /metrics from metrics
collection to avoid noise from K8s probes and scraper hits.
"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from civpulse_geo.observability.metrics import (
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
)

EXCLUDED_PATHS = {"/health/live", "/health/ready", "/metrics"}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        method = request.method
        path = request.url.path

        HTTP_REQUESTS_IN_PROGRESS.inc()
        start = time.monotonic()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.monotonic() - start
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status_code=status_code,
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=method,
                path=path,
            ).observe(duration)
            HTTP_REQUESTS_IN_PROGRESS.dec()

        return response
