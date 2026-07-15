"""Script local para popular o dashboard com dados simulados.

Conecta direto ao banco via DATABASE_URL do .env e insere usage_logs.
Uso: python scripts/seed_local.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

# Adiciona o diretorio do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import AegisApiKey, Tenant, UsageLog
from app.db.session import SessionLocal


async def main():
    async with SessionLocal() as db:
        # Verifica se temos um tenant dev
        from sqlalchemy import select
        result = await db.execute(select(Tenant).limit(1))
        tenant = result.scalars().first()
        if not tenant:
            print("Nenhum tenant encontrado. Execute o app em modo dev primeiro.")
            return

        # Busca chave de API
        result = await db.execute(
            select(AegisApiKey).where(AegisApiKey.tenant_id == tenant.id).limit(1)
        )
        api_key = result.scalars().first()

        now = datetime.now(UTC)
        start = now - timedelta(days=14)
        inserted = 0
        cache_hits = 0
        total_tokens = 0

        print(f"Tenant: {tenant.id} ({tenant.name})")
        print("Inserindo 250 usage_logs nos ultimos 14 dias...")

        for _ in range(250):
            day_offset = random.randint(0, 13)
            req_date = start + timedelta(days=day_offset)
            if req_date.weekday() >= 5 and random.random() > 0.3:
                continue

            hour = random.randint(11, 23)
            req_ts = req_date.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))

            r = random.random()
            if r < 0.6:
                provider, model = random.choice([
                    ("openai", "gpt-4o-mini"), ("anthropic", "claude-3-5-haiku"),
                    ("google", "gemini-2.5-flash"),
                ])
                pt, ct = random.randint(50, 500), random.randint(30, 300)
                cost = round((pt * 0.15 + ct * 0.6) / 1_000_000, 8)
            elif r < 0.9:
                provider, model = random.choice([
                    ("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet"),
                    ("deepseek", "deepseek-chat"),
                ])
                pt, ct = random.randint(200, 2000), random.randint(100, 1000)
                cost = round((pt * 5 + ct * 15) / 1_000_000, 8)
            else:
                provider, model = random.choice([
                    ("openai", "gpt-4o"), ("google", "gemini-2.5-pro"),
                ])
                pt, ct = random.randint(500, 5000), random.randint(200, 3000)
                cost = round((pt * 5 + ct * 15) / 1_000_000, 8)

            cache_hit = r < 0.35 and random.random() < 0.2
            baseline = round((pt * 5 + ct * 15) / 1_000_000, 8)
            saved = max(0.0, round(baseline - cost, 8))
            if cache_hit:
                saved = baseline
                cost = 0.0

            log = UsageLog(
                tenant_id=tenant.id,
                api_key_id=api_key.id if api_key else None,
                request_id=uuid.uuid4().hex[:32],
                provider=provider,
                model_requested=model,
                model_used=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                cost_usd=cost,
                cost_saved_usd=saved,
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
        print(f"\n✅ {inserted} registros inseridos!")
        print(f"   Tokens: {total_tokens:,}")
        print(f"   Cache hits: {cache_hits} ({round(cache_hits/inserted*100, 1)}%)")
        print("   Acesse: https://aegisflow.tech/dashboard")


if __name__ == "__main__":
    asyncio.run(main())