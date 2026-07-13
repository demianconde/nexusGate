"""Auth do painel via Supabase.

Valida o JWT do usuário chamando o endpoint `/auth/v1/user` do Supabase e faz o
provisionamento (get-or-create) do tenant e do usuário no nosso banco.
"""

from __future__ import annotations

import httpx
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Tenant, User
from app.db.session import get_db

from .tokens import extract_bearer


async def verify_supabase_token(token: str) -> dict:
    """Valida o token contra o Supabase e retorna o objeto de usuário (id, email...)."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase não configurado (SUPABASE_URL / SUPABASE_ANON_KEY)",
        )

    endpoint = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(endpoint, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao contatar o Supabase",
        ) from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Supabase inválido"
        )
    return resp.json()


async def _get_or_create_user(db: AsyncSession, supabase_user: dict) -> User:
    """Vincula o usuário Supabase a um User/Tenant local, criando na primeira vez."""
    supabase_user_id = supabase_user.get("id")
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Usuário Supabase sem id")

    result = await db.execute(select(User).where(User.supabase_user_id == supabase_user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    email = supabase_user.get("email") or "novo-usuario"
    tenant_name = email.split("@")[0]
    tenant = Tenant(name=tenant_name)
    db.add(tenant)
    await db.flush()  # garante tenant.id

    user = User(supabase_user_id=supabase_user_id, tenant_id=tenant.id, role="owner")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependência: exige um usuário Supabase autenticado no painel."""
    token = extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization Bearer token é obrigatório",
        )
    supabase_user = await verify_supabase_token(token)
    return await _get_or_create_user(db, supabase_user)
