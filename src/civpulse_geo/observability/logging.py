"""Loguru structured logging configuration.

Configures Loguru with either a JSON sink (for K8s/production) or
human-readable colorized output (for local development).

The OTel trace_id/span_id patcher is installed by configure_logging()
via logger.configure(patcher=_add_otel_context). The patcher reads
get_current_span() lazily at log-emit time, so it is safe to install
before TracerProvider is initialized (produces empty strings until a
real span exists).
"""
import json
import os
import sys
from datetime import timezone

from loguru import logger
from opentelemetry import trace as otel_trace
from opentelemetry.trace import INVALID_SPAN_CONTEXT


def _add_otel_context(record: dict) -> None:
    """Patcher: inject trace_id and span_id from active OTel span.

    Called by Loguru for every log record. Reads get_current_span()
    lazily -- safe to register before TracerProvider is set up.
    Handles INVALID_SPAN_CONTEXT gracefully (Pitfall 7).
    """
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx != INVALID_SPAN_CONTEXT and ctx.trace_id != 0:
        record["extra"]["trace_id"] = format(ctx.trace_id, "032x")
        record["extra"]["span_id"] = format(ctx.span_id, "016x")
    else:
        record["extra"].setdefault("trace_id", "")
        record["extra"].setdefault("span_id", "")


def add_otel_patcher() -> None:
    """Register the OTel context patcher with Loguru.

    Call AFTER configure_logging() and AFTER logger.remove() / logger.add().
    The patcher injects trace_id/span_id into every log record.

    CRITICAL (Pitfall 2): This must be called after configure_logging()
    has already done logger.remove() and logger.add(). The patcher
    applies to all currently registered sinks.
    """
    logger.configure(patcher=_add_otel_context)


def _json_sink(message) -> None:
    """Custom JSON serializer for structured log output (D-01)."""
    record = message.record
    entry = {
        "timestamp": record["time"].astimezone(timezone.utc).isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "service": "civpulse-geo",
        "environment": record["extra"].get("environment", ""),
        "version": record["extra"].get("version", ""),
        "git_commit": record["extra"].get("git_commit", ""),
        "request_id": record["extra"].get("request_id", ""),
        "trace_id": record["extra"].get("trace_id", ""),
        "span_id": record["extra"].get("span_id", ""),
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }
    print(json.dumps(entry), flush=True)


def configure_logging(settings) -> None:
    """Configure Loguru with appropriate sink and OTel patcher.

    Order matters (Pitfall 2):
    1. logger.remove() -- clear default handler
    2. logger.configure(patcher=..., extra=...) -- set patcher and defaults
    3. logger.add(...) -- add sink(s) that benefit from the patcher

    The patcher reads get_current_span() lazily at emit time, so it is
    safe to install before TracerProvider exists.
    """
    logger.remove()

    logger.configure(
        patcher=_add_otel_context,
        extra={
            "environment": settings.environment,
            "version": getattr(
                settings, "git_commit", os.environ.get("GIT_COMMIT", "unknown")
            ),
            "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
            "request_id": "",
            "trace_id": "",
            "span_id": "",
        },
    )

    if settings.is_json_logging:
        logger.add(_json_sink, level=settings.log_level)
    else:
        logger.add(sys.stderr, level=settings.log_level)
