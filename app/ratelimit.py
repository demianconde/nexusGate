"""Rate limiting e quotas via Redis (janela fixa)."""

from __future__ import annotations

import time

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.config import get_settings
from app.logging_config import get_logger
from app.redis_client import get_redis

_log = get_logger("ratelimit")

_WINDOW_SECONDS = 60


def _on_redis_error(exc: RedisError, *, fail_open: bool = False) -> None:
    """Fail-open (segue) ou fail-closed (503), conforme configuração.

    ``fail_open=True`` força seguir mesmo em produção — usado em endpoints públicos
    (ex.: formulário de leads), onde é inaceitável retornar 503 só porque o Redis
    (anti-spam best-effort) está indisponível. Endpoints medidos (API/proxy) mantêm
    o padrão fail-closed em produção.
    """
    _log.warning("rate_limit_unavailable", error=str(exc))
    if not fail_open and get_settings().ratelimit_fail_closed_effective:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de limites indisponível.",
        ) from exc


async def enforce_minute(
    subject: str, rpm: int, label: str = "requisições", *, fail_open: bool = False
) -> None:
    """Limite por minuto para um 'subject' (tenant ou chave)."""
    now = int(time.time())
    key = f"rl:{subject}:{now // _WINDOW_SECONDS}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _WINDOW_SECONDS)
    except RedisError as exc:
        _on_redis_error(exc, fail_open=fail_open)
        return
    if count > rpm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limite de {label} por minuto excedido",
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )


async def enforce_signup_ip(ip: str, limit: int) -> None:
    """Teto de contas novas criadas a partir do mesmo IP por dia (anti-Sybil).

    Best-effort: se o Redis estiver indisponível, NÃO bloqueia o cadastro (não faz
    sentido barrar usuários legítimos por causa do rate limiter). ``limit <= 0``
    desativa a trava.
    """
    if limit <= 0:
        return
    now = int(time.time())
    key = f"signup:{ip}:{time.strftime('%Y%m%d', time.gmtime(now))}"
    try:
        redis = get_redis()
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, 24 * 3600)
    except RedisError as exc:
        _on_redis_error(exc, fail_open=True)
        return
    if used > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas contas criadas a partir deste endereço. Tente novamente mais tarde.",
            headers={"Retry-After": str(24 * 3600)},
        )


async def enforce_monthly_quota(tenant_id: str, quota: int, plan_label: str) -> None:
    """Quota mensal de requisições do tenant."""
    now = int(time.time())
    key = f"quota:{tenant_id}:{time.strftime('%Y%m', time.gmtime(now))}"
    try:
        redis = get_redis()
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, 31 * 24 * 3600)
    except RedisError as exc:
        _on_redis_error(exc)
        return
    if used > quota:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Quota mensal do plano '{plan_label}' excedida. Faça upgrade.",
        )
