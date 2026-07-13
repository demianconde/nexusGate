"""Grava linhas em usage_logs (sessão própria, seguro em fluxo de streaming)."""

from __future__ import annotations

import uuid

from app.db.models import UsageLog
from app.db.session import SessionLocal


async def record_usage(
    *,
    tenant_id: uuid.UUID,
    request_id: str,
    provider: str,
    model_requested: str,
    model_used: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    cost_saved_usd: float = 0.0,
    cache_hit: bool = False,
    latency_ms: int = 0,
) -> None:
    async with SessionLocal() as session:
        session.add(
            UsageLog(
                tenant_id=tenant_id,
                request_id=request_id,
                provider=provider,
                model_requested=model_requested,
                model_used=model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                cost_saved_usd=cost_saved_usd,
                cache_hit=cache_hit,
                latency_ms=latency_ms,
            )
        )
        await session.commit()
