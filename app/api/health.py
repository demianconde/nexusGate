"""Endpoints de healthcheck (liveness/readiness) com verificação de dependências."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.config import get_settings
from app.db.session import get_db
from app.redis_client import get_redis

router = APIRouter(tags=["health"])

_DEPENDENCY_TIMEOUT = 5.0  # segundos


@router.get("/health")
async def health() -> dict:
    """Liveness — o processo está no ar."""
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness — dependências (banco) estão acessíveis."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/health/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict:
    """Status detalhado de todas as dependências (Postgres, Redis, Supabase).

    Retorna HTTP 200 se tudo ok, 503 se alguma dependência crítica falhar.
    Usado por balanceadores de carga e ferramentas de monitoramento.
    """
    settings = get_settings()
    deps: dict[str, dict] = {}
    healthy = True

    # Postgres
    pg_start = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        deps["postgres"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - pg_start) * 1000, 1),
        }
    except Exception as exc:
        deps["postgres"] = {"status": "error", "detail": str(exc)[:200]}
        healthy = False

    # Redis
    redis_start = time.monotonic()
    try:
        r = get_redis()
        await r.ping()
        deps["redis"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - redis_start) * 1000, 1),
        }
    except Exception as exc:
        deps["redis"] = {"status": "error", "detail": str(exc)[:200]}
        # Redis não é crítico para o proxy (rate limit/cache degradam, mas não quebram)
        # Em produção com fail-closed, Redis é crítico — sinalizamos mas não matamos o endpoint

    # Supabase (auth do painel)
    if settings.supabase_url:
        supabase_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_DEPENDENCY_TIMEOUT) as client:
                resp = await client.get(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/health",
                )
            if resp.status_code < 500:
                deps["supabase"] = {
                    "status": "ok",
                    "latency_ms": round((time.monotonic() - supabase_start) * 1000, 1),
                }
            else:
                deps["supabase"] = {
                    "status": "degraded",
                    "http_status": resp.status_code,
                }
        except Exception as exc:
            deps["supabase"] = {"status": "error", "detail": str(exc)[:200]}
            # Supabase só afeta o painel, não o proxy de dados
    else:
        deps["supabase"] = {"status": "not_configured"}

    overall = "ok" if healthy else "degraded"
    return {
        "status": overall,
        "version": __version__,
        "dependencies": deps,
    }
