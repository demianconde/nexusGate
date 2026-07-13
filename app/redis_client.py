"""Cliente Redis assíncrono compartilhado (cache semântico e rate limiting)."""

from __future__ import annotations

from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    """Retorna a conexão Redis única (lazy, pool interno do cliente)."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis
