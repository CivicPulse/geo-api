"""Loguru structured logging configuration.

Configures Loguru with either a JSON sink (for K8s/production) or
human-readable colorized output (for local development).

The OTel trace_id/span_id patcher is NOT wired here -- it is added
in Plan 02 after OTel TracerProvider is available. This module
provides configure_logging() which is safe to call before OTel setup.
"""
import json
import os
import sys
from datetime import timezone

from loguru import logger


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
    """Configure Loguru with appropriate sink based on settings.

    Must be called before any logger.info() calls in lifespan.
    Patcher for OTel context is added separately via add_otel_patcher().
    """
    logger.remove()  # Remove default handler

    # Bind service-level context that persists across all log calls
    logger.configure(
        extra={
            "environment": settings.environment,
            "version": getattr(
                settings, "git_commit", os.environ.get("GIT_COMMIT", "unknown")
            ),
            "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
            "request_id": "",
            "trace_id": "",
            "span_id": "",
        }
    )

    if settings.is_json_logging:
        logger.add(_json_sink, level=settings.log_level)
    else:
        logger.add(sys.stderr, level=settings.log_level)
