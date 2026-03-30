"""OpenTelemetry tracing setup for civpulse-geo.

Initializes TracerProvider with Resource attributes, BatchSpanProcessor,
and OTLP gRPC exporter. Auto-instruments FastAPI, SQLAlchemy, and httpx.

Per D-03:
- Auto-instrumentation for FastAPI, SQLAlchemy (asyncpg), httpx
- Tracer obtained via get_tracer("civpulse-geo")
- OTLP exporter via OTEL_EXPORTER_OTLP_ENDPOINT env var
- /health/live, /health/ready, /metrics excluded from tracing

CRITICAL PITFALLS (from research):
- SQLAlchemy instrumentation requires engine.sync_engine, NOT the async engine
- TracerProvider must be initialized in lifespan, not at module level
- provider.shutdown() must be called in lifespan teardown to flush BatchSpanProcessor
"""
import os

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(app, settings, sync_engine) -> TracerProvider | None:
    """Initialize OTel TracerProvider and auto-instrument FastAPI/SQLAlchemy/httpx.

    Args:
        app: FastAPI application instance.
        settings: Application settings with otel_enabled, otel_exporter_endpoint,
                  environment, and git_commit or GIT_COMMIT env var.
        sync_engine: SQLAlchemy sync engine (from async_engine.sync_engine).
                     MUST be sync engine -- async engine silently fails (Pitfall 3).

    Returns:
        TracerProvider instance (needed for teardown_tracing), or None if disabled.
    """
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing disabled (otel_enabled=False)")
        return None

    git_commit = os.environ.get("GIT_COMMIT", "unknown")

    resource = Resource(
        attributes={
            SERVICE_NAME: "civpulse-geo",
            SERVICE_VERSION: git_commit,
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI -- exclude health and metrics endpoints
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/health/live,/health/ready,/metrics",
    )

    # Auto-instrument SQLAlchemy -- MUST use sync_engine (Pitfall 3)
    SQLAlchemyInstrumentor().instrument(
        engine=sync_engine,
        service="civpulse-geo",
        enable_commenter=True,
    )

    # Auto-instrument httpx -- covers Census API and Ollama calls
    HTTPXClientInstrumentor().instrument()

    logger.info(
        "OpenTelemetry tracing initialized -- exporter endpoint: {}",
        settings.otel_exporter_endpoint,
    )
    return provider


def teardown_tracing(provider: TracerProvider | None) -> None:
    """Shut down TracerProvider, flushing any buffered spans.

    MUST be called in lifespan teardown before engine.dispose() (Pitfall 5).
    """
    if provider is not None:
        provider.shutdown()
        logger.info("OpenTelemetry TracerProvider shut down")
