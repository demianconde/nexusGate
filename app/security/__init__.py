"""Segurança: redação de PII (LGPD) e utilidades de guardrail."""

from .pii import contains_pii, redact_pii

__all__ = ["contains_pii", "redact_pii"]
