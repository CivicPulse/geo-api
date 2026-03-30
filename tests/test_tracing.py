"""Tests for OpenTelemetry tracing setup (OBS-03)."""
import pytest
from unittest.mock import MagicMock, patch
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def memory_exporter():
    """Set up InMemorySpanExporter and TracerProvider for test verification.

    Uses the provider directly for span creation to avoid global TracerProvider
    override restrictions (OTel SDK warns when set_tracer_provider is called twice).
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter, provider
    exporter.clear()
    provider.shutdown()


def test_setup_tracing_returns_provider():
    """setup_tracing returns a TracerProvider instance."""
    from civpulse_geo.observability.tracing import setup_tracing

    settings = MagicMock()
    settings.otel_enabled = True
    settings.otel_exporter_endpoint = "http://localhost:4317"
    settings.environment = "test"

    app = MagicMock()
    sync_engine = MagicMock()

    with patch(
        "civpulse_geo.observability.tracing.FastAPIInstrumentor"
    ) as mock_fai, patch(
        "civpulse_geo.observability.tracing.SQLAlchemyInstrumentor"
    ) as mock_sai, patch(
        "civpulse_geo.observability.tracing.HTTPXClientInstrumentor"
    ) as mock_hci, patch(
        "civpulse_geo.observability.tracing.trace"
    ):
        provider = setup_tracing(app, settings, sync_engine)
        assert provider is not None
        assert isinstance(provider, TracerProvider)
        mock_fai.instrument_app.assert_called_once()
        mock_sai.return_value.instrument.assert_called_once()
        mock_hci.return_value.instrument.assert_called_once()
        provider.shutdown()


def test_setup_tracing_disabled_returns_none():
    """setup_tracing returns None when otel_enabled=False."""
    from civpulse_geo.observability.tracing import setup_tracing

    settings = MagicMock()
    settings.otel_enabled = False

    result = setup_tracing(MagicMock(), settings, MagicMock())
    assert result is None


def test_teardown_tracing_none_safe():
    """teardown_tracing handles None provider without error."""
    from civpulse_geo.observability.tracing import teardown_tracing

    teardown_tracing(None)  # should not raise


def test_tracer_creates_spans(memory_exporter):
    """A tracer obtained from the provider creates spans visible in exporter."""
    exporter, provider = memory_exporter
    # Use the provider directly to avoid global TracerProvider override issues
    tracer = provider.get_tracer("civpulse-geo")
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("test.key", "test-value")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test-span"
    assert spans[0].attributes["test.key"] == "test-value"


def test_excluded_urls_passed_to_fastapi_instrumentor():
    """FastAPIInstrumentor receives the excluded_urls string."""
    from civpulse_geo.observability.tracing import setup_tracing

    settings = MagicMock()
    settings.otel_enabled = True
    settings.otel_exporter_endpoint = "http://localhost:4317"
    settings.environment = "test"

    app = MagicMock()
    sync_engine = MagicMock()

    with patch(
        "civpulse_geo.observability.tracing.FastAPIInstrumentor"
    ) as mock_fai, patch(
        "civpulse_geo.observability.tracing.SQLAlchemyInstrumentor"
    ), patch(
        "civpulse_geo.observability.tracing.HTTPXClientInstrumentor"
    ), patch(
        "civpulse_geo.observability.tracing.trace"
    ):
        provider = setup_tracing(app, settings, sync_engine)
        call_kwargs = mock_fai.instrument_app.call_args
        assert "/health/live" in call_kwargs.kwargs.get("excluded_urls", "")
        assert "/health/ready" in call_kwargs.kwargs.get("excluded_urls", "")
        assert "/metrics" in call_kwargs.kwargs.get("excluded_urls", "")
        provider.shutdown()
