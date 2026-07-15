"""Endpoint de seed para popular o dashboard com dados simulados.

So funciona em dev mode (AEGIS_DEV_MODE=true + nao production).
Injeta usage_logs fake no banco com dados realistas de consumo.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase import get_current_user
from app.config import get_settings
from app.db.models import UsageLog
from app.db.session import get_db

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_MODELS = [
    ("openai", "gpt-4o-mini"),
    ("openai", "gpt-4o"),
    ("anthropic", "claude-3-5-haiku"),
    ("anthropic", "claude-3-5-sonnet"),
    ("google", "gemini-2.5-flash"),
    ("google", "gemini-2.5-pro"),
    ("qwen", "qwen-turbo"),
    ("deepseek", "deepseek-chat"),
    ("groq", "llama-3.1-8b"),
]


@router.post("/seed")
async def seed_dashboard(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = 14,
    requests: int = 200,
) -> dict:
    """Popula o banco com usage_logs simulados para testar o dashboard.

    So funciona quando AEGIS_DEV_MODE=true e AEGIS_ENV != production.
    Aceita parametros: ?days=14&requests=200
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
    from app.db.models import AegisApiKey

    keys_result = await db.execute(
        __import__("sqlalchemy").select(AegisApiKey).where(
            AegisApiKey.tenant_id == tenant_id
        ).limit(1)
    )
    api_key = keys_result.scalars().first()
    api_key_id = api_key.id if api_key else None

    inserted = 0
    total_tokens = 0
    cache_hits = 0

    # Distribui requisicoes ao longo dos dias com padrao realista:
    # - dias uteis tem mais trafego
    # - horario comercial concentrado
    for i in range(requests):
        # Dia aleatorio no periodo
        day_offset = random.randint(0, days - 1)
        req_date = start + timedelta(days=day_offset)

        # Mais trafego em dias uteis (seg-sex)
        if req_date.weekday() >= 5:  # sabado/domingo
            if random.random() > 0.3:  # 70% de chance de pular fim de semana
                continue

        # Horario comercial (8h-20h UTC-3 = 11h-23h UTC)
        hour = random.randint(11, 23)
        minute = random.randint(0, 59)
        req_ts = req_date.replace(hour=hour, minute=minute, second=random.randint(0, 59))

        # Distribuicao: 60% simples, 30% medio, 10% complexo
        r = random.random()
        if r < 0.6:
            # Simples: modelos baratos, poucos tokens
            provider, model = random.choice([
                ("openai", "gpt-4o-mini"),
                ("anthropic", "claude-3-5-haiku"),
                ("google", "gemini-2.5-flash"),
                ("groq", "llama-3.1-8b"),
            ])
            prompt_tokens = random.randint(50, 500)
            completion_tokens = random.randint(30, 300)
            cost = (prompt_tokens * 0.15 + completion_tokens * 0.6) / 1_000_000  # ~precos reais
        elif r < 0.9:
            # Medio: modelos medios
            provider, model = random.choice([
                ("openai", "gpt-4o"),
                ("anthropic", "claude-3-5-sonnet"),
                ("deepseek", "deepseek-chat"),
                ("qwen", "qwen-plus"),
            ])
            prompt_tokens = random.randint(200, 2000)
            completion_tokens = random.randint(100, 1000)
            cost = (prompt_tokens * 5 + completion_tokens * 15) / 1_000_000
        else:
            # Complexo: modelos premium
            provider, model = random.choice([
                ("openai", "gpt-4o"),
                ("anthropic", "claude-3-5-sonnet"),
                ("google", "gemini-2.5-pro"),
            ])
            prompt_tokens = random.randint(500, 5000)
            completion_tokens = random.randint(200, 3000)
            cost = (prompt_tokens * 5 + completion_tokens * 15) / 1_000_000

        # Alguns cache hits (mais comum em prompts simples repetidos)
        cache_hit = r < 0.3 and random.random() < 0.25  # ~7.5% de cache hit

        # Modelo baseline para calculo de economia (modelo mais caro)
        baseline_model = "gpt-4o"
        baseline_cost = (prompt_tokens * 5 + completion_tokens * 15) / 1_000_000
        cost_saved = max(0.0, baseline_cost - cost) if not cache_hit else baseline_cost

        log = UsageLog(
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            request_id=uuid.uuid4().hex[:32],
            provider=provider,
            model_requested=model,
            model_used=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(cost, 8),
            cost_saved_usd=round(cost_saved, 8),
            cache_hit=cache_hit,
            status="ok",
            latency_ms=random.randint(80, 3000),
            ts=req_ts,
        )
        db.add(log)
        inserted += 1
        total_tokens += prompt_tokens + completion_tokens
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