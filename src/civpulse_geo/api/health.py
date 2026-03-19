import os
import subprocess
from functools import lru_cache
from importlib.metadata import metadata

from fastapi import APIRouter, Depends, HTTPException
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
