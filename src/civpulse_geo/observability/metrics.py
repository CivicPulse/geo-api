"""Prometheus metric definitions for civpulse-geo.

Three tiers per D-02:
  Tier 1: Standard HTTP metrics
  Tier 2: Geocoding service-specific metrics
  Tier 3: Business/LLM metrics

All metrics are created at import time and registered with the default
prometheus_client registry. The /metrics endpoint (api/metrics.py)
calls generate_latest() to expose them.
"""
from prometheus_client import Counter, Gauge, Histogram

# ---- Tier 1: Standard HTTP ----
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being processed",
)

# ---- Tier 2: Geocoding service ----
GEO_PROVIDER_REQUESTS_TOTAL = Counter(
    "geo_provider_requests_total",
    "Geocoding provider requests",
    ["provider", "status"],
)
GEO_PROVIDER_DURATION = Histogram(
    "geo_provider_duration_seconds",
    "Geocoding provider call duration",
    ["provider"],
)
GEO_CASCADE_STAGES_USED = Histogram(
    "geo_cascade_stages_used",
    "Number of cascade stages before result",
    buckets=[1, 2, 3, 4, 5, 6, 7],
)
GEO_CACHE_HITS_TOTAL = Counter("geo_cache_hits_total", "Geocoding cache hits")
GEO_CACHE_MISSES_TOTAL = Counter("geo_cache_misses_total", "Geocoding cache misses")

# ---- Tier 3: LLM / batch ----
GEO_LLM_CORRECTIONS_TOTAL = Counter(
    "geo_llm_corrections_total",
    "LLM address corrections",
    ["model"],
)
GEO_LLM_DURATION = Histogram(
    "geo_llm_duration_seconds",
    "LLM correction call duration",
)
GEO_BATCH_SIZE = Histogram(
    "geo_batch_size",
    "Batch endpoint request sizes",
    buckets=[1, 5, 10, 25, 50, 100],
)
