"""Serviço de billing: uso mensal, troca de plano e integração Stripe (opcional).

Stripe é carregado sob demanda e só quando `STRIPE_SECRET_KEY` está configurado —
com suporte a **Pix/boleto/cartão** (BRL). Sem a chave, roda em modo dev: a troca
de plano é aplicada diretamente (sem cobrança), para desenvolvimento/testes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.plans import PLANS, get_plan
from app.config import get_settings
from app.db.models import Subscription, Tenant, UsageLog


async def monthly_request_count(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    stmt = select(func.count()).where(
        UsageLog.tenant_id == tenant_id, UsageLog.ts >= start
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def set_plan(db: AsyncSession, tenant: Tenant, plan_key: str) -> None:
    """Aplica o plano ao tenant (modo dev / pós-confirmação de pagamento)."""
    if plan_key not in PLANS:
        raise ValueError(f"Plano inválido: {plan_key}")
    tenant.plan = plan_key
    result = await db.execute(select(Subscription).where(Subscription.tenant_id == tenant.id))
    sub = result.scalars().first()
    if sub is None:
        sub = Subscription(tenant_id=tenant.id, plan=plan_key, status="active")
        db.add(sub)
    else:
        sub.plan = plan_key
        sub.status = "active"
    await db.commit()


def stripe_enabled() -> bool:
    return bool(get_settings().stripe_secret_key)


async def create_checkout(tenant: Tenant, plan_key: str, success_url: str, cancel_url: str) -> dict:
    """Cria uma sessão de checkout Stripe (Pix/boleto/cartão) ou responde em modo dev."""
    plan = get_plan(plan_key)
    if not stripe_enabled():
        return {
            "mode": "dev",
            "checkout_url": None,
            "message": "Stripe não configurado (modo dev).",
        }

    import stripe  # lazy: só quando configurado

    stripe.api_key = get_settings().stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card", "boleto", "pix"],
        line_items=[
            {
                "price_data": {
                    "currency": "brl",
                    "product_data": {"name": f"NexusGate {plan.label}"},
                    "unit_amount": int(plan.price_brl * 100),
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(tenant.id),
        metadata={"tenant_id": str(tenant.id), "plan": plan_key},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return {"mode": "stripe", "checkout_url": session.url}
