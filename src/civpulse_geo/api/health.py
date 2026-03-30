import os
import subprocess
from functools import lru_cache
from importlib.metadata import metadata

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from civpulse_geo.database import get_db

router = APIRouter()

_pkg_meta = metadata("civpulse-geo")


@lru_cache(maxsize=1)
def _git_commit() -> str:
    sha = os.environ.get("GIT_COMMIT")
    if sha:
        return sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    info = {
        "name": _pkg_meta["Name"],
        "version": _pkg_meta["Version"],
        "description": _pkg_meta["Summary"],
        "authors": [_pkg_meta["Author-email"]],
        "commit": _git_commit(),
    }
    try:
        await db.execute(text("SELECT 1"))
        return {**info, "status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={**info, "status": "error", "database": f"unavailable: {exc}"},
        )


@router.get("/health/live")
async def health_live():
    """Liveness probe -- process-only, no external dependencies (RESIL-01)."""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(request: Request, db: AsyncSession = Depends(get_db)):
    """Readiness probe -- DB connected AND provider threshold met (RESIL-02)."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "reason": f"db: {exc}"},
        )
    geo_count = len(request.app.state.providers)
    val_count = len(request.app.state.validation_providers)
    if geo_count < 2 or val_count < 2:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "geocoding_providers": geo_count,
                "validation_providers": val_count,
                "reason": "insufficient providers",
            },
        )
    return {
        "status": "ready",
        "geocoding_providers": geo_count,
        "validation_providers": val_count,
    }
