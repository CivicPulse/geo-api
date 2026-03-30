import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_shutdown_disposes_engine():
    """Verify lifespan shutdown calls engine.dispose() (RESIL-03, D-10)."""
    from civpulse_geo.main import app, lifespan

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    with patch("civpulse_geo.database.engine", mock_engine):
        # Use the lifespan context manager directly to trigger startup/shutdown
        async with lifespan(app):
            # We're inside lifespan -- do a quick liveness check via direct call
            # (lifespan is running, startup complete)
            pass
        # After exiting lifespan context, shutdown block runs
        mock_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_closes_http_client():
    """Verify lifespan shutdown closes http_client cleanly."""
    from civpulse_geo.main import app, lifespan

    with patch("civpulse_geo.database.engine", MagicMock(dispose=AsyncMock())):
        async with lifespan(app):
            # http_client should be set during startup
            assert hasattr(app.state, "http_client")
            http_client = app.state.http_client

        # After shutdown: http_client.aclose() was called; client is closed
        assert http_client.is_closed
