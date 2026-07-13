"""Testes de comportamento de auth que não precisam de banco/Redis ativos.

Verificam que as camadas rejeitam requisições sem credenciais ANTES de tocar em
qualquer dependência externa (banco/redis).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_proxy_requires_api_key() -> None:
    resp = client.get("/v1/whoami")
    assert resp.status_code == 401


def test_proxy_rejects_malformed_api_key() -> None:
    resp = client.get("/v1/whoami", headers={"x-api-key": "chave-sem-formato"})
    assert resp.status_code == 403


def test_admin_requires_bearer() -> None:
    resp = client.get("/v1/admin/me")
    assert resp.status_code == 401
