"""Redação de PII (LGPD): mascara CPF, CNPJ, e-mail, telefone e cartão.

Usado para (a) nunca vazar PII em logs e (b) guardrail opcional que redige PII
antes de enviar a requisição a provedores **hospedados** (mantendo dados sensíveis
só em modelos locais).
"""

from __future__ import annotations

import re

# Ordem importa: padrões mais específicos primeiro.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("[CARTAO]", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("[CNPJ]", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")),
    ("[CPF]", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("[EMAIL]", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("[TELEFONE]", re.compile(r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[- ]?\d{4}\b")),
]


def redact_pii(text: str) -> str:
    out = text
    for token, pattern in _PATTERNS:
        out = pattern.sub(token, out)
    return out


def contains_pii(text: str) -> bool:
    return any(p.search(text) for _, p in _PATTERNS)


def redact_messages(messages: list[dict]) -> list[dict]:
    """Retorna cópia das mensagens com o conteúdo redigido."""
    return [{**m, "content": redact_pii(str(m.get("content", "")))} for m in messages]
