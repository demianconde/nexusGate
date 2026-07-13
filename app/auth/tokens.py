"""Utilitários de parsing de tokens (header Authorization)."""

from __future__ import annotations


def extract_bearer(authorization: str | None) -> str | None:
    """Extrai o token de um header 'Authorization: Bearer <token>'.

    Parsing robusto (o protótipo usava split('Bearer') frágil). Retorna None se
    o header estiver ausente ou malformado.
    """
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None
