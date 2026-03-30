"""Prometheus /metrics endpoint.

Uses generate_latest() with a plain FastAPI Response to avoid the
307 redirect issue from prometheus_client.make_asgi_app() (Pitfall 4).
"""
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
