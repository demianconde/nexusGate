"""Testes de redação de PII (LGPD)."""

from __future__ import annotations

from app.security.pii import contains_pii, redact_messages, redact_pii


def test_redact_cpf_email_phone():
    t = "Meu CPF é 123.456.789-09, email joao@empresa.com.br, tel (11) 98765-4321"
    r = redact_pii(t)
    assert "123.456.789-09" not in r
    assert "joao@empresa.com.br" not in r
    assert "[CPF]" in r and "[EMAIL]" in r and "[TELEFONE]" in r


def test_contains_pii():
    assert contains_pii("cpf 123.456.789-09")
    assert not contains_pii("texto sem dados pessoais aqui")


def test_redact_messages_keeps_role():
    msgs = [{"role": "user", "content": "cnpj 12.345.678/0001-99"}]
    out = redact_messages(msgs)
    assert out[0]["role"] == "user"
    assert "[CNPJ]" in out[0]["content"]
