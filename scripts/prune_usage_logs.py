"""Retenção de usage_logs — controle de custo (offline).

A tabela `usage_logs` cresce a cada requisição do proxy. Sem retenção, o
armazenamento do Postgres cresce indefinidamente — o principal custo variável do
plano grátis em escala. Este script apaga logs mais antigos que N dias.

Rode periodicamente (ex.: cron diário / GitHub Action agendada):
  python scripts/prune_usage_logs.py                  # apaga logs > 90 dias (padrão)
  python scripts/prune_usage_logs.py --days 30        # janela customizada
  python scripts/prune_usage_logs.py --dry-run        # só conta, não apaga

Observação: o dashboard de "Uso & Economia" mostra o mês corrente, então uma
janela de 90 dias preserva a experiência do usuário com folga.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Adiciona o diretório do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, func, select

from app.db.models import UsageLog
from app.db.session import SessionLocal

DEFAULT_DAYS = 90


async def prune(days: int, dry_run: bool) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with SessionLocal() as db:
        count = int(
            (await db.execute(select(func.count()).where(UsageLog.ts < cutoff))).scalar() or 0
        )
        if dry_run:
            print(f"[dry-run] {count} registros anteriores a {cutoff.isoformat()} seriam apagados.")
            return count
        if count:
            await db.execute(delete(UsageLog).where(UsageLog.ts < cutoff))
            await db.commit()
        print(f"✅ {count} registros anteriores a {cutoff.isoformat()} apagados.")
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Apaga usage_logs antigos (retenção de custo).")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="janela de retenção em dias")
    parser.add_argument("--dry-run", action="store_true", help="apenas conta, não apaga")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days deve ser >= 1")
    asyncio.run(prune(args.days, args.dry_run))


if __name__ == "__main__":
    main()
