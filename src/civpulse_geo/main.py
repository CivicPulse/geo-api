import asyncio
import signal
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from civpulse_geo.api import health, geocoding, validation, tiles, poi, route
from civpulse_geo.api.metrics import router as metrics_router
from civpulse_geo.config import settings as _app_settings
from civpulse_geo.database import AsyncSessionLocal
from civpulse_geo.middleware.metrics import MetricsMiddleware
from civpulse_geo.middleware.request_id import RequestIDMiddleware
from civpulse_geo.observability.logging import configure_logging
from civpulse_geo.observability.tracing import setup_tracing, teardown_tracing
from civpulse_geo.providers.registry import load_providers
from civpulse_geo.providers.census import CensusGeocodingProvider
from civpulse_geo.providers.scourgify import ScourgifyValidationProvider
from civpulse_geo.providers.openaddresses import (
    OAGeocodingProvider,
    OAValidationProvider,
    _oa_data_available,
)
from civpulse_geo.providers.tiger import (
    TigerGeocodingProvider,
    TigerValidationProvider,
    _tiger_extension_available,
)
from civpulse_geo.providers.nad import (
    NADGeocodingProvider,
    NADValidationProvider,
    _nad_data_available,
)
from civpulse_geo.providers.macon_bibb import (
    MaconBibbGeocodingProvider,
    MaconBibbValidationProvider,
    _macon_bibb_data_available,
)
from civpulse_geo.providers.nominatim import NominatimGeocodingProvider, _nominatim_reachable
from civpulse_geo.providers.valhalla import _valhalla_reachable
from civpulse_geo.spell import load_spell_corrector, rebuild_dictionary
from civpulse_geo.services.fuzzy import FuzzyMatcher
from civpulse_geo.services.llm_corrector import LLMAddressCorrector, _ollama_model_available


def _install_sigterm_handler() -> None:
    """Safety-net SIGTERM handler -- disposes async engine if lifespan cleanup is bypassed."""
    loop = asyncio.get_event_loop()

    def _handle_sigterm():
        loop.create_task(_sigterm_cleanup())

    try:
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    except NotImplementedError:
        pass  # Windows -- not applicable to K8s


async def _sigterm_cleanup() -> None:
    from civpulse_geo.database import engine as _engine

    logger.info("SIGTERM received -- disposing async engine (safety net)")
    await _engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Configure structured logging FIRST (before any logger.info)
    configure_logging(_app_settings)

    # 2. Set up OTel tracing (patcher already installed by configure_logging)
    from civpulse_geo.database import engine as _async_engine

    _tracer_provider = setup_tracing(app, _app_settings, _async_engine.sync_engine)

    logger.info("Starting CivPulse Geo API")
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    app.state.providers = load_providers({"census": CensusGeocodingProvider})
    app.state.validation_providers = load_providers({"scourgify": ScourgifyValidationProvider})
    # OA providers (conditional on data presence in openaddresses_points table)
    if await _oa_data_available(AsyncSessionLocal):
        app.state.providers["openaddresses"] = OAGeocodingProvider(AsyncSessionLocal)
        app.state.validation_providers["openaddresses"] = OAValidationProvider(AsyncSessionLocal)
        logger.info("OpenAddresses provider registered")
    else:
        logger.warning(
            "openaddresses_points table is empty — OpenAddresses provider not registered"
        )
    # Tiger providers (conditional on PostGIS Tiger extension availability)
    if await _tiger_extension_available(AsyncSessionLocal):
        app.state.providers["postgis_tiger"] = TigerGeocodingProvider(AsyncSessionLocal)
        app.state.validation_providers["postgis_tiger"] = TigerValidationProvider(AsyncSessionLocal)
        logger.info("Tiger geocoder provider registered")
    else:
        logger.warning(
            "postgis_tiger_geocoder extension not available — Tiger provider not registered"
        )
    # NAD providers (conditional on data presence in nad_points table)
    if await _nad_data_available(AsyncSessionLocal):
        app.state.providers["national_address_database"] = NADGeocodingProvider(AsyncSessionLocal)
        app.state.validation_providers["national_address_database"] = NADValidationProvider(AsyncSessionLocal)
        logger.info("NAD provider registered")
    else:
        logger.warning(
            "nad_points table is empty — NAD provider not registered"
        )
    # Macon-Bibb providers (conditional on data presence in macon_bibb_points table)
    if await _macon_bibb_data_available(AsyncSessionLocal):
        app.state.providers["macon_bibb"] = MaconBibbGeocodingProvider(AsyncSessionLocal)
        app.state.validation_providers["macon_bibb"] = MaconBibbValidationProvider(AsyncSessionLocal)
        logger.info("Macon-Bibb provider registered")
    else:
        logger.warning(
            "macon_bibb_points table is empty — Macon-Bibb provider not registered"
        )
    # Nominatim provider (conditional on HTTP health probe + toggle) — GEO-01, GEO-05
    if _app_settings.nominatim_enabled:
        if await _nominatim_reachable(_app_settings.osm_nominatim_url, app.state.http_client):
            app.state.providers["nominatim"] = NominatimGeocodingProvider(app.state.http_client)
            logger.info("Nominatim provider registered")
        else:
            logger.warning(
                "nominatim unreachable at {} — Nominatim provider not registered",
                _app_settings.osm_nominatim_url,
            )
    else:
        logger.info("Nominatim provider disabled via settings.nominatim_enabled=False")
    # Valhalla routing sidecar (conditional on HTTP health probe + toggle) — ROUTE-01, ROUTE-02
    if _app_settings.valhalla_enabled:
        if await _valhalla_reachable(_app_settings.osm_valhalla_url, app.state.http_client):
            app.state.valhalla_enabled = True
            logger.info("Valhalla routing enabled at {}", _app_settings.osm_valhalla_url)
        else:
            app.state.valhalla_enabled = False
            logger.warning(
                "valhalla unreachable at {} — routing disabled",
                _app_settings.osm_valhalla_url,
            )
    else:
        app.state.valhalla_enabled = False
        logger.info("Valhalla routing disabled via settings.valhalla_enabled=False")
    logger.info(f"Loaded {len(app.state.providers)} geocoding provider(s)")
    logger.info(f"Loaded {len(app.state.validation_providers)} validation provider(s)")

    # Load spell corrector dictionary into memory (D-09)
    # Uses a sync engine since SymSpell.create_dictionary_entry is synchronous.
    # Workers reload dictionary on restart to pick up new rebuilds.
    # Auto-rebuilds when empty if staging tables have data (DEBT-03, D-07, D-08).
    try:
        from sqlalchemy import create_engine as _create_sync_engine
        from sqlalchemy import text as _text
        from civpulse_geo.config import settings as _settings
        import time as _time

        _sync_engine = _create_sync_engine(_settings.database_url_sync)
        with _sync_engine.connect() as conn:
            # Check if spell_dictionary is empty (DEBT-03, D-07, D-08)
            dict_count = conn.execute(
                _text("SELECT COUNT(*) FROM spell_dictionary")
            ).scalar()

            if dict_count == 0:
                # Check if any staging table has data before rebuilding
                staging_count = conn.execute(_text(
                    "SELECT (SELECT COUNT(*) FROM openaddresses_points) "
                    "+ (SELECT COUNT(*) FROM nad_points) "
                    "+ (SELECT COUNT(*) FROM macon_bibb_points)"
                )).scalar()

                if staging_count and staging_count > 0:
                    logger.info(
                        "spell_dictionary empty — auto-rebuilding from staging tables..."
                    )
                    _t0 = _time.monotonic()
                    word_count = rebuild_dictionary(conn)
                    _elapsed_ms = round((_time.monotonic() - _t0) * 1000)
                    logger.info(
                        "spell_dictionary rebuilt: {} words in {}ms",
                        word_count, _elapsed_ms,
                    )
                else:
                    logger.warning(
                        "spell_dictionary empty and staging tables empty "
                        "— skipping auto-rebuild"
                    )

            app.state.spell_corrector = load_spell_corrector(conn)
        loaded_count = len(app.state.spell_corrector._sym_spell.words)
        logger.info(f"SpellCorrector loaded with {loaded_count} dictionary words")
    except Exception as e:
        logger.warning(f"SpellCorrector not loaded: {e}")
        app.state.spell_corrector = None

    # Register FuzzyMatcher (FUZZ-02/03/04) — stateless init, no try/except needed
    app.state.fuzzy_matcher = FuzzyMatcher(AsyncSessionLocal)
    logger.info("FuzzyMatcher registered")

    # Initialize LLM corrector (LLM-01, D-09, D-13)
    from civpulse_geo.config import settings as _settings
    app.state.llm_corrector = None
    if _settings.cascade_llm_enabled:
        try:
            available = await _ollama_model_available(
                _settings.ollama_url,
                app.state.http_client,
                "qwen2.5:3b",
            )
            if available:
                app.state.llm_corrector = LLMAddressCorrector(
                    ollama_url=_settings.ollama_url,
                )
                logger.info("LLM corrector registered (qwen2.5:3b)")
            else:
                logger.warning("Ollama model qwen2.5:3b not available — LLM stage disabled")
        except Exception as e:
            logger.warning(f"LLM corrector not loaded: {e}")

    # Install SIGTERM handler as belt-and-suspenders (D-10)
    _install_sigterm_handler()

    yield

    # Shutdown sequence (D-12): preStop sleep handled by K8s, then SIGTERM arrives,
    # uvicorn drains in-flight requests, then lifespan shutdown runs.
    logger.info("Shutting down CivPulse Geo API")
    await app.state.http_client.aclose()
    logger.info("HTTP client closed")

    teardown_tracing(_tracer_provider)

    from civpulse_geo.database import engine as _async_engine
    await _async_engine.dispose()
    logger.info("Async engine disposed -- shutdown complete")


app = FastAPI(
    title="CivPulse Geo API",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware registered at app-definition time (not in lifespan)
# so it is available during all requests including test client startup.
# Starlette middleware is LIFO: MetricsMiddleware added last, executes first —
# sees the full request duration before RequestIDMiddleware runs.
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: converts unhandled exceptions to structured 500 JSON.

    Prevents raw tracebacks from reaching the client (STAB-01, STAB-02).
    Specific exception types (ValueError -> 404, ProviderError -> 422)
    are still caught by individual endpoints before this handler fires.
    """
    logger.error("Unhandled exception on {}: {}", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(health.router)
app.include_router(geocoding.router)
app.include_router(validation.router)
app.include_router(metrics_router)
app.include_router(tiles.router)
app.include_router(poi.router)
app.include_router(route.router)
