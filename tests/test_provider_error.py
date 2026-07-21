"""Testa a mensagem de erro do provedor repassada ao cliente (sem vazar segredos)."""

from __future__ import annotations

from app.api.chat import _provider_error_detail
from app.providers.service import ProviderError


def test_401_surfaces_status_and_hint():
    err = ProviderError(401, '{"error":{"message":"No auth credentials found"}}')
    d = _provider_error_detail(err)
    assert "401" in d
    assert "chave" in d.lower()  # dica sobre a chave da credencial


def test_404_model_hint():
    assert "Modelo não encontrado" in _provider_error_detail(ProviderError(404, "model not found"))


def test_generic_exception():
    d = _provider_error_detail(ValueError("boom"))
    assert "provedor" in d.lower()


def test_none_is_generic():
    assert _provider_error_detail(None)


def test_message_is_truncated():
    d = _provider_error_detail(ProviderError(400, "x" * 1000))
    assert len(d) < 300  # não despeja o corpo inteiro
