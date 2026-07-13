"""Cache semântico (embeddings locais + store vetorial)."""

from .semantic import CachedResponse, SemanticCache, get_cache

__all__ = ["CachedResponse", "SemanticCache", "get_cache"]
