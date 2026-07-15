"""Endpoint de seed para popular o dashboard com dados simulados.

So funciona em dev mode (AEGIS_DEV_MODE=true + nao production).
Injeta usage_logs fake no banco com dados realistas de consumo.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase import get_current_user
from app.config import get_settings
from app.db.models import AegisApiKey, UsageLog
from app.db.session import get_db

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/seed")
async def seed_dashboard(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(14, ge=1, le=90),
    requests: int = Query(200, ge=10, le=10000),
) -> dict:
    """Popula o banco com usage_logs simulados para testar o dashboard.

    So funciona quando AEGIS_DEV_MODE=true e AEGIS_ENV != production.
    """
    settings = get_settings()
    if not settings.dev_bypass_enabled:
        raise HTTPException(
            status_code=403,
            detail="Seed so funciona em modo dev (AEGIS_DEV_MODE=true, nao production).",
        )

    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    tenant_id = user.tenant_id

    # Busca uma chave de API do tenant para associar aos logs
    keys_result = await db.execute(
        select(AegisApiKey).where(AegisApiKey.tenant_id == tenant_id).limit(1)
    )
    api_key = keys_result.scalars().first()
    api_key_id = api_key.id if api_key else None

    inserted = 0
    total_tokens = 0
    cache_hits = 0

    for _ in range(requests):
        day_offset = random.randint(0, days - 1)
        req_date = start + timedelta(days=day_offset)

        # Menos trafego em fins de semana
        if req_date.weekday() >= 5 and random.random() > 0.3:
            continue

        hour = random.randint(11, 23)
        req_ts = req_date.replace(
            hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59)
        )

        r = random.random()
        if r < 0.6:
            provider, model = random.choice([
                ("openai", "gpt-4o-mini"), ("anthropic", "claude-3-5-haiku"),
                ("google", "gemini-2.5-flash"), ("groq", "llama-3.1-8b"),
            ])
            pt = random.randint(50, 500)
            ct = random.randint(30, 300)
            cost = round((pt * 0.15 + ct * 0.6) / 1_000_000, 8)
        elif r < 0.9:
            provider, model = random.choice([
                ("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet"),
                ("deepseek", "deepseek-chat"), ("qwen", "qwen-plus"),
            ])
            pt = random.randint(200, 2000)
            ct = random.randint(100, 1000)
            cost = round((pt * 5 + ct * 15) / 1_000_000, 8)
        else:
            provider, model = random.choice([
                ("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet"),
                ("google", "gemini-2.5-pro"),
            ])
            pt = random.randint(500, 5000)
            ct = random.randint(200, 3000)
            cost = round((pt * 5 + ct * 15) / 1_000_000, 8)

        cache_hit = r < 0.3 and random.random() < 0.25
        baseline_cost = round((pt * 5 + ct * 15) / 1_000_000, 8)
        cost_saved = max(0.0, round(baseline_cost - cost, 8))
        if cache_hit:
            cost_saved = baseline_cost
            cost = 0.0

        log = UsageLog(
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            request_id=uuid.uuid4().hex[:32],
            provider=provider,
            model_requested=model,
            model_used=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_usd=cost,
            cost_saved_usd=cost_saved,
            cache_hit=cache_hit,
            status="ok",
            latency_ms=random.randint(80, 3000),
            ts=req_ts,
        )
        db.add(log)
        inserted += 1
        total_tokens += pt + ct
        if cache_hit:
            cache_hits += 1

    await db.commit()

    return {
        "inserted": inserted,
        "days": days,
        "total_tokens": total_tokens,
        "cache_hits": cache_hits,
        "cache_hit_rate": round(cache_hits / inserted * 100, 1) if inserted else 0,
        "tenant_id": str(tenant_id),
    }