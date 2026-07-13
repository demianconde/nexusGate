"""Endpoints de healthcheck (liveness/readiness)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness — o processo está no ar."""
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness — dependências (banco) estão acessíveis."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
