import asyncio
import os
import subprocess
from functools import lru_cache
from importlib.metadata import metadata

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.config import settings
from civpulse_geo.database import get_db
from civpulse_geo.providers.nominatim import _nominatim_reachable
from civpulse_geo.providers.tile_server import _tile_server_reachable
from civpulse_geo.providers.valhalla import _valhalla_reachable

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


@lru_cache(maxsize=1)
def _min_ready_geocoding_providers() -> int:
    return max(1, int(os.environ.get("MIN_READY_GEOCODING_PROVIDERS", "1")))


@lru_cache(maxsize=1)
def _min_ready_validation_providers() -> int:
    return max(1, int(os.environ.get("MIN_READY_VALIDATION_PROVIDERS", "1")))


async def _probe_sidecars() -> dict[str, str]:
    """Non-blocking sidecar readiness probes for /health/ready.

    Returns a dict with keys nominatim, tile_server, valhalla whose values
    are 'ready' | 'unavailable' | 'disabled'. 1s timeout per probe.
    Sidecar failures do NOT affect the overall readiness status.
    """
    async with httpx.AsyncClient() as client:
        # nominatim
        if not settings.nominatim_enabled:
            nom_task = None
        else:
            nom_task = _nominatim_reachable(settings.osm_nominatim_url, client, timeout_s=1.0)
        # tile_server (no enable flag — always probed live)
        tile_task = _tile_server_reachable(settings.osm_tile_url, client, timeout_s=1.0)
        # valhalla
        if not settings.valhalla_enabled:
            val_task = None
        else:
            val_task = _valhalla_reachable(settings.osm_valhalla_url, client, timeout_s=1.0)

        # Gather only the tasks that are not None
        to_run = [t for t in (nom_task, tile_task, val_task) if t is not None]
        results_iter = iter(await asyncio.gather(*to_run, return_exceptions=True))

        def _interpret(result: object) -> str:
            if isinstance(result, Exception):
                return "unavailable"
            return "ready" if result else "unavailable"

        out: dict[str, str] = {}
        out["nominatim"] = "disabled" if nom_task is None else _interpret(next(results_iter))
        out["tile_server"] = _interpret(next(results_iter))
        out["valhalla"] = "disabled" if val_task is None else _interpret(next(results_iter))
        return out


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
    """Readiness probe -- DB connected AND minimum provider thresholds met."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "reason": f"db: {exc}"},
        )
    geo_count = len(request.app.state.providers)
    val_count = len(request.app.state.validation_providers)
    min_geo = _min_ready_geocoding_providers()
    min_val = _min_ready_validation_providers()
    if geo_count < min_geo or val_count < min_val:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "geocoding_providers": geo_count,
                "validation_providers": val_count,
                "minimum_geocoding_providers": min_geo,
                "minimum_validation_providers": min_val,
                "reason": "insufficient providers",
            },
        )
    sidecars = await _probe_sidecars()
    return {
        "status": "ready",
        "geocoding_providers": geo_count,
        "validation_providers": val_count,
        "minimum_geocoding_providers": min_geo,
        "minimum_validation_providers": min_val,
        "sidecars": sidecars,
    }
