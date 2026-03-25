from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from loguru import logger

from civpulse_geo.api import health, geocoding, validation
from civpulse_geo.database import AsyncSessionLocal
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    logger.info(f"Loaded {len(app.state.providers)} geocoding provider(s)")
    logger.info(f"Loaded {len(app.state.validation_providers)} validation provider(s)")
    yield
    await app.state.http_client.aclose()
    logger.info("Shutting down CivPulse Geo API")


app = FastAPI(
    title="CivPulse Geo API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(geocoding.router)
app.include_router(validation.router)
