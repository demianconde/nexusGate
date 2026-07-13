"""Rate limiting por tenant usando Redis (janela fixa por minuto)."""

from __future__ import annotations

import time

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.billing.plans import get_plan
from app.config import get_settings
from app.logging_config import get_logger
from app.redis_client import get_redis

_log = get_logger("ratelimit")

_WINDOW_SECONDS = 60


def _on_redis_error(exc: RedisError) -> None:
    """Fail-open (segue) ou fail-closed (503), conforme configuração."""
    _log.warning("rate_limit_unavailable", error=str(exc))
    if get_settings().ratelimit_fail_closed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de limites indisponível.",
        ) from exc


async def enforce_rate_limit(tenant_id: str, plan: str) -> None:
    """Rate limit por minuto (do plano) + quota mensal."""
    spec = get_plan(plan)
    now = int(time.time())
    minute_key = f"rl:{tenant_id}:{now // _WINDOW_SECONDS}"

    try:
        redis = get_redis()
        count = await redis.incr(minute_key)
        if count == 1:
            await redis.expire(minute_key, _WINDOW_SECONDS)
    except RedisError as exc:
        _on_redis_error(exc)
        return

    if count > spec.rpm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de requisições por minuto do plano excedido",
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )

    # Quota mensal (janela de ~31 dias).
    month_key = f"quota:{tenant_id}:{time.strftime('%Y%m', time.gmtime(now))}"
    try:
        used = await redis.incr(month_key)
        if used == 1:
            await redis.expire(month_key, 31 * 24 * 3600)
    except RedisError as exc:
        _on_redis_error(exc)
        return
    if used > spec.monthly_quota:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Quota mensal do plano '{spec.label}' excedida. Faça upgrade.",
        )
