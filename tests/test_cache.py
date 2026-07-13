"""Testes do cache semântico (com embedder simulado, sem rede)."""

from __future__ import annotations

import pytest

from app.cache import semantic
from app.cache.semantic import CachedResponse, SemanticCache, _cosine, prompt_text
from app.config import get_settings


def test_cosine():
    assert _cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert _cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert _cosine([1, 0], []) == 0.0


def test_prompt_text():
    text = prompt_text([{"role": "system", "content": "a"}, {"role": "user", "content": "b"}])
    assert text == "a\nb"


async def test_cache_hit_and_miss(monkeypatch):
    get_settings.cache_clear()

    # embedder determinístico: vetor baseado na 1a letra
    async def fake_embed(text: str):
        return [1.0, 0.0] if text.startswith("ola") else [0.0, 1.0]

    monkeypatch.setattr(semantic, "embed", fake_embed)
    cache = SemanticCache()

    assert await cache.get("t1", "ola mundo") is None  # vazio → miss
    await cache.put("t1", "ola mundo", CachedResponse("oi!", "m", "p", 5, 3))

    hit = await cache.get("t1", "ola pessoal")  # mesmo vetor → hit
    assert hit is not None and hit.content == "oi!"

    assert await cache.get("t1", "xyz outro")  is None  # vetor diferente → miss
    assert await cache.get("t2", "ola mundo") is None  # tenant diferente → isolado
