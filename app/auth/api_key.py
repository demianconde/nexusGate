"""Chaves de API do NexusGate (x-api-key) usadas pelas apps clientes.

Formato: ``nxg_<8 hex>.<segredo>``. Guardamos apenas o prefixo (para lookup) e o
hash SHA-256 da chave completa. O valor em claro só é mostrado uma vez, na criação.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NexusApiKey, Tenant
from app.db.session import get_db
from app.ratelimit import enforce_rate_limit

_PREFIX_NAMESPACE = "nxg_"


def generate_api_key() -> tuple[str, str, str]:
    """Gera (chave_completa, prefixo, hash). A chave completa não é persistida."""
    prefix = _PREFIX_NAMESPACE + secrets.token_hex(4)  # ex.: nxg_a1b2c3d4 (12 chars)
    secret = secrets.token_urlsafe(32)
    full_key = f"{prefix}.{secret}"
    return full_key, prefix, hash_key(full_key)


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def _parse_prefix(full_key: str) -> str | None:
    if not full_key.startswith(_PREFIX_NAMESPACE) or "." not in full_key:
        return None
    return full_key.split(".", 1)[0]


async def get_api_tenant(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Dependência do proxy: resolve o tenant a partir da x-api-key e aplica rate limit."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Header x-api-key é obrigatório"
        )

    prefix = _parse_prefix(x_api_key)
    if not prefix:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chave de API inválida")

    result = await db.execute(
        select(NexusApiKey).where(
            NexusApiKey.key_prefix == prefix,
            NexusApiKey.revoked_at.is_(None),
        )
    )
    key_record = result.scalar_one_or_none()
    # Comparação em tempo constante mesmo quando a chave não existe.
    expected_hash = key_record.key_hash if key_record else "0" * 64
    if key_record is None or not hmac.compare_digest(expected_hash, hash_key(x_api_key)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chave de API inválida")

    tenant = await db.get(Tenant, key_record.tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant inativo")

    await enforce_rate_limit(str(tenant.id), tenant.plan)
    return tenant
