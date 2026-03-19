from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from loguru import logger

from civpulse_geo.api import health, geocoding, validation
from civpulse_geo.providers.registry import load_providers
from civpulse_geo.providers.census import CensusGeocodingProvider
from civpulse_geo.providers.scourgify import ScourgifyValidationProvider


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting CivPulse Geo API")
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    app.state.providers = load_providers({"census": CensusGeocodingProvider})
    logger.info(f"Loaded {len(app.state.providers)} provider(s)")
    app.state.validation_providers = load_providers({"scourgify": ScourgifyValidationProvider})
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
