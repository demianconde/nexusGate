"""Rate limiting por tenant usando Redis (janela fixa por minuto)."""

from __future__ import annotations

import time

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.logging_config import get_logger
from app.redis_client import get_redis

_log = get_logger("ratelimit")

# Requisições por minuto por plano.
PLAN_LIMITS: dict[str, int] = {
    "free": 60,
    "pro": 600,
    "enterprise": 6000,
}

_WINDOW_SECONDS = 60


async def enforce_rate_limit(tenant_id: str, plan: str) -> None:
    """Incrementa o contador do tenant na janela atual e bloqueia se exceder o plano."""
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    window = int(time.time()) // _WINDOW_SECONDS
    key = f"rl:{tenant_id}:{window}"

    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _WINDOW_SECONDS)
    except RedisError as exc:
        # Fail-open: sem Redis, não bloqueia (evita derrubar o proxy). Loga o incidente.
        _log.warning("rate_limit_unavailable", error=str(exc))
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de requisições do plano excedido",
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )
