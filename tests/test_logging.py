"""Tests for structured JSON logging configuration (OBS-01)."""
import json

from loguru import logger

from civpulse_geo.observability.logging import configure_logging


class FakeSettings:
    log_level = "DEBUG"
    environment = "test"
    is_json_logging = True
    log_format = "json"


def test_json_sink_outputs_valid_json(capsys):
    """JSON sink produces valid JSON with all required fields."""
    settings = FakeSettings()
    configure_logging(settings)
    logger.info("test message")
    captured = capsys.readouterr()
    line = captured.out.strip().split("\n")[-1]
    entry = json.loads(line)
    assert entry["message"] == "test message"
    assert entry["service"] == "civpulse-geo"
    assert entry["level"] == "INFO"
    assert "timestamp" in entry
    assert "module" in entry
    assert "function" in entry
    assert "line" in entry
    # These will be empty strings until OTel patcher is added
    assert "trace_id" in entry
    assert "span_id" in entry
    assert "request_id" in entry
    assert "environment" in entry
    assert "git_commit" in entry


def test_json_sink_includes_environment(capsys):
    """JSON sink environment field matches settings.environment."""
    settings = FakeSettings()
    configure_logging(settings)
    logger.info("env check")
    captured = capsys.readouterr()
    line = captured.out.strip().split("\n")[-1]
    entry = json.loads(line)
    assert entry["environment"] == "test"


def test_text_mode_does_not_use_json(capsys):
    """Text mode writes to stderr, not stdout JSON."""
    settings = FakeSettings()
    settings.is_json_logging = False
    configure_logging(settings)
    logger.info("text mode")
    captured = capsys.readouterr()
    # JSON sink writes to stdout; text sink writes to stderr
    assert captured.out.strip() == "" or "text mode" not in captured.out
    # stderr should contain the message
    assert "text mode" in captured.err


def test_request_id_appears_in_json_log(capsys):
    """request_id bound via logger.contextualize appears in JSON output."""
    settings = FakeSettings()
    configure_logging(settings)
    with logger.contextualize(request_id="test-req-123"):
        logger.info("with request id")
    captured = capsys.readouterr()
    line = captured.out.strip().split("\n")[-1]
    entry = json.loads(line)
    assert entry["request_id"] == "test-req-123"
