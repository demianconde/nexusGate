"""Testes da política de e-mail no cadastro (anti-abuso do grátis)."""

from __future__ import annotations

from app.security.email_policy import email_domain, is_disposable_email


def test_email_domain_extracts_and_normalizes() -> None:
    assert email_domain("Fulano@Empresa.com.BR") == "empresa.com.br"
    assert email_domain("  user@gmail.com  ") == "gmail.com"


def test_email_domain_invalid_returns_empty() -> None:
    assert email_domain("sem-arroba") == ""
    assert email_domain("dois@arrobas@x.com") == ""
    assert email_domain("") == ""


def test_disposable_domains_are_blocked() -> None:
    assert is_disposable_email("abc@mailinator.com") is True
    assert is_disposable_email("x@guerrillamail.com") is True
    assert is_disposable_email("y@temp-mail.org") is True


def test_legitimate_domains_are_allowed() -> None:
    assert is_disposable_email("fulano@gmail.com") is False
    assert is_disposable_email("contato@empresa.com.br") is False


def test_invalid_email_treated_as_disposable() -> None:
    # Sem domínio válido → bloqueia por precaução.
    assert is_disposable_email("sem-arroba") is True
    assert is_disposable_email("") is True


def test_extra_domains_extend_blocklist() -> None:
    extra = {"minhalista.com"}
    assert is_disposable_email("a@minhalista.com", extra) is True
    # Sem os extras, o mesmo domínio passa.
    assert is_disposable_email("a@minhalista.com") is False


def test_case_insensitive_matching() -> None:
    assert is_disposable_email("a@MAILINATOR.COM") is True
