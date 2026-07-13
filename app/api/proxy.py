"""Plano de dados (auth por x-api-key).

Na Fase 1 expõe apenas /v1/whoami para validar autenticação, resolução de tenant e
rate limiting. O endpoint real /v1/chat/completions chega na Fase 2.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.api_key import get_api_tenant
from app.db.models import Tenant

router = APIRouter(prefix="/v1", tags=["proxy"])


@router.get("/whoami")
async def whoami(tenant: Tenant = Depends(get_api_tenant)) -> dict:
    """Retorna o tenant resolvido a partir da x-api-key (após passar pelo rate limit)."""
    return {"tenant_id": str(tenant.id), "tenant_name": tenant.name, "plan": tenant.plan}
