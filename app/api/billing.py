"""Endpoints de billing: plano atual, uso do mês, upgrade e webhook Stripe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase import get_current_user
from app.billing.plans import PLANS, get_plan
from app.billing.service import (
    create_checkout,
    monthly_request_count,
    set_plan,
    stripe_enabled,
)
from app.config import get_settings
from app.db.models import Tenant, User
from app.db.session import get_db
from app.logging_config import get_logger

router = APIRouter(prefix="/v1", tags=["billing"])
_log = get_logger("billing")


@router.get("/admin/billing")
async def get_billing(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant = await db.get(Tenant, user.tenant_id)
    plan = get_plan(tenant.plan)
    used = await monthly_request_count(db, user.tenant_id)
    return {
        "plan": plan.key,
        "plan_label": plan.label,
        "price_brl": plan.price_brl,
        "monthly_quota": plan.monthly_quota,
        "used_this_month": used,
        "rpm": plan.rpm,
        "stripe_enabled": stripe_enabled(),
        "plans": [
            {
                "key": p.key,
                "label": p.label,
                "price_brl": p.price_brl,
                "rpm": p.rpm,
                "monthly_quota": p.monthly_quota,
                "features": list(p.features),
            }
            for p in PLANS.values()
        ],
    }


@router.post("/admin/billing/plan")
async def change_plan(
    body: dict,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    plan_key = body.get("plan")
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail="Plano inválido.")
    tenant = await db.get(Tenant, user.tenant_id)
    is_paid = PLANS[plan_key].price_brl > 0
    settings = get_settings()

    if is_paid:
        # Plano pago exige pagamento: só via checkout Stripe.
        if stripe_enabled():
            origin = str(request.base_url).rstrip("/")
            checkout = await create_checkout(
                tenant, plan_key, f"{origin}/dashboard", f"{origin}/dashboard"
            )
            return {"status": "checkout", **checkout}
        # Sem Stripe: em produção NÃO libera de graça; em dev, aplica p/ testes.
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Pagamento não configurado. Contate o suporte para assinar.",
            )

    # Plano free (downgrade) ou dev sem Stripe: aplica direto.
    await set_plan(db, tenant, plan_key)
    return {"status": "applied", "plan": plan_key}


@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    payload = await request.body()
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Webhook não configurado."
        )

    import stripe  # lazy

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Assinatura inválida.") from exc

    if event["type"] in ("checkout.session.completed", "customer.subscription.updated"):
        data = event["data"]["object"]
        tenant_id = (data.get("metadata") or {}).get("tenant_id")
        plan = (data.get("metadata") or {}).get("plan")
        if tenant_id and plan in PLANS:
            import uuid as _uuid

            tenant = await db.get(Tenant, _uuid.UUID(tenant_id))
            if tenant:
                await set_plan(db, tenant, plan)
                _log.info("plan_updated", tenant_id=tenant_id, plan=plan)
    return {"received": True}
