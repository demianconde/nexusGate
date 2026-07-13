"""Camada de provedores de LLM (qualquer endpoint OpenAI-compatível ou Anthropic)."""

from .registry import KNOWN_PROVIDERS, is_local_url, resolve_endpoint
from .service import ProviderError, ProviderService

__all__ = [
    "KNOWN_PROVIDERS",
    "is_local_url",
    "resolve_endpoint",
    "ProviderError",
    "ProviderService",
]
