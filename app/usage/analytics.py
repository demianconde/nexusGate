"""Agregação de uso por LLM + comparação de custo (economia auditável).

O custo é recomputado a partir dos tokens usando o catálogo de preços atual — assim,
ajustar o catálogo corrige os valores retroativamente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageLog
from app.routing.pricing import cost_usd, price_of


async def key_month_spend(db: AsyncSession, api_key_id: uuid.UUID) -> float:
    """Gasto (USD) atribuído a uma chave no mês corrente."""
    now = datetime.now(UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    stmt = select(func.coalesce(func.sum(UsageLog.cost_usd), 0)).where(
        UsageLog.api_key_id == api_key_id, UsageLog.ts >= start
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def recent_logs(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    model: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Logs de requisição recentes do tenant (para a aba de observabilidade)."""
    stmt = select(UsageLog).where(UsageLog.tenant_id == tenant_id)
    if model:
        stmt = stmt.where(UsageLog.model_used == model)
    if status:
        stmt = stmt.where(UsageLog.status == status)
    stmt = stmt.order_by(UsageLog.ts.desc()).limit(min(limit, 200)).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "request_id": r.request_id,
            "ts": r.ts.isoformat() if r.ts else None,
            "provider": r.provider,
            "model_used": r.model_used,
            "status": r.status,
            "cache_hit": r.cache_hit,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_usd": float(r.cost_usd),
            "latency_ms": r.latency_ms,
            "prompt_preview": r.prompt_preview,
            "response_preview": r.response_preview,
        }
        for r in rows
    ]


async def usage_summary(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    stmt = (
        select(
            UsageLog.provider,
            UsageLog.model_used,
            func.count().label("requests"),
            func.coalesce(func.sum(UsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(UsageLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(UsageLog.cost_saved_usd), 0).label("cost_saved"),
        )
        .where(UsageLog.tenant_id == tenant_id)
        .group_by(UsageLog.provider, UsageLog.model_used)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(stmt)).all()

    per_model = []
    total_prompt = 0
    total_completion = 0
    total_requests = 0
    total_cost = 0.0
    total_saved = 0.0
    for provider, model, requests, prompt_tokens, completion_tokens, cost_saved in rows:
        prompt_tokens = int(prompt_tokens)
        completion_tokens = int(completion_tokens)
        cost = cost_usd(model, prompt_tokens, completion_tokens)
        inp, out = price_of(model)
        saved = float(cost_saved)
        per_model.append(
            {
                "provider": provider,
                "model": model,
                "requests": int(requests),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_usd": round(cost, 6),
                "cost_saved_usd": round(saved, 6),
                "priced": (inp > 0 or out > 0),
            }
        )
        total_prompt += prompt_tokens
        total_completion += completion_tokens
        total_requests += int(requests)
        total_cost += cost
        total_saved += saved

    return {
        "per_model": per_model,
        "totals": {
            "requests": total_requests,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "cost_usd": round(total_cost, 6),
            "cost_saved_usd": round(total_saved, 6),
        },
    }


async def monthly_projection(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    """Projecao de consumo: custo real vs custo se tudo rodasse no modelo mais caro.

    Retorna dados diarios do mes corrente para grafico de barras/linha:
    - custo_real_diario: o que realmente gastou (com roteamento + cache)
    - custo_projetado_diario: o que gastaria se todas as requisicoes usassem
      o modelo mais caro disponivel (sem roteamento, sem cache)
    - economia_diaria: diferenca entre os dois
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=UTC)

    # Busca todos os logs do mes corrente
    stmt = (
        select(UsageLog)
        .where(UsageLog.tenant_id == tenant_id, UsageLog.ts >= start_of_month)
        .order_by(UsageLog.ts.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Determina o modelo mais caro usado pelo tenant (baseline para projecao)
    most_expensive_model = "gpt-4o"  # default
    max_price = 0.0
    for r in rows:
        inp, out = price_of(r.model_used)
        total_price = inp + out
        if total_price > max_price:
            max_price = total_price
            most_expensive_model = r.model_used

    # Agrupa por dia
    days: dict[str, dict] = {}
    for r in rows:
        day_key = r.ts.strftime("%Y-%m-%d") if r.ts else now.strftime("%Y-%m-%d")
        if day_key not in days:
            days[day_key] = {
                "date": day_key,
                "real_cost": 0.0,
                "projected_cost": 0.0,
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cache_hits": 0,
            }
        d = days[day_key]
        d["real_cost"] += float(r.cost_usd)
        # Projecao: quanto custaria se usasse o modelo mais caro
        d["projected_cost"] += cost_usd(
            most_expensive_model, r.prompt_tokens, r.completion_tokens
        )
        d["requests"] += 1
        d["prompt_tokens"] += r.prompt_tokens
        d["completion_tokens"] += r.completion_tokens
        if r.cache_hit:
            d["cache_hits"] += 1

    # Preenche dias sem uso (para o grafico ficar continuo)
    daily_data = []
    current = start_of_month
    while current <= now:
        key = current.strftime("%Y-%m-%d")
        if key in days:
            d = days[key]
            d["saved"] = round(d["projected_cost"] - d["real_cost"], 6)
            daily_data.append(d)
        else:
            daily_data.append({
                "date": key,
                "real_cost": 0.0,
                "projected_cost": 0.0,
                "saved": 0.0,
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cache_hits": 0,
            })
        current += timedelta(days=1)

    # Totais do mes
    total_real = sum(d["real_cost"] for d in daily_data)
    total_projected = sum(d["projected_cost"] for d in daily_data)
    total_requests = sum(d["requests"] for d in daily_data)
    total_cache_hits = sum(d["cache_hits"] for d in daily_data)

    return {
        "baseline_model": most_expensive_model,
        "daily": daily_data,
        "totals": {
            "real_cost_usd": round(total_real, 6),
            "projected_cost_usd": round(total_projected, 6),
            "saved_usd": round(total_projected - total_real, 6),
            "savings_percent": round(
                ((total_projected - total_real) / total_projected * 100) if total_projected > 0 else 0, 1
            ),
            "requests": total_requests,
            "cache_hits": total_cache_hits,
            "cache_hit_rate": round(
                (total_cache_hits / total_requests * 100) if total_requests > 0 else 0, 1
            ),
        },
    }
