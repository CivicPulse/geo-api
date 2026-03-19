from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from civpulse_geo.api import health
from civpulse_geo.providers.registry import load_providers


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting CivPulse Geo API")
    app.state.providers = load_providers({})
    logger.info(f"Loaded {len(app.state.providers)} provider(s)")
    yield
    logger.info("Shutting down CivPulse Geo API")


app = FastAPI(
    title="CivPulse Geo API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
